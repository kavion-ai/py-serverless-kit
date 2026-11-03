"""Scheduled jobs.

For a schedule event:

* ``event.type == "schedule"``
* ``event.data`` is the ``input`` configured in pskit.yml (or ``None``)
* ``event.time`` is when the platform fired the trigger (UTC)

A job that raises is retried according to the platform's policy, so make
jobs idempotent: running the same job twice must be harmless.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from py_serverless_kit import Context, Event


def heartbeat(event: Event, ctx: Context):
    """Runs every 5 minutes - e.g. ping dependencies, refresh a cache."""
    ctx.logger.info("heartbeat", extra={"fired_at": event.time.isoformat()})
    return {"ok": True, "at": event.time.isoformat()}


def daily_report(event: Event, ctx: Context):
    """Runs every weekday at 09:00 Europe/Berlin (on clouds that support time zones)."""
    options = event.data or {}
    period_end = event.time.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = period_end - timedelta(days=int(options.get("days", 1)))
    report = {
        "report": options.get("report", "daily"),
        "recipients": options.get("recipients", []),
        "period": [period_start.isoformat(), period_end.isoformat()],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    ctx.logger.info("report generated", extra=report)
    return report


def cleanup(event: Event, ctx: Context):
    """Monthly cleanup - checks the remaining time so it can stop gracefully."""
    retention_days = int((event.data or {}).get("retention_days", 30))
    deleted = 0
    for _batch in range(10):  # pretend to delete in batches
        remaining = ctx.remaining_time_ms()
        if remaining is not None and remaining < 5_000:
            ctx.logger.warning("stopping early, will continue next run", extra={"deleted": deleted})
            break
        deleted += 100
    return {"retention_days": retention_days, "deleted": deleted}
