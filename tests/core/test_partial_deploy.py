"""Partial deploys: a function that cannot be deployed is reported; the others are deployed."""

import json

import pytest

from py_serverless_kit.core import partial
from py_serverless_kit.core.deployer import Deployer, DeployError
from py_serverless_kit.providers.container import PackageLimits
from py_serverless_kit.providers.registry import get_provider
from py_serverless_kit.terraform.runner import TerraformError, TerraformRunner

YML = """
service: part
provider:
  name: {provider}
  {options}
functions:
  api:
    handler: app.handlers.hello
    {api_extra}
    events:
      - http: GET /hello
  api-v2:
    handler: app.handlers.hello
    events:
      - http: GET /v2/hello
  worker:
    handler: app.handlers.worker
    {worker_extra}
    events:
      - schedule: {{rate: 5 minutes}}
"""

APPLY_ERROR = """
aws_iam_role.lambda: Creation complete after 1s [id=part-dev-lambda]
aws_lambda_function.api: Creation complete after 9s

Error: creating Lambda Function (part-dev-worker): operation error Lambda: CreateFunction, InvalidParameterValueException: Unzipped size must be smaller than 262144000 bytes

  with aws_lambda_function.worker,
  on main.tf.json line 120, in resource.aws_lambda_function.worker:
 120:       },

"""


def yml(provider="aws", options="", api_extra="", worker_extra=""):
    return YML.format(provider=provider, options=options, api_extra=api_extra, worker_extra=worker_extra)


class FakeRunner(TerraformRunner):
    def __init__(self, work_dir, fail_with=""):
        super().__init__(work_dir)
        self.fail_with = fail_with
        self.targets = None

    def init(self, upgrade=False, reconfigure=False):
        pass

    def apply(self, plan_file=None, auto_approve=True, targets=None):
        self.targets = targets
        if self.fail_with:
            raise TerraformError("`apply` failed with exit code 1", output=self.fail_with)
        return ""

    def output(self):
        if self.fail_with:
            return {}
        return {"pskit": {"functions": {"api": {"id": "part-dev-api"}}, "workflows": {}, "endpoint": "https://x"}}


def deployer(project, **kw):
    runner = FakeRunner(project.work_dir, kw.pop("fail_with", ""))
    return Deployer(project, echo=lambda _m: None, runner=runner, keep_going=kw.pop("keep_going", True), **kw), runner


# --------------------------------------------------------------------------- pieces
def test_parse_errors():
    errors = partial.parse_errors(APPLY_ERROR)
    assert len(errors) == 1
    address, message = errors[0]
    assert address == "aws_lambda_function.worker"
    assert message.startswith("creating Lambda Function (part-dev-worker)") and "Unzipped size" in message
    assert "main.tf.json" not in message
    assert partial.parse_errors("Error: No valid credential sources found\n\nPlease see the docs\n") == [
        (None, "No valid credential sources found: Please see the docs")
    ]


def test_owner_prefers_the_longest_name():
    names = ["api", "api-v2", "worker"]
    assert partial.owner("api_v2_apigw", names) == "api-v2"
    assert partial.owner("api_apigw", names) == "api"
    assert partial.owner("logs_worker", names) == "worker"
    assert partial.owner("lambda", names) is None


def test_failed_functions_follow_dependencies(make_project, render):
    tf = render(make_project(yml()))
    names = ["api", "api-v2", "worker"]
    only = partial.failed_functions(tf, names, [("aws_lambda_function.worker", "boom")])
    assert only == {"worker": "aws_lambda_function.worker: boom"}
    shared = partial.failed_functions(tf, names, [("aws_iam_role.lambda", "denied")])
    assert set(shared) == set(names)  # every function runs as that role
    api = partial.failed_functions(tf, names, [("aws_apigatewayv2_api.http", "quota")])
    assert set(api) == {"api", "api-v2"}  # the schedule-only worker does not need the API
    general = partial.failed_functions(tf, names, [(None, "no credentials")])
    assert set(general) == set(names)


# --------------------------------------------------------------------------- terraform failure
def test_terraform_failure_of_one_function_is_partial(make_project):
    project = make_project(yml())
    d, _runner = deployer(project, fail_with=APPLY_ERROR)
    record = d.deploy(skip_deps=True)
    assert record["status"] == "partial"
    assert list(record["not_deployed"]) == ["worker"]
    assert record["not_deployed"]["worker"]["step"] == partial.TERRAFORM
    assert "Unzipped size" in record["not_deployed"]["worker"]["reason"]
    worker = next(f for f in record["functions"] if f["name"] == "worker")
    assert worker["status"] == "not_deployed"
    lines = d.report()
    assert lines[0] == "Deployed 2 of 3 function(s). Not deployed (1):"
    saved = json.loads((project.work_dir / "deployment.json").read_text("utf-8"))
    assert saved["not_deployed"]["worker"]["step"] == partial.TERRAFORM


