"""Embedded workflow (state machine) engine.

The same definition the CLI compiles to AWS Step Functions (ASL) or Google
Cloud Workflows is interpreted here for:

* ``pskit workflow run --local`` - test workflows on your laptop;
* providers without a native orchestrator - the CLI deploys an extra
  *orchestrator* function whose handler is :func:`orchestrate`, and which calls
  task handlers in-process (they live in the same bundle).

Supported state types: task, choice, wait, pass, parallel, map, succeed, fail.
"""

from __future__ import annotations

import copy
import fnmatch
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .context import Context
from .event import Event, EventType
from .response import Response

TaskRunner = Callable[[str, Any], Any]
ALL_ERRORS = ("*", "States.ALL")


class WorkflowFailed(Exception):
    def __init__(self, error: str, cause: str = "", history: Optional[List[Dict[str, Any]]] = None) -> None:
        self.error = error
        self.cause = cause
        self.history = history or []
        super().__init__(f"{error}: {cause}" if cause else error)


class WorkflowCancelled(WorkflowFailed):
    """Raised between states once :meth:`WorkflowEngine.cancel` was requested."""

    def __init__(self, history: Optional[List[Dict[str, Any]]] = None) -> None:
        super().__init__("States.Cancelled", "execution was cancelled", history)


TIMEOUT_ERROR = "States.Timeout"


_ID_LOCK = threading.Lock()
_LAST_ID_MS = 0


def new_execution_id() -> str:
    """Time-sortable hex id: millisecond timestamp (strictly increasing in this process) + random suffix."""
    global _LAST_ID_MS
    with _ID_LOCK:
        _LAST_ID_MS = max(int(time.time() * 1000), _LAST_ID_MS + 1)
        stamp = _LAST_ID_MS
    return f"{stamp:013x}{uuid.uuid4().hex[:15]}"


# --------------------------------------------------------------------- JSON path


def _tokens(path: str) -> List[Any]:
    if path in ("$", "", None):
        return []
    if not path.startswith("$"):
        raise ValueError(f"JSON path must start with '$': {path!r}")
    tokens: List[Any] = []
    for part in path[1:].replace("[", ".[").split("."):
        if not part:
            continue
        if part.startswith("[") and part.endswith("]"):
            inner = part[1:-1].strip("'\"")
            tokens.append(int(inner) if inner.lstrip("-").isdigit() else inner)
        else:
            tokens.append(part)
    return tokens


_MISSING = object()  # "no default given" marker for get_path
_ABSENT = object()  # "path not present" value used by choice rules


def get_path(data: Any, path: str, default: Any = _MISSING) -> Any:
    current = data
    for tok in _tokens(path):
        try:
            current = current[tok]
        except (KeyError, IndexError, TypeError):
            if default is _MISSING:
                raise KeyError(path) from None
            return default
    return current


def set_path(data: Any, path: Optional[str], value: Any) -> Any:
    """Return ``data`` with ``value`` written at ``path`` (``$`` replaces; ``None`` discards)."""
    if path is None:
        return data
    tokens = _tokens(path)
    if not tokens:
        return value
    root = copy.deepcopy(data) if isinstance(data, (dict, list)) else {}
    current = root
    for tok in tokens[:-1]:
        if isinstance(current, dict):
            current = current.setdefault(tok, {})
        else:
            current = current[tok]
    current[tokens[-1]] = value
    return root


# --------------------------------------------------------------------- choice


_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    "equals": lambda a, b: a == b,
    "not_equals": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "in": lambda a, b: a in b,
    "contains": lambda a, b: a is not None and b in a,
    "matches": lambda a, b: isinstance(a, str) and fnmatch.fnmatchcase(a, b),
    "is_null": lambda a, b: (a is None) == bool(b),
    "is_present": lambda a, b: (a is not _ABSENT) == bool(b),
}
CHOICE_OPERATORS = tuple(_OPS)


def evaluate_rule(rule: Dict[str, Any], data: Any) -> bool:
    if "and" in rule:
        return all(evaluate_rule(r, data) for r in rule["and"])
    if "or" in rule:
        return any(evaluate_rule(r, data) for r in rule["or"])
    if "not" in rule:
        return not evaluate_rule(rule["not"], data)
    variable = rule.get("variable", "$")
    for op, fn in _OPS.items():
        if op in rule:
            value = get_path(data, variable, _ABSENT)
            if op == "is_present":
                return fn(value, rule[op])
            if value is _ABSENT:
                return False
            try:
                return bool(fn(value, rule[op]))
            except TypeError:
                return False
    raise ValueError(f"Choice rule has no operator (one of {', '.join(_OPS)}): {rule}")


# --------------------------------------------------------------------- engine


def _error_name(exc: BaseException) -> str:
    return getattr(exc, "error", None) or type(exc).__name__


def _matches(errors: List[str], name: str) -> bool:
    return any(e in ALL_ERRORS or e == name for e in (errors or ["*"]))


