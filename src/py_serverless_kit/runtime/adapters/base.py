"""Helpers shared by all adapters."""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, Optional, Tuple

from ..event import EventType

ENVELOPE_KEY = "__pskit"


def envelope(kind: str, data: Any = None, **meta: Any) -> Dict[str, Any]:
    """Wrap a payload so any adapter can recognise its event type.

    The CLI uses this for schedule inputs, workflow task payloads and
    function-to-function ``invoke`` calls, because those arrive on most clouds
    as an opaque JSON object.
    """
    body: Dict[str, Any] = {ENVELOPE_KEY: kind, "data": data}
    body.update(meta)
    return body


def unwrap_envelope(obj: Any) -> Optional[Tuple[str, Any, Dict[str, Any]]]:
    if isinstance(obj, (bytes, str)):
        obj = maybe_json(obj)
    if isinstance(obj, dict) and ENVELOPE_KEY in obj:
        kind = obj[ENVELOPE_KEY]
        if kind not in EventType.ALL:
            kind = EventType.INVOKE
        meta = {k: v for k, v in obj.items() if k not in (ENVELOPE_KEY, "data")}
        return kind, obj.get("data"), meta
    return None


def maybe_json(value: Any) -> Any:
    """Decode bytes/str holding JSON; return the input unchanged otherwise."""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return value
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("{", "[") or text in ("null", "true", "false"):
            try:
                return json.loads(text)
            except ValueError:
                return value
    return value


def b64_text(value: Optional[str]) -> Any:
    """Decode a base64 field to text (or JSON) - used by Pub/Sub style payloads."""
    if not value:
        return None
    try:
        raw = base64.b64decode(value)
    except (ValueError, TypeError):
        return value
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw


def function_name(default: str = "") -> str:
    return os.environ.get("PSKIT_FUNCTION", default)


def action_from(name: str) -> str:
    """Map provider-specific object event names to ``created`` / ``deleted``."""
    lowered = (name or "").lower()
    if any(word in lowered for word in ("delete", "remove", "archive")):
        return "deleted"
    return "created"


def first(mapping: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default
