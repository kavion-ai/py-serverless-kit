"""pskit function split: a function out of a shared code file into its own sub-project (core/function_split.py)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from py_serverless_kit.cli.main import cli
from py_serverless_kit.core import function_split as fs

HANDLERS = '''"""Handlers."""

import json
from py_serverless_kit import Context, Event, NotFound, Response
from .util import clean

_ITEMS = {"1": {"id": "1"}}


def _load(key):
    return _ITEMS.get(clean(key))


def hello(event: Event, ctx: Context):
    return {"message": "hi"}


def get_item(event: Event, ctx: Context):
    item = _load(event.http.path_params["id"])
    if item is None:
        raise NotFound("no item")
    return json.loads(json.dumps(item))


def create_item(event: Event, ctx: Context):
    return Response.json(event.http.json(), status=201)
'''

CONFIG = """service: shop  # the shop
provider:
  name: onprem
  runtime: python3.12
  options:
    placement:
      default: api
      groups:
        api: {local: true}
        reads: {local: true, port: 8081, functions: [get-item]}
functions:
  hello:
    handler: app.handlers.hello   # says hi
    events: [{http: GET /hello}]
  get-item:
    handler: app.handlers.get_item
    events: [{http: 'GET /items/{id}'}]
  create-item:
    handler: app.handlers.create_item
    events: [{http: POST /items}]
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", "utf-8")
    (tmp_path / "app" / "handlers.py").write_text(HANDLERS, "utf-8")
    (tmp_path / "app" / "util.py").write_text("def clean(key):\n    return key.strip()\n", "utf-8")
    (tmp_path / "pskit.yml").write_text(CONFIG, "utf-8")
    (tmp_path / "requirements.txt").write_text("# deps\nrequests==2.32.3\n", "utf-8")
    return tmp_path


def test_split_moves_the_function_its_helpers_and_imports(project):
    result = fs.split(project, "get-item")
    assert result["handler"] == "functions.get_item.handler.get_item"
    new = (project / "functions" / "get_item" / "handler.py").read_text("utf-8")
    ast.parse(new)
    assert "from app.util import clean" in new  # relative import made absolute
    assert "from py_serverless_kit import Context, Event, NotFound\n" in new  # only the names it uses
    assert "import json" in new and "_ITEMS = " in new and "def _load(" in new
    assert "def hello" not in new and "def create_item" not in new
    assert (project / "functions" / "__init__.py").is_file()
    assert (project / "functions" / "get_item" / "requirements.txt").is_file()

    old = (project / "app" / "handlers.py").read_text("utf-8")
    assert "def get_item" not in old and "def hello" in old and "def create_item" in old
    assert "NotFound" not in old  # only get_item used it
    assert "from py_serverless_kit import Context, Event, Response" in old

    text = (project / "pskit.yml").read_text("utf-8")
    assert "handler: functions.get_item.handler.get_item" in text
    assert "# says hi" in text and "# the shop" in text  # comments kept
    assert yaml.safe_load(text)["functions"]["get-item"]["handler"] == "functions.get_item.handler.get_item"

    with pytest.raises(fs.SplitError, match="already has its own folder"):
        fs.split(project, "get-item")


def test_requirements_follow_the_imports(project):
    handlers = project / "app" / "handlers.py"
    handlers.write_text(handlers.read_text("utf-8").replace("import json\n", "import json\nimport requests\n")
                        .replace("return json.loads", "requests.utils\n    return json.loads"), "utf-8")
    result = fs.split(project, "get-item")
    assert result["requirements"] == ["requests==2.32.3"]
    assert "requests==2.32.3" in (project / "functions" / "get_item" / "requirements.txt").read_text("utf-8")


def test_a_function_still_called_from_the_shared_file_stays_there(project):
    handlers = project / "app" / "handlers.py"
    handlers.write_text(handlers.read_text("utf-8") + "\n\ndef both(event, ctx):\n    return get_item(event, ctx)\n",
                        "utf-8")
    assert fs.split(project, "get-item")["kept_in_source"] is True
    assert "def get_item" in handlers.read_text("utf-8")


def test_dry_run_and_cli(project, monkeypatch):
    assert fs.shared_in_project(project) == {"app.handlers": ["create-item", "get-item", "hello"]}
    before = (project / "pskit.yml").read_text("utf-8")
    assert fs.plan(project, "hello")["to"] == "functions/hello/handler.py"
    assert (project / "pskit.yml").read_text("utf-8") == before and not (project / "functions").exists()
    monkeypatch.chdir(project)
    out = CliRunner().invoke(cli, ["function", "split", "--all"])
    assert out.exit_code == 0, out.output
    assert fs.shared_in_project(project) == {}
    assert sorted(p.name for p in (project / "functions").iterdir() if p.is_dir()) == [
        "create_item", "get_item", "hello"]
    bad = CliRunner().invoke(cli, ["function", "split", "nope"])
    assert bad.exit_code != 0 and "no function 'nope'" in bad.output


def test_validation_warns_when_groups_share_code(project):
    from py_serverless_kit.core.project import Project

    issues = Project.load(project / "pskit.yml").validate()
    shared = [i for i in issues if "share app/handlers.py" in i.message]
    assert shared and "pskit function split create-item get-item hello" in shared[0].message
    fs.split(project, "get-item")
    issues = Project.load(project / "pskit.yml").validate()
    assert not [i for i in issues if "share app/" in i.message]  # hello and create-item share it, but one group


def test_node_projects_are_refused(project):
    cfg = project / "pskit.yml"
    cfg.write_text(cfg.read_text("utf-8").replace("python3.12", "nodejs20.x"), "utf-8")
    with pytest.raises(fs.SplitError, match="Node.js"):
        fs.plan(project, "hello")
