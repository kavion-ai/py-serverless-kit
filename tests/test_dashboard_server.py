import json
import sys
import threading
import types
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

import pytest

from py_serverless_kit.core.describe import build_record
from py_serverless_kit.dashboard.server import make_server

CONFIG = """
service: dash
provider: {name: onprem}
functions:
  a: {handler: app.handlers.step}
workflows:
  flow:
    start_at: One
    states:
      One: {type: task, function: a, end: true}
"""


class FakeUnavailable(Exception):
    pass


class FakeControl:
    base_url = "http://127.0.0.1:9"
    calls: list = []
    down = False

    def health(self) -> dict:
        if self.down:
            raise FakeUnavailable("connection refused")
        return {"ok": True}

    def stats(self) -> dict:
        return {"uptime_s": 5, "functions": {"a": {"invocations": 2, "errors": 0}}, "queues": {}}

    def logs(self, since=0, limit=200, level=None, function=None, q=None, source=None) -> dict:
        FakeControl.calls.append({"since": since, "limit": limit, "level": level, "function": function, "q": q})
        if self.down:
            raise FakeUnavailable("connection refused")
        return {"entries": [{"seq": since + 1, "message": "hi", "level": "INFO"}], "next": since + 1, "oldest": 1}

    def log_streams(self) -> dict:
        return {"items": [{"function": "a", "count": 2}, {"function": None, "count": 1}]}

    def clear_logs(self, function=None) -> dict:
        FakeControl.calls.append({"clear": function})
        return {"deleted": 3}


class FakeExecutionError(Exception):
    pass


class FakeBackend:
    supported = True
    reason = ""
    started: list = []

    def list(self, workflow=None, status=None, limit=20, offset=0, token=None) -> dict:
        items = [
            {"execution_id": f"e{i}", "workflow": "flow", "status": "SUCCEEDED"} for i in range(offset, offset + limit)
        ]
        return {"items": items[: max(0, 3 - offset)], "total": 3, "next_token": None}

    def get(self, execution_id: str, workflow: Optional[str] = None) -> dict:
        if execution_id == "missing":
            raise KeyError("no such execution")
        if execution_id == "boom":
            raise FakeExecutionError("backend down")
        return {"execution_id": execution_id, "workflow": "flow", "status": "RUNNING", "history": []}

    def start(self, workflow: str, data: Any) -> dict:
        FakeBackend.started.append((workflow, data))
        return {"execution_id": "new1", "workflow": workflow, "status": "RUNNING"}

    def cancel(self, execution_id: str, workflow: Optional[str] = None) -> dict:
        return {"execution_id": execution_id, "workflow": "flow", "status": "CANCELLED"}


class Unsupported(FakeBackend):
    supported = False
    reason = "embedded workflows on this cloud keep no history"


@pytest.fixture
def fakes(monkeypatch):
    control_mod = types.ModuleType("py_serverless_kit.core.onprem_control")
    control_mod.HostUnavailable = FakeUnavailable  # type: ignore[attr-defined]
    control = FakeControl()
    control_mod.control_for = lambda record, root, server=None: control if record.get("provider") == "onprem" else None  # type: ignore[attr-defined]
    exec_mod = types.ModuleType("py_serverless_kit.core.executions")
    exec_mod.ExecutionError = FakeExecutionError  # type: ignore[attr-defined]
    state = {"backend": FakeBackend()}
    exec_mod.backend_for = lambda record, root: state["backend"]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "py_serverless_kit.core.onprem_control", control_mod)
    monkeypatch.setitem(sys.modules, "py_serverless_kit.core.executions", exec_mod)
    FakeControl.calls = []
    FakeBackend.started = []
    return {"control": control, "state": state}


