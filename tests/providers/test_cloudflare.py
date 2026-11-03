import hashlib
import json
import shutil
import subprocess
import sys
import textwrap

import pytest

from tests.conftest import full_config

CONFIG = """
service: demo
provider:
  name: cloudflare
  options: {account_id: acc1, workers_subdomain: myco, zone_id: zone1}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: "GET /hello/{name}"
    options: {route: "api.example.com/hello*"}
  tick:
    handler: app.handlers.tick
    events:
      - schedule: 5 minutes
      - schedule: {cron: "0 12 * * 1", input: {report: weekly}}
"""

# Executes a generated worker module with a fake `workers` SDK, in a clean interpreter
# so the in-memory import hook cannot leak into the test process.
RUNNER = textwrap.dedent(
    """
    import asyncio, json, runpy, sys, types
    w = types.ModuleType("workers")
    class WorkerEntrypoint:
        env = None
    class Response:
        def __init__(self, body, status=200, headers=None):
            self.body, self.status, self.headers = body, status, headers
    w.WorkerEntrypoint, w.Response = WorkerEntrypoint, Response
    sys.modules["workers"] = w
    hello = runpy.run_path(sys.argv[1])
    class Req:
        method = "GET"
        url = "https://demo-dev-hello.myco.workers.dev/hello/ada"
        headers = {"cf-ray": "r1"}
        async def text(self):
            return ""
    r = asyncio.run(hello["Default"]().fetch(Req()))
    tick = runpy.run_path(sys.argv[2])
    class Ctl:
        cron = "0 12 * * 1"
        scheduledTime = 0
    s = asyncio.run(tick["Default"]().scheduled(Ctl()))
    import py_serverless_kit
    print(json.dumps({"status": r.status, "body": json.loads(r.body), "scheduled": s,
                      "runtime": py_serverless_kit.__file__}))
    """
)


def _errors(project):
    return [str(i) for i in project.validate() if i.level == "error"]


def test_validation(make_project):
    project = make_project(full_config("cloudflare"))
    issues = project.validate()
    joined = "\n".join(str(i) for i in issues if i.level == "error")
    assert "options.account_id is required" in joined
    for kind in ("queue", "storage", "topic"):
        assert f"`{kind}` events" in joined
    assert any("Pyodide" in str(i) for i in issues if i.level == "warning")


