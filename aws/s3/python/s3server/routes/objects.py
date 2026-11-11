"""Object operations: get, head, put, copy, delete, and object subresources (tags, ACL, lock, attributes, restore)."""

from __future__ import annotations

import time
from typing import Dict, Optional

from ..access import acl_from_request, acl_public, acl_xml, bucket_owner_enforced, public_block
from ..checksums import checksum_element, checksum_header
from ..config import ARCHIVED, OBJECT_SUBRESOURCES
from ..errors import S3Error, denied, invalid, malformed, no_key
from ..objectlock import lock_config
from ..objects import (
    check_conditions,
    new_version,
    object_fields,
    object_headers,
    parse_range,
    parse_tagging,
    read_source,
    tags_from_xml,
    tags_xml,
)
from ..payload import copy_file, wanted_checksum
from ..request import Request, Response, need_auth, object_action, xml_response
from ..store import Bucket, abort_upload, get_store, unlink
from ..util import http_date, iso, parse_time, parse_xml, text, x
from ..versions import delete_object, find_version, put_version
from .multipart import complete_upload, create_upload, list_parts, upload_part

SANDBOX = "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads"


def object_route(req: Request) -> Response:
    q, method = req.q, req.method
    with get_store().lock:
        bucket = get_store().get(req.bucket)
    sub = next((s for s in OBJECT_SUBRESOURCES if s in q), "")
    if sub in ("select", "torrent"):
        raise S3Error(
            "NotImplemented",
            f"{'SelectObjectContent' if sub == 'select' else 'GetObjectTorrent'} is not implemented.",
            501,
        )
    if method == "POST" and sub == "uploads":
        need_auth(req, bucket, "s3:PutObject", req.key)
        return create_upload(req, bucket)
    if "uploadId" in q:
        upload_id = q["uploadId"]
        if method == "PUT" and "partNumber" in q:
            need_auth(req, bucket, "s3:PutObject", req.key)
            return upload_part(req, bucket, upload_id)
        if method == "POST":
            need_auth(req, bucket, "s3:PutObject", req.key)
            return complete_upload(req, bucket, upload_id)
        if method == "DELETE":
            need_auth(req, bucket, "s3:AbortMultipartUpload", req.key)
            with get_store().lock:
                if upload_id not in bucket.uploads:
                    raise S3Error("NoSuchUpload", "The specified upload does not exist.", 404, UploadId=upload_id)
                abort_upload(bucket, upload_id)
            return Response(204)
        if method == "GET":
            need_auth(req, bucket, "s3:ListMultipartUploadParts", req.key)
            return list_parts(req, bucket, upload_id)
    if sub == "tagging":
        return object_tagging(req, bucket)
    if sub == "acl":
        return object_acl(req, bucket)
    if sub in ("retention", "legal-hold"):
        return object_lock_route(req, bucket, sub)
    if sub == "attributes" and method == "GET":
        return object_attributes(req, bucket)
    if sub == "restore" and method == "POST":
        return restore_object(req, bucket)
    if method in ("GET", "HEAD"):
        return get_object(req, bucket)
    if method == "PUT":
        if "x-amz-copy-source" in req.headers:
            need_auth(req, bucket, "s3:PutObject", req.key)
            return copy_object(req, bucket)
        need_auth(req, bucket, "s3:PutObject", req.key)
        return put_object(req, bucket)
    if method == "DELETE":
        need_auth(req, bucket, "s3:DeleteObject", req.key)
        return delete_route(req, bucket)
    raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)


def _version_id(req: Request) -> Optional[str]:
    return req.q["versionId"] if "versionId" in req.q else None


def _active_content(ctype: str) -> bool:
    """HTML, XHTML, XML or SVG: content a browser could run scripts from."""
    base = ctype.split(";", 1)[0].strip().lower()
    return base == "text/html" or base.endswith(("/xml", "+xml"))


