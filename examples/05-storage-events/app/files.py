"""Object storage notifications (S3, Cloud Storage, Blob Storage, OSS, COS, OBS ...).

Every record exposes the same fields on every cloud:

    record.bucket   bucket / container name
    record.key      object key (URL-decoded)
    record.size     bytes (None for deletions on some clouds)
    record.action   "created" | "deleted"

Reading the object itself is a cloud SDK call (boto3, google-cloud-storage,
azure-storage-blob, ...); this example only inspects the notification.
"""

from __future__ import annotations

import posixpath

from py_serverless_kit import Context, Event

MAX_IMPORT_BYTES = 50 * 1024 * 1024


def import_csv(event: Event, ctx: Context):
    """Triggered for new ``incoming/*.csv`` objects."""
    accepted, skipped = [], []
    for record in event.records:
        if record.action != "created":
            continue
        if record.size is not None and record.size > MAX_IMPORT_BYTES:
            skipped.append({"key": record.key, "reason": "too large"})
            continue
        dataset = posixpath.splitext(posixpath.basename(record.key))[0]
        ctx.logger.info("importing", extra={"bucket": record.bucket, "key": record.key, "dataset": dataset})
        accepted.append({"bucket": record.bucket, "key": record.key, "dataset": dataset})
    return {"accepted": accepted, "skipped": skipped}


def purge_index(event: Event, ctx: Context):
    """Triggered when an object is deleted - keep a search index / cache in sync."""
    removed = [record.key for record in event.records if record.action == "deleted"]
    ctx.logger.info("removing from index", extra={"keys": removed})
    return {"removed": removed}


def audit_existing_bucket(event: Event, ctx: Context):
    """Listens to a bucket that is managed elsewhere (``existing: true``)."""
    for record in event.records:
        ctx.logger.info(
            "object event",
            extra={"bucket": record.bucket, "key": record.key, "action": record.action, "size": record.size},
        )
