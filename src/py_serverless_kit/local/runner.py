"""Run handlers and workflows on your machine, exactly as the cloud adapters would."""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import parse_qsl, urlsplit

from ..core.project import Project
from ..runtime import dispatch
from ..runtime.context import Context
from ..runtime.event import Event, EventType, Headers, HttpRequest, Record
from ..runtime.manifest import BundleManifest, set_manifest
from ..runtime.workflow import WorkflowEngine, in_process_runner
from ..workflows import definition_dict

LOCAL_NODE_DIR = "local-node"


def load_dotenv(path: Path) -> Dict[str, str]:
    """Minimal ``.env`` parser (KEY=VALUE, comments, optional quotes)."""
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


class LocalRunner:
    """Executes a project's functions in-process with the real dispatcher."""

    def __init__(self, project: Project, env_file: Optional[str] = ".env") -> None:
        self.project = project
        self.source = (project.root / project.config.package.source).resolve()
        self.env_file = project.root / env_file if env_file else None
        manifest = project.bundle_manifest()
        # Every workflow is runnable locally, whatever engine the cloud uses.
        manifest["workflows"] = {
            name: {"orchestrator": f"{name}-orchestrator", "definition": definition_dict(wf)}
            for name, wf in project.config.workflows.items()
        }
        self.manifest_dict = manifest
        self.manifest = BundleManifest.from_dict(manifest)
        self.language = project.config.language
        # Node.js: one worker per function (each gets its own environment), rebuilt on reload.
        self._workers: Dict[str, Any] = {}
        self._node_root: Optional[Path] = None
        if self.language == "node":
            return
        self._purge_foreign_modules()

    def _purge_foreign_modules(self) -> None:
        """Drop cached modules that shadow this project's packages (e.g. another
        project's ``app.handlers`` imported earlier in the same process)."""
        try:
            top_level = {p.stem if p.suffix == ".py" else p.name for p in self.source.iterdir()}
        except OSError:
            return
        src = str(self.source)
        for name, module in list(sys.modules.items()):
            if name.split(".")[0] not in top_level:
                continue
            path = getattr(module, "__file__", None) or ""
            if not path.startswith(src):
                del sys.modules[name]
        dispatch._HANDLERS.clear()

    # ---------------------------------------------------------------- env
    def function_env(self, function: Optional[str] = None) -> Dict[str, str]:
        """The environment a function sees locally (provider + bindings + function + ``.env``)."""
        cfg = self.project.config
        env: Dict[str, str] = {
            "PSKIT_PROVIDER": "local",
            "PSKIT_SERVICE": cfg.service,
            "PSKIT_STAGE": cfg.provider.stage,
            "PSKIT_REGION": "local",
            "PSKIT_LOG_FORMAT": os.environ.get("PSKIT_LOG_FORMAT", "text"),
        }
        env.update(cfg.provider.environment)
        if function and function in cfg.functions:
            env.update(cfg.binding_environment(function))
            env.update(cfg.provider.environment)
            env.update(cfg.functions[function].environment)
            env["PSKIT_FUNCTION"] = function
            env["PSKIT_HANDLER"] = cfg.functions[function].handler
        if self.env_file is not None:
            env.update(load_dotenv(self.env_file))
        return env

    @contextmanager
    def environment(self, function: Optional[str] = None) -> Iterator[None]:
        env = self.function_env(function)
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        added_path = str(self.source)
        sys.path.insert(0, added_path)
        set_manifest(self.manifest)
        try:
            yield
        finally:
            for key, old in saved.items():
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old
            if added_path in sys.path:
                sys.path.remove(added_path)

    # ---------------------------------------------------------------- invoke
    def invoke(self, function: str, event: Event) -> Any:
        if function not in self.project.config.functions:
            known = ", ".join(sorted(self.project.config.functions))
            raise KeyError(f"unknown function {function!r}; known: {known}")
        event.function = function
        event.provider = "local"
        if self.language == "node":
            return self._invoke_node(function, event)
        with self.environment(function):
            return dispatch.execute(event, Context(function=function, provider="local"), function)

    # ---------------------------------------------------------------- Node.js
    def node_root(self) -> Path:
        """Build (once per reload) ``.pskit/local-node``: sources (TypeScript compiled), runtime, manifest."""
        if self._node_root is None:
            from ..packaging import node
            from ..packaging.builder import BuildError

            root = self.project.root / ".pskit" / LOCAL_NODE_DIR
            if root.exists():
                shutil.rmtree(root)
            root.mkdir(parents=True)
            try:
                node.prepare_tree(self.project, root, self.manifest_dict, log=lambda _m: None, node_modules_runtime=True)
            except node.NodeBuildError as exc:
                raise BuildError(str(exc)) from None
            self._node_root = root
        return self._node_root

    def _worker(self, function: str) -> Any:
        worker = self._workers.get(function)
        if worker is None:
            from ..packaging.node import node_exe
            from ..runtime.node_worker import NodeWorker

            root = self.node_root()
            env = dict(os.environ)
            env.update(self.function_env(function))
            env["PSKIT_BUNDLE_ROOT"] = str(root)
            worker = NodeWorker(root, env=env, node=node_exe())
            self._workers[function] = worker
        return worker

    def _invoke_node(self, function: str, event: Event) -> Any:
        """Run a Node.js function in its worker: a Response, BatchResult or value; handler errors raise
        :class:`~py_serverless_kit.runtime.node_worker.NodeFunctionError` (``.error`` = JS error name)."""
        timeout = float(self.project.config.timeout_of(self.project.config.functions[function]))
        ctx = Context(function=function, provider="local", deadline=time.time() + timeout)
        return self._worker(function).execute(function, event, ctx, timeout + 5)

    def close(self) -> None:
        """Stop Node.js workers (no-op for Python services)."""
        for worker in self._workers.values():
            try:
                worker.close()
            except Exception:  # noqa: BLE001, S110 - best effort on shutdown
                pass
        self._workers.clear()

    def run_workflow(self, name: str, data: Any, *, sleep: bool = False) -> Dict[str, Any]:
        wf = self.project.config.workflows.get(name)
        if wf is None:
            known = ", ".join(sorted(self.project.config.workflows)) or "<none>"
            raise KeyError(f"unknown workflow {name!r}; known: {known}")
        if self.language == "node":

            def task(function: str, payload: Any) -> Any:
                return self.invoke(function, Event(type=EventType.WORKFLOW, function=function, data=payload))

            engine = WorkflowEngine(definition_dict(wf), task, sleep=time.sleep if sleep else (lambda _seconds: None))
            return {"output": engine.run(data), "history": engine.history}
        engine = WorkflowEngine(
            definition_dict(wf),
            in_process_runner("local"),
            sleep=time.sleep if sleep else (lambda _seconds: None),
        )
        with self.environment():
            output = engine.run(data)
        return {"output": output, "history": engine.history}

    def reload(self) -> None:
        """Forget imported user modules so edited code is picked up (dev server)."""
        if self.language == "node":
            self.close()
            self._node_root = None
            return
        src = str(self.source)
        for name, module in list(sys.modules.items()):
            path = getattr(module, "__file__", None) or ""
            if path.startswith(src) and "py_serverless_kit" not in path:
                del sys.modules[name]
        dispatch._HANDLERS.clear()


