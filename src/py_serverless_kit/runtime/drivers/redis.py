"""Redis-backed queue for the on-premises host (standard library only).

Layout for queue ``key``:

* ``<key>``             list of ready messages (``LPUSH`` to enqueue, consumed from the right)
* ``<key>:processing``  list of claimed messages (moved there atomically with ``RPOPLPUSH``)
* ``<key>:claims``      hash ``message id -> {"ts": claim time, "raw": message}``

A message is a JSON envelope ``{"id", "body", "attributes", "receives", "enqueued_at"}``.
Claims older than the visibility timeout are put back by :meth:`RedisQueue.recover`,
so a host that crashed mid-batch does not lose messages.
"""

from __future__ import annotations

import json
import socket
import ssl
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import unquote, urlsplit


class RedisError(RuntimeError):
    pass


Reply = Union[None, int, bytes, List[Any]]


def parse_url(url: str) -> Dict[str, Any]:
    """``redis://[user:password@]host[:port][/db]`` (``rediss://`` uses TLS)."""
    parts = urlsplit(url)
    if parts.scheme not in ("redis", "rediss"):
        raise ValueError(f"redis URL must start with redis:// or rediss://, got {url!r}")
    db_text = (parts.path or "/").strip("/") or "0"
    if not db_text.isdigit():
        raise ValueError(f"redis database must be a number, got {db_text!r}")
    return {
        "host": parts.hostname or "127.0.0.1",
        "port": parts.port or 6379,
        "username": unquote(parts.username) if parts.username else "",
        "password": unquote(parts.password) if parts.password else "",
        "db": int(db_text),
        "tls": parts.scheme == "rediss",
    }


def encode_command(*args: Union[str, bytes, int, float]) -> bytes:
    out = [b"*%d\r\n" % len(args)]
    for arg in args:
        data = arg if isinstance(arg, bytes) else str(arg).encode("utf-8")
        out.append(b"$%d\r\n%s\r\n" % (len(data), data))
    return b"".join(out)


class RedisClient:
    """Tiny RESP2 client: one connection, reconnects once on a socket error."""

    def __init__(self, url: str, timeout: float = 5.0) -> None:
        self.settings = parse_url(url)
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._file: Any = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------ connection
    def _connect(self) -> None:
        s = self.settings
        sock = socket.create_connection((s["host"], s["port"]), timeout=self.timeout)
        if s["tls"]:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=s["host"])
        self._sock = sock
        self._file = sock.makefile("rb")
        if s["password"]:
            if s["username"]:
                self._roundtrip("AUTH", s["username"], s["password"])
            else:
                self._roundtrip("AUTH", s["password"])
        if s["db"]:
            self._roundtrip("SELECT", s["db"])

    def close(self) -> None:
        with self._lock:
            for item in (self._file, self._sock):
                try:
                    if item is not None:
                        item.close()
                except OSError:
                    pass
            self._sock = None
            self._file = None

    def _roundtrip(self, *args: Union[str, bytes, int, float]) -> Reply:
        assert self._sock is not None
        self._sock.sendall(encode_command(*args))
        return self._read()

    def _read(self) -> Reply:
        line = self._file.readline()
        if not line:
            raise ConnectionError("redis closed the connection")
        kind, rest = line[:1], line[1:].rstrip(b"\r\n")
        if kind == b"+":
            return rest
        if kind == b"-":
            raise RedisError(rest.decode("utf-8", "replace"))
        if kind == b":":
            return int(rest)
        if kind == b"$":
            size = int(rest)
            if size < 0:
                return None
            data = self._file.read(size + 2)
            return bytes(data[:-2])
        if kind == b"*":
            count = int(rest)
            if count < 0:
                return None
            return [self._read() for _ in range(count)]
        raise RedisError(f"unexpected reply from redis: {line[:40]!r}")

    def execute(self, *args: Union[str, bytes, int, float]) -> Reply:
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._sock is None:
                        self._connect()
                    return self._roundtrip(*args)
                except RedisError:
                    raise
                except (OSError, ConnectionError, ValueError) as exc:
                    self.close()
                    if attempt == 2:
                        host = f"{self.settings['host']}:{self.settings['port']}"
                        raise RedisError(f"redis at {host} is unreachable: {exc}") from exc
        raise RedisError("unreachable")  # pragma: no cover


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


