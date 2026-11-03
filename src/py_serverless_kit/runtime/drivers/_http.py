"""Small HTTP helper shared by the REST-based drivers (standard library only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

Reply = Tuple[int, Dict[str, str], bytes]


class DriverError(RuntimeError):
    """A backend call failed. ``status`` is the HTTP status (0 when unreachable)."""

    def __init__(self, service: str, status: int, message: str) -> None:
        self.service = service
        self.status = status
        prefix = f"{service}: " if service else ""
        super().__init__(f"{prefix}request failed ({status}): {message}" if status else f"{prefix}{message}")


def check_url(url: str, what: str) -> str:
    parts = urlsplit(str(url))
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"{what} must be an http(s) URL, got {url!r}")
    return str(url).rstrip("/")


def request(
    service: str,
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout: float = 10.0,
) -> Reply:
    """Send one request; HTTP errors are returned (not raised), connection errors raise :class:`DriverError`."""
    req = urllib.request.Request(url, data=body, method=method)  # noqa: S310 - operator-configured endpoint
    for name, value in (headers or {}).items():
        if name.lower() != "host":
            req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise DriverError(service, 0, f"{urlsplit(url).netloc} is unreachable: {reason}") from exc


def check(service: str, reply: Reply, ok: Tuple[int, ...] = (200,)) -> bytes:
    status, _headers, body = reply
    if status not in ok:
        raise DriverError(service, status, body[:300].decode("utf-8", "replace").strip() or "no response body")
    return body


def json_body(service: str, reply: Reply, ok: Tuple[int, ...] = (200,)) -> Any:
    body = check(service, reply, ok)
    if not body.strip():
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        raise DriverError(service, reply[0], "response is not JSON") from None
