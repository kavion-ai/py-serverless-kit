"""AWS Signature Version 4: the check every API request passes, exactly as AWS does it."""

from __future__ import annotations

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


def verify_sigv4(method: str, path: str, query: str, headers: Dict[str, str], body: bytes) -> Tuple[str, str]:
    """(access key id, region) of a correctly signed request, else :class:`ApiError` as AWS answers it."""
    auth = headers.get("authorization", "")
    if not auth:
        raise ApiError("MissingAuthenticationTokenException", "Missing Authentication Token")
    match = AUTH_RE.match(auth.strip())
    if not match:
        raise ApiError("IncompleteSignatureException", "Authorization header requires Credential, SignedHeaders and "
                       "Signature (AWS4-HMAC-SHA256).")
    credential, signed_headers, signature = match.groups()
    parts = credential.split("/")
    if len(parts) != 5 or parts[4] != "aws4_request":
        raise ApiError("IncompleteSignatureException", "The Credential is not valid.")
    access_key, day, region, service, _term = parts
    secret = CREDENTIALS.get(access_key)
    if secret is None:
        raise ApiError("UnrecognizedClientException", "The security token included in the request is invalid.")
    amz_date = headers.get("x-amz-date", "")
    try:
        when = datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ApiError("IncompleteSignatureException", "X-Amz-Date is missing or not valid.") from None
    if abs(time.time() - when.timestamp()) > SKEW:
        raise ApiError("InvalidSignatureException", f"Signature expired: {amz_date} is now earlier or later than "
                       "15 minutes from the server's time.")
    if day != amz_date[:8] or service != "secretsmanager":
        raise ApiError("InvalidSignatureException", "The credential scope does not match the request.")
    names = signed_headers.split(";")
    if "host" not in names or any(n not in headers for n in names):
        raise ApiError("InvalidSignatureException", "SignedHeaders must include host and only headers that were sent.")
    payload_hash = hashlib.sha256(body).hexdigest()
    claimed = headers.get("x-amz-content-sha256")
    if claimed and claimed != payload_hash:
        raise ApiError("InvalidSignatureException", "x-amz-content-sha256 does not match the request body.")
    pairs = sorted((_uri_encode(k), _uri_encode(v)) for k, v in parse_qsl(query, keep_blank_values=True))
    canonical = "\n".join([
        method.upper(),
        path or "/",
        "&".join(f"{k}={v}" for k, v in pairs),
        "".join(f"{n}:{' '.join(headers[n].split())}\n" for n in names),
        signed_headers,
        payload_hash,
    ])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
    key = ("AWS4" + secret).encode("utf-8")
    for part in (day, region, service, "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ApiError("InvalidSignatureException", "The request signature we calculated does not match the "
                       "signature you provided. Check your AWS Secret Access Key and signing method.")
    return access_key, region
