"""Queue consumer with partial batch failure reporting.

``event.records`` holds the messages of one batch. Return a ``BatchResult``
naming the records that failed:

* AWS SQS and the on-premises host: only those messages become visible again
                   and are retried (``ReportBatchItemFailures`` on AWS);
* other clouds:    any failure fails the invocation, so the whole batch is redelivered.

Either way a message that keeps failing ends up in the dead-letter queue
configured in pskit.yml (where the cloud supports one), instead of blocking
the queue forever.
"""

from __future__ import annotations

from py_serverless_kit import BatchResult, Context, Event, Record

SUPPORTED_KINDS = {"email", "thumbnail", "invoice"}


class PermanentError(Exception):
    """Retrying will not help (bad payload). Log it and drop the message."""


def handle_job(job: dict) -> dict:
    kind = job.get("kind")
    if kind not in SUPPORTED_KINDS:
        raise PermanentError(f"unknown job kind {kind!r}")
    if job.get("simulate_failure"):
        raise RuntimeError("downstream service unavailable")  # transient -> retry
    return {"kind": kind, "id": job.get("id"), "status": "done"}


def process_jobs(event: Event, ctx: Context):
    result = BatchResult()
    for record in event.records:
        try:
            job = record.json()
            outcome = handle_job(job)
            ctx.logger.info("job done", extra={"message_id": record.id, **outcome})
        except PermanentError as exc:
            # Don't retry poison messages: acknowledge them (and alert / store them elsewhere).
            ctx.logger.error("dropping message", extra={"message_id": record.id, "reason": str(exc)})
        except Exception:  # noqa: BLE001 - anything else is worth retrying
            ctx.logger.exception("job failed, will retry", extra={"message_id": record.id})
            result.fail(record)
    return result


def audit_dead_letters(event: Event, ctx: Context):
    """Consumes the dead-letter queue so failures are visible instead of silently piling up."""
    for record in event.records:
        _log_dead_letter(record, ctx)


def _log_dead_letter(record: Record, ctx: Context) -> None:
    ctx.logger.error(
        "dead letter",
        extra={"message_id": record.id, "body": record.text()[:1000], "attributes": record.attributes},
    )


def enqueue(event: Event, ctx: Context):
    """HTTP producer.

    On premises the host is in this process, so the message is written to the
    file queue. On a cloud, publishing is a cloud SDK call (boto3
    ``sqs.send_message``, ``google-cloud-pubsub`` ``publish``,
    ``azure-storage-queue`` ``send_message``). Keep that call behind a small
    function of your own (see README).
    """
    job = event.http.json()
    queue = ctx.env.get("JOBS_QUEUE") or "jobs"
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import submit_queue

        message_id = submit_queue(queue, job)
        return {"accepted": True, "queue": queue, "message_id": message_id}, 202
    ctx.logger.info("would enqueue", extra={"job": job, "queue": queue})
    return {"accepted": True, "queue": queue}, 202
