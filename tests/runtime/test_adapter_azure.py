from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from py_serverless_kit import BatchResult, Event
from py_serverless_kit.runtime import manifest
from py_serverless_kit.runtime.adapters import azure
from py_serverless_kit.runtime.batch import BatchFailure
from py_serverless_kit.runtime.manifest import BundleManifest, FunctionSpec, Route

SEEN: Dict[str, Any] = {}


def echo(event: Event, ctx):
    SEEN["event"] = event
    if event.http is not None:
        from py_serverless_kit import Response

        resp = Response.json({"id": event.http.path_params.get("id"), "path": event.http.path}, status=201)
        resp.set_cookie("sid", "1")
        return resp
    if event.records and event.records[0].text() == "fail":
        return BatchResult.of(event.records)
    return {"type": event.type, "data": event.data}


class FakeHttpResponse:
    def __init__(self, body=None, status_code=200, headers=None):
        self.body = body
        self.status_code = status_code
        self.headers = headers or {}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    SEEN.clear()
    pkg = types.ModuleType("azure")
    mod = types.ModuleType("azure.functions")
    mod.HttpResponse = FakeHttpResponse
    pkg.functions = mod
    monkeypatch.setitem(sys.modules, "azure", pkg)
    monkeypatch.setitem(sys.modules, "azure.functions", mod)
    manifest.set_manifest(
        BundleManifest(
            provider="azure",
            functions={
                "items": FunctionSpec(name="items", handler=f"{__name__}.echo", routes=[Route("POST", "/items/{id}")])
            },
        )
    )


class FakeHttpRequest:
    def __init__(self, method, url, body=b"", headers=None, params=None, route_params=None):
        self.method = method
        self.url = url
        self._body = body
        self.headers = headers or {}
        self.params = params or {}
        self.route_params = route_params or {}

    def get_body(self):
        return self._body


def test_http_request_response():
    req = FakeHttpRequest(
        "POST",
        "https://app.azurewebsites.net/items/5?x=1",
        b"{}",
        {"x-forwarded-for": "1.2.3.4:5555"},
        {"x": "1"},
        {"id": "5"},
    )
    resp = azure.http(req, "items")
    assert isinstance(resp, FakeHttpResponse)
    assert resp.status_code == 201
    assert json.loads(resp.body) == {"id": "5", "path": "/items/5"}
    assert resp.headers["content-type"] == "application/json"
    assert resp.headers["set-cookie"].startswith("sid=1")
    ev = SEEN["event"]
    assert ev.http.query == {"x": "1"} and ev.http.source_ip == "1.2.3.4"


def test_http_envelope_invoke():
    req = FakeHttpRequest("POST", "https://app/x", json.dumps({"__pskit": "invoke", "data": [1, 2]}).encode())
    resp = azure.http(req, "items")
    assert resp.status_code == 200
    assert json.loads(resp.body) == {"type": "invoke", "data": [1, 2]}


def test_timer():
    class Timer:
        past_due = False

    assert azure.timer(Timer(), "items", {"report": "weekly"}) == {"type": "schedule", "data": {"report": "weekly"}}


class QueueMsg:
    def __init__(self, body):
        self.id = "q1"
        self._body = body
        self.dequeue_count = 1
        self.insertion_time = datetime(2024, 1, 2, tzinfo=timezone.utc)

    def get_body(self):
        return self._body


def test_queue_event_and_batch_failure():
    event = azure.to_queue_event(QueueMsg(b'{"a": 1}'), "items")
    assert event.type == "queue" and event.records[0].json() == {"a": 1} and event.time.year == 2024
    with pytest.raises(BatchFailure):
        azure.queue(QueueMsg(b"fail"), "items")


def test_blob_event():
    class Blob:
        name = "uploads/in/a.csv"
        length = 10
        uri = "https://acct.blob.core.windows.net/uploads/in/a.csv"

    event = azure.to_blob_event(Blob(), "items", "uploads")
    rec = event.records[0]
    assert (event.type, rec.bucket, rec.key, rec.size, rec.action) == ("storage", "uploads", "in/a.csv", 10, "created")


def test_service_bus_event():
    class Msg:
        message_id = "m1"
        user_properties = {"k": "v"}
        enqueued_time_utc = datetime(2024, 3, 1, tzinfo=timezone.utc)

        def get_body(self):
            return b"hello"

    event = azure.to_service_bus_event(Msg(), "items")
    assert event.type == "topic"
    assert event.records[0].text() == "hello" and event.records[0].attributes == {"k": "v"}
    assert azure.service_bus(Msg(), "items") == {"type": "topic", "data": None}
