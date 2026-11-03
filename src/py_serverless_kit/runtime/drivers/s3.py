"""S3-compatible object storage for the on-premises host (standard library only).

Works with AWS S3, MinIO, Ceph RGW, SeaweedFS, Garage and similar. Requests are
signed with AWS Signature Version 4. With an ``endpoint`` (self-hosted servers)
``path_style`` defaults to on: ``<endpoint>/<bucket>/<key>``. Without one the
driver talks to ``https://s3.<region>.amazonaws.com`` in virtual-host style:
``<bucket>.s3.<region>.amazonaws.com/<key>``.

API: https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html
"""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET  # noqa: S405 - parses responses from the configured endpoint
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from ._aws import EMPTY_SHA256, canonical_query, sign, uri_encode

__all__ = ["EMPTY_SHA256", "S3Error", "S3Storage", "canonical_query", "sign", "uri_encode"]


class S3Error(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"S3 request failed ({status}): {message}")


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# `s3.eu-west-1.amazonaws.com` / `s3-eu-west-1.amazonaws.com`: the region part of a regional AWS endpoint.
_AWS_REGIONAL = re.compile(r"^(s3[.-])[a-z]{2}(?:-[a-z]+)+-\d(\.amazonaws\.com(?::\d+)?)$")
_REGION_TAG = re.compile(r"<Region>([A-Za-z0-9-]+)</Region>")
_DEFAULT_REGIONS = ("", "us-east-1", "auto")
_LOCATION = (
    '<CreateBucketConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
    "<LocationConstraint>{}</LocationConstraint></CreateBucketConfiguration>"
)


