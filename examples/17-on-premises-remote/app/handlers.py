"""Handlers for a remote on-premises deploy. Identical to a cloud function."""

from __future__ import annotations

from py_serverless_kit import Context, Event


def hello(event: Event, ctx: Context):
    name = event.http.query.get("name", "world")
    ctx.logger.info("greeting", extra={"name": name})
    return {"message": f"Hello, {name}!", "provider": event.provider, "stage": ctx.stage, "host": "remote"}


def tick(event: Event, ctx: Context):
    ctx.logger.info("tick", extra={"data": event.data})
    return {"ok": True, "data": event.data}
