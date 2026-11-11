"""Small helpers shared by every module: logging, times, XML building and parsing, URI encoding."""

from __future__ import annotations

import email.utils
import re
import time
import xml.etree.ElementTree as ET  # noqa: S405 - bodies are size-limited; expat refuses external entities
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
from urllib.parse import quote, unquote

from .config import NS, OWNER_ID, OWNER_NAME
from .errors import malformed


def log(*parts: Any) -> None:
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"), *parts, flush=True)


def timestamp() -> float:
    return round(time.time(), 3)


def iso(ts: float) -> str:
    millis = int(round(ts * 1000) % 1000)
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def http_date(ts: float) -> str:
    return email.utils.formatdate(int(ts), usegmt=True)


def parse_time(text: str) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return email.utils.parsedate_to_datetime(text).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        cleaned = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        pass
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def esc(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\r", "&#13;")
    )


def x(tag: str, value: Any) -> str:
    return f"<{tag}>{esc(value)}</{tag}>"


def doc(root: str, inner: str) -> bytes:
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<{root} xmlns="{NS}">{inner}</{root}>'.encode()


def parse_xml(body: bytes) -> ET.Element:
    if not body.strip():
        raise malformed()
    if b"<!DOCTYPE" in body or b"<!ENTITY" in body:
        raise malformed()
    try:
        root = ET.fromstring(body)  # noqa: S314 - DOCTYPE/ENTITY refused above, size-limited
    except ET.ParseError:
        raise malformed() from None
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def text(el: Optional[ET.Element], path: str, default: str = "") -> str:
    if el is None:
        return default
    found = el.find(path)
    return (found.text or "").strip() if found is not None and found.text is not None else default


def strip_decl(xml_text: str) -> str:
    return re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", xml_text)


def url_enc(value: str, enabled: bool) -> str:
    return quote(value, safe="/") if enabled else value


def owner_xml() -> str:
    return "<Owner>" + x("ID", OWNER_ID) + x("DisplayName", OWNER_NAME) + "</Owner>"


def uri_encode(value: str, safe: str = "-_.~") -> str:
    return quote(value, safe=safe)


def split_query(raw_query: str) -> List[Tuple[str, str]]:
    pairs = []
    for part in raw_query.split("&"):
        if not part:
            continue
        name, _sep, value = part.partition("=")
        pairs.append((unquote(name), unquote(value)))
    return pairs


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else [value] if value is not None else []
