"""pskit's own web UI for on-prem services whose native UI is missing or limited.

* **Object storage**: S3 (MinIO, RustFS, LocalStack, LocalEmu) and Cloud Storage (fake-gcs-server): buckets, folders,
  paginated object lists, upload / download / delete / copy / rename, metadata, share links (S3 presigned URLs),
  bucket versioning and policies (S3).
* **Secrets**: OpenBao / Vault KV v2 (folders, versions) and AWS Secrets Manager APIs (LocalStack, LocalEmu and
  pskit's own Secrets Manager compatible server, which checks the signature with its keys).
  OpenBao's release images ship without its web UI, so this is the UI for it.

Requests go to the service's address and port, or over SSH to ``127.0.0.1:<port>`` on its server when the port is not
reachable from this machine (the same route as :class:`HostControl`). Credentials come from the service's state entry
(``.pskit/onprem-services.json``) and never reach the browser.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import uuid
import xml.etree.ElementTree as ET  # noqa: S405 - responses of the user's own service
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from ..runtime.drivers._aws import canonical_query, sign, uri_encode
from .onprem_control import HostControl, HostUnavailable

MAX_TRANSFER = 64 * 1024 * 1024  # bytes per upload / download through the studio
REGION = "us-east-1"

# Which browsers a service gets (catalog field ``browsers``).
BROWSERS: Dict[str, List[str]] = {
    "minio": ["s3"],
    "rustfs": ["s3"],
    "localstack": ["s3", "aws-secrets"],
    "localemu": ["s3", "aws-secrets"],
    "fake-gcs": ["gcs"],
    "openbao": ["vault"],
    "secretsmanager": ["aws-secrets"],
    "secretsmanager-node": ["aws-secrets"],
    "s3": ["s3"],
    "s3-node": ["s3"],
}
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


class BrowseError(Exception):
    """A request the service refused or that cannot be made; the message is shown as is."""


def browsers_for(service: str) -> List[str]:
    return list(BROWSERS.get(service, []))


# ----------------------------------------------------------------------------- transport


def _client(entry: Dict[str, Any], timeout: float = 60.0) -> HostControl:
    from .onprem_services import ssh_options

    target = entry.get("target") or {}
    address = str(entry.get("address") or "127.0.0.1")
    port = int(entry.get("port") or 0)
    ssh = ssh_options(target) if target.get("method") == "ssh" else None
    host = f"[{address}]" if ":" in address and not address.startswith("[") else address
    return HostControl(f"http://{host}:{port}", timeout=timeout, ssh=ssh, remote_port=port,
                       server=str(target.get("server") or "") or None)


def _env_value(entry: Dict[str, Any], suffix: str) -> str:
    for name, value in (entry.get("env") or {}).items():
        if str(name).endswith(suffix):
            return str(value)
    return ""


def _fetch(control: HostControl, method: str, path: str, data: Optional[bytes], headers: Dict[str, str],
           timeout: Optional[float] = None) -> Tuple[int, Dict[str, str], bytes]:
    try:
        status, hdrs, body = control.fetch(method, path, data, headers, timeout=timeout)
    except HostUnavailable as exc:
        raise BrowseError(str(exc).replace("on-prem host", "service")) from None
    return status, {k.lower(): v for k, v in hdrs.items()}, body


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: Any) -> bytes:
    try:
        data = base64.b64decode(str(text or ""), validate=True)
    except (ValueError, TypeError):
        raise BrowseError("content must be base64") from None
    if len(data) > MAX_TRANSFER:
        raise BrowseError(f"files up to {MAX_TRANSFER // (1024 * 1024)} MB go through the studio")
    return data


# ----------------------------------------------------------------------------- S3


class S3:
    def __init__(self, entry: Dict[str, Any]) -> None:
        self.entry = entry
        self.control = _client(entry)
        self.host = self.control.base_url.split("://", 1)[1]
        if entry.get("service") in ("localstack", "localemu"):
            self.access_key, self.secret_key = "test", "test"
        else:
            self.access_key = _env_value(entry, "_ACCESS_KEY") or str(entry.get("user") or "")
            self.secret_key = _env_value(entry, "_SECRET_KEY")
        if not self.secret_key:
            raise BrowseError("the service's secret key is not in .pskit/onprem-services.json; recreate the service")

    # -- signing
    def call(self, method: str, bucket: str = "", key: str = "", query: Optional[Dict[str, str]] = None,
             body: bytes = b"", headers: Optional[Dict[str, str]] = None, ok: Tuple[int, ...] = (200,)) -> Tuple[
                 int, Dict[str, str], bytes]:
        path = "/" + (uri_encode(bucket) if bucket else "")
        if key:
            path += "/" + uri_encode(key, keep_slash=True)
        query = dict(query or {})
        signed = sign(method, self.host, path, query, dict(headers or {}), hashlib.sha256(body).hexdigest(),
                      self.access_key, self.secret_key, REGION, datetime.now(timezone.utc))
        suffix = path + (f"?{canonical_query(query)}" if query else "")
        status, hdrs, data = _fetch(self.control, method, suffix, body if method in ("PUT", "POST") else None, signed,
                                    timeout=300)
        if status not in ok:
            raise BrowseError(f"S3 {method} {bucket}/{key}: HTTP {status} {_s3_error(data)}".rstrip())
        return status, hdrs, data

    def presign(self, bucket: str, key: str, expires: int) -> str:
        now = datetime.now(timezone.utc)
        amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        scope = f"{day}/{REGION}/s3/aws4_request"
        path = f"/{uri_encode(bucket)}/{uri_encode(key, keep_slash=True)}"
        query = {"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{self.access_key}/{scope}",
                 "X-Amz-Date": amz_date, "X-Amz-Expires": str(expires), "X-Amz-SignedHeaders": "host"}
        canonical = "\n".join(["GET", path, canonical_query(query), f"host:{self.host}\n", "host", "UNSIGNED-PAYLOAD"])
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        k = ("AWS4" + self.secret_key).encode()
        for part in (day, REGION, "s3", "aws4_request"):
            k = hmac.new(k, part.encode(), hashlib.sha256).digest()
        query["X-Amz-Signature"] = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
        return f"{self.control.base_url}{path}?{canonical_query(query)}"


def _strip(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _xml(data: bytes) -> ET.Element:
    try:
        root = ET.fromstring(data)  # noqa: S314 - the user's own service
    except ET.ParseError:
        raise BrowseError(f"unexpected answer: {data[:200]!r}") from None
    for el in root.iter():
        el.tag = _strip(el.tag)
    return root


def _s3_error(data: bytes) -> str:
    try:
        root = _xml(data)
    except BrowseError:
        return data[:200].decode("utf-8", "replace")
    return " ".join(x for x in (root.findtext("Code"), root.findtext("Message")) if x)


def _bucket(body: Dict[str, Any]) -> str:
    name = str(body.get("bucket") or "")
    if not _BUCKET.match(name):
        raise BrowseError("bucket names are 3-63 lowercase letters, digits, dots and hyphens")
    return name


def _key(body: Dict[str, Any], field: str = "key") -> str:
    key = str(body.get(field) or "")
    if not key or len(key) > 1024 or any(ord(c) < 32 for c in key):
        raise BrowseError(f"{field} must be 1-1024 printable characters")
    return key.lstrip("/")


def _s3(entry: Dict[str, Any], action: str, body: Dict[str, Any]) -> Dict[str, Any]:
    s3 = S3(entry)
    if action == "buckets":
        root = _xml(s3.call("GET")[2])
        return {"buckets": [{"name": b.findtext("Name"), "created": b.findtext("CreationDate")}
                            for b in root.iter("Bucket")]}
    if action == "bucket-create":
        s3.call("PUT", _bucket(body))
        return {"created": body["bucket"]}
    if action == "bucket-delete":
        bucket = _bucket(body)
        deleted = (_s3_delete_prefix(s3, bucket, "") + _s3_delete_versions(s3, bucket, "")) if body.get("force") else 0
        s3.call("DELETE", bucket, ok=(200, 204))
        return {"deleted": bucket, "objects": deleted}
    if action == "list":
        bucket = _bucket(body)
        limit = max(1, min(1000, int(body.get("limit") or 100)))
        query = {"list-type": "2", "max-keys": str(limit), "prefix": str(body.get("prefix") or ""),
                 "fetch-owner": "false"}
        if body.get("delimiter", True):
            query["delimiter"] = "/"
        if body.get("token"):
            query["continuation-token"] = str(body["token"])
        root = _xml(s3.call("GET", bucket, query=query)[2])
        return {
            "folders": [p.findtext("Prefix") for p in root.findall("CommonPrefixes")],
            "objects": [{"key": c.findtext("Key"), "size": int(c.findtext("Size") or 0),
                         "modified": c.findtext("LastModified"), "etag": (c.findtext("ETag") or "").strip('"'),
                         "storage_class": c.findtext("StorageClass")} for c in root.findall("Contents")],
            "next": root.findtext("NextContinuationToken") if root.findtext("IsTruncated") == "true" else None,
        }
    if action == "head":
        _status, hdrs, _ = s3.call("HEAD", _bucket(body), _key(body))
        return {"key": body["key"], "size": int(hdrs.get("content-length") or 0),
                "content_type": hdrs.get("content-type"), "etag": (hdrs.get("etag") or "").strip('"'),
                "modified": hdrs.get("last-modified"), "version": hdrs.get("x-amz-version-id"),
                "metadata": {k[len("x-amz-meta-"):]: v for k, v in hdrs.items() if k.startswith("x-amz-meta-")}}
    if action == "versions":
        bucket, key = _bucket(body), _key(body)
        root = _xml(s3.call("GET", bucket, query={"versions": "", "prefix": key, "max-keys": "100"})[2])
        rows = [{"version": v.findtext("VersionId"), "latest": v.findtext("IsLatest") == "true",
                 "modified": v.findtext("LastModified"), "size": int(v.findtext("Size") or 0),
                 "deleted": v.tag == "DeleteMarker"}
                for v in root if v.tag in ("Version", "DeleteMarker") and v.findtext("Key") == key]
        return {"versions": rows}
    if action == "get":
        bucket, key = _bucket(body), _key(body)
        version = {"versionId": str(body["version"])} if body.get("version") else None
        _status, hdrs, data = s3.call("GET", bucket, key, query=version)
        if len(data) > MAX_TRANSFER:
            raise BrowseError("too large for the studio: use a share link")
        return {"key": key, "content_type": hdrs.get("content-type") or "application/octet-stream",
                "content": _b64(data)}
    if action == "put":
        bucket, key = _bucket(body), _key(body)
        headers = {"content-type": str(body.get("content_type") or "application/octet-stream")}
        for name, value in (body.get("metadata") or {}).items():
            if re.match(r"^[A-Za-z0-9_-]{1,64}$", str(name)):
                headers[f"x-amz-meta-{str(name).lower()}"] = str(value)[:1024]
        data = _unb64(body.get("content"))
        s3.call("PUT", bucket, key, body=data, headers=headers)
        return {"uploaded": key, "size": len(data)}
    if action == "folder":
        bucket, prefix = _bucket(body), _key(body, "prefix")
        s3.call("PUT", bucket, prefix.rstrip("/") + "/", body=b"")
        return {"created": prefix.rstrip("/") + "/"}
    if action == "delete":
        bucket = _bucket(body)
        keys = body.get("keys") or []
        if not isinstance(keys, list) or not keys or len(keys) > 1000:
            raise BrowseError("keys must be a list of 1-1000 keys")
        count = 0
        for key in keys:
            key = _key({"key": key})
            if key.endswith("/"):
                count += _s3_delete_prefix(s3, bucket, key)
            else:
                s3.call("DELETE", bucket, key, ok=(200, 204))
                count += 1
        return {"deleted": count}
    if action in ("copy", "move"):
        bucket, key = _bucket(body), _key(body)
        to_bucket = _bucket({"bucket": body.get("to_bucket") or bucket})
        to_key = _key(body, "to_key")
        source = "/" + quote(f"{bucket}/{key}", safe="/")
        s3.call("PUT", to_bucket, to_key, headers={"x-amz-copy-source": source})
        if action == "move":
            s3.call("DELETE", bucket, key, ok=(200, 204))
        return {"copied": f"{to_bucket}/{to_key}"}
    if action == "share":
        expires = _expires(body)
        return {"url": s3.presign(_bucket(body), _key(body), expires), "expires": expires}
    if action == "versioning":
        bucket = _bucket(body)
        if "enabled" in body:
            state = "Enabled" if body["enabled"] else "Suspended"
            xml = (f'<VersioningConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Status>{state}'
                   "</Status></VersioningConfiguration>").encode()
            s3.call("PUT", bucket, query={"versioning": ""}, body=xml)
        root = _xml(s3.call("GET", bucket, query={"versioning": ""})[2])
        return {"status": root.findtext("Status") or "Off"}
    if action == "policy":
        bucket = _bucket(body)
        if body.get("preset") == "public-read":
            body = {**body, "policy": json.dumps({"Version": "2012-10-17", "Statement": [{
                "Effect": "Allow", "Principal": {"AWS": ["*"]}, "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"]}]})}
            _set_public_block(s3, bucket, False)  # a block refuses public policies
        if body.get("preset") == "private":
            s3.call("DELETE", bucket, query={"policy": ""}, ok=(200, 204))
            # Objects uploaded with a public-read ACL (or a public bucket ACL) stay readable without keys after the
            # policy is gone: reset the bucket ACL and block public access, which also ignores public object ACLs.
            _try(s3, "PUT", bucket, query={"acl": ""}, headers={"x-amz-acl": "private"})
            _set_public_block(s3, bucket, True)
        elif body.get("policy"):
            try:
                text = json.dumps(json.loads(str(body["policy"])))
            except ValueError:
                raise BrowseError("the policy must be JSON") from None
            s3.call("PUT", bucket, query={"policy": ""}, body=text.encode(), ok=(200, 204))
        status, _h, data = s3.call("GET", bucket, query={"policy": ""}, ok=(200, 404))
        return {"policy": data.decode("utf-8", "replace") if status == 200 else "",
                "blocked": _public_blocked(s3, bucket)}
    raise BrowseError(f"unknown S3 action {action!r}")


MAX_SHARE = 7 * 24 * 3600  # the longest S3 presigned URL
PUBLIC_BLOCK = ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")


def _expires(body: Dict[str, Any]) -> int:
    """Seconds a share link stays valid: any whole number from 1 second to 7 days (default 1 hour)."""
    raw = body.get("expires")
    try:
        expires = int(raw) if raw not in (None, "") else 3600
    except (TypeError, ValueError):
        raise BrowseError("expires must be a number of seconds") from None
    if not 1 <= expires <= MAX_SHARE:
        raise BrowseError("a share link is valid for 1 second to 7 days (604800 seconds)")
    return expires


def _try(s3: S3, method: str, bucket: str, **kwargs: Any) -> bool:
    """A call some S3 services don't implement (MinIO has no ACLs or public access block): False when refused."""
    try:
        s3.call(method, bucket, ok=(200, 204), **kwargs)
    except BrowseError:
        return False
    return True


