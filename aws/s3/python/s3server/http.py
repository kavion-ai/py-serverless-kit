"""The HTTP handler: parses each request, routes it, answers errors as S3 XML, adds CORS headers."""

from __future__ import annotations

import base64
import json
import re
import secrets
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional
from urllib.parse import unquote

from .config import ACCOUNT, DOMAINS, UI_ON, VERSION
from .console.router import ui_route
from .cors import cors_match
from .errors import S3Error, denied
from .request import Request, Response, authenticate
from .routes.bucket import bucket_route, preflight
from .routes.objects import object_route
from .routes.post import post_object
from .routes.service import list_buckets
from .routes.website import website
from .store import get_store
from .util import log, x


class Handler(BaseHTTPRequestHandler):
    """Answers every request (HTTP/1.1, keep-alive) through ``route``."""

    server_version = f"pskit-s3/{VERSION}"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - BaseHTTPRequestHandler's signature
        pass

    def lower_headers(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for name in self.headers.keys():
            low = name.lower()
            if low not in out:
                out[low] = ",".join(v.strip() for v in self.headers.get_all(name) or [])
        return out

    def do_GET(self) -> None:  # noqa: N802 - http.server's naming
        self.dispatch()

    do_HEAD = do_PUT = do_POST = do_DELETE = do_OPTIONS = do_GET

    def send(self, resp: Response, req: Optional[Request] = None) -> None:
        self.send_response(resp.status)
        request_id = uuid.uuid4().hex[:16].upper()
        headers = {"x-amz-request-id": request_id, "x-amz-id-2": base64.b64encode(secrets.token_bytes(24)).decode()}
        headers.update(resp.headers)
        if req is not None and (not req.consumed or not req.raw.done):
            # The body was not read to its end (refused early, or an error mid-body): the rest of it must not be
            # taken for the next request on this connection.
            headers["Connection"] = "close"
            self.close_connection = True
        if resp.file is not None:
            length = resp.length
        else:
            length = len(resp.body)
        if resp.status != 304 and resp.status != 204:
            if resp.body or resp.file is not None or "Content-Type" in resp.headers:
                headers.setdefault("Content-Type", resp.ctype)
            headers["Content-Length"] = str(length)
        elif resp.status == 204:
            headers.pop("Content-Length", None)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command == "HEAD" or resp.status in (204, 304):
            return
        if resp.file is not None:
            with open(resp.file, "rb") as handle:
                handle.seek(resp.start)
                left = resp.length
                while left > 0:
                    data = handle.read(min(256 * 1024, left))
                    if not data:
                        break
                    self.wfile.write(data)
                    left -= len(data)
        elif resp.body:
            self.wfile.write(resp.body)

    def error(self, exc: S3Error, req: Optional[Request]) -> Response:
        resource = req.raw_path if req else "/"
        if resource == "/ui" or resource.startswith("/ui/"):
            # The console reads JSON errors.
            data = json.dumps({"code": exc.code, "message": exc.message}).encode()
            return Response(exc.status, data, {"Cache-Control": "no-store"}, "application/json")
        extra = "".join(x(k, v) for k, v in exc.extra.items() if v)
        body = (
            b""
            if exc.status == 304 or self.command == "HEAD"
            else (
                f'<?xml version="1.0" encoding="UTF-8"?>\n<Error>{x("Code", exc.code)}{x("Message", exc.message)}'
                f"{extra}{x('Resource', resource)}{x('RequestId', uuid.uuid4().hex[:16].upper())}</Error>"
            ).encode()
        )
        resp = Response(exc.status, body, exc.headers)
        if self.command == "HEAD" and exc.status != 304:
            resp.headers.setdefault("Content-Type", "application/xml")
        return resp

    def dispatch(self) -> None:
        req: Optional[Request] = None
        try:
            req = Request(self)
            resp = route(req)
        except S3Error as exc:
            resp = self.error(exc, req)
        except Exception as exc:  # noqa: BLE001 - answer every request
            log("error:", repr(exc))
            resp = self.error(S3Error("InternalError", "We encountered an internal error. Please try again.", 500), req)
        if req is not None and req.bucket and "origin" in req.headers and req.method != "OPTIONS":
            bucket = get_store().buckets.get(req.bucket)
            if bucket is not None:
                found = cors_match(bucket, req.headers["origin"], req.method if req.method != "HEAD" else "HEAD", [])
                if found:
                    found.pop("Access-Control-Allow-Headers", None)
                    resp.headers.update(found)
        try:
            self.send(resp, req)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True


def _bucket_from_host(host: str) -> str:
    name = host.rsplit(":", 1)[0].lower() if not host.startswith("[") else ""
    for domain in DOMAINS:
        if name.endswith("." + domain):
            return name[: -len(domain) - 1]
    match = re.match(r"^(.+)\.s3[.-](?:[a-z0-9-]+\.)?amazonaws\.com$", name)
    return match.group(1) if match else ""


def route(req: Request) -> Response:
    """Health, console, website, CORS preflight and POST uploads first; then the authenticated S3 API."""
    if req.raw_path in ("/-/health", "/-/healthz") or (
        req.raw_path in ("/health", "/healthz") and "authorization" not in req.headers and not req.q
    ):
        return Response(
            200,
            json.dumps({"status": "ok", "buckets": len(get_store().buckets), "version": VERSION}).encode(),
            ctype="application/json",
        )
    if req.raw_path == "/ui" or req.raw_path.startswith("/ui/"):
        return ui_route(req)
    if req.raw_path.startswith("/-/website/"):
        rest = req.raw_path[len("/-/website/") :]
        bucket, _s, key = rest.partition("/")
        return website(req, unquote(bucket), unquote(key), f"/-/website/{bucket}/")
    host_bucket = _bucket_from_host(req.host)
    web = re.match(r"^(.+)\.s3-website[.-]", req.host.lower())
    if web:
        return website(req, web.group(1), unquote(req.raw_path.lstrip("/")), "/")
    if host_bucket:
        req.vhost = host_bucket
        req.bucket, req.key = host_bucket, unquote(req.raw_path[1:])
    else:
        bucket, _s, key = req.raw_path[1:].partition("/")
        req.bucket, req.key = unquote(bucket), unquote(key)
    if (
        req.raw_path == "/"
        and not host_bucket
        and UI_ON
        and req.method == "GET"
        and "authorization" not in req.headers
        and "X-Amz-Signature" not in req.q
        and "text/html" in req.headers.get("accept", "")
    ):
        return Response(302, b"", {"Location": "/ui/"}, "text/plain")
    if req.method == "OPTIONS":
        return preflight(req)
    if (
        req.method == "POST"
        and req.bucket
        and not req.key
        and req.headers.get("content-type", "").startswith("multipart/form-data")
        and "authorization" not in req.headers
    ):
        return post_object(req)
    authenticate(req)
    expected_owner = req.headers.get("x-amz-expected-bucket-owner")
    if expected_owner and expected_owner != ACCOUNT:
        raise denied()
    if not req.bucket:
        if req.method == "GET":
            return list_buckets(req)
        raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)
    if len(req.key.encode("utf-8")) > 1024:
        raise S3Error("KeyTooLongError", "Your key is too long", 400)
    if not req.key:
        return bucket_route(req)
    return object_route(req)
