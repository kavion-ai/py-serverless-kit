"""AWS Signature Version 4 (the check every API request passes, exactly as AWS does it) and SES SMTP passwords."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Dict, Tuple
from urllib.parse import parse_qsl, quote

from .config import AUTH_RE, CREDENTIALS, SKEW
from .errors import ApiError


def _uri_encode(text: str) -> str:
    return quote(text, safe="-_.~")


def _forbidden(code: str, message: str) -> ApiError:
    return ApiError(code, message, 403, code)


def verify_sigv4(method: str, raw_path: str, query: str, headers: Dict[str, str], body: bytes) -> Tuple[str, str]:
    """(access key id, region) of a correctly signed request, else :class:`ApiError` as AWS answers it.

    ``raw_path`` is the path as sent (still percent-encoded): SES, like every service but S3, signs it encoded once
    more."""
    auth = headers.get("authorization", "")
    if not auth:
        raise _forbidden("MissingAuthenticationToken", "Request is missing Authentication Token")
    match = AUTH_RE.match(auth.strip())
    if not match:
        raise _forbidden("IncompleteSignature", "Authorization header requires Credential, SignedHeaders and "
                         "Signature (AWS4-HMAC-SHA256).")
    credential, signed_headers, signature = match.groups()
    parts = credential.split("/")
    if len(parts) != 5 or parts[4] != "aws4_request":
        raise _forbidden("IncompleteSignature", "The Credential is not valid.")
    access_key, day, region, service, _term = parts
    secret = CREDENTIALS.get(access_key)
    if secret is None:
        raise _forbidden("InvalidClientTokenId", "The security token included in the request is invalid.")
    amz_date = headers.get("x-amz-date", "")
    try:
        when = datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise _forbidden("IncompleteSignature", "X-Amz-Date is missing or not valid.") from None
    if abs(time.time() - when.timestamp()) > SKEW:
        raise _forbidden("SignatureDoesNotMatch", f"Signature expired: {amz_date} is now earlier or later than "
                         "15 minutes from the server's time.")
    if day != amz_date[:8] or service not in ("ses", "email"):
        raise _forbidden("SignatureDoesNotMatch", "The credential scope does not match the request.")
    names = signed_headers.split(";")
    if "host" not in names or any(n not in headers for n in names):
        raise _forbidden("SignatureDoesNotMatch", "SignedHeaders must include host and only headers that were sent.")
    payload_hash = hashlib.sha256(body).hexdigest()
    claimed = headers.get("x-amz-content-sha256")
    if claimed and claimed not in (payload_hash, "UNSIGNED-PAYLOAD"):
        raise _forbidden("SignatureDoesNotMatch", "x-amz-content-sha256 does not match the request body.")
    pairs = sorted((_uri_encode(k), _uri_encode(v)) for k, v in parse_qsl(query, keep_blank_values=True))
    canonical = "\n".join([
        method.upper(),
        quote(raw_path or "/", safe="/~"),
        "&".join(f"{k}={v}" for k, v in pairs),
        "".join(f"{n}:{' '.join(headers[n].split())}\n" for n in names),
        signed_headers,
        claimed or payload_hash,
    ])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
    key = ("AWS4" + secret).encode("utf-8")
    for part in (day, region, service, "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise _forbidden("SignatureDoesNotMatch", "The request signature we calculated does not match the "
                         "signature you provided. Check your AWS Secret Access Key and signing method.")
    return access_key, region


def smtp_password(secret: str, region: str) -> str:
    """The SES SMTP password of a secret access key in a region (AWS's published algorithm, version 4)."""
    key = ("AWS4" + secret).encode("utf-8")
    for part in ("11111111", region, "ses", "aws4_request", "SendRawEmail"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(b"\x04" + key).decode("ascii")


def check_smtp_login(user: str, password: str) -> bool:
    """An SMTP login: the access key ID with its SES SMTP password (any region) or its secret access key."""
    secret = CREDENTIALS.get(user)
    if secret is None:
        hmac.compare_digest(password, "x" * 44)  # the same work for an unknown user
        return False
    if hmac.compare_digest(password.encode("utf-8"), secret.encode("utf-8")):
        return True
    try:
        raw = base64.b64decode(password, validate=True)
    except ValueError:
        return False
    if len(raw) != 33 or raw[0] != 4:
        return False
    from .config import REGION

    regions = {REGION, "us-east-1", "us-east-2", "us-west-1", "us-west-2", "eu-west-1", "eu-west-2", "eu-west-3",
               "eu-central-1", "eu-north-1", "eu-south-1", "ap-south-1", "ap-southeast-1", "ap-southeast-2",
               "ap-northeast-1", "ap-northeast-2", "ap-northeast-3", "ca-central-1", "sa-east-1", "me-south-1",
               "af-south-1", "il-central-1"}
    return any(hmac.compare_digest(smtp_password(secret, r), password) for r in regions)
