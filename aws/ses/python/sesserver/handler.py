"""The HTTP handler: the SES v1 Query API (``POST /`` with ``Action=``), the SES v2 REST API (``/v2/email/...``),
the health check and the console."""

from __future__ import annotations

import hmac
import json
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlsplit

from . import console, query, rest
from .config import AUTH, MAX_BODY, REGION, SESSION_TTL, UI_ON, UI_PASSWORD, VERSION, log
from .errors import ApiError
from .operations import run
from .sigv4 import verify_sigv4
from .store import db


class Handler(BaseHTTPRequestHandler):
    server_version = f"pskit-ses/{VERSION}"
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
        self._send(status, json.dumps(data).encode("utf-8"), "application/json", extra)

    def _rest_error(self, exc: ApiError) -> None:
        self._json(exc.status, {"message": exc.message, "__type": exc.code}, {"x-amzn-ErrorType": exc.code})

    def _ui_error(self, exc: ApiError) -> None:
        self._json(exc.status, {"__type": exc.code, "message": exc.message}, {"Cache-Control": "no-store"})

    def _body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            raise ApiError("BadRequestException", "The request body is too large.", 413, "MessageRejected")
        return self.rfile.read(length) if length else b""

    def _headers(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for name in self.headers.keys():
            low = name.lower()
            if low not in out:
                out[low] = ",".join(v.strip() for v in self.headers.get_all(name) or [])
        return out

    def _auth(self, method: str, raw_path: str, query_string: str, body: bytes) -> Dict[str, Any]:
        if AUTH == "off":
            who, region = "anonymous", REGION
        else:
            who, region = verify_sigv4(method, raw_path, query_string, self._headers(), body)
        return {"caller": who, "region": region, "source_ip": self.client_address[0], "user": who}

    # ------------------------------------------------------------------ verbs

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        url = urlsplit(self.path)
        path = url.path
        if path in ("/health", "/healthz"):
            store = db()
            self._json(200, {"status": "ok", "version": VERSION, "identities": len(store.identities),
                             "messages": len(store.messages)})
        elif rest.is_rest(path):
            self._rest("GET", url)
        elif UI_ON and path in ("/", "/ui"):
            self._send(302, b"", "text/plain", {"Location": "/ui/"})
        elif UI_ON and path == "/ui/":
            self._send(200, console.index_html(), "text/html; charset=utf-8", console.PAGE_HEADERS)
        elif UI_ON and path.startswith("/ui/assets/"):
            static = console.asset(unquote(path[len("/ui/assets/"):]))
            if static is None:
                self._ui_error(ApiError("NotFound", "Not found.", 404))
            else:
                self._send(200, static[0], static[1], console.ASSET_HEADERS)
        elif UI_ON and path == "/ui/session":
            found = console.session(self.headers.get("Cookie") or "")
            if AUTH == "off":
                data = {"authenticated": True, "user": "", "auth": False, "csrf": "", "password_login": False}
            else:
                data = {"authenticated": bool(found), "user": found["user"] if found else "", "auth": True,
                        "csrf": found["csrf"] if found else "", "password_login": bool(UI_PASSWORD)}
            self._json(200, data, {"Cache-Control": "no-store"})
        else:
            self._ui_error(ApiError("NotFound", "Not found. The SES API takes POST / (Action=...) and /v2/email/...",
                                    404))

    do_HEAD = do_GET

    def do_PUT(self) -> None:  # noqa: N802
        self._rest("PUT", urlsplit(self.path))

    def do_DELETE(self) -> None:  # noqa: N802
        self._rest("DELETE", urlsplit(self.path))

    def do_POST(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        if url.path.startswith("/ui/"):
            try:
                if not UI_ON:
                    raise ApiError("NotFound", "The web console is off (SES_UI=off).", 404)
                self._ui_post(url.path, self._body())
            except ApiError as exc:
                self._ui_error(exc)
            except Exception as exc:  # noqa: BLE001 - answer every request
                log("error:", repr(exc))
                self._ui_error(ApiError("InternalFailure", "The server failed to process the request.", 500))
            return
        if rest.is_rest(url.path):
            self._rest("POST", url)
            return
        try:
            body = self._body()
            ctx = self._auth("POST", url.path, url.query, body)
            status, out = query.handle(body, url.query, ctx)
        except ApiError as exc:
            status, out = query.error(exc)
        except Exception as exc:  # noqa: BLE001
            log("error:", repr(exc))
            status, out = query.error(ApiError("InternalFailure", "The server failed to process the request.", 500))
        self._send(status, out, "text/xml")

    def _rest(self, method: str, url: Any) -> None:
        raw_path = self.path.split("?", 1)[0]
        try:
            body = self._body()
            ctx = self._auth(method, raw_path, url.query, body)
            status, out = rest.handle(method, url.path, url.query, body, ctx)
            self._json(status, out)
        except ApiError as exc:
            self._rest_error(exc)
        except Exception as exc:  # noqa: BLE001
            log("error:", repr(exc))
            self._rest_error(ApiError("InternalFailure", "The server failed to process the request.", 500))

    def _ui_post(self, path: str, body: bytes) -> None:
        ip = self.client_address[0]
        if path == "/ui/login":
            if AUTH == "off":
                self._json(200, {"authenticated": True, "csrf": ""})
                return
            if console.throttled(ip):
                raise ApiError("ThrottlingException", "Too many failed sign-ins; wait 5 minutes.", 429)
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                raise ApiError("BadRequestException", "The request body is not valid JSON.") from None
            user, password = str(data.get("user") or ""), str(data.get("password") or "")
            if not console.check_login(user, password):
                console.failed(ip)
                log("console sign-in refused from", ip)
                raise ApiError("AccessDeniedException", "Wrong access key or password.", 401)
            sid, csrf = console.new_session(user or "console")
            log("console sign-in", user or "console", "from", ip)
            self._json(200, {"authenticated": True, "user": user, "csrf": csrf}, {
                "Set-Cookie": f"ses_session={sid}; Path=/ui/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}",
                "Cache-Control": "no-store",
            })
            return
        found = console.session(self.headers.get("Cookie") or "")
        if path == "/ui/logout":
            if found:
                console.end_session(found["id"])
            self._json(200, {"authenticated": False}, {"Set-Cookie": "ses_session=; Path=/ui/; HttpOnly; Max-Age=0"})
            return
        if not path.startswith("/ui/api/"):
            raise ApiError("NotFound", "Not found.", 404)
        if AUTH != "off":
            if not found:
                raise ApiError("AccessDeniedException", "Sign in first.", 401)
            if not hmac.compare_digest(self.headers.get("X-SES-CSRF") or "", found["csrf"]):
                raise ApiError("AccessDeniedException", "The console's request token is missing; reload the page.",
                               403)
        try:
            params = json.loads(body.decode("utf-8")) if body.strip() else {}
        except (ValueError, UnicodeDecodeError):
            raise ApiError("BadRequestException", "The request body is not valid JSON.") from None
        if not isinstance(params, dict):
            raise ApiError("BadRequestException", "The request body must be a JSON object.")
        user = found["user"] if found else ""
        ctx = {"caller": f"console:{user}" if user else "console", "region": REGION, "source_ip": ip, "user": user}
        self._json(200, run(path[len("/ui/api/"):], params, ctx), {"Cache-Control": "no-store"})
