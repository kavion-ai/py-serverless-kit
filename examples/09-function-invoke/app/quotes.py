"""Function-to-function calls with ``invoke()``.

``invoke("price-calculator", payload)`` calls another function of the same
service by its *logical* name from pskit.yml. The target receives an event
with ``event.type == "invoke"`` and ``event.data == payload``. Its return
value comes back to the caller.

The caller never builds ARNs, URLs or cloud SDK requests itself. See the README
for how each cloud resolves the target.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from py_serverless_kit import BadRequest, Context, Event, invoke

TAX_RATES = {"DE": Decimal("0.19"), "FR": Decimal("0.20"), "US": Decimal("0.00"), "IN": Decimal("0.18")}


def quote(event: Event, ctx: Context):
    """POST /quote {"items": [{"sku": ..., "qty": ..., "unit_price": ...}], "country": "DE"}"""
    body = event.http.json()
    if not isinstance(body, dict) or not body.get("items"):
        raise BadRequest("`items` is required")
    price = invoke("price-calculator", {"items": body["items"], "country": body.get("country", "US")})
    # Fire-and-forget on clouds that support asynchronous invocation (AWS);
    # elsewhere it runs synchronously.
    invoke("audit-log", {"action": "quote", "request_id": ctx.request_id, "total": price["total"]}, asynchronous=True)
    return {"quote": price, "request_id": ctx.request_id}


def price_calculator(event: Event, ctx: Context):
    """Invoke-only: no public trigger. Pure business logic, easy to unit test."""
    data = event.data or {}
    subtotal = sum(Decimal(str(i["unit_price"])) * int(i["qty"]) for i in data.get("items", []))
    rate = TAX_RATES.get(data.get("country", "US"), Decimal("0"))
    tax = (subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"subtotal": float(subtotal), "tax": float(tax), "total": float(subtotal + tax), "tax_rate": float(rate)}


def audit_log(event: Event, ctx: Context):
    ctx.logger.info("audit", extra={"entry": event.data})
    return {"logged": True}
