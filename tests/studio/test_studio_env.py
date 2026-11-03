"""pskit studio: project .venv / npm install, VS Code runtimes, Node.js handler stubs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from py_serverless_kit.studio import devenv
from py_serverless_kit.studio import project as proj
from py_serverless_kit.studio.node_stubs import defines, ensure_node_handler
from py_serverless_kit.studio.vscode import VSCode

from .test_studio import call, studio  # noqa: F401 - fixture

# --------------------------------------------------------------------------- venv


def test_venv_plan_creates_then_installs(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests\n")
    steps = devenv.plan(tmp_path)
    assert steps[0][:3] == [sys.executable, "-m", "venv"] and steps[0][-1] == str(tmp_path / ".venv")
    assert steps[-1][-2:] == ["-r", str(tmp_path / "requirements.txt")]
    assert steps[1][-3:] == ["install", "--upgrade", "pip"]


def test_venv_plan_reuses_existing_and_recreates(tmp_path):
    py = devenv.venv_python(tmp_path)
    py.parent.mkdir(parents=True)
    py.write_text("")
    steps = devenv.plan(tmp_path)
    assert all("venv" not in s[1:3] for s in steps)  # not recreated
    assert "--clear" in devenv.plan(tmp_path, recreate=True)[0]
    with pytest.raises(ValueError):
        devenv.plan(tmp_path, python=str(tmp_path / "nope" / "python"))


def test_node_plan_needs_package_json(tmp_path, monkeypatch):
    monkeypatch.setattr(devenv.shutil, "which", lambda name: "/usr/bin/npm" if name == "npm" else None)
    with pytest.raises(ValueError, match="package.json"):
        devenv.plan(tmp_path, language="node")
    (tmp_path / "package.json").write_text("{}")
    assert devenv.plan(tmp_path, language="node") == [["/usr/bin/npm", "install", "--no-audit", "--no-fund"]]
    (tmp_path / "package-lock.json").write_text("{}")
    assert devenv.plan(tmp_path, language="node")[0][1] == "ci"


def test_run_steps_streams_and_stops_on_failure(tmp_path):
    lines = []
    ok = [[sys.executable, "-c", "print('one')"], [sys.executable, "-c", "import sys; sys.exit(3)"], ["never"]]
    assert devenv.run_steps(tmp_path, ok, lambda text, stream: lines.append((stream, text))) == 3
    assert ("stdout", "one") in lines and not any("never" in t for _, t in lines)


def test_env_endpoints(studio):  # noqa: F811
    base, _root, _ = studio
    status, body = call(base, "GET", "/api/env")
    assert status == 200 and body["venv"]["exists"] is False and body["interpreters"]
    assert call(base, "POST", "/api/env/setup", {"language": "ruby"})[0] == 400
    assert call(base, "POST", "/api/env/setup", {"python": "/definitely/not/python"})[0] == 400


# --------------------------------------------------------------------------- VS Code runtimes


def test_vscode_runtime_image_and_dockerfile(tmp_path):
    vs = VSCode(tmp_path)
    assert vs.target_image() == vs.image  # no runtimes: the plain image
    vs.set_runtimes("3.12", "20")
    assert vs.target_image() == "pskit-code-server:code-server-4.96.4-py3.12-node20"
    text = vs.dockerfile()
    assert text.startswith("# Generated") and f"FROM {vs.image}" in text
    assert "uv python install 3.12" in text and "latest-v20.x" in text and "sha256sum -c" in text
    assert text.rstrip().splitlines()[-2:] == ["USER coder", "RUN code-server --install-extension ms-python.python || true"]
    vs.set_runtimes(None, "20.18.1")
    assert "dist/v20.18.1" in vs.dockerfile() and "uv python" not in vs.dockerfile()
    for bad in (("2.7", None), ("3.12; rm -rf /", None), (None, "16"), (None, "20 && x")):
        with pytest.raises(ValueError):
            vs.set_runtimes(*bad)


def test_vscode_start_builds_the_runtime_image(tmp_path, monkeypatch):
    calls = []

    class Proc:
        def __init__(self, code=0, out=""):
            self.returncode, self.stdout, self.stderr = code, out, ""

    def runner(cmd, timeout):
        calls.append(cmd[1:])
        if cmd[1] == "version":
            return Proc(0, "27.0")
        if cmd[1:3] == ["container", "inspect"]:
            return Proc(1)
        if cmd[1:3] == ["image", "inspect"]:
            return Proc(0 if cmd[3] == "codercom/code-server:4.96.4" else 1)
        return Proc(0)

    vs = VSCode(tmp_path, runner=runner)
    vs.set_runtimes("3.11", None)
    built = []
    monkeypatch.setattr(vs, "_stream", lambda cmd, job: built.append(cmd) or 0)
    monkeypatch.setattr("py_serverless_kit.studio.vscode._wait_http", lambda url, timeout: True)

    class Job:
        def emit(self, *a):
            pass

    assert vs.start(Job()) == 0
    assert built and built[0][1:4] == ["build", "-t", vs.target_image()]
    assert (tmp_path / ".pskit" / "studio" / "vscode" / "Dockerfile").is_file()
    run = next(c for c in calls if c and c[0] == "run")
    assert vs.target_image() in run


# --------------------------------------------------------------------------- Node.js stubs


@pytest.mark.parametrize(
    "typescript,package_type,suffix,needle",
    [
        (True, "commonjs", ".ts", "export async function hello(event: Event, ctx: Context)"),
        (False, "commonjs", ".js", "exports.hello = async function hello(event, ctx)"),
        (False, "module", ".js", "export async function hello(event, ctx)"),
    ],
)
def test_node_stub_flavours(tmp_path, typescript, package_type, suffix, needle):
    path, created, line = ensure_node_handler(tmp_path, tmp_path, "src.handlers.hello", "http", typescript, package_type)
    assert created and path.suffix == suffix and needle in path.read_text()
    assert defines(path.read_text(), "hello") == line
    again = ensure_node_handler(tmp_path, tmp_path, "src.handlers.hello", "http", typescript, package_type)
    assert again[1] is False and again[2] == line


def test_node_stub_adds_batch_import_once(tmp_path):
    ensure_node_handler(tmp_path, tmp_path, "src.handlers.a", "queue", False, "commonjs")
    path, _, _ = ensure_node_handler(tmp_path, tmp_path, "src.handlers.b", "queue", False, "commonjs")
    text = path.read_text()
    assert text.count('require("pskit")') == 1 and text.startswith("// Handlers created")


def test_ensure_handler_follows_the_service_language(tmp_path):
    (tmp_path / "pskit.yml").write_text("service: demo\nprovider: {name: aws, runtime: nodejs20}\n")
    (tmp_path / "tsconfig.json").write_text("{}")
    out = proj.ensure_handler(tmp_path, "src.handlers.hello", ["http"])
    assert out["path"] == "src/handlers.ts" and out["created"]
    assert "export async function hello" in Path(tmp_path, out["path"]).read_text()


def test_init_typescript_project(tmp_path):
    state = proj.init_project(tmp_path, "demo-ts", "aws", "http", language="typescript")
    assert state["raw"]["provider"]["runtime"].startswith("nodejs")
    assert (tmp_path / "tsconfig.json").is_file() and list((tmp_path / "src").glob("*.ts"))
    with pytest.raises(proj.StudioError):
        proj.init_project(tmp_path / "x", "demo", "aws", "http", language="ruby")
