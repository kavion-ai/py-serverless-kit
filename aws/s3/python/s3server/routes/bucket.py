"""Bucket operations: create, head, delete, listings (objects, versions, uploads), DeleteObjects, CORS preflight."""

from __future__ import annotations

import bisect
from typing import Any, Dict, List, Tuple

from ..access import acl_from_request, allowed
from ..config import BUCKET_SUBRESOURCES, NS, OWNER_ID, OWNER_NAME, REGION
from ..cors import cors_match, cors_rules
from ..errors import S3Error, denied, invalid, malformed, no_bucket
from ..listing import contents_xml, list_keys, max_keys_param, token_decode, token_encode, visible
from ..request import Request, Response, config_action, need_auth, xml_response
from ..store import Bucket, create_bucket, delete_bucket, get_store
from ..util import esc, iso, owner_xml, parse_xml, text, url_enc, x
from ..versions import delete_object, find_version
from .config import bucket_config


def bucket_route(req: Request) -> Response:
    q, method = req.q, req.method
    sub = next((s for s in BUCKET_SUBRESOURCES if s in q), "")
    if method == "PUT" and not sub:
        return put_bucket(req)
    if method == "POST" and "delete" in q:
        return delete_objects(req)
    with get_store().lock:
        bucket = get_store().get(req.bucket)
    if method == "HEAD" and not sub:
        need_auth(req, bucket, "s3:ListBucket")
        return Response(
            200, b"", {"x-amz-bucket-region": bucket.meta.get("region") or REGION, "x-amz-access-point-alias": "false"}
        )
    if method == "DELETE" and not sub:
        need_auth(req, bucket, "s3:DeleteBucket", owner_only=True)
        delete_bucket(req.bucket)
        return Response(204)
    if method == "GET" and not sub:
        if q.get("list-type") == "2":
            need_auth(req, bucket, "s3:ListBucket")
            return list_objects_v2(req, bucket)
        need_auth(req, bucket, "s3:ListBucket")
        return list_objects_v1(req, bucket)
    if sub == "versions" and method == "GET":
        need_auth(req, bucket, "s3:ListBucketVersions")
        return list_versions(req, bucket)
    if sub == "uploads" and method == "GET":
        need_auth(req, bucket, "s3:ListBucketMultipartUploads")
        return list_uploads(req, bucket)
    if sub == "location" and method == "GET":
        need_auth(req, bucket, "s3:GetBucketLocation")
        region = bucket.meta.get("region") or REGION
        body = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n<LocationConstraint xmlns="{NS}">'
            f"{esc(region) if region != 'us-east-1' else ''}</LocationConstraint>"
        ).encode()
        return Response(200, body)
    need_auth(req, bucket, config_action(sub, method), owner_only=True)
    return bucket_config(req, bucket, sub)


def put_bucket(req: Request) -> Response:
    if req.who is None:
        raise denied()
    body = req.small_body()
    region = REGION
    if body.strip():
        root = parse_xml(body)
        region = text(root, "LocationConstraint") or REGION
    acl = acl_from_request(req.headers, b"")
    ownership = req.headers.get("x-amz-object-ownership", "")
    if ownership and ownership not in ("BucketOwnerPreferred", "ObjectWriter", "BucketOwnerEnforced"):
        raise invalid("Invalid x-amz-object-ownership header", "x-amz-object-ownership", ownership)
    if ownership == "BucketOwnerEnforced" and acl and acl.get("canned") not in ("private", "bucket-owner-full-control"):
        raise S3Error(
            "InvalidBucketAclWithObjectOwnership",
            "Bucket cannot have ACLs set with ObjectOwnership's BucketOwnerEnforced setting",
        )
    lock = req.headers.get("x-amz-bucket-object-lock-enabled", "").lower() == "true"
    create_bucket(req.bucket, region, acl, lock, ownership)
    return Response(200, b"", {"Location": "/" + req.bucket})


