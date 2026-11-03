"""Handlers don't know which driver feeds them: the same code runs on any queue / bucket."""

from __future__ import annotations

from py_serverless_kit import BadRequest, BatchResult, Context, Event, resource


def enqueue(event: Event, ctx: Context):
    """POST /jobs {"task": "..."} -> publish to the `jobs` resource."""
    job = event.http.json(default=None)
    if not isinstance(job, dict) or not job.get("task"):
        raise BadRequest("send a JSON object with a `task`")
    queue = resource("jobs").native_name
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        # Inside the on-prem host: goes through whatever driver `jobs` uses (here SqliteQueue).
        from py_serverless_kit.runtime.onprem_host import submit_queue

        return {"queued": submit_queue(queue, job), "queue": queue}, 202
    ctx.logger.info("would enqueue", extra={"job": job, "queue": queue})
    return {"queued": None, "queue": queue}, 202


def work(event: Event, ctx: Context) -> BatchResult:
    """Consume `jobs`. A failed record is retried, then dead-lettered after max_receive tries."""
    result = BatchResult()
    for record in event.records:
        job = record.json()
        if job.get("task") == "explode":
            ctx.logger.error("job failed", extra={"id": record.id, "task": job.get("task")})
            result.fail(record)
            continue
        ctx.logger.info("job done", extra={"id": record.id, "task": job.get("task")})
    return result


def dead_letters(event: Event, ctx: Context) -> None:
    for record in event.records:
        ctx.logger.warning("dead letter", extra={"id": record.id, "body": record.text()})


def on_file(event: Event, ctx: Context) -> None:
    """Fires for files created / deleted in the `inbox` folder (FolderStorage)."""
    for record in event.records:
        ctx.logger.info("file event", extra={"action": record.action, "key": record.key, "size": record.size})
