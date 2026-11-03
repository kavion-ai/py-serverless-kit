"""Provider-neutral event model.

Every provider adapter converts its native payload into an :class:`Event`, so a
handler written against this module runs unchanged on any supported cloud.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, Union

from .errors import BadRequest

_MISSING = object()


class EventType:
    HTTP = "http"
    SCHEDULE = "schedule"
    QUEUE = "queue"
    STORAGE = "storage"
    TOPIC = "topic"
    INVOKE = "invoke"
    WORKFLOW = "workflow"
    SMTP = "smtp"  # a received e-mail (on-prem SMTP server); ``data`` is the parsed mail (runtime/mail.py)

    ALL = (HTTP, SCHEDULE, QUEUE, STORAGE, TOPIC, INVOKE, WORKFLOW, SMTP)


class Headers(Mapping[str, str]):
    """Case-insensitive, read-only header mapping.

    Multi-value headers are joined with ``", "`` (RFC 9110 section 5.3).
    """

    __slots__ = ("_data",)

    def __init__(self, raw: Union[Mapping[str, Any], List[Tuple[str, Any]], None] = None) -> None:
        self._data: Dict[str, str] = {}
        items = raw.items() if isinstance(raw, Mapping) else (raw or [])
        for key, value in items:
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                value = ", ".join(str(v) for v in value)
            k = str(key).lower()
            self._data[k] = f"{self._data[k]}, {value}" if k in self._data else str(value)

    def __getitem__(self, key: str) -> str:
        return self._data[key.lower()]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.lower() in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        return self._data.get(key.lower(), default)

    def to_dict(self) -> Dict[str, str]:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"Headers({self._data!r})"


def _decode_json(raw: Union[str, bytes], what: str) -> Any:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if raw == "":
        raise BadRequest(f"{what} is empty, expected JSON")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise BadRequest(f"{what} is not valid JSON", details=str(exc)) from exc


def parse_cookies(header: Optional[str]) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    if not header:
        return cookies
    for part in header.split(";"):
        if "=" in part:
            name, _, value = part.strip().partition("=")
            cookies[name] = value
    return cookies


@dataclass
class HttpRequest:
    method: str = "GET"
    path: str = "/"
    headers: Headers = field(default_factory=Headers)
    query: Dict[str, str] = field(default_factory=dict)
    multi_query: Dict[str, List[str]] = field(default_factory=dict)
    path_params: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    source_ip: Optional[str] = None
    route: Optional[str] = None

    def __post_init__(self) -> None:
        self.method = self.method.upper()
        if not isinstance(self.headers, Headers):
            self.headers = Headers(self.headers)
        if isinstance(self.body, str):
            self.body = self.body.encode("utf-8")
        elif self.body is None:
            self.body = b""
        if self.query and not self.multi_query:
            self.multi_query = {k: [v] for k, v in self.query.items()}

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    @property
    def cookies(self) -> Dict[str, str]:
        return parse_cookies(self.headers.get("cookie"))

    def text(self, encoding: str = "utf-8") -> str:
        return self.body.decode(encoding)

    def json(self, default: Any = _MISSING) -> Any:
        """Parse the body as JSON. Raises :class:`BadRequest` (HTTP 400) on bad input
        unless ``default`` is supplied."""
        try:
            return _decode_json(self.body, "Request body")
        except BadRequest:
            if default is not _MISSING:
                return default
            raise

    def form(self) -> Dict[str, str]:
        from urllib.parse import parse_qsl

        return dict(parse_qsl(self.text(), keep_blank_values=True))

    @staticmethod
    def decode_body(body: Any, is_base64: bool = False) -> bytes:
        if body is None:
            return b""
        if isinstance(body, (dict, list)):
            return json.dumps(body).encode("utf-8")
        if isinstance(body, bytes):
            return base64.b64decode(body) if is_base64 else body
        if is_base64:
            return base64.b64decode(body)
        return str(body).encode("utf-8")


@dataclass
class Record:
    """One message / object notification inside a batch event."""

    id: Optional[str] = None
    body: Any = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    # Storage-only fields.
    bucket: Optional[str] = None
    key: Optional[str] = None
    size: Optional[int] = None
    action: Optional[str] = None  # "created" | "deleted"
    raw: Any = None

    def text(self) -> str:
        if isinstance(self.body, bytes):
            return self.body.decode("utf-8")
        if isinstance(self.body, (dict, list)):
            return json.dumps(self.body)
        return "" if self.body is None else str(self.body)

    def json(self, default: Any = _MISSING) -> Any:
        if isinstance(self.body, (dict, list)):
            return self.body
        try:
            return _decode_json(self.text(), f"Record {self.id or ''} body".strip())
        except BadRequest:
            if default is not _MISSING:
                return default
            raise


@dataclass
class Event:
    type: str
    provider: str = "local"
    function: str = ""
    http: Optional[HttpRequest] = None
    records: List[Record] = field(default_factory=list)
    data: Any = None
    time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: Optional[str] = None
    raw: Any = None

    @property
    def is_http(self) -> bool:
        return self.type == EventType.HTTP

    @property
    def is_batch(self) -> bool:
        return self.type in (EventType.QUEUE, EventType.TOPIC, EventType.STORAGE)

    def json(self, default: Any = _MISSING) -> Any:
        """Best-effort JSON payload regardless of event type.

        * HTTP: the parsed request body
        * queue/topic/storage: the first record's parsed body
        * schedule/invoke/workflow: ``data``
        """
        if self.http is not None:
            return self.http.json(default) if default is not _MISSING else self.http.json()
        if self.records:
            return self.records[0].json(default) if default is not _MISSING else self.records[0].json()
        return self.data

    def __iter__(self) -> Iterator[Record]:
        return iter(self.records)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-friendly summary, handy for logging."""
        out: Dict[str, Any] = {
            "type": self.type,
            "provider": self.provider,
            "function": self.function,
            "time": self.time.isoformat(),
            "source": self.source,
        }
        if self.http is not None:
            out["http"] = {
                "method": self.http.method,
                "path": self.http.path,
                "query": self.http.query,
                "path_params": self.http.path_params,
            }
        if self.records:
            out["records"] = len(self.records)
        if self.data is not None:
            out["data"] = self.data
        return out

    def to_wire(self) -> Dict[str, Any]:
        """The full portable form sent to the Node.js worker (``pskit_runtime/worker.js``).

        Bodies that are bytes travel base64 encoded (``body_b64``); everything
        else must be JSON-serialisable (anything that isn't becomes its ``str``).
        """
        out: Dict[str, Any] = {
            "type": self.type,
            "provider": self.provider,
            "function": self.function,
            "time": self.time.isoformat(),
            "source": self.source,
            "data": _jsonable(self.data),
            "http": None,
            "records": [],
        }
        if self.http is not None:
            out["http"] = {
                "method": self.http.method,
                "path": self.http.path,
                "headers": self.http.headers.to_dict(),
                "query": dict(self.http.query),
                "multi_query": {k: list(v) for k, v in self.http.multi_query.items()},
                "path_params": dict(self.http.path_params),
                "body_b64": base64.b64encode(self.http.body).decode("ascii"),
                "source_ip": self.http.source_ip,
                "route": self.http.route,
            }
        for rec in self.records:
            binary = isinstance(rec.body, (bytes, bytearray))
            out["records"].append(
                {
                    "id": rec.id,
                    "body": None if binary else _jsonable(rec.body),
                    "body_b64": base64.b64encode(bytes(rec.body)).decode("ascii") if binary else None,
                    "attributes": _jsonable(rec.attributes),
                    "source": rec.source,
                    "bucket": rec.bucket,
                    "key": rec.key,
                    "size": rec.size,
                    "action": rec.action,
                }
            )
        return out