def _set_public_block(s3: S3, bucket: str, on: bool) -> bool:
    flags = "".join(f"<{n}>{'true' if on else 'false'}</{n}>" for n in PUBLIC_BLOCK)
    xml = f'<PublicAccessBlockConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">{flags}' \
          "</PublicAccessBlockConfiguration>"
    return _try(s3, "PUT", bucket, query={"publicAccessBlock": ""}, body=xml.encode())


def _public_blocked(s3: S3, bucket: str) -> bool:
    """Requests without keys are refused whatever the policy and ACLs say (public access block)."""
    try:
        status, _h, data = s3.call("GET", bucket, query={"publicAccessBlock": ""}, ok=(200, 404))
    except BrowseError:
        return False
    if status != 200:
        return False
    try:
        root = _xml(data)
    except BrowseError:
        return False
    return all((root.findtext(n) or "").strip().lower() == "true" for n in ("IgnorePublicAcls", "RestrictPublicBuckets"))


def _s3_delete_versions(s3: S3, bucket: str, prefix: str) -> int:
    """Old versions and delete markers (a versioned bucket only deletes once they are gone)."""
    count = 0
    while True:
        root = _xml(s3.call("GET", bucket, query={"versions": "", "prefix": prefix, "max-keys": "1000"})[2])
        rows = [(v.findtext("Key") or "", v.findtext("VersionId") or "") for v in root
                if v.tag in ("Version", "DeleteMarker")]
        for key, version in rows:
            s3.call("DELETE", bucket, key, query={"versionId": version} if version else None, ok=(200, 204))
            count += 1
        if not rows or root.findtext("IsTruncated") != "true":
            return count


