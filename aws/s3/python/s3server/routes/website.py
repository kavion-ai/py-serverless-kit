"""Static website hosting: index and error documents, redirects and routing rules."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote

from ..access import allowed
from ..errors import S3Error
from ..objects import object_headers
from ..request import Request, Response
from ..store import get_store
from ..util import esc, parse_xml, text


def website(req: Request, bucket_name: str, key: str, base: str) -> Response:
    if req.method not in ("GET", "HEAD"):
        raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)
    bucket = get_store().buckets.get(bucket_name)
    if bucket is None:
        return _web_error(404, "NoSuchBucket", f"The specified bucket does not exist: {bucket_name}")
    raw = (bucket.meta.get("configs") or {}).get("website")
    if not raw:
        return _web_error(
            404, "NoSuchWebsiteConfiguration", "The specified bucket does not have a website configuration"
        )
    root = parse_xml(raw.encode())
    redirect_all = root.find("RedirectAllRequestsTo")
    if redirect_all is not None:
        proto = text(redirect_all, "Protocol") or "http"
        return Response(301, b"", {"Location": f"{proto}://{text(redirect_all, 'HostName')}/{quote(key)}"})
    suffix = text(root, "IndexDocument/Suffix")
    error_doc = text(root, "ErrorDocument/Key")
    rules = root.findall("RoutingRules/RoutingRule")

    def redirect_for(code: Optional[int]) -> Optional[Response]:
        for rule in rules:
            cond = rule.find("Condition")
            if cond is not None:
                pfx = text(cond, "KeyPrefixEquals")
                err = text(cond, "HttpErrorCodeReturnedEquals")
                if pfx and not key.startswith(pfx):
                    continue
                if err and str(code) != err:
                    continue
                if not err and code is not None:
                    continue
            elif code is not None:
                continue
            red = rule.find("Redirect")
            new_key = key
            if text(red, "ReplaceKeyWith"):
                new_key = text(red, "ReplaceKeyWith")
            elif red is not None and red.find("ReplaceKeyPrefixWith") is not None and cond is not None:
                new_key = text(red, "ReplaceKeyPrefixWith") + key[len(text(cond, "KeyPrefixEquals")) :]
            host = text(red, "HostName") or req.host
            proto = text(red, "Protocol") or "http"
            status = int(text(red, "HttpRedirectCode") or 301)
            location = f"{proto}://{host}{base if not text(red, 'HostName') else '/'}{quote(new_key)}"
            return Response(status, b"", {"Location": location})
        return None

    early = redirect_for(None)
    if early:
        return early
    target = key + suffix if (not key or key.endswith("/")) else key

    def fetch(name: str) -> Optional[Dict[str, Any]]:
        rec = bucket.objects.get(name)
        if not rec or rec["versions"][0].get("dm"):
            return None
        return rec["versions"][0]

    ctx = req.context()  # the website endpoint is anonymous
    with get_store().lock:
        version = fetch(target)
        if version is None and key and not key.endswith("/") and fetch(key + "/" + suffix):
            return Response(302, b"", {"Location": base + quote(key) + "/"})
        readable = version is not None and allowed(bucket, "s3:GetObject", ctx, target, version)
    if version is not None and not readable:
        return _web_error(403, "AccessDenied", "Access Denied")
    if version is None:
        red = redirect_for(404)
        if red:
            return red
        with get_store().lock:
            err_version = fetch(error_doc) if error_doc else None
            if err_version and allowed(bucket, "s3:GetObject", ctx, error_doc, err_version):
                return Response(
                    404,
                    b"",
                    {"Content-Type": err_version.get("type") or "text/html"},
                    err_version.get("type") or "text/html",
                    bucket.blob_path(err_version["blob"]),
                    0,
                    int(err_version["size"]),
                )
        return _web_error(404, "NoSuchKey", f"The specified key does not exist. Key: {target}")
    if version.get("redirect"):
        return Response(301, b"", {"Location": version["redirect"]})
    headers = object_headers(version)
    return Response(
        200, b"", headers, headers["Content-Type"], bucket.blob_path(version["blob"]), 0, int(version["size"])
    )


def _web_error(status: int, code: str, message: str) -> Response:
    title = {403: "403 Forbidden", 404: "404 Not Found"}.get(status, str(status))
    body = (
        f"<html><head><title>{title}</title></head><body><h1>{title}</h1><ul><li>Code: {esc(code)}</li>"
        f"<li>Message: {esc(message)}</li></ul></body></html>"
    ).encode()
    return Response(status, body, {}, "text/html; charset=utf-8")