class S3Storage:
    """:class:`StorageDriver` on one bucket (optionally below ``prefix``)."""

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        region: str = "us-east-1",
        access_key: str = "",
        secret_key: str = "",
        session_token: str = "",
        prefix: str = "",
        path_style: bool = True,
        timeout: float = 30.0,
    ) -> None:
        parts = urlsplit(endpoint)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError(f"S3 endpoint must be an http(s) URL, got {endpoint!r}")
        self.scheme = parts.scheme
        self.netloc = parts.netloc
        self.base_path = parts.path.rstrip("/")
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        self.path_style = path_style
        self.timeout = timeout

    # ------------------------------------------------------------ http
    def _target(self, key: str) -> Tuple[str, str]:
        encoded = uri_encode(key, keep_slash=True) if key else ""
        # A dotted bucket name does not match the endpoint's wildcard TLS certificate: path-style instead.
        if self.path_style or (self.scheme == "https" and "." in self.bucket):
            return self.netloc, f"{self.base_path}/{uri_encode(self.bucket)}/{encoded}"
        return f"{self.bucket}.{self.netloc}", f"{self.base_path}/{encoded}"

    def _moved(self, status: int, headers: Dict[str, str], body: bytes) -> bool:
        """The bucket lives in another region (AWS answers 301 / 400 naming it): sign for that region, and on a
        regional AWS endpoint talk to that region's endpoint. True when the request is worth repeating."""
        if status not in (301, 307, 400):
            return False
        region = headers.get("x-amz-bucket-region", "")
        if not region:
            match = _REGION_TAG.search(body[:2000].decode("utf-8", "replace"))
            region = match.group(1) if match else ""
        if not region or region == self.region:
            return False
        self.region = region
        self.netloc = _AWS_REGIONAL.sub(lambda m: f"{m.group(1)}{region}{m.group(2)}", self.netloc)
        return True

    def request(
        self,
        method: str,
        key: str = "",
        query: Optional[Dict[str, str]] = None,
        body: bytes = b"",
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        reply = self._send(method, key, query, body, headers)
        if self._moved(*reply):
            reply = self._send(method, key, query, body, headers)
        return reply

    def _send(
        self,
        method: str,
        key: str = "",
        query: Optional[Dict[str, str]] = None,
        body: bytes = b"",
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        host, path = self._target(key)
        query = dict(query or {})
        payload_hash = hashlib.sha256(body).hexdigest()
        hdrs = dict(headers or {})
        if self.session_token:
            hdrs["x-amz-security-token"] = self.session_token
        if self.access_key:
            hdrs = sign(
                method,
                host,
                path,
                query,
                hdrs,
                payload_hash,
                self.access_key,
                self.secret_key,
                self.region,
                datetime.now(timezone.utc),
            )
        else:
            hdrs["host"] = host
        url = f"{self.scheme}://{host}{path}" + (f"?{canonical_query(query)}" if query else "")
        req = urllib.request.Request(url, data=body if method in ("PUT", "POST") else None, method=method)  # noqa: S310
        for name, value in hdrs.items():
            if name != "host":
                req.add_header(name, value)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - operator-configured endpoint
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()
        except urllib.error.URLError as exc:
            raise S3Error(0, f"{url} is unreachable: {exc.reason}") from exc

    @staticmethod
    def _check(status: int, body: bytes, ok: Tuple[int, ...] = (200,)) -> None:
        if status not in ok:
            raise S3Error(status, body[:300].decode("utf-8", "replace"))

    # ------------------------------------------------------------ driver
    def scan(self) -> Dict[str, Tuple[str, int]]:
        """Every object: ListObjectsV2, or the original ListObjects (``marker``) on stores without V2."""
        found: Dict[str, Tuple[str, int]] = {}
        token: Optional[str] = None
        marker = ""
        v2 = True
        while True:
            query = {"list-type": "2"} if v2 else {}
            if self.prefix:
                query["prefix"] = self.prefix
            if token:
                query["continuation-token"] = token
            if marker:
                query["marker"] = marker
            status, _headers, body = self.request("GET", "", query)
            if v2 and status in (400, 501) and not found and not token:
                v2 = False  # e.g. an older Ceph RGW or a gateway that only knows ListObjects
                continue
            self._check(status, body)
            root = ET.fromstring(body)  # noqa: S314 - trusted, operator-configured endpoint
            token = None
            truncated = False
            last = ""
            for child in root:
                tag = _strip_ns(child.tag)
                if tag == "Contents":
                    fields = {_strip_ns(c.tag): (c.text or "") for c in child}
                    key = fields.get("Key", "")
                    last = key or last
                    if not key or key.endswith("/"):
                        continue
                    rel = key[len(self.prefix) :] if self.prefix and key.startswith(self.prefix) else key
                    found[rel] = (fields.get("ETag", "").strip('"'), int(fields.get("Size") or 0))
                elif tag == "IsTruncated":
                    truncated = (child.text or "").strip().lower() == "true"
                elif tag in ("NextContinuationToken", "NextMarker"):
                    token = child.text or None
            if not truncated:
                return found
            if v2 and token:
                continue
            # ListObjects pages by marker: NextMarker when the store sends it, else the last key of the page.
            next_marker = (token if not v2 else None) or last
            token = None
            if not next_marker or next_marker == marker:
                return found
            v2, marker = False, next_marker

    def create_bucket(self) -> int:
        """Create the bucket; the HTTP status (409 / 200 when it already exists).

        Outside us-east-1 AWS (and stores that copy it) wants the region as LocationConstraint; stores that refuse
        one get a plain request. A key allowed to use but not to create the bucket gets 403: 200 if it is there.
        """
        status = 0
        if self.region not in _DEFAULT_REGIONS:
            status = self.request("PUT", body=_LOCATION.format(self.region).encode("utf-8"))[0]
        if status == 0 or status == 400:
            status = self.request("PUT")[0]
        if status >= 400 and status != 409 and self.request("HEAD")[0] == 200:
            return 200
        return status

    def put(self, key: str, data: bytes) -> None:
        status, _headers, body = self.request("PUT", self.prefix + key, body=data)
        self._check(status, body)

    def get(self, key: str) -> bytes:
        status, _headers, body = self.request("GET", self.prefix + key)
        if status == 404:
            raise KeyError(key)
        self._check(status, body)
        return body

    def delete(self, key: str) -> bool:
        status, _headers, body = self.request("HEAD", self.prefix + key)
        if status == 404:
            return False
        self._check(status, body)
        status, _headers, body = self.request("DELETE", self.prefix + key)
        self._check(status, body, (200, 204))
        return True

    def keys(self) -> List[str]:
        return sorted(self.scan())
