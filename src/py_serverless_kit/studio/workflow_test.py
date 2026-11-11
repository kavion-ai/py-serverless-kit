"""Test a workflow from the studio and follow it state by state.

``local`` runs the embedded engine in this process (the same path as
``pskit workflow run``) and reports each function, its output and the next
state as the run moves. ``deployed`` starts the workflow that is already
deployed and follows whatever that engine can report:

* on-premises host — live history (each state's output after a deploy of this runtime);
* AWS Step Functions — live history, including each state's output;
* Google Cloud Workflows — the current step and the final output;
* an embedded orchestrator on another cloud — the synchronous result, plus the
  step history when that deployment's runtime includes it;
* Azure Logic Apps (``engine: native``) — the final HTTP result. The run list
  stays in the Azure portal.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project import StudioError

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")
_SERVER = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,62}$")
_TERMINAL = ("SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "ABORTED")
_KEEP = 30


def _iso(when: float) -> str:
    return datetime.fromtimestamp(when, timezone.utc).isoformat(timespec="milliseconds")


def _functions(definition: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """State name → function, including states inside parallel branches and map iterators."""
    found: Dict[str, str] = {}

    def walk(machine: Any) -> None:
        if not isinstance(machine, dict):
            return
        for name, state in (machine.get("states") or {}).items():
            if not isinstance(state, dict):
                continue
            function = state.get("function")
            if function and name not in found:
                found[str(name)] = str(function)
            for branch in state.get("branches") or []:
                walk(branch)
            walk(state.get("iterator"))

    walk(definition or {})
    return found


def trace_steps(
    history: List[Dict[str, Any]], definition: Optional[Dict[str, Any]] = None, terminal: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Collapse history events into one row per state visit.

    A row says which function ran, the output it left (when the engine recorded
    one), and which state ran next. ``terminal`` closes a visit the history left
    open because the run failed or was cancelled between states.
    """
    functions = _functions(definition)
    steps: List[Dict[str, Any]] = []
    open_steps: List[int] = []

    def find_open(state: Any) -> Optional[int]:
        for index in reversed(open_steps):
            step = steps[index]
            if step["state"] == state or step.get("function") == state:
                return index
        return open_steps[-1] if open_steps else None

    for event in history or []:
        if not isinstance(event, dict):
            continue
        kind = event.get("event")
        state = event.get("state")
        if kind == "enter":
            step: Dict[str, Any] = {
                "state": state,
                "type": event.get("type"),
                "status": "done" if event.get("type") == "succeed" else "running",
                "output_known": False,
            }
            if event.get("type") == "fail":
                step["status"] = "running"
            function = event.get("function") or functions.get(str(state))
            if function:
                step["function"] = function
            if event.get("type") == "succeed":
                step["end"] = True
            steps.append(step)
            if step["status"] == "running":
                open_steps.append(len(steps) - 1)
            continue
        index = find_open(state)
        if index is None:
            continue
        step = steps[index]
        if kind == "retry":
            step["status"] = "retrying"
            if event.get("error"):
                step["error"] = event["error"]
            if event.get("attempt") is not None:
                step["attempt"] = event["attempt"]
            continue
        if kind == "exit":
            step["status"] = "done"
            if "output" in event:
                step["output"] = event["output"]
                step["output_known"] = True
            if event.get("output_truncated"):
                step["output_truncated"] = True
            if event.get("function"):
                step["function"] = event["function"]
            if event.get("duration_ms") is not None:
                step["duration_ms"] = event["duration_ms"]
            if "next" in event:
                step["next"] = event["next"]
            if event.get("end"):
                step["end"] = True
            open_steps = [i for i in open_steps if i != index]
            continue
        if kind == "caught":
            step["status"] = "caught"
            if event.get("error"):
                step["error"] = event["error"]
            if event.get("function"):
                step["function"] = event["function"]
            if event.get("next"):
                step["next"] = event["next"]
            open_steps = [i for i in open_steps if i != index]
            continue
        if kind == "fail":
            step["status"] = "failed"
            step["end"] = True
            if event.get("error"):
                step["error"] = event["error"]
            open_steps = [i for i in open_steps if i != index]
    if terminal == "SUCCEEDED":
        for step in steps:
            if step["status"] in ("running", "retrying"):
                step["status"] = "done"
                step["end"] = True
    elif terminal in ("FAILED", "TIMED_OUT", "CANCELLED", "ABORTED"):
        for step in steps:
            if step["status"] in ("running", "retrying"):
                step["status"] = "cancelled" if terminal in ("CANCELLED", "ABORTED") else "failed"
                step.setdefault("error", terminal)
    return steps


