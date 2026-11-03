"""Drive Node.js functions from Python through ``pskit_runtime/worker.js``.

The on-premises host and the local tooling (``pskit dev`` / ``pskit invoke``)
use one long-lived ``node`` process per bundle and talk JSON lines to it
(protocol in ``deploy_docs/NODE_RUNTIME.md``)::

    worker = NodeWorker(bundle_root)
    reply = worker.call("hello", event, context, timeout=30)   # raw protocol dict
    result = worker.execute("hello", event, context)           # Response / BatchResult / value

Requests may be sent from many threads at once; replies are matched by id. A
worker that died is restarted on the next call. Everything the functions log
(stderr) is passed to ``on_log`` line by line.
"""

from __future__ import annotations

import base64
import itertools
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import IO, Any, Callable, Dict, Optional, Union

from .batch import BatchResult
from .context import Context
from .event import Event
from .response import Response

RUNTIME_DIR = "pskit_runtime"
_PACKAGED = Path(__file__).resolve().parents[1] / "runtime_js"


class NodeWorkerError(RuntimeError):
    """The worker could not be started, died, or broke the protocol."""


class NodeWorkerTimeout(NodeWorkerError, TimeoutError):
    """No reply within the timeout."""


class NodeFunctionError(Exception):
    """The Node.js handler threw. ``error`` holds the JS error name (used by workflow retry/catch rules)."""

    def __init__(self, error_type: str, message: str, stack: str = "") -> None:
        super().__init__(message)
        self.error = error_type or "Error"
        self.message = message
        self.stack = stack

    def __str__(self) -> str:
        return self.message


def _default_log(line: str) -> None:
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


class _Pending:
    __slots__ = ("done", "reply")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.reply: Optional[Dict[str, Any]] = None