def preflight(req: Request) -> Response:
    origin = req.headers.get("origin", "")
    method = req.headers.get("access-control-request-method", "")
    if not origin or not method:
        raise S3Error("BadRequest", "Insufficient information. Origin request header needed.", 400)
    bucket = get_store().buckets.get(req.bucket)
    if bucket is None:
        raise no_bucket(req.bucket)
    if not cors_rules(bucket):
        raise S3Error("CORSResponse", "CORS is not enabled for this bucket.", 403)
    wanted = [h.strip().lower() for h in req.headers.get("access-control-request-headers", "").split(",") if h.strip()]
    found = cors_match(bucket, origin, method.upper(), wanted)
    if not found:
        raise S3Error(
            "CORSResponse",
            "This CORS request is not allowed. This is usually because the evalution of "
            "Origin, request method / Access-Control-Request-Method or Access-Control-Request-Headers are "
            "not whitelisted by the resource's CORS spec.",
            403,
        )
    return Response(200, b"", found)


def list_objects_v1(req: Request, bucket: Bucket) -> Response:
    q = req.q
    prefix, delimiter, marker = q.get("prefix", ""), q.get("delimiter", ""), q.get("marker", "")
    enc = q.get("encoding-type") == "url"
    if q.get("encoding-type") and not enc:
        raise invalid("Invalid Encoding Method specified in Request", "encoding-type", q["encoding-type"])
    max_keys = max_keys_param(q)
    with get_store().lock:
        keys, prefixes, truncated, last = list_keys(bucket, prefix, delimiter, marker, max_keys, visible(bucket))
        items = "".join(contents_xml(bucket, k, bucket.objects[k]["versions"][0], enc, True) for k in keys)
    inner = (
        x("Name", bucket.name)
        + x("Prefix", url_enc(prefix, enc))
        + x("Marker", url_enc(marker, enc))
        + x("MaxKeys", max_keys)
        + (x("Delimiter", url_enc(delimiter, enc)) if delimiter else "")
        + x("IsTruncated", "true" if truncated else "false")
    )
    if truncated:
        inner += x("NextMarker", url_enc(last, enc))
    inner += items + "".join(f"<CommonPrefixes>{x('Prefix', url_enc(p, enc))}</CommonPrefixes>" for p in prefixes)
    if enc:
        inner += x("EncodingType", "url")
    return xml_response("ListBucketResult", inner)


def list_objects_v2(req: Request, bucket: Bucket) -> Response:
    q = req.q
    prefix, delimiter, start_after = q.get("prefix", ""), q.get("delimiter", ""), q.get("start-after", "")
    token = q.get("continuation-token")
    enc = q.get("encoding-type") == "url"
    if q.get("encoding-type") and not enc:
        raise invalid("Invalid Encoding Method specified in Request", "encoding-type", q["encoding-type"])
    if token == "":
        raise invalid("The continuation token provided is incorrect", "continuation-token", "")
    after = token_decode(token) if token else start_after
    max_keys = max_keys_param(q)
    owner = q.get("fetch-owner") == "true"
    with get_store().lock:
        keys, prefixes, truncated, last = list_keys(bucket, prefix, delimiter, after, max_keys, visible(bucket))
        items = "".join(contents_xml(bucket, k, bucket.objects[k]["versions"][0], enc, owner) for k in keys)
    inner = (
        x("Name", bucket.name)
        + x("Prefix", url_enc(prefix, enc))
        + x("MaxKeys", max_keys)
        + (x("Delimiter", url_enc(delimiter, enc)) if delimiter else "")
        + x("IsTruncated", "true" if truncated else "false")
        + x("KeyCount", len(keys) + len(prefixes))
    )
    if token:
        inner += x("ContinuationToken", token)
    if start_after:
        inner += x("StartAfter", url_enc(start_after, enc))
    if truncated:
        inner += x("NextContinuationToken", token_encode(last))
    inner += items + "".join(f"<CommonPrefixes>{x('Prefix', url_enc(p, enc))}</CommonPrefixes>" for p in prefixes)
    if enc:
        inner += x("EncodingType", "url")
    return xml_response("ListBucketResult", inner)


