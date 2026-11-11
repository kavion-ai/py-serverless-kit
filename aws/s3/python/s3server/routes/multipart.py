"""Multipart uploads: create, upload part (and part copy), complete, abort, list parts."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
from typing import Any, Dict
from urllib.parse import quote

from ..checksums import checksum_element, checksum_header, checksum_of, new_checksum
from ..config import ALGORITHMS, MAX_PARTS, MIN_PART, OWNER_ID, OWNER_NAME, PORT
from ..errors import S3Error, invalid, malformed
from ..objects import object_fields, read_source
from ..payload import copy_file, wanted_checksum
from ..request import Request, Response, xml_response
from ..store import Bucket, abort_upload, get_store, unlink, write_json
from ..util import iso, owner_xml, parse_xml, text, timestamp, x
from ..versions import put_version


def create_upload(req: Request, bucket: Bucket) -> Response:
    fields = object_fields(req.headers, bucket)
    alg = (req.headers.get("x-amz-checksum-algorithm") or "").upper()
    if alg and alg not in ALGORITHMS:
        raise invalid(f"Checksum algorithm {alg} is not supported.", "x-amz-checksum-algorithm", alg)
    ctype = (req.headers.get("x-amz-checksum-type") or ("FULL_OBJECT" if alg == "CRC64NVME" else "COMPOSITE")).upper()
    if ctype not in ("COMPOSITE", "FULL_OBJECT"):
        raise invalid("Invalid checksum type", "x-amz-checksum-type", ctype)
    if ctype == "FULL_OBJECT" and alg in ("SHA1", "SHA256"):
        raise invalid("The FULL_OBJECT checksum type is not supported for this algorithm", "x-amz-checksum-type", ctype)
    upload_id = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=").replace("-", ".")
    up = {
        "id": upload_id,
        "key": req.key,
        "initiated": timestamp(),
        "fields": fields,
        "alg": alg,
        "ctype": ctype if alg else "",
        "owner": req.who or "anonymous",
    }
    with get_store().lock:
        write_json(bucket.upload_dir(upload_id) / "upload.json", up)
        up["parts"] = {}
        bucket.uploads[upload_id] = up
    inner = x("Bucket", bucket.name) + x("Key", req.key) + x("UploadId", upload_id)
    headers = {}
    if alg:
        headers = {"x-amz-checksum-algorithm": alg, "x-amz-checksum-type": ctype}
    for k, v in (fields.get("sse") or {}).items():
        if k != "x-amz-server-side-encryption-context":
            headers[k] = v
    return xml_response("InitiateMultipartUploadResult", inner, headers=headers)


def _get_upload(bucket: Bucket, upload_id: str, key: str) -> Dict[str, Any]:
    up = bucket.uploads.get(upload_id)
    if up is None or up["key"] != key:
        raise S3Error(
            "NoSuchUpload",
            "The specified upload does not exist. The upload ID may be invalid, or the "
            "upload may have been aborted or completed.",
            404,
            UploadId=upload_id,
        )
    return up


def upload_part(req: Request, bucket: Bucket, upload_id: str) -> Response:
    try:
        n = int(req.q.get("partNumber", ""))
    except ValueError:
        n = 0
    if n < 1 or n > MAX_PARTS:
        raise invalid(
            "Part number must be an integer between 1 and 10000, inclusive", "partNumber", req.q.get("partNumber", "")
        )
    with get_store().lock:
        up = _get_upload(bucket, upload_id, req.key)
    copy = "x-amz-copy-source" in req.headers
    if copy:
        _sb, _sk, src, src_path = read_source(req.headers, req.context())
        size = int(src["size"])
        start, end = 0, size - 1
        rng = req.headers.get("x-amz-copy-source-range")
        if rng:
            match = re.fullmatch(r"bytes=(\d+)-(\d+)", rng.strip())
            if not match or int(match.group(1)) > int(match.group(2)) or int(match.group(2)) >= size:
                raise invalid(
                    "The x-amz-copy-source-range value must be of the form bytes=first-last where first "
                    "and last are the zero-based offsets of the first and last bytes to copy",
                    "x-amz-copy-source-range",
                    rng,
                )
            start, end = int(match.group(1)), int(match.group(2))
        received = copy_file(src_path, start, end, up.get("alg", ""))
    else:
        alg, expected = wanted_checksum(req.headers)
        if up.get("alg") and alg and alg != up["alg"]:
            raise invalid(
                f"Checksum Type mismatch occurred, expected checksum Type: {up['alg'].lower()}, actual "
                f"checksum Type: {alg.lower()}",
                "x-amz-checksum-algorithm",
                alg,
            )
        received = req.payload(up.get("alg") or alg, expected)
    part = {"n": n, "size": received.size, "etag": received.md5, "time": timestamp()}
    if received.checksum:
        part["checksum"] = next(iter(received.checksum.values()))
    try:
        with get_store().lock:
            up = _get_upload(bucket, upload_id, req.key)
            dest = bucket.upload_dir(upload_id) / (f"{n:05d}.part")
            os.replace(str(received.path), str(dest))
            received.path = None
            write_json(bucket.upload_dir(upload_id) / (f"{n:05d}.json"), part)
            up["parts"][n] = part
    finally:
        if received.path:
            unlink(received.path)
    headers = {}
    if part.get("checksum") and up.get("alg"):
        headers[checksum_header(up["alg"])] = part["checksum"]
    if copy:
        inner = x("LastModified", iso(part["time"])) + x("ETag", f'"{part["etag"]}"')
        if part.get("checksum") and up.get("alg"):
            inner += x(checksum_element(up["alg"]), part["checksum"])
        return xml_response("CopyPartResult", inner, headers=headers)
    headers["ETag"] = f'"{part["etag"]}"'
    for k, v in (up["fields"].get("sse") or {}).items():
        if k != "x-amz-server-side-encryption-context":
            headers[k] = v
    return Response(200, b"", headers)


def complete_upload(req: Request, bucket: Bucket, upload_id: str) -> Response:
    root = parse_xml(req.small_body())
    if root.tag != "CompleteMultipartUpload":
        raise malformed()
    with get_store().lock:
        up = _get_upload(bucket, upload_id, req.key)
        parts = dict(up["parts"])
    alg = up.get("alg", "")
    wanted = []
    for el in root.findall("Part"):
        try:
            wanted.append(
                (
                    int(text(el, "PartNumber")),
                    text(el, "ETag").strip('"'),
                    text(el, checksum_element(alg)) if alg else "",
                )
            )
        except ValueError:
            raise malformed() from None
    if not wanted:
        raise S3Error(
            "MalformedXML", "The XML you provided was not well-formed or did not validate against our published schema"
        )
    numbers = [w[0] for w in wanted]
    if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
        raise S3Error(
            "InvalidPartOrder",
            "The list of parts was not in ascending order. Parts must be ordered by part number.",
            400,
            UploadId=upload_id,
        )
    chosen = []
    for idx, (n, etag, cs) in enumerate(wanted):
        part = parts.get(n)
        if part is None or part["etag"] != etag or (cs and part.get("checksum") and cs != part["checksum"]):
            raise S3Error(
                "InvalidPart",
                "One or more of the specified parts could not be found. The part may not have "
                "been uploaded, or the specified entity tag may not match the part's entity tag.",
                400,
                UploadId=upload_id,
                PartNumber=str(n),
                ETag=etag,
            )
        if idx < len(wanted) - 1 and part["size"] < MIN_PART:
            raise S3Error(
                "EntityTooSmall",
                "Your proposed upload is smaller than the minimum allowed object size.",
                400,
                ProposedSize=str(part["size"]),
                MinSizeAllowed=str(MIN_PART),
                PartNumber=str(n),
                ETag=etag,
            )
        chosen.append(part)
    if req.headers.get("if-none-match") == "*":
        with get_store().lock:
            rec = bucket.objects.get(req.key)
            if rec and not rec["versions"][0].get("dm"):
                raise S3Error(
                    "PreconditionFailed",
                    "At least one of the pre-conditions you specified did not hold",
                    412,
                    Condition="If-None-Match",
                )
    full = new_checksum(alg) if alg and up.get("ctype") == "FULL_OBJECT" else None
    tmp = get_store().temp_file()
    total = 0
    with open(tmp, "wb") as out:
        for part in chosen:
            with open(bucket.upload_dir(upload_id) / (f"{part['n']:05d}.part"), "rb") as fin:
                while True:
                    data = fin.read(1024 * 1024)
                    if not data:
                        break
                    if full:
                        full.update(data)
                    out.write(data)
                    total += len(data)
    etag = hashlib.md5(b"".join(bytes.fromhex(p["etag"]) for p in chosen)).hexdigest() + f"-{len(chosen)}"  # noqa: S324
    checksum = None
    if alg:
        if full:
            value = base64.b64encode(full.digest()).decode()
            checksum = {"alg": alg, "value": value, "type": "FULL_OBJECT"}
        elif all(p.get("checksum") for p in chosen):
            joined = b"".join(base64.b64decode(p["checksum"]) for p in chosen)
            checksum = {"alg": alg, "value": checksum_of(alg, joined) + f"-{len(chosen)}", "type": "COMPOSITE"}
        sent = req.headers.get(checksum_header(alg))
        if sent and checksum and sent != checksum["value"] and sent != checksum["value"].split("-")[0]:
            unlink(tmp)
            raise S3Error(
                "BadDigest", f"The {alg} you specified for the full object did not match the calculated checksum."
            )
    try:
        with get_store().lock:
            up = _get_upload(bucket, upload_id, req.key)
            blob = get_store().commit_blob(bucket, tmp)
            version = dict(up["fields"])
            version.update(
                {
                    "blob": blob,
                    "size": total,
                    "etag": etag,
                    "time": timestamp(),
                    "parts": [
                        {
                            "size": p["size"],
                            "etag": p["etag"],
                            **({"checksum": p["checksum"]} if p.get("checksum") else {}),
                        }
                        for p in chosen
                    ],
                }
            )
            if checksum:
                version["checksum"] = checksum
            version = put_version(bucket, req.key, version)
            abort_upload(bucket, upload_id)
    finally:
        if tmp.exists():
            unlink(tmp)
    host = req.host or f"127.0.0.1:{PORT}"
    inner = (
        x("Location", f"http://{host}/{bucket.name}/{quote(req.key)}")
        + x("Bucket", bucket.name)
        + x("Key", req.key)
        + x("ETag", f'"{etag}"')
    )
    if checksum:
        inner += x(checksum_element(alg), checksum["value"]) + x("ChecksumType", checksum["type"])
    headers = {}
    if bucket.meta.get("versioning"):
        headers["x-amz-version-id"] = version["id"]
    for k, v in (version.get("sse") or {}).items():
        if k != "x-amz-server-side-encryption-context":
            headers[k] = v
    return xml_response("CompleteMultipartUploadResult", inner, headers=headers)


def list_parts(req: Request, bucket: Bucket, upload_id: str) -> Response:
    with get_store().lock:
        up = _get_upload(bucket, upload_id, req.key)
        parts = sorted(up["parts"].values(), key=lambda p: p["n"])
    marker = int(req.q.get("part-number-marker") or 0)
    max_parts = min(int(req.q.get("max-parts") or 1000), 1000)
    after = [p for p in parts if p["n"] > marker]
    page = after[:max_parts]
    truncated = len(after) > max_parts
    alg = up.get("alg", "")
    items = ""
    for p in page:
        items += (
            f"<Part>{x('PartNumber', p['n'])}{x('LastModified', iso(p['time']))}"
            f"{x('ETag', chr(34) + p['etag'] + chr(34))}{x('Size', p['size'])}"
        )
        if alg and p.get("checksum"):
            items += x(checksum_element(alg), p["checksum"])
        items += "</Part>"
    inner = (
        x("Bucket", bucket.name)
        + x("Key", req.key)
        + x("UploadId", upload_id)
        + f"<Initiator>{x('ID', OWNER_ID)}{x('DisplayName', OWNER_NAME)}</Initiator>"
        + owner_xml()
        + x("StorageClass", up["fields"].get("class", "STANDARD"))
        + x("PartNumberMarker", marker)
        + x("NextPartNumberMarker", page[-1]["n"] if page else marker)
        + x("MaxParts", max_parts)
        + x("IsTruncated", "true" if truncated else "false")
        + items
    )
    if alg:
        inner += x("ChecksumAlgorithm", alg) + x("ChecksumType", up.get("ctype") or "COMPOSITE")
    return xml_response("ListPartsResult", inner)
