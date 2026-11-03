"""Azure Functions (Python v2 programming model) adapter.

The generated ``function_app.py`` registers one decorated wrapper per trigger
and calls these helpers with the *logical* function name, because one Function
App hosts every function of the service (app settings are shared, so
``PSKIT_FUNCTION`` cannot be used).

``azure.functions`` is imported lazily so the module can be unit-tested
without the Azure SDK installed.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ..context import Context
from ..dispatch import execute
from ..event import Event, EventType, Headers, HttpRequest, Record, parse_time
from ..response import Response, dumps
from .base import unwrap_envelope

PROVIDER = "azure"
_JSON = "application/json"


def _func() -> Any:
    import azure.functions as func  # type: ignore[import-not-found]

    return func


def _context(fn: str, request_id: Optional[str] = None, raw: Any = None) -> Context:
    return Context(request_id=request_id or str(uuid.uuid4()), function=fn, provider=PROVIDER, raw=raw)


def _text(value: Any) -> Any:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value
    return value


# ------------------------------------------------------------------ HTTP


def to_http_event(req: Any, function: str) -> Event:
    headers = dict(req.headers.items()) if hasattr(req.headers, "items") else dict(req.headers or {})
    params = dict(req.params or {})
    path = urlparse(req.url).path if getattr(req, "url", None) else "/"
    request = HttpRequest(
        method=req.method,
        path=path or "/",
        headers=Headers(headers),
        query=params,
        path_params={k: v for k, v in dict(getattr(req, "route_params", None) or {}).items()},
        body=req.get_body() or b"",
        source_ip=(headers.get("x-forwarded-for") or headers.get("X-Forwarded-For") or "").split(",")[0].split(":")[0]
        or None,
    )
    return Event(type=EventType.HTTP, provider=PROVIDER, function=function, http=request, raw=req)


def _http_response(body: bytes, status: int, headers: Dict[str, str]) -> Any:
    func = _func()
    return func.HttpResponse(body=body, status_code=status, headers=headers)


def http(req: Any, function: str) -> Any:
    body = req.get_body() or b""
    headers = req.headers if req.headers is not None else {}
    req_id = headers.get("x-ms-request-id") or headers.get("x-request-id")
    wrapped = unwrap_envelope(body) if body[:1] == b"{" else None
    if wrapped is not None:
        kind, data, meta = wrapped
        event = Event(type=kind, provider=PROVIDER, function=function, data=data, source=meta.get("source"), raw=req)
        try:
            result = execute(event, _context(function, req_id, req), function)
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            payload = {"errorType": type(exc).__name__, "cause": str(exc)}
            return _http_response(dumps(payload).encode("utf-8"), 500, {"content-type": _JSON})
        return _http_response(dumps(result).encode("utf-8"), 200, {"content-type": _JSON})
    event = to_http_event(req, function)
    resp: Response = execute(event, _context(function, req_id, req), function)
    status, out_headers, raw = resp.render()
    if resp.cookies:
        # Azure's HttpResponse headers are a plain mapping: only one Set-Cookie survives.
        out_headers["set-cookie"] = resp.cookies[-1]
    return _http_response(raw, status, out_headers)


# ------------------------------------------------------------------ other triggers


def timer(timer_request: Any, function: str, data: Any = None) -> Any:
    event = Event(
        type=EventType.SCHEDULE,
        provider=PROVIDER,
        function=function,
        data=data,
        source="azure.timer",
        raw=timer_request,
    )
    return execute(event, _context(function, raw=timer_request), function)


def to_queue_event(msg: Any, function: str) -> Event:
    record = Record(
        id=getattr(msg, "id", None),
        body=_text(msg.get_body()),
        attributes={
            "dequeue_count": getattr(msg, "dequeue_count", None),
            "insertion_time": str(getattr(msg, "insertion_time", "") or ""),
        },
        source="azure.storage.queue",
        raw=msg,
    )
    return Event(
        type=EventType.QUEUE,
        provider=PROVIDER,
        function=function,
        records=[record],
        time=parse_time(getattr(msg, "insertion_time", None)),
        source="azure.storage.queue",
        raw=msg,
    )


def queue(msg: Any, function: str) -> Any:
    return execute(to_queue_event(msg, function), _context(function, getattr(msg, "id", None), msg), function)


def to_blob_event(blob: Any, function: str, bucket: str) -> Event:
    name = getattr(blob, "name", "") or ""
    key = name[len(bucket) + 1 :] if name.startswith(bucket + "/") else name
    record = Record(
        id=getattr(blob, "uri", None) or name,
        bucket=bucket,
        key=key,
        size=getattr(blob, "length", None),
        action="created",
        attributes={"uri": getattr(blob, "uri", None)},
        source="azure.storage.blob",
        raw=blob,
    )
    return Event(
        type=EventType.STORAGE,
        provider=PROVIDER,
        function=function,
        records=[record],
        source="azure.storage.blob",
        raw=blob,
    )


def blob(blob_stream: Any, function: str, bucket: str) -> Any:
    return execute(to_blob_event(blob_stream, function, bucket), _context(function, raw=blob_stream), function)


def to_service_bus_event(msg: Any, function: str) -> Event:
    props = getattr(msg, "user_properties", None) or getattr(msg, "application_properties", None) or {}
    record = Record(
        id=getattr(msg, "message_id", None),
        body=_text(msg.get_body()),
        attributes={str(k): v for k, v in dict(props).items()},
        source="azure.servicebus",
        raw=msg,
    )
    return Event(
        type=EventType.TOPIC,
        provider=PROVIDER,
        function=function,
        records=[record],
        time=parse_time(getattr(msg, "enqueued_time_utc", None)),
        source="azure.servicebus",
        raw=msg,
    )


def service_bus(msg: Any, function: str) -> Any:
    event = to_service_bus_event(msg, function)
    return execute(event, _context(function, getattr(msg, "message_id", None), msg), function)
