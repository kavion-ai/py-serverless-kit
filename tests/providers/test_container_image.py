"""package.type: zip | image | auto - size limits, ECR (AWS) and ACR (Azure) image deploys."""

import json

import pytest

from py_serverless_kit.core.deployer import Deployer, DeployError
from py_serverless_kit.providers.base import Artifact
from py_serverless_kit.providers.container import (
    DOCKER_SOURCE,
    DOCKERFILE,
    MB,
    PackageLimits,
    plan_package,
)
from py_serverless_kit.providers.registry import get_provider

BASE = """
service: big
provider:
  name: {provider}
  {options}
package:
  type: {kind}
  {image}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: {{path: /hello, method: GET}}
  worker:
    handler: app.handlers.worker
    events:
      - schedule: {{rate: 5 minutes}}
"""


def config(provider="aws", kind="image", options="", image=""):
    return BASE.format(provider=provider, kind=kind, options=options, image=image)


def package(project, **kw):
    result = Deployer(project, echo=lambda _m: None, **{k: v for k, v in kw.items() if k == "package_type"}).package(
        skip_deps=True, strict=kw.get("strict", False)
    )
    return result, json.loads(result.tf_file.read_text("utf-8"))


def fake_artifact(size, unpacked, skip_deps=False):
    return Artifact(path=None, sha256="ab" * 32, sha256_b64="", size=size, unpacked_size=unpacked, skip_deps=skip_deps)


# --------------------------------------------------------------------------- AWS / ECR
def test_aws_image_renders_ecr_and_image_lambda(make_project):
    project = make_project(config(image="image: {keep: 5}"))
    result, tf = package(project)
    res = tf["resource"]

    assert result.package.type == "image"
    assert tf["terraform"]["required_providers"]["docker"]["source"] == DOCKER_SOURCE
    auth = tf["provider"]["docker"][0]["registry_auth"][0]
    assert "aws_ecr_authorization_token.registry.proxy_endpoint" in auth["address"]
    assert auth["password"] == "${data.aws_ecr_authorization_token.registry.password}"

    repo = res["aws_ecr_repository"]["functions"]
    assert repo["name"] == "big-dev-functions" and repo["force_delete"] is True
    policy = json.loads(res["aws_ecr_lifecycle_policy"]["functions"]["policy"])
    assert policy["rules"][0]["selection"]["countNumber"] == 5

    build = res["docker_image"]["function"]
    assert build["build"][0]["dockerfile"] == DOCKERFILE
    assert build["build"][0]["platform"] == "linux/amd64"
    # A single image manifest: with attestations BuildKit pushes an OCI index that Lambda rejects
    # ("The image manifest, config or layer media type ... is not supported").
    assert build["build"][0]["provenance"] == "false" and build["build"][0]["sbom"] == "false"
    assert build["name"].startswith("${aws_ecr_repository.functions.repository_url}:")

    for name in ("hello", "worker"):
        fn = res["aws_lambda_function"][name]
        assert fn["package_type"] == "Image"
        assert fn["image_uri"] == (
            "${aws_ecr_repository.functions.repository_url}@${docker_registry_image.function.sha256_digest}"
        )
        assert fn["image_config"] == [{"command": ["pskit_entry.handler"]}]
        for zip_only in ("handler", "runtime", "s3_bucket", "s3_key", "filename", "source_code_hash"):
            assert zip_only not in fn, zip_only
    assert "aws_s3_object" not in res  # no zip upload

    dockerfile = (project.work_dir / "build" / DOCKERFILE).read_text("utf-8")
    assert dockerfile.splitlines()[1] == "FROM public.ecr.aws/lambda/python:3.12"
    assert 'CMD ["pskit_entry.handler"]' in dockerfile
    assert "\r" not in dockerfile


def test_aws_image_tag_is_reproducible(make_project):
    project = make_project(config())
    _r, first = package(project)
    _r, second = package(project)
    assert first["resource"]["docker_image"]["function"]["triggers"] == second["resource"]["docker_image"]["function"]["triggers"]


