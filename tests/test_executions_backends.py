"""Execution backends (AWS, GCP, embedded, on-prem) and the workflow / logs CLI commands."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.core.describe import build_record
from py_serverless_kit.core.executions import (
    AwsBackend,
    EmbeddedCloudBackend,
    ExecutionError,
    GcpBackend,
    OnPremBackend,
    UnsupportedBackend,
    backend_for,
)
from py_serverless_kit.core.onprem_control import HostControl, HostUnavailable, control_for

ARN = "arn:aws:states:eu-west-1:123:stateMachine:svc-dev-orders"
EXEC = "arn:aws:states:eu-west-1:123:execution:svc-dev-orders:abc"
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _record(provider="aws", engine="native", wf_id=ARN, **extra):
    record = {
        "provider": provider,
        "stage": "dev",
        "region": "eu-west-1",
        "status": "deployed",
        "workflows": [{"name": "orders", "engine": engine, "id": wf_id}],
        "functions": [],
    }
    record.update(extra)
    return record


class FakeSfn:
    def __init__(self):
        self.calls = []

    def list_executions(self, **kw):
        self.calls.append(("list", kw))
        return {
            "executions": [
                {"executionArn": EXEC, "status": "SUCCEEDED", "startDate": T0, "stopDate": T0 + timedelta(seconds=2)},
                {"executionArn": EXEC + "2", "status": "RUNNING", "startDate": T0 + timedelta(seconds=5)},
            ],
            "nextToken": "tok2",
        }

    def describe_execution(self, executionArn):
        return {
            "executionArn": executionArn,
            "status": "FAILED",
            "startDate": T0,
            "stopDate": T0 + timedelta(seconds=1),
            "input": '{"order": 1}',
            "error": "Payment.Declined",
            "cause": "card",
        }

    def get_execution_history(self, **kw):
        return {
            "events": [
                {"type": "ExecutionStarted", "timestamp": T0},
                {"type": "TaskStateEntered", "timestamp": T0, "stateEnteredEventDetails": {"name": "Charge"}},
                {"type": "TaskFailed", "timestamp": T0, "taskFailedEventDetails": {"error": "Payment.Declined"}},
                {"type": "TaskStateExited", "timestamp": T0, "stateExitedEventDetails": {"name": "Charge"}},
            ]
        }

    def start_execution(self, **kw):
        self.calls.append(("start", kw))
        return {"executionArn": EXEC, "startDate": T0}

    def stop_execution(self, **kw):
        self.calls.append(("stop", kw))


def test_aws_backend_maps_step_functions():
    sfn = FakeSfn()
    backend = AwsBackend(_record(), client=sfn)
    listed = backend.list(workflow="orders", status="cancelled", limit=5, token="tok1")
    kwargs = sfn.calls[-1][1]
    assert kwargs == {"stateMachineArn": ARN, "maxResults": 5, "statusFilter": "ABORTED", "nextToken": "tok1"}
    assert listed["next_token"] == "tok2" and listed["total"] is None
    assert [i["status"] for i in listed["items"]] == ["RUNNING", "SUCCEEDED"]  # newest first
    assert listed["items"][1]["duration_ms"] == 2000.0 and "eu-west-1.console.aws" in listed["items"][1]["console"]

    detail = backend.get(EXEC)
    assert detail["workflow"] == "orders" and detail["input"] == {"order": 1}
    assert detail["error"] == "Payment.Declined"
    assert [h["event"] for h in detail["history"]] == ["enter", "fail", "exit"]

    started = backend.start("orders", {"x": 1})
    assert started["execution_id"] == EXEC and json.loads(sfn.calls[-1][1]["input"]) == {"x": 1}
    backend.cancel(EXEC)
    assert sfn.calls[-1][0] == "stop"
    with pytest.raises(ValueError):
        backend.list(status="bogus")
    with pytest.raises(KeyError):
        backend.start("nope", {})


def test_aws_backend_without_boto3(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_boto(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("no boto3")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_boto)
    with pytest.raises(ExecutionError, match=r"py-serverless-kit\[aws\]"):
        AwsBackend(_record()).list()


class FakeGcp:
    def __init__(self):
        self.requests = []
        state = SimpleNamespace(name="ACTIVE")
        self.ex = SimpleNamespace(
            name="projects/p/locations/us-central1/workflows/svc-dev-orders/executions/e1",
            state=state,
            start_time=T0,
            end_time=None,
            argument='{"a": 1}',
            result="",
            error=None,
            status=SimpleNamespace(current_steps=[SimpleNamespace(routine="main", step="charge")]),
        )

    def list_executions(self, request):
        self.requests.append(request)
        page = SimpleNamespace(executions=[self.ex], next_page_token="n2")
        return SimpleNamespace(pages=iter([page]))

    def get_execution(self, request):
        return self.ex

    def create_execution(self, request):
        self.requests.append(request)
        return self.ex

    def cancel_execution(self, request):
        return SimpleNamespace(**{**vars(self.ex), "state": SimpleNamespace(name="CANCELLED")})


def test_gcp_backend_maps_cloud_workflows():
    gcp = FakeGcp()
    wf_id = "projects/p/locations/us-central1/workflows/svc-dev-orders"
    backend = GcpBackend(_record("gcp", wf_id=wf_id), client=gcp)
    listed = backend.list(workflow="orders", limit=3)
    assert gcp.requests[-1] == {"parent": wf_id, "page_size": 3}
    item = listed["items"][0]
    assert item["status"] == "RUNNING" and item["current_state"] == "charge" and listed["next_token"] == "n2"
    assert item["console"].endswith("/svc-dev-orders/execution/e1?project=p")
    assert backend.list(workflow="orders", status="SUCCEEDED")["items"] == []
    detail = backend.get(item["execution_id"])
    assert detail["workflow"] == "orders" and detail["input"] == {"a": 1}
    backend.start("orders", {"b": 2})
    assert json.loads(gcp.requests[-1]["execution"]["argument"]) == {"b": 2}
    assert backend.cancel(item["execution_id"])["status"] == "CANCELLED"


def test_backend_selection(tmp_path):
    assert isinstance(backend_for(_record(), tmp_path), AwsBackend)
    assert isinstance(backend_for(_record("gcp"), tmp_path), GcpBackend)
    assert isinstance(backend_for(_record("azure", engine="embedded"), tmp_path), EmbeddedCloudBackend)
    assert isinstance(backend_for(_record("aws", engine="embedded"), tmp_path), EmbeddedCloudBackend)
    local = backend_for(_record(status="local"), tmp_path)
    assert isinstance(local, UnsupportedBackend) and local.list()["supported"] is False
    with pytest.raises(ExecutionError):
        local.get("x")
    assert isinstance(backend_for(_record(workflows=[]), tmp_path), UnsupportedBackend)
    onprem = backend_for(_record("onprem", engine="embedded", endpoint="http://127.0.0.1:9"), tmp_path)
    assert isinstance(onprem, OnPremBackend)


def test_embedded_cloud_backend_posts_to_the_orchestrator(monkeypatch):
    seen = {}

    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen["url"], seen["body"] = req.full_url, json.loads(req.data)
        return Resp(b'{"execution_id": "abc", "status": "SUCCEEDED", "output": 1}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    record = _record(
        "azure",
        engine="embedded",
        functions=[{"name": "orders-orchestrator", "urls": [{"method": "POST", "url": "https://x/workflows/orders"}]}],
    )
    backend = EmbeddedCloudBackend(record)
    result = backend.start("orders", {"n": 1})
    assert seen == {"url": "https://x/workflows/orders", "body": {"n": 1}}
    assert result["execution_id"] == "abc" and result["source"] == "embedded"
    assert backend.list()["supported"] is False and "no execution history" in backend.list()["reason"]
    with pytest.raises(ExecutionError, match="no HTTP URL"):
        EmbeddedCloudBackend(_record("azure", engine="embedded")).start("orders", {})


def test_host_control_errors():
    with pytest.raises(ValueError):
        HostControl("file:///etc/passwd")
    with pytest.raises(HostUnavailable):
        HostControl("http://127.0.0.1:1", timeout=1).health()
    assert control_for(_record("aws"), __import__("pathlib").Path(".")) is None


# ------------------------------------------------------------------ live on-prem host + CLI

HANDLERS = """
from py_serverless_kit import Context, Event