def get_object(req: Request, bucket: Bucket) -> Response:
    vid = _version_id(req)
    with get_store().lock:
        version = find_version(bucket, req.key, vid)
        need_auth(req, bucket, "s3:GetObjectVersion" if vid else "s3:GetObject", req.key, version)
        version = dict(version)
        path = bucket.blob_path(version["blob"])
    if bucket.meta.get("versioning"):
        version["versioned"] = True
    sse_c = (version.get("sse") or {}).get("x-amz-server-side-encryption-customer-key-md5")
    if sse_c and req.headers.get("x-amz-server-side-encryption-customer-key-md5") != sse_c:
        raise S3Error(
            "InvalidRequest",
            "The object was stored using a form of Server Side Encryption. The correct "
            "parameters must be provided to retrieve the object.",
        )
    try:
        check_conditions(version, req.headers)
    except S3Error as exc:
        if exc.status == 304:
            exc.headers = {"ETag": f'"{version["etag"]}"', "Last-Modified": http_date(version["time"])}
        raise
    if version.get("class") in ARCHIVED and req.method == "GET":
        if not version.get("restore") or version["restore"] < time.time():
            raise S3Error(
                "InvalidObjectState",
                "The operation is not valid for the object's storage class",
                403,
                StorageClass=version["class"],
            )
    size = int(version["size"])
    part = req.q.get("partNumber")
    rng = None
    headers = object_headers(version, checksum=req.headers.get("x-amz-checksum-mode", "").upper() == "ENABLED")
    if part:
        try:
            n = int(part)
        except ValueError:
            raise invalid("Part number must be an integer between 1 and 10000, inclusive", "partNumber", part) from None
        parts = version.get("parts") or [{"size": size}]
        if n < 1 or n > len(parts):
            raise S3Error("InvalidPartNumber", "The requested partnumber is not satisfiable", 416)
        start = sum(int(p["size"]) for p in parts[: n - 1])
        rng = (start, start + int(parts[n - 1]["size"]) - 1) if parts[n - 1]["size"] else None
        headers["x-amz-mp-parts-count"] = str(len(parts))
        if rng is None:
            headers["Content-Range"] = f"bytes */{size}"
    elif req.headers.get("range"):
        rng = parse_range(req.headers["range"], size)
    for name in (
        "content-type",
        "content-language",
        "expires",
        "cache-control",
        "content-disposition",
        "content-encoding",
    ):
        override = req.q.get("response-" + name)
        if override is not None:
            if req.who is None:
                raise S3Error(
                    "InvalidRequest", "Request specific response headers cannot be used for anonymous GET requests."
                )
            proper = "-".join(w.capitalize() for w in name.split("-"))
            headers.pop(name, None)
            headers[proper if name != "content-type" else "Content-Type"] = override
    if req.method == "GET" and not req.vhost and _active_content(headers.get("Content-Type", "")):
        # Path-style URLs share the console's origin: a page from a bucket runs in an opaque origin.
        headers["Content-Security-Policy"] = SANDBOX
    if rng is not None:
        for h in [h for h in headers if h.startswith("x-amz-checksum-")]:
            headers.pop(h)
        start, end = rng
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(
            206, b"", headers, headers.get("Content-Type", "binary/octet-stream"), path, start, end - start + 1
        )
    return Response(200, b"", headers, headers.get("Content-Type", "binary/octet-stream"), path, 0, size)


def put_object(req: Request, bucket: Bucket) -> Response:
    if (
        req.headers.get("content-length") is None
        and "chunked" not in req.headers.get("transfer-encoding", "")
        and not req.headers.get("x-amz-decoded-content-length")
    ):
        raise S3Error("MissingContentLength", "You must provide the Content-Length HTTP header.", 411)
    fields = object_fields(req.headers, bucket)
    if req.headers.get("if-none-match", "*") != "*":
        raise S3Error("NotImplemented", "If-None-Match on a write only supports *.", 501)
    alg, expected = wanted_checksum(req.headers)
    received = req.payload(alg, expected)
    try:
        with get_store().lock:
            rec = bucket.objects.get(req.key)
            current = rec["versions"][0] if rec and not rec["versions"][0].get("dm") else None
            if req.headers.get("if-none-match") == "*" and current:
                raise S3Error(
                    "PreconditionFailed",
                    "At least one of the pre-conditions you specified did not hold",
                    412,
                    Condition="If-None-Match",
                )
            if req.headers.get("if-match"):
                if not current:
                    raise no_key(req.key)
                check_conditions(current, {"if-match": req.headers["if-match"]}, write=True)
            blob = get_store().commit_blob(bucket, received.path)  # type: ignore[arg-type]
            received.path = None
            version = put_version(bucket, req.key, new_version(received, fields, blob))
    finally:
        if received.path:
            unlink(received.path)
    headers = {"ETag": f'"{version["etag"]}"'}
    if bucket.meta.get("versioning"):
        headers["x-amz-version-id"] = version["id"]
    if version.get("checksum"):
        headers[checksum_header(version["checksum"]["alg"])] = version["checksum"]["value"]
        headers["x-amz-checksum-type"] = "FULL_OBJECT"
    for k, v in (version.get("sse") or {}).items():
        if k != "x-amz-server-side-encryption-context":
            headers[k] = v
    return Response(200, b"", headers)