# -------------------------------------------------------------------- event builders


def http_event(
    method: str = "GET",
    path: str = "/",
    body: Any = None,
    headers: Optional[Dict[str, str]] = None,
    query: Optional[Dict[str, str]] = None,
) -> Event:
    parts = urlsplit(path)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.update(query or {})
    hdrs = dict(headers or {})
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
        hdrs.setdefault("content-type", "application/json")
    return Event(
        type=EventType.HTTP,
        http=HttpRequest(
            method=method,
            path=parts.path or "/",
            headers=Headers(hdrs),
            query=q,
            body=body or b"",
            source_ip="127.0.0.1",
        ),
    )


def build_event(kind: str, data: Any = None, **http: Any) -> Event:
    """Create a synthetic event for ``pskit invoke``."""
    if kind == EventType.HTTP:
        return http_event(
            http.get("method", "GET"), http.get("path", "/"), data, http.get("headers"), http.get("query")
        )
    if kind in (EventType.QUEUE, EventType.TOPIC):
        items: List[Any] = data if isinstance(data, list) else [data]
        records = [
            Record(id=f"local-{i}", body=json.dumps(item) if isinstance(item, (dict, list)) else item, source="local")
            for i, item in enumerate(items)
        ]
        return Event(type=kind, records=records, source="local")
    if kind == EventType.STORAGE:
        items = data if isinstance(data, list) else [data or {}]
        records = [
            Record(
                id=f"local-{i}",
                bucket=(item or {}).get("bucket", "local-bucket"),
                key=(item or {}).get("key", "example.txt"),
                size=(item or {}).get("size", 0),
                action=(item or {}).get("action", "created"),
                source="local",
            )
            for i, item in enumerate(items)
        ]
        return Event(type=kind, records=records, source="local")
    if kind == EventType.SMTP:
        # A test mail ({"from", "to", "subject", "text", "attachments": [...]}) becomes the event the SMTP
        # service sends; a full event (with "Records") is passed as it is.
        from ..core.onprem_smtp import test_event

        return Event(type=kind, data=test_event(data, "local"), source="local")
    if kind not in EventType.ALL:
        raise ValueError(f"unknown event type {kind!r}; one of {', '.join(EventType.ALL)}")
    return Event(type=kind, data=data)


def parse_data(value: Optional[str]) -> Any:
    """``--data '{"a":1}'`` or ``--data @event.json`` (or plain text)."""
    if value is None:
        return None
    if value.startswith("@"):
        value = Path(value[1:]).read_text("utf-8")
    try:
        return json.loads(value)
    except ValueError:
        return value


def response_to_dict(result: Any) -> Any:
    from ..runtime.batch import BatchResult
    from ..runtime.response import Response

    if isinstance(result, BatchResult):
        return {"batchItemFailures": [{"itemIdentifier": rid} for rid in result.failed]}
    if isinstance(result, Response):
        status, headers, raw = result.render()
        try:
            body: Any = json.loads(raw) if raw else None
        except ValueError:
            try:
                body = raw.decode("utf-8")
            except UnicodeDecodeError:
                body = {"base64": base64.b64encode(raw).decode("ascii")}
        return {"status": status, "headers": headers, "body": body}
    return result
