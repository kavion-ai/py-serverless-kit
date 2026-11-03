"""Node.js / TypeScript services: packaging, ``pskit init`` templates and local runs."""

from __future__ import annotations

import json
import shutil
import textwrap
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.cli.templates import render
from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, build_event, http_event
from py_serverless_kit.packaging import node
from py_serverless_kit.packaging.builder import BuildError

from .node_support import node_skip_reason, tool_path

needs_runtime = pytest.mark.skipif(not node.runtime_available(), reason="runtime_js/index.js is not available")

JS_CONFIG = """
service: node-demo
provider:
  name: {provider}
  runtime: nodejs20
  options: {options}
functions:
  hello:
    handler: src.handlers.hello
    events:
      - http: GET /hello
  worker:
    handler: src.handlers.worker
    events:
      - queue: jobs
  step:
    handler: src.handlers.step
workflows:
  flow:
    engine: embedded
    start_at: Go
    states:
      Go: {{type: task, function: step, end: true}}
"""

JS_HANDLERS = """
const { BatchResult, NotFound, Response } = require("pskit");

async function hello(event, ctx) {
  const name = event.http.query.name || "world";
  if (name === "missing") throw new NotFound("no such name");
  return { message: `hello ${name}`, provider: event.provider };
}

async function worker(event) {
  const result = new BatchResult();
  for (const record of event.records) if (record.text() === "fail") result.fail(record);
  return result;
}

class Boom extends Error {}

async function step(event) {
  if (event.data && event.data.boom) throw new Boom("boom");
  return { ...(event.data || {}), stepped: true };
}

module.exports = { hello, worker, step };
"""

TS_HANDLERS = """
import { Response } from "pskit";
import type { Context, Event } from "pskit";

export async function hello(event: Event, ctx: Context) {
  const name: string = event.http?.query.name ?? "world";
  return Response.json({ message: `hello ${name}`, typed: true }, 201);
}
"""

OPTIONS = {
    "aws": "{}",
    "gcp": "{project: demo-project}",
    "azure": "{subscription_id: 00000000-0000-0000-0000-000000000000}",
}


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(textwrap.dedent(text).lstrip().encode("utf-8"))


def _js_project(root: Path, provider: str = "aws", package: dict = None) -> Project:  # type: ignore[assignment]
    _write(root, "pskit.yml", JS_CONFIG.format(provider=provider, options=OPTIONS[provider]))
    _write(root, "src/handlers.js", JS_HANDLERS)
    if package is not None:
        (root / "package.json").write_bytes(json.dumps(package).encode("utf-8"))
    return Project.load(cwd=root)


def _ts_project(root: Path) -> Project:
    _write(
        root,
        "pskit.yml",
        """
        service: ts-demo
        provider: {name: aws, runtime: nodejs20}
        functions:
          hello:
            handler: src.handlers.hello
            events: [{http: GET /hello}]
        """,
    )
    _write(root, "src/handlers.ts", TS_HANDLERS)
    return Project.load(cwd=root)


@pytest.fixture(autouse=True)
def _tools(monkeypatch):
    monkeypatch.setenv("PATH", tool_path())


# --------------------------------------------------------------------- helpers


def test_language_and_handler_resolution(tmp_path):
    _write(tmp_path, "src/handlers.ts", "export const x = 1;\n")
    _write(tmp_path, "lib/index.js", "")
    assert node.handler_file(tmp_path, "src.handlers.hello") == tmp_path / "src" / "handlers.ts"
    assert node.handler_file(tmp_path, "lib.run") == tmp_path / "lib" / "index.js"
    assert node.handler_file(tmp_path, "nope.fn") is None
    assert node.wants_typescript(None, tmp_path, tmp_path, ["src.handlers.hello"]) is True
    assert node.wants_typescript(False, tmp_path, tmp_path, ["src.handlers.hello"]) is False
    assert node.wants_typescript(None, tmp_path, tmp_path, ["lib.run"]) is False


def test_missing_tools_explain_how_to_install(tmp_path, monkeypatch):
    monkeypatch.setattr(node, "_which", lambda name: None)
    with pytest.raises(node.NodeBuildError, match="nodejs.org"):
        node.node_exe()
    with pytest.raises(node.NodeBuildError, match="typescript"):
        node.tsc_command(tmp_path)


