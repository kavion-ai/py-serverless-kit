"""Request signatures: AWS Signature Version 4 and 2 (header and presigned), chunk signing keys, ``presign()``."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import unquote

from .config import CREDENTIALS, REGION, SKEW, V2_SUBRESOURCES
from .errors import S3Error
from .util import iso, parse_time, split_query, uri_encode

_AUTH4 = re.compile(r"^AWS4-HMAC-SHA256\s+Credential=([^,\s]+),\s*SignedHeaders=([^,\s]+),\s*Signature=([0-9a-f]{64})$")


class Auth:
    """Who signed a request (``principal`` None: anonymous) and how; the signing key for streaming chunks."""

    def __init__(self, principal: Optional[str], mode: str = "anonymous") -> None:
        self.principal = principal
        self.mode = mode
        self.payload = ""  # x-amz-content-sha256 as signed
        self.key = b""  # the signing key, for streaming chunk signatures
        self.signature = ""
        self.amz_date = ""
        self.scope = ""
        self.via = ""  # s3:authType: REST-HEADER, REST-QUERY-STRING or POST


def chunk_signature(auth: Auth, prev: str, kind: str, data_hash: str) -> str:
    empty = hashlib.sha256(b"").hexdigest()
    if kind == "trailer":
        to_sign = "\n".join(["AWS4-HMAC-SHA256-TRAILER", auth.amz_date, auth.scope, prev, data_hash])
    else:
        to_sign = "\n".join(["AWS4-HMAC-SHA256-PAYLOAD", auth.amz_date, auth.scope, prev, empty, data_hash])
    return hmac.new(auth.key, to_sign.encode(), hashlib.sha256).hexdigest()


def signing_key(secret: str, day: str, region: str, service: str) -> bytes:
    key = ("AWS4" + secret).encode("utf-8")
    for part in (day, region, service, "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    return key


def canonical_query(pairs: List[Tuple[str, str]], skip: str = "") -> str:
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
    query = canonical_query(pairs, "X-Amz-Signature" if presigned else "")
    scope = f"{day}/{region}/{service}/aws4_request"
    key = signing_key(secret, day, region, service)
    for path in _canonical_paths(raw_path):
        canonical = "\n".join([method, path, query, canonical_headers, signed_headers.lower(), payload])
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        if hmac.compare_digest(hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest(), signature):
            auth = Auth(access_key, "sigv4")
            auth.via = "REST-QUERY-STRING" if presigned else "REST-HEADER"
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
    auth.via = "REST-QUERY-STRING" if presigned else "REST-HEADER"
    auth.payload = "UNSIGNED-PAYLOAD"
    return auth


def presign(
    method: str,
    host: str,
    bucket: str,
    key: str,
    expires: int,
    access_key: str,
    version_id: str = "",
    scheme: str = "http",
    params: Sequence[Tuple[str, str]] = (),
) -> str:
    """A presigned URL; ``params`` (e.g. ``response-content-disposition``) are signed with it."""
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
    pairs.extend(params)
    query = canonical_query(pairs)
    canonical = "\n".join([method, path, query, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"])
    scope = f"{day}/{REGION}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    signature = hmac.new(signing_key(secret, day, REGION, "s3"), to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{scheme}://{host}{path}?{query}&X-Amz-Signature={signature}"
