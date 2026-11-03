"""Oracle Cloud (OCI) Functions adapter, built on the Fn Project Python FDK.

``func.py`` exposes ``handler(ctx, data)``. Invocations come from:

* OCI API Gateway - the FDK context carries ``Fn-Http-Method``,
  ``Fn-Http-Request-Url`` and ``Fn-Http-H-<name>`` headers;
* OCI Events (object storage) - a CloudEvents JSON body;
* direct invoke (``oci fn function invoke``) / the ``__pskit`` envelope.
"""

from __future__ import annotations

import base64
import io
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlsplit

from ..context import Context
from ..event import Event, EventType, Headers, HttpRequest, Record, parse_time
from ._httpfn import event_from_request, run
from .base import action_from, function_name, maybe_json, unwrap_envelope

PROVIDER = "oracle"
_HEADER_PREFIX = "fn-http-h-"


def _call(obj: Any, name: str, default: Any = None) -> Any:
    fn = getattr(obj, name, None)
    if callable(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001 - FDK accessors are best effort
            return default
    return default


def _ctx_headers(ctx: Any) -> Dict[str, Any]:
    raw = _call(ctx, "Headers") or {}
    return {str(k).lower(): v for k, v in dict(raw).items()}


def _first(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _read(data: Any) -> bytes:
    if data is None:
        return b""
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("utf-8")
    if hasattr(data, "getvalue"):
        return data.getvalue()
    if hasattr(data, "read"):
        return data.read()
    return str(data).encode("utf-8")


def to_request(ctx: Any, body: bytes) -> Optional[HttpRequest]:
    headers = _ctx_headers(ctx)
    method = _first(headers.get("fn-http-method"))
    if not method:
        http_headers = _call(ctx, "HttpHeaders")
        if http_headers is None:
            return None
        method = _call(ctx, "Method")
        if not method:
            return None
    url = _first(headers.get("fn-http-request-url")) or _call(ctx, "RequestURL") or "/"
    http_headers = _call(ctx, "HttpHeaders")
    if http_headers is None:
        http_headers = {k[len(_HEADER_PREFIX) :]: v for k, v in headers.items() if k.startswith(_HEADER_PREFIX)}
    parts = urlsplit(str(url))
    multi = parse_qs(parts.query, keep_blank_values=True)
    return HttpRequest(
        method=str(method),
        path=parts.path or "/",
        headers=Headers(dict(http_headers)),
        query={k: v[-1] for k, v in multi.items()},
        multi_query=multi,
        body=body,
    )


def _cloud_event(payload: Dict[str, Any], fn: str) -> Optional[Event]:
    etype = str(payload.get("eventType") or payload.get("type") or "")
    if "objectstorage" not in etype:
        return None
    data = payload.get("data") or {}
    details = data.get("additionalDetails") or {}
    record = Record(
        id=str(payload.get("eventID") or payload.get("id") or ""),
        bucket=details.get("bucketName"),
        key=data.get("resourceName"),
        action=action_from(etype),
        attributes={"event_type": etype, "namespace": details.get("namespace")},
        source=str(payload.get("source") or "objectstorage"),
        raw=payload,
    )
    return Event(
        type=EventType.STORAGE,
        provider=PROVIDER,
        function=fn,
        records=[record],
        source=record.source,
        time=parse_time(payload.get("eventTime") or payload.get("time")),
        raw=payload,
    )


def to_event(ctx: Any, data: Any, fn: str) -> Event:
    body = _read(data)
    req = to_request(ctx, body)
    if req is not None:
        return event_from_request(req, PROVIDER, fn, raw=ctx)
    payload = maybe_json(body) if body else None
    wrapped = unwrap_envelope(payload)
    if wrapped is not None:
        kind, value, meta = wrapped
        return Event(type=kind, provider=PROVIDER, function=fn, data=value, source=meta.get("source"), raw=payload)
    if isinstance(payload, dict):
        storage = _cloud_event(payload, fn)
        if storage is not None:
            return storage
    return Event(type=EventType.INVOKE, provider=PROVIDER, function=fn, data=payload, raw=payload)


def _respond(ctx: Any, status: int, headers: Dict[str, str], body: Any, is_http: bool) -> Any:
    try:
        from fdk import response as fdk_response  # type: ignore[import-not-found]
    except ImportError:  # local tests without the FDK
        return {"status": status, "headers": headers, "body": body}
    if is_http:
        try:
            from fdk import context as fdk_context  # type: ignore[import-not-found]

            factory = getattr(fdk_context, "GetHTTPGatewayContext", None) or getattr(
                fdk_context, "HTTPGatewayContext", None
            )
            if factory is not None:
                gw = factory(ctx)
                gw.SetStatusCode(status)
                gw.SetResponseHeaders(headers, status)
        except Exception:  # noqa: BLE001, S110 - fall back to protocol headers
            pass
        headers = dict(headers)
        headers["Fn-Http-Status"] = str(status)
    return fdk_response.Response(ctx, response_data=body, headers=headers, status_code=200 if is_http else status)


def handler(ctx: Any, data: Any = None) -> Any:
    """FDK entrypoint used by the generated ``func.py``."""
    fn = function_name()
    event = to_event(ctx, data if data is not None else io.BytesIO(b""), fn)
    context = Context(request_id=str(_call(ctx, "CallID") or ""), function=fn, provider=PROVIDER, raw=ctx)
    status, headers, body, is_b64 = run(event, context)
    payload: Any = base64.b64decode(body) if is_b64 else body
    return _respond(ctx, status, headers, payload, event.http is not None)
