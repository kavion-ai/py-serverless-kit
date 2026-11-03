"""Cluster roles: a ``web`` replica serves HTTP and hands queues, admin calls, workflows and logs to ``main``."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.runtime.onprem_host import ForwardingBroker, Host, activate_layout

from .test_onprem_host import _json, _server, _wait_for

HANDLERS = """
from py_serverless_kit.runtime.onprem_host import put_object, submit_queue


def hello(event, ctx):
    ctx.logger.info("hello from a replica")
    return {"ok": True}


def send(event, ctx):
    submit_queue("jobs", {"order": 7}, {"kind": "test"})
    put_object("files", "a/b.txt", b"hi")
    return {"queued": True}


def work(event, ctx):
    return None


def step(event, ctx):
    return {"seen": event.data}
"""

CONFIG = """
service: shop
provider:
  name: onprem
  runtime: python3.12
  options: {{host: 127.0.0.1, port: 8099, data_dir: {data}}}
resources:
  jobs: {{type: queue}}
  files: {{type: storage}}
functions:
  hello: {{handler: app.handlers.hello, events: [{{http: {{path: /hello, method: get}}}}]}}
  send: {{handler: app.handlers.send, events: [{{http: {{path: /send, method: post}}}}]}}
  work: {{handler: app.handlers.work, events: [{{queue: jobs}}]}}
  step: {{handler: app.handlers.step}}
workflows:
  ping:
    start_at: Go
    states:
      Go: {{type: task, function: step, end: true}}
