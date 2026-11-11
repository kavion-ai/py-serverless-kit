"""Object attributes: a new object's fields from its headers, response headers, conditions, ranges, tags, copies."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote

from .access import acl_from_request, acl_public, allowed, bucket_owner_enforced, public_block
from .checksums import checksum_header
from .config import ARCHIVED, OWNER_ID, STD_HEADERS, STORAGE_CLASSES
from .errors import S3Error, denied, invalid
from .objectlock import lock_config
from .payload import Received
from .policy import Context
from .store import Bucket, get_store
from .util import doc, http_date, iso, parse_time, parse_xml, split_query, text, timestamp, x
from .versions import find_version


def parse_tagging(raw: str) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    for k, v in split_query(raw.replace("+", "%20")):
        tags[k] = v
    validate_tags(tags)
    return tags


def validate_tags(tags: Dict[str, str], limit: int = 10) -> None:
    if len(tags) > limit:
        raise S3Error("InvalidTag", f"Object tags cannot be greater than {limit}")
    for k, v in tags.items():
        if not k or len(k) > 128:
            raise S3Error("InvalidTag", "The TagKey you have provided is invalid")
        if len(v) > 256:
            raise S3Error("InvalidTag", "The TagValue you have provided is too long")
        if k.lower().startswith("aws:"):
            raise S3Error("InvalidTag", "Your TagKey cannot be prefixed with aws:")


def tags_from_xml(body: bytes, limit: int = 10) -> Dict[str, str]:
    root = parse_xml(body)
    tags: Dict[str, str] = {}
    for tag in root.iter("Tag"):
        key = text(tag, "Key")
        if key in tags:
            raise S3Error("InvalidTag", "Cannot provide multiple Tags with the same key")
        tags[key] = text(tag, "Value")
    validate_tags(tags, limit)
    return tags


def tags_xml(tags: Dict[str, str]) -> bytes:
    inner = "".join(f"<Tag>{x('Key', k)}{x('Value', v)}</Tag>" for k, v in sorted(tags.items()))
    return doc("Tagging", f"<TagSet>{inner}</TagSet>")


def object_fields(headers: Dict[str, str], bucket: Bucket) -> Dict[str, Any]:
    """The stored attributes of a new object from its request headers (PutObject, CreateMultipartUpload, copy)."""
    meta = {k[11:]: v for k, v in headers.items() if k.startswith("x-amz-meta-")}
    if sum(len(k) + len(v) for k, v in meta.items()) > 2048:
        raise S3Error("MetadataTooLarge", "Your metadata headers exceed the maximum allowed metadata size.")
    std = {k: headers[k] for k in STD_HEADERS if k in headers}
    sclass = headers.get("x-amz-storage-class", "STANDARD") or "STANDARD"
    if sclass not in STORAGE_CLASSES:
        raise S3Error(
            "InvalidStorageClass", "The storage class you specified is not valid", 400, StorageClassRequested=sclass
        )
    fields: Dict[str, Any] = {
        "type": headers.get("content-type") or "binary/octet-stream",
        "meta": meta,
        "headers": std,
        "class": sclass,
        "tags": parse_tagging(headers["x-amz-tagging"]) if headers.get("x-amz-tagging") else {},
        "owner": OWNER_ID,
    }
    acl = acl_from_request(headers, b"")
    if acl:
        if bucket_owner_enforced(bucket) and acl.get("canned") not in ("bucket-owner-full-control", "private"):
            raise S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs")
        if public_block(bucket)["BlockPublicAcls"] and acl_public(acl, "READ"):
            raise denied()
        fields["acl"] = acl
    redirect = headers.get("x-amz-website-redirect-location")
    if redirect:
        fields["redirect"] = redirect
    sse: Dict[str, str] = {}
    for name in (
        "x-amz-server-side-encryption",
        "x-amz-server-side-encryption-aws-kms-key-id",
        "x-amz-server-side-encryption-context",
        "x-amz-server-side-encryption-bucket-key-enabled",
        "x-amz-server-side-encryption-customer-algorithm",
        "x-amz-server-side-encryption-customer-key-md5",
    ):
        if headers.get(name):
            sse[name] = headers[name]
    if not sse:
        sse = default_encryption(bucket)
    fields["sse"] = sse
    lock = lock_config(bucket)
    mode, until = headers.get("x-amz-object-lock-mode", ""), headers.get("x-amz-object-lock-retain-until-date", "")
    hold = headers.get("x-amz-object-lock-legal-hold", "")
    if (mode or until or hold) and not lock["enabled"]:
        raise S3Error("InvalidRequest", "Bucket is missing Object Lock Configuration")
    if mode or until:
        if mode not in ("GOVERNANCE", "COMPLIANCE") or parse_time(until) is None:
            raise invalid("x-amz-object-lock-mode and x-amz-object-lock-retain-until-date must both be supplied")
        fields["retention"] = {"mode": mode, "until": parse_time(until)}
    elif lock["enabled"] and lock["mode"]:
        period = lock["days"] * 86400 + lock["years"] * 365 * 86400
        fields["retention"] = {"mode": lock["mode"], "until": time.time() + period}
    if hold:
        fields["hold"] = hold == "ON"
    return fields


def default_encryption(bucket: Bucket) -> Dict[str, str]:
    raw = (bucket.meta.get("configs") or {}).get("encryption", "")
    if raw:
        try:
            root = parse_xml(raw.encode())
            alg = text(root, "Rule/ApplyServerSideEncryptionByDefault/SSEAlgorithm") or "AES256"
            out = {"x-amz-server-side-encryption": alg}
            kms = text(root, "Rule/ApplyServerSideEncryptionByDefault/KMSMasterKeyID")
            if kms:
                out["x-amz-server-side-encryption-aws-kms-key-id"] = kms
            if text(root, "Rule/BucketKeyEnabled").lower() == "true":
                out["x-amz-server-side-encryption-bucket-key-enabled"] = "true"
            return out
        except S3Error:
            pass
    return {"x-amz-server-side-encryption": "AES256"}


def object_headers(version: Dict[str, Any], *, checksum: bool = False) -> Dict[str, str]:
    h: Dict[str, str] = {
        "ETag": f'"{version["etag"]}"',
        "Last-Modified": http_date(version["time"]),
        "Content-Type": version.get("type") or "binary/octet-stream",
        "Accept-Ranges": "bytes",
    }
    if version["id"] != "null" or version.get("versioned"):
        h["x-amz-version-id"] = version["id"]
    for k, v in (version.get("headers") or {}).items():
        h[k] = v
    for k, v in (version.get("meta") or {}).items():
        h["x-amz-meta-" + k] = v
    if version.get("class", "STANDARD") != "STANDARD":
        h["x-amz-storage-class"] = version["class"]
    if version.get("tags"):
        h["x-amz-tagging-count"] = str(len(version["tags"]))
    if version.get("redirect"):
        h["x-amz-website-redirect-location"] = version["redirect"]
    for k, v in (version.get("sse") or {}).items():
        if k != "x-amz-server-side-encryption-context":
            h[k] = v
    if version.get("retention"):
        h["x-amz-object-lock-mode"] = version["retention"]["mode"]
        h["x-amz-object-lock-retain-until-date"] = iso(version["retention"]["until"])
    if "hold" in version:
        h["x-amz-object-lock-legal-hold"] = "ON" if version["hold"] else "OFF"
    if version.get("parts"):
        h["x-amz-mp-parts-count"] = str(len(version["parts"]))
    if version.get("class") in ARCHIVED:
        restore = version.get("restore")
        if restore:
            h["x-amz-restore"] = f'ongoing-request="false", expiry-date="{http_date(restore)}"'
    if checksum and version.get("checksum"):
        cs = version["checksum"]
        h[checksum_header(cs["alg"])] = cs["value"]
        h["x-amz-checksum-type"] = cs.get("type", "FULL_OBJECT")
    return h


def check_conditions(
    version: Dict[str, Any], headers: Dict[str, str], prefix: str = "", *, write: bool = False
) -> None:
    """If-Match / If-None-Match / If-(Un)Modified-Since, AWS's precedence. ``prefix`` is "x-amz-copy-source-"."""
    etag = f'"{version["etag"]}"'
    modified = int(version["time"])
    if_match = headers.get(prefix + "if-match")
    if_none = headers.get(prefix + "if-none-match")
    if_mod = parse_time(headers.get(prefix + "if-modified-since", ""))
    if_unmod = parse_time(headers.get(prefix + "if-unmodified-since", ""))

    def matches(value: str) -> bool:
        return any(t.strip() in ("*", etag, etag.strip('"')) for t in value.split(","))

    if if_match is not None and not matches(if_match):
        raise S3Error(
            "PreconditionFailed",
            "At least one of the pre-conditions you specified did not hold",
            412,
            Condition="If-Match",
        )
    if if_unmod is not None and if_match is None and modified > if_unmod:
        raise S3Error(
            "PreconditionFailed",
            "At least one of the pre-conditions you specified did not hold",
            412,
            Condition="If-Unmodified-Since",
        )
    if if_none is not None and matches(if_none):
        if prefix or write:
            raise S3Error(
                "PreconditionFailed",
                "At least one of the pre-conditions you specified did not hold",
                412,
                Condition="If-None-Match",
            )
        raise S3Error("NotModified", "Not Modified", 304)
    if if_mod is not None and if_none is None and modified <= if_mod:
        if prefix:
            raise S3Error(
                "PreconditionFailed",
                "At least one of the pre-conditions you specified did not hold",
                412,
                Condition="If-Modified-Since",
            )
        raise S3Error("NotModified", "Not Modified", 304)