def copy_object(req: Request, bucket: Bucket) -> Response:
    src_bucket, src_key, src, src_path = read_source(req.headers, req.context())
    directive = req.headers.get("x-amz-metadata-directive", "COPY").upper()
    tag_directive = req.headers.get("x-amz-tagging-directive", "COPY").upper()
    if directive not in ("COPY", "REPLACE") or tag_directive not in ("COPY", "REPLACE"):
        raise invalid("Unknown metadata directive.", "x-amz-metadata-directive", directive)
    same = (
        src_bucket is bucket and src_key == req.key and not req.headers.get("x-amz-copy-source", "").count("versionId=")
    )
    changes = (
        directive == "REPLACE"
        or "x-amz-storage-class" in req.headers
        or "x-amz-server-side-encryption" in req.headers
        or "x-amz-website-redirect-location" in req.headers
    )
    if same and not changes:
        raise S3Error(
            "InvalidRequest",
            "This copy request is illegal because it is trying to copy an object to "
            "itself without changing the object's metadata, storage class, website redirect location or "
            "encryption attributes.",
        )
    if directive == "REPLACE":
        fields = object_fields(req.headers, bucket)
    else:
        merged = dict(req.headers)
        merged["content-type"] = src.get("type") or "binary/octet-stream"
        for k, v in (src.get("headers") or {}).items():
            merged[k] = v
        for k in [k for k in merged if k.startswith("x-amz-meta-")]:
            del merged[k]
        for k, v in (src.get("meta") or {}).items():
            merged["x-amz-meta-" + k] = v
        merged.pop("x-amz-tagging", None)
        fields = object_fields(merged, bucket)
    if tag_directive == "COPY":
        fields["tags"] = dict(src.get("tags") or {})
    elif req.headers.get("x-amz-tagging"):
        fields["tags"] = parse_tagging(req.headers["x-amz-tagging"])
    else:
        fields["tags"] = {}
    alg = (req.headers.get("x-amz-checksum-algorithm") or (src.get("checksum") or {}).get("alg") or "").upper()
    received = copy_file(src_path, 0, int(src["size"]) - 1, alg)
    try:
        with get_store().lock:
            blob = get_store().commit_blob(bucket, received.path)  # type: ignore[arg-type]
            received.path = None
            version = put_version(bucket, req.key, new_version(received, fields, blob))
    finally:
        if received.path:
            unlink(received.path)
    headers: Dict[str, str] = {}
    if src["id"] != "null" or src_bucket.meta.get("versioning"):
        headers["x-amz-copy-source-version-id"] = src["id"]
    if bucket.meta.get("versioning"):
        headers["x-amz-version-id"] = version["id"]
    inner = x("LastModified", iso(version["time"])) + x("ETag", f'"{version["etag"]}"')
    if version.get("checksum"):
        inner += x("ChecksumType", "FULL_OBJECT") + x(
            checksum_element(version["checksum"]["alg"]), version["checksum"]["value"]
        )
    return xml_response("CopyObjectResult", inner, headers=headers)