def test_all_or_nothing_raises(make_project):
    d, _runner = deployer(make_project(yml()), fail_with=APPLY_ERROR, keep_going=False)
    with pytest.raises(TerraformError):
        d.deploy(skip_deps=True)


def test_every_function_failing_is_an_error(make_project):
    d, _runner = deployer(make_project(yml()), fail_with="Error: denied\n\n  with aws_iam_role.lambda,\n")
    with pytest.raises(DeployError, match="no function was deployed"):
        d.deploy(skip_deps=True)


# --------------------------------------------------------------------------- skipped before terraform
GCP = "options: {project: p}"


def test_config_error_of_one_function_skips_it(make_project):
    project = make_project(yml("gcp", GCP, worker_extra="package_type: image"))
    d, runner = deployer(project)
    record = d.deploy(skip_deps=True)
    assert [n.function for n in d.not_deployed] == ["worker"]
    assert d.not_deployed[0].step == partial.CONFIG and "coming soon" in d.not_deployed[0].reason
    assert d.not_deployed[0].previous == "it has never been deployed on this stage"
    tf = json.loads((project.work_dir / "main.tf.json").read_text("utf-8"))
    assert not any("worker" in label for bodies in tf["resource"].values() for label in bodies)
    assert runner.targets and all("worker" not in t for t in runner.targets)  # leaves an older worker alone
    assert record["status"] == "partial"
    manifest = json.loads((project.work_dir / "build" / "pskit_manifest.json").read_text("utf-8"))
    assert "worker" not in json.dumps(manifest["functions"])


def test_skipped_function_keeps_its_previous_entry(make_project):
    project = make_project(yml("gcp", GCP))
    deployer(project)[0].deploy(skip_deps=True)  # first deploy: everything
    project = make_project(yml("gcp", GCP, worker_extra="package_type: image"))
    d, _runner = deployer(project)
    record = d.deploy(skip_deps=True)
    assert d.not_deployed[0].previous == "the version deployed before is still running, unchanged"
    worker = next(f for f in record["functions"] if f["name"] == "worker")
    assert worker["status"] == "not_updated"


def test_shared_host_says_the_function_left_it(make_project):
    az = "options: {subscription_id: x}"
    project = make_project(yml("azure", az))
    deployer(project)[0].deploy(skip_deps=True)
    project = make_project(yml("azure", az).replace("- http: GET /v2/hello", "- http: {path: /v2/hello, auth: jwt}"))
    d, _runner = deployer(project)
    d.deploy(skip_deps=True)
    assert [n.function for n in d.not_deployed] == ["api-v2"]
    assert "jwt" in d.not_deployed[0].reason
    assert d.not_deployed[0].previous == "its previous version left Azure Functions: one host runs every function"
    host = json.loads((project.work_dir / "build" / "host.json").read_text("utf-8"))
    app = (project.work_dir / "build" / "function_app.py").read_text("utf-8")
    assert "api_v2" not in app and host


def test_zip_over_the_limit_skips_only_zip_functions(make_project, monkeypatch):
    aws = type(get_provider("aws"))
    monkeypatch.setattr(aws, "package_limits", PackageLimits(zip_compressed=1, zip_unpacked=1))
    project = make_project(yml(api_extra="package_type: image"))
    d, _runner = deployer(project)
    d.deploy(skip_deps=False)
    assert sorted(n.function for n in d.not_deployed) == ["api-v2", "worker"]
    assert all(n.step == partial.SIZE for n in d.not_deployed)
    assert "package_type: image" in d.not_deployed[0].reason
    tf = json.loads((project.work_dir / "main.tf.json").read_text("utf-8"))
    assert tf["resource"]["aws_lambda_function"]["api"]["package_type"] == "Image"
    assert set(tf["resource"]["aws_lambda_function"]) == {"api"}


def test_everything_skipped_is_still_an_error(make_project):
    project = make_project(yml("gcp", GCP, api_extra="package_type: image", worker_extra="package_type: image")
                           .replace("  api-v2:\n    handler: app.handlers.hello\n    events:\n      - http: GET /v2/hello\n", ""))
    d, _runner = deployer(project)
    with pytest.raises(DeployError, match="configuration error"):
        d.deploy(skip_deps=True)
