"""AWS Signature Version 4 and credential lookup, shared by the ``s3`` and ``sqs`` drivers.

https://docs.aws.amazon.com/IAM/latest/UserGuide/create-signed-request.html
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import datetime
from typing import Dict, Mapping, Tuple
from urllib.parse import quote

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def uri_encode(text: str, keep_slash: bool = False) -> str:
    return quote(text, safe="-_.~/" if keep_slash else "-_.~")


def canonical_query(params: Mapping[str, str]) -> str:
    return "&".join(f"{uri_encode(k)}={uri_encode(v)}" for k, v in sorted(params.items()))


def sign(
    method: str,
    host: str,
    path: str,
    query: Mapping[str, str],
    headers: Mapping[str, str],
    payload_sha256: str,
    access_key: str,
    secret_key: str,
    region: str,
    when: datetime,
    service: str = "s3",
) -> Dict[str, str]:
    """Return ``headers`` plus ``host``, ``x-amz-date``, ``x-amz-content-sha256`` and ``Authorization``.

    ``path`` must already be URI-encoded (S3 does not encode it twice).
    """
    amz_date = when.strftime("%Y%m%dT%H%M%SZ")
    day = when.strftime("%Y%m%d")
    out = {k.lower(): str(v).strip() for k, v in headers.items()}
    out["host"] = host
    out["x-amz-date"] = amz_date
    out["x-amz-content-sha256"] = payload_sha256
    names = sorted(out)
    canonical = "\n".join(
        [
            method.upper(),
            path or "/",
            canonical_query(query),
            "".join(f"{n}:{out[n]}\n" for n in names),
            ";".join(names),
            payload_sha256,
        ]
    )
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode("utf-8"), day), region), service), "aws4_request")
    signature = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    out["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={';'.join(names)}, Signature={signature}"
    )
    return out


def credentials(access_key: str = "", secret_key: str = "", session_token: str = "") -> Tuple[str, str, str]:
    """Explicit keys win; otherwise the standard ``AWS_*`` environment variables (both or neither)."""
    if access_key or secret_key:
        return access_key, secret_key, session_token
    return (
        os.environ.get("AWS_ACCESS_KEY_ID", ""),
        os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        session_token or os.environ.get("AWS_SESSION_TOKEN", ""),
    )


_REGION_HOST = re.compile(r"^(?:[\w-]+\.)?(?:sqs|s3)[.-]([a-z]{2}(?:-[a-z]+)+-\d)\.amazonaws\.com", re.I)


def region_from_host(host: str, default: str = "us-east-1") -> str:
    """``sqs.eu-west-1.amazonaws.com`` -> ``eu-west-1`` (the legacy ``queue.amazonaws.com`` is us-east-1)."""
    match = _REGION_HOST.match(host.split(":")[0])
    return match.group(1) if match else default
