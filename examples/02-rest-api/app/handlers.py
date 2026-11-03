"""A small REST API showing every HTTP feature of the portable runtime.

Routes (see pskit.yml):

    GET    /books               list, optional ?author= filter and ?limit=
    GET    /books/{id}          fetch one              -> 404 if missing
    POST   /books               create (JSON body)     -> 201, 400, 409
    PUT    /books/{id}          replace                -> 200, 400, 404
    DELETE /books/{id}          delete                 -> 204, 404
    GET    /books/{id}/cover    binary image/png
    GET    /docs                302 redirect
    POST   /session             sets an HttpOnly cookie
    GET    /admin/stats         protected by JWT on AWS (see README)
"""

from __future__ import annotations

import base64
from typing import Any, Dict

from py_serverless_kit import BadRequest, Conflict, Context, Event, NotFound, Response, Unauthorized

from . import store

# 1x1 transparent PNG, so the example needs no image files.
_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

_REQUIRED = {"title": str, "author": str, "year": int, "isbn": str}


def _validate(body: Any) -> Dict[str, Any]:
    """Return a clean book dict or raise BadRequest (-> HTTP 400 with details)."""
    if not isinstance(body, dict):
        raise BadRequest("body must be a JSON object")
    errors = {}
    for field, kind in _REQUIRED.items():
        value = body.get(field)
        if value is None:
            errors[field] = "required"
        elif not isinstance(value, kind) or isinstance(value, bool):
            errors[field] = f"must be {kind.__name__}"
    if isinstance(body.get("isbn"), str) and len(body["isbn"].replace("-", "")) not in (10, 13):
        errors["isbn"] = "must have 10 or 13 digits"
    if errors:
        raise BadRequest("validation failed", details=errors)
    return {field: body[field] for field in _REQUIRED}


def list_books(event: Event, ctx: Context):
    q = event.http.query
    try:
        limit = int(q.get("limit", "50"))
    except ValueError:
        raise BadRequest("limit must be an integer") from None
    books = store.list_books(q.get("author"))[: max(1, min(limit, 100))]
    return {"items": books, "count": len(books)}


def get_book(event: Event, ctx: Context):
    book = store.get(event.http.path_params["id"])
    if book is None:
        raise NotFound(f"book {event.http.path_params['id']} not found")
    return book


def create_book(event: Event, ctx: Context):
    book = _validate(event.http.json())  # malformed JSON -> automatic 400
    if store.find_by_isbn(book["isbn"]):
        raise Conflict(f"a book with isbn {book['isbn']} already exists")
    created = store.put(book)
    return Response.json(created, status=201, headers={"location": f"/books/{created['id']}"})


def update_book(event: Event, ctx: Context):
    book_id = event.http.path_params["id"]
    if store.get(book_id) is None:
        raise NotFound(f"book {book_id} not found")
    return store.put({**_validate(event.http.json()), "id": book_id})


def delete_book(event: Event, ctx: Context):
    if not store.delete(event.http.path_params["id"]):
        raise NotFound(f"book {event.http.path_params['id']} not found")
    return Response.no_content()


def cover(event: Event, ctx: Context):
    get_book(event, ctx)  # 404 for unknown ids
    # Binary bodies are base64-encoded for API gateways automatically.
    return Response.binary(_PIXEL, "image/png", headers={"cache-control": "public, max-age=86400"})


def docs(event: Event, ctx: Context):
    return Response.redirect("https://github.com/kavion-ai/py-serverless-kit/tree/main/docs")


def create_session(event: Event, ctx: Context):
    body = event.http.json(default={})
    user = body.get("user") if isinstance(body, dict) else None
    if not user:
        raise BadRequest("`user` is required")
    resp = Response.json({"user": user, "request_id": ctx.request_id})
    # Secure + HttpOnly + SameSite=Lax by default.
    return resp.set_cookie("session", f"demo-{user}", max_age=3600)


def admin_stats(event: Event, ctx: Context):
    # On AWS the API Gateway JWT authorizer has already verified the token.
    # On clouds without a gateway authorizer (see `providers:` in pskit.yml) the
    # route is public, so at least require the header here - and verify the
    # token with a JWT library in a real service.
    if event.provider not in ("aws", "local") and not event.http.headers.get("authorization"):
        raise Unauthorized("missing bearer token")
    return {"books": len(store.list_books()), "session_cookie": event.http.cookies.get("session")}