def delete_route(req: Request, bucket: Bucket) -> Response:
    vid = _version_id(req)
    bypass = req.headers.get("x-amz-bypass-governance-retention", "").lower() == "true"
    with get_store().lock:
        if req.headers.get("if-match"):
            rec = bucket.objects.get(req.key)
            if not rec or rec["versions"][0].get("dm"):
                raise no_key(req.key)
            check_conditions(rec["versions"][0], {"if-match": req.headers["if-match"]}, write=True)
        result = delete_object(bucket, req.key, vid, bypass=bypass)
    headers = {}
    if result["marker"]:
        headers["x-amz-delete-marker"] = "true"
    if result["id"]:
        headers["x-amz-version-id"] = result["id"]
    return Response(204, b"", headers)


def object_tagging(req: Request, bucket: Bucket) -> Response:
    vid = _version_id(req)
    need_auth(req, bucket, object_action("tagging", req.method, vid is not None), req.key, owner_only=True)
    with get_store().lock:
        version = find_version(bucket, req.key, vid)
        headers = {"x-amz-version-id": version["id"]} if bucket.meta.get("versioning") else {}
        if req.method == "GET":
            return Response(200, tags_xml(version.get("tags") or {}), headers)
    if req.method == "PUT":
        tags = tags_from_xml(req.small_body())
        with get_store().lock:
            version = find_version(bucket, req.key, vid)
            version["tags"] = tags
            bucket.save_record(req.key)
        return Response(200, b"", headers)
    if req.method == "DELETE":
        with get_store().lock:
            version = find_version(bucket, req.key, vid)
            version["tags"] = {}
            bucket.save_record(req.key)
        return Response(204, b"", headers)
    raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)


def object_acl(req: Request, bucket: Bucket) -> Response:
    vid = _version_id(req)
    need_auth(req, bucket, object_action("acl", req.method, vid is not None), req.key, owner_only=True)
    if req.method == "GET":
        with get_store().lock:
            version = find_version(bucket, req.key, vid)
            return Response(200, acl_xml(version.get("acl")))
    if req.method == "PUT":
        acl = acl_from_request(req.headers, req.small_body())
        if acl is None:
            raise malformed()
        if bucket_owner_enforced(bucket) and acl.get("canned") not in ("private", "bucket-owner-full-control"):
            raise S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs")
        if public_block(bucket)["BlockPublicAcls"] and acl_public(acl, "READ"):
            raise denied()
        with get_store().lock:
            version = find_version(bucket, req.key, vid)
            version["acl"] = acl
            bucket.save_record(req.key)
        return Response(200)
    raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)


def object_lock_route(req: Request, bucket: Bucket, sub: str) -> Response:
    vid = _version_id(req)
    need_auth(req, bucket, object_action(sub, req.method, vid is not None), req.key, owner_only=True)
    if not lock_config(bucket)["enabled"]:
        raise S3Error("InvalidRequest", "Bucket is missing Object Lock Configuration")
    if req.method == "GET":
        with get_store().lock:
            version = find_version(bucket, req.key, vid)
            if sub == "retention":
                if not version.get("retention"):
                    raise S3Error(
                        "NoSuchObjectLockConfiguration",
                        "The specified object does not have a ObjectLock configuration",
                        404,
                    )
                r = version["retention"]
                return xml_response("Retention", x("Mode", r["mode"]) + x("RetainUntilDate", iso(r["until"])))
            if "hold" not in version:
                raise S3Error(
                    "NoSuchObjectLockConfiguration",
                    "The specified object does not have a ObjectLock configuration",
                    404,
                )
            return xml_response("LegalHold", x("Status", "ON" if version["hold"] else "OFF"))
    if req.method == "PUT":
        root = parse_xml(req.small_body())
        bypass = req.headers.get("x-amz-bypass-governance-retention", "").lower() == "true"
        with get_store().lock:
            version = find_version(bucket, req.key, vid)
            if sub == "legal-hold":
                status = text(root, "Status")
                if status not in ("ON", "OFF"):
                    raise malformed()
                version["hold"] = status == "ON"
            else:
                mode, until = text(root, "Mode"), parse_time(text(root, "RetainUntilDate"))
                if (mode and mode not in ("GOVERNANCE", "COMPLIANCE")) or (mode and until is None):
                    raise malformed()
                old = version.get("retention") or {}
                if old.get("until", 0) > time.time():
                    shorter = (
                        not mode
                        or (until or 0) < old["until"]
                        or (old["mode"] == "COMPLIANCE" and mode != "COMPLIANCE")
                    )
                    if shorter and (old["mode"] == "COMPLIANCE" or not bypass):
                        raise denied("Access Denied because object protected by object lock.")
                if mode:
                    if until is not None and until <= time.time():
                        raise invalid("The retain until date must be in the future!")
                    version["retention"] = {"mode": mode, "until": until}
                else:
                    version.pop("retention", None)
            bucket.save_record(req.key)
        return Response(200)
    raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)


