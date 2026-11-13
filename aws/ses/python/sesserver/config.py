"""Settings from the environment (``SES_*``), limits and the credentials clients sign with.

Authentication and where it listens
    ``SES_ACCESS_KEY_ID`` / ``SES_SECRET_ACCESS_KEY`` (the keys clients sign with), ``SES_CREDENTIALS``
    (``id1:secret1,id2:secret2``), ``SES_AUTH`` (``sigv4`` or ``off``), ``SES_PORT`` (4579), ``SES_BIND``
    (0.0.0.0), ``SES_DATA_DIR`` (./data), ``SES_REGION`` (us-east-1), ``SES_ACCOUNT_ID`` (000000000000).
Web console
    ``SES_UI`` (on), ``SES_UI_PASSWORD``, ``SES_UI_DIR``.
SMTP endpoint (like email-smtp.<region>.amazonaws.com)
    ``SES_SMTP`` (on), ``SES_SMTP_PORT`` (2587), ``SES_SMTP_BIND`` (= SES_BIND), ``SES_TLS_CERT`` / ``SES_TLS_KEY``
    (PEM files: STARTTLS), ``SES_SMTP_REQUIRE_TLS`` (off), ``SES_SMTP_HOST`` (the name shown in the console).
Delivery
    ``SES_DELIVERY``: ``relay`` (through ``SES_RELAY_HOST``), ``direct`` (to the recipients' MX hosts) or
    ``capture`` (keep every message, send nothing). Default: ``relay`` when ``SES_RELAY_HOST`` is set, else
    ``direct``. ``SES_RELAY_PORT`` (587), ``SES_RELAY_USER``, ``SES_RELAY_PASSWORD``, ``SES_RELAY_TLS``
    (``starttls``, ``tls`` or ``none``; default ``tls`` on port 465, else ``starttls``), ``SES_RELAY_TLS_VERIFY``
    (on). ``SES_HELO_NAME`` (this host's name), ``SES_DIRECT_PORT`` (25), ``SES_DNS_SERVER`` (host[:port]; default
    from /etc/resolv.conf, else 1.1.1.1), ``SES_DELIVERY_THREADS`` (4), ``SES_RETRY_HOURS`` (12),
    ``SES_RETENTION_DAYS`` (14: how long messages stay in the console).
Sending rules
    ``SES_VERIFY``: ``auto`` (a new identity is verified at once), ``dns`` (domains by their DNS records, addresses
    by their verified domain or the console), ``manual`` (the console marks identities verified), ``off`` (any
    From address, no identity needed). ``SES_SANDBOX`` (off: on also needs verified recipients),
    ``SES_MAX_24H`` (50000), ``SES_MAX_RATE`` (14 per second), ``SES_MAX_MESSAGE_MB`` (40), ``SES_DKIM_CHECK``
    (on: look up DKIM / verification records in DNS).
Events
    ``SES_EVENTS_URL`` (POST every event as JSON, the SES event publishing format), ``SES_EVENTS_TOKEN``
    (sent as ``Authorization: Bearer``).
"""

from __future__ import annotations

import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from . import VERSION

__all__ = ["VERSION"]

ENV = os.environ


def _flag(name: str, default: str) -> bool:
    return (ENV.get(name) or default).strip().lower() not in ("off", "0", "false", "no")


