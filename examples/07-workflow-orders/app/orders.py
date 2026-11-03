"""Task functions of the ``order-pipeline`` workflow.

Each task receives the current workflow state as ``event.data`` and returns
the value that the state's ``result_path`` stores. Raised exceptions are
matched by **class name** against ``retry`` / ``catch`` rules, on AWS Step
Functions, GCP Workflows and the embedded engine alike.
"""

from __future__ import annotations

import threading
from decimal import Decimal

from py_serverless_kit import Context, Event


class PaymentDeclined(Exception):
    """Permanent: the card was refused. Caught by the workflow -> Declined state."""


class PaymentGatewayTimeout(Exception):
    """Transient: retried with exponential backoff by the workflow."""


class OutOfStock(Exception):
    pass


_STOCK = {"sku-book": 100, "sku-mug": 3, "sku-poster": 0}
_FLAKY_CALLS = {"count": 0}
_LOCK = threading.Lock()


def validate_order(event: Event, ctx: Context):
    """Normalise the order so later choice rules can rely on every field existing."""
    order = dict(event.data or {})
    items = order.get("items") or []
    if not items:
        raise ValueError("order has no items")
    for item in items:
        if item.get("qty", 0) <= 0:
            raise ValueError(f"invalid quantity for {item.get('sku')}")
    total = sum(Decimal(str(i["price"])) * i["qty"] for i in items)
    order["total"] = float(total)
    order.setdefault("currency", "EUR")
    order.setdefault("channel", "web")
    order["customer"] = {"vip": False, **(order.get("customer") or {})}
    return order


def reserve_item(event: Event, ctx: Context):
    """Map iterator: called once per item, in parallel."""
    item = event.data
    with _LOCK:
        available = _STOCK.get(item["sku"], 0)
        if available < item["qty"]:
            raise OutOfStock(f"{item['sku']}: wanted {item['qty']}, have {available}")
        _STOCK[item["sku"]] = available - item["qty"]
    return {"sku": item["sku"], "qty": item["qty"], "reserved": True}


def charge_payment(event: Event, ctx: Context):
    order = event.data
    card = order.get("card", "tok_ok")
    if card == "tok_declined":
        raise PaymentDeclined("card declined by issuer")
    if card == "tok_flaky":
        with _LOCK:
            _FLAKY_CALLS["count"] += 1
            attempt = _FLAKY_CALLS["count"]
        if attempt % 2 == 1:  # every first attempt times out, the retry succeeds
            raise PaymentGatewayTimeout("gateway did not answer in 10s")
    ctx.logger.info("charged", extra={"order_id": order.get("order_id"), "total": order["total"]})
    return {"status": "charged", "amount": order["total"], "currency": order["currency"]}


def send_confirmation(event: Event, ctx: Context):
    order = event.data
    return {"email_sent_to": order.get("customer", {}).get("email", "unknown")}


def create_shipment(event: Event, ctx: Context):
    order = event.data
    return {"carrier": "DHL", "tracking": f"TRK-{order.get('order_id', 'x')}"}
