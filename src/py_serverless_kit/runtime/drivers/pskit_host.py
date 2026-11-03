"""A built-in queue of another pskit on-premises host (standard library only).

Functions on host A consume a queue that lives on host B (``use: builtin`` there)
through B's admin API:

* ``POST <endpoint>/__pskit/queues/<queue>`` publishes,
* ``POST .../lease`` claims messages for ``visibility`` seconds (B hides them meanwhile),
* ``POST .../ack`` deletes delivered ones and ``.../nack`` makes failed ones visible again.

A lease that is never settled (host A crashed) expires on B, so ``recover`` is a no-op
and delivery is at-least-once. ``token`` is B's ``admin_token`` (``token_env`` to keep it
out of the files).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote

from ._http import DriverError, check_url, request


class PskitHostQueue:
    def __init__(self, endpoint: str, queue: str, token: str = "", timeout: float = 10.0) -> None:
        if not queue:
            raise ValueError("pskit_host: set queue (the queue's name on the other host)")
        self.base = f"{check_url(endpoint, 'pskit_host endpoint')}/__pskit/queues/{quote(queue, safe='')}"
        self.queue = queue
        self.token = token
        self.timeout = timeout

    @classmethod
    def from_binding(cls, b: Dict[str, Any], label: str = "") -> PskitHostQueue:
        return cls(
            str(b.get("endpoint") or ""),
            str(b.get("queue") or label or ""),
            str(b.get("token") or ""),
            float(b.get("timeout") or 10),
        )

    def _call(self, method: str, suffix: str, payload: Optional[Any] = None) -> Any:
        headers = {"content-type": "application/json"}
        if self.token:
            headers["x-pskit-token"] = self.token
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        status, _h, raw = request("pskit_host", method, self.base + suffix, headers, body, self.timeout)
        if status not in (200, 202):
            text = raw[:300].decode("utf-8", "replace").strip() or "no response body"
            if status == 401:
                text += " (set token / token_env to the other host's admin_token)"
            raise DriverError("pskit_host", status, f"{self.queue}{suffix}: {text}")
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            return {}

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        reply = self._call("POST", "", {"message": body, "attributes": dict(attributes or {})})
        ids = reply.get("queued") if isinstance(reply, dict) else None
        return str(ids[0]) if ids else ""

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        del now
        reply = self._call("POST", "/lease", {"batch": int(batch), "visibility": float(visibility)})
        out: List[Dict[str, Any]] = []
        for msg in (reply or {}).get("messages") or []:
            out.append(
                {
                    "id": str(msg.get("id") or ""),
                    "body": msg.get("body"),
                    "attributes": dict(msg.get("attributes") or {}),
                    "receives": int(msg.get("receives") or 1),
                    "enqueued_at": msg.get("enqueued_at"),
                    "_receipt": str(msg.get("receipt") or ""),
                }
            )
        return out

    def settle(
        self,
        claimed: List[Dict[str, Any]],
        failed_ids: Set[str],
        max_receive: int,
        dead_letter: Optional[Any],
        now: float,
    ) -> None:
        del now
        acks: List[str] = []
        nacks: List[str] = []
        for msg in claimed:
            receipt = msg.get("_receipt")
            if not receipt:
                continue
            if msg["id"] not in failed_ids:
                acks.append(receipt)
            elif dead_letter is not None and int(msg.get("receives") or 1) >= max_receive:
                dead_letter.submit(str(msg.get("body") or ""), dict(msg.get("attributes") or {}))
                acks.append(receipt)
            else:
                nacks.append(receipt)
        if acks:
            self._call("POST", "/ack", {"receipts": acks})
        if nacks:
            self._call("POST", "/nack", {"receipts": nacks})

    def peek(self, offset: int, limit: int) -> Tuple[List[Dict[str, Any]], int]:
        reply = self._call("GET", f"/peek?offset={int(offset)}&limit={int(limit)}")
        return list(reply.get("items") or []), int(reply.get("total") or 0)

    def depth(self) -> int:
        reply = self._call("GET", "")
        depth = reply.get("depth") if isinstance(reply, dict) else None
        return int(depth) if isinstance(depth, int) else -1

    def recover(self, now: float, visibility: float) -> None:
        del now, visibility  # leases expire on the other host