def _s3_delete_prefix(s3: S3, bucket: str, prefix: str) -> int:
    count, token = 0, None
    while True:
        query = {"list-type": "2", "max-keys": "1000", "prefix": prefix}
        if token:
            query["continuation-token"] = token
        root = _xml(s3.call("GET", bucket, query=query)[2])
        for key in [c.findtext("Key") or "" for c in root.findall("Contents")]:
            s3.call("DELETE", bucket, key, ok=(200, 204))
            count += 1
        token = root.findtext("NextContinuationToken")
        if root.findtext("IsTruncated") != "true" or not token:
            return count


# ----------------------------------------------------------------------------- Cloud Storage (fake-gcs-server)


def _gcs(entry: Dict[str, Any], action: str, body: Dict[str, Any]) -> Dict[str, Any]:
    control = _client(entry)

    def call(method: str, path: str, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None,
             ok: Tuple[int, ...] = (200,)) -> Tuple[Dict[str, str], bytes]:
        status, hdrs, out = _fetch(control, method, path, data, headers or {}, timeout=300)
        if status not in ok:
            raise BrowseError(f"Cloud Storage {method} {path.split('?')[0]}: HTTP {status} {out[:200].decode('utf-8', 'replace')}")
        return hdrs, out

    def obj(key: str) -> str:
        return quote(key, safe="")

    if action == "buckets":
        listed = json.loads(call("GET", "/storage/v1/b?project=pskit")[1] or b"{}").get("items") or []
        return {"buckets": [{"name": b.get("name"), "created": b.get("timeCreated")} for b in listed]}
    if action == "bucket-create":
        call("POST", "/storage/v1/b?project=pskit", json.dumps({"name": _bucket(body)}).encode(),
             {"content-type": "application/json"})
        return {"created": body["bucket"]}
    if action == "bucket-delete":
        bucket = _bucket(body)
        deleted = 0
        if body.get("force"):
            while True:
                items = json.loads(call("GET", f"/storage/v1/b/{bucket}/o?maxResults=1000")[1]).get("items") or []
                if not items:
                    break
                for it in items:
                    call("DELETE", f"/storage/v1/b/{bucket}/o/{obj(it['name'])}", ok=(200, 204))
                    deleted += 1
        call("DELETE", f"/storage/v1/b/{bucket}", ok=(200, 204))
        return {"deleted": bucket, "objects": deleted}
    if action == "list":
        # fake-gcs-server drops the rest of a listing when maxResults cuts it (no nextPageToken), so read it all
        # and page here: the token is an offset into folders + objects.
        bucket = _bucket(body)
        limit = max(1, min(1000, int(body.get("limit") or 100)))
        offset = int(body.get("token") or 0)
        q = {"prefix": str(body.get("prefix") or "")}
        if body.get("delimiter", True):
            q["delimiter"] = "/"
        folders: List[str] = []
        objects: List[Dict[str, Any]] = []
        token = ""
        for _ in range(100):
            page = json.loads(call("GET", f"/storage/v1/b/{bucket}/o?{canonical_query({**q, **({'pageToken': token} if token else {})})}")[1] or b"{}")
            folders += [p for p in page.get("prefixes") or [] if p not in folders]
            objects += page.get("items") or []
            token = page.get("nextPageToken") or ""
            if not token:
                break
        rows: List[Any] = [("f", p) for p in sorted(folders)] + [("o", it) for it in sorted(objects, key=lambda i: i.get("name") or "")]
        window = rows[offset:offset + limit]
        return {"folders": [r[1] for r in window if r[0] == "f"],
                "objects": [{"key": it.get("name"), "size": int(it.get("size") or 0), "modified": it.get("updated"),
                             "etag": it.get("etag"), "storage_class": it.get("storageClass")}
                            for kind, it in window if kind == "o"],
                "next": str(offset + limit) if offset + limit < len(rows) else None}
    if action == "head":
        bucket, key = _bucket(body), _key(body)
        it = json.loads(call("GET", f"/storage/v1/b/{bucket}/o/{obj(key)}")[1])
        return {"key": key, "size": int(it.get("size") or 0), "content_type": it.get("contentType"),
                "etag": it.get("etag"), "modified": it.get("updated"), "metadata": it.get("metadata") or {}}
    if action == "get":
        bucket, key = _bucket(body), _key(body)
        hdrs, data = call("GET", f"/storage/v1/b/{bucket}/o/{obj(key)}?alt=media")
        return {"key": key, "content_type": hdrs.get("content-type") or "application/octet-stream",
                "content": _b64(data)}
    if action in ("put", "folder"):
        bucket = _bucket(body)
        key = _key(body) if action == "put" else _key(body, "prefix").rstrip("/") + "/"
        data = _unb64(body.get("content")) if action == "put" else b""
        ctype = str(body.get("content_type") or "application/octet-stream")
        call("POST", f"/upload/storage/v1/b/{bucket}/o?uploadType=media&name={quote(key, safe='')}", data,
             {"content-type": ctype})
        return {"uploaded": key, "size": len(data)}
    if action == "delete":
        bucket = _bucket(body)
        count = 0
        for key in body.get("keys") or []:
            key = _key({"key": key})
            if key.endswith("/"):
                page = json.loads(call("GET", f"/storage/v1/b/{bucket}/o?prefix={quote(key, safe='')}")[1])
                for it in page.get("items") or []:
                    call("DELETE", f"/storage/v1/b/{bucket}/o/{obj(it['name'])}", ok=(200, 204))
                    count += 1
            else:
                call("DELETE", f"/storage/v1/b/{bucket}/o/{obj(key)}", ok=(200, 204))
                count += 1
        return {"deleted": count}
    if action in ("copy", "move"):
        bucket, key = _bucket(body), _key(body)
        to_bucket = _bucket({"bucket": body.get("to_bucket") or bucket})
        to_key = _key(body, "to_key")
        call("POST", f"/storage/v1/b/{bucket}/o/{obj(key)}/copyTo/b/{to_bucket}/o/{obj(to_key)}", b"{}",
             {"content-type": "application/json"})
        if action == "move":
            call("DELETE", f"/storage/v1/b/{bucket}/o/{obj(key)}", ok=(200, 204))
        return {"copied": f"{to_bucket}/{to_key}"}
    if action == "share":
        bucket, key = _bucket(body), _key(body)
        return {"url": f"{control.base_url}/storage/v1/b/{bucket}/o/{obj(key)}?alt=media", "expires": 0}
    raise BrowseError(f"Cloud Storage: {action!r} is not available")