class RedisQueue:
    """:class:`QueueDriver` on a Redis list."""

    def __init__(self, url: str, key: str, client: Optional[RedisClient] = None) -> None:
        self.key = key
        self.processing = f"{key}:processing"
        self.claims = f"{key}:claims"
        self.client = client or RedisClient(url)

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        ident = uuid.uuid4().hex
        envelope = {
            "id": ident,
            "body": body,
            "attributes": dict(attributes or {}),
            "receives": 0,
            "enqueued_at": time.time(),
        }
        self.client.execute("LPUSH", self.key, json.dumps(envelope, separators=(",", ":")))
        return ident

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        del visibility  # recover() applies it
        claimed: List[Dict[str, Any]] = []
        for _ in range(max(1, int(batch))):
            raw = self.client.execute("RPOPLPUSH", self.key, self.processing)
            if raw is None:
                break
            assert isinstance(raw, bytes)
            text = raw.decode("utf-8")
            msg = self._decode(text)
            self.client.execute("HSET", self.claims, msg["id"], json.dumps({"ts": now, "raw": text}))
            msg["_raw"] = text
            claimed.append(msg)
        return claimed

    def settle(
        self,
        claimed: List[Dict[str, Any]],
        failed_ids: Set[str],
        max_receive: int,
        dead_letter: Optional[Any],
        now: float,
    ) -> None:
        del now
        for msg in claimed:
            ident = str(msg.get("id"))
            self.client.execute("LREM", self.processing, 1, msg["_raw"])
            self.client.execute("HDEL", self.claims, ident)
            if ident not in failed_ids:
                continue
            receives = int(msg.get("receives") or 0) + 1
            if dead_letter is not None and receives >= max_receive:
                attrs = dict(msg.get("attributes") or {})
                attrs.update({"pskit_source_queue": self.key, "pskit_receives": receives})
                dead_letter.submit(str(msg.get("body")), attrs)
                continue
            retry = {k: v for k, v in msg.items() if not k.startswith("_")}
            retry["receives"] = receives
            # RPUSH: back to the consuming end, so it is retried next.
            self.client.execute("RPUSH", self.key, json.dumps(retry, separators=(",", ":")))

    def depth(self) -> int:
        value = self.client.execute("LLEN", self.key)
        return int(value or 0) if isinstance(value, int) else 0

    def peek(self, offset: int, limit: int) -> Tuple[List[Dict[str, Any]], int]:
        """Waiting messages, oldest first (the list's tail), without claiming them."""
        total = self.depth()
        stop = -(offset + 1)
        start = -(offset + limit)
        raw = self.client.execute("LRANGE", self.key, start, stop)
        items = [self._decode(_text(r)) for r in (raw if isinstance(raw, list) else [])]
        return list(reversed(items)), total

    def recover(self, now: float, visibility: float) -> None:
        raw_claims = self.client.execute("HGETALL", self.claims) or []
        assert isinstance(raw_claims, list)
        claims: Dict[str, Tuple[float, str]] = {}
        for i in range(0, len(raw_claims) - 1, 2):
            try:
                info = json.loads(_text(raw_claims[i + 1]))
                claims[_text(raw_claims[i])] = (float(info["ts"]), str(info["raw"]))
            except (ValueError, KeyError, TypeError):
                self.client.execute("HDEL", self.claims, raw_claims[i])
        for ident, (ts, raw) in claims.items():
            if now - ts >= visibility:
                self._requeue(ident, raw)
        # Messages moved to processing whose claim was never recorded (crash in between).
        pending = self.client.execute("LRANGE", self.processing, 0, -1) or []
        assert isinstance(pending, list)
        for item in pending:
            raw = _text(item)
            ident = str(self._decode(raw)["id"])
            if ident not in claims:
                self._requeue(ident, raw)

    def _requeue(self, ident: str, raw: str) -> None:
        removed = self.client.execute("LREM", self.processing, 1, raw)
        if ident:
            self.client.execute("HDEL", self.claims, ident)
        if removed:
            self.client.execute("RPUSH", self.key, raw)

    @staticmethod
    def _decode(text: str) -> Dict[str, Any]:
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if not isinstance(data, dict) or "id" not in data:
            # A plain value pushed by another producer: wrap it.
            ident = uuid.uuid5(uuid.NAMESPACE_OID, text).hex
            return {"id": ident, "body": text, "attributes": {}, "receives": 0, "enqueued_at": time.time()}
        data.setdefault("attributes", {})
        data.setdefault("receives", 0)
        data.setdefault("enqueued_at", time.time())
        data["body"] = data.get("body") if isinstance(data.get("body"), str) else json.dumps(data.get("body"))
        return data