@dataclass
class WorkflowEngine:
    definition: Dict[str, Any]
    task_runner: TaskRunner
    sleep: Callable[[float], None] = time.sleep
    max_steps: int = 10_000
    history: List[Dict[str, Any]] = field(default_factory=list)
    # Execution tracking (all optional): called after every history entry, checked between states.
    on_change: Optional[Callable[[WorkflowEngine], None]] = None
    deadline: Optional[float] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    current_state: Optional[str] = None

    def run(self, data: Any = None) -> Any:
        return self._run_machine(self.definition, data)

    def cancel(self) -> None:
        """Stop before the next state starts (a running task is not interrupted)."""
        self.cancel_event.set()

    # ------------------------------------------------------------------
    def _record(self, state: str, kind: str, **extra: Any) -> None:
        self.history.append({"ts": datetime.now(timezone.utc).isoformat(), "state": state, "type": kind, **extra})
        if extra.get("event") == "enter":
            self.current_state = state
        if self.on_change is not None:
            try:
                self.on_change(self)
            except Exception:  # noqa: BLE001, S110 - tracking must never break the run
                pass

    def _checkpoint(self) -> None:
        if self.cancel_event.is_set():
            raise WorkflowCancelled(self.history)
        if self.deadline is not None and time.time() >= self.deadline:
            raise WorkflowFailed(TIMEOUT_ERROR, "workflow exceeded its timeout", self.history)

    def _pause(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self.sleep is time.sleep:
            # Real waits wake up early on cancel and never outlive the deadline.
            # A wait can end a moment early, so wait again until the end has really passed.
            end = time.time() + seconds if self.deadline is None else min(time.time() + seconds, self.deadline)
            while not self.cancel_event.is_set() and time.time() < end:
                self.cancel_event.wait(end - time.time())
        else:
            self.sleep(seconds)
        self._checkpoint()

    def _run_machine(self, machine: Dict[str, Any], data: Any) -> Any:
        states: Dict[str, Dict[str, Any]] = machine["states"]
        name: Optional[str] = machine["start_at"]
        steps = 0
        while name is not None:
            steps += 1
            if steps > self.max_steps:
                raise WorkflowFailed("States.Runtime", f"exceeded {self.max_steps} steps", self.history)
            self._checkpoint()
            state = states[name]
            kind = state["type"]
            self._record(name, kind, event="enter")
            if kind == "succeed":
                return data
            if kind == "fail":
                self._record(name, kind, event="fail", error=state.get("error", "States.Fail"))
                raise WorkflowFailed(state.get("error", "States.Fail"), state.get("cause", ""), self.history)
            if kind == "choice":
                name = self._choose(state, data)
                continue
            began = time.perf_counter()
            try:
                data = self._execute(state, data)
            except WorkflowFailed:
                raise
            except Exception as exc:  # noqa: BLE001 - mapped onto catch rules
                handler = next(
                    (c for c in state.get("catch") or [] if _matches(c.get("errors", ["*"]), _error_name(exc))),
                    None,
                )
                if handler is None:
                    raise WorkflowFailed(_error_name(exc), str(exc), self.history) from exc
                self._record(name, kind, event="caught", error=_error_name(exc))
                info = {"error": _error_name(exc), "cause": str(exc)}
                data = set_path(data, handler.get("result_path", "$.error"), info)
                name = handler["next"]
                continue
            self._record(name, kind, event="exit", duration_ms=round((time.perf_counter() - began) * 1000, 2))
            if state.get("end") or not state.get("next"):
                return data
            name = state["next"]
        return data

    def _choose(self, state: Dict[str, Any], data: Any) -> str:
        for rule in state.get("choices") or []:
            if evaluate_rule(rule, data):
                return rule["next"]
        if state.get("default"):
            return state["default"]
        raise WorkflowFailed("States.NoChoiceMatched", "no choice rule matched and no default", self.history)

    def _execute(self, state: Dict[str, Any], data: Any) -> Any:
        kind = state["type"]
        input_data = get_path(data, state["input_path"]) if state.get("input_path") else data
        if kind == "task":
            result = self._with_retry(state, lambda: self.task_runner(state["function"], input_data))
        elif kind == "pass":
            result = state.get("result", input_data)
        elif kind == "wait":
            if state.get("seconds_path"):
                seconds = float(get_path(data, state["seconds_path"]))
            else:
                seconds = float(state.get("seconds", 0))
            self._pause(seconds)
            result = input_data
        elif kind == "parallel":
            branches = state.get("branches") or []

            def run_branch(branch: Dict[str, Any]) -> Any:
                return self._run_machine(branch, copy.deepcopy(input_data))

            with ThreadPoolExecutor(max_workers=max(1, len(branches))) as pool:
                result = list(pool.map(run_branch, branches))
        elif kind == "map":
            items = get_path(input_data, state.get("items_path", "$"))
            if not isinstance(items, list):
                raise TypeError(f"map items_path did not resolve to a list: {type(items).__name__}")
            iterator = state["iterator"]
            workers = int(state.get("max_concurrency") or 0) or min(32, max(1, len(items)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                result = list(pool.map(lambda item: self._run_machine(iterator, item), items))
        else:
            raise WorkflowFailed("States.Runtime", f"unknown state type {kind!r}", self.history)
        return set_path(data, state.get("result_path", "$"), result)

    def _with_retry(self, state: Dict[str, Any], call: Callable[[], Any]) -> Any:
        attempts: Dict[int, int] = {}
        while True:
            try:
                return call()
            except Exception as exc:  # noqa: BLE001
                name = _error_name(exc)
                rules = state.get("retry") or []
                # Like ASL, the first retrier whose errors match is the one used.
                idx = next((i for i, r in enumerate(rules) if _matches(r.get("errors", ["*"]), name)), None)
                if idx is None:
                    raise
                rule = rules[idx]
                count = attempts.get(idx, 0)
                if count >= int(rule.get("max_attempts", 3)):
                    raise
                attempts[idx] = count + 1
                delay = float(rule.get("interval_seconds", 1)) * float(rule.get("backoff_rate", 2.0)) ** count
                self._record(state.get("function", "?"), "task", event="retry", attempt=count + 1, error=name)
                cap = rule.get("max_delay_seconds")
                self._pause(min(delay, float(300 if cap is None else cap)))


def in_process_runner(provider: str = "local") -> TaskRunner:
    """Task runner that invokes handlers from the current bundle via the dispatcher."""
    from .dispatch import execute

    def run(function: str, data: Any) -> Any:
        from .invoke import NOT_ROUTED, route

        event = Event(type=EventType.WORKFLOW, provider=provider, function=function, data=data)
        routed = route(function, event)  # a step on another server (on-prem placement)
        if routed is not NOT_ROUTED:
            return routed
        result = execute(event, Context(function=function, provider=provider), function)
        return result

    return run


_EXECUTOR: Any = None


def install_executor(executor: Any) -> None:
    """Route orchestrator calls through an :class:`~.executions.Executor` (the on-prem host does)."""
    global _EXECUTOR
    _EXECUTOR = executor


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def wants_wait(event: Event) -> bool:
    """HTTP callers opt into a synchronous run with ``?wait=true`` or ``Prefer: wait``."""
    if event.http is None:
        return True
    prefer = (event.http.headers.get("prefer") or "").lower()
    return _truthy(event.http.query.get("wait")) or _truthy(event.http.headers.get("x-pskit-wait")) or "wait" in prefer


def orchestrate(event: Event, context: Context) -> Any:
    """Handler of the auto-generated ``<workflow>-orchestrator`` function.

    Every run gets an ``execution_id``. Inside the on-prem host (an executor is
    installed) an HTTP start returns ``202`` at once and the run is tracked in the
    execution store; ``?wait=true`` waits for the result. On cloud functions the
    run is synchronous and the response carries the id.
    """
    from .manifest import load_manifest

    manifest = load_manifest()
    target = next(
        (
            (name, wf)
            for name, wf in manifest.workflows.items()
            if wf.get("orchestrator") == (event.function or context.function)
        ),
        None,
    )
    if target is None:
        raise LookupError(f"No workflow is orchestrated by function {event.function!r}")
    name, wf = target
    if event.http is not None:
        data = event.http.json(default=None) if event.http.body else dict(event.http.query)
    else:
        data = event.data
    executor = _EXECUTOR
    if executor is not None and executor.knows(name):
        if not wants_wait(event):
            return Response.json(executor.start(name, data), 202)
        # Synchronous: tasks run in this thread's dispatcher (the caller may hold the host's env lock).
        record = executor.start(name, data, wait=True, task_runner=in_process_runner(event.provider))
        result = executor.result_body(record)
        if record.get("status") != "SUCCEEDED":
            context.logger.error("workflow failed", extra={k: result.get(k) for k in ("workflow", "error", "cause")})
            if event.http is not None:
                return Response.json(result, 500)
            raise WorkflowFailed(str(record.get("error") or "States.Runtime"), str(record.get("cause") or ""))
        return result
    execution_id = new_execution_id()
    engine = WorkflowEngine(wf["definition"], in_process_runner(event.provider))
    timeout = wf.get("timeout")
    if timeout:
        engine.deadline = time.time() + float(timeout)
    started = time.perf_counter()
    try:
        output = engine.run(data)
    except WorkflowFailed as exc:
        failure = {
            "execution_id": execution_id,
            "workflow": name,
            "status": "TIMED_OUT" if exc.error == TIMEOUT_ERROR else "FAILED",
            "error": exc.error,
            "cause": exc.cause,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        context.logger.error("workflow failed", extra=failure)
        if event.http is not None:
            return Response.json(failure, 500)
        raise
    body: Dict[str, Any] = {
        "execution_id": execution_id,
        "workflow": name,
        "status": "SUCCEEDED",
        "output": output,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    return body
