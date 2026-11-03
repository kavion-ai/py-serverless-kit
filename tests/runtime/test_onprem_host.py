"""The on-premises host serves HTTP and the backing services it deploys."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.runtime.onprem_host import Host, activate_layout, health_url

HANDLERS = """
import os
from pathlib import Path

from py_serverless_kit import BatchResult, Context, Event, invoke


def hello(event: Event, ctx: Context):
    return {"provider": event.provider, "name": event.http.query.get("name", "")}


def parent(event: Event, ctx: Context):
    return invoke("child", {"n": 2})


def child(event: Event, ctx: Context):
    return {"n": event.data["n"] + 1}


def tick(event: Event, ctx: Context):
    Path(os.environ["OUT"]).write_text("schedule:" + json_dump(event.data), encoding="utf-8")
    return {"ok": True}


def json_dump(value):
    import json
    return json.dumps(value)


def worker(event: Event, ctx: Context):
    result = BatchResult()
    done = []
    for record in event.records:
        if record.text() == "fail":
            result.fail(record)
        else:
            done.append(record.text())
    path = Path(os.environ["OUT"])
    prev = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(prev + ",".join(done), encoding="utf-8")
    return result


def on_upload(event: Event, ctx: Context):
    text = ",".join(f"{record.action}:{record.key}" for record in event.records)
    Path(os.environ["OUT"]).write_text("storage:" + text, encoding="utf-8")


def on_orders(event: Event, ctx: Context):
    kind = event.records[0].attributes.get("event_type", "")
    Path(os.environ["OUT"]).write_text("topic:" + kind, encoding="utf-8")


def on_all(event: Event, ctx: Context):
    Path(os.environ["ALL"]).write_text(event.records[0].text(), encoding="utf-8")


def step(event: Event, ctx: Context):
    data = dict(event.data or {})
    data["seen"] = True
    return data
"""

CONFIG = """
service: demo
provider:
  name: onprem
  runtime: python3.12
  options:
    host: 127.0.0.1
    port: 8099
    data_dir: {data}
    services:
      storage: {{use: directory, path: {buckets}}}
  environment:
    OUT: "{out}"
    ALL: "{all_path}"
functions:
  hello:
    handler: app.handlers.hello
    events: [{{http: GET /hello}}]
  parent:
    handler: app.handlers.parent
  child:
    handler: app.handlers.child
  tick:
    handler: app.handlers.tick
    events: [{{schedule: 1 minutes}}]
  worker:
    handler: app.handlers.worker
    events:
      - queue: {{name: jobs, batch_size: 10, max_receive: 2, dead_letter: jobs-dlq}}
  on-upload:
    handler: app.handlers.on_upload
    events:
      - storage: {{bucket: uploads, prefix: in/, suffix: .csv, events: [created, deleted]}}
  on-orders:
    handler: app.handlers.on_orders
    events:
      - topic: {{name: orders, filter: {{event_type: [created]}}}}
  on-all:
    handler: app.handlers.on_all
    events: [{{topic: orders}}]
  step:
    handler: app.handlers.step
workflows:
  ping:
    start_at: Go
    states:
      Go: {{type: task, function: step, end: true}}
