"""Portable handlers: they never see which cloud or driver delivered the records."""

from __future__ import annotations

from py_serverless_kit import BatchResult, Context, Event, resources


def process(event: Event, ctx: Context) -> BatchResult:
    result = BatchResult()
    for record in event.records:
        try:
            payload = record.json()
        except ValueError:
            payload = record.text()
        if isinstance(payload, dict) and payload.get("poison"):
            result.fail(record)  # retried by the driver, dead-lettered after max_receive if configured
            continue
        ctx.logger.info("job", extra={"id": record.id, "source": record.source})
    return result


def on_object(event: Event, ctx: Context) -> None:
    for record in event.records:
        ctx.logger.info("object", extra={"bucket": record.bucket, "key": record.key, "action": record.action})


def status(event: Event, ctx: Context):
    """Which external services this function is bound to (names only, never credentials)."""
    return {
        name: {"type": res.type, "name": res.native_name, "external": res.external}
        for name, res in sorted(resources().items())
    }
