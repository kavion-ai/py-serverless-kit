"""On-premises provider: every trigger renders, and missing services are declared."""

import json
from pathlib import Path

import pytest

from tests.conftest import full_config

CONFIG = """
service: demo
provider:
  name: onprem
  options:
    host: 127.0.0.1
    port: 9090
    services:
      queue: builtin
      storage: {use: directory, path: /data/buckets}
      topic: builtin
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
  tick:
    handler: app.handlers.tick
    events:
      - schedule: 7 minutes
      - schedule: {cron: "0 12 * * 1", input: {report: weekly}, timezone: UTC}
  worker:
    handler: app.handlers.worker
    events:
      - queue: {name: jobs, dead_letter: jobs-dlq, max_receive: 3}
      - storage: {bucket: uploads, prefix: in/, suffix: .csv}
      - topic: {name: events, filter: {event_type: [created]}}
"""


def _errors(project):
    return [str(i) for i in project.validate() if i.level == "error"]


def test_full_config_accepts_every_trigger(make_project):
    project = make_project(full_config("onprem"))
    assert _errors(project) == []
    assert not any("capped by the function timeout" in str(i) for i in project.validate())


def test_render_deploys_builtin_services(make_project, render):
    project = make_project(CONFIG)
    assert _errors(project) == []
    tf = render(project)
    assert tf["terraform"]["required_providers"] == {}
    assert "provider" not in tf
    host = tf["resource"]["terraform_data"]["host"]
    create, destroy = host["provisioner"]
    assert create["local-exec"]["command"] == "apply"
    assert create["local-exec"]["interpreter"][-1] == "onprem_deploy.py"
    assert destroy["local-exec"]["when"] == "destroy"
    assert destroy["local-exec"]["command"] == "destroy"

    root = project.work_dir / "onprem_app"
    spec = json.loads((root / "pskit_host.json").read_text("utf-8"))
    assert spec["endpoint"] == "http://127.0.0.1:9090"
    assert spec["services"]["queue"]["use"] == "builtin"
    assert spec["services"]["queue"]["path"].endswith("queues")
    # A leading slash is absolute on POSIX and drive-anchored on Windows.
    assert spec["services"]["storage"]["use"] == "directory"
    assert Path(spec["services"]["storage"]["path"]) == (project.root / Path("/data/buckets"))
    assert spec["services"]["workflow"]["use"] == "embedded"
    worker = spec["functions"]["worker"]["events"]
    queue = next(ev for ev in worker if ev["type"] == "queue")
    assert queue["dead_letter"] == "jobs-dlq"
    assert queue["visibility_timeout"] >= 30
    assert (root / "onprem_ctl.py").is_file()
    assert (root / "onprem_deploy.py").is_file()
    assert spec["deploy"]["method"] == "local"
    assert (root / "staging" / "pskit_manifest.json").is_file()
    assert (root / "staging" / "onprem_handler.py").is_file()
    assert not (root / "app").exists()

    out = tf["output"]["pskit"]["value"]
    assert out["endpoint"] == "http://127.0.0.1:9090"
    assert out["functions"]["hello"]["url"] == "http://127.0.0.1:9090"
    assert out["functions"]["tick"]["url"] is None
    assert out["services"]["storage"]["use"] == "directory"


def test_directory_binding_requires_a_path(make_project):
    project = make_project(CONFIG.replace("path: /data/buckets", "use: directory"))
    assert any("path is required" in err for err in _errors(project))


def test_schedule_service_is_only_builtin(make_project):
    text = CONFIG.replace("queue: builtin", "schedule: {use: directory, path: /tmp}")
    assert any("services.schedule" in err for err in _errors(make_project(text)))


def test_auth_is_rejected(make_project):
    text = CONFIG.replace("http: GET /hello", "http: {path: /hello, auth: jwt}")
    assert any("auth `jwt`" in err for err in _errors(make_project(text)))


def test_impossible_cron_is_an_error(make_project):
    text = CONFIG.replace('cron: "0 12 * * 1"', 'cron: "0 0 31 2 *"')
    assert any("does not match" in err for err in _errors(make_project(text)))