def version_entries(
    bucket: Bucket, prefix: str, delimiter: str, key_marker: str, vid_marker: str, max_keys: int
) -> Tuple[List[Tuple[str, Dict[str, Any], bool]], List[str], bool, str, str]:
    keys = bucket.keys()
    i = bisect.bisect_left(keys, prefix)
    entries: List[Tuple[str, Dict[str, Any], bool]] = []
    prefixes: List[str] = []
    next_key, next_vid = "", ""
    count = 0
    if key_marker:
        i = max(i, bisect.bisect_left(keys, key_marker))
    while i < len(keys):
        key = keys[i]
        if not key.startswith(prefix):
            break
        if delimiter:
            pos = key.find(delimiter, len(prefix))
            if pos >= 0:
                common = key[: pos + len(delimiter)]
                if key_marker and (common <= key_marker or key_marker.startswith(common)):
                    i += 1
                    continue
                if count >= max_keys:
                    return entries, prefixes, True, next_key, next_vid
                prefixes.append(common)
                count += 1
                next_key, next_vid = common, ""
                while i < len(keys) and keys[i].startswith(common):
                    i += 1
                continue
        versions = bucket.objects[key]["versions"]
        start = 0
        if key_marker and key == key_marker:
            if not vid_marker:
                i += 1
                continue
            ids = [v["id"] for v in versions]
            start = ids.index(vid_marker) + 1 if vid_marker in ids else len(ids)
        for idx in range(start, len(versions)):
            if count >= max_keys:
                return entries, prefixes, True, next_key, next_vid
            entries.append((key, versions[idx], idx == 0))
            count += 1
            next_key, next_vid = key, versions[idx]["id"]
        i += 1
    return entries, prefixes, False, "", ""


def list_versions(req: Request, bucket: Bucket) -> Response:
    q = req.q
    prefix, delimiter = q.get("prefix", ""), q.get("delimiter", "")
    key_marker, vid_marker = q.get("key-marker", ""), q.get("version-id-marker", "")
    if vid_marker and not key_marker:
        raise invalid("A version-id marker cannot be specified without a key marker.", "version-id-marker", vid_marker)
    enc = q.get("encoding-type") == "url"
    max_keys = max_keys_param(q)
    with get_store().lock:
        entries, prefixes, truncated, next_key, next_vid = version_entries(
            bucket, prefix, delimiter, key_marker, vid_marker, max_keys
        )
        items = []
        for key, version, latest in entries:
            common = (
                x("Key", url_enc(key, enc))
                + x("VersionId", version["id"])
                + x("IsLatest", "true" if latest else "false")
                + x("LastModified", iso(version["time"]))
            )
            if version.get("dm"):
                items.append(f"<DeleteMarker>{common}{owner_xml()}</DeleteMarker>")
            else:
                cs = ""
                if version.get("checksum"):
                    cs = x("ChecksumAlgorithm", version["checksum"]["alg"]) + x(
                        "ChecksumType", version["checksum"].get("type", "FULL_OBJECT")
                    )
                items.append(
                    f"<Version>{common}{x('ETag', chr(34) + version['etag'] + chr(34))}"
                    f"{x('Size', version['size'])}{x('StorageClass', version.get('class', 'STANDARD'))}"
                    f"{cs}{owner_xml()}</Version>"
                )
    inner = (
        x("Name", bucket.name)
        + x("Prefix", url_enc(prefix, enc))
        + x("KeyMarker", url_enc(key_marker, enc))
        + x("VersionIdMarker", vid_marker)
        + x("MaxKeys", max_keys)
        + (x("Delimiter", url_enc(delimiter, enc)) if delimiter else "")
        + x("IsTruncated", "true" if truncated else "false")
    )
    if truncated:
        inner += x("NextKeyMarker", url_enc(next_key, enc))
        if next_vid:
            inner += x("NextVersionIdMarker", next_vid)
    inner += "".join(items) + "".join(
        f"<CommonPrefixes>{x('Prefix', url_enc(p, enc))}</CommonPrefixes>" for p in prefixes
    )
    if enc:
        inner += x("EncodingType", "url")
    return xml_response("ListVersionsResult", inner)


