"""On-prem resources end to end: drivers bound from `resources:`, env files, and a queue on another host."""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.runtime.drivers.pskit_host import PskitHostQueue
from py_serverless_kit.runtime.onprem_host import Host, activate_layout, load_env_file, parse_env_text

from .test_drivers import redis_server  # noqa: F401 - pytest fixture

HANDLERS = """
import os
from pathlib import Path

from py_serverless_kit import BatchResult, Event, Context, resource
from py_serverless_kit.runtime.onprem_host import submit_queue


def publish(event: Event, ctx: Context):
    return submit_queue(resource("outbox").native_name, {"n": event.data})


def worker(event: Event, ctx: Context):
    result = BatchResult()
    out = Path(os.environ["OUT"])
    for record in event.records:
        if "fail" in record.text():
            result.fail(record)
        else:
            out.write_text((out.read_text() if out.exists() else "") + record.text() + ";")
    return result
"""

CONFIG = """
service: res
provider:
  name: onprem
  runtime: python3.12
  options:
    host: 127.0.0.1
    port: 8097
    data_dir: {data}
    env_file: secrets.env
  environment:
    OUT: "{out}"
resources:
  outbox:                        # a Redis queue nothing consumes: only published to
    type: queue
    external: true
    options: {{driver: redis, url_env: OUTBOX_URL, key: outbox}}
  dlq:                           # dead-letter queue given by resource key, also Redis
    type: queue
    external: true
    name: failed-jobs
    options: {{driver: redis, url_env: OUTBOX_URL, key: failed}}
  archive:                       # managed bucket no event uses
    type: storage
  remote-jobs:                   # the built-in queue of another on-prem host
    type: queue
    external: true
    options: {{driver: pskit_host, endpoint: "{remote}", queue: jobs, token_env: REMOTE_TOKEN}}
functions:
  publish:
    handler: app.handlers.publish
  worker:
    handler: app.handlers.worker
    events:
      - queue: {{resource: remote-jobs, batch_size: 5, max_receive: 2, dead_letter: dlq}}
"""


