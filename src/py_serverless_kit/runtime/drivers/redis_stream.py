"""A Redis / Valkey stream with a consumer group as an on-prem queue (standard library only).

Needs Redis 6.2+ or Valkey (``XAUTOCLAIM``). Layout:

* ``XADD <key> * body <text> attributes <json> enqueued_at <ts>`` publishes; other
  producers may ``XADD`` any fields (``body`` or the first field's value becomes the body).
* The host reads new entries with ``XREADGROUP GROUP <group> <consumer> ... >``. A read
  entry stays in the group's pending list until it is settled, so a crashed host loses
  nothing: entries idle longer than ``visibility`` are taken over with ``XAUTOCLAIM``.
* Delivered entries are ``XACK``-ed and ``XDEL``-eted. A failed one is made claimable at
  once; after ``max_receive`` deliveries (the stream's own delivery counter) it goes to
  ``dead_letter`` and is removed.

Unlike the ``redis`` (list) driver, several hosts can share one stream and consumer group,
and other services can read the same stream with their own groups.
"""

from __future__ import annotations

import json
import os
import socket
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from .redis import RedisClient, RedisError, _text


def _list(reply: Any) -> List[Any]:
    return reply if isinstance(reply, list) else []


def _fields(raw: Any) -> Dict[str, str]:
    items = list(raw or [])
    return {_text(items[i]): _text(items[i + 1]) for i in range(0, len(items) - 1, 2)}


class RedisStreamQueue:
    def __init__(
        self,
        url: str,
        key: str,
        group: str = "pskit",
        consumer: str = "",
        maxlen: int = 0,
        client: Optional[RedisClient] = None,
    ) -> None:
        self.key = key
        self.group = group or "pskit"
        self.consumer = consumer or f"{socket.gethostname()}-{os.getpid()}"
        self.maxlen = int(maxlen or 0)
        self.client = client or RedisClient(url)
        self._ready = False
        self._visibility_ms = 30000

    @classmethod
    def from_binding(cls, b: Dict[str, Any], label: str = "") -> RedisStreamQueue:
        if not str(b.get("url") or "").lower().startswith(("redis://", "rediss://")):
            raise ValueError("redis_stream: set url: redis://host:6379/0 (or url_env)")
        return cls(
            str(b["url"]),
            str(b.get("key") or label or "pskit"),
            str(b.get("group") or "pskit"),
            str(b.get("consumer") or ""),
            int(b.get("maxlen") or 0),
        )

    def _group(self) -> None:
        if self._ready:
            return
        try:
            self.client.execute("XGROUP", "CREATE", self.key, self.group, "0", "MKSTREAM")
        except RedisError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._ready = True

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        args: List[Any] = ["XADD", self.key]
        if self.maxlen > 0:
            args += ["MAXLEN", "~", self.maxlen]
        args += ["*", "body", body, "attributes", json.dumps(dict(attributes or {})), "enqueued_at", time.time()]
        return _text(self.client.execute(*args))

    def _message(self, entry: Any, receives: int) -> Dict[str, Any]:
        ident = _text(entry[0])
        fields = _fields(entry[1])
        try:
            attributes = json.loads(fields.pop("attributes", "") or "{}")
        except ValueError:
            attributes = {}
        if "body" in fields:
            body = fields.pop("body")
        else:  # a foreign producer: the first field's value, the rest as attributes
            body = next(iter(fields.values()), "")
        try:
            enqueued = float(fields.pop("enqueued_at", "") or int(ident.split("-")[0]) / 1000)
        except ValueError:
            enqueued = time.time()
        return {
            "id": ident,
            "body": body,
            "attributes": attributes if isinstance(attributes, dict) else {},
            "receives": receives,
            "enqueued_at": enqueued,
        }

    def _deliveries(self, ident: str) -> int:
        for row in _list(self.client.execute("XPENDING", self.key, self.group, ident, ident, 1)):
            if isinstance(row, list) and len(row) >= 4:
                return int(row[3])
        return 1

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        del now
        self._group()
        count = max(1, int(batch))
        self._visibility_ms = int(max(1.0, visibility) * 1000)
        out: List[Dict[str, Any]] = []
        # Entries a crashed or failed consumer left behind come first.
        reply = self.client.execute(
            "XAUTOCLAIM", self.key, self.group, self.consumer, self._visibility_ms, "0-0", "COUNT", count
        )
        for entry in (reply[1] if isinstance(reply, list) and len(reply) > 1 else []) or []:
            if isinstance(entry, list) and len(entry) == 2 and entry[1] is not None:
                out.append(self._message(entry, self._deliveries(_text(entry[0]))))
        if len(out) < count:
            reply = self.client.execute(
                "XREADGROUP", "GROUP", self.group, self.consumer, "COUNT", count - len(out), "STREAMS", self.key, ">"
            )
            for stream in _list(reply):
                for entry in _list(stream[1] if isinstance(stream, list) and len(stream) > 1 else None):
                    out.append(self._message(entry, 1))
        return out

    def settle(
        self,
        claimed: List[Dict[str, Any]],
        failed_ids: Set[str],
        max_receive: int,
        dead_letter: Optional[Any],
        now: float,
    ) -> None:
        del now
        done: List[str] = []
        for msg in claimed:
            if msg["id"] not in failed_ids:
                done.append(msg["id"])
            elif dead_letter is not None and int(msg.get("receives") or 1) >= max_receive:
                attrs = dict(msg.get("attributes") or {})
                attrs.setdefault("pskit_source_queue", self.key)
                dead_letter.submit(str(msg.get("body") or ""), attrs)
                done.append(msg["id"])
            else:
                # Mark it idle for longer than the lease, so the next claim takes it again at once.
                self.client.execute(
                    "XCLAIM", self.key, self.group, self.consumer, 0, msg["id"], "IDLE", self._visibility_ms + 1000,
                    "JUSTID",
                )
        if done:
            self.client.execute("XACK", self.key, self.group, *done)
            self.client.execute("XDEL", self.key, *done)

    def peek(self, offset: int, limit: int) -> Tuple[List[Dict[str, Any]], int]:
        """Entries still in the stream, oldest first (delivered ones are deleted on settle)."""
        reply = _list(self.client.execute("XRANGE", self.key, "-", "+", "COUNT", offset + limit))
        return [self._message(e, 0) for e in reply[offset:] if isinstance(e, list) and len(e) == 2], self.depth()

    def depth(self) -> int:
        reply = self.client.execute("XLEN", self.key)
        return reply if isinstance(reply, int) else 0

    def recover(self, now: float, visibility: float) -> None:
        del now, visibility  # claim() takes over idle entries with XAUTOCLAIM
