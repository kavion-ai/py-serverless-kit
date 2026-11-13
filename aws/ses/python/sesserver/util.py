"""Time, ids and e-mail address helpers."""

from __future__ import annotations

import base64
import secrets
import time
import uuid
from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr
from typing import Any, List

from .config import DOMAIN_RE, EMAIL_RE
from .errors import bad_request


def now() -> float:
    return round(time.time(), 3)


def iso(ts: float) -> str:
    """``2026-11-13T10:00:00.000Z``: the Query API's and the event format's timestamps."""
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(ts * 1000) % 1000:03d}Z"


def message_id() -> str:
    """An id shaped like SES's: ``<16 hex ms>-<uuid>-000000``."""
    return f"{int(time.time() * 1000):016x}-{uuid.uuid4()}-000000"


def token(nbytes: int = 32) -> str:
    return base64.b64encode(secrets.token_bytes(nbytes)).decode("ascii")


def selector() -> str:
    """A DKIM selector like SES's tokens: 32 lower-case letters and digits."""
    alphabet = "abcdefghijklmnopqrstuvwxyz234567"
    return "".join(secrets.choice(alphabet) for _ in range(32))


def address(text: Any) -> str:
    """The bare address of ``Name <a@b>`` / ``a@b``, lower-cased domain; '' when it is not an address."""
    _name, addr = parseaddr(str(text or ""))
    addr = addr.strip()
    if not EMAIL_RE.match(addr):
        return ""
    local, _at, domain = addr.rpartition("@")
    return f"{local}@{domain.lower()}"


def addresses(values: Any) -> List[str]:
    """Bare addresses of a list of ``Name <a@b>`` strings (each may itself be a comma list)."""
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    out = []
    for _name, addr in getaddresses([str(v) for v in values]):
        clean = address(addr)
        if not clean:
            raise bad_request(f"Illegal address: {addr!r}.")
        out.append(clean)
    return out


def domain_of(addr: str) -> str:
    return addr.rpartition("@")[2].lower()


def is_domain(text: str) -> bool:
    return bool(DOMAIN_RE.match(text))


def is_email(text: str) -> bool:
    return bool(EMAIL_RE.match(text)) and is_domain(domain_of(text))
