"""Check that a database / cache / custom service answers (standard library only).

``values`` are a resource's connection values with lower-case keys, ``<name>_env``
already resolved. A ``url`` is used first (``redis(s)://`` gets a real ``PING``,
anything else a TCP connect to its host and port); otherwise ``host`` + ``port``,
then ``smtp_host`` + ``smtp_port``.
"""

from __future__ import annotations

import socket
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit

DEFAULT_PORTS = {
    "redis": 6379,
    "rediss": 6380,
    "postgres": 5432,
    "postgresql": 5432,
    "mysql": 3306,
    "mariadb": 3306,
    "mongodb": 27017,
    "amqp": 5672,
    "nats": 4222,
    "http": 80,
    "https": 443,
}


def target_of(values: Dict[str, str]) -> Optional[Tuple[str, str, int]]:
    """``(scheme, host, port)`` to check, or None when the values name no endpoint."""
    url = values.get("url") or ""
    if "://" in url:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if parts.hostname:
            return scheme, parts.hostname, int(parts.port or DEFAULT_PORTS.get(scheme, 0) or 0)
    for host_key, port_key in (("host", "port"), ("smtp_host", "smtp_port")):
        host = values.get(host_key)
        if host:
            try:
                return "tcp", host, int(values.get(port_key) or 0)
            except ValueError:
                return "tcp", host, 0
    return None


def probe(values: Dict[str, str], timeout: float = 5.0) -> str:
    """A short description of what answered; raises ``OSError`` / ``RuntimeError`` when it does not."""
    target = target_of(values)
    if target is None:
        raise RuntimeError("no url, host or smtp_host in the connection values to check")
    scheme, host, port = target
    if not port:
        raise RuntimeError(f"no port for {host}; add `port` to the connection values")
    if scheme in ("redis", "rediss"):
        from .redis import RedisClient

        client = RedisClient(values["url"], timeout=timeout)
        try:
            reply = client.execute("PING")
        finally:
            client.close()
        return f"redis at {host}:{port} answered {reply.decode() if isinstance(reply, bytes) else reply}"
    with socket.create_connection((host, port), timeout=timeout):
        pass
    return f"{host}:{port} accepts connections"