"""


def _project(make_project, tmp_path: Path):
    data = tmp_path / "data"
    buckets = tmp_path / "buckets"
    out = tmp_path / "out.txt"
    all_path = tmp_path / "all.txt"
    text = CONFIG.format(
        data=data.as_posix(),
        buckets=buckets.as_posix(),
        out=out.as_posix(),
        all_path=all_path.as_posix(),
    )
    project = make_project(text, files={"app/handlers.py": HANDLERS})
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    return host, out, all_path


def _server(host: Host):
    httpd = host.make_server(0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _json(method: str, url: str, body=None, token=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method=method)
    if data is not None:
        req.add_header("content-type", "application/json")
    if token:
        req.add_header("x-pskit-token", token)
    with urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_http_invoke_schedule_queue_storage_topic_workflow(make_project, tmp_path):
    host, out, all_path = _project(make_project, tmp_path)
    httpd, base = _server(host)
    try:
        status, health = _json("GET", base + "/__pskit/health")
        assert status == 200 and health["ok"] is True
        assert health["services"]["storage"]["use"] == "directory"
        assert health["services"]["queue"]["use"] == "builtin"

        status, hello = _json("GET", base + "/hello?name=Ada")
        assert status == 200 and hello == {"provider": "onprem", "name": "Ada"}
        assert host.invoke("parent", __import__("py_serverless_kit").Event(type="invoke")) == {"n": 3}

        host.rewind_schedules(120)
        host.pump_schedules(__import__("time").time())
        assert out.read_text(encoding="utf-8").startswith("schedule:")

        status, queued = _json("POST", base + "/__pskit/queues/jobs", ["ok", "fail"])
        assert status == 202 and len(queued["queued"]) == 2
        host.pump_queues(__import__("time").time())
        assert "ok" in out.read_text(encoding="utf-8")
        assert host.broker.queue_depth("jobs") == 1
        host.pump_queues(__import__("time").time())
        assert host.broker.queue_depth("jobs") == 0
        assert host.broker.queue_depth("jobs-dlq") == 1

        raw = Request(base + "/__pskit/storage/uploads/in/a.csv", data=b"h,v\n", method="PUT")
        with urlopen(raw, timeout=5) as resp:
            assert resp.status == 201
        assert "storage:created:in/a.csv" in out.read_text(encoding="utf-8")
        note = Request(base + "/__pskit/storage/uploads/note.txt", data=b"x", method="PUT")
        with urlopen(note, timeout=5) as resp:
            assert resp.status == 201
        assert "note.txt" not in out.read_text(encoding="utf-8")

        status, published = _json(
            "POST",
            base + "/__pskit/topics/orders",
            {"message": {"id": 1}, "attributes": {"event_type": "created"}},
        )
        assert status == 202 and published["published"]
        assert out.read_text(encoding="utf-8").endswith("topic:created") or "topic:created" in out.read_text(
            encoding="utf-8"
        )
        assert all_path.read_text(encoding="utf-8")

        status, workflow = _json("POST", base + "/__pskit/workflows/ping?wait=true", {"order": 1})
        assert status == 200
        assert workflow["status"] == "SUCCEEDED" and workflow["execution_id"]
        assert workflow["output"]["seen"] is True
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_admin_token_gates_the_broker(make_project, tmp_path):
    host, _out, _all = _project(make_project, tmp_path)
    host.spec["admin_token"] = "secret"
    httpd, base = _server(host)
    try:
        try:
            _json("POST", base + "/__pskit/queues/jobs", {"a": 1})
            raised = False
        except HTTPError as exc:
            raised = True
            assert exc.code == 401
        assert raised
        status, _body = _json("POST", base + "/__pskit/queues/jobs", {"a": 1}, token="secret")
        assert status == 202
        status, hello = _json("GET", base + "/hello")
        assert status == 200 and hello["provider"] == "onprem"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_health_url_uses_loopback_when_the_process_binds_every_interface():
    assert health_url({"host": "0.0.0.0", "port": 9090}) == "http://127.0.0.1:9090/__pskit/health"
    assert health_url({"host": "::", "port": 8080}) == "http://127.0.0.1:8080/__pskit/health"
    assert health_url({"host": "10.0.1.12", "port": 9090}) == "http://10.0.1.12:9090/__pskit/health"
    assert health_url({"host": "::1", "port": 9090}) == "http://[::1]:9090/__pskit/health"


SLOW_HANDLERS = HANDLERS + """

def slow(event: Event, ctx: Context):
    import time
    print("slow step", event.data)
    ctx.logger.info("slow working", extra={"n": 1})
    time.sleep(float((event.data or {}).get("sleep", 0)))
    return dict(event.data or {}, slow=True)


def boom(event: Event, ctx: Context):
    raise RuntimeError("kaboom")
"""

WORKFLOW_CONFIG = (
    CONFIG.replace(
        "  step:\n    handler: app.handlers.step\n",
        "  step:\n    handler: app.handlers.step\n  slow:\n    handler: app.handlers.slow\n"
        "  boom:\n    handler: app.handlers.boom\n",
    )
    + """
  slowflow:
    start_at: Slow
    states:
      Slow: {{type: task, function: slow, next: Pause}}
      Pause: {{type: wait, seconds: 30, next: Done}}
      Done: {{type: pass, end: true}}
  failing:
    start_at: Boom
    states:
      Boom: {{type: task, function: boom, end: true}}