def _serve(host: Host):
    httpd = host.make_server(0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _post(url: str, body, token: str = ""):
    req = Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("x-pskit-token", token)
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _remote_host(template: Path, dest: Path, data: Path) -> Host:
    """A second host (B) that owns the built-in queue `jobs` and requires an admin token."""
    shutil.copytree(template, dest)
    spec = json.loads((dest / "pskit_host.json").read_text("utf-8"))
    spec.update(
        {
            "service": "producer",
            "data_dir": str(data),
            "services": {"queue": {"use": "builtin", "path": str(data / "queues")}},
            "admin_token": "t0ken",
            "functions": {},
            "resources": {"jobs": {"type": "queue", "external": False, "name": "jobs", "functions": []}},
        }
    )
    (dest / "pskit_host.json").write_text(json.dumps(spec), "utf-8")
    (dest / "host.env").unlink(missing_ok=True)
    host = Host(dest)
    host.open()
    return host


def test_env_file_parsing(tmp_path, monkeypatch):
    text = "# c\nexport A=1\nB='two words'\nC=\"x\"\nD=v # note\nbad line\n1X=no\n"
    assert parse_env_text(text) == {"A": "1", "B": "two words", "C": "x", "D": "v"}
    monkeypatch.setenv("A", "kept")
    monkeypatch.delenv("B", raising=False)
    path = tmp_path / "host.env"
    path.write_text(text, "utf-8")
    added = load_env_file(path)
    assert "A" not in added and "B" in added
    import os

    assert os.environ["A"] == "kept" and os.environ["B"] == "two words"
    monkeypatch.delenv("B", raising=False)
    monkeypatch.delenv("C", raising=False)
    monkeypatch.delenv("D", raising=False)
    assert load_env_file(tmp_path / "missing.env") == []


def test_resource_drivers_env_file_and_remote_host_queue(make_project, tmp_path, redis_server, monkeypatch):  # noqa: F811
    redis_url, redis_state = redis_server
    for var in ("OUTBOX_URL", "REMOTE_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    # Host B first, so host A knows its URL.
    out = tmp_path / "out.txt"
    placeholder = "http://127.0.0.1:9"
    text = CONFIG.format(data=(tmp_path / "data").as_posix(), out=out.as_posix(), remote=placeholder)
    project = make_project(text, files={"app/handlers.py": HANDLERS})
    (project.root / "secrets.env").write_text(f"OUTBOX_URL={redis_url}\nREMOTE_TOKEN=t0ken\n", "utf-8")
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    assert (root / "host.env").read_text("utf-8").startswith("OUTBOX_URL=")
    spec = json.loads((root / "pskit_host.json").read_text("utf-8"))
    assert "env_file_sha256" in spec and redis_url not in json.dumps(spec)  # the secret stays out of the spec
    worker_ev = spec["functions"]["worker"]["events"][0]
    assert worker_ev["dead_letter"] == "failed-jobs"  # resource key -> native name

    remote = _remote_host(root, tmp_path / "hostb", tmp_path / "datab")
    httpd_b, base_b = _serve(remote)
    a = None
    try:
        spec["resources"]["remote-jobs"]["driver"]["endpoint"] = base_b
        for ev in spec["functions"]["worker"]["events"]:
            ev["driver"]["endpoint"] = base_b
        (root / "pskit_host.json").write_text(json.dumps(spec), "utf-8")
        a = Host(root)  # loads host.env, binds drivers from resources
        a.open()

        # Publish-only Redis queue: the handler's submit_queue goes to Redis, not a local folder.
        from py_serverless_kit import Event

        a.invoke("publish", Event(type="invoke", data=7))
        assert len(redis_state.lists.get(b"outbox", [])) == 1
        assert not (tmp_path / "data" / "queues" / "outbox").exists()
        # A managed bucket nobody listens to exists from the start.
        assert (tmp_path / "data" / "buckets" / "archive").is_dir()

        # Messages published on host B are consumed by host A's worker.
        _post(f"{base_b}/__pskit/queues/jobs", {"messages": ["ok-1", "fail-1"]}, token="t0ken")
        a.pump_queues(time.time())
        assert out.read_text() == "ok-1;"
        assert remote.broker.queue_depth("jobs") == 1  # the failed one is visible again on B
        a.pump_queues(time.time())  # second failure reaches max_receive -> Redis DLQ
        assert remote.broker.queue_depth("jobs") == 0
        assert len(redis_state.lists.get(b"failed", [])) == 1

        listing = {item["key"]: item for item in a.resources()["items"]}
        assert listing["remote-jobs"]["driver"] == "pskit_host" and listing["remote-jobs"]["consumers"] == ["worker"]
        assert listing["outbox"]["depth"] == 1 and listing["archive"]["driver"] == "builtin"
    finally:
        httpd_b.shutdown()
        httpd_b.server_close()
        for host in (a, remote):
            if host is not None and host.executor is not None:
                host.executor.shutdown()
            if host is not None:
                host.logs.close()


def test_lease_api_rejects_bad_receipts_and_needs_the_token(make_project, tmp_path):
    project = make_project(
        f"""
        service: lease
        provider:
          name: onprem
          options: {{data_dir: "{(tmp_path / 'd').as_posix()}", admin_token: abc}}
        resources:
          jobs: {{type: queue}}
        functions:
          noop: {{handler: app.handlers.hello}}
        """
    )
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    httpd, base = _serve(host)
    try:
        q = PskitHostQueue(base, "jobs", token="abc")
        q.submit("hello", {"k": "v"})
        assert q.depth() == 1
        claimed = q.claim(10, 30, time.time())
        assert [m["body"] for m in claimed] == ["hello"] and claimed[0]["receives"] == 1
        assert q.claim(10, 30, time.time()) == []  # leased: hidden from other consumers
        q.settle(claimed, set(), 3, None, time.time())
        assert q.depth() == 0
        with pytest.raises(Exception, match="400"):
            _post(f"{base}/__pskit/queues/jobs/ack", {"receipts": ["../../pskit_host.json"]}, token="abc")
        with pytest.raises(Exception, match="401"):
            PskitHostQueue(base, "jobs").depth()
    finally:
        httpd.shutdown()
        httpd.server_close()
        host.executor.shutdown()
        host.logs.close()


def test_check_purge_and_node_publish_helpers(make_project, tmp_path):
    import socket
    import subprocess

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    db_port = listener.getsockname()[1]
    project = make_project(
        f"""
        service: chk
        provider:
          name: onprem
          options: {{data_dir: "{(tmp_path / 'd').as_posix()}"}}
        resources:
          jobs: {{type: queue}}
          files: {{type: storage}}
          db:
            type: database
            external: true
            connection: {{host: 127.0.0.1, port: {db_port}}}
          gone:
            type: cache
            external: true
            connection: {{host: 127.0.0.1, port: 9}}
        functions:
          noop: {{handler: app.handlers.hello}}
        """
    )
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    httpd, base = _serve(host)
    try:
        host.broker.submit_queue("jobs", "a")
        host.broker.put_object("files", "x/y.txt", b"1")
        assert "1 message(s)" in host.check_resource("jobs")["detail"]
        assert "1 object(s)" in host.check_resource("files")["detail"]
        assert host.check_resource("db")["ok"] is True
        assert host.check_resource("gone")["ok"] is False
        with pytest.raises(Exception, match="404"):
            _post(f"{base}/__pskit/resources/nope/check", {})
        out = _post(f"{base}/__pskit/resources/db/check", {})
        assert out["ok"] and out["checked_from"] == "host"

        req = Request(f"{base}/__pskit/resources/jobs/data", method="DELETE")
        with urlopen(req, timeout=5) as resp:
            assert json.loads(resp.read())["deleted"] == 1
        assert host.broker.queue_depth("jobs") == 0
        with pytest.raises(Exception, match="400"):
            urlopen(Request(f"{base}/__pskit/resources/db/data", method="DELETE"), timeout=5)

        if shutil.which("node") is None:
            pytest.skip("node is not installed")
        runtime_js = Path(__file__).resolve().parents[2] / "src" / "py_serverless_kit" / "runtime_js"
        script = (
            f"const p = require({json.dumps(str(runtime_js / 'index.js'))});\n"
            "(async () => {\n"
            "  const id = await p.submitQueue('jobs', {n: 1}, {k: 'v'});\n"
            "  await p.putObject('files', 'from/node.txt', 'hi');\n"
            "  const gone = await p.deleteObject('files', 'x/y.txt');\n"
            "  console.log(JSON.stringify({id, gone}));\n"
            "})().catch((e) => { console.error(e.message); process.exit(1); });\n"
        )
        env = dict(__import__("os").environ, PSKIT_HOST_URL=base)
        proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, env=env, timeout=60)
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["id"] and result["gone"] is True
        assert host.broker.queue_depth("jobs") == 1
        assert host.broker.get_object("files", "from/node.txt") == b"hi"
    finally:
        listener.close()
        httpd.shutdown()
        httpd.server_close()
        host.executor.shutdown()
        host.logs.close()


def test_browse_paginates_and_generated_host_scripts_run(make_project, tmp_path):
    import os
    import re
    import subprocess
    import sys

    from py_serverless_kit.core.onprem_clients import via_host

    project = make_project(
        f"""
        service: browse
        provider:
          name: onprem
          options: {{data_dir: "{(tmp_path / 'd').as_posix()}"}}
        resources:
          jobs: {{type: queue}}
          files: {{type: storage}}
          news: {{type: topic}}
        functions:
          noop: {{handler: app.handlers.hello}}
        """
    )
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    httpd, base = _serve(host)
    try:
        for i in range(7):
            host.broker.submit_queue("jobs", {"n": i})
        page = host.browse_resource("jobs", offset=5, limit=5)
        assert page["total"] == 7 and [json.loads(m["body"])["n"] for m in page["items"]] == [5, 6]
        host.broker.claim_queue({"name": "jobs", "batch_size": 1, "visibility_timeout": 60}, time.time())
        first = host.browse_resource("jobs", 0, 1)["items"][0]
        assert first["leased"] is True
        assert host.broker.delete_message("jobs", first["id"]) is True
        assert host.browse_resource("jobs")["total"] == 6

        host.broker.put_object("files", "in/a.txt", b"hello")
        host.broker.put_object("files", "in/b.bin", b"\xff\x00")
        host.broker.put_object("files", "out/c.txt", b"x" * 10)
        listed = host.browse_resource("files", 0, 10, prefix="in/")
        assert [i["key"] for i in listed["items"]] == ["in/a.txt", "in/b.bin"] and listed["total"] == 2
        assert host.read_object("files", "in/a.txt")["content"] == "hello"
        assert host.read_object("files", "in/b.bin")["encoding"] == "base64"
        host.broker.submit_topic("news", {"title": "hi"})
        assert host.browse_resource("news")["total"] == 1

        # The "use it from any program" scripts, run for real against this host.
        for kind, name in (("queue", "jobs"), ("storage", "files"), ("topic", "news")):
            snip = via_host(kind, name, name, base)
            env = dict(os.environ, PSKIT_HOST=base)
            proc = subprocess.run([sys.executable, "-c", snip["python"]], capture_output=True, text=True, env=env, timeout=60)
            assert proc.returncode == 0, (kind, proc.stderr)
            if shutil.which("node"):
                proc = subprocess.run(["node", "-e", snip["node"]], capture_output=True, text=True, env=env, timeout=60)
                assert proc.returncode == 0, (kind, proc.stderr)
        assert "processing" in subprocess.run(
            [sys.executable, "-c", via_host("queue", "jobs", "jobs", base)["python"]],
            capture_output=True, text=True, env=dict(os.environ, PSKIT_HOST=base), timeout=60,
        ).stdout
        assert re.search(r"\d+ waiting", subprocess.run(
            [sys.executable, "-c", via_host("queue", "jobs", "jobs", base)["python"]],
            capture_output=True, text=True, env=dict(os.environ, PSKIT_HOST=base), timeout=60,
        ).stdout)

        # The remote-host driver browses through the other host's peek endpoint.
        for i in range(3):
            host.broker.submit_queue("jobs", {"again": i})
        remote = PskitHostQueue(base, "jobs")
        items, total = remote.peek(0, 2)
        assert total == host.broker.queue_depth("jobs") and len(items) == 2
    finally:
        httpd.shutdown()
        httpd.server_close()
        host.executor.shutdown()
        host.logs.close()
