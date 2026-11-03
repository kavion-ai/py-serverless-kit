"""Tencent Cloud SCF adapter.

Handles API Gateway (integrated response), timer triggers, COS triggers and
direct invocation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Mapping
from urllib.parse import parse_qs, unquote_plus

from ..context import Context
from ..dispatch import execute
from ..event import Event, EventType, Headers, HttpRequest, Record, parse_time
from ..response import Response
from .base import action_from, function_name, maybe_json, unwrap_envelope

PROVIDER = "tencent"


def _ctx_get(ctx: Any, key: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(key, default)
    return getattr(ctx, key, default)


def _http(evt: Dict[str, Any]) -> HttpRequest:
    rc = evt.get("requestContext") or {}
    query: Dict[str, str] = {}
    multi: Dict[str, List[str]] = {}
    raw_query = evt.get("queryString")
    if isinstance(raw_query, dict):
        for key, value in raw_query.items():
            values = [str(v) for v in value] if isinstance(value, list) else [str(value)]
            multi[key] = values
            query[key] = values[-1] if values else ""
    elif isinstance(raw_query, str) and raw_query:
        multi = parse_qs(raw_query, keep_blank_values=True)
        query = {k: v[-1] for k, v in multi.items()}
    if not query and evt.get("queryStringParameters"):
        query = {k: str(v) for k, v in evt["queryStringParameters"].items()}
    return HttpRequest(
        method=evt.get("httpMethod") or rc.get("httpMethod") or "GET",
        path=evt.get("path") or rc.get("path") or "/",
        headers=Headers(evt.get("headers") or {}),
        query=query,
        multi_query=multi,
        path_params={k: str(v) for k, v in (evt.get("pathParameters") or {}).items()},
        body=HttpRequest.decode_body(evt.get("body"), bool(evt.get("isBase64Encoded"))),
        source_ip=rc.get("sourceIp"),
    )


def _cos(evt: Dict[str, Any], fn: str) -> Event:
    records = []
    for r in evt.get("Records") or []:
        cos = r.get("cos") or {}
        obj = cos.get("cosObject") or {}
        bucket = (cos.get("cosBucket") or {}).get("name")
        key = obj.get("key") or ""
        # COS keys look like "/<appid>/<bucket>/<path>"; strip that prefix.
        parts = key.lstrip("/").split("/", 2)
        if len(parts) == 3 and parts[0].isdigit():
            key = parts[2]
        event_name = (r.get("event") or {}).get("eventName", "")
        records.append(
            Record(
                id=(obj.get("meta") or {}).get("x-cos-request-id"),
                bucket=bucket,
                key=unquote_plus(key),
                size=obj.get("size"),
                action=action_from(event_name),
                attributes={"event_name": event_name, "url": obj.get("url")},
                source="cos",
                raw=r,
            )
        )
    first = (evt.get("Records") or [{}])[0]
    return Event(
        type=EventType.STORAGE,
        provider=PROVIDER,
        function=fn,
        records=records,
        source="cos",
        time=parse_time((first.get("event") or {}).get("eventTime")),
        raw=evt,
    )


def to_event(native: Any, ctx: Any = None) -> Event:
    fn = function_name(_ctx_get(ctx, "function_name", "") or "")
    evt = maybe_json(native)
    wrapped = unwrap_envelope(evt)
    if wrapped is not None:
        kind, data, meta = wrapped
        return Event(type=kind, provider=PROVIDER, function=fn, data=data, source=meta.get("source"), raw=evt)
    if isinstance(evt, dict):
        if "httpMethod" in evt and ("requestContext" in evt or "path" in evt):
            return Event(type=EventType.HTTP, provider=PROVIDER, function=fn, http=_http(evt), raw=evt)
        if evt.get("Type") == "Timer":
            message = evt.get("Message")
            inner = unwrap_envelope(message) if message else None
            return Event(
                type=EventType.SCHEDULE,
                provider=PROVIDER,
                function=fn,
                data=inner[1] if inner else (maybe_json(message) if message else None),
                time=parse_time(evt.get("Time")),
                source=evt.get("TriggerName"),
                raw=evt,
            )
        records = evt.get("Records")
        if isinstance(records, list) and records and isinstance(records[0], dict) and "cos" in records[0]:
            return _cos(evt, fn)
    return Event(type=EventType.INVOKE, provider=PROVIDER, function=fn, data=evt, raw=native)


def to_context(ctx: Any, fn: str) -> Context:
    if ctx is None:
        return Context(function=fn, provider=PROVIDER)
    limit_ms = _ctx_get(ctx, "time_limit_in_ms")
    memory = _ctx_get(ctx, "memory_limit_in_mb")
    return Context(
        request_id=str(_ctx_get(ctx, "request_id", "") or ""),
        function=fn,
        provider=PROVIDER,
        memory_mb=int(memory) if memory else None,
        deadline=(time.time() + float(limit_ms) / 1000.0) if limit_ms else None,
        raw=ctx,
    )


def to_native(result: Any, event: Event) -> Any:
    if event.http is not None:
        resp: Response = result
        status, headers, body, is_b64 = resp.render_for_gateway()
        if resp.cookies:
            headers["set-cookie"] = resp.cookies[0] if len(resp.cookies) == 1 else ", ".join(resp.cookies)
        return {"isBase64Encoded": is_b64, "statusCode": status, "headers": headers, "body": body}
    return result


def main_handler(native: Any, ctx: Any = None) -> Any:
    """SCF entrypoint - the generated ``index.main_handler`` points here."""
    event = to_event(native, ctx)
    context = to_context(ctx, event.function)
    return to_native(execute(event, context), event)


handler = main_handler
