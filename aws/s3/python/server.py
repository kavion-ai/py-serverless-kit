"""An Amazon S3 compatible server (Python, standard library only).

boto3, the AWS SDKs (JavaScript v3, Java, Go, ...), the AWS CLI (``aws s3`` and ``aws s3api``), rclone, s3cmd and
pskit's ``s3`` storage driver talk to it unchanged: point their endpoint at this server and sign with an access key /
secret key it knows. Requests are checked with AWS Signature Version 4 (headers, presigned URLs, streaming chunk
signatures, browser POST policies) or Version 2, so a wrong secret key is refused.

Buckets: create / delete / head / list, location, versioning (Enabled / Suspended), tags, policies (anonymous access
follows them), ACLs (canned and grants), CORS (applied), lifecycle rules (applied: expiration, noncurrent versions,
delete markers, incomplete uploads, transitions), static website hosting, object lock (governance / compliance
retention, legal hold), public access block, ownership controls, default encryption, and logging, notification,
replication, accelerate, request payment, metrics, analytics, inventory and intelligent-tiering configurations
(stored and returned).

Objects: put / get / head / delete / copy, ranges, part numbers, conditional requests (If-Match, If-None-Match,
If-Modified-Since, If-Unmodified-Since, also on writes), user metadata and standard headers, response header
overrides, tags, ACLs, storage classes, checksums (CRC32, CRC32C, CRC64NVME, SHA1, SHA256, Content-MD5), version ids
and delete markers, multi-object delete, GetObjectAttributes, restore (archive storage classes), multipart uploads
(upload part copy, list parts / uploads, composite and full-object checksums) and SSE headers (accepted and returned;
the data is not encrypted at rest).

A web console (``/ui/``) browses buckets and folders, uploads (drag and drop), downloads, copies, moves, deletes,
shows versions, edits metadata and tags, makes share links and edits every bucket setting. It signs in with an access
key and its secret key (or ``S3_UI_PASSWORD``) and keeps the session in an HttpOnly cookie.

Settings (environment):

``S3_ACCESS_KEY_ID`` / ``S3_SECRET_ACCESS_KEY``
    The credentials clients sign with (``aws_access_key_id`` / ``aws_secret_access_key``).
``S3_CREDENTIALS``
    More credentials: ``id1:secret1,id2:secret2``.
``S3_AUTH``
    ``sigv4`` (default: Signature Version 4 and 2) or ``off`` (no authentication: development only).
``S3_PORT`` (9000), ``S3_BIND`` (0.0.0.0), ``S3_DATA_DIR`` (./data), ``S3_REGION`` (us-east-1),
``S3_ACCOUNT_ID`` (000000000000)
    Where it listens, where the data lives, and the region / account it reports.
``S3_DOMAIN`` (``localhost``)
    Comma-separated domains for virtual-hosted style requests (``<bucket>.<domain>``).
``S3_UI`` (``on``), ``S3_UI_PASSWORD``
    The web console, and a console password other than the secret key.
``S3_MAX_OBJECT_SIZE`` (5 GiB), ``S3_MIN_PART_SIZE`` (5 MiB), ``S3_LIFECYCLE_INTERVAL`` (3600 seconds),
``S3_LIFECYCLE_DAY_SECONDS`` (86400)
    Limits and the lifecycle sweep (a shorter "day" makes lifecycle rules testable).

The data lives under ``S3_DATA_DIR/buckets``: ``bucket.json`` per bucket, one JSON record per key and one file per
object version. The Node.js server (``../nodejs/server.js``) reads and writes the same layout.

``python server.py --check`` exits 0 when the server answers on ``/-/health`` (a container health check).
"""

from __future__ import annotations

import base64
import binascii
import bisect
import email.utils
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET  # noqa: S405 - bodies are size-limited; expat refuses external entities
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote, unquote, urlsplit

VERSION = "1.0.0"
ENV = os.environ
PORT = int(ENV.get("S3_PORT") or 9000)
BIND = ENV.get("S3_BIND") or "0.0.0.0"  # noqa: S104 - a server; set S3_BIND=127.0.0.1 to keep it local
DATA_DIR = Path(ENV.get("S3_DATA_DIR") or Path.cwd() / "data")
REGION = ENV.get("S3_REGION") or "us-east-1"
ACCOUNT = ENV.get("S3_ACCOUNT_ID") or "000000000000"
AUTH = (ENV.get("S3_AUTH") or "sigv4").lower()
DOMAINS = [d.strip().lower() for d in (ENV.get("S3_DOMAIN") or "localhost").split(",") if d.strip()]
UI_ON = (ENV.get("S3_UI") or "on").lower() not in ("off", "0", "false", "no")
UI_PASSWORD = ENV.get("S3_UI_PASSWORD") or ""
UI_FILE = ENV.get("S3_UI_FILE") or ""
MAX_OBJECT = int(ENV.get("S3_MAX_OBJECT_SIZE") or 5 * 1024**3)
MIN_PART = int(ENV.get("S3_MIN_PART_SIZE") or 5 * 1024**2)
LIFECYCLE_INTERVAL = float(ENV.get("S3_LIFECYCLE_INTERVAL") or 3600)
DAY = float(ENV.get("S3_LIFECYCLE_DAY_SECONDS") or 86400)
MAX_XML = 4 * 1024 * 1024
MAX_POST = 256 * 1024 * 1024
MAX_PARTS = 10000
SKEW = 15 * 60
SESSION_TTL = 12 * 3600
OWNER_ID = hashlib.sha256(("pskit-s3:" + ACCOUNT).encode()).hexdigest()
OWNER_NAME = "pskit"
NS = "http://s3.amazonaws.com/doc/2006-03-01/"
ALL_USERS = "http://acs.amazonaws.com/groups/global/AllUsers"
AUTH_USERS = "http://acs.amazonaws.com/groups/global/AuthenticatedUsers"
LOG_DELIVERY = "http://acs.amazonaws.com/groups/s3/LogDelivery"
STORAGE_CLASSES = (
    "STANDARD",
    "REDUCED_REDUNDANCY",
    "STANDARD_IA",
    "ONEZONE_IA",
    "INTELLIGENT_TIERING",
    "GLACIER",
    "DEEP_ARCHIVE",
    "GLACIER_IR",
    "OUTPOSTS",
    "SNOW",
    "EXPRESS_ONEZONE",
)
ARCHIVED = ("GLACIER", "DEEP_ARCHIVE")
CANNED = (
    "private",
    "public-read",
    "public-read-write",
    "authenticated-read",
    "aws-exec-read",
    "bucket-owner-read",
    "bucket-owner-full-control",
    "log-delivery-write",
)
STD_HEADERS = ("cache-control", "content-disposition", "content-encoding", "content-language", "expires")
ALGORITHMS = ("CRC32", "CRC32C", "CRC64NVME", "SHA1", "SHA256")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_IP = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
_AUTH4 = re.compile(r"^AWS4-HMAC-SHA256\s+Credential=([^,\s]+),\s*SignedHeaders=([^,\s]+),\s*Signature=([0-9a-f]{64})$")
# Bucket configurations kept as the XML the client sent: subresource -> (error when missing, delete allowed).
CONFIGS: Dict[str, Tuple[str, str]] = {
    "cors": ("NoSuchCORSConfiguration", "The CORS configuration does not exist"),
    "lifecycle": ("NoSuchLifecycleConfiguration", "The lifecycle configuration does not exist"),
    "website": ("NoSuchWebsiteConfiguration", "The specified bucket does not have a website configuration"),
    "encryption": (
        "ServerSideEncryptionConfigurationNotFoundError",
        "The server side encryption configuration was not found",
    ),
    "replication": ("ReplicationConfigurationNotFoundError", "The replication configuration was not found"),
    "ownershipControls": ("OwnershipControlsNotFoundError", "The bucket ownership controls were not found"),
    "publicAccessBlock": (
        "NoSuchPublicAccessBlockConfiguration",
        "The public access block configuration was not found",
    ),
    "object-lock": ("ObjectLockConfigurationNotFoundError", "Object Lock configuration does not exist for this bucket"),
    "logging": ("", ""),
    "notification": ("", ""),
    "accelerate": ("", ""),
    "requestPayment": ("", ""),
}
# Defaults returned by GET when a stored-only configuration was never set.
EMPTY_CONFIGS = {
    "logging": '<BucketLoggingStatus xmlns="%s"/>' % NS,
    "notification": '<NotificationConfiguration xmlns="%s"/>' % NS,
    "accelerate": '<AccelerateConfiguration xmlns="%s"/>' % NS,
    "requestPayment": '<RequestPaymentConfiguration xmlns="%s"><Payer>BucketOwner</Payer></RequestPaymentConfiguration>'
    % NS,
}
ID_CONFIGS = {
    "metrics": "MetricsConfiguration",
    "analytics": "AnalyticsConfiguration",
    "inventory": "InventoryConfiguration",
    "intelligent-tiering": "IntelligentTieringConfiguration",
}
BUCKET_SUBRESOURCES = (
    "acl",
    "cors",
    "delete",
    "encryption",
    "lifecycle",
    "location",
    "logging",
    "notification",
    "policy",
    "policyStatus",
    "replication",
    "requestPayment",
    "tagging",
    "uploads",
    "versioning",
    "versions",
    "website",
    "accelerate",
    "ownershipControls",
    "publicAccessBlock",
    "object-lock",
    "metrics",
    "analytics",
    "inventory",
    "intelligent-tiering",
)
OBJECT_SUBRESOURCES = (
    "acl",
    "tagging",
    "retention",
    "legal-hold",
    "attributes",
    "restore",
    "uploads",
    "uploadId",
    "select",
    "torrent",
)
V2_SUBRESOURCES = {
    "acl",
    "cors",
    "delete",
    "lifecycle",
    "location",
    "logging",
    "notification",
    "partNumber",
    "policy",
    "requestPayment",
    "restore",
    "tagging",
    "torrent",
    "uploadId",
    "uploads",
    "versionId",
    "versioning",
    "versions",
    "website",
    "response-cache-control",
    "response-content-disposition",
    "response-content-encoding",
    "response-content-language",
    "response-content-type",
    "response-expires",
    "retention",
    "legal-hold",
    "object-lock",
    "encryption",
    "accelerate",
    "publicAccessBlock",
    "ownershipControls",
    "replication",
    "attributes",
    "policyStatus",
}


def _credentials() -> Dict[str, str]:
    out: Dict[str, str] = {}
    if ENV.get("S3_SECRET_ACCESS_KEY"):
        out[ENV.get("S3_ACCESS_KEY_ID") or "pskit"] = ENV["S3_SECRET_ACCESS_KEY"]
    for pair in (ENV.get("S3_CREDENTIALS") or "").split(","):
        key, sep, secret = pair.strip().partition(":")
        if sep and key and secret:
            out[key] = secret
    return out


CREDENTIALS = _credentials()


def log(*parts: Any) -> None:
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"), *parts, flush=True)


class S3Error(Exception):
    def __init__(self, code: str, message: str, status: int = 400, **extra: str) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra
        self.headers: Dict[str, str] = {}


def _no_bucket(name: str) -> S3Error:
    return S3Error("NoSuchBucket", "The specified bucket does not exist", 404, BucketName=name)


def _no_key(key: str) -> S3Error:
    return S3Error("NoSuchKey", "The specified key does not exist.", 404, Key=key)


def _invalid(message: str, name: str = "", value: str = "") -> S3Error:
    extra = {"ArgumentName": name, "ArgumentValue": value} if name else {}
    return S3Error("InvalidArgument", message, 400, **extra)


def _malformed() -> S3Error:
    return S3Error(
        "MalformedXML", "The XML you provided was not well-formed or did not validate against our published schema"
    )


def _denied(message: str = "Access Denied") -> S3Error:
    return S3Error("AccessDenied", message, 403)


# ----------------------------------------------------------------------------- formats


def _now() -> float:
    return round(time.time(), 3)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % int(
        round(ts * 1000) % 1000
    )


def http_date(ts: float) -> str:
    return email.utils.formatdate(int(ts), usegmt=True)


def parse_time(text: str) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return email.utils.parsedate_to_datetime(text).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        cleaned = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        pass
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def esc(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\r", "&#13;")
    )


def x(tag: str, value: Any) -> str:
    return f"<{tag}>{esc(value)}</{tag}>"


def doc(root: str, inner: str) -> bytes:
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<{root} xmlns="{NS}">{inner}</{root}>'.encode("utf-8")


def parse_xml(body: bytes) -> ET.Element:
    if not body.strip():
        raise _malformed()
    if b"<!DOCTYPE" in body or b"<!ENTITY" in body:
        raise _malformed()
    try:
        root = ET.fromstring(body)  # noqa: S314 - DOCTYPE/ENTITY refused above, size-limited
    except ET.ParseError:
        raise _malformed() from None
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def text(el: Optional[ET.Element], path: str, default: str = "") -> str:
    if el is None:
        return default
    found = el.find(path)
    return (found.text or "").strip() if found is not None and found.text is not None else default


def strip_decl(xml_text: str) -> str:
    return re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", xml_text)


def url_enc(value: str, enabled: bool) -> str:
    return quote(value, safe="/") if enabled else value


def owner_xml() -> str:
    return "<Owner>" + x("ID", OWNER_ID) + x("DisplayName", OWNER_NAME) + "</Owner>"


# ----------------------------------------------------------------------------- checksums


def _crc_table(poly: int) -> List[int]:
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ poly if c & 1 else c >> 1
        table.append(c)
    return table


_CRC32C = _crc_table(0x82F63B78)
_CRC64 = _crc_table(0x9A6C9329AC4BC9B5)


class _Crc:
    def __init__(self, table: List[int], mask: int, size: int) -> None:
        self.table, self.mask, self.size, self.value = table, mask, size, mask

    def update(self, data: bytes) -> None:
        t, c = self.table, self.value
        for b in data:
            c = t[(c ^ b) & 0xFF] ^ (c >> 8)
        self.value = c

    def digest(self) -> bytes:
        return (self.value ^ self.mask).to_bytes(self.size, "big")


class _Crc32:
    def __init__(self) -> None:
        self.value = 0

    def update(self, data: bytes) -> None:
        self.value = binascii.crc32(data, self.value)

    def digest(self) -> bytes:
        return (self.value & 0xFFFFFFFF).to_bytes(4, "big")


def new_checksum(alg: str) -> Any:
    if alg == "CRC32":
        return _Crc32()
    if alg == "CRC32C":
        return _Crc(_CRC32C, 0xFFFFFFFF, 4)
    if alg == "CRC64NVME":
        return _Crc(_CRC64, 0xFFFFFFFFFFFFFFFF, 8)
    if alg == "SHA1":
        return hashlib.sha1()  # noqa: S324 - the S3 checksum algorithm, not a security use
    if alg == "SHA256":
        return hashlib.sha256()
    raise _invalid(f"Checksum algorithm {alg} is not supported.", "x-amz-checksum-algorithm", alg)


def checksum_of(alg: str, data: bytes) -> str:
    h = new_checksum(alg)
    h.update(data)
    return base64.b64encode(h.digest()).decode()


def checksum_header(alg: str) -> str:
    return "x-amz-checksum-" + alg.lower()


def checksum_element(alg: str) -> str:
    return "Checksum" + alg