def test_render_and_run_worker(make_project, render, tmp_path):
    project = make_project(CONFIG)
    assert _errors(project) == []
    tf = render(project)
    assert tf["terraform"]["required_providers"]["cloudflare"]["source"] == "cloudflare/cloudflare"
    res = tf["resource"]
    script = res["cloudflare_workers_script"]["hello"]
    assert script["script_name"] == "demo-dev-hello"
    assert script["content_type"] == "text/x-python"
    assert script["compatibility_flags"] == ["python_workers"]
    hello_file = project.work_dir / "cloudflare" / "hello.py"
    tick_file = project.work_dir / "cloudflare" / "tick.py"
    assert script["content_file"] == "${path.module}/cloudflare/hello.py"
    assert script["content_sha256"] == hashlib.sha256(hello_file.read_bytes()).hexdigest()
    assert "route" not in script
    assert res["cloudflare_workers_route"]["hello"]["pattern"] == "api.example.com/hello*"
    assert "hello" in res["cloudflare_workers_script_subdomain"]
    assert "tick" not in res["cloudflare_workers_script_subdomain"]
    crons = [s["cron"] for s in res["cloudflare_workers_cron_trigger"]["tick"]["schedules"]]
    assert crons == ["*/5 * * * *", "0 12 * * 1"]
    out = tf["output"]["pskit"]["value"]
    assert out["functions"]["hello"]["url"] == "https://demo-dev-hello.myco.workers.dev"

    runner = tmp_path / "run_worker.py"
    runner.write_text(RUNNER)
    proc = subprocess.run(
        [sys.executable, "-I", str(runner), str(hello_file), str(tick_file)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["status"] == 200
    assert result["body"]["message"] == "hello ada"
    assert result["scheduled"] == {"type": "schedule", "data": {"report": "weekly"}}
    assert result["runtime"].startswith("/pskit_bundle/")


NODE_SKIP = pytest.mark.skipif(shutil.which("node") is None or shutil.which("npm") is None, reason="needs Node.js and npm")

JS_HANDLERS = {"app/handlers.js": "exports.hello = async () => ({ ok: true });\nexports.tick = async () => null;\n"}


def node_config(provider: str, options: str = "{}", extra: str = "") -> str:
    return f"""
service: demo
provider:
  name: {provider}
  runtime: nodejs20
  options: {options}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: "GET /hello/{{name}}"
  tick:
    handler: app.handlers.tick
{extra}
"""


CF_OPTS = "{account_id: acc1, workers_subdomain: myco}"


def test_node_entries_import_handlers_statically(make_project):
    extra = """
    events:
      - schedule: {cron: "0 12 * * 1", input: {report: weekly}}
"""
    project = make_project(node_config("cloudflare", CF_OPTS, extra), files=JS_HANDLERS)
    provider = project.provider
    files = provider.shim_files(project.config)
    assert set(files) == {"_pskit_cf/hello.mjs", "_pskit_cf/tick.mjs", "_pskit_cf/require_shim.mjs"}
    tick = files["_pskit_cf/tick.mjs"]
    assert tick.splitlines()[1] == 'import "./require_shim.mjs";'  # before anything that calls require()
    assert 'import * as m0 from "../app/handlers";' in tick
    assert 'modules: { "app.handlers": m0 }' in tick
    assert '"0 12 * * 1": {"report": "weekly"}' in tick
    assert 'import * as b2 from "node:crypto";' in files["_pskit_cf/require_shim.mjs"]
    assert provider.node_bundle_entries(project.config) == {
        "_pskit_cf/hello.bundle.mjs": "_pskit_cf/hello.mjs",
        "_pskit_cf/tick.bundle.mjs": "_pskit_cf/tick.mjs",
    }
    assert "--format=esm" in provider.node_bundle_options
    # No Pyodide warning for JavaScript Workers.
    assert not any("Pyodide" in i.message for i in project.validate())


def test_node_render_uploads_the_bundle_with_bindings(make_project, tmp_path, monkeypatch):
    from py_serverless_kit.core.deployer import Deployer

    project = make_project(node_config("cloudflare", CF_OPTS), files=JS_HANDLERS)
    build = project.work_dir / "build"

    def fake_build(proj, skip_deps=False, log=print):  # the esbuild step itself is the builder's job
        from py_serverless_kit.providers.base import Artifact

        (build / "_pskit_cf").mkdir(parents=True, exist_ok=True)
        for name in ("hello", "tick"):
            (build / "_pskit_cf" / f"{name}.bundle.mjs").write_text(f"export default {{}}; // {name}\n")
        zip_path = project.work_dir / "artifact.zip"
        zip_path.write_bytes(b"zip")
        return Artifact(path=zip_path, sha256="0" * 64, sha256_b64="x", size=3, build_dir=build)

    monkeypatch.setattr("py_serverless_kit.core.deployer.build_artifact", fake_build)
    result = Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    tf = json.loads(result.tf_file.read_text("utf-8"))
    script = tf["resource"]["cloudflare_workers_script"]["hello"]
    assert script["content_type"] == "application/javascript+module"
    assert script["main_module"] == "worker.mjs"
    assert script["compatibility_flags"] == ["nodejs_compat"]
    assert script["content_file"].endswith("/cloudflare/hello.mjs")
    names = {b["name"]: b for b in script["bindings"]}
    assert names["PSKIT_FUNCTION"] == {"name": "PSKIT_FUNCTION", "type": "plain_text", "text": "hello"}
    assert (project.work_dir / "cloudflare" / "hello.mjs").read_text().startswith("export default")


def test_node_render_without_bundle_is_a_clear_error(make_project, monkeypatch):
    import pytest as _pytest

    from py_serverless_kit.core.deployer import Deployer
    from py_serverless_kit.providers.base import Artifact, ProviderError

    project = make_project(node_config("cloudflare", CF_OPTS), files=JS_HANDLERS)

    def fake_build(proj, skip_deps=False, log=print):
        build = project.work_dir / "build"
        build.mkdir(parents=True, exist_ok=True)
        return Artifact(path=build / "a.zip", sha256="0" * 64, sha256_b64="x", size=0, build_dir=build)

    monkeypatch.setattr("py_serverless_kit.core.deployer.build_artifact", fake_build)
    with _pytest.raises(ProviderError, match="esbuild bundle"):
        Deployer(project, echo=lambda _m: None).package(skip_deps=True)