def _int(name: str, default: int) -> int:
    try:
        return int(ENV.get(name) or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(ENV.get(name) or default)
    except ValueError:
        return default


PORT = _int("SES_PORT", 4579)
BIND = ENV.get("SES_BIND") or "0.0.0.0"  # noqa: S104 - a server; set SES_BIND=127.0.0.1 to keep it local
DATA_DIR = Path(ENV.get("SES_DATA_DIR") or Path.cwd() / "data")
STORE_FILE = DATA_DIR / "ses.json"
MESSAGES_DIR = DATA_DIR / "messages"
REGION = ENV.get("SES_REGION") or "us-east-1"
ACCOUNT = ENV.get("SES_ACCOUNT_ID") or "000000000000"
AUTH = (ENV.get("SES_AUTH") or "sigv4").lower()
UI_ON = _flag("SES_UI", "on")
UI_PASSWORD = ENV.get("SES_UI_PASSWORD") or ""
UI_DIR = ENV.get("SES_UI_DIR") or ""

SMTP_ON = _flag("SES_SMTP", "on")
SMTP_PORT = _int("SES_SMTP_PORT", 2587)
SMTP_BIND = ENV.get("SES_SMTP_BIND") or BIND
SMTP_HOST = ENV.get("SES_SMTP_HOST") or ""
TLS_CERT = ENV.get("SES_TLS_CERT") or ""
TLS_KEY = ENV.get("SES_TLS_KEY") or ""
SMTP_REQUIRE_TLS = _flag("SES_SMTP_REQUIRE_TLS", "off")

RELAY_HOST = ENV.get("SES_RELAY_HOST") or ""
DELIVERY = (ENV.get("SES_DELIVERY") or ("relay" if RELAY_HOST else "direct")).lower()
RELAY_PORT = _int("SES_RELAY_PORT", 587)
RELAY_USER = ENV.get("SES_RELAY_USER") or ""
RELAY_PASSWORD = ENV.get("SES_RELAY_PASSWORD") or ""
RELAY_TLS = (ENV.get("SES_RELAY_TLS") or ("tls" if RELAY_PORT == 465 else "starttls")).lower()
RELAY_TLS_VERIFY = _flag("SES_RELAY_TLS_VERIFY", "on")
HELO_NAME = ENV.get("SES_HELO_NAME") or socket.getfqdn() or "localhost"
DIRECT_PORT = _int("SES_DIRECT_PORT", 25)
DNS_SERVER = ENV.get("SES_DNS_SERVER") or ""
DELIVERY_THREADS = max(1, _int("SES_DELIVERY_THREADS", 4))
RETRY_HOURS = _float("SES_RETRY_HOURS", 12)
RETENTION_DAYS = _float("SES_RETENTION_DAYS", 14)

VERIFY = (ENV.get("SES_VERIFY") or "auto").lower()
SANDBOX = _flag("SES_SANDBOX", "off")
MAX_24H = _float("SES_MAX_24H", 50000)
MAX_RATE = _float("SES_MAX_RATE", 14)
MAX_MESSAGE = int(_float("SES_MAX_MESSAGE_MB", 40) * 1024 * 1024)
DKIM_CHECK = _flag("SES_DKIM_CHECK", "on")

EVENTS_URL = ENV.get("SES_EVENTS_URL") or ""
EVENTS_TOKEN = ENV.get("SES_EVENTS_TOKEN") or ""

# A base64 message of MAX_MESSAGE bytes in a JSON or form body is about 4/3 larger.
MAX_BODY = MAX_MESSAGE * 4 // 3 + 1024 * 1024
MAX_RECIPIENTS = 50
SKEW = 15 * 60
SESSION_TTL = 12 * 3600
SIMULATOR = "simulator.amazonses.com"
AUTH_RE = re.compile(r"^AWS4-HMAC-SHA256\s+Credential=([^,\s]+),\s*SignedHeaders=([^,\s]+),\s*Signature=([0-9a-f]{64})$")
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$")
EMAIL_RE = re.compile(r"^[^@\s<>()\[\],;:\"]{1,64}@[A-Za-z0-9.-]{1,253}$")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _credentials() -> Dict[str, str]:
    out: Dict[str, str] = {}
    if ENV.get("SES_SECRET_ACCESS_KEY"):
        out[ENV.get("SES_ACCESS_KEY_ID") or "pskit"] = ENV["SES_SECRET_ACCESS_KEY"]
    for pair in (ENV.get("SES_CREDENTIALS") or "").split(","):
        key, sep, secret = pair.strip().partition(":")
        if sep and key and secret:
            out[key] = secret
    return out


CREDENTIALS = _credentials()


def log(*parts: Any) -> None:
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"), *parts, flush=True)
