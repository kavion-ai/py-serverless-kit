"""Settings from the environment (``SM_*``), limits and the credentials clients sign with.

``SM_ACCESS_KEY_ID`` / ``SM_SECRET_ACCESS_KEY``
    The credentials clients sign with (``aws_access_key_id`` / ``aws_secret_access_key``).
``SM_CREDENTIALS``
    More credentials: ``id1:secret1,id2:secret2``.
``SM_AUTH``
    ``sigv4`` (default) or ``off`` (no authentication: development only).
``SM_PORT`` (4584), ``SM_BIND`` (0.0.0.0), ``SM_DATA_DIR`` (./data), ``SM_REGION`` (us-east-1),
``SM_ACCOUNT_ID`` (000000000000)
    Where it listens, where the secrets file lives, and the region / account in ARNs.
``SM_UI`` (``on``), ``SM_UI_PASSWORD``, ``SM_UI_DIR``
    The web console, a console password other than the secret key, and the folder of the console's files
    (default: ``ui`` next to ``server.py``, else ``../ui``).
``SM_MASTER_KEY``, ``SM_MASTER_KEYS``, ``SM_MASTER_KEY_ID``, ``SM_ENCRYPTION``
    Encryption at rest, read by :class:`smserver.keyring.Keyring`.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from . import VERSION

__all__ = ["VERSION"]

ENV = os.environ
PORT = int(ENV.get("SM_PORT") or 4584)
BIND = ENV.get("SM_BIND") or "0.0.0.0"  # noqa: S104 - a server; set SM_BIND=127.0.0.1 to keep it local
DATA_DIR = Path(ENV.get("SM_DATA_DIR") or Path.cwd() / "data")
STORE_FILE = DATA_DIR / "secretsmanager.json"
REGION = ENV.get("SM_REGION") or "us-east-1"
ACCOUNT = ENV.get("SM_ACCOUNT_ID") or "000000000000"
AUTH = (ENV.get("SM_AUTH") or "sigv4").lower()
UI_ON = (ENV.get("SM_UI") or "on").lower() not in ("off", "0", "false", "no")
UI_PASSWORD = ENV.get("SM_UI_PASSWORD") or ""
UI_DIR = ENV.get("SM_UI_DIR") or ""
MAX_BODY = 1024 * 1024
MAX_VALUE = 65536
MAX_VERSIONS = 100
SKEW = 15 * 60
SESSION_TTL = 12 * 3600
PUNCTUATION = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
NAME_RE = re.compile(r"^[A-Za-z0-9/_+=.@-]{1,512}$")
AUTH_RE = re.compile(r"^AWS4-HMAC-SHA256\s+Credential=([^,\s]+),\s*SignedHeaders=([^,\s]+),\s*Signature=([0-9a-f]{64})$")


def _credentials() -> Dict[str, str]:
    out: Dict[str, str] = {}
    if ENV.get("SM_SECRET_ACCESS_KEY"):
        out[ENV.get("SM_ACCESS_KEY_ID") or "pskit"] = ENV["SM_SECRET_ACCESS_KEY"]
    for pair in (ENV.get("SM_CREDENTIALS") or "").split(","):
        key, sep, secret = pair.strip().partition(":")
        if sep and key and secret:
            out[key] = secret
    return out


CREDENTIALS = _credentials()


def log(*parts: Any) -> None:
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"), *parts, flush=True)
