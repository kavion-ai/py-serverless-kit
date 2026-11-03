"""Huawei Cloud FunctionGraph adapter.

Handles APIG (dedicated gateway) events, timer triggers, OBS triggers, SMN
topic triggers and direct invocation.
"""

from __future__ import annotations

import time
from typing import Any, Dict
from urllib.parse import unquote_plus

from ..context import Context
from ..dispatch import execute
from ..event import Event, EventType, Headers, HttpRequest, Record, parse_time
from ..response import Response
from .base import action_from, function_name, maybe_json, unwrap_envelope

PROVIDER = "huawei"


def _call(ctx: Any, method: str, default: Any = None) -> Any:
    fn = getattr(ctx, method, None)
    if callable(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001 - context helpers are best effort
            return default
    return default


def _http(evt: Dict[str, Any]) -> HttpRequest:
    rc = evt.get("requestContext") or {}
    query: Dict[str, str] = {}
    multi = {}
    for key, value in (evt.get("queryStringParameters") or {}).items():
        values = [str(v) for v in value] if isinstance(value, list) else [str(value)]
        multi[key] = values
        query[key] = values[-1] if values else ""
    return HttpRequest(
        method=evt.get("httpMethod", "GET"),
        path=evt.get("path") or "/",
        headers=Headers(evt.get("headers") or {}),
        query=query,
        multi_query=multi,
        path_params={k: str(v) for k, v in (evt.get("pathParameters") or {}).items()},
        body=HttpRequest.decode_body(evt.get("body"), bool(evt.get("isBase64Encoded"))),
        source_ip=rc.get("sourceIp"),
    )


def _obs(evt: Dict[str, Any], fn: str) -> Event:
    records = []
    for r in evt.get("Records") or []:
        obs = r.get("obs") or r.get("s3") or {}
        obj = obs.get("object") or {}
        records.append(
            Record(
                id=obj.get("sequencer"),
                bucket=(obs.get("bucket") or {}).get("name"),
                key=unquote_plus(obj.get("key", "")),
                size=obj.get("size"),
                action=action_from(r.get("eventName", "")),
                attributes={"event_name": r.get("eventName"), "etag": obj.get("eTag")},
                source="obs",
                raw=r,
            )
        )
    first = (evt.get("Records") or [{}])[0]
    return Event(
        type=EventType.STORAGE,
        provider=PROVIDER,
        function=fn,
        records=records,
        source="obs",
        time=parse_time(first.get("eventTime")),
        raw=evt,
    )


def _smn(evt: Dict[str, Any], fn: str) -> Event:
    records = []
    for r in evt.get("record") or []:
        smn = r.get("smn") or {}
        records.append(
            Record(
                id=smn.get("message_id"),
                body=smn.get("message"),
                attributes={"subject": smn.get("subject"), **(smn.get("message_attributes") or {})},
                source=smn.get("topic_urn"),
                raw=r,
            )
        )
    first = ((evt.get("record") or [{}])[0].get("smn")) or {}
    return Event(
        type=EventType.TOPIC,
        provider=PROVIDER,
        function=fn,
        records=records,
        source=first.get("topic_urn"),
        time=parse_time(first.get("timestamp")),
        raw=evt,
    )


def to_event(native: Any, ctx: Any = None) -> Event:
    fn = function_name(_call(ctx, "getFunctionName", "") or "")
    evt = maybe_json(native)
    wrapped = unwrap_envelope(evt)
    if wrapped is not None:
        kind, data, meta = wrapped
        return Event(type=kind, provider=PROVIDER, function=fn, data=data, source=meta.get("source"), raw=evt)
    if isinstance(evt, dict):
        if "httpMethod" in evt and ("requestContext" in evt or "path" in evt):
            return Event(type=EventType.HTTP, provider=PROVIDER, function=fn, http=_http(evt), raw=evt)
        if str(evt.get("trigger_type", "")).upper() == "TIMER":
            user_event = evt.get("user_event")
            inner = unwrap_envelope(user_event) if user_event else None
            return Event(
                type=EventType.SCHEDULE,
                provider=PROVIDER,
                function=fn,
                data=inner[1] if inner else (maybe_json(user_event) if user_event else None),
                time=parse_time(evt.get("time")),
                source=evt.get("trigger_name"),
                raw=evt,
            )
        records = evt.get("Records")
        if (
            isinstance(records, list)
            and records
            and isinstance(records[0], dict)
            and ("obs" in records[0] or "s3" in records[0])
        ):
            return _obs(evt, fn)
        smn = evt.get("record")
        if isinstance(smn, list) and smn and isinstance(smn[0], dict) and "smn" in smn[0]:
            return _smn(evt, fn)
    return Event(type=EventType.INVOKE, provider=PROVIDER, function=fn, data=evt, raw=native)


def to_context(ctx: Any, fn: str) -> Context:
    if ctx is None:
        return Context(function=fn, provider=PROVIDER)
    remaining = getattr(ctx, "getRemainingTimeInMilliSeconds", None)
    memory = _call(ctx, "getMemorySize")
    remaining_ms = _call(ctx, "getRemainingTimeInMilliSeconds")
    return Context(
        request_id=str(_call(ctx, "getRequestID", "") or ""),
        function=fn,
        provider=PROVIDER,
        memory_mb=int(memory) if memory else None,
        deadline=(time.time() + float(remaining_ms) / 1000.0) if remaining_ms else None,
        raw=ctx,
        _remaining=remaining if callable(remaining) else None,
    )


def to_native(result: Any, event: Event) -> Any:
    if event.http is not None:
        resp: Response = result
        status, headers, body, is_b64 = resp.render_for_gateway()
        if resp.cookies:
            headers["set-cookie"] = resp.cookies[0] if len(resp.cookies) == 1 else ", ".join(resp.cookies)
        return {"statusCode": status, "isBase64Encoded": is_b64, "headers": headers, "body": body}
    return result


def handler(native: Any, ctx: Any = None) -> Any:
    """FunctionGraph entrypoint - the generated ``index.handler`` points here."""
    event = to_event(native, ctx)
    context = to_context(ctx, event.function)
    return to_native(execute(event, context), event)
