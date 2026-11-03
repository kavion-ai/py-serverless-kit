"""Log capture for the on-premises host.

Everything the host and its handlers emit lands in one :class:`LogBuffer`:

* ``logging`` records (``context.logger`` and any ``logging.getLogger(...)``),
* ``print`` / ``sys.stdout`` / ``sys.stderr`` output, line by line,
* one ``invocation`` entry per handler call (function, event type, status, duration),
* host notes (failed schedules, queue errors, ...).

Entries carry the function and request id of the invocation that produced them
(tracked per thread), get a monotonically increasing ``seq``, are kept in a ring
buffer for ``GET /__pskit/logs`` and appended to a size-rotated JSON-lines file
so they survive restarts.
"""

from __future__ import annotations

import collections
import io
import json
import logging
import os
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional

LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
SOURCES = ("function", "host", "stdout", "stderr", "invocation")
_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}
_MAX_MESSAGE = 16 * 1024
HOST_STREAM = "__host__"  # entries not tied to a function
_STATE = threading.local()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _level_no(level: Optional[str]) -> int:
    if not level:
        return 0
    text = str(level).upper()
    if text == "WARN":
        text = "WARNING"
    return LEVELS.get(text, 0)


@contextmanager
def invocation(function: str, request_id: str) -> Iterator[None]:
    """Tag every entry written by this thread with ``function`` / ``request_id``."""
    previous = getattr(_STATE, "current", None)
    _STATE.current = (function, request_id)
    try:
        yield
    finally:
        _STATE.current = previous


def current() -> Optional[tuple]:
    return getattr(_STATE, "current", None)


