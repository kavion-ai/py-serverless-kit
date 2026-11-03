"""Google Cloud Pub/Sub (pull) and Cloud Storage drivers (REST, standard library only).

OAuth access token, in order: ``access_token`` (or ``access_token_env``), the
output of ``token_command`` (e.g. ``["gcloud", "auth", "print-access-token"]``,
cached for 45 minutes), or the GCE/GKE metadata server. Emulators need none:
set ``emulator: true`` with ``endpoint``, or ``PUBSUB_EMULATOR_HOST`` /
``STORAGE_EMULATOR_HOST`` on the host.

* Pub/Sub REST: https://cloud.google.com/pubsub/docs/reference/rest
* Cloud Storage JSON API: https://cloud.google.com/storage/docs/json_api/v1
* Metadata server token: https://cloud.google.com/compute/docs/access/authenticate-workloads
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urlencode

from ._http import DriverError, check, check_url, json_body, request

METADATA_TOKEN = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"  # noqa: S105 - a URL, not a secret
_COMMAND_TTL = 45 * 60.0


class TokenSource:
    def __init__(self, service: str, b: Dict[str, Any], emulator: bool) -> None:
        self.service = service
        self.emulator = emulator
        self.static = str(b.get("access_token") or "")
        raw = b.get("token_command")
        if isinstance(raw, str):
            raw = shlex.split(raw)
        if raw is not None and not (isinstance(raw, list) and raw and all(isinstance(x, str) for x in raw)):
            raise ValueError(f"{service}: token_command must be a list of strings (or one command line)")
        self.command: Optional[List[str]] = list(raw) if raw else None
        self._token = ""
        self._expires = 0.0
        self._lock = threading.Lock()

    def headers(self) -> Dict[str, str]:
        if self.emulator:
            return {}
        return {"authorization": f"Bearer {self.token()}"}

    def token(self) -> str:
        if self.static:
            return self.static
        with self._lock:
            if self._token and time.time() < self._expires:
                return self._token
            if self.command:
                self._token, ttl = self._from_command(), _COMMAND_TTL
            else:
                self._token, ttl = self._from_metadata()
            self._expires = time.time() + max(30, ttl - 60)
            return self._token

    def _from_command(self) -> str:
        assert self.command is not None
        try:
            done = subprocess.run(  # noqa: S603 - operator-configured command, no shell
                self.command, capture_output=True, text=True, timeout=60, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise DriverError(self.service, 0, f"token_command {self.command[0]!r} failed: {exc}") from exc
        token = done.stdout.strip().splitlines()[-1].strip() if done.stdout.strip() else ""
        if done.returncode != 0 or not token:
            raise DriverError(self.service, 0, f"token_command exited {done.returncode}: {done.stderr.strip()[:200]}")
        return token

    def _from_metadata(self) -> Tuple[str, float]:
        try:
            reply = request(self.service, "GET", METADATA_TOKEN, {"metadata-flavor": "Google"}, timeout=3)
        except DriverError:
            raise DriverError(
                self.service,
                0,
                "no credentials: set access_token(_env) or token_command, or run on GCE/GKE (metadata server)",
            ) from None
        data = json_body(self.service, reply)
        return str(data.get("access_token") or ""), float(data.get("expires_in") or 300)


def _emulator(b: Dict[str, Any], env_var: str) -> Tuple[str, bool]:
    """``(endpoint, emulator)`` from the binding or the conventional emulator variable."""
    if b.get("endpoint"):
        return check_url(str(b["endpoint"]), "endpoint"), bool(b.get("emulator"))
    host = os.environ.get(env_var, "")
    if host:
        return check_url(host if "://" in host else f"http://{host}", env_var), True
    return "", False


def _qualify(value: str, kind: str, project: str, service: str) -> str:
    if value.startswith("projects/"):
        return value
    if not project:
        raise ValueError(f"{service}: {kind} {value!r} needs `project` (or use projects/<p>/{kind}s/<name>)")
    return f"projects/{project}/{kind}s/{value}"


class PubSubQueue:
    """:class:`QueueDriver` on one Pub/Sub pull subscription (``submit`` publishes to ``topic``)."""

    def __init__(
        self,
        subscription: str,
        tokens: TokenSource,
        endpoint: str = "https://pubsub.googleapis.com",
        topic: str = "",
        return_immediately: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self.subscription = subscription
        self.topic = topic
        self.tokens = tokens
        self.endpoint = check_url(endpoint, "pubsub endpoint")
        self.return_immediately = return_immediately
        self.timeout = timeout
        self._attempts: Dict[str, int] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_binding(cls, b: Dict[str, Any], label: str = "") -> PubSubQueue:
        endpoint, emulator = _emulator(b, "PUBSUB_EMULATOR_HOST")
        project = str(b.get("project") or "")
        sub = str(b.get("subscription") or label)
        if not sub:
            raise ValueError("pubsub: set subscription (defaults to the resource name)")
        topic = str(b.get("topic") or "")
        return cls(
            _qualify(sub, "subscription", project, "pubsub"),
            TokenSource("pubsub", b, emulator),
            endpoint or "https://pubsub.googleapis.com",
            _qualify(topic, "topic", project, "pubsub") if topic else "",
            return_immediately=bool(b.get("return_immediately", True)),
            timeout=float(b.get("timeout") or 10),
        )

    def _post(self, resource: str, verb: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"content-type": "application/json"}
        headers.update(self.tokens.headers())
        url = f"{self.endpoint}/v1/{resource}:{verb}"
        data = json_body("pubsub", request("pubsub", "POST", url, headers, json.dumps(payload).encode(), self.timeout))
        return data if isinstance(data, dict) else {}

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        if not self.topic:
            raise ValueError(f"pubsub: set `topic` to publish to {self.subscription}")
        message: Dict[str, Any] = {"data": base64.b64encode(body.encode("utf-8")).decode("ascii")}
        attrs = {str(k): str(v) for k, v in (attributes or {}).items()}
        if attrs:
            message["attributes"] = attrs
        ids = self._post(self.topic, "publish", {"messages": [message]}).get("messageIds") or [""]
        return str(ids[0])

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"maxMessages": max(1, min(int(batch), 1000))}
        if self.return_immediately:
            payload["returnImmediately"] = True  # deprecated by Google but honoured; keeps the host poll short
        received = self._post(self.subscription, "pull", payload).get("receivedMessages") or []
        claimed: List[Dict[str, Any]] = []
        for item in received:
            msg = item.get("message") or {}
            mid = str(msg.get("messageId") or "")
            with self._lock:
                self._attempts[mid] = self._attempts.get(mid, 0) + 1
                if len(self._attempts) > 10000:
                    for old in list(self._attempts)[:1000]:
                        del self._attempts[old]
                local = self._attempts[mid]
            try:
                body = base64.b64decode(msg.get("data") or "").decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                body = str(msg.get("data") or "")
            claimed.append(
                {
                    "id": mid,
                    "body": body,
                    "attributes": dict(msg.get("attributes") or {}),
                    "receives": int(item.get("deliveryAttempt") or local),
                    "enqueued_at": now,
                    "_ack": item.get("ackId"),
                }
            )
        if claimed:
            deadline = max(10, min(int(visibility), 600))
            self._post(
                self.subscription,
                "modifyAckDeadline",
                {"ackIds": [m["_ack"] for m in claimed], "ackDeadlineSeconds": deadline},
            )
        return claimed

    def settle(
        self,
        claimed: List[Dict[str, Any]],
        failed_ids: Set[str],
        max_receive: int,
        dead_letter: Optional[Any],
        now: float,
    ) -> None:
        ack: List[str] = []
        retry: List[str] = []
        for msg in claimed:
            if msg["id"] not in failed_ids:
                ack.append(msg["_ack"])
            elif dead_letter is not None and msg["receives"] >= max_receive:
                dead_letter.submit(str(msg.get("body") or ""), dict(msg.get("attributes") or {}))
                ack.append(msg["_ack"])
            else:
                retry.append(msg["_ack"])
        if retry:
            self._post(self.subscription, "modifyAckDeadline", {"ackIds": retry, "ackDeadlineSeconds": 0})
        if ack:
            self._post(self.subscription, "acknowledge", {"ackIds": ack})
            with self._lock:
                for msg in claimed:
                    if msg["_ack"] in ack:
                        self._attempts.pop(msg["id"], None)

    def depth(self) -> int:
        return -1  # Pub/Sub only reports backlog through Cloud Monitoring

    def recover(self, now: float, visibility: float) -> None:
        return None  # ack deadlines expire on the service


class GcsStorage:
    """:class:`StorageDriver` on one Cloud Storage bucket (optionally below ``prefix``)."""

    def __init__(
        self,
        bucket: str,
        tokens: TokenSource,
        endpoint: str = "https://storage.googleapis.com",
        prefix: str = "",
        timeout: float = 30.0,
    ) -> None:
        if not bucket:
            raise ValueError("gcs: set bucket (defaults to the resource name)")
        self.bucket = bucket
        self.tokens = tokens
        self.endpoint = check_url(endpoint, "gcs endpoint")
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        self.timeout = timeout

    @classmethod
    def from_binding(cls, b: Dict[str, Any], label: str = "") -> GcsStorage:
        endpoint, emulator = _emulator(b, "STORAGE_EMULATOR_HOST")
        return cls(
            str(b.get("bucket") or label),
            TokenSource("gcs", b, emulator),
            endpoint or "https://storage.googleapis.com",
            str(b.get("prefix") or ""),
            float(b.get("timeout") or 30),
        )

    def _object(self, key: str) -> str:
        return f"{self.endpoint}/storage/v1/b/{quote(self.bucket, safe='')}/o/{quote(self.prefix + key, safe='')}"

    def scan(self) -> Dict[str, Tuple[str, int]]:
        found: Dict[str, Tuple[str, int]] = {}
        token = ""
        while True:
            query = {"fields": "items(name,etag,size),nextPageToken"}
            if self.prefix:
                query["prefix"] = self.prefix
            if token:
                query["pageToken"] = token
            url = f"{self.endpoint}/storage/v1/b/{quote(self.bucket, safe='')}/o?{urlencode(query)}"
            data = json_body("gcs", request("gcs", "GET", url, self.tokens.headers(), timeout=self.timeout))
            for item in data.get("items") or []:
                name = str(item.get("name") or "")
                rel = name[len(self.prefix) :] if self.prefix and name.startswith(self.prefix) else name
                if rel and not rel.endswith("/"):
                    found[rel] = (str(item.get("etag") or ""), int(item.get("size") or 0))
            token = str(data.get("nextPageToken") or "")
            if not token:
                return found

    def put(self, key: str, data: bytes) -> None:
        query = urlencode({"uploadType": "media", "name": self.prefix + key})
        url = f"{self.endpoint}/upload/storage/v1/b/{quote(self.bucket, safe='')}/o?{query}"
        headers = {"content-type": "application/octet-stream"}
        headers.update(self.tokens.headers())
        check("gcs", request("gcs", "POST", url, headers, data, self.timeout))

    def get(self, key: str) -> bytes:
        reply = request("gcs", "GET", self._object(key) + "?alt=media", self.tokens.headers(), timeout=self.timeout)
        if reply[0] == 404:
            raise KeyError(key)
        return check("gcs", reply)

    def delete(self, key: str) -> bool:
        reply = request("gcs", "DELETE", self._object(key), self.tokens.headers(), timeout=self.timeout)
        if reply[0] == 404:
            return False
        check("gcs", reply, (200, 204))
        return True


__all__ = ["GcsStorage", "PubSubQueue", "TokenSource"]
