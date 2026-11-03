"""Native payloads the on-premises adapter accepts."""

from __future__ import annotations

import json
from typing import Any, Dict

from py_serverless_kit import Event
from py_serverless_kit.runtime import manifest
from py_serverless_kit.runtime.adapters import onprem
from py_serverless_kit.runtime.adapters.base import envelope
from py_serverless_kit.runtime.manifest import BundleManifest, FunctionSpec, Route

SEEN: Dict[str, Any] = {}


def echo(event: Event, ctx):
    SEEN["event"] = event
    SEEN["ctx"] = ctx
    if event.http is not None:
        return {"path": event.http.path, "body": event.http.json(default=None)}
    if event.records:
        return {"type": event.type, "n": len(event.records), "id": event.records[0].id}
    return {"type": event.type, "data": event.data}


class FakeContext:
    request_id = "req-1"

    def get_remaining_time_in_millis(self):
        return 4000


def test_http_schedule_and_queue(monkeypatch):
    SEEN.clear()
    monkeypatch.setenv("PSKIT_FUNCTION", "api")
    manifest.set_manifest(
        BundleManifest(
            provider="onprem",
            functions={"api": FunctionSpec(name="api", handler=f"{__name__}.echo", routes=[Route("POST", "/jobs")])},
        )
    )
    out = onprem.main(
        {"http": {"method": "POST", "path": "/jobs", "headers": {"content-type": "application/json"}, "body": "{}"}},
        FakeContext(),
    )
    assert out["statusCode"] == 200
    assert json.loads(out["body"])["path"] == "/jobs"
    assert SEEN["ctx"].request_id == "req-1"

    scheduled = onprem.main(envelope("schedule", {"report": "daily"}), FakeContext())
    assert json.loads(scheduled["body"]) == {"type": "schedule", "data": {"report": "daily"}}

    queued = onprem.main(
        {"type": "queue", "records": [{"id": "m1", "body": {"kind": "email"}}]},
        FakeContext(),
    )
    assert json.loads(queued["body"])["id"] == "m1"