def parse_range(value: str, size: int) -> Optional[Tuple[int, int]]:
    match = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*", value or "")
    if not match or (not match.group(1) and not match.group(2)):
        return None  # S3 ignores a Range it cannot parse
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
        if start >= size or (last and int(last) < start):
            raise S3Error(
                "InvalidRange",
                "The requested range is not satisfiable",
                416,
                RangeRequested=value,
                ActualObjectSize=str(size),
            )
    else:
        suffix = int(last)
        if suffix == 0:
            raise S3Error(
                "InvalidRange",
                "The requested range is not satisfiable",
                416,
                RangeRequested=value,
                ActualObjectSize=str(size),
            )
        start, end = max(0, size - suffix), size - 1
    if size == 0:
        raise S3Error(
            "InvalidRange", "The requested range is not satisfiable", 416, RangeRequested=value, ActualObjectSize="0"
        )
    return start, end


def new_version(received: Received, fields: Dict[str, Any], blob: str) -> Dict[str, Any]:
    version = dict(fields)
    version.update({"blob": blob, "size": received.size, "etag": received.md5, "time": timestamp()})
    if received.checksum:
        alg, value = next(iter(received.checksum.items()))
        version["checksum"] = {"alg": alg, "value": value, "type": "FULL_OBJECT"}
    return version


