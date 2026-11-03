import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.terraform.runner import TerraformRunner


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(tmp_path / "svc"), "--template", "full", "--provider", "aws"])
    assert result.exit_code == 0, result.output
    monkeypatch.chdir(tmp_path / "svc")
    return tmp_path / "svc"


def run(*args):
    result = CliRunner().invoke(cli, list(args), catch_exceptions=False)
    return result


def test_init_creates_files(project_dir):
    for rel in ("pskit.yml", "app/handlers.py", "requirements.txt", "tests/test_handlers.py", ".gitignore"):
        assert (project_dir / rel).is_file(), rel


@pytest.mark.parametrize("provider", ["aws", "gcp", "azure"])
def test_init_every_template_validates(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setenv("ARM_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000000")
    for template in ("http", "events", "workflow"):
        target = tmp_path / f"{provider}-{template}"
        assert run("init", str(target), "-t", template, "-p", provider).exit_code == 0
        monkeypatch.chdir(target)
        result = run("validate")
        assert result.exit_code == 0, result.output


def test_ask_onprem_pem_records_the_path(tmp_path, monkeypatch):
    import sys

    from py_serverless_kit.cli.main import _ask_onprem_pem
    from py_serverless_kit.core.project import Project

    root = tmp_path / "svc"
    root.mkdir()
    pem = tmp_path / "server.pem"
    pem.write_text("key\n", encoding="utf-8")
    (root / "pskit.yml").write_text(
        "service: demo\n"
        "provider:\n"
        "  name: onprem\n"
        "  options:\n"
        "    host: 0.0.0.0\n"
        "    deploy: {method: docker, host: 10.0.1.12, user: pskit}\n"
        "functions:\n"
        "  hello:\n"
        "    handler: app.handlers.hello\n"
        "    events: [{http: GET /hello}]\n",
        encoding="utf-8",
    )
    project = Project.load(cwd=root)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("py_serverless_kit.cli.main.click.prompt", lambda *_a, **_k: str(pem))
    _ask_onprem_pem(project)
    stored = project.config.provider.options["deploy"]["pem"]
    assert Path(stored) == pem.resolve()


def test_ask_onprem_pem_for_ssh_keeps_the_agent_when_blank(tmp_path, monkeypatch):
    import sys

    from py_serverless_kit.cli.main import _ask_onprem_pem
    from py_serverless_kit.core.project import Project

    root = tmp_path / "svc"
    root.mkdir()
    (root / "pskit.yml").write_text(
        "service: demo\n"
        "provider:\n"
        "  name: onprem\n"
        "  options:\n"
        "    host: 0.0.0.0\n"
        "    deploy: {method: ssh, host: 10.0.1.12, user: pskit}\n"
        "functions:\n"
        "  hello:\n"
        "    handler: app.handlers.hello\n"
        "    events: [{http: GET /hello}]\n",
        encoding="utf-8",
    )
    project = Project.load(cwd=root)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("py_serverless_kit.cli.main.click.prompt", lambda *_a, **_k: "")
    _ask_onprem_pem(project)
    assert "pem" not in project.config.provider.options["deploy"]


def test_remote_docker_deploy_with_a_missing_pem_fails_off_a_terminal(tmp_path, monkeypatch):
    root = tmp_path / "svc"
    root.mkdir()
    (root / "pskit.yml").write_text(
        "service: demo\n"
        "provider:\n"
        "  name: onprem\n"
        "  options:\n"
        "    host: 0.0.0.0\n"
        "    port: 9090\n"
        "    deploy:\n"
        "      method: docker\n"
        "      host: 10.0.1.12\n"
        "      user: pskit\n"
        "      pem: missing.pem\n"
        "functions:\n"
        "  hello:\n"
        "    handler: app.handlers.hello\n"
        "    events:\n"
        "      - http: GET /hello\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    result = CliRunner().invoke(cli, ["deploy"])
    assert result.exit_code != 0
    assert "missing.pem" in result.output


def test_validate_and_providers(project_dir):
    result = run("validate")
    assert result.exit_code == 0 and "Configuration is valid" in result.output
    result = run("providers", "--json")
    names = {p["name"] for p in json.loads(result.output)}
    assert {"aws", "gcp", "azure"} <= names


def test_invoke_http_and_events(project_dir):
    result = run("invoke", "-f", "hello", "--path", "/hello?name=Ada")
    assert result.exit_code == 0
    assert '"message": "Hello, Ada!"' in result.output
    result = run("invoke", "-f", "get-item", "--path", "/items/404")
    assert '"status": 404' in result.output
    result = run("invoke", "-f", "process-jobs", "-d", '[{"a": 1}, "not json"]')
    assert '"itemIdentifier": "local-1"' in result.output
    result = run("invoke", "-f", "nightly-report")
    assert '"ok": true' in result.output


def test_invoke_errors(project_dir):
    result = CliRunner().invoke(cli, ["invoke", "-f", "nope"])
    assert result.exit_code == 1 and "unknown function" in result.output


def test_workflow_commands(project_dir):
    result = run("workflow", "run", "order-pipeline", "-i", '{"amount": 10}')
    assert result.exit_code == 0 and '"charged": true' in result.output
    result = CliRunner().invoke(cli, ["workflow", "run", "order-pipeline", "-i", '{"amount": 0}'])
    assert result.exit_code == 2 and "OrderRejected" in result.output
    result = run("workflow", "show", "order-pipeline")
    assert '"StartAt": "Validate"' in result.output
    result = run("workflow", "show", "order-pipeline", "--format", "gcp")
    assert '"main"' in result.output


def test_package_info_dashboard(project_dir):
    assert run("package", "--skip-deps").exit_code == 0
    assert (project_dir / ".pskit" / "aws-dev" / "main.tf.json").is_file()
    result = run("info", "--json")
    record = json.loads(result.output)
    assert record["status"] == "not deployed" and len(record["functions"]) == 8
    result = run("dashboard")
    assert result.exit_code == 0
    html = (project_dir / ".pskit" / "dashboard" / "index.html").read_text("utf-8")
    assert "order-pipeline" in html and "<script" in html


def test_stage_and_provider_flags(project_dir):
    result = run("package", "--skip-deps", "--stage", "prod", "--provider", "aws", "--region", "eu-central-1")
    assert result.exit_code == 0
    tf = json.loads((project_dir / ".pskit" / "aws-prod" / "main.tf.json").read_text())
    assert tf["provider"]["aws"][0]["region"] == "eu-central-1"
    assert tf["resource"]["aws_lambda_function"]["hello"]["function_name"] == "svc-prod-hello"


def test_config_error_exit_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["validate"])
    assert result.exit_code == 1 and "no config found" in result.output


class FakeRunner(TerraformRunner):
    """Records terraform calls instead of running the binary."""

    def __init__(self, work_dir: Path) -> None:
        super().__init__(work_dir)
        self.calls = []

    def init(self, upgrade=False, reconfigure=False):
        self.calls.append("init")

    def apply(self, plan_file=None, auto_approve=True):
        self.calls.append("apply")

    def destroy(self, auto_approve=True):
        self.calls.append("destroy")

    def output(self):
        return {
            "pskit": {
                "endpoint": "https://api.example.com",
                "functions": {"hello": {"id": "svc-dev-hello", "base_url": "https://api.example.com"}},
                "workflows": {"order-pipeline": {"id": "arn:sm"}},
            }
        }


def test_deploy_and_remove_with_fake_terraform(project_dir):
    from py_serverless_kit.core.project import Project

    project = Project.load()
    fake = FakeRunner(project.work_dir)
    deployer = Deployer(project, echo=lambda _m: None, runner=fake)
    record = deployer.deploy(skip_deps=True)
    assert fake.calls == ["init", "apply"]
    hello = next(f for f in record["functions"] if f["name"] == "hello")
    assert hello["urls"] == [{"method": "GET", "url": "https://api.example.com/hello"}]
    assert record["workflows"][0]["id"] == "arn:sm"
    assert (project.work_dir / "deployment.json").is_file()
    info = run("info")
    assert "https://api.example.com/hello" in info.output
    deployer.remove()
    assert fake.calls[-1] == "destroy"
    assert json.loads((project.work_dir / "deployment.json").read_text())["status"] == "removed"


def test_terraform_missing(monkeypatch, tmp_path):
    from py_serverless_kit.terraform.runner import TerraformError, find_binary

    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("PSKIT_TERRAFORM_BIN", raising=False)
    with pytest.raises(TerraformError, match="Install Terraform"):
        find_binary()


@pytest.mark.skipif(not os.environ.get("PSKIT_TERRAFORM_BIN"), reason="set PSKIT_TERRAFORM_BIN to run")
def test_terraform_validate_aws(project_dir):
    """Runs `terraform validate` on the generated config (needs network for provider download)."""
    from py_serverless_kit.core.project import Project

    project = Project.load()
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    runner = TerraformRunner(project.work_dir)
    runner._run(["init", "-backend=false", "-input=false", "-no-color"], capture=True)
    runner._run(["validate", "-no-color"], capture=True)


def test_root_help_lists_every_command_and_subcommand():
    import click

    out = CliRunner().invoke(cli, ["--help"]).output
    assert "..." not in out.split("Commands:")[1].split("Getting started")[0]  # short help not truncated
    for name, command in cli.commands.items():
        assert name in out, name
        if isinstance(command, click.Group):
            for sub in command.commands:
                assert f"pskit {name} {sub}" in out, f"{name} {sub}"
    for name, command in cli.commands.items():
        result = CliRunner().invoke(cli, [name, "--help"])
        assert result.exit_code == 0, name
        if name not in ("logs",):
            assert "Examples:" in result.output, name


def test_doctor(tmp_path, monkeypatch):
    from py_serverless_kit.core import setup_check

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code == 2 and "pskit doctor -p aws" in result.output

    def fake(provider, raw=None, root=None):
        status = "missing" if provider == "gcp" else "ok"
        item = {
            "id": "tool:terraform",
            "title": "Terraform",
            "status": status,
            "detail": "not found",
            "fix": {
                "summary": "Install Terraform",
                "links": [{"label": "Install", "url": "https://example.test/tf"}],
                "steps": {"windows": ["winget install X"], "macos": ["brew install X"], "linux": ["apt install X"]},
                "commands": [],
                "action": None,
            },
        }
        return {"provider": provider, "ok": status == "ok", "checks": [item]}

    monkeypatch.setattr(setup_check, "check", fake)
    ok_run = CliRunner().invoke(cli, ["doctor", "-p", "aws"])
    assert ok_run.exit_code == 0, ok_run.output
    bad = CliRunner().invoke(cli, ["doctor", "-p", "gcp"])
    assert bad.exit_code == 1 and "https://example.test/tf" in bad.output and "Install Terraform" in bad.output
    js = CliRunner().invoke(cli, ["doctor", "-p", "gcp", "--json"])
    assert json.loads(js.output)["provider"] == "gcp"
    assert CliRunner().invoke(cli, ["doctor", "-p", "nope"]).exit_code == 2
    (tmp_path / "pskit.yml").write_text("service: s\nprovider: aws\n")
    assert "aws" in CliRunner().invoke(cli, ["doctor"]).output