def object_attributes(req: Request, bucket: Bucket) -> Response:
    vid = _version_id(req)
    need_auth(req, bucket, "s3:GetObject", req.key)
    wanted = {a.strip() for a in req.headers.get("x-amz-object-attributes", "").split(",") if a.strip()}
    if not wanted:
        raise invalid(
            "The x-amz-object-attributes header specifying the attributes to be retrieved is either missing or empty",
            "x-amz-object-attributes",
            "",
        )
    with get_store().lock:
        version = dict(find_version(bucket, req.key, vid))
    inner = ""
    if "ETag" in wanted:
        inner += x("ETag", version["etag"])
    if "Checksum" in wanted and version.get("checksum"):
        cs = version["checksum"]
        value = x(checksum_element(cs["alg"]), cs["value"]) + x("ChecksumType", cs.get("type", "FULL_OBJECT"))
        inner += f"<Checksum>{value}</Checksum>"
    if "ObjectParts" in wanted and version.get("parts"):
        parts = version["parts"]
        marker = int(req.q.get("part-number-marker") or req.headers.get("x-amz-part-number-marker") or 0)
        max_parts = int(req.headers.get("x-amz-max-parts") or 1000)
        chosen = [(i + 1, p) for i, p in enumerate(parts) if i + 1 > marker][:max_parts]
        more = len([1 for i in range(len(parts)) if i + 1 > marker]) > max_parts
        items = ""
        for n, p in chosen:
            items += f"<Part>{x('PartNumber', n)}{x('Size', p['size'])}"
            if p.get("checksum") and version.get("checksum"):
                items += x(checksum_element(version["checksum"]["alg"]), p["checksum"])
            items += "</Part>"
        inner += (
            f"<ObjectParts>{x('TotalPartsCount', len(parts))}{x('PartNumberMarker', marker)}"
            f"{x('NextPartNumberMarker', chosen[-1][0] if chosen else marker)}{x('MaxParts', max_parts)}"
            f"{x('IsTruncated', 'true' if more else 'false')}{items}</ObjectParts>"
        )
    if "StorageClass" in wanted:
        inner += x("StorageClass", version.get("class", "STANDARD"))
    if "ObjectSize" in wanted:
        inner += x("ObjectSize", version["size"])
    headers = {"Last-Modified": http_date(version["time"])}
    if bucket.meta.get("versioning"):
        headers["x-amz-version-id"] = version["id"]
    return xml_response("GetObjectAttributesResponse", inner, headers=headers)


def restore_object(req: Request, bucket: Bucket) -> Response:
    vid = _version_id(req)
    need_auth(req, bucket, object_action("restore", req.method, vid is not None), req.key, owner_only=True)
    body = req.small_body()
    days = 1
    if body.strip():
        root = parse_xml(body)
        if text(root, "Type") == "SELECT":
            raise S3Error("NotImplemented", "S3 Select restore requests are not implemented.", 501)
        days = int(text(root, "Days") or 1)
    with get_store().lock:
        version = find_version(bucket, req.key, vid)
        if version.get("class") not in ARCHIVED:
            raise S3Error("InvalidObjectState", "Restore is not allowed for the object's current storage class", 403)
        already = bool(version.get("restore")) and version["restore"] > time.time()
        version["restore"] = time.time() + days * 86400
        bucket.save_record(req.key)
    return Response(200 if already else 202)
