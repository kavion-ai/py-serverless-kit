"""The on-premises host drives Node.js functions through a worker process."""

from __future__ import annotations

import base64
import importlib.util
import json
import shutil
import sys
import threading
import types
from pathlib import Path
from urllib.request import urlopen

import pytest

from py_serverless_kit.runtime.batch import BatchResult
from py_serverless_kit.runtime.event import Event, EventType, HttpRequest, Record
from py_serverless_kit.runtime.onprem_host import Host, NodeFunctionError, node_result
from py_serverless_kit.runtime.response import Response


def _write_host(root: Path, functions, workflows=None, extra=None) -> Path:
    app = root / "app"
    app.mkdir(parents=True)
    manifest = {
        "service": "demo",
        "stage": "dev",
        "provider": "onprem",
        "region": "local",
        "functions": {
            name: {
                "handler": body["handler"],
                "routes": body.get("routes", []),
                "timeout": 10,
                "memory": 128,
                "resource_name": f"demo-dev-{name}",
            }
            for name, body in functions.items()
        },
        "workflows": workflows or {},
    }
    (app / "pskit_manifest.json").write_text(json.dumps(manifest), "utf-8")
    spec = {
        "service": "demo",
        "stage": "dev",
        "region": "local",
        "host": "127.0.0.1",
        "port": 0,
        "endpoint": "http://127.0.0.1:0",
        "data_dir": str(root / "data"),
        "services": {},
        "resources": {},
        "language": "node",
        "node_bin": "node",
        "functions": {
            name: {
                "handler": body["handler"],
                "timeout": 10,
                "environment": {"GREETING": "hi"},
                "events": body.get("events", []),
            }
            for name, body in functions.items()
        },
        **(extra or {}),
    }
    (root / "pskit_host.json").write_text(json.dumps(spec), "utf-8")
    return root


class FakeWorker:
    created: list = []

    def __init__(self, bundle_root, env=None, node="node", on_log=None):
        self.bundle_root = bundle_root
        self.env = env or {}
        self.node = node
        self.on_log = on_log
        self.calls: list = []
        self.closed = False
        FakeWorker.created.append(self)

    def call(self, function, event, context, timeout):
        # Same API as NodeWorker.call: an Event and a Context; inspect the wire form.
        event = event.to_wire()
        self.calls.append((function, event, context, timeout))
        if self.on_log:
            self.on_log(json.dumps({"level": "WARNING", "message": "from node", "order": 7}))
            self.on_log("plain text on stderr")
        kind = event["type"]
        if kind == "http":
            body = base64.b64encode(json.dumps({"path": event["http"]["path"]}).encode()).decode()
            return {"id": "1", "ok": True, "kind": "http", "status": 201, "headers": {"x-a": "1"}, "body_b64": body}
        if kind == "queue":
            return {"id": "1", "ok": True, "kind": "batch", "failed": ["m2"]}
        if kind == "invoke" and event.get("data") == "boom":
            return {"id": "1", "ok": False, "error": {"type": "TypeError", "message": "bad", "stack": "at x"}}
        data = dict(event.get("data") or {})
        data["by"] = function
        return {"id": "1", "ok": True, "kind": "value", "value": data}

    def close(self):
        self.closed = True


def _to_wire(self):
    out = {"type": self.type, "provider": self.provider, "function": self.function, "data": self.data}
    if self.http is not None:
        out["http"] = {"method": self.http.method, "path": self.http.path}
    out["records"] = [{"id": r.id, "body": r.body} for r in self.records]
    return out


