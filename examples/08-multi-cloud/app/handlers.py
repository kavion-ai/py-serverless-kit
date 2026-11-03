"""One codebase, every provider. Nothing in this file knows where it runs.

``event.provider`` / ``ctx.region`` are informational only - the logic below
is identical on every provider.
"""

from __future__ import annotations

import platform
from datetime import datetime, timezone

from py_serverless_kit import BadRequest, Context, Event, Response


def whoami(event: Event, ctx: Context):
    """GET /whoami - shows the portable context the runtime builds for you."""
    return {
        "provider": event.provider,
        "service": ctx.service,
        "stage": ctx.stage,
        "region": ctx.region,
        "function": ctx.function,
        "request_id": ctx.request_id,
        "python": platform.python_version(),
        "path": event.http.path,
        "client_ip": event.http.source_ip,
    }


def echo(event: Event, ctx: Context):
    """POST /echo - returns the JSON body plus a few request headers."""
    body = event.http.json()
    if not isinstance(body, dict):
        raise BadRequest("send a JSON object")
    return Response.json(
        {"you_sent": body, "content_type": event.http.content_type, "query": event.http.query},
        headers={"x-served-by": event.provider},
    )


def ticker(event: Event, ctx: Context):
    """Hourly schedule (on the clouds that support schedules)."""
    now = datetime.now(timezone.utc).isoformat()
    ctx.logger.info("tick", extra={"provider": event.provider, "at": now, "input": event.data})
    return {"ticked_at": now}