def copy_source(headers: Dict[str, str]) -> Tuple[str, str, Optional[str]]:
    raw = headers.get("x-amz-copy-source", "")
    path, _q, query = raw.partition("?")
    path = unquote(path).lstrip("/")
    if path.startswith("arn:"):
        raise S3Error("NotImplemented", "Copying from an access point is not supported.", 501)
    src_bucket, _s, src_key = path.partition("/")
    if not src_bucket or not src_key:
        raise invalid(
            "Copy Source must mention the source bucket and key: sourcebucket/sourcekey", "x-amz-copy-source", raw
        )
    version_id = None
    for k, v in split_query(query):
        if k == "versionId":
            version_id = v
    return src_bucket, src_key, version_id


def read_source(headers: Dict[str, str], ctx: Context) -> Tuple[Bucket, str, Dict[str, Any], Path]:
    """The copy source of a CopyObject / UploadPartCopy, after the requester's read access and its conditions."""
    src_bucket_name, src_key, src_vid = copy_source(headers)
    with get_store().lock:
        src_bucket = get_store().get(src_bucket_name)
        version = find_version(src_bucket, src_key, src_vid)
        if not allowed(src_bucket, "s3:GetObject", ctx, src_key, version):
            raise denied()
        if version.get("class") in ARCHIVED and not version.get("restore"):
            raise S3Error(
                "InvalidObjectState",
                "The operation is not valid for the object's storage class",
                403,
                StorageClass=version["class"],
            )
        check_conditions(version, headers, "x-amz-copy-source-")
        return src_bucket, src_key, dict(version), src_bucket.blob_path(version["blob"])