def test_foreign_terraform_is_omitted(make_project, render):
    text = CONFIG.replace(
        "name: onprem\n",
        "name: onprem\n"
        "  terraform:\n"
        "    extra:\n"
        "      resource:\n"
        "        aws_dynamodb_table:\n"
        "          orders: {name: orders, hash_key: id, billing_mode: PAY_PER_REQUEST}\n"
        "        terraform_data:\n"
        "          note: {input: {ok: true}}\n"
        "      output:\n"
        '        orders_table_arn: {value: "${aws_dynamodb_table.orders.arn}"}\n'
        '        kept: {value: "yes"}\n',
    )
    project = make_project(text)
    warnings = [str(i) for i in project.validate() if i.level == "warning"]
    assert any("aws_dynamodb_table" in warning for warning in warnings)
    tf = render(project)
    assert "aws_dynamodb_table" not in tf["resource"]
    assert "note" in tf["resource"]["terraform_data"]
    assert "orders_table_arn" not in tf["output"]
    assert tf["output"]["kept"]["value"] == "yes"


SSH_CONFIG = """
service: demo
provider:
  name: onprem
  architecture: x86_64
  options:
    host: 0.0.0.0
    port: 9090
    deploy:
      method: ssh
      host: 10.0.1.12
      user: pskit
      path: /opt/pskit/demo
      python: bundle
      target_os: linux
      install: systemd
      sudo: true
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
"""

DOCKER_CONFIG = """
service: demo
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 9090
    deploy:
      method: docker
      image: pskit-demo:dev
      docker_host: ssh://pskit@10.0.1.12
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
"""


def test_ssh_bundle_systemd_renders(make_project, render):
    project = make_project(SSH_CONFIG)
    assert _errors(project) == []
    tf = render(project)
    root = project.work_dir / "onprem_app"
    spec = json.loads((root / "pskit_host.json").read_text("utf-8"))
    assert spec["deploy"]["method"] == "ssh"
    assert spec["deploy"]["python"] == "bundle"
    assert spec["deploy"]["ssh"]["host"] == "10.0.1.12"
    assert spec["deploy"]["ssh"]["path"] == "/opt/pskit/demo"
    assert spec["endpoint"] == "http://10.0.1.12:9090"
    assert spec["data_dir"] == "/opt/pskit/demo/data"
    assert (root / "pskit.service").is_file()
    unit = (root / "pskit.service").read_text("utf-8")
    assert "ExecStart=/opt/pskit/demo/pskit-run.sh" in unit
    launcher = (root / "pskit-run.sh").read_text(encoding="utf-8")
    assert "./python/bin/python3" in launcher
    assert "python3.12" in launcher
    assert tf["output"]["pskit"]["value"]["deploy"] == "ssh"
    flags = project.provider.pip_platform_for(project.config)
    assert "--platform" in flags and "manylinux2014_x86_64" in flags


