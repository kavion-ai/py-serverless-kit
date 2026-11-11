"""Browser POST uploads: multipart/form-data with a signed POST policy (or anonymous, when the bucket allows it)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
from typing import Dict, Optional, Tuple
from urllib.parse import quote

from ..access import allowed
from ..checksums import checksum_of
from ..config import AUTH, CREDENTIALS, MAX_POST, STD_HEADERS
from ..errors import S3Error, denied, invalid
from ..objects import new_version, object_fields, tags_from_xml
from ..payload import Received, wanted_checksum
from ..request import Request, Response
from ..sigv4 import Auth, signing_key
from ..store import get_store, unlink
from ..util import parse_time, x
from ..versions import put_version


def _form_fields(body: bytes, ctype: str) -> Tuple[Dict[str, str], Optional[Tuple[str, str, bytes]]]:
    match = re.search(r'boundary="?([^";]+)"?', ctype)
    if not match:
        raise S3Error("MalformedPOSTRequest", "The body of your POST request is not well-formed multipart/form-data.")
    boundary = b"--" + match.group(1).encode()
    fields: Dict[str, str] = {}
    file_part = None
    for chunk in body.split(boundary)[1:]:
        if chunk.startswith(b"--"):
            break
        head, _sep, data = chunk.lstrip(b"\r\n").partition(b"\r\n\r\n")
        if data.endswith(b"\r\n"):
            data = data[:-2]
        disposition = ""
        part_type = ""
        for line in head.decode("utf-8", "replace").split("\r\n"):
            name, _c, value = line.partition(":")
            if name.strip().lower() == "content-disposition":
                disposition = value
            elif name.strip().lower() == "content-type":
                part_type = value.strip()
        field = re.search(r'name="([^"]*)"', disposition)
        if not field:
            continue
        filename = re.search(r'filename="([^"]*)"', disposition)
        if field.group(1).lower() == "file":
            file_part = (filename.group(1) if filename else "", part_type, data)
            break
        fields[field.group(1).lower()] = data.decode("utf-8")
    return fields, file_part


def post_object(req: Request) -> Response:
    with get_store().lock:
        bucket = get_store().get(req.bucket)
    length = int(req.headers.get("content-length") or 0)
    if length > MAX_POST:
        raise S3Error("EntityTooLarge", "Your proposed upload exceeds the maximum allowed size", 400)
    body = req.small_body(MAX_POST)
    fields, file_part = _form_fields(body, req.headers.get("content-type", ""))
    if file_part is None:
        raise invalid("POST requires exactly one file upload per request.", "file", "0")
    filename, part_type, data = file_part
    key = fields.get("key", "")
    if not key:
        raise invalid(
            "Bucket POST must contain a field named 'key'.  If it is specified, please check the order of the fields.",
            "key",
            "",
        )
    key = key.replace("${filename}", filename)
    if AUTH == "off":
        req.auth = Auth("anonymous", "off")
    elif "x-amz-signature" in fields or "signature" in fields:
        policy_b64 = fields.get("policy", "")
        if not policy_b64:
            raise invalid("Bucket POST must contain a field named 'policy'.", "policy", "")
        if "x-amz-signature" in fields:
            if fields.get("x-amz-algorithm") != "AWS4-HMAC-SHA256":
                raise invalid(
                    "Only AWS4-HMAC-SHA256 is supported.", "x-amz-algorithm", fields.get("x-amz-algorithm", "")
                )
            parts = fields.get("x-amz-credential", "").split("/")
            if len(parts) != 5:
                raise invalid("The Credential is not valid.", "x-amz-credential", fields.get("x-amz-credential", ""))
            secret = CREDENTIALS.get(parts[0])
            if secret is None:
                raise S3Error(
                    "InvalidAccessKeyId", "The AWS Access Key Id you provided does not exist in our records.", 403
                )
            expected = hmac.new(
                signing_key(secret, parts[1], parts[2], parts[3]), policy_b64.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, fields["x-amz-signature"]):
                raise S3Error(
                    "SignatureDoesNotMatch",
                    "The request signature we calculated does not match the signature you provided.",
                    403,
                )
            req.auth = Auth(parts[0], "sigv4")
        else:
            secret = CREDENTIALS.get(fields.get("awsaccesskeyid", ""))
            if secret is None:
                raise S3Error(
                    "InvalidAccessKeyId", "The AWS Access Key Id you provided does not exist in our records.", 403
                )
            expected = base64.b64encode(hmac.new(secret.encode(), policy_b64.encode(), hashlib.sha1).digest()).decode()
            if not hmac.compare_digest(expected, fields["signature"]):
                raise S3Error(
                    "SignatureDoesNotMatch",
                    "The request signature we calculated does not match the signature you provided.",
                    403,
                )
            req.auth = Auth(fields["awsaccesskeyid"], "sigv2")
        req.auth.via = "POST"
        check_post_policy(policy_b64, fields, bucket.name, key, len(data))
    if not allowed(bucket, "s3:PutObject", req.context(), key):
        raise denied()
    headers = {
        k: v
        for k, v in fields.items()
        if k.startswith("x-amz-meta-")
        or k in STD_HEADERS
        or k in ("x-amz-storage-class", "x-amz-server-side-encryption", "x-amz-website-redirect-location", "acl")
    }
    if "acl" in headers:
        headers["x-amz-acl"] = headers.pop("acl")
    headers["content-type"] = fields.get("content-type") or part_type or "binary/octet-stream"
    if fields.get("tagging"):
        tags = tags_from_xml(fields["tagging"].encode())
        headers["x-amz-tagging"] = "&".join(f"{quote(k)}={quote(v)}" for k, v in tags.items())
    fields_obj = object_fields(headers, bucket)
    alg, expected_cs = wanted_checksum({k: v for k, v in fields.items() if k.startswith("x-amz-checksum-")})
    received = Received()
    received.path = get_store().temp_file()
    received.path.write_bytes(data)
    received.size = len(data)
    received.md5 = hashlib.md5(data).hexdigest()  # noqa: S324
    if alg:
        received.checksum = {alg: checksum_of(alg, data)}
        if expected_cs and expected_cs != received.checksum[alg]:
            unlink(received.path)
            raise S3Error("BadDigest", f"The {alg} you specified did not match the calculated checksum.")
    with get_store().lock:
        blob = get_store().commit_blob(bucket, received.path)
        version = put_version(bucket, key, new_version(received, fields_obj, blob))
    etag = f'"{version["etag"]}"'
    location = f"http://{req.host}/{bucket.name}/{quote(key)}"
    out_headers = {"ETag": etag, "Location": location}
    if bucket.meta.get("versioning"):
        out_headers["x-amz-version-id"] = version["id"]
    redirect = fields.get("success_action_redirect") or fields.get("redirect")
    if redirect:
        sep = "&" if "?" in redirect else "?"
        out_headers["Location"] = f"{redirect}{sep}bucket={quote(bucket.name)}&key={quote(key)}&etag={quote(etag)}"
        return Response(303, b"", out_headers)
    status = fields.get("success_action_status", "204")
    if status == "201":
        inner = x("Location", location) + x("Bucket", bucket.name) + x("Key", key) + x("ETag", etag)
        return Response(
            201, f'<?xml version="1.0" encoding="UTF-8"?>\n<PostResponse>{inner}</PostResponse>'.encode(), out_headers
        )
    return Response(200 if status == "200" else 204, b"", out_headers)


def check_post_policy(policy_b64: str, fields: Dict[str, str], bucket: str, key: str, size: int) -> None:
    try:
        policy = json.loads(base64.b64decode(policy_b64))
    except (ValueError, binascii.Error):
        raise invalid("Invalid Policy: Invalid JSON.", "policy", "") from None
    expiration = parse_time(str(policy.get("expiration", "")))
    if expiration is None or expiration < time.time():
        raise denied("Invalid according to Policy: Policy expired.")
    values = dict(fields)
    values["bucket"] = bucket
    values["key"] = key
    covered = {"bucket"}
    for cond in policy.get("conditions") or []:
        if isinstance(cond, dict):
            for name, want in cond.items():
                name = name.lower()
                covered.add(name)
                if str(values.get(name, "")) != str(want):
                    raise denied(f'Invalid according to Policy: Policy Condition failed: ["eq", "${name}", "{want}"]')
        elif isinstance(cond, list) and len(cond) == 3:
            op = str(cond[0]).lower()
            if op == "content-length-range":
                if not int(cond[1]) <= size <= int(cond[2]):
                    raise S3Error(
                        "EntityTooLarge" if size > int(cond[2]) else "EntityTooSmall",
                        "Your proposed upload size does not match the policy's content-length-range.",
                    )
                continue
            name = str(cond[1]).lstrip("$").lower()
            covered.add(name)
            value = str(values.get(name, ""))
            if op == "eq" and value != str(cond[2]):
                raise denied(f"Invalid according to Policy: Policy Condition failed: {json.dumps(cond)}")
            if op == "starts-with":
                prefixes = [p.strip() for p in str(cond[2]).split(",")] if name == "content-type" else [str(cond[2])]
                if not any(value.startswith(p) for p in prefixes):
                    raise denied(f"Invalid according to Policy: Policy Condition failed: {json.dumps(cond)}")
    for name in fields:
        if name in ("policy", "x-amz-signature", "signature", "file", "awsaccesskeyid") or name.startswith("x-ignore-"):
            continue
        if name not in covered:
            raise denied(f"Invalid according to Policy: Extra input fields: {name}")