"""


@pytest.fixture
def pair(make_project, tmp_path: Path, monkeypatch):
    project = make_project(CONFIG.format(data=(tmp_path / "main-data").as_posix()),
                           files={"app/handlers.py": HANDLERS})
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    main_root = project.work_dir / "onprem_app"
    web_root = tmp_path / "web_app"
    shutil.copytree(main_root, web_root)
    spec = json.loads((web_root / "pskit_host.json").read_text("utf-8"))
    spec["data_dir"] = (tmp_path / "web-data").as_posix()  # each replica has its own disk
    (web_root / "pskit_host.json").write_text(json.dumps(spec), "utf-8")
    for root in (main_root, web_root):
        activate_layout(root)

    monkeypatch.setenv("PSKIT_HOST_ROLE", "main")
    main = Host(main_root)
    main.open()
    main_httpd, main_base = _server(main)
    monkeypatch.setenv("PSKIT_HOST_ROLE", "web")
    monkeypatch.setenv("PSKIT_MAIN_URL", main_base)
    monkeypatch.setenv("PSKIT_REPLICA", "node-b-1")
    web = Host(web_root)
    web.open()  # opened last: handlers in this process publish through the web replica's broker
    web_httpd, web_base = _server(web)
    try:
        yield main, main_base, web, web_base
    finally:
        for httpd in (web_httpd, main_httpd):
            httpd.shutdown()
            httpd.server_close()
        if main.executor is not None:
            main.executor.shutdown()


def test_web_replica_forwards_state_to_main(pair):
    main, _main_base, web, web_base = pair
    assert isinstance(web.broker, ForwardingBroker) and web.role == "web" and main.role == "main"
    status, health = _json("GET", web_base + "/__pskit/health")
    assert status == 200 and health["role"] == "web" and health["replica"] == "node-b-1"

    assert _json("GET", web_base + "/hello")[1] == {"ok": True}  # HTTP runs on the web replica
    assert _json("POST", web_base + "/send", {})[1] == {"queued": True}
    assert main.broker.queue_depth("jobs") == 1  # ... but the message is on the main replica
    assert main.broker.get_object("files", "a/b.txt") == b"hi"
    assert not (Path(web.spec["data_dir"]) / "queues" / "jobs" / "messages").is_dir() or not any(
        (Path(web.spec["data_dir"]) / "queues" / "jobs" / "messages").iterdir())
    assert web.broker.get_object("files", "a/b.txt") == b"hi"

    # Admin calls on a web replica are answered by main (same data whichever replica the balancer picks).
    assert _json("GET", web_base + "/__pskit/queues/jobs")[1] == {"queue": "jobs", "depth": 1}
    assert _json("POST", web_base + "/__pskit/queues/jobs", {"order": 8})[0] == 202
    assert main.broker.queue_depth("jobs") == 2

    # invoke() runs locally on the replica
    assert _json("POST", web_base + "/__pskit/invoke/step", {"x": 1})[1] == {"result": {"seen": {"x": 1}}}


def test_logs_and_counts_reach_main(pair):
    main, main_base, web, web_base = pair
    _json("GET", web_base + "/hello")
    _json("GET", web_base + "/hello")
    assert web.ship_logs() is True
    entries = _json("GET", main_base + "/__pskit/logs?function=hello&limit=50")[1]["entries"]
    replicas = {e["fields"].get("replica") for e in entries}
    calls = [e for e in entries if e["source"] == "invocation"]
    assert replicas == {"node-b-1"} and len(calls) == 2 and calls[0]["message"].startswith("GET /hello -> 200")
    assert main.stats()["functions"]["hello"]["invocations"] == 2  # counted where the stats are read
    # Logs read through the web replica come from main too.
    via_web = _json("GET", web_base + "/__pskit/logs?function=hello&limit=50")[1]["entries"]
    assert len(via_web) == len(entries)
    assert web.ship_logs() is True  # nothing new: nothing sent twice
    assert len(_json("GET", main_base + "/__pskit/logs?function=hello&limit=50")[1]["entries"]) == len(entries)
    # The web replica's own buffer is readable without going through main.
    status, local = _json("GET", web_base + "/__pskit/logs/local?function=hello&limit=50")
    assert status == 200 and local["role"] == "web" and local["replica"] == "node-b-1"
    assert len(local["entries"]) == len(entries)
    _json("POST", main_base + "/__pskit/invoke/step", {"x": 1})
    local_after = _json("GET", web_base + "/__pskit/logs/local?limit=50")[1]["entries"]
    assert all(entry.get("function") != "step" for entry in local_after)


def test_workflow_started_on_web_runs_on_main(pair):
    main, main_base, _web, web_base = pair
    status, started = _json("POST", web_base + "/workflows/ping", {"n": 1})
    assert status == 202 and started["status"] == "RUNNING"
    record = _wait_for(lambda: (lambda r: r if r["status"] != "RUNNING" else None)(
        _json("GET", main_base + f"/__pskit/executions/{started['execution_id']}")[1]))
    assert record["status"] == "SUCCEEDED"
    status, body = _json("POST", web_base + "/workflows/ping?wait=true", {"n": 2})
    assert status == 200 and body["status"] == "SUCCEEDED" and body["output"] == {"seen": {"n": 2}}


def test_web_role_needs_the_main_url(make_project, tmp_path, monkeypatch):
    project = make_project(CONFIG.format(data=(tmp_path / "d").as_posix()), files={"app/handlers.py": HANDLERS})
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    monkeypatch.setenv("PSKIT_HOST_ROLE", "web")
    monkeypatch.delenv("PSKIT_MAIN_URL", raising=False)
    with pytest.raises(ValueError, match="PSKIT_MAIN_URL"):
        Host(root)
    monkeypatch.setenv("PSKIT_HOST_ROLE", "leader")
    with pytest.raises(ValueError, match="PSKIT_HOST_ROLE"):
        Host(root)


def test_forwarding_retries_only_while_main_is_unreachable(monkeypatch):
    from urllib.error import URLError

    import py_serverless_kit.runtime.onprem_host as oh

    calls = []

    def fake(url, token, method, path, body=None, headers=None, timeout=30.0):
        calls.append(path)
        if len(calls) < 3:
            raise URLError(ConnectionRefusedError("refused"))
        return 202, {}, b'{"queued": ["m1"]}'

    monkeypatch.setattr(oh, "main_request", fake)
    monkeypatch.setattr(oh.time, "sleep", lambda _s: None)
    broker = oh.ForwardingBroker({"data_dir": "unused", "services": {}}, "http://main:8080", "")
    assert broker.submit_queue("jobs", {"a": 1}) == "m1" and len(calls) == 3

    calls.clear()

    def timeout(url, token, method, path, body=None, headers=None, timeout=30.0):
        calls.append(path)
        raise URLError(TimeoutError("timed out"))  # it may have arrived: never sent twice

    monkeypatch.setattr(oh, "main_request", timeout)
    with pytest.raises(URLError):
        broker.submit_queue("jobs", {"a": 1})
    assert len(calls) == 1


def test_requests_feed_names_the_replica_and_server(pair):
    main, main_base, web, web_base = pair
    main.node, web.node = "node-a", "node-b"
    _json("GET", web_base + "/hello")
    assert web.ship_logs()
    _json("POST", main_base + "/__pskit/invoke/step", {"x": 1})  # runs on main
    status, page = _json("GET", web_base + "/__pskit/requests")  # a web replica hands it to main
    assert status == 200 and page["role"] == "main"
    hello = next(r for r in page["items"] if r.get("path") == "/hello")
    assert hello["replica"] == "node-b-1" and hello["node"] == "node-b" and hello["status"] == 200
    assert hello["method"] == "GET" and hello["function"] == "hello"
    step = next(r for r in page["items"] if r["function"] == "step")
    assert step["node"] == "node-a" and step["replica"] == main.replica
    later = _json("GET", main_base + f"/__pskit/requests?since={page['next']}")[1]
    assert later["items"] == []  # polling with `next` returns only new requests