"""
)


def _workflow_host(make_project, tmp_path: Path):
    text = WORKFLOW_CONFIG.format(
        data=(tmp_path / "data").as_posix(),
        buckets=(tmp_path / "buckets").as_posix(),
        out=(tmp_path / "out.txt").as_posix(),
        all_path=(tmp_path / "all.txt").as_posix(),
    )
    project = make_project(text, files={"app/handlers.py": SLOW_HANDLERS})
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    return host, root


def _wait_for(fn, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


def _execution(base, execution_id):
    return _json("GET", base + f"/__pskit/executions/{execution_id}")[1]


def _finished(base, execution_id):
    return _wait_for(lambda: (lambda r: r if r["status"] != "RUNNING" else None)(_execution(base, execution_id)))


def _expect_http_error(code, method, url, body=None):
    try:
        _json(method, url, body)
    except HTTPError as exc:
        assert exc.code == code
        return
    raise AssertionError(f"expected HTTP {code}")


def test_workflow_start_is_async_and_tracked(make_project, tmp_path):
    host, _root = _workflow_host(make_project, tmp_path)
    httpd, base = _server(host)
    try:
        status, started = _json("POST", base + "/__pskit/workflows/ping", {"order": 7})
        assert status == 202 and started["status"] == "RUNNING"
        execution_id = started["execution_id"]
        assert started["status_url"] == f"/__pskit/executions/{execution_id}"
        record = _finished(base, execution_id)
        assert record["status"] == "SUCCEEDED" and record["output"] == {"order": 7, "seen": True}
        assert record["input"] == {"order": 7}
        assert [h["event"] for h in record["history"]] == ["enter", "exit"]

        # The orchestrator's own user route is tracked the same way.
        status, started2 = _json("POST", base + "/workflows/ping", {"order": 8})
        assert status == 202
        assert _finished(base, started2["execution_id"])["status"] == "SUCCEEDED"

        _status, failed = _json("POST", base + "/__pskit/workflows/failing", {})
        record = _finished(base, failed["execution_id"])
        assert record["status"] == "FAILED" and record["error"] == "RuntimeError" and "kaboom" in record["cause"]

        status, listing = _json("GET", base + "/__pskit/executions?workflow=ping&limit=1")
        assert status == 200 and listing["total"] == 2 and len(listing["items"]) == 1
        assert listing["items"][0]["execution_id"] == started2["execution_id"]  # newest first
        _status, page2 = _json("GET", base + "/__pskit/executions?workflow=ping&limit=1&offset=1")
        assert page2["items"][0]["execution_id"] == execution_id
        _status, only_failed = _json("GET", base + "/__pskit/executions?status=failed")
        assert [i["workflow"] for i in only_failed["items"]] == ["failing"]
        _expect_http_error(404, "GET", base + "/__pskit/executions/not-an-id")
        _expect_http_error(404, "POST", base + "/__pskit/workflows/nope", {})
        _expect_http_error(400, "GET", base + "/__pskit/executions?limit=x")
    finally:
        httpd.shutdown()
        httpd.server_close()
        host.executor.shutdown()


def test_workflow_cancel_and_restart_recovery(make_project, tmp_path):
    host, root = _workflow_host(make_project, tmp_path)
    httpd, base = _server(host)
    try:
        _status, started = _json("POST", base + "/__pskit/workflows/slowflow", {"sleep": 0})
        execution_id = started["execution_id"]
        _wait_for(lambda: _execution(base, execution_id)["current_state"] == "Pause")
        status, record = _json("POST", base + f"/__pskit/executions/{execution_id}/cancel")
        assert status == 200 and record["cancel_requested"] is True
        assert _finished(base, execution_id)["status"] == "CANCELLED"

        _status, other = _json("POST", base + "/__pskit/workflows/slowflow", {"sleep": 0})
        _wait_for(lambda: _execution(base, other["execution_id"])["current_state"] == "Pause")
    finally:
        httpd.shutdown()
        httpd.server_close()
    host.executor.shutdown()
    path = tmp_path / "data" / "executions" / f"{other['execution_id']}.json"
    _wait_for(lambda: json.loads(path.read_text("utf-8"))["status"] != "RUNNING")
    # Simulate a crash: the record on disk still says RUNNING.
    stale = json.loads(path.read_text("utf-8"))
    stale["status"] = "RUNNING"
    path.write_text(json.dumps(stale), "utf-8")
    again = Host(root)
    again.open()
    try:
        record = again.executor.get(other["execution_id"])
        assert record["status"] == "ABORTED" and record["cause"] == "host restarted"
        assert any("marked ABORTED" in note for note in again.notes)
    finally:
        again.executor.shutdown()
        again.logs.close()


def test_logs_and_stats(make_project, tmp_path):
    host, root = _workflow_host(make_project, tmp_path)
    httpd, base = _server(host)
    try:
        _json("GET", base + "/hello?name=Ada")
        _json("POST", base + "/__pskit/workflows/ping?wait=1", {"x": 1})
        _expect_http_error(500, "POST", base + "/__pskit/invoke/boom", {})

        status, logs = _json("GET", base + "/__pskit/logs")
        assert status == 200
        invocations = [e for e in logs["entries"] if e["source"] == "invocation"]
        assert any(e["function"] == "hello" and e["fields"]["status"] == 200 for e in invocations)
        assert any(e["function"] == "step" for e in invocations)
        boom = [e for e in invocations if e["function"] == "boom"]
        assert boom and boom[0]["level"] == "ERROR" and "kaboom" in boom[0]["message"]

        last = logs["next"]
        _status, errors = _json("GET", base + "/__pskit/logs?level=error")
        assert errors["entries"] and all(e["level"] in ("ERROR", "CRITICAL") for e in errors["entries"])
        _status, only_hello = _json("GET", base + "/__pskit/logs?function=hello&source=invocation")
        assert {e["function"] for e in only_hello["entries"]} == {"hello"}
        _status, tail = _json("GET", base + f"/__pskit/logs?since={last}")
        assert tail["entries"] == [] and tail["next"] == last
        _json("GET", base + "/hello")
        _status, tail = _json("GET", base + f"/__pskit/logs?since={last}&source=invocation")
        assert [e["function"] for e in tail["entries"]] == ["hello"] and tail["next"] > last
        first = tail["entries"][0]["seq"]
        _status, older = _json("GET", base + f"/__pskit/logs?before={first}&limit=2")
        assert len(older["entries"]) == 2 and older["entries"][-1]["seq"] < first
        _expect_http_error(400, "GET", base + "/__pskit/logs?limit=abc")

        _status, stats = _json("GET", base + "/__pskit/stats")
        assert stats["functions"]["hello"]["invocations"] == 2
        assert stats["functions"]["boom"]["errors"] == 1 and "kaboom" in stats["functions"]["boom"]["last_error"]
        assert stats["functions"]["tick"]["invocations"] == 0
        assert stats["queues"] == {"jobs": 0, "jobs-dlq": 0}
    finally:
        httpd.shutdown()
        httpd.server_close()
        host.executor.shutdown()
        host.logs.close()
    # Entries survive a restart (JSON-lines file) and seq keeps increasing.
    again = Host(root)
    try:
        assert again.logs.last_seq >= last
        assert again.logs.query(function="hello")["entries"]
    finally:
        again.logs.close()


def test_captured_print_and_logging_are_tagged(make_project, tmp_path):
    from py_serverless_kit import Event
    from py_serverless_kit.runtime import hostlog

    host, _root = _workflow_host(make_project, tmp_path)
    hostlog.install(host.logs, capture_streams=True)
    try:
        host.invoke("slow", Event(type="invoke", data={"sleep": 0}))
    finally:
        hostlog.uninstall()
        host.executor.shutdown()
        host.logs.close()
    entries = host.logs.query(function="slow")["entries"]
    printed = [e for e in entries if e["source"] == "stdout"]
    logged = [e for e in entries if e["source"] == "function" and e["message"] == "slow working"]
    assert printed and printed[0]["message"].startswith("slow step") and printed[0]["request_id"]
    assert logged and logged[0]["fields"]["n"] == 1


def test_log_streams_and_clear(make_project, tmp_path):
    host, root = _workflow_host(make_project, tmp_path)
    httpd, base = _server(host)
    try:
        _json("GET", base + "/hello")
        _expect_http_error(500, "POST", base + "/__pskit/invoke/boom", {})
        host.logs.append("WARNING", "host", "host note")
        status, streams = _json("GET", base + "/__pskit/logs/streams")
        assert status == 200
        by_fn = {item["function"]: item for item in streams["items"]}
        assert {"hello", "boom", None} <= set(by_fn) and by_fn["hello"]["count"] >= 1
        _expect_http_error(405, "POST", base + "/__pskit/logs/streams", {})

        status, cleared = _json("DELETE", base + "/__pskit/logs?function=hello")
        assert status == 200 and cleared["deleted"] >= 1
        _status, left = _json("GET", base + "/__pskit/logs")
        assert left["entries"] and all(e["function"] != "hello" for e in left["entries"])
        _status, cleared = _json("DELETE", base + "/__pskit/logs?function=__host__")
        _status, left = _json("GET", base + "/__pskit/logs")
        assert all(e["function"] for e in left["entries"])
        _json("DELETE", base + "/__pskit/logs")
        _status, left = _json("GET", base + "/__pskit/logs")
        assert left["entries"] == []
    finally:
        httpd.shutdown()
        httpd.server_close()
        host.executor.shutdown()
        host.logs.close()
    # The JSON-lines file was rewritten too: nothing comes back after a restart.
    again = Host(root)
    try:
        assert not again.logs.query(function="hello")["entries"]
    finally:
        again.logs.close()


def test_a_host_that_crashes_at_start_fails_fast_and_shows_its_log(tmp_path):
    import subprocess
    import sys

    from py_serverless_kit.runtime import onprem_host

    log = tmp_path / "host.log"
    log.write_bytes(b"old run\n")
    proc = subprocess.Popen([sys.executable, "-c", "import sys; print('PermissionError: /home/x'); sys.exit(1)"],
                            stdout=open(log, "ab"), stderr=subprocess.STDOUT)  # noqa: SIM115
    started = time.time()
    assert onprem_host._wait_healthy("http://127.0.0.1:9/__pskit/health", 30, proc) is False
    assert time.time() - started < 15  # not the full 30 s
    tail = onprem_host._log_tail(log, len(b"old run\n"))
    assert "PermissionError: /home/x" in tail and "old run" not in tail and tail.startswith("  | ")
