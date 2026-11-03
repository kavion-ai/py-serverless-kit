"""Handlers under test (see tests/)."""

from __future__ import annotations

from py_serverless_kit import BadRequest, BatchResult, Context, Event

DISCOUNTS = {"WELCOME10": 0.10, "VIP25": 0.25}


def price(event: Event, ctx: Context):
    """POST /price {"amount": 100, "code": "WELCOME10"}"""
    body = event.http.json()
    amount = body.get("amount")
    if not isinstance(amount, (int, float)) or amount < 0:
        raise BadRequest("amount must be a non-negative number")
    code = (body.get("code") or event.http.query.get("code") or "").upper()
    rate = DISCOUNTS.get(code, 0.0)
    return {"amount": amount, "discount": round(amount * rate, 2), "total": round(amount * (1 - rate), 2), "code": code or None}


def ingest(event: Event, ctx: Context):
    """Queue: messages must be JSON objects with an `id`."""
    result = BatchResult()
    for record in event.records:
        payload = record.json(default=None)
        if not isinstance(payload, dict) or "id" not in payload:
            result.fail(record)
    return result


def shipped_only(event: Event, ctx: Context):
    """Topic subscriber that relies on message attributes."""
    return [r.json()["order_id"] for r in event.records if r.attributes.get("event_type") == "order.shipped"]


def enrich(event: Event, ctx: Context):
    """Workflow task."""
    return {**event.data, "enriched": True}


def score(event: Event, ctx: Context):
    """Workflow task."""
    data = event.data
    return {**data, "score": 90 if data.get("vip") else 40}