@pytest.fixture
def server(make_project, fakes):
    project = make_project(CONFIG)
    work = project.work_dir
    work.mkdir(parents=True)
    (work / "deployment.json").write_text(json.dumps(build_record(project)), "utf-8")
    httpd = make_server(project.root, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, work.name
    httpd.shutdown()
    httpd.server_close()


def call(
    url: str, method: str = "GET", body: Any = None, headers: Optional[Dict[str, str]] = None
) -> Tuple[int, Any, Dict[str, str]]:
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("content-type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            status, hdrs = resp.status, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        raw, status, hdrs = exc.read(), exc.code, dict(exc.headers)
    ctype = hdrs.get("Content-Type", hdrs.get("content-type", ""))
    return status, json.loads(raw) if "json" in ctype else raw.decode(), hdrs


def test_page_and_deployments(server):
    base, key = server
    status, html, headers = call(base + "/")
    assert status == 200 and "dash dashboard" in html and '<script type="application/json" id="data">' in html
    assert "content-security-policy" in {k.lower() for k in headers}
    status, data, _ = call(base + "/api/deployments")
    assert status == 200 and data["deployments"][0]["key"] == key == "onprem-dev"
    assert call(base + "/nope")[0] == 404


def test_logs_and_health(server, fakes):
    base, key = server
    status, data, _ = call(f"{base}/api/deployments/{key}/logs?since=4&limit=5000&level=ERROR")
    assert status == 200 and data["supported"] and data["next"] == 5
    assert FakeControl.calls[-1] == {"since": 4, "limit": 1000, "level": "ERROR", "function": None, "q": None}
    assert call(f"{base}/api/deployments/{key}/logs?since=x")[0] == 400
    status, data, _ = call(f"{base}/api/deployments/{key}/health")
    assert data["live"] and data["stats"]["functions"]["a"]["invocations"] == 2
    fakes["control"].down = True
    try:
        status, data, _ = call(f"{base}/api/deployments/{key}/health")
        assert status == 200 and data == {"live": False, "reason": "connection refused"}
        status, data, _ = call(f"{base}/api/deployments/{key}/logs")
        assert status == 502 and "unreachable" in data["error"]
    finally:
        fakes["control"].down = False


def test_unknown_deployment(server):
    base, _ = server
    assert call(f"{base}/api/deployments/aws-prod/logs")[0] == 404
    assert call(f"{base}/api/deployments/..%2f..%2fetc/logs")[0] == 400


def test_executions_api(server, fakes):
    base, key = server
    status, data, _ = call(f"{base}/api/deployments/{key}/executions?workflow=flow&limit=2&offset=1")
    assert status == 200 and data["total"] == 3 and [i["execution_id"] for i in data["items"]] == ["e1", "e2"]
    assert call(f"{base}/api/deployments/{key}/executions?workflow=other")[0] == 404
    assert call(f"{base}/api/deployments/{key}/executions/x1")[1]["status"] == "RUNNING"
    assert call(f"{base}/api/deployments/{key}/executions/missing")[0] == 404
    assert call(f"{base}/api/deployments/{key}/executions/boom")[0] == 502

    status, data, _ = call(f"{base}/api/deployments/{key}/workflows/flow/start", "POST", {"n": 1})
    assert status == 202 and data["execution_id"] == "new1" and FakeBackend.started == [("flow", {"n": 1})]
    assert call(f"{base}/api/deployments/{key}/workflows/ghost/start", "POST", {})[0] == 404
    status, data, _ = call(f"{base}/api/deployments/{key}/executions/new1/cancel", "POST", {})
    assert status == 200 and data["status"] == "CANCELLED"

    fakes["state"]["backend"] = Unsupported()
    status, data, _ = call(f"{base}/api/deployments/{key}/executions")
    assert status == 200 and data["supported"] is False and "history" in data["reason"]
    assert call(f"{base}/api/deployments/{key}/workflows/flow/start", "POST", {})[0] == 400


def test_post_protections(server):
    base, key = server
    url = f"{base}/api/deployments/{key}/workflows/flow/start"
    assert call(url, "POST", b"x=1", {"content-type": "application/x-www-form-urlencoded"})[0] == 403
    assert call(url, "POST", {}, {"origin": "http://evil.example"})[0] == 403
    assert call(url, "POST", {}, {"origin": "null"})[0] == 403
    assert call(url, "POST", {}, {"origin": base})[0] == 202
    assert call(url, "POST", b"{not json")[0] == 400
    assert call(url, "POST", b"{}", {"content-length": str(1024 * 1024 + 1)})[0] == 413
    assert call(f"{base}/api/deployments/{key}/logs", "POST", {})[0] == 405


def test_rejects_foreign_host_header(server):
    base, key = server
    status, data, _ = call(f"{base}/api/deployments", headers={"host": "attacker.example:80"})
    assert status == 421
    port = base.rsplit(":", 1)[1]
    assert call(f"{base}/api/deployments", headers={"host": f"localhost:{port}"})[0] == 200


def test_non_onprem_logs_unsupported(make_project, fakes):
    project = make_project("service: dash\nprovider: {name: aws}\nfunctions: {a: {handler: app.handlers.hello}}\n")
    httpd = make_server(project.root, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        status, data, _ = call(base + "/api/deployments")
        assert data["deployments"][0]["status"] == "local" and data["deployments"][0]["key"] == "aws-dev"
        status, data, _ = call(base + "/api/deployments/aws-dev/logs")
        assert status == 200 and data["supported"] is False
        assert call(base + "/api/deployments/aws-dev/health")[1]["live"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_log_streams_and_delete(server, fakes):
    base, key = server
    status, data, _ = call(f"{base}/api/deployments/{key}/logs?since=1")
    assert data["mode"] == "seq" and data["can_delete"] is True
    status, data, _ = call(f"{base}/api/deployments/{key}/logs/streams")
    assert status == 200 and [i["id"] for i in data["items"]] == ["a", "__host__"] and data["can_delete"]
    status, data, _ = call(f"{base}/api/deployments/{key}/logs/delete", "POST", {"ids": ["a"]})
    assert status == 200 and data["deleted"] == 3 and FakeControl.calls[-1] == {"clear": "a"}
    status, data, _ = call(f"{base}/api/deployments/{key}/logs/delete", "POST", {"all": True})
    assert status == 200 and FakeControl.calls[-1] == {"clear": None}
    assert call(f"{base}/api/deployments/{key}/logs/delete", "POST", {})[0] == 400
    assert call(f"{base}/api/deployments/{key}/logs/delete", "POST", {"ids": "a"})[0] == 400
    assert call(f"{base}/api/deployments/{key}/logs/delete", "POST", [1])[0] == 400
    status, _, _ = call(
        f"{base}/api/deployments/{key}/logs/delete", "POST", {"all": True}, headers={"Origin": "http://evil.example"}
    )
    assert status == 403
    assert call(f"{base}/api/deployments/{key}/logs/delete")[0] == 404


def test_cloud_logs_unsupported_delete(make_project, fakes):
    project = make_project("service: dash\nprovider: {name: cloudflare}\nfunctions: {a: {handler: app.handlers.hello}}\n")
    work = project.work_dir
    work.mkdir(parents=True)
    (work / "deployment.json").write_text(json.dumps(build_record(project)), "utf-8")
    httpd = make_server(project.root, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}/api/deployments/{work.name}"
        status, data, _ = call(base + "/logs")
        assert status == 200 and data["supported"] is False and "can't read" in data["reason"]
        status, data, _ = call(base + "/logs/streams")
        assert status == 200 and data["supported"] is False and data["items"] == []
        status, data, _ = call(base + "/logs/delete", "POST", {"all": True})
        assert status == 400
    finally:
        httpd.shutdown()
        httpd.server_close()
