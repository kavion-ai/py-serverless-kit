"""PskitClient (Python and Node.js) against a live in-process on-prem host."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from py_serverless_kit.client import PskitClient, PskitClientError
from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.runtime.onprem_host import Host, activate_layout

HANDLERS = """
def hello(event, ctx):
    return {"echo": event.data}
"""


@pytest.fixture
def live_host(make_project, tmp_path):
    project = make_project(
        f"""
        service: cli
        provider:
          name: onprem
          options: {{data_dir: "{(tmp_path / 'd').as_posix()}", admin_token: s3cret}}
        resources:
          jobs: {{type: queue, name: order-jobs}}
          files: {{type: storage}}
          news: {{type: topic}}
        functions:
          hello: {{handler: app.handlers.hello}}
        """,
        files={"app/handlers.py": HANDLERS},
    )
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    httpd = host.make_server(0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield host, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    host.executor.shutdown()
    host.logs.close()


def test_python_client_end_to_end(live_host):
    host, base = live_host
    client = PskitClient(base, token="s3cret")
    assert client.health()["ok"] is True
    assert {r["key"] for r in client.resources()} == {"jobs", "files", "news"}

    jobs = client.queue("jobs")                      # resource key -> native name order-jobs
    assert jobs.name == "order-jobs"
    ids = [jobs.send({"n": i}, attributes={"k": "v"}) for i in range(3)] + jobs.send_batch([{"n": 3}, {"n": 4}])
    assert len(ids) == 5 and jobs.depth() == 5
    page = jobs.peek(offset=0, limit=2)
    assert page.total == 5 and page.has_more and json.loads(page.items[0]["body"]) == {"n": 0}
    assert client.queue("order-jobs").peek(limit=10).total == 5   # by native name too
    leased = jobs.receive(batch=2, visibility=30)
    assert [m.json()["n"] for m in leased] == [0, 1]
    leased[0].ack()
    leased[1].nack()
    assert jobs.depth() == 4

    files = client.bucket("files")
    files.put("in/a.txt", "hello")
    files.put("in/b.bin", b"\x00\xff")
    files.put("out/c.txt", "x")
    assert files.get("in/a.txt") == b"hello"
    listed = files.list(prefix="in/", limit=1)
    assert listed.total == 2 and listed.has_more
    assert list(files.keys(prefix="in/", page_size=1)) == ["in/a.txt", "in/b.bin"]
    assert files.delete("in/a.txt") is True and files.delete("in/a.txt") is False
    with pytest.raises(PskitClientError, match="404"):
        files.get("missing.txt")

    client.topic("news").publish({"t": 1}, attributes={"type": "x"})
    assert client.topic("news").peek().total in (0, 1)   # delivered at once when nobody subscribes
    assert client.invoke("hello", {"a": 1}) == {"echo": {"a": 1}}
    assert client.check("jobs")["ok"] is True


def test_python_client_errors_are_fast_and_clear(live_host):
    _host, base = live_host
    with pytest.raises(PskitClientError, match="admin_token") as exc:
        PskitClient(base, token="").resources()
    assert exc.value.status == 401
    started = time.monotonic()
    with pytest.raises(PskitClientError, match="not reachable"):
        PskitClient("http://127.0.0.1:9", timeout=2).health()
    assert time.monotonic() - started < 5
    with pytest.raises(PskitClientError, match="no host"):
        PskitClient(None)


def test_node_client_end_to_end(live_host):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    _host, base = live_host
    runtime_js = Path(__file__).resolve().parents[2] / "src" / "py_serverless_kit" / "runtime_js"
    script = f"""
