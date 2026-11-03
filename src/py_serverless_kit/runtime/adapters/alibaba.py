"""Alibaba Cloud Function Compute 3.0 adapter.

Handles HTTP triggers (event handler mode), timer triggers, OSS triggers,
MNS topic triggers and direct invocation. FC passes the event as ``bytes``.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from ..context import Context
from ..dispatch import execute
from ..event import Event, EventType, Headers, HttpRequest, Record, parse_time
from ..response import Response
from .base import action_from, function_name, maybe_json, unwrap_envelope

PROVIDER = "alibaba"


def _http(evt: Dict[str, Any]) -> HttpRequest:
    rc = evt.get("requestContext") or {}
    http = rc.get("http") or {}
    query: Dict[str, Any] = {}
    multi: Dict[str, List[str]] = {}
    for key, value in (evt.get("queryParameters") or {}).items():
        values = [str(v) for v in value] if isinstance(value, list) else [str(value)]
        multi[key] = values
        query[key] = values[-1] if values else ""
    return HttpRequest(
        method=http.get("method", "GET"),
        path=evt.get("rawPath") or http.get("path") or "/",
        headers=Headers(evt.get("headers") or {}),
        query=query,
        multi_query=multi,
        body=HttpRequest.decode_body(evt.get("body"), bool(evt.get("isBase64Encoded"))),
        source_ip=http.get("sourceIp"),
    )


def _oss(evt: Dict[str, Any], fn: str) -> Event:
    records = []
    for r in evt.get("events") or []:
        oss = r.get("oss") or {}
        obj = oss.get("object") or {}
        records.append(
            Record(
                id=(r.get("responseElements") or {}).get("requestId"),
                bucket=(oss.get("bucket") or {}).get("name"),
                key=obj.get("key"),
                size=obj.get("size"),
                action=action_from(r.get("eventName", "")),
                attributes={"event_name": r.get("eventName"), "etag": obj.get("eTag")},
                source="acs:oss",
                raw=r,
            )
        )
    first = (evt.get("events") or [{}])[0]
    return Event(
        type=EventType.STORAGE,
        provider=PROVIDER,
        function=fn,
        records=records,
        source="acs:oss",
        time=parse_time(first.get("eventTime")),
        raw=evt,
    )


def to_event(native: Any, ctx: Any = None) -> Event:
    fn = function_name(getattr(getattr(ctx, "function", None), "name", "") or "")
    evt = maybe_json(native)
    wrapped = unwrap_envelope(evt)
    if wrapped is not None:
        kind, data, meta = wrapped
        return Event(type=kind, provider=PROVIDER, function=fn, data=data, source=meta.get("source"), raw=evt)
    if isinstance(evt, dict):
        rc = evt.get("requestContext")
        if isinstance(rc, dict) and isinstance(rc.get("http"), dict):
            return Event(type=EventType.HTTP, provider=PROVIDER, function=fn, http=_http(evt), raw=evt)
        if "triggerTime" in evt and "triggerName" in evt:
            payload = evt.get("payload")
            inner = unwrap_envelope(payload) if payload else None
            return Event(
                type=EventType.SCHEDULE,
                provider=PROVIDER,
                function=fn,
                data=inner[1] if inner else maybe_json(payload) if payload else None,
                time=parse_time(evt.get("triggerTime")),
                source=evt.get("triggerName"),
                raw=evt,
            )
        events = evt.get("events")
        if isinstance(events, list) and events and isinstance(events[0], dict) and "oss" in events[0]:
            return _oss(evt, fn)
        if "TopicName" in evt and "Message" in evt:  # MNS topic, JSON notify format
            record = Record(
                id=evt.get("MessageId"),
                body=evt.get("Message"),
                attributes={k: v for k, v in evt.items() if k not in ("Message",)},
                source=evt.get("TopicOwner", "") + ":" + evt.get("TopicName", ""),
                raw=evt,
            )
            return Event(
                type=EventType.TOPIC,
                provider=PROVIDER,
                function=fn,
                records=[record],
                source=evt.get("TopicName"),
                time=parse_time(evt.get("PublishTime")),
                raw=evt,
            )
    return Event(type=EventType.INVOKE, provider=PROVIDER, function=fn, data=evt, raw=native)


def to_context(ctx: Any, fn: str) -> Context:
    if ctx is None:
        return Context(function=fn, provider=PROVIDER)
    func = getattr(ctx, "function", None)
    memory = getattr(func, "memory", None)
    timeout = getattr(func, "timeout", None)
    return Context(
        request_id=getattr(ctx, "request_id", "") or "",
        function=fn,
        provider=PROVIDER,
        region=getattr(ctx, "region", "") or "",
        memory_mb=int(memory) if memory else None,
        deadline=(time.time() + float(timeout)) if timeout else None,
        raw=ctx,
    )


def to_native(result: Any, event: Event) -> Any:
    if event.http is not None:
        resp: Response = result
        status, headers, body, is_b64 = resp.render_for_gateway()
        if resp.cookies:
            headers["set-cookie"] = resp.cookies[0] if len(resp.cookies) == 1 else ", ".join(resp.cookies)
        return {"statusCode": status, "headers": headers, "body": body, "isBase64Encoded": is_b64}
    return result


def handler(native: Any, ctx: Any = None) -> Any:
    """FC 3.0 entrypoint - the generated ``index.handler`` points here."""
    event = to_event(native, ctx)
    context = to_context(ctx, event.function)
    return to_native(execute(event, context), event)
