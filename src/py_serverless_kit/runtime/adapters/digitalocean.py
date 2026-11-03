"""DigitalOcean Functions adapter (``main(event, context)``).

Web functions deployed with ``web: raw`` receive ``event["http"]`` with
``method``, ``path``, ``headers``, ``queryString``, ``body`` and
``isBase64Encoded``. Scheduled triggers deliver their ``withBody`` payload,
which the CLI fills with the ``__pskit`` envelope.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

from ..context import Context
from ..event import Event, EventType, Headers, HttpRequest
from ..response import dumps
from ._httpfn import decode_body, event_from_request, run
from .base import function_name, unwrap_envelope

PROVIDER = "digitalocean"


def to_request(event: Dict[str, Any]) -> Optional[HttpRequest]:
    http = event.get("http")
    if not isinstance(http, dict) or not http.get("method"):
        return None
    headers = dict(http.get("headers") or {})
    body: Any = http.get("body")
    if body is None:
        # `web: true` (non-raw) merges body params into the event.
        plain = {k: v for k, v in event.items() if k != "http" and not k.startswith("__ow_")}
        body = dumps(plain) if plain else None
    is_b64 = http.get("isBase64Encoded")
    multi = parse_qs(str(http.get("queryString") or ""), keep_blank_values=True)
    return HttpRequest(
        method=str(http["method"]),
        path=http.get("path") or "/",
        headers=Headers(headers),
        query={k: v[-1] for k, v in multi.items()},
        multi_query=multi,
        body=decode_body(body, headers, bool(is_b64) if is_b64 is not None else False),
        source_ip=str(headers.get("x-forwarded-for", "")).split(",")[0].strip() or None,
    )


def to_event(event: Dict[str, Any], fn: str) -> Event:
    req = to_request(event)
    if req is not None:
        return event_from_request(req, PROVIDER, fn, raw=event)
    wrapped = unwrap_envelope(event)
    if wrapped is not None:
        kind, data, meta = wrapped
        return Event(type=kind, provider=PROVIDER, function=fn, data=data, source=meta.get("source"), raw=event)
    return Event(type=EventType.INVOKE, provider=PROVIDER, function=fn, data=event, raw=event)


def to_context(ctx: Any, fn: str) -> Context:
    remaining = getattr(ctx, "get_remaining_time_in_millis", None)
    return Context(
        request_id=str(getattr(ctx, "activation_id", "") or getattr(ctx, "request_id", "") or ""),
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