def _trace_kind(steps: List[Dict[str, Any]], fallback: str) -> str:
    if any(step.get("output_known") for step in steps):
        return "full"
    if steps:
        return "states"
    return fallback


def _load(root: Path, provider: str, stage: str) -> Any:
    from ..core.project import Project

    try:
        return Project.load(cwd=root, provider=provider or None, stage=stage or None)
    except Exception as exc:  # noqa: BLE001 - an invalid project is a message, not a crash
        raise StudioError(400, f"the saved pskit.yml does not load for {provider}/{stage}: {exc}") from None


def _provider_stage(root: Path, provider: Optional[str], stage: Optional[str]) -> Any:
    project = _load(root, provider or "", stage or "")
    return project


def describe(root: Path, provider: str, stage: str, workflow: str) -> Dict[str, Any]:
    """What a Test button can do for this workflow on this provider and stage."""
    if not _NAME.match(workflow or ""):
        raise StudioError(400, "invalid workflow name")
    project = _provider_stage(root, provider, stage)
    if workflow not in project.config.workflows:
        known = ", ".join(sorted(project.config.workflows)) or "none"
        raise StudioError(404, f"unknown workflow {workflow!r}; known: {known}")
    provider = project.config.provider.name
    stage = project.config.provider.stage
    local = {
        "id": "local",
        "label": "This machine",
        "available": True,
        "trace": "full",
        "note": (
            "Runs the embedded engine here, with your handlers. Nothing is deployed. "
            "Each function, its output and the next state show as the run moves. "
            "Wait states are skipped unless you turn on real waits."
        ),
    }
    return {"workflow": workflow, "provider": provider, "stage": stage, "targets": [local, _deployed(root, project, workflow)]}


def _deployed(root: Path, project: Any, workflow: str) -> Dict[str, Any]:
    from .system import deployment_record

    provider = project.config.provider.name
    stage = project.config.provider.stage
    label = f"Deployed {provider}/{stage}"
    base: Dict[str, Any] = {
        "id": "deployed",
        "label": label,
        "available": False,
        "trace": "result",
        "reason": f"{provider}/{stage} is not deployed from this folder yet.",
        "note": "Deploy this stage to run the workflow on it. Until then, test it on this machine.",
    }
    record = deployment_record(root, provider, stage)
    if not record or record.get("status") in ("local", "not deployed", "removed"):
        return base
    found = {w.get("name"): w for w in record.get("workflows") or []}
    wf = found.get(workflow)
    if not isinstance(wf, dict):
        base["reason"] = f"{workflow} is not in the last deployment of {provider}/{stage}. Save and deploy, then test it there."
        return base
    engine = wf.get("engine") or "embedded"
    console = wf.get("console")
    if provider == "onprem":
        from ..core.onprem_control import control_for

        if control_for(record, root) is None:
            base["reason"] = "the on-prem host address is unknown; deploy again"
            return base
        return {
            "id": "deployed",
            "label": "Deployed on-prem host",
            "available": True,
            "trace": "full",
            "engine": engine,
            "console": console,
            "note": (
                "Starts the workflow on the host and follows it live: the state it is in, "
                "each function, and what ran next. A host deployed with this version of pskit "
                "also stores each state's output. Cancel stops the run before the next state."
            ),
        }
    if provider == "aws" and engine == "native":
        return {
            "id": "deployed",
            "label": "AWS Step Functions",
            "available": True,
            "trace": "full",
            "engine": engine,
            "console": console,
            "note": (
                "Starts a Step Functions execution and follows it live: each state, its output, "
                "and the next state. Uses this machine's AWS credentials "
                "(pip install 'py-serverless-kit[aws]')."
            ),
        }
    if provider == "gcp" and engine == "native":
        return {
            "id": "deployed",
            "label": "Google Cloud Workflows",
            "available": True,
            "trace": "states",
            "engine": engine,
            "console": console,
            "note": (
                "Cloud Workflows reports the step that is running and the final output. "
                "It does not return each function's output. Test on this machine for that trace. "
                "Uses this machine's Google credentials (pip install 'py-serverless-kit[gcp]')."
            ),
        }
    if engine == "native":
        return {
            "id": "deployed",
            "label": label,
            "available": True,
            "trace": "result",
            "engine": engine,
            "console": console,
            "note": (
                "This native engine answers with the final result. The step-by-step run stays in "
                "the cloud console. Test on this machine to see each function, its output and the next state."
            ),
        }
    return {
        "id": "deployed",
        "label": label,
        "available": True,
        "trace": "result",
        "engine": engine,
        "console": console,
        "note": (
            "This cloud runs the workflow inside one function call. A deployment of this pskit "
            "version returns each state's output in that response. An older deployment returns "
            "only the final output. Test on this machine for a live trace without deploying."
        ),
    }


