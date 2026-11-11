"""The console's static files: the page shell (``/ui/``) and ``/ui/assets/<path>``. Neither needs a session."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

from ..config import UI_DIR
from ..errors import S3Error
from ..request import Response

SERVER_DIR = Path(__file__).resolve().parents[2]  # the folder holding server.py
UI_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; "
    "frame-src 'self' blob:; frame-ancestors 'none'; form-action 'self'; base-uri 'none'",
}
TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".json": "application/json",
}


def ui_dir() -> Path:
    """``S3_UI_DIR``, else ``ui`` next to server.py (the images), else ``../ui`` (the repository)."""
    if UI_DIR:
        return Path(UI_DIR)
    beside = SERVER_DIR / "ui"
    return beside if beside.is_dir() else SERVER_DIR.parent / "ui"


def index_page() -> Response:
    page = ui_dir() / "index.html"
    body = (
        page.read_bytes()
        if page.is_file()
        else b"<!doctype html><title>S3 console</title><p>The console page (index.html) is missing."
    )
    return Response(200, body, UI_HEADERS, "text/html; charset=utf-8")


def asset(raw_path: str) -> Response:
    """A file under ``ui/assets/``; ``raw_path`` is the URL path after ``/ui/assets/``, still percent-encoded."""
    rel = unquote(raw_path)
    parts = rel.split("/")
    unsafe = any(c in rel for c in ("\\", "\0", ":")) or any(not p or p.startswith(".") for p in parts)
    path = ui_dir().joinpath("assets", *parts)
    if unsafe or not path.is_file():
        raise S3Error("NotFound", "Not found.", 404)
    headers = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
    ctype = TYPES.get(path.suffix.lower(), "application/octet-stream")
    return Response(200, b"", headers, ctype, path, 0, path.stat().st_size)