def list_uploads(req: Request, bucket: Bucket) -> Response:
    q = req.q
    prefix, delimiter = q.get("prefix", ""), q.get("delimiter", "")
    key_marker, id_marker = q.get("key-marker", ""), q.get("upload-id-marker", "")
    max_uploads = max_keys_param(q, "max-uploads")
    enc = q.get("encoding-type") == "url"
    with get_store().lock:
        ups = sorted(bucket.uploads.values(), key=lambda u: (u["key"], u["initiated"], u["id"]))
    items, prefixes = [], []
    truncated, next_key, next_id = False, "", ""
    for up in ups:
        key = up["key"]
        if not key.startswith(prefix):
            continue
        if key_marker and (key < key_marker or (key == key_marker and (not id_marker or up["id"] <= id_marker))):
            continue
        if delimiter:
            pos = key.find(delimiter, len(prefix))
            if pos >= 0:
                common = key[: pos + len(delimiter)]
                if common in prefixes:
                    continue
                if len(items) + len(prefixes) >= max_uploads:
                    truncated = True
                    break
                prefixes.append(common)
                continue
        if len(items) + len(prefixes) >= max_uploads:
            truncated = True
            break
        items.append(
            f"<Upload>{x('Key', url_enc(key, enc))}{x('UploadId', up['id'])}"
            f"<Initiator>{x('ID', OWNER_ID)}{x('DisplayName', OWNER_NAME)}</Initiator>{owner_xml()}"
            f"{x('StorageClass', up['fields'].get('class', 'STANDARD'))}{x('Initiated', iso(up['initiated']))}"
            + (
                x("ChecksumAlgorithm", up["alg"]) + x("ChecksumType", up.get("ctype", "COMPOSITE"))
                if up.get("alg")
                else ""
            )
            + "</Upload>"
        )
        next_key, next_id = key, up["id"]
    inner = (
        x("Bucket", bucket.name)
        + x("KeyMarker", url_enc(key_marker, enc))
        + x("UploadIdMarker", id_marker)
        + x("NextKeyMarker", url_enc(next_key, enc) if truncated else "")
        + x("NextUploadIdMarker", next_id if truncated else "")
        + x("Prefix", url_enc(prefix, enc))
        + (x("Delimiter", url_enc(delimiter, enc)) if delimiter else "")
        + x("MaxUploads", max_uploads)
        + x("IsTruncated", "true" if truncated else "false")
        + "".join(items)
        + "".join(f"<CommonPrefixes>{x('Prefix', url_enc(p, enc))}</CommonPrefixes>" for p in prefixes)
    )
    if enc:
        inner += x("EncodingType", "url")
    return xml_response("ListMultipartUploadsResult", inner)


def delete_objects(req: Request) -> Response:
    with get_store().lock:
        bucket = get_store().get(req.bucket)
    root = parse_xml(req.small_body())
    if root.tag != "Delete":
        raise malformed()
    quiet = text(root, "Quiet").lower() == "true"
    objects = root.findall("Object")
    if len(objects) > 1000:
        raise malformed()
    bypass = req.headers.get("x-amz-bypass-governance-retention", "").lower() == "true"
    out = []
    ctx = req.context()
    for obj in objects:
        key = text(obj, "Key")
        vid_el = obj.find("VersionId")
        vid = (vid_el.text or "").strip() if vid_el is not None else None
        try:
            if not allowed(bucket, "s3:DeleteObject", ctx, key):
                raise denied()
            if vid_el is not None and not vid:
                raise S3Error("NoSuchVersion", "The specified version does not exist.", 404)
            etag = text(obj, "ETag")
            with get_store().lock:
                if etag:
                    current = find_version(bucket, key, vid)
                    if etag.strip('"') != current["etag"]:
                        raise S3Error(
                            "PreconditionFailed", "At least one of the pre-conditions you specified did not hold", 412
                        )
                result = delete_object(bucket, key, vid, bypass=bypass)
            if not quiet:
                item = x("Key", key)
                if vid:
                    item += x("VersionId", vid)
                if result["marker"]:
                    item += x("DeleteMarker", "true")
                    if not vid:
                        item += x("DeleteMarkerVersionId", result["id"])
                    else:
                        item += x("DeleteMarkerVersionId", vid)
                out.append(f"<Deleted>{item}</Deleted>")
        except S3Error as exc:
            out.append(
                f"<Error>{x('Key', key)}{x('VersionId', vid) if vid else ''}{x('Code', exc.code)}"
                f"{x('Message', exc.message)}</Error>"
            )
    return xml_response("DeleteResult", "".join(out))
