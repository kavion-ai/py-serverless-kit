"""Tracked workflow executions for the embedded engine.

An :class:`Executor` starts runs of the embedded engine (in the background or
in the caller's thread), gives each one an ``execution_id`` and keeps an
execution record up to date in a store while it runs::

    {"execution_id", "workflow", "status", "started_at", "stopped_at", "duration_ms",
     "current_state", "source", "console", "input", "output", "error", "cause", "history"}

``status`` is RUNNING, SUCCEEDED, FAILED, TIMED_OUT, CANCELLED or ABORTED (the
process stopped mid-run). :class:`FileExecutionStore` keeps one JSON file per
execution, so records survive a restart of the on-prem host;
:class:`MemoryExecutionStore` is for tests and short-lived processes.
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .workflow import (
    TIMEOUT_ERROR,
    TaskRunner,
    WorkflowCancelled,
    WorkflowEngine,
    WorkflowFailed,
    new_execution_id,
)

RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
TIMED_OUT = "TIMED_OUT"
CANCELLED = "CANCELLED"
ABORTED = "ABORTED"
STATUSES = (RUNNING, SUCCEEDED, FAILED, TIMED_OUT, CANCELLED, ABORTED)
SUMMARY_KEYS = (
    "execution_id",
    "workflow",
    "status",
    "started_at",
    "stopped_at",
    "duration_ms",
    "current_state",
    "source",
    "console",
)
MAX_HISTORY = 1000
_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")
_SAVE_INTERVAL = 0.25
NO_ENTRY: Any = object()  # Executor.start: no result of the first task was given


def entry_function(definition: Dict[str, Any]) -> Optional[str]:
    """The function of the first state when that state is a task, else ``None``."""
    first = (definition.get("states") or {}).get(definition.get("start_at")) or {}
    if first.get("type") != "task":
        return None
    return first.get("function") or None


def _seeded(runner: TaskRunner, function: Optional[str], result: Any) -> TaskRunner:
    """``runner`` whose first call of ``function`` (the first state: it already ran) returns ``result``."""
    pending = [True]

    def run(name: str, data: Any) -> Any:
        if pending and name == function:
            pending.clear()
            return result
        return runner(name, data)

    return run


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds")


def valid_id(execution_id: str) -> bool:
    return bool(_ID_RE.match(str(execution_id or "")))


def summary(record: Dict[str, Any]) -> Dict[str, Any]:
    return {key: record.get(key) for key in SUMMARY_KEYS}


def _jsonable(value: Any) -> Any:
    """Round-trip through JSON so stored records never hold live objects."""
    return json.loads(json.dumps(value, default=str))


def _matches(record: Dict[str, Any], workflow: Optional[str], status: Optional[str]) -> bool:
    if workflow and record.get("workflow") != workflow:
        return False
    if status and record.get("status") != status.upper():
        return False
    return True


def _page(items: List[Dict[str, Any]], limit: int, offset: int) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit or 20), 500))
    offset = max(0, int(offset or 0))
    return items[offset : offset + limit]


class MemoryExecutionStore:
    def __init__(self, retention: int = 200) -> None:
        self.retention = max(1, int(retention))
        self._items: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def save(self, record: Dict[str, Any]) -> None:
        with self._lock:
            self._items[record["execution_id"]] = _jsonable(record)
            self._prune()

    def get(self, execution_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            found = self._items.get(execution_id)
            return copy.deepcopy(found) if found is not None else None

    def list(
        self, workflow: Optional[str] = None, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            rows = [summary(r) for r in self._items.values() if _matches(r, workflow, status)]
        rows.sort(key=lambda r: str(r.get("execution_id")), reverse=True)
        return _page(rows, limit, offset), len(rows)

    def running(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(r) for r in self._items.values() if r.get("status") == RUNNING]

    def _prune(self) -> None:
        extra = len(self._items) - self.retention
        if extra <= 0:
            return
        done = sorted(eid for eid, r in self._items.items() if r.get("status") != RUNNING)
        for eid in done[:extra]:
            del self._items[eid]


class FileExecutionStore:
    """``<directory>/<execution_id>.json`` plus an in-memory index of summaries."""

    def __init__(self, directory: Path, retention: int = 500) -> None:
        self.directory = Path(directory)
        self.retention = max(1, int(retention))
        self._lock = threading.RLock()
        self._index: Dict[str, Dict[str, Any]] = {}
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in self.directory.glob("*.json"):
            if not valid_id(path.stem):
                continue
            try:
                record = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(record, dict) and record.get("execution_id") == path.stem:
                self._index[path.stem] = summary(record)

    def _path(self, execution_id: str) -> Path:
        if not valid_id(execution_id):
            raise ValueError(f"invalid execution id {execution_id!r}")
        return self.directory / f"{execution_id}.json"

    def save(self, record: Dict[str, Any]) -> None:
        data = json.dumps(record, default=str, separators=(",", ":")).encode("utf-8")
        path = self._path(record["execution_id"])
        with self._lock:
            tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
            self._index[record["execution_id"]] = summary(json.loads(data))
            self._prune()

    def get(self, execution_id: str) -> Optional[Dict[str, Any]]:
        if not valid_id(execution_id):
            return None
        try:
            with self._lock:
                raw = self._path(execution_id).read_text("utf-8")
        except OSError:
            return None
        try:
            record = json.loads(raw)
        except ValueError:
            return None
        return record if isinstance(record, dict) else None

    def list(
        self, workflow: Optional[str] = None, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            rows = [dict(r) for r in self._index.values() if _matches(r, workflow, status)]
        rows.sort(key=lambda r: str(r.get("execution_id")), reverse=True)
        return _page(rows, limit, offset), len(rows)

    def running(self) -> List[Dict[str, Any]]:
        with self._lock:
            ids = [eid for eid, r in self._index.items() if r.get("status") == RUNNING]
        return [r for r in (self.get(eid) for eid in ids) if r is not None]

    def _prune(self) -> None:
        extra = len(self._index) - self.retention
        if extra <= 0:
            return
        done = sorted(eid for eid, r in self._index.items() if r.get("status") != RUNNING)
        for eid in done[:extra]:
            self._index.pop(eid, None)
            try:
                self._path(eid).unlink()
            except OSError:
                pass


class _Run:
    """One execution in flight: the engine, its record, and throttled saving."""

    def __init__(self, store: Any, record: Dict[str, Any]) -> None:
        self.store = store
        self.record = record
        self.engine: Optional[WorkflowEngine] = None
        self.cancel = threading.Event()
        self._lock = threading.Lock()
        self._saved = 0.0
        self._timer: Optional[threading.Timer] = None
        self._done = False

    def on_change(self, engine: WorkflowEngine) -> None:
        with self._lock:
            if self._done:
                return
            self.record["current_state"] = engine.current_state
            self._set_history(engine.history)
            last = engine.history[-1] if engine.history else {}
            urgent = last.get("event") in ("caught", "retry", "fail")
            now = time.time()
            if urgent or now - self._saved >= _SAVE_INTERVAL:
                self._save_locked(now)
            elif self._timer is None:
                # Throttled: make sure the latest state is written soon even if nothing else happens
                # (e.g. the run just entered a long wait state).
                self._timer = threading.Timer(_SAVE_INTERVAL, self._flush)
                self._timer.daemon = True
                self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            self._timer = None
            if not self._done:
                self._save_locked(time.time())

    def _save_locked(self, now: float) -> None:
        self._saved = now
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self.store.save(self.record)

    def _set_history(self, history: List[Dict[str, Any]]) -> None:
        items = list(history)
        if len(items) > MAX_HISTORY:
            self.record["history_truncated"] = len(items) - MAX_HISTORY
            items = items[-MAX_HISTORY:]
        self.record["history"] = items

    def finish(self, status: str, **fields: Any) -> Dict[str, Any]:
        with self._lock:
            self._done = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self.record.update(fields)
            self.record["status"] = status
            self.record["stopped_at"] = _iso(time.time())
            self.record["duration_ms"] = round((time.perf_counter() - self.record["_t0"]) * 1000, 2)
            if self.engine is not None:
                self.record["current_state"] = self.engine.current_state
                self._set_history(self.engine.history)
            self.store.save(self.record)
            return self.record


class Executor:
    """Starts, tracks and cancels embedded workflow runs.

    ``workflows`` maps a workflow name to its bundle-manifest entry
    (``{"definition": {...}, "timeout": seconds?}``). ``task_runner`` calls one
    task function; it can be overridden per run.
    """

    def __init__(
        self,
        store: Any,
        workflows: Dict[str, Dict[str, Any]],
        task_runner: TaskRunner,
        *,
        max_workers: int = 8,
        sleep: Callable[[float], None] = time.sleep,
        source: str = "embedded",
    ) -> None:
        self.store = store
        self.workflows = dict(workflows or {})
        self.task_runner = task_runner
        self.sleep = sleep
        self.source = source
        self._runs: Dict[str, _Run] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max(1, int(max_workers)), thread_name_prefix="pskit-workflow")

    def knows(self, workflow: str) -> bool:
        return workflow in self.workflows

    # ------------------------------------------------------------------ start
    def start(
        self,
        workflow: str,
        data: Any = None,
        *,
        wait: bool = False,
        task_runner: Optional[TaskRunner] = None,
        entry_result: Any = NO_ENTRY,
    ) -> Dict[str, Any]:
        """Start a run. Returns the summary at once, or the finished record with ``wait=True``.

        ``entry_result``: the first state's function already ran (it was called on its own); the run uses this
        result for that state instead of calling the function again.
        """
        spec = self.workflows.get(workflow)
        if spec is None:
            known = ", ".join(sorted(self.workflows)) or "<none>"
            raise KeyError(f"unknown workflow {workflow!r}; known: {known}")
        started = time.time()
        execution_id = new_execution_id()
        record: Dict[str, Any] = {
            "execution_id": execution_id,
            "workflow": workflow,
            "status": RUNNING,
            "started_at": _iso(started),
            "stopped_at": None,
            "duration_ms": None,
            "current_state": None,
            "source": self.source,
            "console": None,
            "input": _jsonable(data),
            "output": None,
            "error": None,
            "cause": None,
            "history": [],
        }
        run = _Run(_PublicStore(self.store, self._public), record)
        record["_started"] = started
        record["_t0"] = time.perf_counter()
        with self._lock:
            self._runs[execution_id] = run
        self.store.save(self._public(record))
        runner = task_runner or self.task_runner
        if entry_result is not NO_ENTRY:
            runner = _seeded(runner, entry_function(spec.get("definition") or {}), entry_result)
        if wait:
            return self._public(self._execute(run, spec, data, runner))
        accepted = summary(record)  # before the worker can change it
        try:
            self._pool.submit(self._execute, run, spec, data, runner)
        except RuntimeError as exc:  # pool shut down
            self._execute_failed(run, exc)
            return summary(run.record)
        return accepted

    def _public(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in record.items() if not k.startswith("_")}

    def _execute(self, run: _Run, spec: Dict[str, Any], data: Any, runner: TaskRunner) -> Dict[str, Any]:
        engine = WorkflowEngine(spec["definition"], runner, sleep=self.sleep, cancel_event=run.cancel)
        timeout = spec.get("timeout")
        if timeout:
            engine.deadline = run.record["_started"] + float(timeout)
        run.engine = engine
        engine.on_change = run.on_change
        try:
            output = engine.run(data)
        except WorkflowCancelled:
            record = run.finish(CANCELLED, error="States.Cancelled", cause="execution was cancelled")
        except WorkflowFailed as exc:
            status = TIMED_OUT if exc.error == TIMEOUT_ERROR else FAILED
            record = run.finish(status, error=exc.error, cause=exc.cause)
        except Exception as exc:  # noqa: BLE001 - the record must always reach a final status
            record = run.finish(FAILED, error=type(exc).__name__, cause=str(exc))
        else:
            record = run.finish(SUCCEEDED, output=_jsonable(output))
        finally:
            with self._lock:
                self._runs.pop(run.record["execution_id"], None)
        return record

    def _execute_failed(self, run: _Run, exc: BaseException) -> None:
        run.finish(FAILED, error=type(exc).__name__, cause=str(exc))
        with self._lock:
            self._runs.pop(run.record["execution_id"], None)

    # ------------------------------------------------------------------ inspect / control
    def get(self, execution_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get(execution_id)

    def list(
        self, workflow: Optional[str] = None, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> Dict[str, Any]:
        items, total = self.store.list(workflow=workflow, status=status, limit=limit, offset=offset)
        return {"items": items, "total": total}

    def cancel(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Request cancellation. A run stops before its next state; the record says ``cancel_requested``."""
        record = self.store.get(execution_id)
        if record is None:
            return None
        if record.get("status") != RUNNING:
            return record
        with self._lock:
            run = self._runs.get(execution_id)
        if run is None:  # left over from a previous process
            record.update(status=ABORTED, stopped_at=_iso(time.time()), cause="no longer running in this process")
            self.store.save(record)
            return record
        run.cancel.set()
        record["cancel_requested"] = True
        with run._lock:
            run.record["cancel_requested"] = True
        return record

    def recover(self) -> int:
        """Mark runs left RUNNING by a previous process as ABORTED. Returns how many."""
        count = 0
        for record in self.store.running():
            with self._lock:
                live = record.get("execution_id") in self._runs
            if live:
                continue
            record.update(status=ABORTED, stopped_at=_iso(time.time()), error="States.Aborted", cause="host restarted")
            self.store.save(record)
            count += 1
        return count

    def result_body(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Response body of a synchronous run (keeps the historical ``workflow/status/output`` keys)."""
        body = {
            key: record.get(key)
            for key in ("execution_id", "workflow", "status", "output", "duration_ms", "started_at", "stopped_at")
        }
        if record.get("status") != SUCCEEDED:
            body.pop("output", None)
            body["error"] = record.get("error")
            body["cause"] = record.get("cause")
        return body

    def shutdown(self, wait: bool = False) -> None:
        with self._lock:
            runs = list(self._runs.values())
        for run in runs:
            run.cancel.set()
        self._pool.shutdown(wait=wait)


class _PublicStore:
    """Saves records without the executor's private ``_`` keys."""

    def __init__(self, store: Any, public: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self._store = store
        self._public = public

    def save(self, record: Dict[str, Any]) -> None:
        self._store.save(self._public(record))
