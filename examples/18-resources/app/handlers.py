"""Read resource bindings the same way on every cloud.

``resource("<key>")`` returns the native name (bucket / queue / topic), whether
the resource is external, its ``connection`` values and, where the provider knows
them, ``arn`` / ``url`` / ``id``. Use them with the SDK of your cloud, or with
any client library for an external database or cache.
"""

from __future__ import annotations

import os

from py_serverless_kit import BatchResult, Context, Event, resource, resources


def bindings(event: Event, ctx: Context):
    """GET /bindings: what this function can reach (never returns secret values)."""
    return {
        name: {
            "type": res.type,
            "native_name": res.native_name,
            "external": res.external,
            "settings": sorted(res.connection),
        }
        for name, res in resources().items()
    }


def _dsn() -> str:
    db = resource("orders-db")
    password = os.environ.get(db.get("password_env") or "", "")
    auth = f"app:{password}@" if password else "app@"
    return f"postgresql://{auth}{db['host']}:{db['port']}/{db['database']}"


def work(event: Event, ctx: Context):
    result = BatchResult()
    topic = resource("notifications").native_name
    for record in event.records:
        try:
            job = record.json()
            ctx.logger.info("job done", extra={"job": job, "notify": topic, "db": _dsn().split("@")[-1]})
        except ValueError:
            result.fail(record)
    return result