# ----------------------------------------------------------------------------- secrets


def _secret_path(body: Dict[str, Any], field: str = "path", folder: bool = False) -> str:
    path = str(body.get(field) or "").strip("/")
    if folder and not path:
        return ""
    if not re.match(r"^[A-Za-z0-9_.@+=-]+(/[A-Za-z0-9_.@+=-]+)*$", path) or any(
            part in (".", "..") for part in path.split("/")):
        raise BrowseError("secret names use letters, digits and _ . @ + = - (folders with /)")
    return path


def _values(body: Dict[str, Any]) -> Dict[str, str]:
    data = body.get("data")
    if not isinstance(data, dict) or not data:
        raise BrowseError("data must be an object of key: value pairs")
    return {str(k): str(v) for k, v in data.items()}


def _vault(entry: Dict[str, Any], action: str, body: Dict[str, Any]) -> Dict[str, Any]:
    control = _client(entry)
    token = _env_value(entry, "_TOKEN")
    mount = _env_value(entry, "_MOUNT") or "secret"
    if not token:
        raise BrowseError("the OpenBao token is not in .pskit/onprem-services.json; recreate the service")

    def call(method: str, path: str, payload: Any = None, ok: Tuple[int, ...] = (200, 204)) -> Tuple[int, Any]:
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"x-vault-token": token, **({"content-type": "application/json"} if data else {})}
        status, _h, out = _fetch(control, method, f"/v1/{mount}/{path}", data, headers)
        if status not in ok:
            try:
                errors = "; ".join(json.loads(out).get("errors") or [])
            except ValueError:
                errors = out[:200].decode("utf-8", "replace")
            if status == 503:
                errors = (errors or "") + " (sealed: restart the service; it unseals itself on start)"
            raise BrowseError(f"OpenBao {method} {path}: HTTP {status} {errors}".rstrip())
        return status, (json.loads(out) if out.strip() else {})

    if action == "list":
        folder = _secret_path(body, folder=True)
        status, out = call("GET", f"metadata/{folder}?list=true" if folder else "metadata/?list=true", ok=(200, 404))
        keys = (out.get("data") or {}).get("keys") or [] if status == 200 else []
        return {"items": [{"name": k.rstrip("/"), "folder": k.endswith("/"),
                           "path": f"{folder}/{k}".strip("/") if folder else k.rstrip("/")} for k in sorted(keys)],
                "next": None}
    if action == "get":
        path = _secret_path(body)
        version = body.get("version")
        _s, out = call("GET", f"data/{path}" + (f"?version={int(version)}" if version else ""))
        _s, meta = call("GET", f"metadata/{path}")
        versions = (meta.get("data") or {}).get("versions") or {}
        return {"path": path, "data": (out.get("data") or {}).get("data") or {},
                "version": ((out.get("data") or {}).get("metadata") or {}).get("version"),
                "versions": [{"version": int(v), "created": d.get("created_time"),
                              "deleted": bool(d.get("deletion_time")) or bool(d.get("destroyed"))}
                             for v, d in sorted(versions.items(), key=lambda kv: -int(kv[0]))]}
    if action == "put":
        path = _secret_path(body)
        _s, out = call("POST", f"data/{path}", {"data": _values(body)})
        return {"path": path, "version": (out.get("data") or {}).get("version")}
    if action == "delete":
        path = _secret_path(body)
        call("DELETE", f"metadata/{path}")
        return {"deleted": path}
    raise BrowseError(f"unknown secrets action {action!r}")


