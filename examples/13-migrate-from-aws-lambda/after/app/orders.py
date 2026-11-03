"""AFTER: the same service, cloud-neutral.

What changed compared with before/lambda_function.py:

* no event parsing - ``event.http.json()`` / ``path_params`` / ``records``;
* no ``statusCode`` dicts - return data or ``Response``; raise ``BadRequest``;
* no boto3 Step Functions client - the workflow is started by its own HTTP
  trigger or the cloud's console/CLI, and is defined in pskit.yml;
* task functions read ``event.data`` instead of the raw event.

The business rules themselves (validation, totals, charging) are untouched.
"""

from __future__ import annotations

from py_serverless_kit import BadRequest, BatchResult, Context, Event, NotFound


def create_order(event: Event, ctx: Context):
    order = event.http.json()  # invalid JSON -> 400 automatically
    if not isinstance(order, dict) or not order.get("items"):
        raise BadRequest("items required")
    order["total"] = sum(i["qty"] * i["price"] for i in order["items"])
    # Hand-off: the workflow is started by POSTing this order to the
    # workflow's trigger (see README, "Starting the workflow").
    return {"accepted": True, "order": order}, 202


def get_order(event: Event, ctx: Context):
    order_id = event.http.path_params.get("id")
    if not order_id:
        raise NotFound("not found")
    return {"id": order_id, "status": "unknown"}


def email_worker(event: Event, ctx: Context):
    result = BatchResult()
    for record in event.records:
        try:
            message = record.json()
            ctx.logger.info("sending email", extra={"to": message["to"]})
        except Exception:  # noqa: BLE001
            result.fail(record)
    return result


# Workflow tasks: the state arrives as event.data on every cloud.
def validate(event: Event, ctx: Context):
    order = event.data
    if sum(i["qty"] for i in order["items"]) <= 0:
        raise ValueError("empty order")  # matched by `catch: [{errors: [ValueError]}]`
    total = order.get("total", sum(i["qty"] * i["price"] for i in order["items"]))
    return {**order, "valid": True, "total": total}


def charge(event: Event, ctx: Context):
    return {**event.data, "charged": True}