def test_tool_lookup_prefers_project_then_path_then_npx(tmp_path, monkeypatch):
    found = {"npx": "/usr/bin/npx"}
    monkeypatch.setattr(node, "_which", lambda name: found.get(name))
    assert node.tsc_command(tmp_path) == ["/usr/bin/npx", "--yes", *node.TSC_NPX]
    found["tsc"] = "/usr/bin/tsc"
    assert node.tsc_command(tmp_path) == ["/usr/bin/tsc"]
    local = tmp_path / "node_modules" / ".bin"
    local.mkdir(parents=True)
    for name in ("tsc", "tsc.cmd"):
        (local / name).write_text("")
    assert Path(node.tsc_command(tmp_path)[0]).parent == local


def test_python_services_are_untouched(make_project):
    project = make_project(
        """
        service: py-demo
        provider: {name: aws}
        functions:
          hello: {handler: app.handlers.hello, events: [{http: GET /hello}]}
        """
    )
    artifact = Deployer(project, echo=lambda _m: None).package(skip_deps=True).artifact
    names = zipfile.ZipFile(artifact.path).namelist()
    assert "py_serverless_kit/runtime/dispatch.py" in names
    assert not any(n.startswith("pskit_runtime/") for n in names)


# --------------------------------------------------------------------- packaging