const {{ PskitClient, PskitClientError }} = require({json.dumps(str(runtime_js / "index.js"))});
(async () => {{
  const client = new PskitClient(process.env.PSKIT_HOST);
  const jobs = client.queue("jobs");
  await jobs.send({{ n: 1 }}, {{ k: "v" }});
  await jobs.sendBatch([{{ n: 2 }}, {{ n: 3 }}]);
  const page = await jobs.peek({{ limit: 2 }});
  const leased = await jobs.receive({{ batch: 1 }});
  await leased[0].ack();
  const files = client.bucket("files");
  await files.put("in/n.txt", "node");
  const keys = [];
  for await (const k of files.keys({{ prefix: "in/" }})) keys.push(k);
  await client.topic("news").publish({{ t: 1 }});
  const echo = await client.invoke("hello", {{ a: 1 }});
  let unauthorized = 0;
  try {{ await new PskitClient(process.env.PSKIT_HOST, {{ token: "" }}).resources(); }} catch (e) {{ unauthorized = e.status; }}
  let unreachable = "";
  try {{ await new PskitClient("http://127.0.0.1:9", {{ timeout: 2000 }}).health(); }} catch (e) {{ unreachable = e.message; }}
  console.log(JSON.stringify({{ total: page.total, first: leased[0].json(), depth: await jobs.depth(),
    got: (await files.get("in/n.txt")).toString(), keys, echo, unauthorized, unreachable }}));
}})().catch((e) => {{ console.error(e.stack); process.exit(1); }});
"""
    env = dict(os.environ, PSKIT_HOST=base, PSKIT_ADMIN_TOKEN="s3cret")
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["total"] == 3 and out["first"] == {"n": 1} and out["depth"] == 2
    assert out["got"] == "node" and out["keys"] == ["in/n.txt"] and out["echo"] == {"echo": {"a": 1}}
    assert out["unauthorized"] == 401 and "not reachable" in out["unreachable"]


def test_client_guide_and_tunnels(make_project, tmp_path):
    from py_serverless_kit.core.client_guide import client_guide
    from py_serverless_kit.core.onprem_services import local_env, tunnel_argv

    project = make_project(
        "service: cg\nprovider:\n  name: onprem\nresources:\n  jobs: {type: queue}\n  files: {type: storage}\n"
        "functions:\n  hello: {handler: app.handlers.hello}\n"
    )
    guide = client_guide(project, "http://127.0.0.1:9", token=True)
    md = guide["markdown"]
    assert guide["reachable"] is False and "pskit client tunnel" in md
    assert 'client.queue("jobs")' in md and 'client.bucket("files")' in md and "x-pskit-token" in md
    for block in md.split("```python\n")[1:]:
        compile(block.split("```")[0], "client.py", "exec")
    if shutil.which("node"):
        for block in md.split("```js\n")[1:]:
            proc = subprocess.run(["node", "--check", "-"], input=block.split("```")[0], capture_output=True, text=True)
            assert proc.returncode == 0, proc.stderr

    argv = tunnel_argv({"method": "ssh", "host": "13.72.87.80", "user": "azureuser", "identity_file": "k.pem"}, 19324, 9324)
    assert argv[:4] == ["ssh", "-N", "-L", "19324:127.0.0.1:9324"] and argv[-1] == "azureuser@13.72.87.80"
    assert "BatchMode=yes" not in argv and argv.count("-o") == sum(1 for a in argv if "=" in a)
    entry = {"address": "13.72.87.80", "port": 6379, "env": {"PSKIT_X_URL": "redis://:pw@13.72.87.80:6379/0"}}
    assert local_env(entry, 16379) == {"PSKIT_X_URL": "redis://:pw@127.0.0.1:16379/0"}


@pytest.mark.parametrize("consumed", [False, True])
def test_generated_programs_run_against_the_host(live_host, tmp_path, consumed):
    import sys

    from py_serverless_kit.core.client_examples import node_program, python_program

    host, base = live_host
    env = dict(os.environ, PSKIT_HOST=base, PSKIT_ADMIN_TOKEN="s3cret")
    runtime_js = Path(__file__).resolve().parents[2] / "src" / "py_serverless_kit" / "runtime_js"
    copy = tmp_path / "node_modules" / "pskit"
    shutil.copytree(runtime_js, copy)
    for key, native, kind in (("jobs", "order-jobs", "queue"), ("files", "files", "storage"), ("news", "news", "topic")):
        code = python_program(base, key, native, kind, consumed=consumed, builtin=True)
        script = tmp_path / f"use_{key}.py"
        script.write_text(code, "utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=60)
        assert proc.returncode == 0, (kind, proc.stderr)
        if kind == "queue":
            assert "queued" in proc.stdout and ("processing" in proc.stdout) is (not consumed)
        if shutil.which("node"):
            js = tmp_path / f"use-{key}.js"
            js.write_text(node_program(base, key, native, kind, consumed=consumed, builtin=True), "utf-8")
            proc = subprocess.run(["node", str(js)], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=60)
            assert proc.returncode == 0, (kind, proc.stderr)
    assert (tmp_path / "copy-of-hello.txt").read_text() == "hello from a script"
    if not consumed:
        assert host.broker.queue_depth("order-jobs") == 0   # the programs consumed what they sent
