from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional

import pytest

from py_serverless_kit import Event, NotFound
from py_serverless_kit.runtime import manifest
from py_serverless_kit.runtime.adapters import gcp
from py_serverless_kit.runtime.manifest import BundleManifest, FunctionSpec, Route

SEEN: Dict[str, Any] = {}


def echo(event: Event, ctx):
    SEEN["event"] = event
    if event.http is not None:
        if event.http.path_params.get("id") == "missing":
            raise NotFound("nope")
        return {"id": event.http.path_params.get("id"), "q": event.http.query, "body": event.http.json(default=None)}
    if event.data == {"boom": True}:
        raise ValueError("bad input")
    return {"type": event.type, "data": event.data}


class FakeArgs(dict):
    def getlist(self, key):
        value = self[key]
        return value if isinstance(value, list) else [value]


class FakeRequest:
    def __init__(self, method="GET", path="/", body=b"", headers: Optional[Dict[str, str]] = None, args=None):
        self.method = method
        self.path = path
        self._body = body
        self.headers = headers or {}
        self.args = FakeArgs(args or {})
        self.remote_addr = "10.0.0.1"

    def get_data(self):
        return self._body


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    SEEN.clear()
    monkeypatch.setenv("PSKIT_FUNCTION", "users")
    manifest.set_manifest(
        BundleManifest(
            provider="gcp",
            functions={
                "users": FunctionSpec(
                    name="users",
                    handler=f"{__name__}.echo",
                    routes=[Route("GET", "/users/{id}"), Route("POST", "/users/{id}")],
                )
            },
        )
    )


def test_http_with_path_params_relative_path():
    # GCP serves the function at https://.../<fn>/<rest>; the static prefix is stripped.
    body, status, headers = gcp.http(
        FakeRequest("GET", "/42", headers={"Function-Execution-Id": "abc"}, args={"x": "1"})
    )
    assert status == 200
    assert json.loads(body) == {"id": "42", "q": {"x": "1"}, "body": None}
    assert ("content-type", "application/json") in headers
    assert SEEN["event"].provider == "gcp"


def test_http_full_path_and_json_body():
    body, status, _ = gcp.http(
        FakeRequest("POST", "/users/7", body=b'{"a": 1}', headers={"Content-Type": "application/json"})
    )
    assert status == 200
    assert json.loads(body)["body"] == {"a": 1}


def test_http_error_mapping():
    body, status, _ = gcp.http(FakeRequest("GET", "/users/missing"))
    assert status == 404
    assert json.loads(body)["error"] == "nope"


def test_http_method_not_allowed():
    _, status, headers = gcp.http(FakeRequest("DELETE", "/users/1"))
    assert status == 405


def test_envelope_runs_as_workflow_event():
    payload = json.dumps({"__pskit": "workflow", "data": {"n": 1}}).encode()
    body, status, _ = gcp.http(FakeRequest("POST", "/", body=payload))
    assert status == 200
    assert json.loads(body) == {"type": "workflow", "data": {"n": 1}}
    assert SEEN["event"].http is None


def test_envelope_error_shape_for_workflows():
    payload = json.dumps({"__pskit": "workflow", "data": {"boom": True}}).encode()
    body, status, _ = gcp.http(FakeRequest("POST", "/", body=payload))
    assert status == 500
    assert json.loads(body) == {"errorType": "ValueError", "cause": "bad input"}


def _pubsub(data: bytes, attrs=None) -> Dict[str, Any]:
    return {
        "type": "google.cloud.pubsub.topic.v1.messagePublished",
        "source": "//pubsub.googleapis.com/projects/p/topics/jobs",
        "id": "evt-1",
        "time": "2024-05-01T10:00:00Z",
        "data": {
            "message": {"data": base64.b64encode(data).decode(), "attributes": attrs or {}, "messageId": "m-1"},
            "subscription": "projects/p/subscriptions/s",
        },
    }


def test_pubsub_queue_event(monkeypatch):
    monkeypatch.setenv("PSKIT_TRIGGER_KIND", "queue")
    event = gcp.to_cloud_event(_pubsub(b'{"job": 1}', {"k": "v"}), "users")
    assert event.type == "queue"
    rec = event.records[0]
    assert rec.id == "m-1" and rec.json() == {"job": 1} and rec.attributes == {"k": "v"}
    assert event.time.year == 2024


def test_pubsub_topic_default_and_scheduler_envelope():
    assert gcp.to_cloud_event(_pubsub(b"hi"), "users").type == "topic"
    env = json.dumps({"__pskit": "schedule", "data": {"r": 1}, "source": "gcp.scheduler"}).encode()
    event = gcp.to_cloud_event(_pubsub(env), "users")
    assert event.type == "schedule" and event.data == {"r": 1}


def test_storage_event_and_filters(monkeypatch):
    ce = {
        "type": "google.cloud.storage.object.v1.finalized",
        "source": "//storage.googleapis.com/projects/_/buckets/up",
        "id": "1",
        "data": {"bucket": "up", "name": "in/a.csv", "size": "12", "generation": "99", "contentType": "text/csv"},
    }
    event = gcp.to_cloud_event(ce, "users")
    rec = event.records[0]
    assert (event.type, rec.bucket, rec.key, rec.size, rec.action) == ("storage", "up", "in/a.csv", 12, "created")
    deleted = dict(ce, type="google.cloud.storage.object.v1.deleted")
    assert gcp.to_cloud_event(deleted, "users").records[0].action == "deleted"
    monkeypatch.setenv("PSKIT_STORAGE_SUFFIX", ".json")
    assert gcp.to_cloud_event(ce, "users") is None


def test_cloud_event_dispatch_object_style():
    class CE:
        def __init__(self, attrs, data):
            self._attrs = attrs
            self.data = data

        def __getitem__(self, key):
            return self._attrs[key]

    ce = CE({"type": "custom.event", "source": "s", "id": "x"}, {"hello": 1})
    assert gcp.cloud_event(ce) == {"type": "invoke", "data": {"hello": 1}}
