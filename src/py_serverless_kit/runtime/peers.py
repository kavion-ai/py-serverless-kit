"""Function groups on other servers (on-prem ``provider.options.placement``): reach them over HTTP.

The host of every group gets the whole map in ``pskit_host.json``::

    "group": "gpu",
    "default_group": "api",
    "groups": {"api": {"url": "http://10.0.0.5:8080"}, "gpu": {"url": "http://10.0.0.7:8080"}},
    "function_groups": {"resize": {"group": "gpu", "timeout": 60}, "hello": {"group": "api", "timeout": 30}},
    "owners": {"queue:jobs": "gpu", "storage:uploads": "api", "topic:events": ["api", "gpu"]},
    "peer_token": "..."

A call goes to ``POST <url>/__pskit/peer/<function>`` with the event in the Node.js worker's wire format
(``Event.to_wire``); the answer is the worker's reply format (``kind``: http / batch / value, or an error with its
type, so workflow ``Retry`` / ``Catch`` rules match an error raised on another server by name). HTTP requests for a
route of another group are passed through as they are. A peer only runs its own functions (no second hop).
"""

from __future__ import annotations

import base64
import json
import socket
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .batch import BatchResult
from .event import Event, HttpRequest, event_from_wire
from .response import Response, dumps

PEER_PATH = "/__pskit/peer/"
HOP_HEADER = "x-pskit-peer"  # set on every call between groups; a peer never forwards such a call again
# Request headers that are not passed through when an HTTP request goes to another group.
_HOP_BY_HOP = ("connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "te", "trailer",
               "host", "content-length")


class PeerError(Exception):
    """The function failed on another group's host. ``error`` is its error type (for workflow retry / catch)."""

    def __init__(self, error_type: str, message: str, group: str = "") -> None:
        super().__init__(message)
        self.error = error_type or "Error"
        self.message = message
        self.group = group

    def __str__(self) -> str:
        return self.message


class PeerUnavailable(PeerError):
    """The other group's host could not be reached."""

    def __init__(self, group: str, url: str, reason: Any) -> None:
        super().__init__("PeerUnavailable", f"group {group} ({url}) is not reachable: {reason}", group)


def encode_result(result: Any) -> Dict[str, Any]:
    """A function's result as a reply (the inverse of :func:`decode_result`)."""
    if isinstance(result, Response):
        status, headers, body = result.render()
        return {"ok": True, "kind": "http", "status": status, "headers": dict(headers),
                "cookies": list(result.cookies or []), "body_b64": base64.b64encode(body).decode("ascii")}
    if isinstance(result, BatchResult):
        return {"ok": True, "kind": "batch", "failed": [str(i) for i in result.failed]}
    return {"ok": True, "kind": "value", "value": result}


def encode_error(exc: BaseException) -> Dict[str, Any]:
    name = getattr(exc, "error", None) or type(exc).__name__
    return {"ok": False, "error": {"type": str(name), "message": str(exc)}}


def decode_result(reply: Dict[str, Any], group: str = "") -> Any:
    if not isinstance(reply, dict):
        raise PeerError("PeerProtocolError", f"group {group} answered {reply!r}", group)
    if not reply.get("ok"):
        err = reply.get("error") or {}
        raise PeerError(str(err.get("type") or "Error"), str(err.get("message") or ""), group)
    kind = reply.get("kind")
    if kind == "http":
        resp = Response(int(reply.get("status") or 200), base64.b64decode(reply.get("body_b64") or ""),
                        {str(k): str(v) for k, v in (reply.get("headers") or {}).items()})
        resp.cookies = [str(c) for c in reply.get("cookies") or []]
        return resp
    if kind == "batch":
        return BatchResult(failed=[str(i) for i in reply.get("failed") or []])
    return reply.get("value")


