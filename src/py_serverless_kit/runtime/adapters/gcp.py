"""Google Cloud Functions (2nd gen) adapter.

Two entrypoints are exposed through the generated ``main.py``:

* :func:`http` - ``@functions_framework.http``; receives a Flask request. A body
  carrying the ``__pskit`` envelope (Cloud Scheduler, Cloud Workflows,
  ``invoke()``) is dispatched as a *non-HTTP* event and answered with the raw
  JSON result, or a 500 ``{"errorType", "cause"}`` that the workflow compiler
  understands.
* :func:`cloud_event` - ``@functions_framework.cloud_event``; Pub/Sub
  ``messagePublished`` (queue / topic) and Cloud Storage object events.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..context import Context
from ..dispatch import execute
from ..event import Event, EventType, Headers, HttpRequest, Record, parse_time
from ..response import Response, dumps
from .base import action_from, b64_text, function_name, unwrap_envelope

PROVIDER = "gcp"
_JSON = "application/json"


def _context(fn: str, request_id: Optional[str] = None, raw: Any = None) -> Context:
    return Context(request_id=request_id or str(uuid.uuid4()), function=fn, provider=PROVIDER, raw=raw)


def _request_id(headers: Any) -> Optional[str]:
    for key in ("Function-Execution-Id", "X-Cloud-Trace-Context"):
        value = headers.get(key) if headers is not None else None
        if value:
            return str(value).split("/")[0]
    return None


# ------------------------------------------------------------------ HTTP


def to_http_event(request: Any, fn: str) -> Event:
    headers = dict(request.headers.items()) if hasattr(request.headers, "items") else dict(request.headers or {})
    args = getattr(request, "args", None) or {}
    multi: Dict[str, List[str]] = {}
    if hasattr(args, "getlist"):
        multi = {k: list(args.getlist(k)) for k in args.keys()}
    query = {k: (v[-1] if v else "") for k, v in multi.items()} if multi else dict(args)
    req = HttpRequest(
        method=request.method,
        path=request.path or "/",
        headers=Headers(headers),
        query=query,
        multi_query=multi or {k: [v] for k, v in query.items()},
        body=request.get_data() or b"",
        source_ip=headers.get("X-Forwarded-For", "").split(",")[0].strip() or getattr(request, "remote_addr", None),
    )
    return Event(type=EventType.HTTP, provider=PROVIDER, function=fn, http=req, raw=request)


def _render(resp: Response) -> Tuple[bytes, int, List[Tuple[str, str]]]:
    status, headers, body = resp.render()
    items = list(headers.items()) + [("set-cookie", c) for c in resp.cookies]
    return body, status, items


def http(request: Any) -> Tuple[bytes, int, Any]:
    fn = function_name()
    body = request.get_data() or b""
    req_id = _request_id(request.headers)
    wrapped = unwrap_envelope(body) if body[:1] == b"{" else None
    if wrapped is not None:
        kind, data, meta = wrapped
        event = Event(type=kind, provider=PROVIDER, function=fn, data=data, source=meta.get("source"), raw=request)
        try:
            result = execute(event, _context(fn, req_id, request))
        except Exception as exc:  # noqa: BLE001 - reported to the caller (workflow / scheduler)
            payload = {"errorType": type(exc).__name__, "cause": str(exc)}
            return dumps(payload).encode("utf-8"), 500, [("content-type", _JSON)]
        return dumps(result).encode("utf-8"), 200, [("content-type", _JSON)]
    event = to_http_event(request, fn)
    return _render(execute(event, _context(fn, req_id, request)))


# ------------------------------------------------------------------ CloudEvents


def _ce_attr(ce: Any, key: str, default: Any = None) -> Any:
    try:
        value = ce[key]
    except (KeyError, TypeError, IndexError):
        value = None
    if value is None:
        value = getattr(ce, key, None)
    return default if value is None else value


def _ce_data(ce: Any) -> Any:
    data = getattr(ce, "data", None)
    if data is None and isinstance(ce, dict):
        data = ce.get("data")
    if isinstance(data, (bytes, str)):
        try:
            data = json.loads(data)
        except ValueError:
            pass
    return data


def _storage_wanted(key: str) -> bool:
    prefix = os.environ.get("PSKIT_STORAGE_PREFIX", "")
    suffix = os.environ.get("PSKIT_STORAGE_SUFFIX", "")
    return key.startswith(prefix) and key.endswith(suffix)


def to_cloud_event(ce: Any, fn: str = "") -> Optional[Event]:
    """Translate a CloudEvent; returns ``None`` when filtered out (storage prefix/suffix)."""
    ce_type = str(_ce_attr(ce, "type", ""))
    source = _ce_attr(ce, "source")
    when = parse_time(_ce_attr(ce, "time"))
    data = _ce_data(ce) or {}
    if ce_type.startswith("google.cloud.pubsub.topic"):
        msg = data.get("message") or {}
        body = b64_text(msg.get("data"))
        wrapped = unwrap_envelope(body) if isinstance(body, str) else None
        if wrapped is not None:  # Cloud Scheduler -> Pub/Sub target
            kind, payload, meta = wrapped
            return Event(
                type=kind,
                provider=PROVIDER,
                function=fn,
                data=payload,
                time=when,
                source=meta.get("source", source),
                raw=ce,
            )
        kind = EventType.QUEUE if os.environ.get("PSKIT_TRIGGER_KIND") == "queue" else EventType.TOPIC
        record = Record(
            id=msg.get("messageId") or msg.get("message_id") or _ce_attr(ce, "id"),
            body=body,
            attributes=dict(msg.get("attributes") or {}),
            source=data.get("subscription") or source,
            raw=msg,
        )
        return Event(type=kind, provider=PROVIDER, function=fn, records=[record], time=when, source=source, raw=ce)
    if ce_type.startswith("google.cloud.storage.object"):
        key = data.get("name", "")
        if not _storage_wanted(key):
            return None
        size = data.get("size")
        record = Record(
            id=str(data.get("generation") or _ce_attr(ce, "id") or ""),
            bucket=data.get("bucket"),
            key=key,
            size=int(size) if size is not None and size != "" else None,
            action=action_from(ce_type.rsplit(".", 1)[-1]),
            attributes={"content_type": data.get("contentType"), "event_type": ce_type},
            source=source,
            raw=data,
        )
        return Event(
            type=EventType.STORAGE, provider=PROVIDER, function=fn, records=[record], time=when, source=source, raw=ce
        )
    return Event(type=EventType.INVOKE, provider=PROVIDER, function=fn, data=data, time=when, source=source, raw=ce)


def cloud_event(ce: Any) -> Any:
    fn = function_name()
    event = to_cloud_event(ce, fn)
    if event is None:
        return None
    return execute(event, _context(fn, str(_ce_attr(ce, "id", "")) or None, ce))
