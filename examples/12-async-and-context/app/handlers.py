"""Async handlers, the invocation context and structured logging.

* ``async def`` handlers are awaited for you. On most clouds the runtime runs
  them with ``asyncio.run``; Cloudflare Workers await them on their own event loop.
* ``ctx.logger`` writes one JSON object per line (``PSKIT_LOG_FORMAT=text``
  for humans; the CLI sets it locally). Every line carries ``function``,
  ``request_id`` and ``provider``, plus whatever you pass in ``extra``. CloudWatch,
  Cloud Logging and Application Insights can all query those fields.
"""

from __future__ import annotations

import asyncio
import time

from py_serverless_kit import Context, Event


async def _fetch(source: str, delay: float) -> dict:
    # Stand-in for an async HTTP / database call (httpx, aiohttp, asyncpg ...).
    await asyncio.sleep(delay)
    return {"source": source, "latency_ms": int(delay * 1000)}


async def aggregate(event: Event, ctx: Context):
    """GET /aggregate - fan out to three 'services' concurrently."""
    started = time.perf_counter()
    results = await asyncio.gather(_fetch("inventory", 0.05), _fetch("pricing", 0.08), _fetch("reviews", 0.03))
    elapsed = round((time.perf_counter() - started) * 1000)
    ctx.logger.info("aggregated", extra={"sources": len(results), "elapsed_ms": elapsed})
    # ~80 ms in total instead of ~160 ms sequentially
    return {"results": results, "elapsed_ms": elapsed}


def inspect(event: Event, ctx: Context):
    """POST /inspect - everything the runtime tells you about this invocation."""
    ctx.logger.debug("full event", extra={"event": event.to_dict()})
    return {
        "event": event.to_dict(),               # type, provider, function, time, http summary ...
        "context": {
            "request_id": ctx.request_id,       # use it in error messages and logs
            "function": ctx.function,
            "provider": ctx.provider,
            "service": ctx.service,
            "stage": ctx.stage,
            "region": ctx.region,
            "memory_mb": ctx.memory_mb,
            "remaining_time_ms": ctx.remaining_time_ms(),   # None when the platform doesn't say
        },
        "headers": {k: v for k, v in event.http.headers.items() if k.startswith("x-")},
    }


async def batch_job(event: Event, ctx: Context):
    """Scheduled: process work in chunks and stop before the platform timeout."""
    processed = 0
    for _ in range(100):
        remaining = ctx.remaining_time_ms()
        if remaining is not None and remaining < 3_000:
            ctx.logger.warning("time budget almost used, stopping", extra={"processed": processed})
            break
        await asyncio.sleep(0)  # do one chunk of real work here
        processed += 1
    ctx.logger.info("batch finished", extra={"processed": processed})
    return {"processed": processed}
