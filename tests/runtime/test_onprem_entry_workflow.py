"""On premises, running a workflow's first task function on its own starts the workflow."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

from py_serverless_kit import Event
from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.runtime.executions import Executor, MemoryExecutionStore, entry_function
from py_serverless_kit.runtime.onprem_host import Host, activate_layout

HANDLERS = """
import os
from pathlib import Path

from py_serverless_kit import BadRequest, Event


def _count(name):
    path = Path(os.environ["CALLS"])
    prev = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(prev + name + ",", encoding="utf-8")


def step01(event: Event, ctx):
    _count("step01")
    if event.http is not None:
        if event.http.query.get("fail"):
            raise BadRequest("bad input")
        return {"order": event.http.query.get("order"), "steps": ["step01"]}
    data = dict(event.data or {})
    return {"order": data.get("order"), "steps": ["step01"]}


def step02(event: Event, ctx):
    _count("step02")
    data = dict(event.data)
    data["steps"] = data["steps"] + ["step02"]
    return data


def step3(event: Event, ctx):
    _count("step3")
    data = dict(event.data)
    data["steps"] = data["steps"] + ["step3"]
    return data
"""

CONFIG = """
service: chain
provider:
  name: onprem
  runtime: python3.12
  options:
    host: 127.0.0.1
    port: 8098
    data_dir: {data}
  environment:
    CALLS: "{calls}"
functions:
  step01:
    handler: app.handlers.step01
    events: [{{http: GET /step01}}]
  step02:
    handler: app.handlers.step02
  step3:
    handler: app.handlers.step3
workflows:
  my-workflow:
    start_at: Call
    options: {options}
    states:
      Call: {{type: task, function: step01, next: Call3}}
      Call3: {{type: task, function: step02, next: Call2}}
      Call2: {{type: task, function: step3, end: true}}
"""


def _host(make_project, tmp_path: Path, options: str = "{{}}"):
    calls = tmp_path / "calls.txt"
    text = CONFIG.replace("{options}", options).format(data=(tmp_path / "data").as_posix(), calls=calls.as_posix())
    project = make_project(text, files={"app/handlers.py": HANDLERS})
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    httpd = host.make_server(0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return host, httpd, f"http://127.0.0.1:{httpd.server_address[1]}", calls


def _get(url: str):
    with urlopen(Request(url), timeout=5) as resp:
        return resp.status, dict(resp.headers), json.loads(resp.read().decode("utf-8"))


def _post(url: str, body):
    req = Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("content-type", "application/json")
    with urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _finished(base: str, execution_id: str):
    deadline = time.time() + 10
    while time.time() < deadline:
        record = _get(base + f"/__pskit/executions/{execution_id}")[2]
        if record["status"] != "RUNNING":
            return record
        time.sleep(0.05)
    raise AssertionError("workflow did not finish")


def _executions(base: str):
    return _get(base + "/__pskit/executions?workflow=my-workflow")[2]["items"]


def _close(host, httpd):
    httpd.shutdown()
    httpd.server_close()
    host.executor.shutdown()


def test_http_call_of_the_first_step_runs_the_workflow_once(make_project, tmp_path):
    host, httpd, base, calls = _host(make_project, tmp_path)
    try:
        status, headers, body = _get(base + "/step01?order=7")
        assert status == 200 and body == {"order": "7", "steps": ["step01"]}
        execution_id = headers["x-pskit-execution-id"]
        record = _finished(base, execution_id)
        assert record["status"] == "SUCCEEDED", record
        assert record["input"] == {"order": "7"}
        assert record["output"] == {"order": "7", "steps": ["step01", "step02", "step3"]}
        assert [h["state"] for h in record["history"] if h["event"] == "exit"] == ["Call", "Call3", "Call2"]
        assert calls.read_text(encoding="utf-8") == "step01,step02,step3,"  # step01 is not run again
    finally:
        _close(host, httpd)


def test_invoke_of_the_first_step_runs_the_workflow(make_project, tmp_path):
    host, httpd, base, calls = _host(make_project, tmp_path)
    try:
        assert host.invoke("step01", Event(type="invoke", data={"order": 3})) == {"order": 3, "steps": ["step01"]}
        (item,) = _executions(base)
        record = _finished(base, item["execution_id"])
        assert record["output"] == {"order": 3, "steps": ["step01", "step02", "step3"]}
        assert calls.read_text(encoding="utf-8") == "step01,step02,step3,"
    finally:
        _close(host, httpd)


def test_workflow_steps_and_explicit_starts_do_not_start_another_run(make_project, tmp_path):
    host, httpd, base, calls = _host(make_project, tmp_path)
    try:
        status, started = _post(base + "/__pskit/workflows/my-workflow", {"order": 1})
        assert status == 202
        assert _finished(base, started["execution_id"])["status"] == "SUCCEEDED"
        assert len(_executions(base)) == 1
        assert calls.read_text(encoding="utf-8") == "step01,step02,step3,"
        # Not the first state: a call of step02 on its own starts nothing.
        host.invoke("step02", Event(type="invoke", data={"steps": []}))
        assert len(_executions(base)) == 1
    finally:
        _close(host, httpd)


def test_a_failed_http_answer_starts_nothing(make_project, tmp_path):
    host, httpd, base, _calls = _host(make_project, tmp_path)
    try:
        req = Request(base + "/step01?fail=1")
        try:
            urlopen(req, timeout=5)
        except Exception as exc:  # noqa: BLE001
            assert getattr(exc, "code", None) == 400
        assert _executions(base) == []
    finally:
        _close(host, httpd)


def test_start_on_entry_false_turns_it_off(make_project, tmp_path):
    host, httpd, base, calls = _host(make_project, tmp_path, options="{{start_on_entry: false}}")
    try:
        status, headers, _body = _get(base + "/step01?order=1")
        assert status == 200 and "x-pskit-execution-id" not in headers
        assert _executions(base) == []
        assert calls.read_text(encoding="utf-8") == "step01,"
    finally:
        _close(host, httpd)


def test_another_groups_host_starts_the_run_with_the_entry_result(make_project, tmp_path):
    host, httpd, base, calls = _host(make_project, tmp_path)
    try:
        status, started = _post(
            base + "/__pskit/workflows/my-workflow?entry=true",
            {"input": {"order": 5}, "entry_result": {"order": 5, "steps": ["step01"]}},
        )
        assert status == 202
        record = _finished(base, started["execution_id"])
        assert record["input"] == {"order": 5}
        assert record["output"] == {"order": 5, "steps": ["step01", "step02", "step3"]}
        assert calls.read_text(encoding="utf-8") == "step02,step3,"
    finally:
        _close(host, httpd)


def test_executor_entry_result_replaces_only_the_first_call():
    definition = {
        "start_at": "A",
        "states": {
            "A": {"type": "task", "function": "f", "next": "B"},
            "B": {"type": "task", "function": "f", "end": True},
        },
    }
    assert entry_function(definition) == "f"
    assert entry_function({"start_at": "P", "states": {"P": {"type": "pass", "end": True}}}) is None
    called = []

    def runner(fn, data):
        called.append(data)
        return data + 1

    executor = Executor(MemoryExecutionStore(), {"w": {"definition": definition}}, runner)
    record = executor.start("w", 0, wait=True, entry_result=10)
    assert record["status"] == "SUCCEEDED" and record["output"] == 11
    assert called == [10]
    executor.shutdown()
