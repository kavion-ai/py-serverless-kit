"""Console routes under ``/ui``: page and assets, session, sign-in and sign-out, and the authenticated API."""

from __future__ import annotations

import hmac
import json

from ..config import AUTH, REGION, SESSION_TTL, UI_ON, UI_PASSWORD, VERSION
from ..errors import S3Error, invalid
from ..request import Request, Response
from ..sigv4 import Auth
from ..util import log
from .api import UI_OPS, ui_download, ui_upload
from .session import check_login, end_session, find_session, new_session, record_failure, throttled
from .static import asset, index_page


def ui_route(req: Request) -> Response:
    if not UI_ON:
        raise S3Error("NotFound", "The web console is off (S3_UI=off).", 404)
    path = req.raw_path
    if path in ("/ui",):
        return Response(302, b"", {"Location": "/ui/"}, "text/plain")
    if req.method in ("GET", "HEAD"):
        if path == "/ui/":
            return index_page()
        if path.startswith("/ui/assets/"):
            return asset(path[len("/ui/assets/") :])
    found = find_session(req.headers.get("cookie", ""))
    if path == "/ui/session":
        if AUTH == "off":
            data = {"authenticated": True, "user": "", "auth": False, "csrf": ""}
        else:
            data = {
                "authenticated": bool(found),
                "user": found["user"] if found else "",
                "auth": True,
                "csrf": found["csrf"] if found else "",
                "password_login": bool(UI_PASSWORD),
            }
        data.update({"region": REGION, "version": VERSION})
        return Response(200, json.dumps(data).encode(), {"Cache-Control": "no-store"}, "application/json")
    if path == "/ui/login" and req.method == "POST":
        ip = req.handler.client_address[0]
        body = req.small_body(65536)
        if AUTH == "off":
            return Response(200, json.dumps({"authenticated": True, "csrf": ""}).encode(), {}, "application/json")
        if throttled(ip):
            raise S3Error("SlowDown", "Too many failed sign-ins; wait 5 minutes.", 429)
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except ValueError:
            raise invalid("The request body is not valid JSON.") from None
        user, password = str(data.get("user") or ""), str(data.get("password") or "")
        if not check_login(user, password):
            record_failure(ip)
            log("console sign-in refused from", ip)
            raise S3Error("AccessDenied", "Wrong access key or password.", 401)
        sid, csrf = new_session(user or "console")
        log("console sign-in", user or "console", "from", ip)
        return Response(
            200,
            json.dumps({"authenticated": True, "user": user, "csrf": csrf}).encode(),
            {
                "Set-Cookie": f"s3_session={sid}; Path=/ui/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}",
                "Cache-Control": "no-store",
            },
            "application/json",
        )
    if path == "/ui/logout" and req.method == "POST":
        if found:
            end_session(found["id"])
        return Response(
            200,
            b'{"authenticated": false}',
            {"Set-Cookie": "s3_session=; Path=/ui/; HttpOnly; Max-Age=0"},
            "application/json",
        )
    if AUTH != "off" and not found:
        raise S3Error("AccessDenied", "Sign in first.", 401)
    user = found["user"] if found else ""
    if path == "/ui/download" and req.method == "GET":
        return ui_download(req)
    if AUTH != "off" and not hmac.compare_digest(req.headers.get("x-s3-csrf", ""), found["csrf"] if found else ""):
        raise S3Error("AccessDenied", "The console's request token is missing; reload the page.", 403)
    if path == "/ui/upload" and req.method == "PUT":
        return ui_upload(req)
    if path.startswith("/ui/api/") and req.method == "POST":
        try:
            params = json.loads(req.small_body().decode("utf-8") or "{}")
        except ValueError:
            raise invalid("The request body is not valid JSON.") from None
        op = path[len("/ui/api/") :]
        handler = UI_OPS.get(op)
        if handler is None:
            raise S3Error("NotImplemented", f"Unknown console operation {op}.", 501)
        req.auth = Auth(user or "console", "console")
        result = handler(params, req)
        if op not in (
            "ListBuckets",
            "ListObjects",
            "BucketInfo",
            "HeadObject",
            "ListVersions",
            "ListUploads",
            "Presign",
            "Stats",
        ):
            log("console", op, params.get("bucket", ""), params.get("key", ""), "by", user or "console")
        return Response(200, json.dumps(result).encode(), {"Cache-Control": "no-store"}, "application/json")
    raise S3Error("NotFound", "Not found.", 404)
