from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pytest

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.core.project import Project
from py_serverless_kit.runtime import manifest as runtime_manifest

HANDLERS = """
from py_serverless_kit import Event, Context, Response, BatchResult, NotFound


def hello(event: Event, ctx: Context):
    name = event.http.path_params.get("name") or event.http.query.get("name", "world")
    return {"message": f"hello {name}", "provider": event.provider}


def create(event: Event, ctx: Context):
    body = event.http.json()
    if "id" not in body:
        raise NotFound("missing id")
    return Response.json(body, status=201)


def worker(event: Event, ctx: Context):
    result = BatchResult()
    for record in event.records:
        if record.text() == "fail":
            result.fail(record)
    return result


def tick(event: Event):
    return {"type": event.type, "data": event.data}


def step(event: Event, ctx: Context):
    data = dict(event.data or {})
    data["steps"] = data.get("steps", 0) + 1
    return data
"""

FULL_CONFIG = """
service: demo
provider:
  name: {provider}
  {region_line}
  options: {options}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello/{{name}}
      - http: {{path: /hello, method: POST, cors: true}}
  tick:
    handler: app.handlers.tick
    events:
      - schedule: 5 minutes
      - schedule: {{cron: "0 12 * * 1", input: {{report: weekly}}}}
  worker:
    handler: app.handlers.worker
    events:
      - queue: {{name: jobs}}
      - storage: {{bucket: demo-uploads-1234, suffix: .csv}}
      - topic: events
  step:
    handler: app.handlers.step
workflows:
  pipeline:
    start_at: First
    states:
      First: {{type: task, function: step, next: Second}}
      Second: {{type: task, function: step, end: true}}
"""


@pytest.fixture(autouse=True)
def _reset_manifest():
    runtime_manifest.set_manifest(None)
    yield
    runtime_manifest.set_manifest(None)


@pytest.fixture(autouse=True)
def _reset_onprem_globals(monkeypatch):
    """Host.open() installs a process-wide broker/executor and sets env vars; undo that after each test."""
    from py_serverless_kit.runtime import onprem_host, workflow

    for key in ("PSKIT_ONPREM_ROOT", "PSKIT_MANIFEST"):
        monkeypatch.setenv(key, "x")  # registers the current value (or absence) for restoration
        monkeypatch.delenv(key)
    yield
    onprem_host.install_broker(None)
    workflow.install_executor(None)


@pytest.fixture
def make_project(tmp_path: Path) -> Callable[..., Project]:
    """Create a project directory from YAML text and return a loaded :class:`Project`."""

    def _make(
        yaml_text: str,
        files: Optional[Dict[str, str]] = None,
        provider: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> Project:
        (tmp_path / "pskit.yml").write_text(textwrap.dedent(yaml_text), "utf-8")
        app = tmp_path / "app"
        app.mkdir(exist_ok=True)
        (app / "__init__.py").write_text("", "utf-8")
        (app / "handlers.py").write_text(HANDLERS, "utf-8")
        for rel, content in (files or {}).items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(content), "utf-8")
        return Project.load(cwd=tmp_path, provider=provider, stage=stage)

    return _make


@pytest.fixture
def render() -> Callable[[Project], Dict[str, Any]]:
    """Package (without pip) and return the generated Terraform JSON as a dict."""

    def _render(project: Project) -> Dict[str, Any]:
        result = Deployer(project, echo=lambda _msg: None).package(skip_deps=True)
        return json.loads(result.tf_file.read_text("utf-8"))

    return _render


def full_config(provider: str, region: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> str:
    return FULL_CONFIG.format(
        provider=provider,
        region_line=f"region: {region}" if region else "",
        options=json.dumps(options or {}),
    )
