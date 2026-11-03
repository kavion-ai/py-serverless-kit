"""``pskit studio --ailogs=true``: every step of Hana's conversations, printed in the studio's terminal.

What is printed, per turn: the user's message and the Environment line; whether a studio action answered (and its
cards) or the model did; each model request (what was added since the last one) and its answer with the tool calls,
token usage and time; each tool with its arguments and result; plans, questions and the user's answers; changed
files, errors and the end of the turn. Passwords are already hidden before anything reaches this log.

Off by default. Also switched on by the environment variable ``PSKIT_HANA_AILOGS=1``.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

MAX_TEXT = 4000  # characters of one block (a long tool result is cut in the middle; the length is shown)

_lock = threading.Lock()
_enabled = os.environ.get("PSKIT_HANA_AILOGS", "").lower() in ("1", "true", "yes", "on")


def enable(on: bool = True) -> None:
    global _enabled
    _enabled = bool(on)


def enabled() -> bool:
    return _enabled


def _style(text: str, **kw: Any) -> str:
    try:
        import click

        return click.style(text, **kw)
    except Exception:  # noqa: BLE001 - plain text without click
        return text


def _cut(text: str) -> str:
    if len(text) <= MAX_TEXT:
        return text
    head, tail = text[: MAX_TEXT * 2 // 3], text[-MAX_TEXT // 3:]
    return f"{head}\n... [{len(text) - len(head) - len(tail)} more characters, {len(text)} in all] ...\n{tail}"


def _dump(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return repr(value)


def log(turn: str, kind: str, title: str = "", body: Any = None, color: str = "cyan") -> None:
    """One entry: ``[hana 14:02:11 turn 3f2a] KIND  title`` then the indented body."""
    if not _enabled:
        return
    stamp = time.strftime("%H:%M:%S")
    head = _style(f"[hana {stamp} {turn[:6]}]", dim=True) + " " + _style(kind.upper().ljust(13), fg=color, bold=True)
    lines = [head + (" " + title if title else "")]
    if body is not None and body != "":
        lines += ["    " + line for line in _cut(_dump(body)).split("\n")]
    with _lock:
        try:
            sys.stderr.write("\n".join(lines) + "\n")
            sys.stderr.flush()
        except (OSError, ValueError):  # a closed terminal must never break a chat
            pass


def messages_since(messages: List[Dict[str, Any]], seen: int) -> List[Dict[str, Any]]:
    """The messages added since the last model request (the full list on the first one)."""
    return messages[seen:]


def show_messages(turn: str, messages: List[Dict[str, Any]], first: bool) -> None:
    """What a model request adds: on the first request of a turn the system prompt (once) and the history."""
    if not _enabled:
        return
    for m in messages:
        role = m.get("role")
        if role == "system":
            if first:
                log(turn, "system", f"({len(str(m.get('content') or ''))} characters)", m.get("content"), "white")
            continue
        if m.get("tool_calls"):
            calls = [{"name": c["function"]["name"], "arguments": c["function"]["arguments"]} for c in m["tool_calls"]]
            log(turn, "→ assistant", "tool call" + (f" after: {m.get('content')}" if m.get("content") else ""),
                calls, "blue")
        elif role == "tool":
            log(turn, "→ tool result", str(m.get("name") or ""), m.get("content"), "blue")
        else:
            log(turn, f"→ {role}", "", m.get("content"), "blue")


class Timer:
    def __init__(self) -> None:
        self.start = time.monotonic()

    def ms(self) -> int:
        return int((time.monotonic() - self.start) * 1000)


def usage_text(usage: Optional[Dict[str, Any]]) -> str:
    if not usage:
        return ""
    parts = [f"{k.replace('_tokens', '')} {v}" for k, v in usage.items() if k.endswith("tokens") and v is not None]
    return ("tokens: " + ", ".join(parts)) if parts else ""
