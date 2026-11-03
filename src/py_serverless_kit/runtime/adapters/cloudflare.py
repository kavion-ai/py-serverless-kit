"""Cloudflare Python Workers adapter (Pyodide).

The generated worker module defines ``class Default(WorkerEntrypoint)`` whose
``fetch`` / ``scheduled`` methods call :func:`fetch` / :func:`scheduled` here.
Everything is async because the Workers runtime already owns the event loop.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from ..context import Context
from ..dispatch import execute_async
from ..event import Event, EventType, Headers, HttpRequest, parse_time
from ._httpfn import event_from_request, run_async
from .base import function_name

PROVIDER = "cloudflare"

# Filled by the generated worker module: {cron expression: schedule input}.
SCHEDULE_INPUTS: Dict[str, Any] = {}


def _header_items(headers: Any) -> Iterable[Tuple[str, str]]:
    if headers is None:
        return []
    items = getattr(headers, "items", None)
    if callable(items):
        try:
            return [(str(k), str(v)) for k, v in items()]
        except TypeError:
            pass
    try:
        return [(str(k), str(v)) for k, v in headers]
    except (TypeError, ValueError):
        return []


async def _read_body(request: Any) -> bytes:
    for name in ("bytes", "text"):
        reader = getattr(request, name, None)
        if not callable(reader):
            continue
        value = await reader()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        if hasattr(value, "to_bytes"):  # JsProxy of an ArrayBuffer / Uint8Array
            return bytes(value.to_bytes())
        if value is None:
            return b""
        return str(value).encode("utf-8")
    return b""


async def to_request(request: Any) -> HttpRequest:
    method = str(getattr(request, "method", "GET"))
    parts = urlsplit(str(getattr(request, "url", "/")))
    headers: List[Tuple[str, str]] = list(_header_items(getattr(request, "headers", None)))
    body = await _read_body(request) if method not in ("GET", "HEAD") else b""
    multi = parse_qs(parts.query, keep_blank_values=True)
    lookup = {k.lower(): v for k, v in headers}
    return HttpRequest(
        method=method,
        path=parts.path or "/",
        headers=Headers(headers),
        query={k: v[-1] for k, v in multi.items()},
        multi_query=multi,
        body=body,
        source_ip=lookup.get("cf-connecting-ip"),
    )


def _response(status: int, headers: Dict[str, str], body: str, is_b64: bool) -> Any:
    payload: Any = body
    if is_b64:
        import base64

        payload = base64.b64decode(body)
    try:
        from workers import Response as WorkerResponse  # type: ignore[import-not-found]
    except ImportError:  # local tests
        return {"status": status, "headers": headers, "body": payload}
    return WorkerResponse(payload, status=status, headers=headers)


async def fetch(request: Any, env: Any = None) -> Any:
    fn = function_name()
    req = await to_request(request)
    event = event_from_request(req, PROVIDER, fn, raw=request)
    context = Context(
        request_id=req.headers.get("cf-ray", "") or Context().request_id,
        function=fn,
        provider=PROVIDER,
        raw=env,
    )
    status, headers, body, is_b64 = await run_async(event, context)
    return _response(status, headers, body, is_b64)


async def scheduled(controller: Any, env: Any = None) -> Any:
    fn = function_name()
    cron = str(getattr(controller, "cron", "") or "")
    event = Event(
        type=EventType.SCHEDULE,
        provider=PROVIDER,
        function=fn,
        data=SCHEDULE_INPUTS.get(cron),
        time=parse_time(getattr(controller, "scheduledTime", None)),
        source=cron or None,
        raw=controller,
    )
    return await execute_async(event, Context(function=fn, provider=PROVIDER, raw=env))


def configure(
    function: str,
    environment: Optional[Dict[str, str]] = None,
    schedules: Optional[Dict[str, Any]] = None,
) -> None:
    """Called once by the generated worker module at import time."""
    os.environ.update(environment or {})
    os.environ["PSKIT_FUNCTION"] = function
    SCHEDULE_INPUTS.clear()
    SCHEDULE_INPUTS.update(schedules or {})
