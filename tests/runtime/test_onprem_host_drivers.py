"""The on-prem host consumes resource-backed queues (Redis) and buckets (S3-compatible)."""

from __future__ import annotations

import json
import time

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.runtime.onprem_host import Host, activate_layout

from .test_drivers import redis_server, s3_server  # noqa: F401 - pytest fixtures

HANDLERS = """
import os
from pathlib import Path

from py_serverless_kit import BatchResult, Event, Context, resource


def worker(event: Event, ctx: Context):
    result = BatchResult()
    out = Path(os.environ["OUT"])
    for record in event.records:
        if record.text() == "fail":
            result.fail(record)
        else:
            out.write_text(out.read_text() + record.text() + "," if out.exists() else record.text() + ",")
    return result


def on_media(event: Event, ctx: Context):
    Path(os.environ["MEDIA_OUT"]).write_text(
        ",".join(f"{r.action}:{r.key}" for r in event.records), encoding="utf-8"
    )


def binding(event: Event, ctx: Context):
    jobs = resource("jobs")
    return {"type": jobs.type, "name": jobs.native_name, "external": jobs.external}
"""

CONFIG = """
service: drv
provider:
  name: onprem
  runtime: python3.12
  options:
    host: 127.0.0.1
    port: 8098
    data_dir: {data}
  environment:
    OUT: "{out}"
    MEDIA_OUT: "{media_out}"
resources:
  jobs:
    type: queue
    external: true
    options: {{driver: redis, url: "{redis}", key: jobs}}
  media:
    type: storage
    external: true
    name: media
    options: {{driver: s3, endpoint: "{s3}", access_key: AK, secret_key: SK, path_style: true}}
functions:
  worker:
    handler: app.handlers.worker
    events:
      - queue: {{resource: jobs, batch_size: 10, max_receive: 1, dead_letter: jobs-dlq}}
  on-media:
    handler: app.handlers.on_media
    events:
      - storage: {{resource: media, events: [created, deleted]}}
  binding:
    handler: app.handlers.binding
"""


def _host(make_project, tmp_path, redis_url, s3_url):
    text = CONFIG.format(
        data=(tmp_path / "data").as_posix(),
        out=(tmp_path / "out.txt").as_posix(),
        media_out=(tmp_path / "media.txt").as_posix(),
        redis=redis_url,
        s3=s3_url,
    )
    project = make_project(text, files={"app/handlers.py": HANDLERS})
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    spec = json.loads((root / "pskit_host.json").read_text("utf-8"))
    host = Host(root)
    host.open()
    return host, spec


def test_redis_queue_and_s3_bucket_drive_handlers(make_project, tmp_path, redis_server, s3_server):  # noqa: F811
    redis_url, _state = redis_server
    host, spec = _host(make_project, tmp_path, redis_url, s3_server)
    try:
        events = {ev["type"]: ev for fn in spec["functions"].values() for ev in fn["events"]}
        assert events["queue"]["driver"]["use"] == "redis"
        assert events["storage"]["driver"]["use"] == "s3"
        assert host.broker.queue_driver("jobs") is not None and host.broker.storage_driver("media") is not None

        # Queue: publish through the broker (same path as POST /__pskit/queues/jobs).
        host.broker.submit_queue("jobs", "a")
        host.broker.submit_queue("jobs", "fail")
        assert host.broker.queue_depth("jobs") == 2
        now = time.time()
        host.pump_queues(now)
        assert (tmp_path / "out.txt").read_text() == "a,"
        assert host.broker.queue_depth("jobs") == 0
        assert host.broker.queue_depth("jobs-dlq") == 1  # builtin DLQ by name

        # Storage: an object written to the S3 bucket fires `created`, removing it fires `deleted`.
        host.broker.put_object("media", "pics/cat.png", b"meow")
        assert host.broker.get_object("media", "pics/cat.png") == b"meow"
        host.pump_storage(time.time())
        assert (tmp_path / "media.txt").read_text("utf-8") == "created:pics/cat.png"
        assert host.broker.delete_object("media", "pics/cat.png") is True
        host.pump_storage(time.time())
        assert (tmp_path / "media.txt").read_text("utf-8") == "deleted:pics/cat.png"

        from py_serverless_kit import Event

        out = host.invoke("binding", Event(type="invoke"))
        assert out == {"type": "queue", "name": "jobs", "external": True}

        stats = host.stats()
        assert stats["queues"]["jobs"] == 0 and stats["functions"]["worker"]["invocations"] == 1
    finally:
        host.executor.shutdown()
        host.logs.close()


def test_unreachable_backends_become_notes_not_crashes(make_project, tmp_path):
    host, _spec = _host(make_project, tmp_path, "redis://127.0.0.1:1/0", "http://127.0.0.1:1")
    try:
        host.pump(time.time())
        joined = " ".join(host.notes)
        assert "queue jobs" in joined and "storage media" in joined
        warnings = host.logs.query(source="host", level="warning")["entries"]
        assert any("queue jobs" in e["message"] for e in warnings)
        assert host.stats()["queues"]["jobs"] is None
    finally:
        host.executor.shutdown()
        host.logs.close()
