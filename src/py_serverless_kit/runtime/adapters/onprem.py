"""On-premises adapter.

The host normally calls the dispatcher with a portable ``Event``. This module
is the bundle entrypoint for anything that invokes ``main(event, context)``
with a native payload: an HTTP request, a ``__pskit`` envelope, or a batch of
queue / topic / storage records.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

from ..context import Context
from ..event import Event, EventType, Headers, HttpRequest, Record
from ..response import dumps
from ._httpfn import decode_body, event_from_request, run
from .base import function_name, unwrap_envelope

PROVIDER = "onprem"


def to_request(event: Dict[str, Any]) -> Optional[HttpRequest]:
    http = event.get("http")
    if not isinstance(http, dict) or not http.get("method"):
        return None
    headers = dict(http.get("headers") or {})
    body = http.get("body")
    if body is None:
        plain = {key: value for key, value in event.items() if key != "http"}
        body = dumps(plain) if plain else None
    multi = parse_qs(str(http.get("queryString") or ""), keep_blank_values=True)
    is_b64 = http.get("isBase64Encoded")
    return HttpRequest(
        method=str(http["method"]),
        path=http.get("path") or "/",
        headers=Headers(headers),
        query={key: value[-1] for key, value in multi.items()},
        multi_query=multi,
        body=decode_body(body, headers, bool(is_b64) if is_b64 is not None else False),
        source_ip=str(headers.get("x-forwarded-for", "")).split(",")[0].strip() or None,
    )


def _records(kind: str, data: Any) -> Optional[List[Record]]:
    if kind not in (EventType.QUEUE, EventType.TOPIC, EventType.STORAGE):
        return None
    items = data if isinstance(data, list) else [data]
    records = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            records.append(Record(id=f"onprem-{index}", body=item, source="onprem"))
            continue
        records.append(
            Record(
                id=str(item.get("id") or item.get("messageId") or f"onprem-{index}"),
                body=item.get("body", item.get("data", item)),
                attributes=dict(item.get("attributes") or {}),
                bucket=item.get("bucket"),
                key=item.get("key"),
                size=item.get("size"),
                action=item.get("action") or "created",
                source="onprem",
            )
        )
    return records


def to_event(event: Dict[str, Any], fn: str) -> Event:
    req = to_request(event)
    if req is not None:
        return event_from_request(req, PROVIDER, fn, raw=event)
    wrapped = unwrap_envelope(event)
    if wrapped is not None:
        kind, data, meta = wrapped
        records = _records(kind, data)
        if records is not None:
            return Event(
                type=kind,
                provider=PROVIDER,
                function=fn,
                records=records,
                source=meta.get("source"),
                raw=event,
            )
        return Event(type=kind, provider=PROVIDER, function=fn, data=data, source=meta.get("source"), raw=event)
    native = event.get("type")
    if native in (EventType.QUEUE, EventType.TOPIC, EventType.STORAGE):
        native_kind = str(native)
        records = _records(native_kind, event.get("records") or event.get("Records") or [])
        return Event(
            type=native_kind, provider=PROVIDER, function=fn, records=records or [], source="onprem", raw=event
        )
    if event.get("method") and event.get("path"):
        # Flat HTTP shape, same fields ``to_request`` reads under ``http``.
        return to_event({"http": event}, fn)
    return Event(type=EventType.INVOKE, provider=PROVIDER, function=fn, data=event, raw=event)


def to_context(ctx: Any, fn: str) -> Context:
    remaining = getattr(ctx, "get_remaining_time_in_millis", None)
    return Context(
        request_id=str(getattr(ctx, "request_id", "") or ""),
        function=fn,
        provider=PROVIDER,
        deadline=(time.time() + remaining() / 1000.0) if callable(remaining) else None,
        raw=ctx,
        _remaining=remaining if callable(remaining) else None,
    )


def main(event: Optional[Dict[str, Any]] = None, context: Any = None) -> Dict[str, Any]:
    event = event or {}
    fn = function_name()
    status, headers, body, _ = run(to_event(event, fn), to_context(context, fn))
    return {"statusCode": status, "headers": headers, "body": body}