class Peers:
    """The other groups of this project, as ``pskit_host.json`` lists them."""

    def __init__(self, spec: Dict[str, Any]) -> None:
        self.group = str(spec.get("group") or "")
        self.default = str(spec.get("default_group") or self.group)
        self.urls = {str(g): str((v or {}).get("url") or "").rstrip("/") for g, v in (spec.get("groups") or {}).items()}
        self.functions = {str(f): dict(v or {}) for f, v in (spec.get("function_groups") or {}).items()}
        self.owners: Dict[str, Any] = dict(spec.get("owners") or {})
        self.token = str(spec.get("peer_token") or "")

    @classmethod
    def from_spec(cls, spec: Dict[str, Any]) -> Optional[Peers]:
        return cls(spec) if spec.get("groups") and spec.get("group") else None

    # ------------------------------------------------------------------ where things are
    def group_of(self, function: str) -> str:
        return str((self.functions.get(function) or {}).get("group") or "")

    def remote(self, function: str) -> Optional[str]:
        """The group that runs ``function`` when it is not this one (None: here, or unknown)."""
        group = self.group_of(function)
        return group if group and group != self.group and group in self.urls else None

    def owner(self, kind: str, name: str) -> Optional[str]:
        """The group that keeps built-in ``kind`` ``name`` when it is another one (None: here, or not routed)."""
        group = self.owners.get(f"{kind}:{name}")
        if isinstance(group, str) and group and group != self.group and group in self.urls:
            return group
        return None

    def subscribers(self, kind: str, name: str) -> List[str]:
        """Groups with a function on topic / SMTP server ``name``; an unknown name stays with this group."""
        groups = self.owners.get(f"{kind}:{name}")
        if not isinstance(groups, list):
            return [self.group]
        return [g for g in groups if g == self.group or g in self.urls] or [self.default]

    def timeout(self, function: str) -> float:
        return float((self.functions.get(function) or {}).get("timeout") or 30) + 30.0

    # ------------------------------------------------------------------ HTTP
    def request(self, group: str, method: str, path: str, body: Optional[bytes] = None,
                headers: Optional[Dict[str, str]] = None, timeout: float = 60.0) -> Tuple[int, Dict[str, str], bytes]:
        """One call to ``group``'s host: ``(status, headers, body)`` for any status. While the host cannot be
        reached at all (it restarts during a deploy) it is retried for about 8 s; a request that reached it is
        never sent twice."""
        url = self.urls.get(group) or ""
        if not url:
            raise PeerUnavailable(group, "?", "unknown group")
        sent = {k: v for k, v in (headers or {}).items() if v}
        sent[HOP_HEADER] = self.group or "1"
        if self.token:
            sent["x-pskit-token"] = self.token
        for delay in (0.5, 1.0, 2.0, 4.0, 0.0):
            req = Request(url + path, data=body, method=method, headers=sent)  # noqa: S310 - our own peers
            try:
                with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                    return resp.status, _headers(resp.headers), resp.read()
            except HTTPError as exc:
                return exc.code, _headers(exc.headers), exc.read()
            except URLError as exc:
                if not delay or not isinstance(exc.reason, (ConnectionError, socket.gaierror, socket.timeout)):
                    raise PeerUnavailable(group, url, exc.reason) from None
            except (ConnectionError, socket.timeout) as exc:
                if not delay:
                    raise PeerUnavailable(group, url, exc) from None
            time.sleep(delay)
        raise PeerUnavailable(group, url, "no answer")  # pragma: no cover

    def call(self, group: str, method: str, path: str, payload: Any = None, raw: Optional[bytes] = None,
             timeout: float = 60.0) -> Any:
        """JSON in, JSON out; a status of 300 or more raises."""
        body = raw if raw is not None else (dumps(payload).encode("utf-8") if payload is not None else None)
        kind = "application/octet-stream" if raw is not None else "application/json"
        status, _headers, data = self.request(group, method, path, body, {"content-type": kind}, timeout)
        if status >= 300:
            text = data[:300].decode("utf-8", "replace")
            raise PeerError("PeerError", f"group {group} answered {status} to {method} {path}: {text}", group)
        return json.loads(data.decode("utf-8") or "null") if data else None

    def invoke(self, function: str, event: Event, group: Optional[str] = None) -> Any:
        """Run ``function`` on its group's host with ``event``; its result, or its error raised here."""
        group = group or self.remote(function) or self.group_of(function)
        event.function = function
        body = dumps(event.to_wire()).encode("utf-8")
        status, _headers, data = self.request(group, "POST", PEER_PATH + quote(function, safe=""), body,
                                              {"content-type": "application/json"}, self.timeout(function))
        try:
            reply = json.loads(data.decode("utf-8") or "null")
        except ValueError:
            reply = None
        if not isinstance(reply, dict) or ("ok" not in reply):
            text = data[:300].decode("utf-8", "replace")
            raise PeerError("PeerError", f"group {group} answered {status} for {function}: {text}", group)
        return decode_result(reply, group)

    def forward_http(self, group: str, req: HttpRequest, timeout: float) -> Response:
        """Pass an HTTP request for another group's route through unchanged; its answer as a Response."""
        query = ""
        if req.multi_query:
            from urllib.parse import urlencode

            query = "?" + urlencode([(k, v) for k, vs in req.multi_query.items() for v in vs])
        headers = {k: v for k, v in req.headers.to_dict().items() if k.lower() not in _HOP_BY_HOP}
        if req.source_ip:
            prior = headers.get("x-forwarded-for")
            headers["x-forwarded-for"] = f"{prior}, {req.source_ip}" if prior else req.source_ip
        body = req.body if req.body or req.method in ("POST", "PUT", "PATCH") else None
        status, reply, data = self.request(group, req.method, quote(req.path, safe="/%:@!$&'()*+,;=-._~") + query,
                                           body, headers, timeout)
        passed = {k: v for k, v in reply.items() if k.lower() not in _HOP_BY_HOP and k.lower() != "set-cookie"
                  and k.lower() not in ("date", "server")}
        resp = Response(status, data, passed)
        resp.cookies = [c for k, v in reply.items() if k.lower() == "set-cookie" for c in v.split("\n") if c]
        return resp


def _headers(message: Any) -> Dict[str, str]:
    """Response headers as a dict; several Set-Cookie headers are kept, one per line."""
    out: Dict[str, str] = {}
    get_all = getattr(message, "get_all", None)
    for key in list(message.keys()) if message is not None else []:
        if key.lower() == "set-cookie" and callable(get_all):
            out["set-cookie"] = "\n".join(get_all(key) or [])
        else:
            out[key] = message[key]
    return out


def run_peer_call(host: Any, function: str, raw: bytes) -> Dict[str, Any]:
    """``POST /__pskit/peer/<function>`` on the host that runs ``function``: the reply to send back."""
    try:
        data = json.loads(raw.decode("utf-8") or "null")
    except ValueError:
        return encode_error(ValueError("the peer call body must be JSON"))
    if not isinstance(data, dict):
        return encode_error(ValueError("the peer call body must be an event"))
    event = event_from_wire(data)
    try:
        return encode_result(host.invoke(function, event, from_peer=True))
    except Exception as exc:  # noqa: BLE001 - the caller raises it again with the same error type
        return encode_error(exc)
