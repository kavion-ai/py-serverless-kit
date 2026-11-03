"""Shared logic for providers where *every* invocation arrives as an HTTP-ish
request (IBM Code Engine, DigitalOcean web functions, Cloudflare Workers,
OCI behind API Gateway).

A request whose JSON body carries the ``__pskit`` envelope is treated as a
non-HTTP event (``invoke()``, workflow task, scheduler with input): the handler
result is returned as JSON 200, and failures as JSON 500
``{"errorType", "cause"}`` - the same contract the GCP adapter uses.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, Optional, Tuple

from ..context import Context
from ..dispatch import execute, execute_async
from ..event import Event, EventType, HttpRequest
from ..response import Response, dumps
from .base import maybe_json, unwrap_envelope

NativeHttp = Tuple[int, Dict[str, str], str, bool]  # status, headers, body, is_base64


def event_from_request(req: HttpRequest, provider: str, function: str, raw: Any = None) -> Event:
    if req.method == "POST" and req.body[:1] == b"{":
        wrapped = unwrap_envelope(req.body)
        if wrapped is not None:
            kind, data, meta = wrapped
            return Event(type=kind, provider=provider, function=function, data=data, source=meta.get("source"), raw=raw)
    return Event(type=EventType.HTTP, provider=provider, function=function, http=req, raw=raw)


def error_body(exc: BaseException) -> Dict[str, Any]:
    return {"errorType": getattr(exc, "error", None) or type(exc).__name__, "cause": str(exc)}


def result_to_http(event: Event, result: Any) -> NativeHttp:
    if isinstance(result, Response):
        return result.render_for_gateway()
    return 200, {"content-type": "application/json"}, dumps(result), False


def run(event: Event, context: Context) -> NativeHttp:
    """Execute and always return an HTTP-shaped result."""
    if event.http is not None:
        return execute(event, context).render_for_gateway()
    try:
        result = execute(event, context)
    except Exception as exc:  # noqa: BLE001 - reported to the caller as JSON
        return 500, {"content-type": "application/json"}, dumps(error_body(exc)), False
    return result_to_http(event, result)


async def run_async(event: Event, context: Context) -> NativeHttp:
    if event.http is not None:
        resp = await execute_async(event, context)
        return resp.render_for_gateway()
    try:
        result = await execute_async(event, context)
    except Exception as exc:  # noqa: BLE001
        return 500, {"content-type": "application/json"}, dumps(error_body(exc)), False
    return result_to_http(event, result)


def decode_body(body: Any, headers: Dict[str, Any], is_base64: Optional[bool] = None) -> bytes:
    """Decode a body that may be base64 when the content type is binary."""
    if body is None:
        return b""
    if isinstance(body, (dict, list)):
        return dumps(body).encode("utf-8")
    if isinstance(body, bytes):
        return body
    text = str(body)
    if is_base64 is None:
        ctype = ""
        for k, v in headers.items():
            if str(k).lower() == "content-type":
                ctype = str(v).lower()
        textual = (not ctype) or ctype.startswith("text/") or "json" in ctype or "xml" in ctype or "form" in ctype
        is_base64 = not textual
    if is_base64:
        try:
            return base64.b64decode(text, validate=True)
        except (ValueError, TypeError):
            return text.encode("utf-8")
    return text.encode("utf-8")


def json_or_text(text: str) -> Any:
    return maybe_json(text)