def _aws_secrets(entry: Dict[str, Any], action: str, body: Dict[str, Any]) -> Dict[str, Any]:
    control = _client(entry)
    host = control.base_url.split("://", 1)[1]
    # The emulators accept any key; pskit's Secrets Manager server checks the signature with the service's keys.
    access = _env_value(entry, "_ACCESS_KEY") or "test"
    secret = _env_value(entry, "_SECRET_KEY") or "test"

    def call(target: str, payload: Dict[str, Any], ok: Tuple[int, ...] = (200,)) -> Tuple[int, Dict[str, Any]]:
        data = json.dumps(payload).encode()
        headers = sign("POST", host, "/", {}, {"content-type": "application/x-amz-json-1.1",
                                                "x-amz-target": f"secretsmanager.{target}"},
                       hashlib.sha256(data).hexdigest(), access, secret, REGION, datetime.now(timezone.utc),
                       service="secretsmanager")
        status, _h, out = _fetch(control, "POST", "/", data, headers)
        parsed = json.loads(out) if out.strip() else {}
        if status not in ok:
            raise BrowseError(f"Secrets Manager {target}: HTTP {status} {parsed.get('message') or parsed.get('Message') or ''}")
        return status, parsed

    if action == "list":
        payload: Dict[str, Any] = {"MaxResults": max(1, min(100, int(body.get("limit") or 50)))}
        if body.get("token"):
            payload["NextToken"] = str(body["token"])
        if body.get("path"):
            payload["Filters"] = [{"Key": "name", "Values": [str(body["path"])]}]
        _s, out = call("ListSecrets", payload)
        return {"items": [{"name": s.get("Name"), "folder": False, "path": s.get("Name"),
                           "modified": str(s.get("LastChangedDate") or "")} for s in out.get("SecretList") or []],
                "next": out.get("NextToken")}
    if action == "get":
        path = _secret_path(body)
        _s, out = call("GetSecretValue", {"SecretId": path})
        text = out.get("SecretString") or ""
        try:
            data = json.loads(text)
            data = data if isinstance(data, dict) else {"value": text}
        except ValueError:
            data = {"value": text}
        return {"path": path, "data": {k: str(v) for k, v in data.items()}, "version": out.get("VersionId"),
                "versions": []}
    if action == "put":
        path = _secret_path(body)
        text = json.dumps(_values(body))
        token = str(uuid.uuid4())  # required by the API (SDKs add it); idempotency for retries
        status, _out = call("PutSecretValue", {"SecretId": path, "SecretString": text, "ClientRequestToken": token},
                            ok=(200, 400))
        if status == 400:
            call("CreateSecret", {"Name": path, "SecretString": text, "ClientRequestToken": token})
        return {"path": path}
    if action == "delete":
        path = _secret_path(body)
        call("DeleteSecret", {"SecretId": path, "ForceDeleteWithoutRecovery": True})
        return {"deleted": path}
    raise BrowseError(f"unknown secrets action {action!r}")


# ----------------------------------------------------------------------------- entry point

_HANDLERS = {"s3": _s3, "gcs": _gcs, "vault": _vault, "aws-secrets": _aws_secrets}


def browse(entry: Dict[str, Any], kind: str, action: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run one browser ``action`` (``buckets``, ``list``, ``get``, ``put`` ...) of ``kind`` on a service entry."""
    service = str(entry.get("service") or "")
    if kind not in BROWSERS.get(service, []):
        offered = ", ".join(BROWSERS.get(service, [])) or "none"
        raise BrowseError(f"{service} has no {kind!r} browser (it has: {offered})")
    try:
        return _HANDLERS[kind](entry, action, dict(body or {}))
    except (ValueError, TypeError) as exc:  # bad numbers / shapes in the request
        raise BrowseError(str(exc)) from None