def test_aws_existing_repository_and_arm64(make_project):
    yml = config(options="architecture: arm64", image="image: {repository: shared/lambdas, base_image: my/base:1, "
                                                       "dockerfile_lines: ['RUN echo hi']}")
    project = make_project(yml)
    _r, tf = package(project)
    assert tf["data"]["aws_ecr_repository"]["functions"] == {"name": "shared/lambdas"}
    assert "aws_ecr_repository" not in tf["resource"]
    assert tf["resource"]["docker_image"]["function"]["build"][0]["platform"] == "linux/arm64"
    text = (project.work_dir / "build" / DOCKERFILE).read_text("utf-8")
    assert "FROM my/base:1\nRUN echo hi\n" in text


def test_aws_image_rejects_mixed_architectures(make_project):
    yml = config().replace("handler: app.handlers.worker", "handler: app.handlers.worker\n    architecture: arm64")
    issues = make_project(yml).validate()
    assert any(i.level == "error" and "one architecture" in i.message for i in issues)


def test_package_type_flag_overrides_yaml(make_project):
    project = make_project(config(kind="zip"))
    result, tf = package(project, package_type="image")
    assert result.package.type == "image"
    assert tf["resource"]["aws_lambda_function"]["hello"]["package_type"] == "Image"


def test_auto_stays_zip_when_small(make_project):
    result, tf = package(make_project(config(kind="auto")))
    assert result.package.type == "zip"
    assert tf["resource"]["aws_lambda_function"]["hello"]["handler"] == "pskit_entry.handler"
    assert "docker" not in tf["terraform"]["required_providers"]


def test_auto_switches_to_image_over_the_limit(make_project, monkeypatch):
    aws = type(get_provider("aws"))
    monkeypatch.setattr(aws, "package_limits", PackageLimits(zip_compressed=1, zip_unpacked=1))
    result, tf = package(make_project(config(kind="auto")))
    assert result.package.type == "image"
    assert tf["resource"]["aws_lambda_function"]["hello"]["package_type"] == "Image"


def test_zip_over_the_limit_notes_and_stops_deploy(make_project, monkeypatch):
    aws = type(get_provider("aws"))
    monkeypatch.setattr(aws, "package_limits", PackageLimits(zip_compressed=1, zip_unpacked=1))
    project = make_project(config(kind="zip"))
    result, _tf = package(project)  # package / plan only report it
    assert result.package.errors and "package.type: image" in result.package.errors[0].message
    deployer = Deployer(project, echo=lambda _m: None)
    plan = deployer.package_plan(fake_artifact(10, 10))
    with pytest.raises(DeployError, match="too big"):
        deployer.package_plan(fake_artifact(10, 10), strict=True)
    assert plan.type == "zip"


def test_plan_notes_sizes_and_near_limit():
    aws = get_provider("aws")
    from py_serverless_kit.config.schema import ServiceConfig

    cfg = ServiceConfig.model_validate({"service": "svc", "provider": {"name": "aws"}, "functions": {"f": {"handler": "a.b"}}})
    plan = plan_package(aws, cfg, fake_artifact(40 * MB, 220 * MB))
    assert plan.type == "zip"
    assert "250.0 MB" in str(plan.notes[0])
    assert [n.level for n in plan.notes] == ["info", "warning"]
    direct = cfg.model_copy(update={"provider": cfg.provider.model_copy(update={"options": {"artifact_upload": "direct"}})})
    over = plan_package(aws, direct, fake_artifact(60 * MB, 100 * MB))
    assert over.errors and "zipped" in over.errors[0].message


# --------------------------------------------------------------------------- Azure / ACR
AZ = "options: {subscription_id: '00000000-0000-0000-0000-000000000000'}"


def test_azure_image_renders_acr_and_container_app(make_project):
    project = make_project(config("azure", options=AZ))
    result, tf = package(project)
    res = tf["resource"]
    assert result.package.type == "image"
    acr = res["azurerm_container_registry"]["acr"]
    assert acr["admin_enabled"] is True and acr["sku"] == "Basic"
    assert acr["name"].isalnum() and 5 <= len(acr["name"]) <= 50
    assert res["azurerm_service_plan"]["plan"]["sku_name"] == "EP1"
    app = res["azurerm_linux_function_app"]["app"]
    assert "zip_deploy_file" not in app
    assert app["depends_on"] == ["docker_registry_image.function"]
    docker = app["site_config"]["application_stack"]["docker"][0]
    assert docker["registry_url"] == "https://${azurerm_container_registry.acr.login_server}"
    assert docker["image_tag"] == res["docker_image"]["function"]["triggers"]["tag"]
    settings = app["app_settings"]
    assert "ENABLE_ORYX_BUILD" not in settings and settings["WEBSITES_ENABLE_APP_SERVICE_STORAGE"] == "false"
    auth = tf["provider"]["docker"][0]["registry_auth"][0]
    assert auth["address"] == "${azurerm_container_registry.acr.login_server}"
    text = (project.work_dir / "build" / DOCKERFILE).read_text("utf-8")
    assert "FROM mcr.microsoft.com/azure-functions/python:4-python3.12" in text
    assert "RUN pip install --no-cache-dir -r /requirements.txt" in text