@pytest.fixture
def fake_worker(monkeypatch):
    FakeWorker.created = []
    module = types.ModuleType("py_serverless_kit.runtime.node_worker")
    module.NodeWorker = FakeWorker  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "py_serverless_kit.runtime.node_worker", module)
    if not hasattr(Event, "to_wire"):
        monkeypatch.setattr(Event, "to_wire", _to_wire, raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/node" if name == "node" else None)
    return FakeWorker


def test_node_result_mapping():
    body = base64.b64encode(b"hello").decode()
    resp = node_result(
        {"ok": True, "kind": "http", "status": 200, "headers": {"set-cookie": ["a=1", "b=2"]}, "body_b64": body}
    )
    assert isinstance(resp, Response) and resp.body == b"hello" and resp.cookies == ["a=1", "b=2"]
    assert node_result({"ok": True, "kind": "batch", "failed": ["x"]}).failed == ["x"]
    assert node_result({"ok": True, "kind": "value", "value": {"a": 1}}) == {"a": 1}
    with pytest.raises(NodeFunctionError, match="TypeError: bad"):
        node_result({"ok": False, "error": {"type": "TypeError", "message": "bad"}})


def test_host_routes_every_invocation_through_the_worker(tmp_path, fake_worker):
    root = _write_host(
        tmp_path,
        {
            "api": {"handler": "src.handlers.api", "routes": [{"method": "GET", "path": "/hi", "cors": None}]},
            "jobs": {"handler": "src.handlers.jobs", "events": [{"type": "queue", "name": "jobs"}]},
            "step": {"handler": "src.handlers.step"},
        },
    )
    host = Host(root)
    host.open()
    try:
        assert host.invoke("step", Event(type=EventType.INVOKE, data={"n": 1})) == {"n": 1, "by": "step"}
        resp = host.invoke("api", Event(type=EventType.HTTP, http=HttpRequest(path="/hi")))
        assert isinstance(resp, Response) and resp.status == 201
        result = host.invoke("jobs", Event(type=EventType.QUEUE, records=[Record(id="m1"), Record(id="m2")]))
        assert isinstance(result, BatchResult) and result.failed == ["m2"]
        with pytest.raises(NodeFunctionError):
            host.invoke("step", Event(type=EventType.INVOKE, data="boom"))
        # One worker per function, each with its own environment.
        workers = {w.env["PSKIT_FUNCTION"]: w for w in fake_worker.created}
        assert set(workers) == {"step", "api", "jobs"}
        assert workers["api"].env["GREETING"] == "hi"
        assert workers["api"].env["PSKIT_BUNDLE_ROOT"] == str(root / "app")
        assert workers["step"].calls[0][2].deadline > 0
        # Worker stderr lands in the host log as function entries.
        entries = host.logs.query(limit=100)["entries"]
        assert any(e["source"] == "function" and e["message"] == "from node" and e["level"] == "WARNING" for e in entries)
        assert any(e["source"] == "stdout" and e["message"] == "plain text on stderr" for e in entries)
        assert host.stats()["functions"]["step"]["errors"] == 1
    finally:
        host.close_workers()
    assert all(w.closed for w in fake_worker.created)


def test_embedded_workflow_tasks_run_in_the_worker(tmp_path, fake_worker):
    definition = {"start_at": "Go", "states": {"Go": {"type": "task", "function": "step", "end": True}}}
    root = _write_host(
        tmp_path,
        {
            "step": {"handler": "src.handlers.step"},
            "ping-orchestrator": {"handler": "pskit_runtime.workflow.orchestrate"},
        },
        workflows={"ping": {"orchestrator": "ping-orchestrator", "definition": definition}},
    )
    host = Host(root)
    host.open()
    try:
        record = host.executor.start("ping", {"order": 1}, wait=True)  # type: ignore[union-attr]
        assert record["status"] == "SUCCEEDED"
        assert host.executor.result_body(record)["output"] == {"order": 1, "by": "step"}  # type: ignore[union-attr]
        # The orchestrator itself never reaches a worker: the Python executor runs it.
        # A direct invoke waits for the run (like the Python orchestrator does).
        done = host.invoke("ping-orchestrator", Event(type=EventType.INVOKE, data={"order": 2}))
        assert done["status"] == "SUCCEEDED" and done["output"] == {"order": 2, "by": "step"}
        assert {w.env["PSKIT_FUNCTION"] for w in fake_worker.created} == {"step"}
    finally:
        host.close_workers()
        host.executor.shutdown()  # type: ignore[union-attr]


def test_missing_node_is_a_clear_error(tmp_path, fake_worker, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    root = _write_host(tmp_path, {"step": {"handler": "src.handlers.step"}})
    host = Host(root)
    host.open()
    with pytest.raises(RuntimeError, match="Node.js"):
        host.invoke("step", Event(type=EventType.INVOKE, data={}))


def test_bundled_node_binary_is_preferred(tmp_path, fake_worker):
    root = _write_host(tmp_path, {"step": {"handler": "src.handlers.step"}}, extra={"node_bin": "node/bin/node"})
    binary = root / "node" / "bin" / "node"
    binary.parent.mkdir(parents=True)
    binary.write_text("", "utf-8")
    host = Host(root)
    host.open()
    host.invoke("step", Event(type=EventType.INVOKE, data={}))
    assert fake_worker.created[0].node == str(binary)
    host.close_workers()


# --------------------------------------------------------------------------- real node

_WORKER = Path(__file__).resolve().parents[2] / "src" / "py_serverless_kit" / "runtime_js" / "worker.js"
_REAL = (
    shutil.which("node") is not None
    and _WORKER.is_file()
    and importlib.util.find_spec("py_serverless_kit.runtime.node_worker") is not None
    and hasattr(Event, "to_wire")
)

NODE_CONFIG = """
service: nodedemo
provider:
  name: onprem
  runtime: nodejs20
  options:
    host: 127.0.0.1
    port: 8098
    data_dir: {data}
functions:
  hello:
    handler: src.handlers.hello
    events: [{{http: GET /hello}}]
  step:
    handler: src.handlers.step
  jobs:
    handler: src.handlers.jobs
    events: [{{queue: {{name: jobs, max_receive: 1}}}}]
workflows:
  ping:
    start_at: Go
    states:
      Go: {{type: task, function: step, end: true}}
"""

NODE_HANDLERS = """
exports.hello = async (event, ctx) => {
  ctx.logger.info("hello from node");
  return { name: event.http.query.name || "", runtime: "node" };
};
exports.step = (event) => ({ ...(event.data || {}), seen: true });
exports.jobs = (event) => ({ failed: [] });
"""


@pytest.mark.skipif(not _REAL, reason="needs node, runtime_js/worker.js and runtime/node_worker.py")
def test_end_to_end_with_a_real_node_worker(make_project, tmp_path):
    from py_serverless_kit.core.deployer import Deployer
    from py_serverless_kit.runtime.onprem_host import activate_layout

    project = make_project(
        NODE_CONFIG.format(data=(tmp_path / "data").as_posix()),
        files={"src/handlers.js": NODE_HANDLERS, "package.json": json.dumps({"name": "nodedemo", "version": "1.0.0"})},
    )
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    httpd = host.make_server(0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urlopen(base + "/hello?name=Ada", timeout=30) as resp:
            assert json.loads(resp.read().decode()) == {"name": "Ada", "runtime": "node"}
        assert host.invoke("step", Event(type=EventType.INVOKE, data={"a": 1})) == {"a": 1, "seen": True}
        record = host.executor.start("ping", {"o": 1}, wait=True)  # type: ignore[union-attr]
        assert record["status"] == "SUCCEEDED"
        entries = host.logs.query(limit=200)["entries"]
        assert any(e["source"] == "function" and "hello from node" in e["message"] for e in entries)
    finally:
        httpd.shutdown()
        httpd.server_close()
        host.close_workers()
        host.executor.shutdown()  # type: ignore[union-attr]
