"""IBM Cloud Code Engine functions adapter.

Code Engine calls ``main(params)``; HTTP request data arrives in ``__ce_*`` keys
(``__ow_*`` from the older Cloud Functions / OpenWhisk platform is accepted too)
and the function returns ``{"statusCode", "headers", "body"}``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

from ..context import Context
from ..event import Event, EventType, Headers, HttpRequest
from ..response import dumps
from ._httpfn import decode_body, event_from_request, run
from .base import function_name, unwrap_envelope

PROVIDER = "ibm"
_PREFIXES = ("__ce_", "__ow_")


def _get(params: Dict[str, Any], key: str) -> Any:
    for prefix in _PREFIXES:
        if prefix + key in params:
            return params[prefix + key]
    return None


def _query(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return {str(k): v if isinstance(v, list) else [str(v)] for k, v in raw.items()}
    if isinstance(raw, str) and raw:
        return parse_qs(raw.lstrip("?"), keep_blank_values=True)
    return {}


def to_request(params: Dict[str, Any]) -> Optional[HttpRequest]:
    method = _get(params, "method")
    if not method:
        return None
    headers = dict(_get(params, "headers") or {})
    body = _get(params, "body")
    if body is None:
        # Code Engine merges JSON bodies into params; rebuild it from the plain keys.
        plain = {k: v for k, v in params.items() if not k.startswith(_PREFIXES)}
        body = dumps(plain) if plain else None
    multi = _query(_get(params, "query"))
    return HttpRequest(
        method=str(method),
        path=_get(params, "path") or "/",
        headers=Headers(headers),
        query={k: v[-1] for k, v in multi.items() if v},
        multi_query=multi,
        body=decode_body(body, headers),
        source_ip=headers.get("x-forwarded-for", "").split(",")[0].strip() or None,
    )


def main(params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    params = params or {}
    fn = function_name()
    req = to_request(params)
    if req is None:
        # Direct invocation without HTTP metadata: params are the payload.
        wrapped = unwrap_envelope(params)
        if wrapped is not None:
            event = Event(type=wrapped[0], provider=PROVIDER, function=fn, data=wrapped[1], raw=params)
        else:
            event = Event(type=EventType.INVOKE, provider=PROVIDER, function=fn, data=params, raw=params)
    else:
        event = event_from_request(req, PROVIDER, fn, raw=params)
    context = Context(
        request_id=os.environ.get("CE_REQUEST_ID", "") or headers_id(params),
        function=fn,
        provider=PROVIDER,
        raw=params,
    )
    status, headers, body, _is_b64 = run(event, context)
    return {"statusCode": status, "headers": headers, "body": body}


def headers_id(params: Dict[str, Any]) -> str:
    headers = _get(params, "headers") or {}
    for key in ("x-request-id", "X-Request-Id", "x-ce-request-id"):
        if key in headers:
            return str(headers[key])
    import uuid

    return str(uuid.uuid4())
