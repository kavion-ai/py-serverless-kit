"""Node.js runtime: the JS test suite (``node --test``) and the Python ``NodeWorker`` client end to end."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from py_serverless_kit._version import __version__
from py_serverless_kit.runtime.batch import BatchResult
from py_serverless_kit.runtime.context import Context
from py_serverless_kit.runtime.event import Event, HttpRequest, Record, event_from_wire
from py_serverless_kit.runtime.node_worker import NodeFunctionError, NodeWorker, NodeWorkerError, NodeWorkerTimeout
from py_serverless_kit.runtime.response import Response

HERE = Path(__file__).resolve().parent
RUNTIME_JS = HERE.parents[1] / "src" / "py_serverless_kit" / "runtime_js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")


def test_runtime_package_version_matches_pskit():
    assert json.loads((RUNTIME_JS / "package.json").read_text("utf-8"))["version"] == __version__


@needs_node
def test_js_suite():
    files = sorted(str(p) for p in HERE.glob("*.test.js"))
    assert files
    env = dict(os.environ, PSKIT_LOG_LEVEL="CRITICAL")
    proc = subprocess.run(
        [NODE, "--test", *files], cwd=str(HERE.parents[1]), capture_output=True, text=True, env=env, timeout=600
    )  # type: ignore[list-item]
    assert proc.returncode == 0, proc.stdout[-6000:] + proc.stderr[-3000:]


def test_wire_round_trip_python():
    ev = Event(
        type="http",
        provider="onprem",
        function="f",
        http=HttpRequest(method="POST", path="/x", headers={"A": "b"}, body=b"\x00\xff", path_params={"id": "1"}),
        records=[Record(id="r", body=b"bin"), Record(id="j", body={"k": 1})],
        data={"d": 1},
    )
    wire = json.loads(json.dumps(ev.to_wire()))
    assert wire["http"]["body_b64"] == "AP8="
    assert wire["records"][0] == {
        "id": "r",
        "body": None,
        "body_b64": "Ymlu",
        "attributes": {},
        "source": None,
        "bucket": None,
        "key": None,
        "size": None,
        "action": None,
    }
    back = event_from_wire(wire)
    assert back.http is not None and back.http.body == b"\x00\xff" and back.http.headers["a"] == "b"
    assert back.records[0].body == b"bin" and back.records[1].body == {"k": 1}
    assert back.data == {"d": 1} and back.time == ev.time.replace(microsecond=ev.time.microsecond)


HANDLERS = """
const { Response, BatchResult } = require("pskit_runtime");
exports.hello = (e, ctx) => {
  console.log("console line");
  ctx.logger.info("hello", { who: e.http.pathParams.name });
  return Response.json({ hi: e.http.pathParams.name, rid: ctx.requestId });
};
exports.echo = async (e) => ({ type: e.type, data: e.data });
exports.slow = async (e) => { await new Promise((r) => setTimeout(r, e.data.ms)); return e.data.ms; };
exports.batch = (e) => BatchResult.of(e.records.filter((r) => r.json().bad));
exports.boom = () => { throw new TypeError("nope"); };
exports.die = () => { process.exit(3); };
exports.hang = () => new Promise(() => {});
"""


@pytest.fixture
def bundle(tmp_path):
    shutil.copytree(RUNTIME_JS, tmp_path / "pskit_runtime")
    (tmp_path / "app.js").write_text(HANDLERS, "utf-8")
    manifest = {
        "service": "demo",
        "stage": "dev",
        "provider": "onprem",
        "functions": {
            "hello": {"handler": "app.hello", "routes": [{"method": "GET", "path": "/hello/{name}"}]},
            **{name: {"handler": f"app.{name}"} for name in ("echo", "slow", "batch", "boom", "die", "hang")},
        },
        "workflows": {},
    }
    (tmp_path / "pskit_manifest.json").write_text(json.dumps(manifest), "utf-8")
    # `require("pskit_runtime")` from handlers resolves like the bundled node_modules/pskit would.
    (tmp_path / "node_modules").mkdir()
    shutil.copytree(RUNTIME_JS, tmp_path / "node_modules" / "pskit_runtime")
    return tmp_path


@pytest.fixture
def worker(bundle):
    logs = []
    w = NodeWorker(bundle, env={"PSKIT_LOG_LEVEL": "INFO"}, on_log=logs.append)
    w.logs = logs  # type: ignore[attr-defined]
    yield w
    w.close()


@needs_node
def test_worker_http_value_batch_and_errors(worker):
    resp = worker.execute(
        "hello", Event(type="http", provider="onprem", http=HttpRequest(path="/hello/ada")), Context(request_id="rq-1")
    )
    assert isinstance(resp, Response) and resp.status == 200
    assert json.loads(resp.body) == {"hi": "ada", "rid": "rq-1"}
    assert resp.headers["content-type"] == "application/json"

    raw = worker.call(
        "hello", Event(type="http", provider="onprem", http=HttpRequest(method="POST", path="/hello/ada"))
    )
    assert raw["kind"] == "http" and raw["status"] == 405

    assert worker.execute("echo", Event(type="invoke", data={"x": [1, 2]})) == {"type": "invoke", "data": {"x": [1, 2]}}

    batch = worker.execute(
        "batch",
        Event(
            type="queue",
            provider="onprem",
            records=[Record(id="1", body='{"bad": false}'), Record(id="2", body='{"bad": true}')],
        ),
    )
    assert isinstance(batch, BatchResult) and batch.failed == ["2"]

    with pytest.raises(NodeFunctionError) as exc:
        worker.execute("boom", Event(type="invoke"))
    assert exc.value.error == "TypeError" and str(exc.value) == "nope" and "app.js" in exc.value.stack

    deadline = time.time() + 5
    while time.time() < deadline and not any("console line" in line for line in worker.logs):
        time.sleep(0.05)
    assert any("console line" in line for line in worker.logs)
    assert any('"message":"hello"' in line and '"who":"ada"' in line for line in worker.logs)


@needs_node
def test_worker_concurrent_calls(worker):
    results = {}

    def run(ms):
        results[ms] = worker.execute("slow", Event(type="invoke", data={"ms": ms}))

    started = time.perf_counter()
    threads = [threading.Thread(target=run, args=(ms,)) for ms in (300, 250, 200, 10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert results == {300: 300, 250: 250, 200: 200, 10: 10}
    assert time.perf_counter() - started < 3  # ran concurrently in one process


@needs_node
def test_worker_restarts_after_crash_and_times_out(worker):
    first = worker.pid
    with pytest.raises(NodeWorkerError):
        worker.execute("die", Event(type="invoke"), timeout=20)
    assert worker.execute("echo", Event(type="invoke", data=1)) == {"type": "invoke", "data": 1}
    assert worker.pid != first
    with pytest.raises(NodeWorkerTimeout):
        worker.execute("hang", Event(type="invoke"), timeout=0.3)
    assert worker.ping()


@needs_node
def test_worker_uses_packaged_runtime_for_a_project_folder(tmp_path):
    # Local dev: no pskit_runtime/ in the folder, the packaged runtime is used with PSKIT_BUNDLE_ROOT.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "handlers.js").write_text("exports.hi = (e) => `hi ${e.data}`;\n", "utf-8")
    (tmp_path / "pskit_manifest.json").write_text(
        json.dumps({"functions": {"hi": {"handler": "src.handlers.hi"}}}), "utf-8"
    )
    with NodeWorker(tmp_path, on_log=lambda _l: None) as w:
        assert w.worker == (RUNTIME_JS / "worker.js").resolve()
        assert w.execute("hi", Event(type="invoke", data="you")) == "hi you"


def test_missing_node_is_a_clear_error(tmp_path):
    w = NodeWorker(tmp_path, node="definitely-not-node-xyz")
    with pytest.raises(NodeWorkerError, match="was not found"):
        w.execute("x", Event(type="invoke"))
