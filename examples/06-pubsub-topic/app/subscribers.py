"""Two independent subscribers to the same ``order-events`` topic (fan-out).

Every published message is delivered to *each* subscriber. Messages carry
attributes (SNS message attributes, Pub/Sub attributes, Service Bus
application properties) available as ``record.attributes``.

The YAML adds a filter policy so ``notify_customer`` only receives
``order.shipped`` events. Filters are enforced by AWS SNS; on clouds where
pskit cannot configure them, ``_wants`` repeats the check in code, so the
handler behaves the same everywhere.
"""

from __future__ import annotations

from py_serverless_kit import Context, Event, Record


def _wants(record: Record, allowed: set) -> bool:
    return record.attributes.get("event_type") in allowed


def update_analytics(event: Event, ctx: Context):
    """Receives every order event."""
    counts: dict = {}
    for record in event.records:
        kind = record.attributes.get("event_type", "unknown")
        counts[kind] = counts.get(kind, 0) + 1
        ctx.logger.info("analytics", extra={"message_id": record.id, "event_type": kind})
    return {"counts": counts}


def notify_customer(event: Event, ctx: Context):
    """Receives only shipped orders (filter policy + defensive check)."""
    sent = []
    for record in event.records:
        if not _wants(record, {"order.shipped"}):
            continue
        order = record.json()
        ctx.logger.info("emailing customer", extra={"order_id": order.get("order_id"), "email": order.get("email")})
        sent.append(order.get("order_id"))
    return {"notified": sent}
