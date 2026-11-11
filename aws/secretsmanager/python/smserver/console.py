"""The web console's server side: sign-in (with throttling), sessions in memory, and the console's static files.

The session lives in an ``HttpOnly``, ``SameSite=Strict`` cookie (``sm_session``); every ``/ui/api`` request also
carries the page's CSRF token in ``X-SM-CSRF``. The console's files are ``index.html`` and ``assets/**`` in the UI
folder: ``SM_UI_DIR``, else ``ui`` next to ``server.py`` (the container layout), else ``../ui`` (the repository).
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import CREDENTIALS, SESSION_TTL, UI_DIR, UI_PASSWORD

SESSIONS: Dict[str, Dict[str, Any]] = {}
FAILURES: Dict[str, List[float]] = {}
_lock = threading.Lock()

# No inline scripts: everything the page runs is in ui/assets/js.
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
       "img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": CSP,
}
ASSET_HEADERS = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".json": "application/json",
    ".html": "text/html; charset=utf-8",
}
_MISSING = b"<!doctype html><title>Secrets Manager console</title><p>The console page (index.html) is missing."


# ----------------------------------------------------------------------------- sign-in and sessions


def check_login(user: str, password: str) -> bool:
    if UI_PASSWORD:
        return hmac.compare_digest(password.encode("utf-8"), UI_PASSWORD.encode("utf-8"))
    secret = CREDENTIALS.get(user)
    # compare_digest on a dummy keeps the time the same for an unknown user.
    return hmac.compare_digest(password.encode("utf-8"), (secret or "\0" * 32).encode("utf-8")) and secret is not None


def throttled(ip: str) -> bool:
    """Ten failed sign-ins from one address in five minutes lock it out."""
    now = time.time()
    with _lock:
        recent = [t for t in FAILURES.get(ip, []) if now - t < 300]
        FAILURES[ip] = recent
        return len(recent) >= 10


def failed(ip: str) -> None:
    with _lock:
        FAILURES.setdefault(ip, []).append(time.time())


def new_session(user: str) -> Tuple[str, str]:
    """(session id, CSRF token) of a new session."""
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    with _lock:
        now = time.time()
        for key in [k for k, s in SESSIONS.items() if s["expires"] < now]:
            del SESSIONS[key]
        SESSIONS[sid] = {"user": user, "csrf": csrf, "expires": now + SESSION_TTL}
    return sid, csrf


def session(cookie_header: str) -> Optional[Dict[str, Any]]:
    for part in cookie_header.split(";"):
        name, _sep, value = part.strip().partition("=")
        if name == "sm_session":
            with _lock:
                found = SESSIONS.get(value)
                if found and found["expires"] > time.time():
                    return {**found, "id": value}
    return None


def end_session(sid: str) -> None:
    with _lock:
        SESSIONS.pop(sid, None)


# ----------------------------------------------------------------------------- static files


def ui_dir() -> Optional[Path]:
    here = Path(__file__).resolve().parent.parent  # the folder of server.py
    for candidate in ([Path(UI_DIR)] if UI_DIR else []) + [here / "ui", here.parent / "ui"]:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def index_html() -> bytes:
    base = ui_dir()
    return (base / "index.html").read_bytes() if base else _MISSING


def asset(rel: str) -> Optional[Tuple[bytes, str]]:
    """(content, Content-Type) of ``ui/assets/<rel>``, or None (answered 404). ``rel`` is the decoded URL path after
    ``/ui/assets/``; dot segments, hidden files, backslashes and NUL are refused, and the file must stay inside
    ``assets``."""
    base = ui_dir()
    parts = rel.split("/")
    if base is None or not rel or "\\" in rel or "\0" in rel or any(not p or p.startswith(".") for p in parts):
        return None
    root = (base / "assets").resolve()
    path = (root / Path(*parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path.read_bytes(), TYPES.get(path.suffix.lower(), "application/octet-stream")
