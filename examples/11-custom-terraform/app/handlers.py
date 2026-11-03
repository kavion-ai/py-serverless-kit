import uuid

from py_serverless_kit import BadRequest, Context, Event, NotFound, Response

from .repository import repository


def create_order(event: Event, ctx: Context):
    body = event.http.json()
    if not isinstance(body, dict) or "item" not in body:
        raise BadRequest("`item` is required")
    order = {"id": uuid.uuid4().hex, "item": body["item"], "status": "new"}
    repository().put(order)
    return Response.json(order, status=201)


def get_order(event: Event, ctx: Context):
    order = repository().get(event.http.path_params["id"])
    if order is None:
        raise NotFound("order not found")
    return order