def test_ssh_url_shorthand(make_project, render):
    text = """
service: demo
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 9090
    deploy: ssh://ops@factory.internal:2222/opt/pskit/demo
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
"""
    project = make_project(text)
    assert _errors(project) == []
    render(project)
    spec = json.loads((project.work_dir / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    assert spec["deploy"]["method"] == "ssh"
    assert spec["deploy"]["ssh"]["user"] == "ops"
    assert spec["deploy"]["ssh"]["host"] == "factory.internal"
    assert spec["deploy"]["ssh"]["port"] == 2222
    assert spec["deploy"]["ssh"]["path"] == "/opt/pskit/demo"


def test_ssh_requires_host(make_project):
    text = SSH_CONFIG.replace("      host: 10.0.1.12\n", "")
    assert any("host is required" in err for err in _errors(make_project(text)))


def test_ctl_swaps_staging_into_app_before_import(tmp_path):
    import subprocess
    import sys

    from py_serverless_kit.providers.onprem import _CTL

    pkg = tmp_path / "staging" / "py_serverless_kit" / "runtime"
    pkg.mkdir(parents=True)
    (tmp_path / "staging" / "py_serverless_kit" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "onprem_host.py").write_text("def main(root):\n    return 0\n", encoding="utf-8")
    (tmp_path / "onprem_ctl.py").write_bytes(_CTL.replace("\r\n", "\n").encode("utf-8"))
    proc = subprocess.run(
        [sys.executable, str(tmp_path / "onprem_ctl.py"), "start"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "app" / "py_serverless_kit" / "runtime" / "onprem_host.py").is_file()
    assert not (tmp_path / "staging").exists()


def test_scp_is_an_alias_of_ssh(make_project, render):
    text = SSH_CONFIG.replace("method: ssh", "method: scp")
    project = make_project(text)
    assert _errors(project) == []
    render(project)
    spec = json.loads((project.work_dir / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    assert spec["deploy"]["method"] == "ssh"
    assert (project.work_dir / "onprem_app" / "pskit-run.sh").is_file()


def test_unknown_deploy_method(make_project):
    text = CONFIG.replace("port: 9090\n", "port: 9090\n    deploy: {method: ftp}\n")
    assert any("method must be one of" in err for err in _errors(make_project(text)))


def test_systemd_rejected_on_windows_target(make_project):
    text = SSH_CONFIG.replace("target_os: linux", "target_os: windows")
    assert any("systemd is only valid" in err for err in _errors(make_project(text)))


def test_docker_writes_dockerfile(make_project, render):
    project = make_project(DOCKER_CONFIG)
    assert _errors(project) == []
    render(project)
    root = project.work_dir / "onprem_app"
    spec = json.loads((root / "pskit_host.json").read_text("utf-8"))
    assert spec["deploy"]["method"] == "docker"
    assert spec["host"] == "0.0.0.0"
    assert spec["data_dir"] == "/var/pskit/data"
    assert spec["deploy"]["ssh"]["host"] == "10.0.1.12"
    assert spec["deploy"]["ssh"]["user"] == "pskit"
    assert spec["deploy"]["docker"]["install_docker"] is True
    assert spec["deploy"]["sudo"] is True
    docker = (root / "Dockerfile").read_text("utf-8")
    assert docker.startswith("FROM python:3.12-slim-bookworm")
    assert "onprem_ctl.py" in docker
    assert spec["endpoint"] == "http://10.0.1.12:9090"
    warnings = [str(i) for i in project.validate() if i.level == "warning"]
    # No .pem: the SSH agent or the default key is used, so it is no longer a warning.
    assert not any("pem" in warning for warning in warnings)


REMOTE_DOCKER = """
service: demo
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 9090
    deploy:
      method: docker
      host: 10.0.1.12
      user: pskit
      pem: keys/server.pem
      image: pskit-demo:dev
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
"""


def test_remote_docker_pem_is_stored_absolute(make_project, render):
    project = make_project(REMOTE_DOCKER)
    assert _errors(project) == []
    render(project)
    spec = json.loads((project.work_dir / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    identity = Path(spec["deploy"]["ssh"]["identity_file"])
    assert identity.is_absolute()
    assert identity.name == "server.pem"
    assert spec["deploy"]["docker"]["install_docker"] is True
    assert spec["endpoint"] == "http://10.0.1.12:9090"


def test_local_pip_platform_stays_native(make_project):
    project = make_project(CONFIG)
    assert project.provider.pip_platform_for(project.config) == []


def test_host_tuning_options_reach_the_spec_and_are_validated(make_project):
    import json as _json

    from py_serverless_kit.core.deployer import Deployer

    project = make_project(
        """
        service: tune
        provider:
          name: onprem
          options: {execution_retention: 50, workflow_workers: 2, log_buffer: 1000, log_level: debug, capture_output: false}
        functions: {a: {handler: app.handlers.hello}}
        """
    )
    assert not [i for i in project.validate() if i.level == "error"]
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    spec = _json.loads((project.work_dir / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    assert spec["execution_retention"] == 50 and spec["workflow_workers"] == 2 and spec["capture_output"] is False
    bad = make_project(
        """
        service: tune
        provider:
          name: onprem
          options: {workflow_workers: 0, log_level: loud, capture_output: "no"}
        functions: {a: {handler: app.handlers.hello}}
        """
    )
    errors = {i.where for i in bad.validate() if i.level == "error"}
    assert {"provider.options.workflow_workers", "provider.options.log_level", "provider.options.capture_output"} <= errors


def _driver_project(make_project, kind, options):
    import json as _json

    event = {"queue": "queue", "storage": "storage"}[kind]
    return make_project(
        f"""
        service: drv
        provider: {{name: onprem}}
        resources:
          res: {{type: {kind}, external: true, options: {_json.dumps(options)}}}
        functions:
          w: {{handler: app.handlers.worker, events: [{{{event}: {{resource: res}}}}]}}
        """
    )


@pytest.mark.parametrize(
    "kind,options,message",
    [
        ("queue", {"driver": "sqs"}, "needs account_id, region"),
        ("queue", {"driver": "sqs", "queue_url": "https://x/1/q", "access_key": "a"}, "set both access_key and secret_key"),
        ("queue", {"driver": "sqs", "queue_url": "https://x/1/q", "wait_seconds": 99}, "wait_seconds must be between"),
        ("queue", {"driver": "azure_queue"}, "needs account, endpoint or connection_string"),
        ("queue", {"driver": "azure_queue", "account": "a"}, "needs account_key, sas_token or connection_string"),
        ("queue", {"driver": "azure_queue", "connection_string": "x", "message_encoding": "hex"}, "base64 or text"),
        ("queue", {"driver": "pubsub"}, "needs `project`"),
        ("queue", {"driver": "pubsub", "project": "p", "token_command": 5}, "token_command must be"),
        ("queue", {"driver": "mns", "access_key": "a", "secret_key": "b"}, "needs account_id, region"),
        ("queue", {"driver": "mns", "endpoint": "https://x"}, "needs access_key, secret_key"),
        ("queue", {"driver": "cloudflare_queue", "account_id": "a"}, "needs queue_id, api_token"),
        ("queue", {"driver": "custom"}, "needs `class: package.module:ClassName`"),
        ("queue", {"driver": "custom", "class": "app.x:Y", "resource": "z"}, "`resource` is reserved"),
        ("queue", {"driver": "sqs", "queue_url": "https://x/1/q", "endpoint": "ftp://x"}, "endpoint must be an http(s) URL"),
        ("storage", {"driver": "oci", "region": "r"}, "needs namespace"),
        ("storage", {"driver": "r2"}, "needs account_id"),
        ("storage", {"driver": "minio"}, "needs endpoint"),
        ("storage", {"driver": "s3", "provider": "dropbox"}, "s3 provider must be one of"),
        ("storage", {"driver": "azure_blob", "account": "a"}, "needs account_key, sas_token"),
        ("storage", {"driver": "gcs", "token_command": {"x": 1}}, "token_command must be"),
        ("storage", {"driver": "kafka"}, "driver must be one of"),
    ],
)
def test_external_driver_validation(make_project, kind, options, message):
    project = _driver_project(make_project, kind, options)
    errors = [i.message for i in project.validate() if i.level == "error"]
    assert any(message in e for e in errors), errors


@pytest.mark.parametrize(
    "kind,options,expected",
    [
        (
            "queue",
            {"driver": "sqs", "queue_url": "https://sqs.eu-west-1.amazonaws.com/1/q", "access_key_env": "AK",
             "secret_key_env": "SK", "wait_seconds": 5},
            {"use": "sqs", "queue_url": "https://sqs.eu-west-1.amazonaws.com/1/q", "access_key_env": "AK",
             "secret_key_env": "SK", "wait_seconds": 5},
        ),
        (
            "queue",
            {"driver": "azure_queue", "connection_string_env": "AZ_CONN"},
            {"use": "azure_queue", "queue": "res", "connection_string_env": "AZ_CONN"},
        ),
        (
            "queue",
            {"driver": "pubsub", "project": "p", "token_command": ["gcloud", "auth", "print-access-token"]},
            {"use": "pubsub", "subscription": "res", "project": "p",
             "token_command": ["gcloud", "auth", "print-access-token"]},
        ),
        (
            "queue",
            {"driver": "mns", "account_id": "123", "region": "cn-hangzhou", "access_key": "a", "secret_key_env": "S"},
            {"use": "mns", "queue": "res", "account_id": "123", "region": "cn-hangzhou", "access_key": "a",
             "secret_key_env": "S"},
        ),
        (
            "queue",
            {"driver": "cloudflare_queue", "account_id": "a", "queue_id": "q", "api_token_env": "CF"},
            {"use": "cloudflare_queue", "account_id": "a", "queue_id": "q", "api_token_env": "CF"},
        ),
        (
            "queue",
            {"driver": "custom", "class": "app.backends:Q", "url": "amqp://x", "password_env": "PW"},
            {"use": "custom", "class": "app.backends:Q", "url": "amqp://x", "password_env": "PW"},
        ),
        (
            "storage",
            {"driver": "s3", "region": "eu-west-1"},
            {"use": "s3", "bucket": "res", "region": "eu-west-1"},
        ),
        (
            "storage",
            {"driver": "cos", "region": "ap-guangzhou", "bucket": "media-1250000000", "access_key_env": "A",
             "secret_key_env": "B"},
            {"use": "cos", "bucket": "media-1250000000", "region": "ap-guangzhou", "access_key_env": "A",
             "secret_key_env": "B"},
        ),
        (
            "storage",
            {"driver": "s3", "provider": "r2", "account_id": "abc"},
            {"use": "s3", "bucket": "res", "account_id": "abc", "provider": "r2"},
        ),
        (
            "storage",
            {"driver": "azure_blob", "account": "acct", "sas_token_env": "SAS", "prefix": "in/"},
            {"use": "azure_blob", "container": "res", "account": "acct", "sas_token_env": "SAS", "prefix": "in/"},
        ),
        (
            "storage",
            {"driver": "gcs", "bucket": "b", "access_token_env": "TOK"},
            {"use": "gcs", "bucket": "b", "access_token_env": "TOK"},
        ),
    ],
)
def test_external_driver_bindings_keep_secrets_as_env_names(make_project, kind, options, expected):
    import json as _json

    from py_serverless_kit.core.deployer import Deployer

    project = _driver_project(make_project, kind, options)
    assert not [i for i in project.validate() if i.level == "error"]
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    spec = _json.loads((project.work_dir / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    assert spec["resources"]["res"]["driver"] == expected
    assert spec["functions"]["w"]["events"][0]["driver"] == expected


def test_storage_event_watches_another_bucket_on_a_resource_service(make_project):
    import json as _json

    from py_serverless_kit.core.deployer import Deployer

    project = make_project(
        """
        service: drv
        provider: {name: onprem}
        resources:
          store: {type: storage, external: true, options: {driver: minio, endpoint: "http://minio:9000",
                  bucket: files, access_key_env: A, secret_key_env: B}}
        functions:
          w: {handler: app.handlers.worker, events: [{storage: {resource: store, bucket: invoices}},
                                                     {storage: {resource: store}}]}
        """
    )
    assert not [i for i in project.validate() if i.level == "error"]
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    spec = _json.loads((project.work_dir / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    invoices, own = spec["functions"]["w"]["events"]
    assert invoices["bucket"] == "invoices"
    assert invoices["driver"] == {**spec["resources"]["store"]["driver"], "bucket": "invoices"}
    assert invoices["driver"]["endpoint"] == "http://minio:9000"
    assert own["bucket"] == "store" and own["driver"]["bucket"] == "files"


def test_storage_event_bucket_on_a_directory_resource_is_an_error(make_project):
    project = make_project(
        """
        service: drv
        provider: {name: onprem}
        resources:
          store: {type: storage, options: {driver: directory, path: ./drop}}
        functions:
          w: {handler: app.handlers.worker, events: [{storage: {resource: store, bucket: invoices}}]}
        """
    )
    errors = [i.message for i in project.validate() if i.level == "error"]
    assert any("is one folder" in e for e in errors), errors
