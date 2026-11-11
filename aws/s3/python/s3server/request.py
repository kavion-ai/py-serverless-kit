"""One HTTP request (``Request``), its ``Response``, authentication, and the policy context of a request."""

from __future__ import annotations

import ipaddress
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional
from urllib.parse import urlsplit

from .access import allowed
from .config import ACCOUNT, AUTH, MAX_OBJECT, MAX_XML
from .errors import S3Error, denied
from .payload import Raw, Received, receive
from .policy import Context
from .sigv4 import Auth, verify_v2, verify_v4
from .store import Bucket
from .util import doc, split_query

if TYPE_CHECKING:
    from .http import Handler


SIGNATURE_VERSIONS = {"sigv4": "AWS4-HMAC-SHA256", "sigv2": "AWS"}
# Request headers available to policy conditions as s3:<header>.
CONDITION_HEADERS = ("x-amz-acl", "x-amz-server-side-encryption", "x-amz-storage-class", "x-amz-content-sha256")


class Request:
    """One S3 request: its path, query, lower-cased headers, body reader and (once authenticated) its signer."""

    def __init__(self, handler: Handler) -> None:
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

    def context(self) -> Context:
        """The requester and condition key values bucket policies are matched against."""
        peer = str(self.handler.client_address[0])
        local = _loopback(peer)
        forwarded = self.headers.get("x-forwarded-for", "").split(",")[0].strip()
        secure = local and self.headers.get("x-forwarded-proto", "").strip().lower() == "https"
        now = time.time()
        values = {
            "aws:SourceIp": forwarded if local and forwarded else peer,
            "aws:SecureTransport": "true" if secure else "false",
            "aws:CurrentTime": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "aws:EpochTime": str(int(now)),
            "aws:PrincipalType": "Anonymous" if self.who is None else "Account",
        }
        for key, header in (("aws:Referer", "referer"), ("aws:UserAgent", "user-agent")):
            if header in self.headers:
                values[key] = self.headers[header]
        if self.who is not None:
            values.update({"aws:username": self.who, "aws:userid": self.who, "aws:PrincipalAccount": ACCOUNT})
            if self.auth.via:
                values["s3:authType"] = self.auth.via
            if self.auth.mode in SIGNATURE_VERSIONS:
                values["s3:signatureversion"] = SIGNATURE_VERSIONS[self.auth.mode]
        for name in ("prefix", "delimiter", "max-keys"):
            if name in self.q:
                values["s3:" + name] = self.q[name]
        if "versionId" in self.q:
            values["s3:VersionId"] = self.q["versionId"]
        for header in CONDITION_HEADERS:
            if header in self.headers:
                values["s3:" + header] = self.headers[header]
        return Context(self.who, values)


class Response:
    """A status, headers and a body (bytes, or a byte range of a file)."""

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
    req: Request,
    bucket: Optional[Bucket],
    action: str,
    key: str = "",
    version: Optional[Dict[str, Any]] = None,
    *,
    owner_only: bool = False,
) -> None:
    """Refuse the request unless it may do ``action``.

    Without a bucket, or with ``owner_only`` (bucket settings and object subresources), only signed requests may; a
    bucket policy Deny still applies to them.
    """
    if (bucket is None or owner_only) and req.who is None:
        raise denied()
    if bucket is not None and not allowed(bucket, action, req.context(), key, version):
        raise denied()


# Bucket subresource -> the action name of (GET, PUT, DELETE), as IAM names them.
_CONFIG_ACTIONS = {
    "policy": ("GetBucketPolicy", "PutBucketPolicy", "DeleteBucketPolicy"),
    "policyStatus": ("GetBucketPolicyStatus", "", ""),
    "versioning": ("GetBucketVersioning", "PutBucketVersioning", ""),
    "tagging": ("GetBucketTagging", "PutBucketTagging", "PutBucketTagging"),
    "cors": ("GetBucketCORS", "PutBucketCORS", "PutBucketCORS"),
    "website": ("GetBucketWebsite", "PutBucketWebsite", "DeleteBucketWebsite"),
    "lifecycle": ("GetLifecycleConfiguration", "PutLifecycleConfiguration", "PutLifecycleConfiguration"),
    "acl": ("GetBucketAcl", "PutBucketAcl", ""),
    "publicAccessBlock": ("GetBucketPublicAccessBlock", "PutBucketPublicAccessBlock", "PutBucketPublicAccessBlock"),
    "ownershipControls": ("GetBucketOwnershipControls", "PutBucketOwnershipControls", "PutBucketOwnershipControls"),
    "object-lock": ("GetBucketObjectLockConfiguration", "PutBucketObjectLockConfiguration", ""),
    "encryption": ("GetEncryptionConfiguration", "PutEncryptionConfiguration", "PutEncryptionConfiguration"),
}


def config_action(sub: str, method: str) -> str:
    """The IAM action of a bucket configuration request (``s3:Get<Sub>`` style for the rarely used ones)."""
    names = _CONFIG_ACTIONS.get(sub, ("", "", ""))
    name = names[{"GET": 0, "HEAD": 0, "PUT": 1, "DELETE": 2}.get(method, 1)]
    if not name:
        verb = {"GET": "Get", "HEAD": "Get", "DELETE": "Delete"}.get(method, "Put")
        name = verb + "Bucket" + sub[:1].upper() + sub[1:].replace("-", "")
    return "s3:" + name


def object_action(sub: str, method: str, versioned: bool) -> str:
    """The IAM action of an object subresource request (tagging, acl, retention, legal-hold, restore)."""
    if sub == "restore":
        return "s3:RestoreObject"
    noun = {"tagging": "Tagging", "acl": "Acl", "retention": "Retention", "legal-hold": "LegalHold"}[sub]
    verb = {"GET": "Get", "HEAD": "Get", "DELETE": "Delete"}.get(method, "Put")
    version = "Version" if versioned and sub in ("tagging", "acl") else ""
    return f"s3:{verb}Object{version}{noun}"


def _loopback(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return bool(ip.is_loopback or (mapped is not None and mapped.is_loopback))
