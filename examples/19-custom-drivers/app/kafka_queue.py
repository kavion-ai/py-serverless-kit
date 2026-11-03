"""A Kafka topic as an on-prem queue, through ``kafka-python`` (add it to requirements.txt).

Template: not run in CI. Delivery is at-least-once. Offsets are committed
only after a batch is settled. A failed record is produced again to the same
topic with a ``pskit-receives`` header, or to the dead-letter target once it
has failed ``max_receive`` times, and then committed. One failure doesn't hold
the whole partition back.

Use it with::

    resources:
      orders:
        type: queue
        external: true
        options:
          driver: custom
          class: app.kafka_queue:KafkaQueue
          bootstrap_servers: kafka-1:9092,kafka-2:9092
          topic: orders
          group_id: order-workers

Kafka has no visibility timeout and no queue depth. ``depth()`` returns -1
(unknown); use consumer-group lag in your Kafka tooling instead.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, List, Optional, Set


class KafkaQueue:
    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        poll_timeout_ms: int = 500,
        **client_options: Any,
    ) -> None:
        from kafka import KafkaConsumer, KafkaProducer  # imported here so packaging works without the library

        servers = [s.strip() for s in bootstrap_servers.split(",") if s.strip()]
        self.topic = topic
        # A zero timeout never completes the consumer-group join, so nothing is ever assigned.
        self.poll_timeout_ms = max(1, int(poll_timeout_ms))
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=servers,
            group_id=group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            **client_options,
        )
        self.producer = KafkaProducer(bootstrap_servers=servers, acks="all", **client_options)
        self._lock = threading.Lock()

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        ident = uuid.uuid4().hex
        headers = [("pskit-id", ident.encode())] + [(str(k), str(v).encode()) for k, v in (attributes or {}).items()]
        with self._lock:
            self.producer.send(self.topic, value=body.encode("utf-8"), headers=headers).get(timeout=30)
        return ident

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        polled = self.consumer.poll(timeout_ms=self.poll_timeout_ms, max_records=max(1, batch))
        claimed: List[Dict[str, Any]] = []
        for records in polled.values():
            for record in records:
                headers = {k: v.decode("utf-8", "replace") for k, v in (record.headers or [])}
                claimed.append(
                    {
                        "id": headers.pop("pskit-id", f"{record.partition}:{record.offset}"),
                        "body": record.value.decode("utf-8", "replace"),
                        "attributes": {k: v for k, v in headers.items() if k != "pskit-receives"},
                        "receives": int(headers.get("pskit-receives", 0)),
                        "enqueued_at": record.timestamp / 1000 if record.timestamp else now,
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
        for msg in claimed:
            if msg["id"] not in failed_ids:
                continue
            receives = int(msg["receives"]) + 1
            attrs = dict(msg["attributes"], **{"pskit-receives": receives})
            if dead_letter is not None and receives >= max_receive:
                dead_letter.submit(msg["body"], attrs)
            else:
                self.submit(msg["body"], attrs)  # the retry goes to the back of the topic
        self.consumer.commit()  # everything in this batch is now either done or re-queued

    def depth(self) -> int:
        return -1

    def recover(self, now: float, visibility: float) -> None:
        return None  # uncommitted records are delivered again after a restart or rebalance