def test_azure_image_on_consumption_is_an_error(make_project):
    opts = "options: {subscription_id: x, plan_sku: Y1}"
    issues = make_project(config("azure", options=opts)).validate()
    assert any(i.level == "error" and "cannot run custom containers" in i.message for i in issues)


def test_azure_zip_keeps_consumption(make_project):
    _r, tf = package(make_project(config("azure", kind="zip", options=AZ)))
    assert tf["resource"]["azurerm_service_plan"]["plan"]["sku_name"] == "Y1"
    assert "zip_deploy_file" in tf["resource"]["azurerm_linux_function_app"]["app"]


# --------------------------------------------------------------------------- coming soon
def test_gcp_image_is_coming_soon(make_project):
    issues = make_project(config("gcp", options="options: {project: p}")).validate()
    errors = [i for i in issues if i.level == "error" and i.where == "package.type"]
    assert errors and "coming soon" in errors[0].message and "Artifact Registry" in errors[0].message


def test_describe_package():
    assert get_provider("aws").describe()["package"]["types"] == ["zip", "image", "auto"]
    assert get_provider("azure").describe()["package"]["image_registry"].startswith("Azure Container Registry")
    gcp = get_provider("gcp").describe()["package"]
    assert gcp["types"] == ["zip"] and gcp["image_soon"] and gcp["limits"]["zip_compressed"] == 100 * MB


def test_studio_job_passes_package_type():
    from py_serverless_kit.studio.jobs import StudioError, build_argv

    assert build_argv("deploy", "aws", "dev", {"package_type": "image"})[-2:] == ["--package-type", "image"]
    with pytest.raises(StudioError):
        build_argv("deploy", "aws", "dev", {"package_type": "tar"})


# --------------------------------------------------------------------------- per function
def test_aws_mixes_zip_and_image_functions(make_project):
    yml = config(kind="zip").replace("handler: app.handlers.hello", "handler: app.handlers.hello\n    package_type: image")
    result, tf = package(make_project(yml))
    assert result.package.type == "mixed"
    assert result.package.functions == {"hello": "image", "worker": "zip"}
    fns = tf["resource"]["aws_lambda_function"]
    assert fns["hello"]["package_type"] == "Image" and "handler" not in fns["hello"]
    assert fns["worker"]["handler"] == "pskit_entry.handler" and fns["worker"]["filename"].endswith("artifact.zip")
    assert "aws_s3_object" not in tf["resource"] and "docker_image" in tf["resource"]  # small zip: no code bucket


def test_image_checks_only_apply_to_image_functions(make_project):
    yml = config(kind="zip").replace(
        "handler: app.handlers.hello", "handler: app.handlers.hello\n    package_type: image"
    ).replace("handler: app.handlers.worker", "handler: app.handlers.worker\n    architecture: arm64")
    assert not [i for i in make_project(yml).validate() if i.level == "error"]


def test_package_type_flag_overrides_functions_too(make_project):
    yml = config(kind="zip").replace("handler: app.handlers.hello", "handler: app.handlers.hello\n    package_type: image")
    result, _tf = package(make_project(yml), package_type="zip")
    assert result.package.type == "zip"


def test_azure_needs_one_package_type(make_project):
    yml = config("azure", kind="zip", options=AZ).replace(
        "handler: app.handlers.hello", "handler: app.handlers.hello\n    package_type: image"
    )
    issues = make_project(yml).validate()
    assert any(i.level == "error" and "one Function App hosts every function" in i.message for i in issues)


def test_unsupported_image_per_function_is_scoped(make_project):
    yml = config("gcp", kind="zip", options="options: {project: p}").replace(
        "handler: app.handlers.worker", "handler: app.handlers.worker\n    package_type: image"
    )
    errors = [i for i in make_project(yml).validate() if i.level == "error"]
    assert [i.where for i in errors] == ["functions.worker.package_type"]