def step(event: Event, ctx: Context):
    print("stepping", event.data)
    return dict(event.data or {}, done=True)
"""

CONFIG = """
service: clidemo
provider:
  name: onprem
  runtime: python3.12
  options: {{host: 127.0.0.1, port: 8097, data_dir: {data}, admin_token: tok}}
functions:
  step:
    handler: app.handlers.step
workflows:
  flow:
    start_at: Go
    states:
      Go: {{type: task, function: step, end: true}}
"""


@pytest.fixture
def live_host(make_project, tmp_path, monkeypatch):
    from py_serverless_kit.core.deployer import Deployer
    from py_serverless_kit.runtime.onprem_host import Host, activate_layout

    project = make_project(CONFIG.format(data=(tmp_path / "data").as_posix()), files={"app/handlers.py": HANDLERS})
    deployer = Deployer(project, echo=lambda _m: None)
    deployer.package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    httpd = host.make_server(0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    spec_path = root / "pskit_host.json"
    spec = json.loads(spec_path.read_text("utf-8"))
    spec["port"] = port
    spec_path.write_text(json.dumps(spec), "utf-8")
    deployer.save_record(build_record(project, {"pskit": {"endpoint": f"http://127.0.0.1:{port}"}}))
    monkeypatch.chdir(tmp_path)
    yield project, host
    httpd.shutdown()
    httpd.server_close()
    host.executor.shutdown()
    host.logs.close()


def _cli(*args):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


def test_cli_workflow_lifecycle_and_logs(live_host):
    project, host = live_host
    record = json.loads((project.work_dir / "deployment.json").read_text("utf-8"))
    control = control_for(record, project.root)
    assert control is not None and control.token == "tok"

    result = _cli("workflow", "start", "flow", "-i", '{"n": 1}', "--json")
    assert result.exit_code == 0, result.output
    started = json.loads(result.output)
    eid = started["execution_id"]
    deadline = time.time() + 5
    while host.executor.get(eid)["status"] == "RUNNING" and time.time() < deadline:
        time.sleep(0.05)

    result = _cli("workflow", "status", eid, "--history")
    assert result.exit_code == 0 and "SUCCEEDED" in result.output and '"done": true' in result.output
    assert "enter" in result.output

    result = _cli("workflow", "start", "flow", "--wait")
    assert result.exit_code == 0 and "SUCCEEDED" in result.output and "execution_id:" in result.output

    result = _cli("workflow", "executions", "flow", "-n", "1")
    assert result.exit_code == 0 and "more (use --offset 1)" in result.output

    result = _cli("workflow", "executions", "--json")
    assert json.loads(result.output)["total"] == 2

    result = _cli("workflow", "cancel", eid)
    assert result.exit_code == 0 and "SUCCEEDED" in result.output  # already finished: unchanged

    result = _cli("workflow", "start", "nope")
    assert result.exit_code == 1 and "unknown workflow" in result.output

    result = _cli("logs", "--source", "invocation", "--json")
    lines = [json.loads(line) for line in result.output.splitlines()]
    assert lines and all(e["source"] == "invocation" for e in lines) and lines[0]["function"] == "step"

    result = _cli("logs", "--function", "step", "-n", "5")
    assert result.exit_code == 0 and "[step]" in result.output


def test_cli_logs_cloud_without_sdk(make_project, monkeypatch, tmp_path):
    from py_serverless_kit.core import cloud_logs
    from py_serverless_kit.core.deployer import Deployer

    monkeypatch.setattr(cloud_logs, "_installed", lambda module: False)

    project = make_project("service: xx\nprovider: {name: aws}\nfunctions: {a: {handler: app.handlers.hello}}\n")
    monkeypatch.chdir(tmp_path)
    result = _cli("logs")
    assert result.exit_code == 1 and "not deployed yet" in result.output
    Deployer(project, echo=lambda _m: None).save_record(build_record(project))
    result = _cli("logs")
    assert result.exit_code == 1 and "boto3" in result.output
    result = _cli("workflow", "executions")
    assert result.exit_code == 1 and "no workflows" in result.output
