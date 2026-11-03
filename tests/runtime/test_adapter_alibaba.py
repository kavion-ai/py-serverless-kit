import base64
import json
import sys
import types

import pytest

from py_serverless_kit.runtime.adapters import alibaba
from py_serverless_kit.runtime.adapters.base import envelope
from py_serverless_kit.runtime.manifest import BundleManifest, FunctionSpec, Route, set_manifest

HTTP = {
    "version": "v1",
    "rawPath": "/users/42",
    "body": base64.b64encode(b'{"x": 1}').decode(),
    "isBase64Encoded": True,
    "headers": {"Content-Type": "application/json", "Origin": "https://app.example"},
    "queryParameters": {"a": "1", "tags": ["x", "y"]},
    "requestContext": {
        "accountId": "123",
        "domainName": "demo.cn-hangzhou.fcapp.run",
        "http": {"method": "GET", "path": "/users/42", "protocol": "HTTP/1.1", "sourceIp": "1.2.3.4"},
        "requestId": "req-1",
    },
}

TIMER = {
    "triggerTime": "2026-10-15T08:00:00Z",
    "triggerName": "timer-0",
    "payload": json.dumps(envelope("schedule", {"report": "weekly"}, source="alibaba.timer")),
}

OSS = {
    "events": [
        {
            "eventName": "ObjectCreated:PutObject",
            "eventTime": "2026-10-15T08:00:00.000Z",
            "oss": {"bucket": {"name": "uploads"}, "object": {"key": "in/a.csv", "size": 12, "eTag": "e"}},
            "responseElements": {"requestId": "r1"},
        }
    ]
}

MNS = {
    "TopicOwner": "123",
    "TopicName": "events",
    "MessageId": "m1",
    "Message": '{"k": 1}',
    "PublishTime": 1760515200000,
}


class FakeCtx:
    request_id = "req-ctx"
    region = "cn-hangzhou"

    class function:  # noqa: N801 - mimics FC's attribute layout
        name = "demo-dev-api"
        memory = 256
        timeout = 30


def test_http_event_from_bytes():
    event = alibaba.to_event(json.dumps(HTTP).encode(), FakeCtx())
    assert event.type == "http"
    assert event.http.method == "GET"
    assert event.http.path == "/users/42"
    assert event.http.query == {"a": "1", "tags": "y"}
    assert event.http.multi_query["tags"] == ["x", "y"]
    assert event.http.json() == {"x": 1}
    assert event.http.source_ip == "1.2.3.4"
    assert event.http.headers["content-type"] == "application/json"


def test_timer_unwraps_envelope_payload():
    event = alibaba.to_event(TIMER)
    assert event.type == "schedule"
    assert event.data == {"report": "weekly"}
    assert event.source == "timer-0"
    plain = alibaba.to_event({"triggerTime": "2026-10-15T08:00:00Z", "triggerName": "t", "payload": "hi"})
    assert plain.type == "schedule" and plain.data == "hi"


def test_oss_and_mns_records():
    event = alibaba.to_event(json.dumps(OSS).encode())
    assert event.type == "storage"
    rec = event.records[0]
    assert (rec.bucket, rec.key, rec.size, rec.action) == ("uploads", "in/a.csv", 12, "created")
    topic = alibaba.to_event(MNS)
    assert topic.type == "topic"
    assert topic.records[0].json() == {"k": 1}
    assert topic.source == "events"


def test_envelope_and_invoke():
    wf = alibaba.to_event(json.dumps(envelope("workflow", {"n": 1})).encode())
    assert wf.type == "workflow" and wf.data == {"n": 1}
    inv = alibaba.to_event(b'{"hello": "world"}')
    assert inv.type == "invoke" and inv.data == {"hello": "world"}


def test_context():
    ctx = alibaba.to_context(FakeCtx(), "api")
    assert ctx.request_id == "req-ctx"
    assert ctx.memory_mb == 256
    assert 0 < ctx.remaining_time_ms() <= 30000


@pytest.fixture
def app_module(monkeypatch):
    mod = types.ModuleType("ali_app")

    def api(event, ctx):
        return {"id": event.http.path_params["id"], "provider": event.provider}

    def tick(event, ctx):
        return {"type": event.type, "data": event.data}

    mod.api, mod.tick = api, tick
    monkeypatch.setitem(sys.modules, "ali_app", mod)
    set_manifest(
        BundleManifest(
            provider="alibaba",
            functions={
                "api": FunctionSpec("api", "ali_app.api", [Route("GET", "/users/{id}", {"origins": ["*"]})]),
                "tick": FunctionSpec("tick", "ali_app.tick"),
            },
        )
    )
    return mod


def test_handler_end_to_end(app_module, monkeypatch):
    monkeypatch.setenv("PSKIT_FUNCTION", "api")
    out = alibaba.handler(json.dumps(HTTP).encode(), FakeCtx())
    assert out["statusCode"] == 200
    assert out["isBase64Encoded"] is False
    assert json.loads(out["body"]) == {"id": "42", "provider": "alibaba"}
    assert out["headers"]["access-control-allow-origin"] == "*"

    monkeypatch.setenv("PSKIT_FUNCTION", "tick")
    assert alibaba.handler(TIMER, FakeCtx()) == {"type": "schedule", "data": {"report": "weekly"}}