class _Run:
    def __init__(self, workflow: str, target: str, data: Any, definition: Dict[str, Any], hint: str) -> None:
        self.id = uuid.uuid4().hex[:16]
        self.workflow = workflow
        self.target = target
        self.input = data
        self.definition = definition
        self.hint = hint
        self.note = ""
        self.status = "RUNNING"
        self.history: List[Dict[str, Any]] = []
        self.output: Any = None
        self.error: Optional[str] = None
        self.cause: Optional[str] = None
        self.current_state: Optional[str] = None
        self.execution_id: Optional[str] = None
        self.console: Optional[str] = None
        self.poll_error: Optional[str] = None
        self.cancel_requested = False
        self.cancel_event = threading.Event()
        self.backend: Any = None
        self.started = time.time()
        self.stopped: Optional[float] = None
        self._lock = threading.Lock()

    def set_progress(self, current: Optional[str], history: List[Dict[str, Any]]) -> None:
        with self._lock:
            if self.status != "RUNNING":
                return
            self.current_state = current
            self.history = history

    def finish(self, status: str, **fields: Any) -> None:
        with self._lock:
            if self.status != "RUNNING":
                return
            self.status = status
            self.stopped = time.time()
            for key, value in fields.items():
                setattr(self, key, value)

    def apply_remote(self, record: Dict[str, Any]) -> None:
        with self._lock:
            status = str(record.get("status") or self.status)
            if record.get("history") is not None:
                self.history = [item for item in record.get("history") or [] if isinstance(item, dict)]
            if "output" in record:
                self.output = record.get("output")
            self.error = record.get("error")
            self.cause = record.get("cause")
            self.current_state = record.get("current_state")
            if record.get("execution_id"):
                self.execution_id = str(record["execution_id"])
            if record.get("console"):
                self.console = str(record["console"])
            self.status = status
            if status != "RUNNING":
                self.stopped = self.stopped or time.time()

    def public(self) -> Dict[str, Any]:
        with self._lock:
            status = self.status
            history = list(self.history)
            stopped = self.stopped
            started = self.started
            payload = {
                "run_id": self.id,
                "workflow": self.workflow,
                "target": self.target,
                "status": status,
                "execution_id": self.execution_id,
                "current_state": self.current_state,
                "started_at": _iso(started),
                "stopped_at": _iso(stopped) if stopped else None,
                "duration_ms": round(((stopped or time.time()) - started) * 1000, 2),
                "input": self.input,
                "output": self.output,
                "error": self.error,
                "cause": self.cause,
                "console": self.console,
                "note": self.note,
                "poll_error": self.poll_error,
                "cancel_requested": self.cancel_requested,
                "definition": self.definition,
                "hint": self.hint,
            }
        steps = trace_steps(history, payload.pop("definition"), status if status in _TERMINAL else None)
        hint = payload.pop("hint")
        trace = _trace_kind(steps, hint)
        if trace == "full":
            payload["note"] = ""
        payload["trace"] = trace
        payload["steps"] = steps
        return payload


