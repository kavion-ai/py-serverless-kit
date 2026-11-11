"""Console sign-in: credential check, sessions with a CSRF token, and a lock-out after repeated failures."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ..config import CREDENTIALS, SESSION_TTL, UI_PASSWORD

# Sessions and failed sign-ins live in memory only: a restart signs everyone out.
SESSIONS: Dict[str, Dict[str, Any]] = {}  # session id -> {user, csrf, expires}
FAILURES: Dict[str, List[float]] = {}  # client address -> times of failed sign-ins
_session_lock = threading.Lock()


def check_login(user: str, password: str) -> bool:
    if UI_PASSWORD:
        return hmac.compare_digest(password.encode("utf-8"), UI_PASSWORD.encode("utf-8"))
    secret = CREDENTIALS.get(user)
    return hmac.compare_digest(password.encode("utf-8"), (secret or "\0" * 32).encode("utf-8")) and secret is not None


def throttled(ip: str) -> bool:
    now = time.time()
    with _session_lock:
        recent = [t for t in FAILURES.get(ip, []) if now - t < 300]
        FAILURES[ip] = recent
        return len(recent) >= 10


def record_failure(ip: str) -> None:
    with _session_lock:
        FAILURES.setdefault(ip, []).append(time.time())


def new_session(user: str) -> Tuple[str, str]:
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    with _session_lock:
        now = time.time()
        for key in [k for k, s in SESSIONS.items() if s["expires"] < now]:
            del SESSIONS[key]
        SESSIONS[sid] = {"user": user, "csrf": csrf, "expires": now + SESSION_TTL}
    return sid, csrf


def find_session(cookie_header: str) -> Optional[Dict[str, Any]]:
    for part in cookie_header.split(";"):
        name, _sep, value = part.strip().partition("=")
        if name == "s3_session":
            with _session_lock:
                found = SESSIONS.get(value)
                if found and found["expires"] > time.time():
                    return {**found, "id": value}
    return None


def end_session(sid: str) -> None:
    with _session_lock:
        SESSIONS.pop(sid, None)
