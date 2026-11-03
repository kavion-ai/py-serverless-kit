"""Cloudflare Queues driver through the HTTP pull consumer API (standard library only).

* Pull consumers: https://developers.cloudflare.com/queues/configuration/pull-consumers/
* REST API: https://developers.cloudflare.com/api/resources/queues/

The queue needs an HTTP pull consumer and an API token with Queues read/write.
Pulled messages are leased for ``visibility_timeout_ms``; unacknowledged leases
expire on Cloudflare, so ``recover`` is a no-op. ``attempts`` counts deliveries.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from ._http import DriverError, check_url, request

API = "https://api.cloudflare.com"


class CloudflareQueue:
    def __init__(
        self,
        account_id: str,
        queue_id: str,
        api_token: str,
        endpoint: str = API,
        timeout: float = 10.0,
    ) -> None:
        missing = [
            n for n, v in (("account_id", account_id), ("queue_id", queue_id), ("api_token", api_token)) if not v
        ]
        if missing:
            raise ValueError(f"cloudflare_queue: set {', '.join(missing)} (the token may come from api_token_env)")
        self.base = f"{check_url(endpoint, 'cloudflare endpoint')}/client/v4/accounts/{account_id}/queues/{queue_id}"
        self.queue_id = queue_id
        self.token = api_token
        self.timeout = timeout

    @classmethod
    def from_binding(cls, b: Dict[str, Any], label: str = "") -> CloudflareQueue:
        return cls(
            str(b.get("account_id") or ""),
            str(b.get("queue_id") or ""),
            str(b.get("api_token") or ""),
            str(b.get("endpoint") or API),
            float(b.get("timeout") or 10),
        )

    def _post(self, suffix: str, payload: Dict[str, Any]) -> Any:
        headers = {"authorization": f"Bearer {self.token}", "content-type": "application/json"}
        status, _h, raw = request(
            "cloudflare_queue", "POST", self.base + suffix, headers, json.dumps(payload).encode(), self.timeout
        )
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            data = {}
        if status != 200 or not data.get("success", False):
            errors = data.get("errors") or [{"message": raw[:200].decode("utf-8", "replace")}]
            text = "; ".join(str(e.get("message") or e) for e in errors if isinstance(e, dict)) or f"HTTP {status}"
            raise DriverError("cloudflare_queue", status, f"{self.queue_id}{suffix}: {text}")
        return data.get("result")

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        # Messages carry no attributes; they are dropped. The API does not return an id.
        self._post("/messages", {"body": body, "content_type": "text"})
        return ""

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        result = self._post(
            "/messages/pull",
            {"batch_size": max(1, min(int(batch), 100)), "visibility_timeout_ms": int(max(1, visibility) * 1000)},
        )
        messages = (result or {}).get("messages") if isinstance(result, dict) else result
        claimed: List[Dict[str, Any]] = []
        for msg in messages or []:
            body = msg.get("body")
            ts = msg.get("timestamp_ms")
            claimed.append(
                {
                    "id": str(msg.get("id") or msg.get("lease_id")),
                    "body": body if isinstance(body, str) else json.dumps(body),
                    "attributes": dict(msg.get("metadata") or {}),
                    "receives": int(msg.get("attempts") or 1),
                    "enqueued_at": float(ts) / 1000.0 if isinstance(ts, (int, float)) else now,
                    "_lease": msg.get("lease_id"),
                }
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
        acks: List[Dict[str, Any]] = []
        retries: List[Dict[str, Any]] = []
        for msg in claimed:
            if msg["id"] not in failed_ids:
                acks.append({"lease_id": msg["_lease"]})
            elif dead_letter is not None and msg["receives"] >= max_receive:
                dead_letter.submit(str(msg.get("body") or ""), dict(msg.get("attributes") or {}))
                acks.append({"lease_id": msg["_lease"]})
            else:
                retries.append({"lease_id": msg["_lease"], "delay_seconds": 0})
        if acks or retries:
            self._post("/messages/ack", {"acks": acks, "retries": retries})

    def depth(self) -> int:
        return -1  # backlog is only exposed through Cloudflare analytics

    def recover(self, now: float, visibility: float) -> None:
        return None