@needs_runtime
def test_js_bundle_layout_and_reproducible(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(node, "npm_install", lambda *a, **k: calls.append(a))
    project = _js_project(tmp_path)
    first = Deployer(project, echo=lambda _m: None).package(skip_deps=True).artifact
    names = set(zipfile.ZipFile(first.path).namelist())
    assert {"src/handlers.js", "pskit_manifest.json", "package.json", "pskit_runtime/index.js"} <= names
    assert "node_modules/pskit/index.js" in names
    assert not calls  # no dependencies, nothing to install
    manifest = json.loads(zipfile.ZipFile(first.path).read("pskit_manifest.json"))
    assert manifest["functions"]["flow-orchestrator"]["handler"] == "pskit_runtime.workflow.orchestrate"
    second = Deployer(Project.load(cwd=tmp_path), echo=lambda _m: None).package(skip_deps=True).artifact
    assert first.sha256 == second.sha256
    assert (tmp_path / ".pskit" / "types" / "pskit" / "package.json").is_file() or not (
        node.RUNTIME_JS / "index.d.ts"
    ).is_file()


@needs_runtime
def test_dependencies_are_installed_unless_skipped(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(node, "npm_install", lambda build_dir, args, log: calls.append((build_dir, args)))
    package = {"name": "x", "dependencies": {"left-pad": "1.3.0", "pskit": "file:somewhere"}, "devDependencies": {"t": "1"}}
    project = _js_project(tmp_path, package=package)
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    assert not calls
    Deployer(Project.load(cwd=tmp_path), echo=lambda _m: None).package(skip_deps=False)
    assert len(calls) == 1
    bundled = json.loads((project.work_dir / "build" / "package.json").read_text("utf-8"))
    assert bundled["dependencies"] == {"left-pad": "1.3.0"}  # pskit is vendored, never fetched
    assert bundled["devDependencies"] == {"t": "1"}  # kept so a lockfile still matches; npm omits them


@needs_runtime
@pytest.mark.parametrize("provider", ["gcp", "azure"])
def test_remote_build_providers_get_a_pskit_dependency(tmp_path, monkeypatch, provider):
    monkeypatch.setattr(node, "npm_install", lambda *a, **k: pytest.fail("must not npm install"))
    project = _js_project(tmp_path, provider=provider, package={"name": "x", "dependencies": {"left-pad": "1.3.0"}})
    assert project.provider.node_vendor_dependencies is False
    Deployer(project, echo=lambda _m: None).package(skip_deps=False)
    build = project.work_dir / "build"
    bundled = json.loads((build / "package.json").read_text("utf-8"))
    deps = bundled["dependencies"]
    assert deps["left-pad"] == "1.3.0" and deps["pskit"] == "file:./pskit_runtime"
    hook = getattr(project.provider, "node_package", None)
    if callable(hook):  # the provider's framework dependency / main are merged in, provider wins
        extra = hook(project.config)
        assert all(deps.get(k) == v for k, v in (extra.get("dependencies") or {}).items())
        if extra.get("main"):
            assert bundled["main"] == extra["main"]
    assert (build / "pskit_runtime" / "index.js").is_file()
    assert not (build / "node_modules").exists()


@needs_runtime
def test_build_command_and_out_dir(tmp_path, monkeypatch):
    project = _js_project(tmp_path)
    shutil.move(str(tmp_path / "src"), str(tmp_path / "dist-src"))
    calls = []
    monkeypatch.setattr(node, "run", lambda cmd, cwd, what, env=None: calls.append(cmd) or "")
    yml = (tmp_path / "pskit.yml").read_text("utf-8")
    yml += "package:\n  node: {build: [npm, run, build], out_dir: dist-src}\n"
    (tmp_path / "pskit.yml").write_bytes(yml.replace("src.handlers", "handlers").encode("utf-8"))
    shutil.move(str(tmp_path / "dist-src" / "handlers.js"), str(tmp_path / "dist-src" / "handlers.js"))
    project = Project.load(cwd=tmp_path)
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    assert calls and calls[0][1:] == ["run", "build"]
    assert (project.work_dir / "build" / "handlers.js").is_file()


@needs_runtime
def test_tsc_failure_is_a_build_error(tmp_path, monkeypatch):
    def boom(cmd, cwd, what, env=None):
        raise node.NodeBuildError("TypeScript compile (tsc) failed (exit 2):\nsrc/handlers.ts(1,1): error TS1")

    monkeypatch.setattr(node, "run", boom)
    project = _ts_project(tmp_path)
    with pytest.raises(BuildError, match="TS1"):
        Deployer(project, echo=lambda _m: None).package(skip_deps=True)


@needs_runtime
def test_typescript_is_compiled(tmp_path):
    if not shutil.which("tsc", path=tool_path()) or not (node.RUNTIME_JS / "index.d.ts").is_file():
        pytest.skip("tsc or runtime_js/index.d.ts is not available")
    project = _ts_project(tmp_path)
    artifact = Deployer(project, echo=lambda _m: None).package(skip_deps=True).artifact
    names = zipfile.ZipFile(artifact.path).namelist()
    assert "src/handlers.js" in names and "src/handlers.ts" not in names
    code = zipfile.ZipFile(artifact.path).read("src/handlers.js").decode("utf-8")
    assert "exports.hello" in code and 'require("pskit")' in code


# --------------------------------------------------------------------- init templates


@pytest.mark.parametrize("template", ["http", "events", "workflow", "full"])
@pytest.mark.parametrize("typescript", [False, True])
def test_node_templates_validate(tmp_path, template, typescript):
    files = render(template, "tpl-demo", "aws", runtime="nodejs20", typescript=typescript)
    for rel, text in files.items():
        _write(tmp_path, rel, text)
    project = Project.load(cwd=tmp_path)
    assert project.config.language == "node"
    assert [i for i in project.validate() if i.level == "error"] == []
    source = tmp_path / "src"
    for fn in project.config.functions.values():
        if fn.handler.startswith("pskit_runtime."):
            continue
        found = node.handler_file(tmp_path, fn.handler)
        assert found is not None and found.suffix == (".ts" if typescript else ".js")
        assert fn.handler.rsplit(".", 1)[1] in found.read_text("utf-8")
    assert ("tsconfig.json" in files) == typescript
    assert json.loads(files["package.json"])["name"] == "tpl-demo"
    assert source.is_dir()


def test_cli_init_typescript(tmp_path):
    result = CliRunner().invoke(cli, ["init", str(tmp_path / "svc"), "-p", "aws", "--typescript", "-t", "full"])
    assert result.exit_code == 0, result.output
    root = tmp_path / "svc"
    assert b"\r\n" not in (root / "src" / "handlers.ts").read_bytes()
    assert "runtime: nodejs20" in (root / "pskit.yml").read_text("utf-8")
    assert (root / "tsconfig.json").is_file()
    if (node.RUNTIME_JS / "index.d.ts").is_file():
        assert (root / ".pskit" / "types" / "pskit" / "index.d.ts").is_file()


def test_cli_init_runtime_and_language_must_agree(tmp_path):
    result = CliRunner().invoke(cli, ["init", str(tmp_path / "xy"), "--runtime", "python3.12", "--language", "typescript"])
    assert result.exit_code != 0 and "does not match" in result.output
    result = CliRunner().invoke(cli, ["init", str(tmp_path / "js"), "--runtime", "nodejs22"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "js" / "src" / "handlers.js").is_file()
    assert "runtime: nodejs22" in (tmp_path / "js" / "pskit.yml").read_text("utf-8")


# --------------------------------------------------------------------- local runs


def _skip_without_node(typescript: bool = False) -> None:
    reason = node_skip_reason(typescript)
    if reason:
        pytest.skip(reason)


def test_local_invoke_javascript(tmp_path):
    _skip_without_node()
    runner = LocalRunner(_js_project(tmp_path), env_file=None)
    try:
        resp = runner.invoke("hello", http_event("GET", "/hello?name=Ada"))
        assert resp.status == 200 and json.loads(resp.render()[2])["message"] == "hello Ada"
        assert runner.invoke("hello", http_event("GET", "/hello?name=missing")).status == 404
        batch = runner.invoke("worker", build_event("queue", ["ok", "fail", "ok"]))
        assert batch.failed == ["local-1"]
        out = runner.run_workflow("flow", {"a": 1})
        assert out["output"] == {"a": 1, "stepped": True}
        from py_serverless_kit.runtime.workflow import WorkflowFailed

        with pytest.raises(WorkflowFailed) as exc:
            runner.run_workflow("flow", {"boom": True})
        assert exc.value.error == "Boom"
    finally:
        runner.close()


def test_local_invoke_typescript_and_reload(tmp_path):
    _skip_without_node(typescript=True)
    runner = LocalRunner(_ts_project(tmp_path), env_file=None)
    try:
        resp = runner.invoke("hello", http_event("GET", "/hello?name=Ts"))
        assert resp.status == 201 and json.loads(resp.render()[2]) == {"message": "hello Ts", "typed": true_()}
        _write(tmp_path, "src/handlers.ts", TS_HANDLERS.replace("typed: true", "typed: false"))
        runner.reload()
        resp = runner.invoke("hello", http_event("GET", "/hello"))
        assert json.loads(resp.render()[2])["typed"] is False
    finally:
        runner.close()


def true_() -> bool:
    return True


def test_cli_invoke_javascript(tmp_path, monkeypatch):
    _skip_without_node()
    _js_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["invoke", "-f", "hello", "--path", "/hello?name=Cli"])
    assert result.exit_code == 0, result.output
    out = result.output
    body = out if out.startswith("{") else out[out.index("\n{") + 1 :]  # skip function log lines
    assert json.loads(body)["body"]["message"] == "hello Cli"


@needs_runtime
def test_provider_package_json_wins_and_overwrites_warn(tmp_path, monkeypatch):
    project = _js_project(tmp_path, package={"name": "x", "main": "src/handlers.js", "scripts": {"a": "b"}})
    _write(tmp_path, "index.js", "// user file\n")
    original = type(project.provider).shim_files

    def shims(self, cfg):
        out = dict(original(self, cfg))
        out["index.js"] = "module.exports = require('./pskit_runtime');\n"
        out["package.json"] = json.dumps({"main": "index.js", "scripts": {"start": "node index.js"}})
        return out

    monkeypatch.setattr(type(project.provider), "shim_files", shims)
    messages = []
    Deployer(project, echo=messages.append).package(skip_deps=True)
    build = project.work_dir / "build"
    bundled = json.loads((build / "package.json").read_text("utf-8"))
    assert bundled["main"] == "index.js"
    assert bundled["scripts"] == {"a": "b", "start": "node index.js"}
    assert "pskit_runtime" in (build / "index.js").read_text("utf-8")
    assert any("index.js in your sources is replaced" in m for m in messages)
