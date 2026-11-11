"""The HTTP handler: the Secrets Manager API (``POST /`` with ``X-Amz-Target``), the health check and the console."""

from __future__ import annotations

import hmac
import json
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlsplit

from . import console
from .config import AUTH, MAX_BODY, REGION, SESSION_TTL, UI_ON, UI_PASSWORD, VERSION, log
from .errors import ApiError
from .operations import run
from .sigv4 import verify_sigv4
from .store import db


class Handler(BaseHTTPRequestHandler):
    server_version = f"pskit-secretsmanager/{VERSION}"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - BaseHTTPRequestHandler's signature
        pass

    def _send(self, status: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("x-amzn-RequestId", str(uuid.uuid4()))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: Any, extra: Optional[Dict[str, str]] = None) -> None:
        self._send(status, json.dumps(data).encode("utf-8"), "application/x-amz-json-1.1", extra)

    def _error(self, exc: ApiError, ui: bool = False) -> None:
        body = {"__type": exc.code, "message": exc.message}
        self._json(exc.status, body, None if ui else {"x-amzn-ErrorType": exc.code})

    def _body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            raise ApiError("SerializationException", "The request body is too large.", 413)
        return self.rfile.read(length) if length else b""

    def _params(self, body: bytes) -> Dict[str, Any]:
        try:
            data = json.loads(body.decode("utf-8")) if body.strip() else {}
        except (ValueError, UnicodeDecodeError):
            raise ApiError("SerializationException", "The request body is not valid JSON.") from None
        if not isinstance(data, dict):
            raise ApiError("SerializationException", "The request body must be a JSON object.")
        return data

    def _headers(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for name in self.headers.keys():
            low = name.lower()
            if low not in out:
                out[low] = ",".join(v.strip() for v in self.headers.get_all(name) or [])
        return out

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        path = urlsplit(self.path).path
        if path in ("/health", "/healthz"):
            self._send(200, json.dumps({"status": "ok", "secrets": len(db().secrets), "version": VERSION}).encode(),
                       "application/json")
        elif UI_ON and path in ("/", "/ui"):
            self._send(302, b"", "text/plain", {"Location": "/ui/"})
        elif UI_ON and path == "/ui/":
            self._send(200, console.index_html(), "text/html; charset=utf-8", console.PAGE_HEADERS)
        elif UI_ON and path.startswith("/ui/assets/"):
            static = console.asset(unquote(path[len("/ui/assets/"):]))
            if static is None:
                self._error(ApiError("NotFound", "Not found.", 404))
            else:
                self._send(200, static[0], static[1], console.ASSET_HEADERS)
        elif UI_ON and path == "/ui/session":
            found = console.session(self.headers.get("Cookie") or "")
            if AUTH == "off":
                self._send(200, json.dumps({"authenticated": True, "user": "", "auth": False, "csrf": ""}).encode(),
                           "application/json", {"Cache-Control": "no-store"})
            else:
                data = {"authenticated": bool(found), "user": found["user"] if found else "", "auth": True,
                        "csrf": found["csrf"] if found else "", "password_login": bool(UI_PASSWORD)}
                self._send(200, json.dumps(data).encode(), "application/json", {"Cache-Control": "no-store"})
        else:
            self._error(ApiError("NotFound", "Not found. The Secrets Manager API takes POST / with X-Amz-Target.", 404))

    do_HEAD = do_GET

    def do_POST(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        try:
            body = self._body()
            if url.path.startswith("/ui/"):
                if not UI_ON:
                    raise ApiError("NotFound", "The web console is off (SM_UI=off).", 404)
                self._ui_post(url.path, body)
                return
            headers = self._headers()
            target = headers.get("x-amz-target", "")
            service, _dot, operation = target.partition(".")
            if service != "secretsmanager" or not operation:
                raise ApiError("UnknownOperationException", "X-Amz-Target must be secretsmanager.<Operation>.")
            if AUTH == "off":
                who, region = "anonymous", REGION
            else:
                who, region = verify_sigv4("POST", url.path, url.query, headers, body)
            self._json(200, run(operation, self._params(body), region, who))
        except ApiError as exc:
            self._error(exc)
        except Exception as exc:  # noqa: BLE001 - answer every request
            log("error:", repr(exc))
            self._error(ApiError("InternalServiceError", "The server failed to process the request.", 500))

    def _ui_post(self, path: str, body: bytes) -> None:
        ip = self.client_address[0]
        if path == "/ui/login":
            if AUTH == "off":
                self._json(200, {"authenticated": True, "csrf": ""}, None)
                return
            if console.throttled(ip):
                raise ApiError("ThrottlingException", "Too many failed sign-ins; wait 5 minutes.", 429)
            data = self._params(body)
            user, password = str(data.get("user") or ""), str(data.get("password") or "")
            if not console.check_login(user, password):
                console.failed(ip)
                log("console sign-in refused from", ip)
                raise ApiError("AccessDeniedException", "Wrong access key or password.", 401)
            sid, csrf = console.new_session(user or "console")
            log("console sign-in", user or "console", "from", ip)
            self._json(200, {"authenticated": True, "user": user, "csrf": csrf}, {
                "Set-Cookie": f"sm_session={sid}; Path=/ui/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}",
                "Cache-Control": "no-store",
            })
            return
        found = console.session(self.headers.get("Cookie") or "")
        if path == "/ui/logout":
            if found:
                console.end_session(found["id"])
            self._json(200, {"authenticated": False}, {"Set-Cookie": "sm_session=; Path=/ui/; HttpOnly; Max-Age=0"})
            return
        if not path.startswith("/ui/api/"):
            raise ApiError("NotFound", "Not found.", 404)
        if AUTH != "off":
            if not found:
                raise ApiError("AccessDeniedException", "Sign in first.", 401)
            if not hmac.compare_digest(self.headers.get("X-SM-CSRF") or "", found["csrf"]):
                raise ApiError("AccessDeniedException", "The console's request token is missing; reload the page.", 403)
        who = f"console:{found['user']}" if found else "console"
        self._json(200, run(path[len("/ui/api/"):], self._params(body), REGION, who), {"Cache-Control": "no-store"})