class WorkflowRuns:
    """In-memory test runs for one studio process."""

    def __init__(self) -> None:
        self._runs: Dict[str, _Run] = {}
        self._lock = threading.Lock()

    def _remember(self, run: _Run, local: bool) -> None:
        with self._lock:
            if local and any(item.target == "local" and item.status == "RUNNING" for item in self._runs.values()):
                raise StudioError(409, "a workflow test is already running on this machine", code="busy")
            self._runs[run.id] = run
            if len(self._runs) <= _KEEP:
                return
            finished = [item for item in self._runs.values() if item.status != "RUNNING"]
            finished.sort(key=lambda item: item.started)
            for old in finished[: len(self._runs) - _KEEP]:
                self._runs.pop(old.id, None)

    def _get(self, run_id: str) -> _Run:
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise StudioError(404, "unknown workflow test")
        return run

    def start(self, root: Path, body: Dict[str, Any]) -> Dict[str, Any]:
        workflow = str(body.get("workflow") or "")
        if not _NAME.match(workflow):
            raise StudioError(400, "invalid workflow name")
        target = str(body.get("target") or "local")
        if target not in ("local", "deployed"):
            raise StudioError(400, "target must be local or deployed")
        server = body.get("server") or None
        if server is not None and not _SERVER.match(str(server)):
            raise StudioError(400, "invalid server name")
        project = _provider_stage(root, str(body.get("provider") or ""), str(body.get("stage") or ""))
        if workflow not in project.config.workflows:
            known = ", ".join(sorted(project.config.workflows)) or "none"
            raise StudioError(404, f"unknown workflow {workflow!r}; known: {known}")
        from ..workflows import definition_dict

        definition = definition_dict(project.config.workflows[workflow])
        data = body.get("input", body.get("data"))
        if data is None:
            data = {}
        info = _deployed(root, project, workflow) if target == "deployed" else {"trace": "full", "note": "", "console": None}
        if target == "deployed" and not info.get("available"):
            raise StudioError(400, str(info.get("reason") or "this stage is not deployed"))
        run = _Run(workflow, target, data, definition, str(info.get("trace") or "result"))
        run.note = str(info.get("note") or "")
        if info.get("console"):
            run.console = str(info["console"])
        self._remember(run, target == "local")
        try:
            if target == "local":
                thread = threading.Thread(
                    target=self._local, args=(run, project, workflow, data, bool(body.get("sleep"))), daemon=True
                )
                thread.start()
            else:
                self._start_deployed(run, project, workflow, data, str(server) if server else None)
        except StudioError:
            with self._lock:
                self._runs.pop(run.id, None)
            raise
        return run.public()

    def _local(self, run: _Run, project: Any, workflow: str, data: Any, sleep: bool) -> None:
        from ..local.runner import LocalRunner
        from ..runtime.workflow import TIMEOUT_ERROR, WorkflowCancelled, WorkflowFailed

        def on_change(engine: Any) -> None:
            run.set_progress(engine.current_state, list(engine.history))

        runner = LocalRunner(project)
        try:
            result = runner.run_workflow(
                workflow, data, sleep=sleep, on_change=on_change, cancel_event=run.cancel_event
            )
        except WorkflowCancelled as exc:
            run.finish("CANCELLED", error=exc.error, cause=exc.cause, history=list(exc.history))
        except WorkflowFailed as exc:
            status = "TIMED_OUT" if exc.error == TIMEOUT_ERROR else "FAILED"
            run.finish(status, error=exc.error, cause=exc.cause, history=list(exc.history))
        except Exception as exc:  # noqa: BLE001 - the panel shows the failure instead of a 500
            run.finish("FAILED", error=type(exc).__name__, cause=str(exc))
        else:
            run.finish("SUCCEEDED", output=result.get("output"), history=list(result.get("history") or []))
        finally:
            runner.close()

    def _start_deployed(self, run: _Run, project: Any, workflow: str, data: Any, server: Optional[str]) -> None:
        from ..core.deployer import Deployer
        from ..core.executions import ExecutionError, backend_for

        loaded = Deployer(project, echo=lambda _message: None).load_record()
        if not loaded:
            raise StudioError(400, "this stage is not deployed")
        try:
            backend = backend_for(loaded, project.root, server)
            run.backend = backend
            started = backend.start(workflow, data, wait=False)
        except (ExecutionError, KeyError, OSError, ValueError) as exc:
            run.finish("FAILED", error=type(exc).__name__, cause=str(exc))
            return
        if not isinstance(started, dict):
            run.finish("FAILED", error="States.Runtime", cause=f"unexpected response: {started!r}")
            return
        if started.get("execution_id"):
            run.execution_id = str(started["execution_id"])
        # A synchronous cloud run is already finished. A live engine (on-prem, Step
        # Functions, Cloud Workflows) stays RUNNING so the panel can poll it.
        if str(started.get("status") or "") == "RUNNING" and not getattr(backend, "supported", False):
            started = dict(started)
            started["status"] = "FAILED" if started.get("error") else "SUCCEEDED"
        run.apply_remote(started)

    def get(self, run_id: str) -> Dict[str, Any]:
        run = self._get(run_id)
        if run.target == "deployed" and run.status == "RUNNING" and run.backend is not None and run.execution_id:
            from ..core.executions import ExecutionError

            try:
                record = run.backend.get(run.execution_id, run.workflow)
            except (ExecutionError, OSError, ValueError, KeyError) as exc:
                run.poll_error = str(exc)
            else:
                run.poll_error = None
                if isinstance(record, dict):
                    run.apply_remote(record)
        return run.public()

    def cancel(self, run_id: str) -> Dict[str, Any]:
        run = self._get(run_id)
        if run.status != "RUNNING":
            return run.public()
        run.cancel_requested = True
        if run.target == "local":
            run.cancel_event.set()
            return run.public()
        if run.backend is None or not run.execution_id:
            run.finish("FAILED", error="States.Runtime", cause="this run cannot be cancelled")
            return run.public()
        from ..core.executions import ExecutionError

        try:
            record = run.backend.cancel(run.execution_id, run.workflow)
        except (ExecutionError, OSError, ValueError, KeyError) as exc:
            run.poll_error = str(exc)
            return run.public()
        if isinstance(record, dict):
            run.apply_remote(record)
        return run.public()
