"""Provider-neutral HTTP response model."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

_TEXT_PREFIXES = ("text/",)
_TEXT_TYPES = (
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-www-form-urlencoded",
    "image/svg+xml",
)


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (UUID, bytes)):
        return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if hasattr(value, "model_dump"):  # pydantic v2
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dumps(value: Any) -> str:
    return json.dumps(value, default=json_default, separators=(",", ":"))


def is_text_content_type(content_type: str) -> bool:
    ct = content_type.split(";")[0].strip().lower()
    return ct.startswith(_TEXT_PREFIXES) or ct in _TEXT_TYPES or ct.endswith("+json")


@dataclass
class Response:
    status: int = 200
    body: Any = None
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: List[str] = field(default_factory=list)

    # ---- constructors -------------------------------------------------
    @classmethod
    def json(cls, data: Any, status: int = 200, headers: Optional[Dict[str, str]] = None) -> Response:
        return cls(status, dumps(data), {"content-type": "application/json", **(headers or {})})

    @classmethod
    def text(cls, text: str, status: int = 200, headers: Optional[Dict[str, str]] = None) -> Response:
        return cls(status, text, {"content-type": "text/plain; charset=utf-8", **(headers or {})})

    @classmethod
    def html(cls, html: str, status: int = 200, headers: Optional[Dict[str, str]] = None) -> Response:
        return cls(status, html, {"content-type": "text/html; charset=utf-8", **(headers or {})})

    @classmethod
    def binary(
        cls,
        data: bytes,
        content_type: str = "application/octet-stream",
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        return cls(status, bytes(data), {"content-type": content_type, **(headers or {})})

    @classmethod
    def redirect(cls, location: str, status: int = 302) -> Response:
        return cls(status, "", {"location": location})

    @classmethod
    def no_content(cls) -> Response:
        return cls(204, "")

    # ---- helpers ------------------------------------------------------
    def set_cookie(
        self,
        name: str,
        value: str,
        *,
        max_age: Optional[int] = None,
        path: str = "/",
        http_only: bool = True,
        secure: bool = True,
        same_site: str = "Lax",
    ) -> Response:
        parts = [f"{name}={value}", f"Path={path}", f"SameSite={same_site}"]
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        if http_only:
            parts.append("HttpOnly")
        if secure:
            parts.append("Secure")
        self.cookies.append("; ".join(parts))
        return self

    @property
    def content_type(self) -> str:
        for key, value in self.headers.items():
            if key.lower() == "content-type":
                return value
        return ""

    def render(self) -> Tuple[int, Dict[str, str], bytes]:
        """Return ``(status, headers, body_bytes)`` with lower-cased header names
        and a content-type guaranteed to be set when there is a body."""
        headers = {k.lower(): str(v) for k, v in self.headers.items()}
        body = self.body
        if body is None:
            raw = b""
        elif isinstance(body, bytes):
            raw = body
            if raw:
                headers.setdefault("content-type", "application/octet-stream")
        elif isinstance(body, str):
            raw = body.encode("utf-8")
            if raw:
                headers.setdefault("content-type", "text/plain; charset=utf-8")
        else:
            raw = dumps(body).encode("utf-8")
            headers.setdefault("content-type", "application/json")
        return int(self.status), headers, raw

    def render_for_gateway(self) -> Tuple[int, Dict[str, str], str, bool]:
        """Like :meth:`render` but returns a ``str`` body plus an ``is_base64`` flag,
        which is what API-gateway style integrations expect."""
        status, headers, raw = self.render()
        if not raw:
            return status, headers, "", False
        if is_text_content_type(headers.get("content-type", "")):
            try:
                return status, headers, raw.decode("utf-8"), False
            except UnicodeDecodeError:
                pass
        return status, headers, base64.b64encode(raw).decode("ascii"), True


def to_response(result: Any) -> Response:
    """Coerce whatever a handler returned into a :class:`Response`.

    * ``Response``                    -> unchanged
    * ``None``                        -> 204 No Content
    * ``dict`` / ``list`` / numbers   -> JSON 200
    * ``str``                         -> text/plain 200
    * ``bytes``                       -> application/octet-stream 200
    * ``(body, status)`` / ``(body, status, headers)`` -> Flask-style tuple
    """
    if isinstance(result, Response):
        return result
    if result is None:
        return Response.no_content()
    if isinstance(result, tuple) and 2 <= len(result) <= 3 and isinstance(result[1], int):
        base = to_response(result[0])
        base.status = result[1]
        if len(result) == 3 and result[2]:
            base.headers.update(result[2])
        return base
    if isinstance(result, bytes):
        return Response.binary(result)
    if isinstance(result, str):
        return Response.text(result)
    return Response.json(result)
