import json
import zipfile

import pytest

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.packaging.builder import collect_sources, glob_to_regex, read_requirements

CONFIG = """
service: pkg
provider: {name: aws}
package:
  exclude: ["app/secret_*.py"]
functions:
  hello: {handler: app.handlers.hello, events: [{http: GET /hello}]}
"""


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("**/*.py", "a/b/c.py", True),
        ("**/*.py", "c.py", True),
        ("*.py", "a/c.py", False),
        (".git/**", ".git/config", True),
        ("tests/", "tests/x/y.py", True),
        ("./app/*.py", "app/x.py", True),
        ("app/?.py", "app/x.py", True),
    ],
)
def test_glob(pattern, path, expected):
    assert bool(glob_to_regex(pattern).match(path)) is expected


def test_collect_sources_defaults(tmp_path):
    for rel in [
        "app/a.py",
        "app/__pycache__/a.pyc",
        ".git/HEAD",
        ".venv/lib/x.py",
        "tests/test_a.py",
        ".env",
        "pskit.yml",
        "data/x.json",
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    files = sorted(p.relative_to(tmp_path).as_posix() for p in collect_sources(tmp_path, ["**/*"], []))
    assert files == ["app/a.py", "data/x.json"]


def test_read_requirements_strips_kit(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("# comment\nrequests==2.32.0\npy-serverless-kit>=0.1\npy_serverless_kit\n\nhttpx\n")
    assert read_requirements(req) == ["requests==2.32.0", "httpx"]
    assert read_requirements(tmp_path / "missing.txt") == []


def test_artifact_contents_and_reproducible(make_project):
    project = make_project(CONFIG, files={"app/secret_keys.py": "KEY = 1\n", ".env": "X=1\n"})
    deployer = Deployer(project, echo=lambda _m: None)
    first = deployer.package(skip_deps=True)
    with zipfile.ZipFile(first.artifact.path) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("pskit_manifest.json"))
        infos = zf.infolist()
    assert "app/handlers.py" in names
    assert "pskit_entry.py" in names
    assert "py_serverless_kit/runtime/dispatch.py" in names
    assert "py_serverless_kit/cli/main.py" not in names  # CLI never shipped
    assert "app/secret_keys.py" not in names and ".env" not in names and "pskit.yml" not in names
    assert all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in infos)
    assert manifest["functions"]["hello"]["routes"] == [{"method": "GET", "path": "/hello", "cors": None}]
    assert manifest["functions"]["hello"]["resource_name"] == "pkg-dev-hello"
    second = deployer.package(skip_deps=True)
    assert first.artifact.sha256 == second.artifact.sha256
    assert (project.root / ".pskit" / ".gitignore").is_file()


def test_vendored_runtime_is_stdlib_only(make_project):
    """The runtime shipped to the cloud must import without pydantic / yaml / click."""
    import ast

    project = make_project(CONFIG)
    result = Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    with zipfile.ZipFile(result.artifact.path) as zf:
        sources = {
            n: zf.read(n).decode() for n in zf.namelist() if n.startswith("py_serverless_kit/") and n.endswith(".py")
        }
    forbidden = {"pydantic", "yaml", "click"}
    for name, src in sources.items():
        for node in ast.walk(ast.parse(src)):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            for mod in mods:
                assert mod.split(".")[0] not in forbidden, f"{name} imports {mod}"


def test_hooks_run(make_project, tmp_path):
    import sys

    python = sys.executable.replace("\\", "/")
    project = make_project(
        CONFIG + f"hooks:\n  before_package:\n    - '\"{python}\" make_marker.py'\n",
        files={"make_marker.py": "open('hook.txt', 'w').write('ok')\n"},
    )
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    assert (project.root / "hook.txt").read_text() == "ok"


def test_runtime_is_python39_compatible():
    """The vendored runtime runs on clouds still offering Python 3.9 (Tencent, Huawei, ...)."""
    import ast
    import pathlib

    import py_serverless_kit

    pkg = pathlib.Path(py_serverless_kit.__file__).parent
    for path in [pkg / "__init__.py", *sorted((pkg / "runtime").rglob("*.py"))]:
        source = path.read_text("utf-8")
        tree = ast.parse(source, feature_version=(3, 9))
        if "from __future__ import annotations" in source:
            continue
        for node in ast.walk(tree):
            ann = getattr(node, "annotation", None) or getattr(node, "returns", None)
            if ann is not None:
                assert not any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(ann)), (
                    f"{path}:{node.lineno} uses X | Y annotations without `from __future__ import annotations`"
                )