# ----------------------------------------------------------------------------- store


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex[:8] + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    os.replace(str(tmp), str(path))


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass  # open on Windows, or gone: the startup sweep removes blobs nothing refers to


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class Bucket:
    def __init__(self, path: Path, meta: Dict[str, Any]) -> None:
        self.path = path
        self.meta = meta
        self.objects: Dict[str, Dict[str, Any]] = {}
        self.uploads: Dict[str, Dict[str, Any]] = {}
        self._sorted: Optional[List[str]] = None
        self.parsed: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return str(self.meta["name"])

    def keys(self) -> List[str]:
        if self._sorted is None:
            self._sorted = sorted(self.objects)
        return self._sorted

    def record_path(self, key: str) -> Path:
        h = key_hash(key)
        return self.path / "objects" / h[:2] / (h + ".json")

    def blob_path(self, blob: str) -> Path:
        return self.path / "blobs" / blob[:2] / blob

    def upload_dir(self, upload_id: str) -> Path:
        return self.path / "uploads" / upload_id

    def save_meta(self) -> None:
        self.parsed.clear()
        _write_json(self.path / "bucket.json", self.meta)

    def save_record(self, key: str) -> None:
        rec = self.objects.get(key)
        path = self.record_path(key)
        if rec is None or not rec["versions"]:
            self.objects.pop(key, None)
            _unlink(path)
            self._sorted = None
            return
        if self._sorted is not None and key not in self.objects:
            self._sorted = None
        _write_json(path, rec)

    def set_record(self, key: str, rec: Dict[str, Any]) -> None:
        if key not in self.objects:
            self._sorted = None
        self.objects[key] = rec
        self.save_record(key)


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.RLock()
        self.buckets: Dict[str, Bucket] = {}
        self.tmp = root / "tmp"
        (root / "buckets").mkdir(parents=True, exist_ok=True)
        if self.tmp.is_dir():
            shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        for meta_file in sorted((root / "buckets").glob("*/bucket.json")):
            try:
                meta = json.loads(meta_file.read_text("utf-8"))
            except (OSError, ValueError):
                log("skipping unreadable", meta_file)
                continue
            bucket = Bucket(meta_file.parent, meta)
            self._load(bucket)
            self.buckets[bucket.name] = bucket

    def _load(self, bucket: Bucket) -> None:
        used = set()
        for rec_file in (bucket.path / "objects").glob("*/*.json"):
            try:
                rec = json.loads(rec_file.read_text("utf-8"))
            except (OSError, ValueError):
                log("skipping unreadable", rec_file)
                continue
            if rec.get("versions"):
                bucket.objects[rec["key"]] = rec
                used.update(v["blob"] for v in rec["versions"] if v.get("blob"))
        for up_file in (bucket.path / "uploads").glob("*/upload.json"):
            try:
                up = json.loads(up_file.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            up["parts"] = {}
            for part_file in up_file.parent.glob("*.json"):
                if part_file.name == "upload.json":
                    continue
                try:
                    part = json.loads(part_file.read_text("utf-8"))
                except (OSError, ValueError):
                    continue
                if (up_file.parent / ("%05d.part" % part["n"])).is_file():
                    up["parts"][part["n"]] = part
            bucket.uploads[up["id"]] = up
        for blob in (bucket.path / "blobs").glob("*/*"):
            if blob.name not in used:
                _unlink(blob)

    def get(self, name: str) -> Bucket:
        bucket = self.buckets.get(name)
        if bucket is None:
            raise _no_bucket(name)
        return bucket

    def temp_file(self) -> Path:
        return self.tmp / uuid.uuid4().hex

    def commit_blob(self, bucket: Bucket, tmp: Path) -> str:
        blob = uuid.uuid4().hex
        dest = bucket.blob_path(blob)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(tmp), str(dest))
        return blob


STORE: Store

# ----------------------------------------------------------------------------- request bodies


class Raw:
    """The request body as sent: ``Content-Length`` bytes, or HTTP chunked transfer coding."""

    def __init__(self, rfile: Any, length: Optional[int], chunked: bool) -> None:
        self.rfile, self.left, self.chunked = rfile, length or 0, chunked
        self.chunk_left = 0
        self.done = not chunked and not length
        self.buf = b""

    def _fill(self) -> bytes:
        if self.done:
            return b""
        if not self.chunked:
            data = self.rfile.read(min(65536, self.left))
            if not data:
                raise S3Error(
                    "IncompleteBody",
                    "You did not provide the number of bytes specified by the Content-Length HTTP header",
                )
            self.left -= len(data)
            self.done = self.left <= 0
            return data
        if self.chunk_left == 0:
            line = self.rfile.readline(1024)
            size = int(line.split(b";")[0].strip() or b"0", 16)
            if size == 0:
                while self.rfile.readline(8192) not in (b"\r\n", b"\n", b""):
                    pass
                self.done = True
                return b""
            self.chunk_left = size
        data = self.rfile.read(min(65536, self.chunk_left))
        if not data:
            raise S3Error("IncompleteBody", "The request body ended early.")
        self.chunk_left -= len(data)
        if self.chunk_left == 0:
            self.rfile.readline(16)
        return data

    def read(self, n: int) -> bytes:
        while len(self.buf) < n and not self.done:
            self.buf += self._fill()
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def readline(self, limit: int = 8192) -> bytes:
        while b"\n" not in self.buf and not self.done and len(self.buf) < limit:
            self.buf += self._fill()
        idx = self.buf.find(b"\n")
        end = idx + 1 if idx >= 0 else len(self.buf)
        out, self.buf = self.buf[:end], self.buf[end:]
        return out

    def chunks(self) -> Iterator[bytes]:
        if self.buf:
            data, self.buf = self.buf, b""
            yield data
        while not self.done:
            data = self._fill()
            if data:
                yield data

    def drain(self) -> None:
        for _ in self.chunks():
            pass


class Auth:
    def __init__(self, principal: Optional[str], mode: str = "anonymous") -> None:
        self.principal = principal
        self.mode = mode
        self.payload = ""  # x-amz-content-sha256 as signed
        self.key = b""  # the signing key, for streaming chunk signatures
        self.signature = ""
        self.amz_date = ""
        self.scope = ""


def _chunk_signature(auth: Auth, prev: str, kind: str, data_hash: str) -> str:
    empty = hashlib.sha256(b"").hexdigest()
    if kind == "trailer":
        to_sign = "\n".join(["AWS4-HMAC-SHA256-TRAILER", auth.amz_date, auth.scope, prev, data_hash])
    else:
        to_sign = "\n".join(["AWS4-HMAC-SHA256-PAYLOAD", auth.amz_date, auth.scope, prev, empty, data_hash])
    return hmac.new(auth.key, to_sign.encode(), hashlib.sha256).hexdigest()


def payload_chunks(raw: Raw, headers: Dict[str, str], auth: Auth, trailers: Dict[str, str]) -> Iterator[bytes]:
    """The decoded payload: plain, or ``aws-chunked`` with chunk signatures and trailing checksums."""
    mode = auth.payload or headers.get("x-amz-content-sha256", "")
    if not mode.startswith("STREAMING-"):
        yield from raw.chunks()
        return
    if mode not in (
        "STREAMING-AWS4-HMAC-SHA256-PAYLOAD",
        "STREAMING-AWS4-HMAC-SHA256-PAYLOAD-TRAILER",
        "STREAMING-UNSIGNED-PAYLOAD-TRAILER",
    ):
        raise S3Error("NotImplemented", f"x-amz-content-sha256 {mode} is not supported.", 501)
    signed = mode.startswith("STREAMING-AWS4-HMAC") and auth.key
    prev = auth.signature
    while True:
        line = raw.readline(4096).strip().decode("latin-1")
        if not line:
            raise S3Error("IncompleteBody", "The aws-chunked body ended early.")
        size_text, _sep, ext = line.partition(";")
        try:
            size = int(size_text, 16)
        except ValueError:
            raise S3Error("InvalidRequest", "The aws-chunked body is not valid.") from None
        data = raw.read(size) if size else b""
        if len(data) != size:
            raise S3Error("IncompleteBody", "The aws-chunked body ended early.")
        if signed:
            claimed = ext.partition("chunk-signature=")[2].strip()
            expected = _chunk_signature(auth, prev, "chunk", hashlib.sha256(data).hexdigest())
            if not hmac.compare_digest(claimed, expected):
                raise S3Error("SignatureDoesNotMatch", "The chunk signature does not match.", 403)
            prev = expected
        if size:
            raw.read(2)
            yield data
            continue
        lines: List[str] = []
        while True:
            tl = raw.readline(8192)
            if tl in (b"\r\n", b"\n", b""):
                break
            lines.append(tl.decode("latin-1").rstrip("\r\n"))
        canonical = ""
        for tl_text in lines:
            name, _c, value = tl_text.partition(":")
            name = name.strip().lower()
            if name == "x-amz-trailer-signature":
                if signed:
                    expected = _chunk_signature(auth, prev, "trailer", hashlib.sha256(canonical.encode()).hexdigest())
                    if not hmac.compare_digest(value.strip(), expected):
                        raise S3Error("SignatureDoesNotMatch", "The trailer signature does not match.", 403)
            else:
                trailers[name] = value.strip()
                canonical += f"{name}:{value.strip()}\n"
        raw.drain()
        return


class Received:
    def __init__(self) -> None:
        self.path: Optional[Path] = None
        self.size = 0
        self.md5 = ""
        self.checksum: Dict[str, str] = {}  # alg -> base64


def wanted_checksum(headers: Dict[str, str]) -> Tuple[str, str]:
    """(algorithm, value the client sent or "" for a trailer / to compute) of a write."""
    for alg in ALGORITHMS:
        value = headers.get(checksum_header(alg))
        if value:
            return alg, value
    trailer = headers.get("x-amz-trailer", "").strip().lower()
    for alg in ALGORITHMS:
        if trailer == checksum_header(alg):
            return alg, ""
    alg = (headers.get("x-amz-sdk-checksum-algorithm") or headers.get("x-amz-checksum-algorithm") or "").upper()
    if alg:
        if alg not in ALGORITHMS:
            raise _invalid(f"Checksum algorithm {alg} is not supported.", "x-amz-checksum-algorithm", alg)
        return alg, ""
    return "", ""


def receive(
    raw: Raw, headers: Dict[str, str], auth: Auth, limit: int, alg: str = "", expected: str = "", to_file: bool = True
) -> Tuple[Received, bytes]:
    """Read the payload into a temporary file (or memory), checking its length, MD5, SHA-256 and checksum."""
    out = Received()
    md5 = hashlib.md5()  # noqa: S324 - the S3 ETag
    claimed = auth.payload or headers.get("x-amz-content-sha256", "")
    sha = hashlib.sha256() if re.fullmatch(r"[0-9a-f]{64}", claimed or "") else None
    hasher = new_checksum(alg) if alg else None
    trailers: Dict[str, str] = {}
    buf = bytearray()
    handle = None
    if to_file:
        out.path = STORE.temp_file()
        handle = open(out.path, "wb")  # noqa: SIM115 - closed below
    try:
        for data in payload_chunks(raw, headers, auth, trailers):
            out.size += len(data)
            if out.size > limit:
                raise S3Error(
                    "EntityTooLarge",
                    "Your proposed upload exceeds the maximum allowed size",
                    400,
                    MaxSizeAllowed=str(limit),
                )
            md5.update(data)
            if sha:
                sha.update(data)
            if hasher:
                hasher.update(data)
            if handle:
                handle.write(data)
            else:
                buf += data
    except BaseException:
        if handle:
            handle.close()
        if out.path:
            _unlink(out.path)
        raise
    if handle:
        handle.close()
    try:
        decoded = headers.get("x-amz-decoded-content-length")
        if decoded and claimed.startswith("STREAMING-") and int(decoded) != out.size:
            raise S3Error("IncompleteBody", "The decoded body is not x-amz-decoded-content-length bytes long.")
        if sha and sha.hexdigest() != claimed:
            raise S3Error(
                "XAmzContentSHA256Mismatch",
                "The provided 'x-amz-content-sha256' header does not match what was computed.",
                400,
                ClientComputedContentSHA256=claimed,
                S3ComputedContentSHA256=sha.hexdigest(),
            )
        out.md5 = md5.hexdigest()
        content_md5 = headers.get("content-md5")
        if content_md5:
            try:
                given = base64.b64decode(content_md5, validate=True)
            except (binascii.Error, ValueError):
                raise S3Error("InvalidDigest", "The Content-MD5 you specified was invalid.") from None
            if len(given) != 16:
                raise S3Error("InvalidDigest", "The Content-MD5 you specified was invalid.")
            if given != md5.digest():
                raise S3Error("BadDigest", "The Content-MD5 you specified did not match what we received.")
        if hasher:
            value = base64.b64encode(hasher.digest()).decode()
            sent = expected or trailers.get(checksum_header(alg), "")
            if sent and sent != value:
                raise S3Error("BadDigest", f"The {alg} you specified did not match the calculated checksum.")
            out.checksum = {alg: value}
    except BaseException:
        if out.path:
            _unlink(out.path)
        raise
    return out, bytes(buf)


# ----------------------------------------------------------------------------- signatures


def uri_encode(value: str, safe: str = "-_.~") -> str:
    return quote(value, safe=safe)


def split_query(raw_query: str) -> List[Tuple[str, str]]:
    pairs = []
    for part in raw_query.split("&"):
        if not part:
            continue
        name, _sep, value = part.partition("=")
        pairs.append((unquote(name), unquote(value)))
    return pairs