def _jsonable(value: Any) -> Any:
    """``value`` if JSON can carry it, else a JSON-friendly copy (bytes -> text, unknown -> str)."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def event_from_wire(data: Dict[str, Any]) -> Event:
    """Inverse of :meth:`Event.to_wire` (used by tests and Python-side tooling)."""
    http = None
    raw_http = data.get("http")
    if raw_http:
        body_b64 = raw_http.get("body_b64")
        http = HttpRequest(
            method=raw_http.get("method") or "GET",
            path=raw_http.get("path") or "/",
            headers=Headers(raw_http.get("headers") or {}),
            query=dict(raw_http.get("query") or {}),
            multi_query={k: list(v) for k, v in (raw_http.get("multi_query") or {}).items()},
            path_params=dict(raw_http.get("path_params") or {}),
            body=base64.b64decode(body_b64) if body_b64 else HttpRequest.decode_body(raw_http.get("body")),
            source_ip=raw_http.get("source_ip"),
            route=raw_http.get("route"),
        )
    records = []
    for rec in data.get("records") or []:
        body_b64 = rec.get("body_b64")
        records.append(
            Record(
                id=rec.get("id"),
                body=base64.b64decode(body_b64) if body_b64 else rec.get("body"),
                attributes=dict(rec.get("attributes") or {}),
                source=rec.get("source"),
                bucket=rec.get("bucket"),
                key=rec.get("key"),
                size=rec.get("size"),
                action=rec.get("action"),
            )
        )
    return Event(
        type=str(data.get("type") or EventType.INVOKE),
        provider=str(data.get("provider") or "local"),
        function=str(data.get("function") or ""),
        http=http,
        records=records,
        data=data.get("data"),
        time=parse_time(data.get("time")),
        source=data.get("source"),
    )


def parse_time(value: Any) -> datetime:
    """Parse the many timestamp shapes providers emit; fall back to *now*."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str) and value:
        text = value.strip()
        if text.isdigit():
            return parse_time(int(text))
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)