class LogBuffer:
    def __init__(
        self,
        path: Optional[Path] = None,
        capacity: int = 5000,
        max_bytes: int = 10 * 1024 * 1024,
        backups: int = 3,
    ) -> None:
        self.path = Path(path) if path else None
        self.capacity = max(100, int(capacity))
        self.max_bytes = max(64 * 1024, int(max_bytes))
        self.backups = max(0, int(backups))
        self._entries: Deque[Dict[str, Any]] = collections.deque(maxlen=self.capacity)
        self._lock = threading.Lock()
        self._seq = 0
        self._file: Optional[io.BufferedWriter] = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._restore()

    # ------------------------------------------------------------------ write
    def append(
        self,
        level: str,
        source: str,
        message: str,
        function: Optional[str] = None,
        request_id: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
    ) -> int:
        tagged = current()
        if tagged is not None:
            function = function or tagged[0]
            request_id = request_id or tagged[1]
        text = str(message)
        if len(text) > _MAX_MESSAGE:
            text = text[:_MAX_MESSAGE] + f"... [{len(text) - _MAX_MESSAGE} more characters]"
        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "ts": _now(),
                "level": str(level).upper() if str(level).upper() in LEVELS else "INFO",
                "source": source if source in SOURCES else "host",
                "function": function,
                "request_id": request_id,
                "message": text,
                "fields": _safe_fields(fields),
            }
            self._entries.append(entry)
            self._persist(entry)
            return self._seq

    def _persist(self, entry: Dict[str, Any]) -> None:
        if self.path is None:
            return
        try:
            line = (json.dumps(entry, default=str, separators=(",", ":")) + "\n").encode("utf-8")
            if self._file is None:
                self._file = open(self.path, "ab")  # noqa: SIM115 - kept open for the process lifetime
            if self._file.tell() + len(line) > self.max_bytes:
                self._rotate()
            assert self._file is not None
            self._file.write(line)
            self._file.flush()
        except OSError:
            # A full disk must not take the host down; the ring buffer still works.
            self._file = None

    def _rotate(self) -> None:
        assert self.path is not None
        if self._file is not None:
            self._file.close()
            self._file = None
        for index in range(self.backups, 0, -1):
            older = self.path.with_name(f"{self.path.name}.{index}")
            newer = self.path.with_name(f"{self.path.name}.{index - 1}") if index > 1 else self.path
            if newer.exists():
                if index == self.backups and older.exists():
                    older.unlink()
                os.replace(newer, older)
        if self.backups == 0 and self.path.exists():
            self.path.unlink()
        self._file = open(self.path, "ab")  # noqa: SIM115

    def _restore(self) -> None:
        assert self.path is not None
        lines: List[bytes] = []
        for candidate in (self.path.with_name(self.path.name + ".1"), self.path):
            try:
                lines.extend(_tail_lines(candidate, self.capacity))
            except OSError:
                continue
        for raw in lines[-self.capacity :]:
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            if isinstance(entry, dict) and isinstance(entry.get("seq"), int):
                self._entries.append(entry)
                self._seq = max(self._seq, entry["seq"])

    def clear(self, function: Optional[str] = None) -> int:
        """Drop entries (all, those of ``function``, or host entries for ``__host__``) from memory and disk.

        ``seq`` keeps counting up, so live tails simply see no new entries.
        """
        with self._lock:
            before = len(self._entries)
            if function == HOST_STREAM:
                kept = [e for e in self._entries if e.get("function")]
            elif function:
                kept = [e for e in self._entries if e.get("function") != function]
            else:
                kept = []
            self._entries.clear()
            self._entries.extend(kept)
            removed = before - len(kept)
            if self.path is not None:
                if self._file is not None:
                    self._file.close()
                    self._file = None
                for index in range(1, self.backups + 1):
                    older = self.path.with_name(f"{self.path.name}.{index}")
                    try:
                        if older.exists():
                            older.unlink()
                    except OSError:
                        pass
                try:
                    with open(self.path, "wb") as fh:
                        for entry in kept:
                            fh.write((json.dumps(entry, default=str, separators=(",", ":")) + "\n").encode("utf-8"))
                except OSError:
                    pass
            return removed

    def functions(self) -> List[Dict[str, Any]]:
        """One summary per function (``None`` = host) found in the buffer."""
        with self._lock:
            snapshot = list(self._entries)
        out: Dict[Any, Dict[str, Any]] = {}
        for entry in snapshot:
            key = entry.get("function")
            item = out.get(key)
            if item is None:
                item = out[key] = {"function": key, "first": entry.get("ts"), "last": entry.get("ts"), "count": 0}
            item["last"] = entry.get("ts")
            item["count"] += 1
        return sorted(out.values(), key=lambda i: (i["function"] is None, str(i["function"] or "")))

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None

    # ------------------------------------------------------------------ read
    @property
    def last_seq(self) -> int:
        return self._seq

    def query(
        self,
        since: int = 0,
        limit: int = 200,
        level: Optional[str] = None,
        function: Optional[str] = None,
        q: Optional[str] = None,
        source: Optional[str] = None,
        before: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Entries oldest-first.

        * ``since=N`` - entries after ``seq`` N (live tail; poll again with ``next``).
        * ``since=0`` - the newest ``limit`` matching entries.
        * ``before=N`` - the ``limit`` matching entries just before ``seq`` N (scroll back).

        ``level`` is a minimum (WARNING shows WARNING, ERROR and CRITICAL).
        """
        limit = max(1, min(int(limit or 200), 2000))
        floor = _level_no(level)
        needle = (q or "").lower()

        def keep(entry: Dict[str, Any]) -> bool:
            if floor and LEVELS.get(entry.get("level", "INFO"), 20) < floor:
                return False
            if function and entry.get("function") != function:
                return False
            if source and entry.get("source") != source:
                return False
            if needle and needle not in str(entry.get("message", "")).lower():
                return False
            return True

        with self._lock:
            snapshot = list(self._entries)
            last = self._seq
        oldest = snapshot[0]["seq"] if snapshot else last + 1
        if before is not None and int(before) > 0:
            picked = [e for e in snapshot if e["seq"] < int(before) and keep(e)][-limit:]
            return {"entries": picked, "next": last, "oldest": oldest, "more": _has_more(snapshot, picked, keep)}
        since = max(0, int(since or 0))
        if since == 0:
            picked = [e for e in snapshot if keep(e)][-limit:]
            return {"entries": picked, "next": last, "oldest": oldest, "more": _has_more(snapshot, picked, keep)}
        picked = []
        next_seq = since
        for entry in snapshot:
            if entry["seq"] <= since:
                continue
            if len(picked) >= limit:
                break
            next_seq = entry["seq"]
            if keep(entry):
                picked.append(entry)
        if not picked and next_seq == since:
            next_seq = max(since, last)
        return {"entries": picked, "next": next_seq, "oldest": oldest, "gap": since + 1 < oldest}


def _has_more(snapshot: List[Dict[str, Any]], picked: List[Dict[str, Any]], keep: Any) -> bool:
    if not picked:
        return False
    first = picked[0]["seq"]
    return any(e["seq"] < first and keep(e) for e in snapshot)


def _safe_fields(fields: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not fields:
        return {}
    try:
        return json.loads(json.dumps(fields, default=str))
    except (TypeError, ValueError):
        return {"fields": str(fields)}


def _tail_lines(path: Path, count: int) -> List[bytes]:
    size = path.stat().st_size
    with open(path, "rb") as fh:
        block = 64 * 1024
        data = b""
        offset = size
        while offset > 0 and data.count(b"\n") <= count:
            step = min(block, offset)
            offset -= step
            fh.seek(offset)
            data = fh.read(step) + data
    lines = [line for line in data.split(b"\n") if line.strip()]
    if offset > 0 and lines:
        lines = lines[1:]  # first one may be cut in half
    return lines[-count:]


class BufferHandler(logging.Handler):
    """``logging`` handler that writes into a :class:`LogBuffer`."""

    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__(logging.DEBUG)
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            fields = {k: v for k, v in record.__dict__.items() if k not in _RESERVED and not k.startswith("_")}
            function = fields.pop("function", None)
            request_id = fields.pop("request_id", None)
            fields.pop("provider", None)
            message = record.getMessage()
            if record.exc_info:
                message += "\n" + logging.Formatter().formatException(record.exc_info)
            fields["logger"] = record.name
            tagged = current() is not None or bool(function)
            self.buffer.append(
                record.levelname,
                "function" if tagged else "host",
                message,
                function=function,
                request_id=request_id,
                fields=fields,
            )
        except Exception:  # noqa: BLE001
            self.handleError(record)


class TeeStream(io.TextIOBase):
    """Writes through to the real stream and records complete lines in the buffer."""

    def __init__(self, stream: Any, buffer: LogBuffer, source: str, level: str) -> None:
        self.pskit_passthrough = stream
        self._buffer = buffer
        self._source = source
        self._level = level
        self._partial = threading.local()

    def write(self, text: str) -> int:  # type: ignore[override]
        try:
            self.pskit_passthrough.write(text)
        except Exception:  # noqa: BLE001, S110 - a closed console must not break handlers
            pass
        pending = getattr(self._partial, "text", "") + str(text)
        *lines, rest = pending.split("\n")
        self._partial.text = rest[-_MAX_MESSAGE:]
        for line in lines:
            line = line.rstrip("\r")
            if line.strip():
                self._buffer.append(self._level, self._source, line)
        return len(text)

    def flush(self) -> None:
        try:
            self.pskit_passthrough.flush()
        except Exception:  # noqa: BLE001, S110
            pass

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return getattr(self.pskit_passthrough, "encoding", "utf-8") or "utf-8"

    def writable(self) -> bool:
        return True


def install(buffer: LogBuffer, level: str = "INFO", capture_streams: bool = True) -> None:
    """Route logging and (optionally) stdout/stderr of this process into ``buffer``."""
    handler = BufferHandler(buffer)
    root = logging.getLogger()
    for existing in list(root.handlers):
        if isinstance(existing, BufferHandler):
            root.removeHandler(existing)
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > _level_no(level):
        root.setLevel(_level_no(level) or logging.INFO)
    # The "pskit" logger does not propagate (see runtime/log.py); attach to it too.
    pskit = logging.getLogger("pskit")
    for existing in list(pskit.handlers):
        if isinstance(existing, BufferHandler):
            pskit.removeHandler(existing)
    pskit.addHandler(handler)
    if capture_streams:
        if not isinstance(sys.stdout, TeeStream):
            sys.stdout = TeeStream(sys.stdout, buffer, "stdout", "INFO")  # type: ignore[assignment]
        if not isinstance(sys.stderr, TeeStream):
            sys.stderr = TeeStream(sys.stderr, buffer, "stderr", "WARNING")  # type: ignore[assignment]


def uninstall() -> None:
    for name in ("", "pskit"):
        logger = logging.getLogger(name)
        for existing in list(logger.handlers):
            if isinstance(existing, BufferHandler):
                logger.removeHandler(existing)
    if isinstance(sys.stdout, TeeStream):
        sys.stdout = sys.stdout.pskit_passthrough
    if isinstance(sys.stderr, TeeStream):
        sys.stderr = sys.stderr.pskit_passthrough
