"""Handlers for the on-premises demo. The same functions run on a cloud."""

from __future__ import annotations

from py_serverless_kit import BatchResult, Context, Event


def hello(event: Event, ctx: Context):
    name = event.http.query.get("name", "world")
    ctx.logger.info("greeting", extra={"name": name})
    return {"message": f"Hello, {name}!", "provider": event.provider, "stage": ctx.stage}


def tick(event: Event, ctx: Context):
    ctx.logger.info("tick", extra={"data": event.data})
    return {"ok": True, "data": event.data}


def worker(event: Event, ctx: Context):
    result = BatchResult()
    for record in event.records:
        job = record.json()
        if isinstance(job, dict) and job.get("fail"):
            ctx.logger.error("job failed", extra={"message_id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("job done", extra={"message_id": record.id})
    return result


def audit_dlq(event: Event, ctx: Context):
    for record in event.records:
        ctx.logger.error("dead letter", extra={"message_id": record.id, "body": record.text()[:500]})
    return {"seen": len(event.records)}


def on_upload(event: Event, ctx: Context):
    names = []
    for record in event.records:
        ctx.logger.info("object", extra={"key": record.key, "action": record.action})
        names.append(record.key)
    return {"keys": names}


def on_order(event: Event, ctx: Context):
    ctx.logger.info("order event", extra={"count": len(event.records)})
    return {"records": len(event.records)}


def mark(event: Event, ctx: Context):
    data = dict(event.data or {})
    data["seen"] = True
    ctx.logger.info("marked", extra=data)
    return data
