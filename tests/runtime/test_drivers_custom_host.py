"""The on-prem host runs `custom` queue and storage drivers defined in the deployed app."""

from __future__ import annotations

import json
import time

import pytest

from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.runtime.onprem_host import Host, activate_layout

BACKENDS = '''
import time
import uuid

QUEUES = {}
BUCKETS = {}
SEEN = {}


class MemoryQueue:
    """Leases like a real broker: claimed messages stay invisible until settled or expired."""

    def __init__(self, name, token):
        SEEN["queue"] = {"name": name, "token": token}
        self.items = QUEUES.setdefault(name, [])

    def submit(self, body, attributes):
        msg = {"id": uuid.uuid4().hex, "body": body, "attributes": dict(attributes), "receives": 0, "visible": 0.0}
        self.items.append(msg)
        return msg["id"]

    def claim(self, batch, visibility, now):
        picked = [m for m in self.items if m["visible"] <= now][:batch]
        for m in picked:
            m["receives"] += 1
            m["visible"] = now + visibility
        return [dict(m, enqueued_at=now) for m in picked]

    def settle(self, claimed, failed_ids, max_receive, dead_letter, now):
        for c in claimed:
            m = next(x for x in self.items if x["id"] == c["id"])
            if c["id"] not in failed_ids:
                self.items.remove(m)
            elif dead_letter is not None and m["receives"] >= max_receive:
                dead_letter.submit(m["body"], m["attributes"])
                self.items.remove(m)
            else:
                m["visible"] = 0.0


class MemoryBucket:
    def __init__(self, bucket="media"):
        self.objects = BUCKETS.setdefault(bucket, {})

    def scan(self):
        return {k: (str(hash(v)), len(v)) for k, v in self.objects.items()}

    def put(self, key, data):
        self.objects[key] = data

    def get(self, key):
        return self.objects[key]

    def delete(self, key):
        return self.objects.pop(key, None) is not None
'''

HANDLERS = """
import os
from pathlib import Path

from py_serverless_kit import BatchResult, Context, Event


def worker(event: Event, ctx: Context):
    result = BatchResult()
    out = Path(os.environ["OUT"])
    for record in event.records:
        if record.text() == "fail":
            result.fail(record)
        else:
            out.write_text((out.read_text() if out.exists() else "") + record.text() + ",")
    return result


def on_media(event: Event, ctx: Context):
    Path(os.environ["MEDIA_OUT"]).write_text(",".join(f"{r.action}:{r.key}" for r in event.records))
"""

CONFIG = """
service: custom-drv
provider:
  name: onprem
  runtime: python3.12
  options: {{host: 127.0.0.1, port: 8096, data_dir: {data}}}
  environment:
    OUT: "{out}"
    MEDIA_OUT: "{media_out}"
resources:
  jobs:
    type: queue
    external: true
    options: {{driver: custom, class: "app.backends:MemoryQueue", name: jobs, token_env: BACKEND_TOKEN}}
  media:
    type: storage
    external: true
    options: {{driver: custom, class: "app.backends:MemoryBucket"}}
functions:
  worker:
    handler: app.handlers.worker
    events:
      - queue: {{resource: jobs, max_receive: 2, dead_letter: jobs-dlq}}
  on-media:
    handler: app.handlers.on_media
    events:
      - storage: {{resource: media, events: [created, deleted]}}
"""


def _host(make_project, tmp_path):
    text = CONFIG.format(
        data=(tmp_path / "data").as_posix(),
        out=(tmp_path / "out.txt").as_posix(),
        media_out=(tmp_path / "media.txt").as_posix(),
    )
    project = make_project(text, files={"app/handlers.py": HANDLERS, "app/backends.py": BACKENDS})
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    return root


def test_custom_queue_and_storage_drive_handlers(make_project, tmp_path, monkeypatch):
    root = _host(make_project, tmp_path)
    spec = json.loads((root / "pskit_host.json").read_text("utf-8"))
    driver = spec["resources"]["jobs"]["driver"]
    assert driver == {"use": "custom", "class": "app.backends:MemoryQueue", "name": "jobs", "token_env": "BACKEND_TOKEN"}

    monkeypatch.setenv("BACKEND_TOKEN", "t0k")
    # Fresh process state: the bundle is not importable yet and no `app` module is cached.
    import sys

    monkeypatch.setattr(sys, "path", [p for p in sys.path if not p.startswith(str(root))])
    for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
        monkeypatch.delitem(sys.modules, name)
    host = Host(root)
    host.open()
    try:
        import app.backends as backends  # the module the host imported from the bundle

        assert backends.SEEN["queue"] == {"name": "jobs", "token": "t0k"}
        host.broker.submit_queue("jobs", "a")
        host.broker.submit_queue("jobs", "fail")
        host.pump_queues(time.time())
        assert (tmp_path / "out.txt").read_text() == "a,"
        assert [m["body"] for m in backends.QUEUES["jobs"]] == ["fail"]
        host.pump_queues(time.time())
        assert backends.QUEUES["jobs"] == [] and host.broker.queue_depth("jobs-dlq") == 1
        assert host.stats()["queues"]["jobs"] is None  # custom class without depth()

        host.broker.put_object("media", "in/x.csv", b"1,2")
        host.pump_storage(time.time())
        assert (tmp_path / "media.txt").read_text() == "created:in/x.csv"
        assert host.broker.get_object("media", "in/x.csv") == b"1,2"
        host.broker.delete_object("media", "in/x.csv")
        host.pump_storage(time.time())
        assert (tmp_path / "media.txt").read_text() == "deleted:in/x.csv"
    finally:
        host.executor.shutdown()
        host.logs.close()


def test_missing_secret_variable_stops_the_host_with_a_clear_error(make_project, tmp_path, monkeypatch):
    root = _host(make_project, tmp_path)
    monkeypatch.delenv("BACKEND_TOKEN", raising=False)
    with pytest.raises(ValueError, match="BACKEND_TOKEN"):
        Host(root)
