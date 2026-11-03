"""Alibaba Cloud MNS (Message Service) queue driver (REST + XML, standard library only).

* API overview / signing: https://www.alibabacloud.com/help/en/mns/developer-reference/request-signatures
* Queue messages: https://www.alibabacloud.com/help/en/mns/developer-reference/api-mns-open-2022-01-19-dir-queue-message/

``Authorization: MNS <AccessKeyId>:<Signature>`` where the signature is
base64(HMAC-SHA1(AccessKeySecret, VERB\\nContent-MD5\\nContent-Type\\nDate\\n
<x-mns-* headers>\\n<resource>)). Leases are native: a received message stays
invisible until its visibility timeout ends, so ``recover`` is a no-op.
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

from ._http import DriverError, check_url, request

API_VERSION = "2015-06-06"
_CONTENT_TYPE = "text/xml;charset=utf-8"
_NS = "http://mns.aliyuncs.com/doc/v1/"


def string_to_sign(
    method: str, content_md5: str, content_type: str, date: str, headers: Dict[str, str], resource: str
) -> str:
    mns = "".join(
        f"{k}:{v}\n"
        for k, v in sorted((k.lower(), str(v).strip()) for k, v in headers.items())
        if k.startswith("x-mns-")
    )
    return f"{method.upper()}\n{content_md5}\n{content_type}\n{date}\n{mns}{resource}"


def signature(secret: str, text: str) -> str:
    return base64.b64encode(hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha1).digest()).decode()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _fields(node: ET.Element) -> Dict[str, str]:
    return {_local(child.tag): (child.text or "") for child in node}


class MnsQueue:
    def __init__(
        self,
        endpoint: str,
        queue: str,
        access_key: str,
        secret_key: str,
        wait_seconds: int = 0,
        encoding: str = "base64",
        timeout: float = 10.0,
    ) -> None:
        if not queue:
            raise ValueError("mns: set queue (defaults to the resource name)")
        if not access_key or not secret_key:
            raise ValueError("mns: set access_key and secret_key (or *_env)")
        if encoding not in ("base64", "text"):
            raise ValueError("mns: message_encoding must be base64 or text")
        self.endpoint = check_url(endpoint, "mns endpoint")
        self.queue = queue
        self.access_key = access_key
        self.secret_key = secret_key
        self.wait_seconds = max(0, min(int(wait_seconds or 0), 30))
        self.encoding = encoding
        self.timeout = max(float(timeout), self.wait_seconds + 5.0)

    @classmethod
    def from_binding(cls, b: Dict[str, Any], label: str = "") -> MnsQueue:
        endpoint = str(b.get("endpoint") or "")
        if not endpoint:
            account, region = str(b.get("account_id") or ""), str(b.get("region") or "")
            if not (account and region):
                raise ValueError("mns: set endpoint, or account_id + region")
            endpoint = f"https://{account}.mns.{region}.aliyuncs.com"
        return cls(
            endpoint,
            str(b.get("queue") or label),
            str(b.get("access_key") or ""),
            str(b.get("secret_key") or ""),
            int(b.get("wait_seconds") or 0),
            str(b.get("message_encoding") or "base64"),
            float(b.get("timeout") or 10),
        )

    # ------------------------------------------------------------------ transport
    def call(
        self, method: str, suffix: str, query: Optional[Dict[str, str]] = None, body: Optional[bytes] = None
    ) -> Tuple[int, Dict[str, str], bytes]:
        path = urlsplit(self.endpoint).path.rstrip("/") + "/queues/" + quote(self.queue, safe="") + suffix
        resource = path + (f"?{urlencode(query, quote_via=quote)}" if query else "")
        date = formatdate(usegmt=True)
        headers = {"x-mns-version": API_VERSION, "date": date, "content-type": _CONTENT_TYPE}
        text = string_to_sign(method, "", _CONTENT_TYPE, date, headers, resource)
        headers["authorization"] = f"MNS {self.access_key}:{signature(self.secret_key, text)}"
        base = urlsplit(self.endpoint)
        return request("mns", method, f"{base.scheme}://{base.netloc}{resource}", headers, body, self.timeout)

    @staticmethod
    def _error(reply: Tuple[int, Dict[str, str], bytes]) -> Tuple[str, str]:
        try:
            fields = _fields(ET.fromstring(reply[2]))  # noqa: S314
        except ET.ParseError:
            return "", reply[2][:200].decode("utf-8", "replace")
        return fields.get("Code", ""), fields.get("Message", "")

    def _check(self, reply: Tuple[int, Dict[str, str], bytes], ok: Tuple[int, ...]) -> bytes:
        if reply[0] not in ok:
            code, message = self._error(reply)
            raise DriverError("mns", reply[0], f"{self.queue}: {code} {message}".strip())
        return reply[2]

    def _encode(self, text: str) -> str:
        return base64.b64encode(text.encode("utf-8")).decode("ascii") if self.encoding == "base64" else text

    def _decode(self, text: str) -> str:
        if self.encoding != "base64":
            return text
        try:
            return base64.b64decode(text, validate=True).decode("utf-8")
        except (binascii.Error, ValueError):
            return text

    # ------------------------------------------------------------------ driver
    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        # MNS queue messages carry no attributes; they are dropped.
        xml = (
            f'<?xml version="1.0" encoding="UTF-8"?><Message xmlns="{_NS}">'
            f"<MessageBody>{escape(self._encode(body))}</MessageBody><DelaySeconds>0</DelaySeconds>"
            "<Priority>8</Priority></Message>"
        )
        root = ET.fromstring(self._check(self.call("POST", "/messages", body=xml.encode("utf-8")), (201,)))  # noqa: S314
        return _fields(root).get("MessageId", "")

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        claimed: List[Dict[str, Any]] = []
        want = max(1, int(batch))
        while len(claimed) < want:
            query = {"numOfMessages": str(min(16, want - len(claimed)))}
            if self.wait_seconds and not claimed:
                query["waitseconds"] = str(self.wait_seconds)
            reply = self.call("GET", "/messages", query)
            if reply[0] == 404 and self._error(reply)[0] == "MessageNotExist":
                break
            root = ET.fromstring(self._check(reply, (200,)))  # noqa: S314
            nodes = [root] if _local(root.tag) == "Message" else [n for n in root if _local(n.tag) == "Message"]
            for node in nodes:
                f = _fields(node)
                handle = self._lease(f.get("ReceiptHandle", ""), visibility)
                enqueued = f.get("EnqueueTime", "")
                claimed.append(
                    {
                        "id": f.get("MessageId", ""),
                        "body": self._decode(f.get("MessageBody", "")),
                        "attributes": {},
                        "receives": int(f.get("DequeueCount") or 1),
                        "enqueued_at": int(enqueued) / 1000.0 if enqueued.isdigit() else now,
                        "_handle": handle,
                    }
                )
            if not nodes:
                break
        return claimed

    def _lease(self, handle: str, seconds: float) -> str:
        """Set the visibility timeout; MNS returns a new receipt handle."""
        query = {"receiptHandle": handle, "visibilityTimeout": str(max(1, min(int(seconds), 43200)))}
        root = ET.fromstring(self._check(self.call("PUT", "/messages", query), (200,)))  # noqa: S314
        return _fields(root).get("ReceiptHandle", handle)

    def settle(
        self,
        claimed: List[Dict[str, Any]],
        failed_ids: Set[str],
        max_receive: int,
        dead_letter: Optional[Any],
        now: float,
    ) -> None:
        for msg in claimed:
            failed = msg["id"] in failed_ids
            if failed and not (dead_letter is not None and msg["receives"] >= max_receive):
                self._lease(msg["_handle"], 1)  # 1 second is the minimum: visible again almost at once
                continue
            if failed and dead_letter is not None:
                dead_letter.submit(str(msg.get("body") or ""), {})
            self._check(self.call("DELETE", "/messages", {"ReceiptHandle": msg["_handle"]}), (204,))

    def depth(self) -> int:
        root = ET.fromstring(self._check(self.call("GET", ""), (200,)))  # noqa: S314
        try:
            return int(_fields(root).get("ActiveMessages", "-1"))
        except ValueError:
            return -1

    def recover(self, now: float, visibility: float) -> None:
        return None
