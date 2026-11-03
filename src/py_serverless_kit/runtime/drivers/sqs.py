"""AWS SQS queue driver (JSON protocol, SigV4, standard library only).

API: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/Welcome.html
JSON protocol: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-json-faqs.html

Every action is a ``POST /`` to the service endpoint with
``X-Amz-Target: AmazonSQS.<Action>`` and an ``application/x-amz-json-1.0`` body.
Claimed messages are leased by SQS itself (``VisibilityTimeout``), so a crashed
host loses nothing and ``recover`` has nothing to do.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlsplit

from ._aws import credentials, region_from_host, sign
from ._http import DriverError, check_url, json_body, request

_TARGET = "AmazonSQS."


class SqsQueue:
    def __init__(
        self,
        queue_url: str,
        region: str = "",
        access_key: str = "",
        secret_key: str = "",
        session_token: str = "",
        endpoint: str = "",
        wait_seconds: int = 0,
        message_group_id: str = "pskit",
        timeout: float = 10.0,
        create_queue: bool = False,
    ) -> None:
        # ElasticMQ keeps queues in memory: create the queue when the service says it is missing.
        self.create_queue = create_queue
        self.queue_url = check_url(queue_url, "sqs queue_url")
        self.endpoint = check_url(endpoint, "sqs endpoint") if endpoint else self._service_url(self.queue_url)
        host = urlsplit(self.endpoint).netloc
        self.region = region or region_from_host(urlsplit(self.queue_url).netloc)
        self.access_key, self.secret_key, self.session_token = credentials(access_key, secret_key, session_token)
        if not self.access_key or not self.secret_key:
            raise ValueError(
                "sqs: no credentials; set access_key/secret_key (or *_env), or AWS_ACCESS_KEY_ID and "
                "AWS_SECRET_ACCESS_KEY on the host"
            )
        self.host = host
        self.wait_seconds = max(0, min(int(wait_seconds or 0), 20))
        self.fifo = self.queue_url.endswith(".fifo")
        self.message_group_id = message_group_id or "pskit"
        # A long poll must not trip the HTTP timeout.
        self.timeout = max(float(timeout), self.wait_seconds + 5.0)
        self.name = self.queue_url.rsplit("/", 1)[-1]

    @staticmethod
    def _service_url(queue_url: str) -> str:
        parts = urlsplit(queue_url)
        return f"{parts.scheme}://{parts.netloc}"

    @classmethod
    def from_binding(cls, b: Dict[str, Any], label: str = "") -> SqsQueue:
        url = str(b.get("queue_url") or "")
        if not url:
            account, region = str(b.get("account_id") or ""), str(b.get("region") or "")
            name = str(b.get("name") or label)
            if not (account and region and name):
                raise ValueError("sqs: set queue_url, or account_id + region (+ name, default the resource name)")
            base = str(b.get("endpoint") or f"https://sqs.{region}.amazonaws.com").rstrip("/")
            url = f"{base}/{account}/{name}"
        return cls(
            queue_url=url,
            region=str(b.get("region") or ""),
            access_key=str(b.get("access_key") or ""),
            secret_key=str(b.get("secret_key") or ""),
            session_token=str(b.get("session_token") or ""),
            endpoint=str(b.get("endpoint") or ""),
            wait_seconds=int(b.get("wait_seconds") or 0),
            message_group_id=str(b.get("message_group_id") or "pskit"),
            timeout=float(b.get("timeout") or 10),
            create_queue=str(b.get("create_queue") or "").strip().lower() in ("1", "true", "yes", "on"),
        )

    # ------------------------------------------------------------------ transport
    def call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._call(action, dict(payload, QueueUrl=self.queue_url))
        except DriverError as exc:
            missing = "QueueDoesNotExist" in str(exc) or "NonExistentQueue" in str(exc)
            if not (self.create_queue and missing):
                raise
        attributes = {"FifoQueue": "true"} if self.fifo else {}
        self._call("CreateQueue", {"QueueName": self.name, "Attributes": attributes})
        return self._call(action, dict(payload, QueueUrl=self.queue_url))

    def _call(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(data).encode("utf-8")
        headers = {"content-type": "application/x-amz-json-1.0", "x-amz-target": _TARGET + action}
        if self.session_token:
            headers["x-amz-security-token"] = self.session_token
        signed = sign(
            "POST",
            self.host,
            "/",
            {},
            headers,
            hashlib.sha256(body).hexdigest(),
            self.access_key,
            self.secret_key,
            self.region,
            datetime.now(timezone.utc),
            service="sqs",
        )
        reply = request("sqs", "POST", self.endpoint + "/", signed, body, self.timeout)
        if reply[0] != 200:
            raise DriverError("sqs", reply[0], f"{action} on {self.name}: {_aws_error(reply[2])}")
        result = json_body("sqs", reply)
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------ driver
    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        payload: Dict[str, Any] = {"MessageBody": body}
        attrs = {
            str(k): {"DataType": "String", "StringValue": str(v)} for k, v in (attributes or {}).items() if str(v) != ""
        }
        if attrs:
            payload["MessageAttributes"] = attrs
        if self.fifo:
            payload["MessageGroupId"] = self.message_group_id
            payload["MessageDeduplicationId"] = uuid.uuid4().hex
        return str(self.call("SendMessage", payload).get("MessageId") or "")

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        claimed: List[Dict[str, Any]] = []
        want = max(1, int(batch))
        while len(claimed) < want:
            result = self.call(
                "ReceiveMessage",
                {
                    "MaxNumberOfMessages": min(10, want - len(claimed)),
                    "VisibilityTimeout": max(0, min(int(visibility), 43200)),
                    # Long-poll only for the first request of a batch.
                    "WaitTimeSeconds": self.wait_seconds if not claimed else 0,
                    "AttributeNames": ["ApproximateReceiveCount", "SentTimestamp"],
                    "MessageSystemAttributeNames": ["ApproximateReceiveCount", "SentTimestamp"],
                    "MessageAttributeNames": ["All"],
                },
            )
            messages = result.get("Messages") or []
            for msg in messages:
                system = msg.get("Attributes") or {}
                attrs = {
                    k: v.get("StringValue", v.get("BinaryValue"))
                    for k, v in (msg.get("MessageAttributes") or {}).items()
                    if isinstance(v, dict)
                }
                sent = system.get("SentTimestamp")
                claimed.append(
                    {
                        "id": str(msg.get("MessageId")),
                        "body": msg.get("Body", ""),
                        "attributes": attrs,
                        "receives": int(system.get("ApproximateReceiveCount") or 1),
                        "enqueued_at": int(sent) / 1000.0 if sent else now,
                        "_handle": msg.get("ReceiptHandle"),
                    }
                )
            if len(messages) == 0:
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
        done: List[str] = []
        for msg in claimed:
            if msg["id"] not in failed_ids:
                done.append(msg["_handle"])
            elif dead_letter is not None and int(msg.get("receives") or 0) >= max_receive:
                dead_letter.submit(str(msg.get("body") or ""), dict(msg.get("attributes") or {}))
                done.append(msg["_handle"])
            else:
                self.call("ChangeMessageVisibility", {"ReceiptHandle": msg["_handle"], "VisibilityTimeout": 0})
        for start in range(0, len(done), 10):
            chunk = done[start : start + 10]
            result = self.call(
                "DeleteMessageBatch",
                {"Entries": [{"Id": str(i), "ReceiptHandle": handle} for i, handle in enumerate(chunk)]},
            )
            failed = result.get("Failed") or []
            if failed:
                first = failed[0]
                raise DriverError("sqs", 0, f"could not delete {len(failed)} message(s): {first.get('Message')}")

    def depth(self) -> int:
        result = self.call("GetQueueAttributes", {"AttributeNames": ["ApproximateNumberOfMessages"]})
        try:
            return int(str((result.get("Attributes") or {}).get("ApproximateNumberOfMessages")))
        except (TypeError, ValueError):
            return -1

    def recover(self, now: float, visibility: float) -> None:
        return None  # SQS releases expired leases itself


def _aws_error(raw: bytes) -> str:
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return raw[:300].decode("utf-8", "replace")
    kind = str(data.get("__type") or data.get("code") or "").rsplit("#", 1)[-1]
    message = data.get("message") or data.get("Message") or ""
    return f"{kind}: {message}".strip(": ")