class NodeWorker:
    def __init__(
        self,
        bundle_root: Union[str, Path],
        env: Optional[Dict[str, str]] = None,
        node: str = "node",
        worker: Optional[Union[str, Path]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.bundle_root = Path(bundle_root).resolve()
        self.env = dict(env or {})
        self.node = node
        if worker is None:
            bundled = self.bundle_root / RUNTIME_DIR / "worker.js"
            worker = bundled if bundled.is_file() else _PACKAGED / "worker.js"
        self.worker = Path(worker).resolve()
        self.on_log = on_log or _default_log
        self._proc: Optional[subprocess.Popen] = None
        self._pending: Dict[str, _Pending] = {}
        self._lock = threading.Lock()  # start / restart / pending table
        self._write_lock = threading.Lock()
        self._ids = itertools.count(1)
        self._closed = False

    # ------------------------------------------------------------------ process
    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc is not None else None

    def start(self) -> None:
        with self._lock:
            self._ensure_started()

    def _ensure_started(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        exe = shutil.which(self.node) or (self.node if Path(self.node).is_file() else None)
        if not exe:
            raise NodeWorkerError(
                f"Node.js ({self.node!r}) was not found on PATH; install Node.js 18+ from https://nodejs.org/"
            )
        if not self.worker.is_file():
            raise NodeWorkerError(f"the Node.js worker {self.worker} does not exist")
        env = dict(os.environ)
        env.update(self.env)
        env["PSKIT_BUNDLE_ROOT"] = str(self.bundle_root)
        try:
            proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                [exe, str(self.worker)],
                cwd=str(self.bundle_root),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise NodeWorkerError(f"could not start {exe}: {exc}") from exc
        self._proc = proc
        threading.Thread(target=self._read_replies, args=(proc,), name="pskit-node-out", daemon=True).start()
        threading.Thread(target=self._read_logs, args=(proc,), name="pskit-node-err", daemon=True).start()
        return proc

    def _read_replies(self, proc: subprocess.Popen) -> None:
        stream: IO[bytes] = proc.stdout  # type: ignore[assignment]
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                reply = json.loads(line)
            except ValueError:
                self.on_log(f"[node worker] unexpected output: {line[:500]}")
                continue
            if not isinstance(reply, dict):
                continue
            with self._lock:
                pending = self._pending.pop(str(reply.get("id")), None)
            if pending is not None:
                pending.reply = reply
                pending.done.set()
        code = proc.wait()
        with self._lock:
            # Only fail requests sent to this process (a restart may already own new ones).
            if self._proc is proc:
                orphans = list(self._pending.items())
                self._pending.clear()
            else:
                orphans = []
        for _, pending in orphans:
            pending.reply = {
                "ok": False,
                "error": {"type": "NodeWorkerError", "message": f"node worker exited with code {code}", "stack": ""},
                "_worker_died": True,
            }
            pending.done.set()

    def _read_logs(self, proc: subprocess.Popen) -> None:
        stream: IO[bytes] = proc.stderr  # type: ignore[assignment]
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line:
                try:
                    self.on_log(line)
                except Exception:  # noqa: BLE001, S110 - a log sink must never stop the reader
                    pass

    # ------------------------------------------------------------------ requests
    def _send(self, message: Dict[str, Any], timeout: Optional[float]) -> Dict[str, Any]:
        if self._closed:
            raise NodeWorkerError("the node worker was closed")
        rid = f"r{next(self._ids)}"
        message = dict(message, id=rid)
        line = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        pending = _Pending()
        for attempt in (1, 2):
            with self._lock:
                proc = self._ensure_started()
                self._pending[rid] = pending
            try:
                with self._write_lock:
                    proc.stdin.write(line)  # type: ignore[union-attr]
                    proc.stdin.flush()  # type: ignore[union-attr]
                break
            except (BrokenPipeError, OSError, ValueError) as exc:
                with self._lock:
                    self._pending.pop(rid, None)
                if attempt == 2:
                    raise NodeWorkerError(f"could not send to the node worker: {exc}") from exc
                try:
                    proc.wait(2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if not pending.done.wait(timeout):
            with self._lock:
                self._pending.pop(rid, None)
            raise NodeWorkerTimeout(f"no reply from the node worker within {timeout} s")
        assert pending.reply is not None
        return pending.reply

    def call(
        self,
        function: str,
        event: Event,
        context: Optional[Context] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run ``function`` and return the raw protocol reply (``ok``, ``kind``, ...)."""
        ctx = context or Context(function=function, provider=event.provider)
        message = {
            "function": function,
            "event": event.to_wire(),
            "context": {
                "request_id": ctx.request_id,
                "function": ctx.function or function,
                "provider": ctx.provider or event.provider,
                "deadline": ctx.deadline,
                "memory_mb": ctx.memory_mb,
            },
        }
        return self._send(message, timeout)

    def execute(
        self,
        function: str,
        event: Event,
        context: Optional[Context] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Like the Python dispatcher: a Response (http), BatchResult (batch) or the value.

        A handler error raises :class:`NodeFunctionError`; a broken worker :class:`NodeWorkerError`.
        """
        return decode_reply(self.call(function, event, context, timeout))

    def ping(self, timeout: float = 10.0) -> bool:
        return self._send({"op": "ping"}, timeout).get("kind") == "pong"

    def close(self, timeout: float = 5.0) -> None:
        """Let in-flight requests finish (stdin EOF), then stop the process."""
        self._closed = True
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)

    def __enter__(self) -> NodeWorker:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def decode_reply(reply: Dict[str, Any]) -> Any:
    """Protocol reply -> Response / BatchResult / value; errors raise."""
    if not reply.get("ok"):
        err = reply.get("error") or {}
        if reply.get("_worker_died"):
            raise NodeWorkerError(str(err.get("message") or "node worker exited"))
        raise NodeFunctionError(
            str(err.get("type") or "Error"), str(err.get("message") or ""), str(err.get("stack") or "")
        )
    kind = reply.get("kind")
    if kind == "http":
        resp = Response(
            int(reply.get("status") or 200),
            base64.b64decode(reply.get("body_b64") or ""),
            {str(k): str(v) for k, v in (reply.get("headers") or {}).items()},
        )
        resp.cookies = [str(c) for c in reply.get("cookies") or []]
        return resp
    if kind == "batch":
        return BatchResult(failed=[str(i) for i in reply.get("failed") or []])
    if kind == "value":
        return reply.get("value")
    return None


__all__ = ["NodeFunctionError", "NodeWorker", "NodeWorkerError", "NodeWorkerTimeout", "decode_reply"]
