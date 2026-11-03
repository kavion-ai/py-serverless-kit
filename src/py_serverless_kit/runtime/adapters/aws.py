"""AWS Lambda adapter.

Handles API Gateway HTTP API (payload v2), REST API / ALB (payload v1),
Lambda Function URLs, SQS, SNS, S3, EventBridge, Step Functions and direct
invocation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from urllib.parse import unquote_plus

from ..batch import BatchResult
from ..context import Context
from ..dispatch import execute
from ..event import Event, EventType, Headers, HttpRequest, Record, parse_time
from ..response import Response
from .base import action_from, function_name, maybe_json, unwrap_envelope

PROVIDER = "aws"


def _http_v2(evt: Dict[str, Any]) -> HttpRequest:
    rc = evt.get("requestContext") or {}
    http = rc.get("http") or {}
    headers = dict(evt.get("headers") or {})
    if evt.get("cookies"):
        headers["cookie"] = "; ".join(evt["cookies"])
    query = dict(evt.get("queryStringParameters") or {})
    multi = {k: v.split(",") for k, v in query.items()}
    return HttpRequest(
        method=http.get("method", "GET"),
        path=evt.get("rawPath") or http.get("path") or "/",
        headers=Headers(headers),
        query=query,
        multi_query=multi,
        path_params=dict(evt.get("pathParameters") or {}),
        body=HttpRequest.decode_body(evt.get("body"), bool(evt.get("isBase64Encoded"))),
        source_ip=http.get("sourceIp"),
        route=(evt.get("routeKey") or "").split(" ", 1)[-1] or None,
    )


def _http_v1(evt: Dict[str, Any]) -> HttpRequest:
    rc = evt.get("requestContext") or {}
    multi_headers = evt.get("multiValueHeaders") or {}
    headers: Dict[str, Any] = dict(multi_headers) if multi_headers else dict(evt.get("headers") or {})
    multi_query = {k: list(v) for k, v in (evt.get("multiValueQueryStringParameters") or {}).items()}
    query = dict(evt.get("queryStringParameters") or {})
    if not query and multi_query:
        query = {k: v[-1] for k, v in multi_query.items()}
    return HttpRequest(
        method=evt.get("httpMethod", "GET"),
        path=evt.get("path") or "/",
        headers=Headers(headers),
        query=query,
        multi_query=multi_query or {k: [v] for k, v in query.items()},
        path_params=dict(evt.get("pathParameters") or {}),
        body=HttpRequest.decode_body(evt.get("body"), bool(evt.get("isBase64Encoded"))),
        source_ip=(rc.get("identity") or {}).get("sourceIp"),
        route=evt.get("resource"),
    )


def _records(evt: Dict[str, Any]) -> Optional[Event]:
    records = evt.get("Records")
    if not isinstance(records, list) or not records:
        return None
    first = records[0]
    source = first.get("eventSource") or first.get("EventSource") or ""
    out: List[Record] = []
    if source == "aws:sqs":
        for r in records:
            out.append(
                Record(
                    id=r.get("messageId"),
                    body=r.get("body"),
                    attributes={
                        **(r.get("attributes") or {}),
                        **{k: v.get("stringValue") for k, v in (r.get("messageAttributes") or {}).items()},
                    },
                    source=r.get("eventSourceARN"),
                    raw=r,
                )
            )
        return Event(type=EventType.QUEUE, provider=PROVIDER, records=out, source=first.get("eventSourceARN"), raw=evt)
    if source == "aws:sns":
        for r in records:
            sns = r.get("Sns") or {}
            out.append(
                Record(
                    id=sns.get("MessageId"),
                    body=sns.get("Message"),
                    attributes={k: v.get("Value") for k, v in (sns.get("MessageAttributes") or {}).items()},
                    source=sns.get("TopicArn"),
                    raw=r,
                )
            )
        return Event(
            type=EventType.TOPIC,
            provider=PROVIDER,
            records=out,
            source=(first.get("Sns") or {}).get("TopicArn"),
            time=parse_time((first.get("Sns") or {}).get("Timestamp")),
            raw=evt,
        )
    if source == "aws:s3":
        for r in records:
            s3 = r.get("s3") or {}
            obj = s3.get("object") or {}
            out.append(
                Record(
                    id=obj.get("sequencer"),
                    bucket=(s3.get("bucket") or {}).get("name"),
                    key=unquote_plus(obj.get("key", "")),
                    size=obj.get("size"),
                    action=action_from(r.get("eventName", "")),
                    attributes={"etag": obj.get("eTag"), "event_name": r.get("eventName")},
                    source="aws:s3",
                    raw=r,
                )
            )
        return Event(
            type=EventType.STORAGE,
            provider=PROVIDER,
            records=out,
            source="aws:s3",
            time=parse_time(first.get("eventTime")),
            raw=evt,
        )
    return None


def to_event(evt: Any, ctx: Any = None) -> Event:
    fn = function_name(getattr(ctx, "function_name", "") or "")
    wrapped = unwrap_envelope(evt)
    if wrapped is not None:
        kind, data, meta = wrapped
        return Event(type=kind, provider=PROVIDER, function=fn, data=data, source=meta.get("source"), raw=evt)
    if isinstance(evt, dict):
        rc = evt.get("requestContext")
        if isinstance(rc, dict) and isinstance(rc.get("http"), dict):
            return Event(type=EventType.HTTP, provider=PROVIDER, function=fn, http=_http_v2(evt), raw=evt)
        if "httpMethod" in evt:
            return Event(type=EventType.HTTP, provider=PROVIDER, function=fn, http=_http_v1(evt), raw=evt)
        batch = _records(evt)
        if batch is not None:
            batch.function = fn
            return batch
        if evt.get("source") == "aws.events" or evt.get("detail-type") == "Scheduled Event":
            return Event(
                type=EventType.SCHEDULE,
                provider=PROVIDER,
                function=fn,
                data=evt.get("detail"),
                time=parse_time(evt.get("time")),
                source=evt.get("source"),
                raw=evt,
            )
    return Event(type=EventType.INVOKE, provider=PROVIDER, function=fn, data=maybe_json(evt), raw=evt)


def to_context(ctx: Any, fn: str) -> Context:
    if ctx is None:
        return Context(function=fn, provider=PROVIDER)
    remaining = getattr(ctx, "get_remaining_time_in_millis", None)
    memory = getattr(ctx, "memory_limit_in_mb", None)
    return Context(
        request_id=getattr(ctx, "aws_request_id", "") or "",
        function=fn,
        provider=PROVIDER,
        memory_mb=int(memory) if memory else None,
        deadline=(time.time() + remaining() / 1000.0) if callable(remaining) else None,
        raw=ctx,
        _remaining=remaining if callable(remaining) else None,
    )


def to_native(result: Any, event: Event) -> Any:
    if event.http is not None:
        resp: Response = result
        status, headers, body, is_b64 = resp.render_for_gateway()
        out: Dict[str, Any] = {"statusCode": status, "headers": headers, "body": body, "isBase64Encoded": is_b64}
        if resp.cookies:
            if (event.raw or {}).get("version") == "2.0":
                out["cookies"] = list(resp.cookies)
            else:
                out["multiValueHeaders"] = {"set-cookie": list(resp.cookies)}
        return out
    if isinstance(result, BatchResult):
        return {"batchItemFailures": [{"itemIdentifier": rid} for rid in result.failed]}
    return result


def handler(evt: Any, ctx: Any = None) -> Any:
    """Lambda entrypoint - the generated ``pskit_entry.handler`` points here."""
    event = to_event(evt, ctx)
    context = to_context(ctx, event.function)
    result = execute(event, context)
    return to_native(result, event)