def _signing_key(secret: str, day: str, region: str, service: str) -> bytes:
    key = ("AWS4" + secret).encode("utf-8")
    for part in (day, region, service, "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    return key


def _canonical_query(pairs: List[Tuple[str, str]], skip: str = "") -> str:
    enc = sorted((uri_encode(k), uri_encode(v)) for k, v in pairs if k != skip)
    return "&".join(f"{k}={v}" for k, v in enc)


def _canonical_paths(raw_path: str) -> List[str]:
    normalized = uri_encode(unquote(raw_path), safe="/-_.~")
    return [raw_path] if normalized == raw_path else [raw_path, normalized]


def verify_v4(
    method: str, raw_path: str, pairs: List[Tuple[str, str]], headers: Dict[str, str], presigned: bool
) -> Auth:
    q = dict(pairs)
    if presigned:
        if q.get("X-Amz-Algorithm") != "AWS4-HMAC-SHA256":
            raise S3Error("AuthorizationQueryParametersError", 'X-Amz-Algorithm only supports "AWS4-HMAC-SHA256"')
        credential, signed_headers = q.get("X-Amz-Credential", ""), q.get("X-Amz-SignedHeaders", "")
        signature, amz_date = q.get("X-Amz-Signature", ""), q.get("X-Amz-Date", "")
    else:
        match = _AUTH4.match(headers.get("authorization", "").strip())
        if not match:
            raise S3Error("AuthorizationHeaderMalformed", "The authorization header is malformed.")
        credential, signed_headers, signature = match.groups()
        amz_date = headers.get("x-amz-date", "")
    parts = credential.split("/")
    if len(parts) != 5 or parts[4] != "aws4_request":
        raise S3Error("AuthorizationHeaderMalformed", "The Credential is not valid.")
    access_key, day, region, service, _t = parts
    secret = CREDENTIALS.get(access_key)
    if secret is None:
        raise S3Error(
            "InvalidAccessKeyId",
            "The AWS Access Key Id you provided does not exist in our records.",
            403,
            AWSAccessKeyId=access_key,
        )
    when = parse_time(amz_date)
    if when is None and not presigned and headers.get("date"):
        when = parse_time(headers["date"])
        amz_date = datetime.fromtimestamp(when or 0, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if when is None:
        raise S3Error("AccessDenied", "AWS authentication requires a valid Date or x-amz-date header", 403)
    now = time.time()
    if presigned:
        try:
            expires = int(q.get("X-Amz-Expires", ""))
        except ValueError:
            raise S3Error("AuthorizationQueryParametersError", "X-Amz-Expires must be a number.") from None
        if expires < 1 or expires > 604800:
            raise S3Error("AuthorizationQueryParametersError", "X-Amz-Expires must be between 1 and 604800 seconds.")
        if now > when + expires:
            raise S3Error("AccessDenied", "Request has expired", 403, Expires=iso(when + expires), ServerTime=iso(now))
        if when - now > SKEW:
            raise S3Error(
                "RequestTimeTooSkewed",
                "The difference between the request time and the current time is too large.",
                403,
            )
    elif abs(now - when) > SKEW:
        raise S3Error(
            "RequestTimeTooSkewed",
            "The difference between the request time and the current time is too large.",
            403,
            RequestTime=amz_date,
            ServerTime=iso(now),
        )
    if day != amz_date[:8] or service not in ("s3", "s3-object-lambda"):
        raise S3Error("SignatureDoesNotMatch", "The credential scope does not match the request.", 403)
    names = signed_headers.lower().split(";")
    if "host" not in names or any(n not in headers for n in names):
        raise S3Error("SignatureDoesNotMatch", "SignedHeaders must include host and only headers that were sent.", 403)
    if presigned:
        payload = headers.get("x-amz-content-sha256") or q.get("X-Amz-Content-Sha256") or "UNSIGNED-PAYLOAD"
    else:
        payload = headers.get("x-amz-content-sha256", "")
        if not payload:
            raise S3Error("InvalidRequest", "Missing required header for this request: x-amz-content-sha256")
    canonical_headers = "".join(f"{n}:{' '.join(headers[n].strip().split())}\n" for n in names)
    query = _canonical_query(pairs, "X-Amz-Signature" if presigned else "")
    scope = f"{day}/{region}/{service}/aws4_request"
    key = _signing_key(secret, day, region, service)
    for path in _canonical_paths(raw_path):
        canonical = "\n".join([method, path, query, canonical_headers, signed_headers.lower(), payload])
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        if hmac.compare_digest(hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest(), signature):
            auth = Auth(access_key, "sigv4")
            auth.payload, auth.key, auth.signature, auth.amz_date, auth.scope = payload, key, signature, amz_date, scope
            return auth
    raise S3Error(
        "SignatureDoesNotMatch",
        "The request signature we calculated does not match the signature you "
        "provided. Check your key and signing method.",
        403,
        AWSAccessKeyId=access_key,
    )


def verify_v2(
    method: str, raw_path: str, raw_query: str, headers: Dict[str, str], bucket_vhost: str, presigned: bool
) -> Auth:
    q = dict(split_query(raw_query))
    if presigned:
        access_key, signature, date = q.get("AWSAccessKeyId", ""), q.get("Signature", ""), q.get("Expires", "")
        try:
            if time.time() > int(date):
                raise S3Error("AccessDenied", "Request has expired", 403)
        except ValueError:
            raise S3Error("AccessDenied", "Expires is not valid.", 403) from None
    else:
        value = headers.get("authorization", "")[4:]
        access_key, _sep, signature = value.rpartition(":")
        date = "" if "x-amz-date" in headers else headers.get("date", "")
        when = parse_time(headers.get("x-amz-date") or headers.get("date", ""))
        if when is None or abs(time.time() - when) > SKEW:
            raise S3Error(
                "RequestTimeTooSkewed",
                "The difference between the request time and the current time is too large.",
                403,
            )
    secret = CREDENTIALS.get(access_key)
    if secret is None:
        raise S3Error("InvalidAccessKeyId", "The AWS Access Key Id you provided does not exist in our records.", 403)
    amz = sorted((k, " ".join(v.strip().split())) for k, v in headers.items() if k.startswith("x-amz-"))
    path = ("/" + bucket_vhost if bucket_vhost else "") + raw_path
    subs = sorted(p for p in raw_query.split("&") if p and unquote(p.partition("=")[0]) in V2_SUBRESOURCES)
    query = ""
    if subs:
        query = "?" + "&".join(
            unquote(s) if "=" not in s else s.partition("=")[0] + "=" + unquote(s.partition("=")[2]) for s in subs
        )
    head = "\n".join([method, headers.get("content-md5", ""), headers.get("content-type", ""), date]) + "\n"
    head += "".join(f"{k}:{v}\n" for k, v in amz)
    # A bucket's resource is signed as /bucket or /bucket/ depending on the client.
    paths = [path] + ([path + "/"] if path.count("/") == 1 else [path.rstrip("/")] if path.endswith("/") else [])
    to_sign = head + path + query
    for candidate in paths:
        attempt = head + candidate + query
        digest = hmac.new(secret.encode(), attempt.encode("utf-8"), hashlib.sha1).digest()
        if hmac.compare_digest(base64.b64encode(digest).decode(), signature):
            break
    else:
        raise S3Error(
            "SignatureDoesNotMatch",
            "The request signature we calculated does not match the signature you provided.",
            403,
            AWSAccessKeyId=access_key,
            StringToSign=to_sign,
        )
    auth = Auth(access_key, "sigv2")
    auth.payload = "UNSIGNED-PAYLOAD"
    return auth


# ----------------------------------------------------------------------------- access control


def acl_from_canned(canned: str) -> List[Dict[str, str]]:
    grants = [{"type": "CanonicalUser", "id": OWNER_ID, "permission": "FULL_CONTROL"}]
    if canned in ("public-read", "public-read-write"):
        grants.append({"type": "Group", "uri": ALL_USERS, "permission": "READ"})
    if canned == "public-read-write":
        grants.append({"type": "Group", "uri": ALL_USERS, "permission": "WRITE"})
    if canned == "authenticated-read":
        grants.append({"type": "Group", "uri": AUTH_USERS, "permission": "READ"})
    if canned == "log-delivery-write":
        grants += [
            {"type": "Group", "uri": LOG_DELIVERY, "permission": "WRITE"},
            {"type": "Group", "uri": LOG_DELIVERY, "permission": "READ_ACP"},
        ]
    return grants


def acl_grants(acl: Any) -> List[Dict[str, str]]:
    if isinstance(acl, dict) and isinstance(acl.get("grants"), list):
        return acl["grants"]
    canned = acl.get("canned", "private") if isinstance(acl, dict) else "private"
    return acl_from_canned(canned)


def acl_xml(acl: Any) -> bytes:
    inner = []
    for g in acl_grants(acl):
        if g["type"] == "Group":
            grantee = (
                f'<Grantee xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="Group">'
                f"{x('URI', g['uri'])}</Grantee>"
            )
        elif g["type"] == "AmazonCustomerByEmail":
            grantee = (
                f'<Grantee xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                f'xsi:type="AmazonCustomerByEmail">{x("EmailAddress", g.get("email", ""))}</Grantee>'
            )
        else:
            name = OWNER_NAME if g.get("id") == OWNER_ID else g.get("name", "")
            grantee = (
                f'<Grantee xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="CanonicalUser">'
                f"{x('ID', g.get('id', ''))}{x('DisplayName', name) if name else ''}</Grantee>"
            )
        inner.append(f"<Grant>{grantee}{x('Permission', g['permission'])}</Grant>")
    return doc("AccessControlPolicy", owner_xml() + "<AccessControlList>" + "".join(inner) + "</AccessControlList>")


_GRANT_HEADERS = {
    "x-amz-grant-read": "READ",
    "x-amz-grant-write": "WRITE",
    "x-amz-grant-read-acp": "READ_ACP",
    "x-amz-grant-write-acp": "WRITE_ACP",
    "x-amz-grant-full-control": "FULL_CONTROL",
}


def acl_from_request(
    headers: Dict[str, str], body: bytes, default: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    canned = headers.get("x-amz-acl", "")
    grants: List[Dict[str, str]] = []
    for header, permission in _GRANT_HEADERS.items():
        for item in re.findall(r'(id|uri|emailAddress)\s*=\s*"?([^",]+)"?', headers.get(header, "")):
            kind, value = item
            if kind == "id":
                grants.append({"type": "CanonicalUser", "id": value, "permission": permission})
            elif kind == "uri":
                grants.append({"type": "Group", "uri": value, "permission": permission})
            else:
                grants.append({"type": "AmazonCustomerByEmail", "email": value, "permission": permission})
    if canned and grants:
        raise _invalid("Specifying both Canned ACLs and Header Grants is not allowed")
    if canned:
        if canned not in CANNED:
            raise _invalid(f"{canned} is not a canned ACL.", "x-amz-acl", canned)
        return {"canned": canned}
    if grants:
        return {"grants": grants}
    if body.strip():
        root = parse_xml(body)
        found = []
        for grant in root.iter("Grant"):
            grantee, permission = grant.find("Grantee"), text(grant, "Permission")
            if grantee is None or permission not in ("READ", "WRITE", "READ_ACP", "WRITE_ACP", "FULL_CONTROL"):
                raise _malformed()
            if text(grantee, "URI"):
                found.append({"type": "Group", "uri": text(grantee, "URI"), "permission": permission})
            elif text(grantee, "EmailAddress"):
                found.append(
                    {"type": "AmazonCustomerByEmail", "email": text(grantee, "EmailAddress"), "permission": permission}
                )
            else:
                found.append(
                    {
                        "type": "CanonicalUser",
                        "id": text(grantee, "ID"),
                        "name": text(grantee, "DisplayName"),
                        "permission": permission,
                    }
                )
        return {"grants": found}
    return default


def acl_public(acl: Any, permission: str) -> bool:
    return any(
        g["type"] == "Group"
        and g.get("uri") in (ALL_USERS, AUTH_USERS)
        and g["permission"] in (permission, "FULL_CONTROL")
        for g in acl_grants(acl)
    )


def acl_canned_name(acl: Any) -> str:
    if isinstance(acl, dict) and acl.get("canned"):
        return str(acl["canned"])
    return "custom" if isinstance(acl, dict) and acl.get("grants") else "private"


def bucket_owner_enforced(bucket: Bucket) -> bool:
    return "BucketOwnerEnforced" in (bucket.meta.get("configs") or {}).get("ownershipControls", "")


def public_block(bucket: Bucket) -> Dict[str, bool]:
    raw = (bucket.meta.get("configs") or {}).get("publicAccessBlock", "")
    out = {
        "BlockPublicAcls": False,
        "IgnorePublicAcls": False,
        "BlockPublicPolicy": False,
        "RestrictPublicBuckets": False,
    }
    if raw:
        try:
            root = parse_xml(raw.encode())
        except S3Error:
            return out
        for name in out:
            out[name] = text(root, name).lower() == "true"
    return out


def _wild(pattern: str, value: str) -> bool:
    regex = "^" + ".*".join(re.escape(p).replace(r"\?", ".") for p in pattern.split("*")) + "$"
    return re.match(regex, value, re.IGNORECASE if pattern.lower().startswith("s3:") else 0) is not None


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else [value] if value is not None else []


def policy_decision(bucket: Bucket, action: str, resource: str) -> str:
    """ "allow", "deny" or "" for an anonymous request under the bucket policy."""
    raw = bucket.meta.get("policy")
    if not raw:
        return ""
    try:
        policy = json.loads(raw)
    except ValueError:
        return ""
    decision = ""
    for st in _as_list(policy.get("Statement")):
        if not isinstance(st, dict) or st.get("Condition") or "NotPrincipal" in st:
            continue
        principal = st.get("Principal")
        if not (principal == "*" or (isinstance(principal, dict) and "*" in _as_list(principal.get("AWS")))):
            continue
        actions = _as_list(st.get("Action"))
        if not any(_wild(a, action) for a in actions if isinstance(a, str)):
            continue
        resources = _as_list(st.get("Resource"))
        if not any(_wild(r, resource) for r in resources if isinstance(r, str)):
            continue
        if st.get("Effect") == "Deny":
            return "deny"
        if st.get("Effect") == "Allow":
            decision = "allow"
    return decision


def policy_is_public(bucket: Bucket) -> bool:
    raw = bucket.meta.get("policy")
    if not raw:
        return False
    try:
        return _statements_public(json.loads(raw))
    except ValueError:
        return False


def _statements_public(policy: Dict[str, Any]) -> bool:
    for st in _as_list(policy.get("Statement")):
        if isinstance(st, dict) and st.get("Effect") == "Allow" and not st.get("Condition"):
            principal = st.get("Principal")
            if principal == "*" or (isinstance(principal, dict) and "*" in _as_list(principal.get("AWS"))):
                return True
    return False


def anonymous_allowed(bucket: Bucket, action: str, key: str = "", version: Optional[Dict[str, Any]] = None) -> bool:
    block = public_block(bucket)
    resource = f"arn:aws:s3:::{bucket.name}" + (f"/{key}" if key else "")
    if not block["RestrictPublicBuckets"]:
        decision = policy_decision(bucket, action, resource)
        if decision == "deny":
            return False
        if decision == "allow":
            return True
    if block["IgnorePublicAcls"] or bucket_owner_enforced(bucket):
        return False
    if action in ("s3:ListBucket", "s3:ListBucketVersions", "s3:ListBucketMultipartUploads"):
        return acl_public(bucket.meta.get("acl"), "READ")
    if action in ("s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"):
        return acl_public(bucket.meta.get("acl"), "WRITE")
    if action in ("s3:GetObject", "s3:GetObjectVersion") and version is not None:
        return acl_public(version.get("acl"), "READ")
    return False


# ----------------------------------------------------------------------------- CORS


def cors_rules(bucket: Bucket) -> List[Dict[str, List[str]]]:
    if "cors" in bucket.parsed:
        return bucket.parsed["cors"]
    rules: List[Dict[str, List[str]]] = []
    raw = (bucket.meta.get("configs") or {}).get("cors")
    if raw:
        try:
            root = parse_xml(raw.encode())
            for rule in root.iter("CORSRule"):
                rules.append(
                    {
                        "origins": [(e.text or "").strip() for e in rule.findall("AllowedOrigin")],
                        "methods": [(e.text or "").strip().upper() for e in rule.findall("AllowedMethod")],
                        "headers": [(e.text or "").strip().lower() for e in rule.findall("AllowedHeader")],
                        "expose": [(e.text or "").strip() for e in rule.findall("ExposeHeader")],
                        "max_age": [text(rule, "MaxAgeSeconds")] if text(rule, "MaxAgeSeconds") else [],
                    }
                )
        except S3Error:
            rules = []
    bucket.parsed["cors"] = rules
    return rules


def cors_match(bucket: Bucket, origin: str, method: str, req_headers: List[str]) -> Optional[Dict[str, str]]:
    for rule in cors_rules(bucket):
        if not any(_wild(o, origin) for o in rule["origins"]):
            continue
        if method not in rule["methods"]:
            continue
        if any(not any(_wild(a, h) for a in rule["headers"]) for h in req_headers if h):
            continue
        out = {
            "Access-Control-Allow-Origin": "*" if rule["origins"] == ["*"] else origin,
            "Access-Control-Allow-Methods": ", ".join(rule["methods"]),
            "Vary": "Origin, Access-Control-Request-Headers, Access-Control-Request-Method",
        }
        if origin != "*" and rule["origins"] != ["*"]:
            out["Access-Control-Allow-Credentials"] = "true"
        if rule["expose"]:
            out["Access-Control-Expose-Headers"] = ", ".join(rule["expose"])
        if rule["max_age"]:
            out["Access-Control-Max-Age"] = rule["max_age"][0]
        if req_headers:
            out["Access-Control-Allow-Headers"] = ", ".join(req_headers)
        return out
    return None


def validate_cors(body: bytes) -> None:
    root = parse_xml(body)
    if root.tag != "CORSConfiguration":
        raise _malformed()
    rules = root.findall("CORSRule")
    if not rules or len(rules) > 100:
        raise _malformed()
    for rule in rules:
        methods = [(e.text or "").strip() for e in rule.findall("AllowedMethod")]
        if not methods or not rule.findall("AllowedOrigin"):
            raise _malformed()
        for m in methods:
            if m not in ("GET", "PUT", "POST", "DELETE", "HEAD"):
                raise _invalid(
                    f"Found unsupported HTTP method in CORS config. Unsupported method is {m}",
                    "CORSRule/AllowedMethod",
                    m,
                )


# ----------------------------------------------------------------------------- lifecycle


def lifecycle_rules(bucket: Bucket) -> List[Dict[str, Any]]:
    if "lifecycle" in bucket.parsed:
        return bucket.parsed["lifecycle"]
    rules: List[Dict[str, Any]] = []
    raw = (bucket.meta.get("configs") or {}).get("lifecycle")
    if raw:
        try:
            rules = parse_lifecycle(raw.encode())
        except S3Error:
            rules = []
    bucket.parsed["lifecycle"] = rules
    return rules


def _num(value: str) -> Optional[int]:
    try:
        return int(value) if value else None
    except ValueError:
        raise _malformed() from None


def parse_lifecycle(body: bytes) -> List[Dict[str, Any]]:
    root = parse_xml(body)
    if root.tag != "LifecycleConfiguration":
        raise _malformed()
    rules = []
    for rule in root.findall("Rule"):
        status = text(rule, "Status")
        if status not in ("Enabled", "Disabled"):
            raise _malformed()
        flt = rule.find("Filter")
        prefix, tags, gt, lt = text(rule, "Prefix"), {}, None, None
        if flt is not None:
            scope = flt.find("And") if flt.find("And") is not None else flt
            prefix = text(scope, "Prefix", prefix)
            for tag in scope.findall("Tag"):
                tags[text(tag, "Key")] = text(tag, "Value")
            gt, lt = _num(text(scope, "ObjectSizeGreaterThan")), _num(text(scope, "ObjectSizeLessThan"))
        exp = rule.find("Expiration")
        nce = rule.find("NoncurrentVersionExpiration")
        abort = rule.find("AbortIncompleteMultipartUpload")
        transitions = []
        for tr in rule.findall("Transition"):
            transitions.append(
                {
                    "days": _num(text(tr, "Days")),
                    "date": parse_time(text(tr, "Date")),
                    "class": text(tr, "StorageClass"),
                }
            )
        nc_transitions = []
        for tr in rule.findall("NoncurrentVersionTransition"):
            nc_transitions.append({"days": _num(text(tr, "NoncurrentDays")), "class": text(tr, "StorageClass")})
        item = {
            "id": text(rule, "ID"),
            "enabled": status == "Enabled",
            "prefix": prefix,
            "tags": tags,
            "gt": gt,
            "lt": lt,
            "exp_days": _num(text(exp, "Days")),
            "exp_date": parse_time(text(exp, "Date")),
            "exp_marker": text(exp, "ExpiredObjectDeleteMarker").lower() == "true",
            "nc_days": _num(text(nce, "NoncurrentDays")),
            "nc_keep": _num(text(nce, "NewerNoncurrentVersions")),
            "abort_days": _num(text(abort, "DaysAfterInitiation")),
            "transitions": transitions,
            "nc_transitions": nc_transitions,
        }
        if item["exp_days"] is not None and item["exp_days"] < 1:
            raise _invalid("'Days' for Expiration action must be a positive integer")
        rules.append(item)
    if not rules or len(rules) > 1000:
        raise _malformed()
    return rules


def _rule_matches(rule: Dict[str, Any], key: str, version: Dict[str, Any]) -> bool:
    if not rule["enabled"] or not key.startswith(rule["prefix"]):
        return False
    tags = version.get("tags") or {}
    if any(tags.get(k) != v for k, v in rule["tags"].items()):
        return False
    size = int(version.get("size") or 0)
    if rule["gt"] is not None and not size > rule["gt"]:
        return False
    return not (rule["lt"] is not None and not size < rule["lt"])


def sweep_lifecycle(now: Optional[float] = None) -> int:
    """Apply every bucket's lifecycle rules once. Returns how many changes were made."""
    now = now or time.time()
    changes = 0
    with STORE.lock:
        for bucket in list(STORE.buckets.values()):
            rules = lifecycle_rules(bucket)
            if not rules:
                continue
            for key in list(bucket.keys()):
                rec = bucket.objects.get(key)
                if not rec:
                    continue
                changes += _sweep_key(bucket, key, rec, rules, now)
            for upload_id, up in list(bucket.uploads.items()):
                for rule in rules:
                    if (
                        rule["enabled"]
                        and rule["abort_days"] is not None
                        and up["key"].startswith(rule["prefix"])
                        and now - up["initiated"] >= rule["abort_days"] * DAY
                    ):
                        abort_upload(bucket, upload_id)
                        changes += 1
                        break
    if changes:
        log("lifecycle:", changes, "changes")
    return changes


def _sweep_key(bucket: Bucket, key: str, rec: Dict[str, Any], rules: List[Dict[str, Any]], now: float) -> int:
    changes = 0
    versions = rec["versions"]
    current = versions[0]
    for rule in rules:
        if not current.get("dm") and _rule_matches(rule, key, current):
            due = (rule["exp_days"] is not None and now - current["time"] >= rule["exp_days"] * DAY) or (
                rule["exp_date"] is not None and now >= rule["exp_date"]
            )
            if due and not _locked(current, now):
                delete_object(bucket, key, None, bypass=False)
                return 1
            for tr in rule["transitions"]:
                due = (tr["days"] is not None and now - current["time"] >= tr["days"] * DAY) or (
                    tr["date"] is not None and now >= tr["date"]
                )
                if due and tr["class"] and current.get("class", "STANDARD") != tr["class"]:
                    current["class"] = tr["class"]
                    bucket.save_record(key)
                    changes += 1
    noncurrent = versions[1:]
    for rule in rules:
        if not rule["enabled"] or not key.startswith(rule["prefix"]):
            continue
        if rule["nc_days"] is not None:
            kept = 0
            for version in list(noncurrent):
                if version.get("dm"):
                    continue
                if rule["nc_keep"] is not None and kept < rule["nc_keep"]:
                    kept += 1
                    continue
                # A version becomes noncurrent when the next newer one is written.
                since = versions[versions.index(version) - 1]["time"]
                if now - since >= rule["nc_days"] * DAY and not _locked(version, now):
                    _remove_version(bucket, key, version["id"])
                    changes += 1
        for tr in rule["nc_transitions"]:
            for version in versions[1:]:
                since = versions[versions.index(version) - 1]["time"]
                if (
                    not version.get("dm")
                    and tr["days"] is not None
                    and now - since >= tr["days"] * DAY
                    and tr["class"]
                    and version.get("class", "STANDARD") != tr["class"]
                ):
                    version["class"] = tr["class"]
                    bucket.save_record(key)
                    changes += 1
    rec = bucket.objects.get(key)
    if rec and len(rec["versions"]) == 1 and rec["versions"][0].get("dm"):
        if any(r["enabled"] and r["exp_marker"] and key.startswith(r["prefix"]) for r in rules):
            _remove_version(bucket, key, rec["versions"][0]["id"])
            changes += 1
    return changes


def lifecycle_loop() -> None:
    time.sleep(min(60.0, LIFECYCLE_INTERVAL))
    while True:
        try:
            sweep_lifecycle()
        except Exception as exc:  # noqa: BLE001 - keep sweeping
            log("lifecycle error:", repr(exc))
        time.sleep(LIFECYCLE_INTERVAL)


# ----------------------------------------------------------------------------- object lock


def lock_config(bucket: Bucket) -> Dict[str, Any]:
    raw = (bucket.meta.get("configs") or {}).get("object-lock", "")
    out: Dict[str, Any] = {"enabled": bool(bucket.meta.get("object_lock")), "mode": "", "days": 0, "years": 0}
    if raw:
        try:
            root = parse_xml(raw.encode())
        except S3Error:
            return out
        out["enabled"] = out["enabled"] or text(root, "ObjectLockEnabled") == "Enabled"
        out["mode"] = text(root, "Rule/DefaultRetention/Mode")
        out["days"] = int(text(root, "Rule/DefaultRetention/Days") or 0)
        out["years"] = int(text(root, "Rule/DefaultRetention/Years") or 0)
    return out


def _locked(version: Dict[str, Any], now: float, bypass: bool = False) -> bool:
    if version.get("hold"):
        return True
    retention = version.get("retention") or {}
    if retention.get("until") and retention["until"] > now:
        return not (retention.get("mode") == "GOVERNANCE" and bypass)
    return False


def check_unlocked(version: Dict[str, Any], bypass: bool) -> None:
    if version.get("hold"):
        raise _denied("Access Denied because object protected by object lock.")
    if _locked(version, time.time(), bypass):
        raise _denied("Access Denied because object protected by object lock.")


# ----------------------------------------------------------------------------- bucket and object operations


def _vid() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(24)).decode().replace("-", ".")


def create_bucket(
    name: str, region: str, acl: Optional[Dict[str, Any]], object_lock: bool, ownership: str = ""
) -> Bucket:
    if (
        not _BUCKET.match(name)
        or ".." in name
        or _IP.match(name)
        or name.startswith("xn--")
        or name.endswith("-s3alias")
        or name.endswith("--ol-s3")
    ):
        raise S3Error("InvalidBucketName", "The specified bucket is not valid.", 400, BucketName=name)
    with STORE.lock:
        if name in STORE.buckets:
            raise S3Error(
                "BucketAlreadyOwnedByYou",
                "Your previous request to create the named bucket succeeded and you already own it.",
                409,
                BucketName=name,
            )
        path = STORE.root / "buckets" / name
        meta: Dict[str, Any] = {
            "name": name,
            "created": _now(),
            "region": region,
            "versioning": "",
            "mfa_delete": "",
            "object_lock": object_lock,
            "acl": acl or {"canned": "private"},
            "tags": {},
            "policy": None,
            "configs": {},
            "ids": {},
        }
        if object_lock:
            meta["versioning"] = "Enabled"
            meta["configs"]["object-lock"] = (
                f'<ObjectLockConfiguration xmlns="{NS}"><ObjectLockEnabled>Enabled'
                "</ObjectLockEnabled></ObjectLockConfiguration>"
            )
        if ownership:
            meta["configs"]["ownershipControls"] = (
                f'<OwnershipControls xmlns="{NS}"><Rule><ObjectOwnership>'
                f"{esc(ownership)}</ObjectOwnership></Rule></OwnershipControls>"
            )
        bucket = Bucket(path, meta)
        bucket.save_meta()
        STORE.buckets[name] = bucket
        log("bucket created", name)
        return bucket


def delete_bucket(name: str) -> None:
    with STORE.lock:
        bucket = STORE.get(name)
        if bucket.objects:
            raise S3Error("BucketNotEmpty", "The bucket you tried to delete is not empty", 409, BucketName=name)
        for upload_id in list(bucket.uploads):
            abort_upload(bucket, upload_id)
        del STORE.buckets[name]
        shutil.rmtree(bucket.path, ignore_errors=True)
        log("bucket deleted", name)


def find_version(bucket: Bucket, key: str, version_id: Optional[str], *, allow_marker: bool = False) -> Dict[str, Any]:
    rec = bucket.objects.get(key)
    if version_id is not None:
        if version_id == "":
            raise _invalid("Version id cannot be the empty string", "versionId", "")
        for version in (rec or {}).get("versions", []):
            if version["id"] == version_id:
                if version.get("dm") and not allow_marker:
                    err = S3Error(
                        "MethodNotAllowed",
                        "The specified method is not allowed against this resource.",
                        405,
                        Method="GET",
                        ResourceType="DeleteMarker",
                    )
                    err.headers = {
                        "x-amz-delete-marker": "true",
                        "x-amz-version-id": version_id,
                        "Last-Modified": http_date(version["time"]),
                    }
                    raise err
                return version
        if rec is None and not re.fullmatch(r"[A-Za-z0-9._=-]+", version_id):
            raise _invalid("Invalid version id specified", "versionId", version_id)
        raise S3Error("NoSuchVersion", "The specified version does not exist.", 404, Key=key, VersionId=version_id)
    if not rec:
        raise _no_key(key)
    latest = rec["versions"][0]
    if latest.get("dm"):
        err = _no_key(key)
        err.headers = {"x-amz-delete-marker": "true", "x-amz-version-id": latest["id"]}
        raise err
    return latest


def _remove_version(bucket: Bucket, key: str, version_id: str) -> Optional[Dict[str, Any]]:
    rec = bucket.objects.get(key)
    if not rec:
        return None
    for idx, version in enumerate(rec["versions"]):
        if version["id"] == version_id:
            del rec["versions"][idx]
            bucket.save_record(key)
            if version.get("blob"):
                _unlink(bucket.blob_path(version["blob"]))
            return version
    return None


def put_version(bucket: Bucket, key: str, version: Dict[str, Any]) -> Dict[str, Any]:
    """Make ``version`` the newest version of ``key``, under the bucket's versioning state. Caller holds the lock."""
    rec = bucket.objects.get(key) or {"key": key, "versions": []}
    if bucket.meta.get("versioning") == "Enabled":
        version["id"] = _vid()
    else:
        version["id"] = "null"
        for old in [v for v in rec["versions"] if v["id"] == "null"]:
            rec["versions"].remove(old)
            if old.get("blob"):
                _unlink(bucket.blob_path(old["blob"]))
    rec["versions"].insert(0, version)
    bucket.set_record(key, rec)
    return version


def delete_object(bucket: Bucket, key: str, version_id: Optional[str], *, bypass: bool) -> Dict[str, Any]:
    """{"marker": bool, "id": version id or ""}. Caller holds the lock."""
    rec = bucket.objects.get(key)
    if version_id is not None:
        for version in (rec or {}).get("versions", []):
            if version["id"] == version_id:
                if not version.get("dm"):
                    check_unlocked(version, bypass)
                _remove_version(bucket, key, version_id)
                return {"marker": bool(version.get("dm")), "id": version_id}
        return {"marker": False, "id": version_id}
    state = bucket.meta.get("versioning")
    if not state:
        if rec:
            for version in list(rec["versions"]):
                _remove_version(bucket, key, version["id"])
        return {"marker": False, "id": ""}
    marker = {"dm": True, "time": _now(), "owner": OWNER_ID}
    put_version(bucket, key, marker)
    return {"marker": True, "id": marker["id"]}


def abort_upload(bucket: Bucket, upload_id: str) -> None:
    bucket.uploads.pop(upload_id, None)
    shutil.rmtree(bucket.upload_dir(upload_id), ignore_errors=True)


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
            raise _denied()
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
            raise _invalid("x-amz-object-lock-mode and x-amz-object-lock-retain-until-date must both be supplied")
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
    version.update({"blob": blob, "size": received.size, "etag": received.md5, "time": _now()})
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
        raise _invalid(
            "Copy Source must mention the source bucket and key: sourcebucket/sourcekey", "x-amz-copy-source", raw
        )
    version_id = None
    for k, v in split_query(query):
        if k == "versionId":
            version_id = v
    return src_bucket, src_key, version_id


def read_source(headers: Dict[str, str], who: Optional[str]) -> Tuple[Bucket, str, Dict[str, Any], Path]:
    src_bucket_name, src_key, src_vid = copy_source(headers)
    with STORE.lock:
        src_bucket = STORE.get(src_bucket_name)
        version = find_version(src_bucket, src_key, src_vid)
        if who is None and not anonymous_allowed(src_bucket, "s3:GetObject", src_key, version):
            raise _denied()
        if version.get("class") in ARCHIVED and not version.get("restore"):
            raise S3Error(
                "InvalidObjectState",
                "The operation is not valid for the object's storage class",
                403,
                StorageClass=version["class"],
            )
        check_conditions(version, headers, "x-amz-copy-source-")
        return src_bucket, src_key, dict(version), src_bucket.blob_path(version["blob"])


def copy_file(src: Path, start: int, end: int, alg: str) -> Received:
    out = Received()
    out.path = STORE.temp_file()
    md5 = hashlib.md5()  # noqa: S324 - the S3 ETag
    hasher = new_checksum(alg) if alg else None
    with open(src, "rb") as fin, open(out.path, "wb") as fout:
        fin.seek(start)
        left = end - start + 1
        while left > 0:
            data = fin.read(min(1024 * 1024, left))
            if not data:
                break
            left -= len(data)
            md5.update(data)
            if hasher:
                hasher.update(data)
            fout.write(data)
            out.size += len(data)
    out.md5 = md5.hexdigest()
    if hasher:
        out.checksum = {alg: base64.b64encode(hasher.digest()).decode()}
    return out


# ----------------------------------------------------------------------------- listing


def list_keys(
    bucket: Bucket, prefix: str, delimiter: str, after: str, max_keys: int, include: Callable[[str], bool]
) -> Tuple[List[str], List[str], bool, str]:
    keys = bucket.keys()
    i = bisect.bisect_left(keys, prefix)
    if after:
        i = max(i, bisect.bisect_right(keys, after))
        if delimiter and after.endswith(delimiter):
            while i < len(keys) and keys[i].startswith(after):
                i += 1
    contents: List[str] = []
    prefixes: List[str] = []
    last = ""
    count = 0
    truncated = False
    while i < len(keys):
        key = keys[i]
        if not key.startswith(prefix):
            break
        if not include(key):
            i += 1
            continue
        if delimiter:
            pos = key.find(delimiter, len(prefix))
            if pos >= 0:
                common = key[: pos + len(delimiter)]
                if count >= max_keys:
                    truncated = True
                    break
                prefixes.append(common)
                last = common
                count += 1
                while i < len(keys) and keys[i].startswith(common):
                    i += 1
                continue
        if count >= max_keys:
            truncated = True
            break
        contents.append(key)
        last = key
        count += 1
        i += 1
    return contents, prefixes, truncated, last


def _max_keys(q: Dict[str, str], name: str = "max-keys", default: int = 1000) -> int:
    try:
        value = int(q.get(name, default))
    except ValueError:
        raise _invalid("Provided max-keys not an integer or within integer range", name, q.get(name, "")) from None
    if value < 0:
        raise _invalid("Argument maxKeys must be an integer between 0 and 2147483647", name, str(value))
    return min(value, 1000)


def _token_encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode()


def _token_decode(value: str) -> str:
    try:
        return base64.urlsafe_b64decode(value.encode() + b"=" * (-len(value) % 4)).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise _invalid("The continuation token provided is incorrect", "continuation-token", value) from None


def contents_xml(bucket: Bucket, key: str, version: Dict[str, Any], enc: bool, owner: bool) -> str:
    out = (
        f"<Contents>{x('Key', url_enc(key, enc))}{x('LastModified', iso(version['time']))}"
        f"{x('ETag', chr(34) + version['etag'] + chr(34))}{x('Size', version['size'])}"
        f"{x('StorageClass', version.get('class', 'STANDARD'))}"
    )
    if version.get("checksum"):
        out += x("ChecksumAlgorithm", version["checksum"]["alg"]) + x(
            "ChecksumType", version["checksum"].get("type", "FULL_OBJECT")
        )
    if owner:
        out += owner_xml()
    if version.get("class") in ARCHIVED and version.get("restore"):
        expiry = x("RestoreExpiryDate", iso(version["restore"]))
        out += f"<RestoreStatus><IsRestoreInProgress>false</IsRestoreInProgress>{expiry}</RestoreStatus>"
    return out + "</Contents>"


def visible(bucket: Bucket) -> Callable[[str], bool]:
    return lambda k: bool(bucket.objects.get(k)) and not bucket.objects[k]["versions"][0].get("dm")


# ----------------------------------------------------------------------------- web console sessions
SESSIONS: Dict[str, Dict[str, Any]] = {}
FAILURES: Dict[str, List[float]] = {}
_session_lock = threading.Lock()


def _check_login(user: str, password: str) -> bool:
    if UI_PASSWORD:
        return hmac.compare_digest(password.encode("utf-8"), UI_PASSWORD.encode("utf-8"))
    secret = CREDENTIALS.get(user)
    return hmac.compare_digest(password.encode("utf-8"), (secret or "\0" * 32).encode("utf-8")) and secret is not None


def _throttled(ip: str) -> bool:
    now = time.time()
    with _session_lock:
        recent = [t for t in FAILURES.get(ip, []) if now - t < 300]
        FAILURES[ip] = recent
        return len(recent) >= 10


def _failed(ip: str) -> None:
    with _session_lock:
        FAILURES.setdefault(ip, []).append(time.time())


def _new_session(user: str) -> Tuple[str, str]:
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    with _session_lock:
        now = time.time()
        for key in [k for k, s in SESSIONS.items() if s["expires"] < now]:
            del SESSIONS[key]
        SESSIONS[sid] = {"user": user, "csrf": csrf, "expires": now + SESSION_TTL}
    return sid, csrf


def _session(cookie_header: str) -> Optional[Dict[str, Any]]:
    for part in cookie_header.split(";"):
        name, _sep, value = part.strip().partition("=")
        if name == "s3_session":
            with _session_lock:
                found = SESSIONS.get(value)
                if found and found["expires"] > time.time():
                    return {**found, "id": value}
    return None


def _ui_html() -> bytes:
    here = Path(__file__).resolve().parent
    for candidate in ([Path(UI_FILE)] if UI_FILE else []) + [here / "index.html", here.parent / "ui" / "index.html"]:
        if candidate.is_file():
            return candidate.read_bytes()
    return b"<!doctype html><title>S3 console</title><p>The console page (index.html) is missing."


UI_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
    "frame-src 'self' blob:; frame-ancestors 'none'; form-action 'self'",
}


def presign(
    method: str,
    host: str,
    bucket: str,
    key: str,
    expires: int,
    access_key: str,
    version_id: str = "",
    scheme: str = "http",
) -> str:
    secret = CREDENTIALS.get(access_key) or ""
    now = datetime.now(timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    path = "/" + uri_encode(bucket) + "/" + uri_encode(key, safe="/-_.~")
    pairs = [
        ("X-Amz-Algorithm", "AWS4-HMAC-SHA256"),
        ("X-Amz-Credential", f"{access_key}/{day}/{REGION}/s3/aws4_request"),
        ("X-Amz-Date", amz_date),
        ("X-Amz-Expires", str(expires)),
        ("X-Amz-SignedHeaders", "host"),
    ]
    if version_id:
        pairs.append(("versionId", version_id))
    query = _canonical_query(pairs)
    canonical = "\n".join([method, path, query, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"])
    scope = f"{day}/{REGION}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    signature = hmac.new(_signing_key(secret, day, REGION, "s3"), to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{scheme}://{host}{path}?{query}&X-Amz-Signature={signature}"


# ----------------------------------------------------------------------------- HTTP


class Request:
    def __init__(self, handler: "Handler") -> None:
        self.handler = handler
        self.method = handler.command
        split = urlsplit(handler.path)
        self.raw_path = split.path or "/"
        self.raw_query = split.query
        self.pairs = split_query(split.query)
        self.q = {k: v for k, v in self.pairs}
        self.headers = handler.lower_headers()
        self.host = self.headers.get("host", "")
        self.bucket = ""
        self.key = ""
        self.vhost = ""
        self.auth = Auth(None)
        length = self.headers.get("content-length")
        chunked = "chunked" in self.headers.get("transfer-encoding", "").lower()
        try:
            n = int(length) if length else 0
        except ValueError:
            raise S3Error("InvalidArgument", "Content-Length is not valid.") from None
        self.raw = Raw(handler.rfile, n, chunked)
        self.consumed = not n and not chunked

    @property
    def who(self) -> Optional[str]:
        return self.auth.principal

    def small_body(self, limit: int = MAX_XML) -> bytes:
        self.consumed = True
        received, data = receive(self.raw, self.headers, self.auth, limit, to_file=False)
        return data

    def payload(self, alg: str, expected: str, limit: int = MAX_OBJECT) -> Received:
        self.consumed = True
        received, _data = receive(self.raw, self.headers, self.auth, limit, alg, expected)
        return received


class Response:
    def __init__(
        self,
        status: int = 200,
        body: bytes = b"",
        headers: Optional[Dict[str, str]] = None,
        ctype: str = "application/xml",
        file: Optional[Path] = None,
        start: int = 0,
        length: int = 0,
    ) -> None:
        self.status, self.body, self.headers, self.ctype = status, body, dict(headers or {}), ctype
        self.file, self.start, self.length = file, start, length


def xml_response(root: str, inner: str, status: int = 200, headers: Optional[Dict[str, str]] = None) -> Response:
    return Response(status, doc(root, inner), headers)


class Handler(BaseHTTPRequestHandler):
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
            bucket = STORE.buckets.get(req.bucket)
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
    if req.raw_path in ("/-/health", "/-/healthz") or (
        req.raw_path in ("/health", "/healthz") and "authorization" not in req.headers and not req.q
    ):
        return Response(
            200,
            json.dumps({"status": "ok", "buckets": len(STORE.buckets), "version": VERSION}).encode(),
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
        raise _denied()
    if not req.bucket:
        if req.method == "GET":
            return list_buckets(req)
        raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)
    if len(req.key.encode("utf-8")) > 1024:
        raise S3Error("KeyTooLongError", "Your key is too long", 400)
    if not req.key:
        return bucket_route(req)
    return object_route(req)


def authenticate(req: Request) -> None:
    if AUTH == "off":
        req.auth = Auth("anonymous", "off")
        if req.headers.get("x-amz-content-sha256", "").startswith("STREAMING-"):
            req.auth.payload = req.headers["x-amz-content-sha256"]
        return
    authorization = req.headers.get("authorization", "")
    method = req.method
    if authorization.startswith("AWS4-HMAC-SHA256"):
        req.auth = verify_v4(method, req.raw_path, req.pairs, req.headers, False)
    elif authorization.startswith("AWS "):
        req.auth = verify_v2(method, req.raw_path, req.raw_query, req.headers, req.vhost, False)
    elif "X-Amz-Signature" in req.q:
        req.auth = verify_v4(method, req.raw_path, req.pairs, req.headers, True)
    elif "Signature" in req.q and "AWSAccessKeyId" in req.q:
        req.auth = verify_v2(method, req.raw_path, req.raw_query, req.headers, req.vhost, True)
    elif authorization:
        raise S3Error("InvalidArgument", "Unsupported Authorization Type", 400)
    else:
        req.auth = Auth(None)


def need_auth(
    req: Request, bucket: Optional[Bucket], action: str, key: str = "", version: Optional[Dict[str, Any]] = None
) -> None:
    if req.who is not None:
        return
    if bucket is not None and anonymous_allowed(bucket, action, key, version):
        return
    raise _denied()


def preflight(req: Request) -> Response:
    origin = req.headers.get("origin", "")
    method = req.headers.get("access-control-request-method", "")
    if not origin or not method:
        raise S3Error("BadRequest", "Insufficient information. Origin request header needed.", 400)
    bucket = STORE.buckets.get(req.bucket)
    if bucket is None:
        raise _no_bucket(req.bucket)
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


# ----------------------------------------------------------------------------- service and bucket routes


def list_buckets(req: Request) -> Response:
    if req.who is None:
        raise _denied()
    prefix = req.q.get("prefix", "")
    region = req.q.get("bucket-region", "")
    limit = int(req.q.get("max-buckets") or 10000)
    after = _token_decode(req.q["continuation-token"]) if req.q.get("continuation-token") else ""
    with STORE.lock:
        names = [
            n
            for n in sorted(STORE.buckets)
            if n.startswith(prefix) and n > after and (not region or STORE.buckets[n].meta.get("region") == region)
        ]
        page, more = names[:limit], len(names) > limit
        items = "".join(
            f"<Bucket>{x('Name', n)}{x('CreationDate', iso(STORE.buckets[n].meta['created']))}"
            f"{x('BucketRegion', STORE.buckets[n].meta.get('region') or REGION)}</Bucket>"
            for n in page
        )
    inner = owner_xml() + f"<Buckets>{items}</Buckets>"
    if more:
        inner += x("ContinuationToken", _token_encode(page[-1]))
    if prefix:
        inner += x("Prefix", prefix)
    return xml_response("ListAllMyBucketsResult", inner)


def bucket_route(req: Request) -> Response:
    q, method = req.q, req.method
    sub = next((s for s in BUCKET_SUBRESOURCES if s in q), "")
    if method == "PUT" and not sub:
        return put_bucket(req)
    if method == "POST" and "delete" in q:
        return delete_objects(req)
    with STORE.lock:
        bucket = STORE.get(req.bucket)
    if method == "HEAD" and not sub:
        need_auth(req, bucket, "s3:ListBucket")
        return Response(
            200, b"", {"x-amz-bucket-region": bucket.meta.get("region") or REGION, "x-amz-access-point-alias": "false"}
        )
    if method == "DELETE" and not sub:
        need_auth(req, None, "")
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
    need_auth(req, None, "")
    return bucket_config(req, bucket, sub)


def put_bucket(req: Request) -> Response:
    if req.who is None:
        raise _denied()
    body = req.small_body()
    region = REGION
    if body.strip():
        root = parse_xml(body)
        region = text(root, "LocationConstraint") or REGION
    acl = acl_from_request(req.headers, b"")
    ownership = req.headers.get("x-amz-object-ownership", "")
    if ownership and ownership not in ("BucketOwnerPreferred", "ObjectWriter", "BucketOwnerEnforced"):
        raise _invalid("Invalid x-amz-object-ownership header", "x-amz-object-ownership", ownership)
    if ownership == "BucketOwnerEnforced" and acl and acl.get("canned") not in ("private", "bucket-owner-full-control"):
        raise S3Error(
            "InvalidBucketAclWithObjectOwnership",
            "Bucket cannot have ACLs set with ObjectOwnership's BucketOwnerEnforced setting",
        )
    lock = req.headers.get("x-amz-bucket-object-lock-enabled", "").lower() == "true"
    create_bucket(req.bucket, region, acl, lock, ownership)
    return Response(200, b"", {"Location": "/" + req.bucket})


def bucket_config(req: Request, bucket: Bucket, sub: str) -> Response:
    method = req.method
    configs = bucket.meta.setdefault("configs", {})
    if sub == "versioning":
        if method == "GET":
            inner = ""
            if bucket.meta.get("versioning"):
                inner += x("Status", bucket.meta["versioning"])
            if bucket.meta.get("mfa_delete"):
                inner += x("MfaDelete", bucket.meta["mfa_delete"])
            return xml_response("VersioningConfiguration", inner)
        if method == "PUT":
            root = parse_xml(req.small_body())
            status = text(root, "Status")
            if status not in ("Enabled", "Suspended", ""):
                raise _malformed()
            with STORE.lock:
                if bucket.meta.get("object_lock") and status == "Suspended":
                    raise S3Error(
                        "InvalidBucketState",
                        "An Object Lock configuration is present on this bucket, so "
                        "the versioning state cannot be changed.",
                        409,
                    )
                if status:
                    bucket.meta["versioning"] = status
                if text(root, "MfaDelete"):
                    bucket.meta["mfa_delete"] = text(root, "MfaDelete")
                bucket.save_meta()
            return Response(200)
    if sub == "tagging":
        if method == "GET":
            if not bucket.meta.get("tags"):
                raise S3Error("NoSuchTagSet", "The TagSet does not exist", 404, BucketName=bucket.name)
            return Response(200, tags_xml(bucket.meta["tags"]))
        if method == "PUT":
            tags = tags_from_xml(req.small_body(), 50)
            with STORE.lock:
                bucket.meta["tags"] = tags
                bucket.save_meta()
            return Response(204)
        if method == "DELETE":
            with STORE.lock:
                bucket.meta["tags"] = {}
                bucket.save_meta()
            return Response(204)
    if sub == "policy":
        if method == "GET":
            if not bucket.meta.get("policy"):
                raise S3Error("NoSuchBucketPolicy", "The bucket policy does not exist", 404, BucketName=bucket.name)
            return Response(200, bucket.meta["policy"].encode(), ctype="application/json")
        if method == "PUT":
            raw = req.small_body(20 * 1024).decode("utf-8", "replace")
            set_policy(bucket, raw)
            return Response(204)
        if method == "DELETE":
            with STORE.lock:
                bucket.meta["policy"] = None
                bucket.save_meta()
            return Response(204)
    if sub == "policyStatus" and method == "GET":
        return xml_response("PolicyStatus", x("IsPublic", "true" if policy_is_public(bucket) else "false"))
    if sub == "acl":
        if method == "GET":
            return Response(200, acl_xml(bucket.meta.get("acl")))
        if method == "PUT":
            acl = acl_from_request(req.headers, req.small_body())
            if acl is None:
                raise _malformed()
            if bucket_owner_enforced(bucket) and acl.get("canned") not in ("private", "bucket-owner-full-control"):
                raise S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs")
            if public_block(bucket)["BlockPublicAcls"] and (acl_public(acl, "READ") or acl_public(acl, "WRITE")):
                raise _denied()
            with STORE.lock:
                bucket.meta["acl"] = acl
                bucket.save_meta()
            return Response(200)
    if sub in ID_CONFIGS:
        store = bucket.meta.setdefault("ids", {}).setdefault(sub, {})
        config_id = req.q.get("id", "")
        element = ID_CONFIGS[sub]
        if method == "GET" and not config_id:
            inner = "".join(strip_decl(v) for _k, v in sorted(store.items())) + x("IsTruncated", "false")
            root = {
                "metrics": "ListMetricsConfigurationsResult",
                "analytics": "ListBucketAnalyticsConfigurationResult",
                "inventory": "ListInventoryConfigurationsResult",
                "intelligent-tiering": "ListBucketIntelligentTieringConfigurationsOutput",
            }[sub]
            return xml_response(root, inner)
        if not config_id:
            raise _invalid("The id parameter is required", "id", "")
        if method == "GET":
            if config_id not in store:
                raise S3Error("NoSuchConfiguration", "The specified configuration does not exist.", 404)
            return Response(200, ('<?xml version="1.0" encoding="UTF-8"?>\n' + strip_decl(store[config_id])).encode())
        if method == "PUT":
            body = req.small_body()
            root = parse_xml(body)
            if root.tag != element:
                raise _malformed()
            with STORE.lock:
                store[config_id] = body.decode("utf-8")
                bucket.save_meta()
            return Response(204 if sub != "inventory" else 200)
        if method == "DELETE":
            with STORE.lock:
                store.pop(config_id, None)
                bucket.save_meta()
            return Response(204)
    if sub in CONFIGS:
        missing_code, missing_message = CONFIGS[sub]
        if method == "GET":
            raw = configs.get(sub)
            if not raw:
                if sub in EMPTY_CONFIGS:
                    return Response(200, ('<?xml version="1.0" encoding="UTF-8"?>\n' + EMPTY_CONFIGS[sub]).encode())
                if sub == "encryption":
                    alg = "AES256"
                    return xml_response(
                        "ServerSideEncryptionConfiguration",
                        f"<Rule><ApplyServerSideEncryptionByDefault>{x('SSEAlgorithm', alg)}"
                        "</ApplyServerSideEncryptionByDefault><BucketKeyEnabled>false"
                        "</BucketKeyEnabled></Rule>",
                    )
                raise S3Error(missing_code, missing_message, 404, BucketName=bucket.name)
            return Response(200, ('<?xml version="1.0" encoding="UTF-8"?>\n' + strip_decl(raw)).encode())
        if method == "PUT":
            body = req.small_body()
            set_config(bucket, sub, body)
            return Response(200)
        if method == "DELETE":
            if sub == "object-lock":
                raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)
            with STORE.lock:
                configs.pop(sub, None)
                bucket.save_meta()
            return Response(204)
    raise S3Error(
        "NotImplemented", "A header or query you provided implies functionality that is not implemented.", 501
    )


def set_policy(bucket: Bucket, raw: str) -> None:
    try:
        policy = json.loads(raw)
    except ValueError:
        raise S3Error("MalformedPolicy", "Policies must be valid JSON and the first byte must be '{'") from None
    if not isinstance(policy, dict) or not isinstance(policy.get("Statement"), (list, dict)):
        raise S3Error("MalformedPolicy", "Missing required field Statement")
    for st in _as_list(policy["Statement"]):
        if not isinstance(st, dict) or st.get("Effect") not in ("Allow", "Deny"):
            raise S3Error("MalformedPolicy", "Statement must have an Effect of Allow or Deny")
        if "Action" not in st and "NotAction" not in st:
            raise S3Error("MalformedPolicy", "Missing required field Action")
        for resource in _as_list(st.get("Resource")):
            if isinstance(resource, str) and not resource.startswith(f"arn:aws:s3:::{bucket.name}"):
                raise S3Error("MalformedPolicy", "Policy has invalid resource")
    if public_block(bucket)["BlockPublicPolicy"] and _statements_public(policy):
        raise _denied()
    with STORE.lock:
        bucket.meta["policy"] = raw
        bucket.save_meta()


def set_config(bucket: Bucket, sub: str, body: bytes) -> None:
    root = parse_xml(body)
    expected = {
        "cors": "CORSConfiguration",
        "lifecycle": "LifecycleConfiguration",
        "website": "WebsiteConfiguration",
        "encryption": "ServerSideEncryptionConfiguration",
        "replication": "ReplicationConfiguration",
        "ownershipControls": "OwnershipControls",
        "publicAccessBlock": "PublicAccessBlockConfiguration",
        "object-lock": "ObjectLockConfiguration",
        "logging": "BucketLoggingStatus",
        "notification": "NotificationConfiguration",
        "accelerate": "AccelerateConfiguration",
        "requestPayment": "RequestPaymentConfiguration",
    }[sub]
    if root.tag != expected:
        raise _malformed()
    if sub == "cors":
        validate_cors(body)
    elif sub == "lifecycle":
        parse_lifecycle(body)
    elif sub == "website":
        if root.find("RedirectAllRequestsTo") is None and not text(root, "IndexDocument/Suffix"):
            raise _invalid("A value for IndexDocument Suffix must be provided if RedirectAllRequestsTo is empty")
    elif sub == "replication":
        if bucket.meta.get("versioning") != "Enabled":
            raise S3Error(
                "InvalidRequest", "Versioning must be 'Enabled' on the bucket to apply a replication configuration"
            )
    elif sub == "object-lock":
        if text(root, "ObjectLockEnabled") != "Enabled":
            raise _malformed()
        if bucket.meta.get("versioning") != "Enabled":
            raise S3Error(
                "InvalidBucketState",
                "Versioning must be 'Enabled' on the bucket to apply a Object Lock configuration",
                409,
            )
        mode = text(root, "Rule/DefaultRetention/Mode")
        if mode and mode not in ("GOVERNANCE", "COMPLIANCE"):
            raise _malformed()
        if mode and bool(text(root, "Rule/DefaultRetention/Days")) == bool(text(root, "Rule/DefaultRetention/Years")):
            raise _malformed()
    elif sub == "ownershipControls":
        if text(root, "Rule/ObjectOwnership") not in ("BucketOwnerPreferred", "ObjectWriter", "BucketOwnerEnforced"):
            raise _malformed()
    elif sub == "accelerate":
        if text(root, "Status") not in ("Enabled", "Suspended"):
            raise _malformed()
    elif sub == "requestPayment":
        if text(root, "Payer") not in ("Requester", "BucketOwner"):
            raise _malformed()
    elif sub == "encryption":
        alg = text(root, "Rule/ApplyServerSideEncryptionByDefault/SSEAlgorithm")
        if alg not in ("AES256", "aws:kms", "aws:kms:dsse"):
            raise _malformed()
    with STORE.lock:
        bucket.meta.setdefault("configs", {})[sub] = body.decode("utf-8")
        if sub == "object-lock":
            bucket.meta["object_lock"] = True
        bucket.save_meta()


def list_objects_v1(req: Request, bucket: Bucket) -> Response:
    q = req.q
    prefix, delimiter, marker = q.get("prefix", ""), q.get("delimiter", ""), q.get("marker", "")
    enc = q.get("encoding-type") == "url"
    if q.get("encoding-type") and not enc:
        raise _invalid("Invalid Encoding Method specified in Request", "encoding-type", q["encoding-type"])
    max_keys = _max_keys(q)
    with STORE.lock:
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
        raise _invalid("Invalid Encoding Method specified in Request", "encoding-type", q["encoding-type"])
    if token == "":
        raise _invalid("The continuation token provided is incorrect", "continuation-token", "")
    after = _token_decode(token) if token else start_after
    max_keys = _max_keys(q)
    owner = q.get("fetch-owner") == "true"
    with STORE.lock:
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
        inner += x("NextContinuationToken", _token_encode(last))
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
        raise _invalid("A version-id marker cannot be specified without a key marker.", "version-id-marker", vid_marker)
    enc = q.get("encoding-type") == "url"
    max_keys = _max_keys(q)
    with STORE.lock:
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
    max_uploads = _max_keys(q, "max-uploads")
    enc = q.get("encoding-type") == "url"
    with STORE.lock:
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
    with STORE.lock:
        bucket = STORE.get(req.bucket)
    root = parse_xml(req.small_body())
    if root.tag != "Delete":
        raise _malformed()
    quiet = text(root, "Quiet").lower() == "true"
    objects = root.findall("Object")
    if len(objects) > 1000:
        raise _malformed()
    bypass = req.headers.get("x-amz-bypass-governance-retention", "").lower() == "true"
    out = []
    for obj in objects:
        key = text(obj, "Key")
        vid_el = obj.find("VersionId")
        vid = (vid_el.text or "").strip() if vid_el is not None else None
        try:
            if req.who is None and not anonymous_allowed(bucket, "s3:DeleteObject", key):
                raise _denied()
            if vid_el is not None and not vid:
                raise S3Error("NoSuchVersion", "The specified version does not exist.", 404)
            etag = text(obj, "ETag")
            with STORE.lock:
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


# ----------------------------------------------------------------------------- object routes


def object_route(req: Request) -> Response:
    q, method = req.q, req.method
    with STORE.lock:
        bucket = STORE.get(req.bucket)
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
            with STORE.lock:
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


def get_object(req: Request, bucket: Bucket) -> Response:
    vid = _version_id(req)
    with STORE.lock:
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
            raise _invalid(
                "Part number must be an integer between 1 and 10000, inclusive", "partNumber", part
            ) from None
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
        with STORE.lock:
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
                    raise _no_key(req.key)
                check_conditions(current, {"if-match": req.headers["if-match"]}, write=True)
            blob = STORE.commit_blob(bucket, received.path)  # type: ignore[arg-type]
            received.path = None
            version = put_version(bucket, req.key, new_version(received, fields, blob))
    finally:
        if received.path:
            _unlink(received.path)
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
    src_bucket, src_key, src, src_path = read_source(req.headers, req.who)
    directive = req.headers.get("x-amz-metadata-directive", "COPY").upper()
    tag_directive = req.headers.get("x-amz-tagging-directive", "COPY").upper()
    if directive not in ("COPY", "REPLACE") or tag_directive not in ("COPY", "REPLACE"):
        raise _invalid("Unknown metadata directive.", "x-amz-metadata-directive", directive)
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
        with STORE.lock:
            blob = STORE.commit_blob(bucket, received.path)  # type: ignore[arg-type]
            received.path = None
            version = put_version(bucket, req.key, new_version(received, fields, blob))
    finally:
        if received.path:
            _unlink(received.path)
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
    with STORE.lock:
        if req.headers.get("if-match"):
            rec = bucket.objects.get(req.key)
            if not rec or rec["versions"][0].get("dm"):
                raise _no_key(req.key)
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
    need_auth(req, None, "")
    with STORE.lock:
        version = find_version(bucket, req.key, vid)
        headers = {"x-amz-version-id": version["id"]} if bucket.meta.get("versioning") else {}
        if req.method == "GET":
            return Response(200, tags_xml(version.get("tags") or {}), headers)
    if req.method == "PUT":
        tags = tags_from_xml(req.small_body())
        with STORE.lock:
            version = find_version(bucket, req.key, vid)
            version["tags"] = tags
            bucket.save_record(req.key)
        return Response(200, b"", headers)
    if req.method == "DELETE":
        with STORE.lock:
            version = find_version(bucket, req.key, vid)
            version["tags"] = {}
            bucket.save_record(req.key)
        return Response(204, b"", headers)
    raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)


def object_acl(req: Request, bucket: Bucket) -> Response:
    vid = _version_id(req)
    need_auth(req, None, "")
    if req.method == "GET":
        with STORE.lock:
            version = find_version(bucket, req.key, vid)
            return Response(200, acl_xml(version.get("acl")))
    if req.method == "PUT":
        acl = acl_from_request(req.headers, req.small_body())
        if acl is None:
            raise _malformed()
        if bucket_owner_enforced(bucket) and acl.get("canned") not in ("private", "bucket-owner-full-control"):
            raise S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs")
        if public_block(bucket)["BlockPublicAcls"] and acl_public(acl, "READ"):
            raise _denied()
        with STORE.lock:
            version = find_version(bucket, req.key, vid)
            version["acl"] = acl
            bucket.save_record(req.key)
        return Response(200)
    raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)


def object_lock_route(req: Request, bucket: Bucket, sub: str) -> Response:
    vid = _version_id(req)
    need_auth(req, None, "")
    if not lock_config(bucket)["enabled"]:
        raise S3Error("InvalidRequest", "Bucket is missing Object Lock Configuration")
    if req.method == "GET":
        with STORE.lock:
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
        with STORE.lock:
            version = find_version(bucket, req.key, vid)
            if sub == "legal-hold":
                status = text(root, "Status")
                if status not in ("ON", "OFF"):
                    raise _malformed()
                version["hold"] = status == "ON"
            else:
                mode, until = text(root, "Mode"), parse_time(text(root, "RetainUntilDate"))
                if (mode and mode not in ("GOVERNANCE", "COMPLIANCE")) or (mode and until is None):
                    raise _malformed()
                old = version.get("retention") or {}
                if old.get("until", 0) > time.time():
                    shorter = (
                        not mode
                        or (until or 0) < old["until"]
                        or (old["mode"] == "COMPLIANCE" and mode != "COMPLIANCE")
                    )
                    if shorter and (old["mode"] == "COMPLIANCE" or not bypass):
                        raise _denied("Access Denied because object protected by object lock.")
                if mode:
                    if until is not None and until <= time.time():
                        raise _invalid("The retain until date must be in the future!")
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
        raise _invalid(
            "The x-amz-object-attributes header specifying the attributes to be retrieved is either missing or empty",
            "x-amz-object-attributes",
            "",
        )
    with STORE.lock:
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
    need_auth(req, None, "")
    body = req.small_body()
    days = 1
    if body.strip():
        root = parse_xml(body)
        if text(root, "Type") == "SELECT":
            raise S3Error("NotImplemented", "S3 Select restore requests are not implemented.", 501)
        days = int(text(root, "Days") or 1)
    with STORE.lock:
        version = find_version(bucket, req.key, vid)
        if version.get("class") not in ARCHIVED:
            raise S3Error("InvalidObjectState", "Restore is not allowed for the object's current storage class", 403)
        already = bool(version.get("restore")) and version["restore"] > time.time()
        version["restore"] = time.time() + days * 86400
        bucket.save_record(req.key)
    return Response(200 if already else 202)


# ----------------------------------------------------------------------------- multipart uploads


def create_upload(req: Request, bucket: Bucket) -> Response:
    fields = object_fields(req.headers, bucket)
    alg = (req.headers.get("x-amz-checksum-algorithm") or "").upper()
    if alg and alg not in ALGORITHMS:
        raise _invalid(f"Checksum algorithm {alg} is not supported.", "x-amz-checksum-algorithm", alg)
    ctype = (req.headers.get("x-amz-checksum-type") or ("FULL_OBJECT" if alg == "CRC64NVME" else "COMPOSITE")).upper()
    if ctype not in ("COMPOSITE", "FULL_OBJECT"):
        raise _invalid("Invalid checksum type", "x-amz-checksum-type", ctype)
    if ctype == "FULL_OBJECT" and alg in ("SHA1", "SHA256"):
        raise _invalid(
            "The FULL_OBJECT checksum type is not supported for this algorithm", "x-amz-checksum-type", ctype
        )
    upload_id = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=").replace("-", ".")
    up = {
        "id": upload_id,
        "key": req.key,
        "initiated": _now(),
        "fields": fields,
        "alg": alg,
        "ctype": ctype if alg else "",
        "owner": req.who or "anonymous",
    }
    with STORE.lock:
        _write_json(bucket.upload_dir(upload_id) / "upload.json", up)
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
        raise _invalid(
            "Part number must be an integer between 1 and 10000, inclusive", "partNumber", req.q.get("partNumber", "")
        )
    with STORE.lock:
        up = _get_upload(bucket, upload_id, req.key)
    copy = "x-amz-copy-source" in req.headers
    if copy:
        _sb, _sk, src, src_path = read_source(req.headers, req.who)
        size = int(src["size"])
        start, end = 0, size - 1
        rng = req.headers.get("x-amz-copy-source-range")
        if rng:
            match = re.fullmatch(r"bytes=(\d+)-(\d+)", rng.strip())
            if not match or int(match.group(1)) > int(match.group(2)) or int(match.group(2)) >= size:
                raise _invalid(
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
            raise _invalid(
                f"Checksum Type mismatch occurred, expected checksum Type: {up['alg'].lower()}, actual "
                f"checksum Type: {alg.lower()}",
                "x-amz-checksum-algorithm",
                alg,
            )
        received = req.payload(up.get("alg") or alg, expected)
    part = {"n": n, "size": received.size, "etag": received.md5, "time": _now()}
    if received.checksum:
        part["checksum"] = next(iter(received.checksum.values()))
    try:
        with STORE.lock:
            up = _get_upload(bucket, upload_id, req.key)
            dest = bucket.upload_dir(upload_id) / ("%05d.part" % n)
            os.replace(str(received.path), str(dest))
            received.path = None
            _write_json(bucket.upload_dir(upload_id) / ("%05d.json" % n), part)
            up["parts"][n] = part
    finally:
        if received.path:
            _unlink(received.path)
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
        raise _malformed()
    with STORE.lock:
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
            raise _malformed() from None
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
        with STORE.lock:
            rec = bucket.objects.get(req.key)
            if rec and not rec["versions"][0].get("dm"):
                raise S3Error(
                    "PreconditionFailed",
                    "At least one of the pre-conditions you specified did not hold",
                    412,
                    Condition="If-None-Match",
                )
    full = new_checksum(alg) if alg and up.get("ctype") == "FULL_OBJECT" else None
    tmp = STORE.temp_file()
    total = 0
    with open(tmp, "wb") as out:
        for part in chosen:
            with open(bucket.upload_dir(upload_id) / ("%05d.part" % part["n"]), "rb") as fin:
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
            _unlink(tmp)
            raise S3Error(
                "BadDigest", f"The {alg} you specified for the full object did not match the calculated checksum."
            )
    try:
        with STORE.lock:
            up = _get_upload(bucket, upload_id, req.key)
            blob = STORE.commit_blob(bucket, tmp)
            version = dict(up["fields"])
            version.update(
                {
                    "blob": blob,
                    "size": total,
                    "etag": etag,
                    "time": _now(),
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
            _unlink(tmp)
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
    with STORE.lock:
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


# ----------------------------------------------------------------------------- browser POST uploads


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
    with STORE.lock:
        bucket = STORE.get(req.bucket)
    length = int(req.headers.get("content-length") or 0)
    if length > MAX_POST:
        raise S3Error("EntityTooLarge", "Your proposed upload exceeds the maximum allowed size", 400)
    body = req.small_body(MAX_POST)
    fields, file_part = _form_fields(body, req.headers.get("content-type", ""))
    if file_part is None:
        raise _invalid("POST requires exactly one file upload per request.", "file", "0")
    filename, part_type, data = file_part
    key = fields.get("key", "")
    if not key:
        raise _invalid(
            "Bucket POST must contain a field named 'key'.  If it is specified, please check the order of the fields.",
            "key",
            "",
        )
    key = key.replace("${filename}", filename)
    if AUTH == "off":
        pass
    elif "x-amz-signature" in fields or "signature" in fields:
        policy_b64 = fields.get("policy", "")
        if not policy_b64:
            raise _invalid("Bucket POST must contain a field named 'policy'.", "policy", "")
        if "x-amz-signature" in fields:
            if fields.get("x-amz-algorithm") != "AWS4-HMAC-SHA256":
                raise _invalid(
                    "Only AWS4-HMAC-SHA256 is supported.", "x-amz-algorithm", fields.get("x-amz-algorithm", "")
                )
            parts = fields.get("x-amz-credential", "").split("/")
            if len(parts) != 5:
                raise _invalid("The Credential is not valid.", "x-amz-credential", fields.get("x-amz-credential", ""))
            secret = CREDENTIALS.get(parts[0])
            if secret is None:
                raise S3Error(
                    "InvalidAccessKeyId", "The AWS Access Key Id you provided does not exist in our records.", 403
                )
            expected = hmac.new(
                _signing_key(secret, parts[1], parts[2], parts[3]), policy_b64.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, fields["x-amz-signature"]):
                raise S3Error(
                    "SignatureDoesNotMatch",
                    "The request signature we calculated does not match the signature you provided.",
                    403,
                )
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
        check_post_policy(policy_b64, fields, bucket.name, key, len(data))
    elif not anonymous_allowed(bucket, "s3:PutObject", key):
        raise _denied()
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
    received.path = STORE.temp_file()
    received.path.write_bytes(data)
    received.size = len(data)
    received.md5 = hashlib.md5(data).hexdigest()  # noqa: S324
    if alg:
        received.checksum = {alg: checksum_of(alg, data)}
        if expected_cs and expected_cs != received.checksum[alg]:
            _unlink(received.path)
            raise S3Error("BadDigest", f"The {alg} you specified did not match the calculated checksum.")
    with STORE.lock:
        blob = STORE.commit_blob(bucket, received.path)
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
        raise _invalid("Invalid Policy: Invalid JSON.", "policy", "") from None
    expiration = parse_time(str(policy.get("expiration", "")))
    if expiration is None or expiration < time.time():
        raise _denied("Invalid according to Policy: Policy expired.")
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
                    raise _denied(f'Invalid according to Policy: Policy Condition failed: ["eq", "${name}", "{want}"]')
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
                raise _denied(f"Invalid according to Policy: Policy Condition failed: {json.dumps(cond)}")
            if op == "starts-with":
                prefixes = [p.strip() for p in str(cond[2]).split(",")] if name == "content-type" else [str(cond[2])]
                if not any(value.startswith(p) for p in prefixes):
                    raise _denied(f"Invalid according to Policy: Policy Condition failed: {json.dumps(cond)}")
    for name in fields:
        if name in ("policy", "x-amz-signature", "signature", "file", "awsaccesskeyid") or name.startswith("x-ignore-"):
            continue
        if name not in covered:
            raise _denied(f"Invalid according to Policy: Extra input fields: {name}")


# ----------------------------------------------------------------------------- static website hosting


def website(req: Request, bucket_name: str, key: str, base: str) -> Response:
    if req.method not in ("GET", "HEAD"):
        raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)
    bucket = STORE.buckets.get(bucket_name)
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

    with STORE.lock:
        version = fetch(target)
        if version is None and key and not key.endswith("/") and fetch(key + "/" + suffix):
            return Response(302, b"", {"Location": base + quote(key) + "/"})
        allowed = version is not None and anonymous_allowed(bucket, "s3:GetObject", target, version)
    if version is not None and not allowed:
        return _web_error(403, "AccessDenied", "Access Denied")
    if version is None:
        red = redirect_for(404)
        if red:
            return red
        with STORE.lock:
            err_version = fetch(error_doc) if error_doc else None
            if err_version and anonymous_allowed(bucket, "s3:GetObject", error_doc, err_version):
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


# ----------------------------------------------------------------------------- web console API


def ui_route(req: Request) -> Response:
    if not UI_ON:
        raise S3Error("NotFound", "The web console is off (S3_UI=off).", 404)
    path = req.raw_path
    if path in ("/ui",):
        return Response(302, b"", {"Location": "/ui/"}, "text/plain")
    if path == "/ui/" and req.method in ("GET", "HEAD"):
        return Response(200, _ui_html(), UI_HEADERS, "text/html; charset=utf-8")
    found = _session(req.headers.get("cookie", ""))
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
        if _throttled(ip):
            raise S3Error("SlowDown", "Too many failed sign-ins; wait 5 minutes.", 429)
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except ValueError:
            raise _invalid("The request body is not valid JSON.") from None
        user, password = str(data.get("user") or ""), str(data.get("password") or "")
        if not _check_login(user, password):
            _failed(ip)
            log("console sign-in refused from", ip)
            raise S3Error("AccessDenied", "Wrong access key or password.", 401)
        sid, csrf = _new_session(user or "console")
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
            with _session_lock:
                SESSIONS.pop(found["id"], None)
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
            raise _invalid("The request body is not valid JSON.") from None
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


def _p(params: Dict[str, Any], name: str, required: bool = True) -> str:
    value = params.get(name)
    if value is None or value == "":
        if required:
            raise _invalid(f"{name} is required.", name, "")
        return ""
    return str(value)


def _version_json(key: str, version: Dict[str, Any], latest: bool = False) -> Dict[str, Any]:
    out = {
        "key": key,
        "versionId": version["id"],
        "modified": iso(version["time"]),
        "latest": latest,
        "deleteMarker": bool(version.get("dm")),
    }
    if not version.get("dm"):
        out.update(
            {
                "size": version["size"],
                "etag": version["etag"],
                "class": version.get("class", "STANDARD"),
                "type": version.get("type", ""),
            }
        )
    return out


def ui_list_buckets(_p_: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with STORE.lock:
        out = []
        for name in sorted(STORE.buckets):
            b = STORE.buckets[name]
            out.append(
                {
                    "name": name,
                    "created": iso(b.meta["created"]),
                    "region": b.meta.get("region") or REGION,
                    "versioning": b.meta.get("versioning") or "",
                    "objectLock": bool(b.meta.get("object_lock")),
                    "objects": sum(1 for r in b.objects.values() if not r["versions"][0].get("dm")),
                    "public": policy_is_public(b) or acl_public(b.meta.get("acl"), "READ"),
                }
            )
    return {"buckets": out}


def ui_create_bucket(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    name = _p(p, "bucket")
    bucket = create_bucket(name, str(p.get("region") or REGION), None, bool(p.get("objectLock")))
    if p.get("versioning") and not bucket.meta.get("versioning"):
        with STORE.lock:
            bucket.meta["versioning"] = "Enabled"
            bucket.save_meta()
    return {"bucket": name}


def ui_delete_bucket(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    name = _p(p, "bucket")
    with STORE.lock:
        bucket = STORE.get(name)
        if p.get("force"):
            for key in list(bucket.objects):
                for version in list(bucket.objects.get(key, {}).get("versions", [])):
                    if not version.get("dm"):
                        check_unlocked(version, bool(p.get("bypass")))
                    _remove_version(bucket, key, version["id"])
        delete_bucket(name)
    return {"deleted": name}


def ui_bucket_info(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        size = versions = objects = 0
        for rec in bucket.objects.values():
            if not rec["versions"][0].get("dm"):
                objects += 1
            for v in rec["versions"]:
                versions += 1
                size += int(v.get("size") or 0)
        meta = bucket.meta
        return {
            "name": bucket.name,
            "created": iso(meta["created"]),
            "region": meta.get("region") or REGION,
            "versioning": meta.get("versioning") or "",
            "mfaDelete": meta.get("mfa_delete") or "",
            "objectLock": bool(meta.get("object_lock")),
            "tags": meta.get("tags") or {},
            "policy": meta.get("policy") or "",
            "acl": acl_canned_name(meta.get("acl")),
            "configs": {k: strip_decl(v) for k, v in (meta.get("configs") or {}).items()},
            "ids": {k: sorted(v) for k, v in (meta.get("ids") or {}).items()},
            "publicBlock": public_block(bucket),
            "policyPublic": policy_is_public(bucket),
            "stats": {"objects": objects, "versions": versions, "bytes": size, "uploads": len(bucket.uploads)},
            "websiteUrl": f"/-/website/{bucket.name}/",
        }


def ui_list_objects(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        prefix = str(p.get("prefix") or "")
        search = str(p.get("search") or "").lower()
        delimiter = "" if search else str(p.get("delimiter", "/"))
        after = str(p.get("token") or "")
        limit = min(int(p.get("max") or 500), 1000)
        include = visible(bucket)
        if p.get("deleted"):
            include = lambda k: bool(bucket.objects.get(k))  # noqa: E731
        if search:
            base = include
            include = lambda k: base(k) and search in k[len(prefix) :].lower()  # noqa: E731
        keys, prefixes, truncated, last = list_keys(bucket, prefix, delimiter, after, limit, include)
        objects = [_version_json(k, bucket.objects[k]["versions"][0], True) for k in keys]
    return {"folders": prefixes, "objects": objects, "next": last if truncated else ""}


def ui_head_object(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        key = _p(p, "key")
        rec = bucket.objects.get(key)
        if not p.get("versionId") and rec and rec["versions"][0].get("dm"):
            # A deleted object (shown with "Show deleted"): its newest real version.
            live = [v for v in rec["versions"] if not v.get("dm")]
            if not live:
                raise _no_key(key)
            version = live[0]
        else:
            version = find_version(bucket, key, p.get("versionId") or None)
            rec = bucket.objects[key]
        out = _version_json(key, version, version is rec["versions"][0])
        out.update(
            {
                "meta": version.get("meta") or {},
                "headers": version.get("headers") or {},
                "tags": version.get("tags") or {},
                "acl": acl_canned_name(version.get("acl")),
                "checksum": version.get("checksum"),
                "parts": len(version.get("parts") or []),
                "retention": (
                    {"mode": version["retention"]["mode"], "until": iso(version["retention"]["until"])}
                    if version.get("retention")
                    else None
                ),
                "legalHold": bool(version.get("hold")),
                "sse": version.get("sse") or {},
                "redirect": version.get("redirect") or "",
                "objectLock": lock_config(bucket)["enabled"],
                "versions": [_version_json(key, v, i == 0) for i, v in enumerate(rec["versions"])],
                "restore": iso(version["restore"]) if version.get("restore") else "",
            }
        )
        return out


def ui_list_versions(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        prefix = str(p.get("prefix") or "")
        out = []
        for key in bucket.keys():
            if not key.startswith(prefix):
                continue
            for i, v in enumerate(bucket.objects[key]["versions"]):
                out.append(_version_json(key, v, i == 0))
                if len(out) >= 2000:
                    return {"versions": out, "truncated": True}
    return {"versions": out, "truncated": False}


def ui_delete_objects(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    deleted, errors = [], []
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        for item in p.get("objects") or []:
            key, vid = str(item.get("key") or ""), item.get("versionId") or None
            try:
                if key.endswith("/") and item.get("recursive"):
                    for sub in [k for k in bucket.keys() if k.startswith(key)]:
                        delete_object(bucket, sub, None, bypass=False)
                else:
                    delete_object(bucket, key, vid, bypass=bool(p.get("bypass")))
                deleted.append(key)
            except S3Error as exc:
                errors.append({"key": key, "code": exc.code, "message": exc.message})
    return {"deleted": deleted, "errors": errors}


def ui_copy(p: Dict[str, Any], req: Request) -> Dict[str, Any]:
    src_bucket, src_key = _p(p, "bucket"), _p(p, "key")
    dst_bucket, dst_key = str(p.get("toBucket") or src_bucket), _p(p, "toKey")
    moved = []
    with STORE.lock:
        sb = STORE.get(src_bucket)
        db = STORE.get(dst_bucket)
        if src_key.endswith("/"):
            pairs = [
                (k, dst_key.rstrip("/") + "/" + k[len(src_key) :])
                for k in sb.keys()
                if k.startswith(src_key) and not sb.objects[k]["versions"][0].get("dm")
            ]
        else:
            pairs = [(src_key, dst_key)]
    for skey, dkey in pairs:
        if sb is db and skey == dkey:
            continue
        with STORE.lock:
            src = dict(find_version(sb, skey, p.get("versionId") or None if len(pairs) == 1 else None))
            path = sb.blob_path(src["blob"])
        received = copy_file(path, 0, int(src["size"]) - 1, (src.get("checksum") or {}).get("alg", ""))
        fields = {
            k: src[k]
            for k in ("type", "meta", "headers", "class", "tags", "acl", "sse", "redirect", "owner")
            if k in src
        }
        with STORE.lock:
            blob = STORE.commit_blob(db, received.path)  # type: ignore[arg-type]
            put_version(db, dkey, new_version(received, fields, blob))
            if p.get("move"):
                delete_object(sb, skey, None, bypass=False)
        moved.append(dkey)
    return {"copied": moved}


def ui_create_folder(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    key = _p(p, "key")
    if not key.endswith("/"):
        key += "/"
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        tmp = STORE.temp_file()
        tmp.write_bytes(b"")
        received = Received()
        received.path, received.md5 = tmp, hashlib.md5(b"").hexdigest()  # noqa: S324
        blob = STORE.commit_blob(bucket, tmp)
        put_version(
            bucket,
            key,
            new_version(
                received,
                {
                    "type": "application/x-directory",
                    "meta": {},
                    "headers": {},
                    "class": "STANDARD",
                    "tags": {},
                    "owner": OWNER_ID,
                    "sse": default_encryption(bucket),
                },
                blob,
            ),
        )
    return {"key": key}


def ui_put_object_tags(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    tags = {str(k): str(v) for k, v in (p.get("tags") or {}).items()}
    validate_tags(tags)
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        version = find_version(bucket, _p(p, "key"), p.get("versionId") or None)
        version["tags"] = tags
        bucket.save_record(_p(p, "key"))
    return {"tags": tags}


def ui_update_meta(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    """Replace the content type, standard headers, user metadata and storage class (a copy onto itself)."""
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        key = _p(p, "key")
        src = dict(find_version(bucket, key, None))
        path = bucket.blob_path(src["blob"])
    headers = {k.lower(): str(v) for k, v in (p.get("headers") or {}).items() if k.lower() in STD_HEADERS and v}
    meta = {str(k).lower(): str(v) for k, v in (p.get("meta") or {}).items() if k}
    if sum(len(k) + len(v) for k, v in meta.items()) > 2048:
        raise S3Error("MetadataTooLarge", "Your metadata headers exceed the maximum allowed metadata size.")
    sclass = str(p.get("class") or src.get("class") or "STANDARD")
    if sclass not in STORAGE_CLASSES:
        raise S3Error("InvalidStorageClass", "The storage class you specified is not valid")
    received = copy_file(path, 0, int(src["size"]) - 1, (src.get("checksum") or {}).get("alg", ""))
    fields = {k: src[k] for k in ("tags", "acl", "sse", "redirect", "owner", "retention", "hold") if k in src}
    fields.update(
        {
            "type": str(p.get("type") or src.get("type") or "binary/octet-stream"),
            "headers": headers,
            "meta": meta,
            "class": sclass,
        }
    )
    with STORE.lock:
        blob = STORE.commit_blob(bucket, received.path)  # type: ignore[arg-type]
        version = put_version(bucket, key, new_version(received, fields, blob))
    return {"versionId": version["id"]}


def ui_restore_version(p: Dict[str, Any], req: Request) -> Dict[str, Any]:
    """Make an older version the current one (copies it on top, like the AWS console)."""
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        key = _p(p, "key")
        src = dict(find_version(bucket, key, _p(p, "versionId")))
        path = bucket.blob_path(src["blob"])
    received = copy_file(path, 0, int(src["size"]) - 1, (src.get("checksum") or {}).get("alg", ""))
    fields = {
        k: src[k] for k in ("type", "meta", "headers", "class", "tags", "acl", "sse", "redirect", "owner") if k in src
    }
    with STORE.lock:
        blob = STORE.commit_blob(bucket, received.path)  # type: ignore[arg-type]
        version = put_version(bucket, key, new_version(received, fields, blob))
    return {"versionId": version["id"]}


def ui_put_bucket_setting(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    """One bucket setting: versioning, tags, policy, acl, or a configuration document (XML, "" deletes it)."""
    name, setting = _p(p, "bucket"), _p(p, "setting")
    value = p.get("value")
    with STORE.lock:
        bucket = STORE.get(name)
    if setting == "versioning":
        if value not in ("Enabled", "Suspended"):
            raise _invalid("versioning must be Enabled or Suspended")
        if bucket.meta.get("object_lock") and value == "Suspended":
            raise S3Error("InvalidBucketState", "Object Lock is on: versioning cannot be suspended.", 409)
        with STORE.lock:
            bucket.meta["versioning"] = value
            bucket.save_meta()
    elif setting == "tags":
        tags = {str(k): str(v) for k, v in (value or {}).items()}
        validate_tags(tags, 50)
        with STORE.lock:
            bucket.meta["tags"] = tags
            bucket.save_meta()
    elif setting == "policy":
        if value:
            set_policy(bucket, str(value))
        else:
            with STORE.lock:
                bucket.meta["policy"] = None
                bucket.save_meta()
    elif setting == "acl":
        if value not in CANNED:
            raise _invalid("Unknown canned ACL")
        if bucket_owner_enforced(bucket) and value not in ("private", "bucket-owner-full-control"):
            raise S3Error(
                "AccessControlListNotSupported",
                "The bucket does not allow ACLs (ownership controls are BucketOwnerEnforced).",
            )
        if public_block(bucket)["BlockPublicAcls"] and value in ("public-read", "public-read-write"):
            raise _denied("Block public access is on (BlockPublicAcls).")
        with STORE.lock:
            bucket.meta["acl"] = {"canned": value}
            bucket.save_meta()
    elif setting in CONFIGS:
        if value:
            set_config(bucket, setting, str(value).encode("utf-8"))
        else:
            if setting == "object-lock":
                raise _invalid("Object Lock cannot be turned off.")
            with STORE.lock:
                bucket.meta.setdefault("configs", {}).pop(setting, None)
                bucket.save_meta()
    else:
        raise _invalid(f"Unknown setting {setting}.")
    return ui_bucket_info({"bucket": name}, _r)


def ui_put_object_acl(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    value = _p(p, "acl")
    if value not in CANNED:
        raise _invalid("Unknown canned ACL")
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        if bucket_owner_enforced(bucket) and value not in ("private", "bucket-owner-full-control"):
            raise S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs.")
        if public_block(bucket)["BlockPublicAcls"] and value in ("public-read", "public-read-write"):
            raise _denied("Block public access is on (BlockPublicAcls).")
        version = find_version(bucket, _p(p, "key"), p.get("versionId") or None)
        version["acl"] = {"canned": value}
        bucket.save_record(_p(p, "key"))
    return {"acl": value}


def ui_object_lock(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        if not lock_config(bucket)["enabled"]:
            raise S3Error("InvalidRequest", "Bucket is missing Object Lock Configuration")
        key = _p(p, "key")
        version = find_version(bucket, key, p.get("versionId") or None)
        if "legalHold" in p:
            version["hold"] = bool(p["legalHold"])
        if "mode" in p:
            mode = str(p.get("mode") or "")
            old = version.get("retention") or {}
            until = parse_time(str(p.get("until") or ""))
            if old.get("until", 0) > time.time():
                shorter = not mode or (until or 0) < old["until"]
                if shorter and (old["mode"] == "COMPLIANCE" or not p.get("bypass")):
                    raise _denied("The object is protected by its retention; it cannot be shortened.")
            if mode:
                if mode not in ("GOVERNANCE", "COMPLIANCE") or until is None or until <= time.time():
                    raise _invalid("Pick GOVERNANCE or COMPLIANCE and a date in the future.")
                version["retention"] = {"mode": mode, "until": until}
            else:
                version.pop("retention", None)
        bucket.save_record(key)
    return ui_head_object(p, _r)


def ui_presign(p: Dict[str, Any], req: Request) -> Dict[str, Any]:
    try:
        expires = int(p.get("expires") or 3600)
    except (TypeError, ValueError):
        raise _invalid("Expiry must be a number of seconds.") from None
    if expires < 1 or expires > 604800:
        raise _invalid("Expiry must be between 1 second and 7 days.")
    access = req.who if req.who in CREDENTIALS else next(iter(CREDENTIALS), "")
    if not access:
        raise _invalid("Share links need a credential (S3_SECRET_ACCESS_KEY); authentication is off.")
    method = str(p.get("method") or "GET").upper()
    if method not in ("GET", "PUT"):
        raise _invalid("method must be GET or PUT")
    host = str(p.get("host") or req.host)
    scheme = "https" if str(p.get("scheme") or "") == "https" else "http"
    return {
        "url": presign(
            method, host, _p(p, "bucket"), _p(p, "key"), expires, access, str(p.get("versionId") or ""), scheme
        ),
        "expires": expires,
    }


def ui_list_uploads(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        return {
            "uploads": [
                {
                    "key": u["key"],
                    "uploadId": u["id"],
                    "initiated": iso(u["initiated"]),
                    "parts": len(u["parts"]),
                    "bytes": sum(int(x_["size"]) for x_ in u["parts"].values()),
                }
                for u in sorted(bucket.uploads.values(), key=lambda u: u["initiated"])
            ]
        }


def ui_abort_upload(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        if _p(p, "uploadId") not in bucket.uploads:
            raise S3Error("NoSuchUpload", "The specified upload does not exist.", 404)
        abort_upload(bucket, _p(p, "uploadId"))
    return {"aborted": True}


def ui_restore_archived(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    days = int(p.get("days") or 1)
    with STORE.lock:
        bucket = STORE.get(_p(p, "bucket"))
        version = find_version(bucket, _p(p, "key"), p.get("versionId") or None)
        if version.get("class") not in ARCHIVED:
            raise S3Error("InvalidObjectState", "Only GLACIER and DEEP_ARCHIVE objects are restored.", 403)
        version["restore"] = time.time() + days * 86400
        bucket.save_record(_p(p, "key"))
    return {"restored": True}


def ui_run_lifecycle(_p_: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    return {"changes": sweep_lifecycle()}


UI_OPS: Dict[str, Callable[[Dict[str, Any], Request], Dict[str, Any]]] = {
    "ListBuckets": ui_list_buckets,
    "CreateBucket": ui_create_bucket,
    "DeleteBucket": ui_delete_bucket,
    "BucketInfo": ui_bucket_info,
    "ListObjects": ui_list_objects,
    "HeadObject": ui_head_object,
    "ListVersions": ui_list_versions,
    "DeleteObjects": ui_delete_objects,
    "Copy": ui_copy,
    "CreateFolder": ui_create_folder,
    "PutObjectTags": ui_put_object_tags,
    "UpdateMeta": ui_update_meta,
    "RestoreVersion": ui_restore_version,
    "PutBucketSetting": ui_put_bucket_setting,
    "PutObjectAcl": ui_put_object_acl,
    "ObjectLock": ui_object_lock,
    "Presign": ui_presign,
    "ListUploads": ui_list_uploads,
    "AbortUpload": ui_abort_upload,
    "RestoreArchived": ui_restore_archived,
    "RunLifecycle": ui_run_lifecycle,
}


def ui_upload(req: Request) -> Response:
    bucket_name, key = req.q.get("bucket", ""), req.q.get("key", "")
    if not key:
        raise _invalid("key is required", "key", "")
    with STORE.lock:
        bucket = STORE.get(bucket_name)
    headers = {"content-type": req.headers.get("content-type") or "binary/octet-stream"}
    sclass = req.q.get("class")
    if sclass:
        headers["x-amz-storage-class"] = sclass
    fields = object_fields(headers, bucket)
    req.auth = Auth("console", "console")
    req.auth.payload = "UNSIGNED-PAYLOAD"
    received = req.payload("", "")
    try:
        with STORE.lock:
            blob = STORE.commit_blob(bucket, received.path)  # type: ignore[arg-type]
            received.path = None
            version = put_version(bucket, key, new_version(received, fields, blob))
    finally:
        if received.path:
            _unlink(received.path)
    log("console upload", bucket_name, key, received.size, "bytes")
    return Response(
        200,
        json.dumps({"key": key, "etag": version["etag"], "versionId": version["id"]}).encode(),
        {"Cache-Control": "no-store"},
        "application/json",
    )


def ui_download(req: Request) -> Response:
    with STORE.lock:
        bucket = STORE.get(req.q.get("bucket", ""))
        key = req.q.get("key", "")
        version = dict(find_version(bucket, key, req.q.get("versionId") or None))
        path = bucket.blob_path(version["blob"])
    name = key.rstrip("/").rsplit("/", 1)[-1] or "download"
    inline = req.q.get("inline") == "1"
    ctype = version.get("type") or "binary/octet-stream"
    # Inline previews only for types a browser shows without running anything from the bucket.
    safe_inline = inline and (
        ctype.startswith(("image/", "video/", "audio/", "text/plain")) or ctype == "application/pdf"
    )
    if ctype.startswith("image/svg"):
        safe_inline = False
    disposition = ("inline" if safe_inline else "attachment") + f"; filename*=UTF-8''{quote(name)}"
    headers = {
        "Content-Disposition": disposition,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; "
        "style-src 'unsafe-inline'; sandbox",
    }
    return Response(
        200, b"", headers, ctype if safe_inline else "application/octet-stream", path, 0, int(version["size"])
    )


# ----------------------------------------------------------------------------- main


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return  # the client went away
        super().handle_error(request, client_address)


def check() -> int:
    import urllib.request

    host = "127.0.0.1" if BIND in ("0.0.0.0", "") else BIND  # noqa: S104
    try:
        with urllib.request.urlopen(f"http://{host}:{PORT}/-/health", timeout=3) as resp:  # noqa: S310 - local health
            return 0 if resp.status == 200 else 1
    except OSError:
        return 1


def main() -> int:
    global STORE
    if "--check" in sys.argv[1:]:
        return check()
    if AUTH not in ("sigv4", "off"):
        print("S3_AUTH must be sigv4 or off", file=sys.stderr)
        return 2
    if AUTH != "off" and not CREDENTIALS:
        print(
            "set S3_SECRET_ACCESS_KEY (and S3_ACCESS_KEY_ID), or S3_CREDENTIALS=id:secret, or S3_AUTH=off",
            file=sys.stderr,
        )
        return 2
    STORE = Store(DATA_DIR)
    server = Server((BIND, PORT), Handler)
    threading.Thread(target=lifecycle_loop, name="lifecycle", daemon=True).start()
    log(
        f"S3 compatible server {VERSION} (Python) on {BIND}:{PORT}, data {DATA_DIR}, {len(STORE.buckets)} buckets, "
        f"auth {AUTH}" + (", console /ui/" if UI_ON else "")
    )
    if AUTH == "off":
        log("warning: S3_AUTH=off, anyone who reaches the port can read and change every object")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
