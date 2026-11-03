"""Azure Storage Queue and Blob drivers (REST, standard library only).

Auth, in order of preference: a ``connection_string`` (``AccountName``/``AccountKey``,
``QueueEndpoint``/``BlobEndpoint``, ``SharedAccessSignature``, or
``UseDevelopmentStorage=true`` for Azurite), a ``sas_token``, or an
``account_key`` (Shared Key signing).

* Shared Key: https://learn.microsoft.com/en-us/rest/api/storageservices/authorize-with-shared-key
* Queue service: https://learn.microsoft.com/en-us/rest/api/storageservices/queue-service-rest-api
* Blob service: https://learn.microsoft.com/en-us/rest/api/storageservices/blob-service-rest-api
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import xml.etree.ElementTree as ET  # noqa: S405 - parses responses from the configured endpoint
from email.utils import formatdate
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urlencode, urlsplit
from xml.sax.saxutils import escape

from ._http import DriverError, check, check_url, request

API_VERSION = "2020-10-02"
# Azurite's documented, public development account.
DEV_ACCOUNT = "devstoreaccount1"
DEV_KEY = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
DEV_ENDPOINTS = {"blob": "http://127.0.0.1:10000/devstoreaccount1", "queue": "http://127.0.0.1:10001/devstoreaccount1"}


def parse_connection_string(text: str) -> Dict[str, str]:
    parts: Dict[str, str] = {}
    for item in str(text).split(";"):
        key, sep, value = item.strip().partition("=")
        if sep:
            parts[key.strip()] = value.strip()
    if parts.get("UseDevelopmentStorage", "").lower() == "true":
        parts.setdefault("AccountName", DEV_ACCOUNT)
        parts.setdefault("AccountKey", DEV_KEY)
        parts.setdefault("BlobEndpoint", DEV_ENDPOINTS["blob"])
        parts.setdefault("QueueEndpoint", DEV_ENDPOINTS["queue"])
    return parts


def string_to_sign(method: str, account: str, path: str, query: Dict[str, str], headers: Dict[str, str]) -> str:
    """Shared Key string-to-sign for the Blob, Queue and File services (version 2015-02-21 and later)."""
    h = {k.lower(): str(v).strip() for k, v in headers.items()}
    length = h.get("content-length", "")
    standard = [
        method.upper(),
        h.get("content-encoding", ""),
        h.get("content-language", ""),
        "" if length in ("", "0") else length,
        h.get("content-md5", ""),
        h.get("content-type", ""),
        "",  # Date: x-ms-date is used instead
        h.get("if-modified-since", ""),
        h.get("if-match", ""),
        h.get("if-none-match", ""),
        h.get("if-unmodified-since", ""),
        h.get("range", ""),
    ]
    canonical_headers = "".join(f"{k}:{h[k]}\n" for k in sorted(h) if k.startswith("x-ms-"))
    resource = f"/{account}{path or '/'}"
    grouped: Dict[str, List[str]] = {}
    for key, value in query.items():
        grouped.setdefault(key.lower(), []).append(value)
    for key in sorted(grouped):
        resource += f"\n{key}:{','.join(sorted(grouped[key]))}"
    return "\n".join(standard) + "\n" + canonical_headers + resource


def shared_key(account: str, key: str, method: str, path: str, query: Dict[str, str], headers: Dict[str, str]) -> str:
    try:
        secret = base64.b64decode(key)
    except (binascii.Error, ValueError):
        raise ValueError("azure account_key must be base64 (copy it from the storage account's Access keys)") from None
    digest = hmac.new(secret, string_to_sign(method, account, path, query, headers).encode("utf-8"), hashlib.sha256)
    return f"SharedKey {account}:{base64.b64encode(digest.digest()).decode('ascii')}"


class AzureAuth:
    """Where a storage service lives and how to sign requests to it."""

    def __init__(self, service: str, b: Dict[str, Any]) -> None:
        self.service = service  # "queue" | "blob"
        conn = parse_connection_string(str(b.get("connection_string") or "")) if b.get("connection_string") else {}
        self.account = str(b.get("account") or conn.get("AccountName") or "")
        self.key = str(b.get("account_key") or conn.get("AccountKey") or "")
        self.sas = str(b.get("sas_token") or conn.get("SharedAccessSignature") or "").lstrip("?")
        endpoint = str(b.get("endpoint") or conn.get(f"{service.capitalize()}Endpoint") or "")
        if not endpoint:
            if not self.account:
                raise ValueError(f"azure_{service}: set account (or connection_string / endpoint)")
            suffix = conn.get("EndpointSuffix") or "core.windows.net"
            protocol = conn.get("DefaultEndpointsProtocol") or "https"
            endpoint = f"{protocol}://{self.account}.{service}.{suffix}"
        self.endpoint = check_url(endpoint, f"azure_{service} endpoint")
        if not self.account:
            self.account = urlsplit(self.endpoint).netloc.split(".")[0]
        if not self.key and not self.sas:
            raise ValueError(f"azure_{service}: set account_key, sas_token or connection_string (or their *_env)")
        self.timeout = float(b.get("timeout") or 10)

    def call(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        base = urlsplit(self.endpoint)
        full_path = base.path.rstrip("/") + path
        params = dict(query or {})
        hdrs = {"x-ms-version": API_VERSION, "x-ms-date": formatdate(usegmt=True)}
        hdrs.update(headers or {})
        if body is not None:
            hdrs["content-length"] = str(len(body))
            hdrs.setdefault("content-type", "application/octet-stream")
        url_query = urlencode(params, quote_via=quote)
        if self.key and not self.sas:
            hdrs["authorization"] = shared_key(self.account, self.key, method, full_path, params, hdrs)
        elif self.sas:
            url_query = "&".join(q for q in (url_query, self.sas) if q)
        url = f"{base.scheme}://{base.netloc}{full_path}" + (f"?{url_query}" if url_query else "")
        hdrs.pop("content-length", None)  # urllib sets it from the body
        return request(f"azure_{self.service}", method, url, hdrs, body, self.timeout)


def _text(node: Optional[ET.Element], name: str) -> str:
    if node is None:
        return ""
    child = node.find(name)
    return (child.text or "") if child is not None else ""


class AzureQueue:
    """:class:`QueueDriver` on one Azure Storage queue. Leases are native (``visibilitytimeout``)."""

    def __init__(self, auth: AzureAuth, queue: str, encoding: str = "base64") -> None:
        if not queue:
            raise ValueError("azure_queue: set queue (defaults to the resource name)")
        if encoding not in ("base64", "text"):
            raise ValueError("azure_queue: message_encoding must be base64 or text")
        self.auth = auth
        self.queue = queue
        self.encoding = encoding

    @classmethod
    def from_binding(cls, b: Dict[str, Any], label: str = "") -> AzureQueue:
        return cls(AzureAuth("queue", b), str(b.get("queue") or label), str(b.get("message_encoding") or "base64"))

    def _path(self, suffix: str = "") -> str:
        return "/" + quote(self.queue, safe="") + suffix

    def _encode(self, text: str) -> str:
        if self.encoding == "base64":
            return base64.b64encode(text.encode("utf-8")).decode("ascii")
        return text

    def _decode(self, text: str) -> str:
        if self.encoding != "base64":
            return text
        try:
            return base64.b64decode(text, validate=True).decode("utf-8")
        except (binascii.Error, ValueError):
            return text  # a producer that did not encode

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        # Azure queue messages have no attributes; they are dropped.
        xml = f"<QueueMessage><MessageText>{escape(self._encode(body))}</MessageText></QueueMessage>"
        reply = self.auth.call(
            "POST", self._path("/messages"), body=xml.encode("utf-8"), headers={"content-type": "application/xml"}
        )
        root = ET.fromstring(check("azure_queue", reply, (201,)))  # noqa: S314
        return _text(root.find("QueueMessage"), "MessageId")

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        claimed: List[Dict[str, Any]] = []
        want = max(1, int(batch))
        while len(claimed) < want:
            query = {
                "numofmessages": str(min(32, want - len(claimed))),
                "visibilitytimeout": str(max(1, min(int(visibility), 604800))),
            }
            reply = self.auth.call("GET", self._path("/messages"), query)
            root = ET.fromstring(check("azure_queue", reply) or b"<QueueMessagesList/>")  # noqa: S314
            messages = root.findall("QueueMessage")
            for msg in messages:
                claimed.append(
                    {
                        "id": _text(msg, "MessageId"),
                        "body": self._decode(_text(msg, "MessageText")),
                        "attributes": {},
                        "receives": int(_text(msg, "DequeueCount") or 1),
                        "enqueued_at": now,
                        "_pop": _text(msg, "PopReceipt"),
                    }
                )
            if not messages:
                break
        return claimed

    def settle(
        self,
        claimed: List[Dict[str, Any]],
        failed_ids: Set[str],
        max_receive: int,
        dead_letter: Optional[Any],
        now: float,
    ) -> None:
        for msg in claimed:
            path = self._path("/messages/" + quote(msg["id"], safe=""))
            if msg["id"] in failed_ids and not (dead_letter is not None and msg["receives"] >= max_receive):
                reply = self.auth.call(
                    "PUT",
                    path,
                    {"popreceipt": msg["_pop"], "visibilitytimeout": "0"},
                    body=b"",
                    headers={"content-type": "application/xml"},
                )
                check("azure_queue", reply, (204,))
                continue
            if msg["id"] in failed_ids and dead_letter is not None:
                dead_letter.submit(str(msg.get("body") or ""), {})
            reply = self.auth.call("DELETE", path, {"popreceipt": msg["_pop"]})
            check("azure_queue", reply, (204, 404))

    def depth(self) -> int:
        reply = self.auth.call("GET", self._path(), {"comp": "metadata"})
        check("azure_queue", reply)
        try:
            return int(reply[1].get("x-ms-approximate-messages-count", "-1"))
        except ValueError:
            return -1

    def recover(self, now: float, visibility: float) -> None:
        return None  # visibility timeouts expire on the service


class AzureBlobStorage:
    """:class:`StorageDriver` on one blob container (optionally below ``prefix``)."""

    def __init__(self, auth: AzureAuth, container: str, prefix: str = "") -> None:
        if not container:
            raise ValueError("azure_blob: set container (defaults to the resource name)")
        self.auth = auth
        self.container = container
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""

    @classmethod
    def from_binding(cls, b: Dict[str, Any], label: str = "") -> AzureBlobStorage:
        return cls(AzureAuth("blob", b), str(b.get("container") or label), str(b.get("prefix") or ""))

    def _path(self, key: str = "") -> str:
        path = "/" + quote(self.container, safe="")
        return path + ("/" + quote(self.prefix + key, safe="/~-._") if key else "")

    def scan(self) -> Dict[str, Tuple[str, int]]:
        found: Dict[str, Tuple[str, int]] = {}
        marker = ""
        while True:
            query = {"restype": "container", "comp": "list"}
            if self.prefix:
                query["prefix"] = self.prefix
            if marker:
                query["marker"] = marker
            root = ET.fromstring(check("azure_blob", self.auth.call("GET", self._path(), query)))  # noqa: S314
            for blob in root.iter("Blob"):
                name = _text(blob, "Name")
                props = blob.find("Properties")
                rel = name[len(self.prefix) :] if self.prefix and name.startswith(self.prefix) else name
                if rel and not rel.endswith("/"):
                    found[rel] = (_text(props, "Etag").strip('"'), int(_text(props, "Content-Length") or 0))
            marker = _text(root, "NextMarker")
            if not marker:
                return found

    def put(self, key: str, data: bytes) -> None:
        reply = self.auth.call("PUT", self._path(key), body=data, headers={"x-ms-blob-type": "BlockBlob"})
        check("azure_blob", reply, (201,))

    def get(self, key: str) -> bytes:
        reply = self.auth.call("GET", self._path(key))
        if reply[0] == 404:
            raise KeyError(key)
        return check("azure_blob", reply)

    def delete(self, key: str) -> bool:
        reply = self.auth.call("DELETE", self._path(key))
        if reply[0] == 404:
            return False
        check("azure_blob", reply, (202,))
        return True


__all__ = ["AzureAuth", "AzureBlobStorage", "AzureQueue", "DriverError", "parse_connection_string", "string_to_sign"]
