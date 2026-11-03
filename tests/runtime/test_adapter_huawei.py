import base64
import json
import sys
import types

import pytest

from py_serverless_kit import BatchResult
from py_serverless_kit.runtime.adapters import huawei
from py_serverless_kit.runtime.adapters.base import envelope
from py_serverless_kit.runtime.batch import BatchFailure
from py_serverless_kit.runtime.manifest import BundleManifest, FunctionSpec, Route, set_manifest

APIG = {
    "body": base64.b64encode(b"hello").decode(),
    "requestContext": {"apiId": "a1", "requestId": "r1", "stage": "RELEASE", "sourceIp": "9.9.9.9"},
    "queryStringParameters": {"lang": "en"},
    "httpMethod": "PUT",
    "pathParameters": {"name": "ada"},
    "headers": {"content-type": "text/plain"},
    "path": "/hello/ada",
    "isBase64Encoded": True,
}

TIMER = {
    "version": "v1.0",
    "time": "2026-10-15T08:00:00+08:00",
    "trigger_type": "TIMER",
    "trigger_name": "timer-0",
    "user_event": json.dumps(envelope("schedule", None, source="huawei.timer")),
}

OBS = {
    "Records": [
        {
            "eventVersion": "3.0",
            "eventSource": "ObjectStorage",
            "eventRegion": "cn-north-4",
            "eventTime": "2026-10-15T08:00:00.000Z",
            "eventName": "ObjectCreated:Put",
            "obs": {
                "bucket": {"name": "uploads"},
                "object": {"key": "in%2Fa.csv", "eTag": "e", "size": 5, "sequencer": "s1"},
            },
        }
    ]
}

SMN = {
    "record": [
        {
            "event_version": "1.0",
            "smn": {
                "topic_urn": "urn:smn:cn-north-4:p:events",
                "timestamp": "2026-10-15T08:00:00Z",
                "message_attributes": {"kind": "a"},
                "message": "fail",
                "type": "notification",
                "message_id": "m1",
                "subject": "s",
            },
            "event_subscription_urn": "urn:fss:...",
            "event_source": "smn",
        }
    ],
    "functionname": "demo-dev-worker",
}


class FakeCtx:
    def getRequestID(self):  # noqa: N802 - FunctionGraph API
        return "req-ctx"

    def getRemainingTimeInMilliSeconds(self):  # noqa: N802
        return 5000

    def getFunctionName(self):  # noqa: N802
        return "demo-dev-api"

    def getMemorySize(self):  # noqa: N802
        return "256"


def test_apig_event():
    event = huawei.to_event(APIG, FakeCtx())
    assert event.type == "http"
    assert (event.http.method, event.http.path, event.http.text()) == ("PUT", "/hello/ada", "hello")
    assert event.http.path_params == {"name": "ada"}
    assert event.http.query == {"lang": "en"}
    assert event.http.source_ip == "9.9.9.9"


def test_timer_obs_smn():
    timer = huawei.to_event(TIMER)
    assert timer.type == "schedule" and timer.data is None and timer.source == "timer-0"
    obs = huawei.to_event(OBS)
    assert obs.type == "storage"
    assert (obs.records[0].bucket, obs.records[0].key, obs.records[0].action) == ("uploads", "in/a.csv", "created")
    smn = huawei.to_event(SMN)
    assert smn.type == "topic"
    assert smn.records[0].text() == "fail" and smn.records[0].attributes["kind"] == "a"


def test_context_and_invoke():
    ctx = huawei.to_context(FakeCtx(), "api")
    assert ctx.request_id == "req-ctx" and ctx.memory_mb == 256 and ctx.remaining_time_ms() == 5000
    assert huawei.to_event({"x": 1}).type == "invoke"
    assert huawei.to_event(json.dumps(envelope("invoke", 5))).data == 5


@pytest.fixture
def app_module(monkeypatch):
    mod = types.ModuleType("hw_app")

    def api(event, ctx):
        return f"hi {event.http.path_params['name']}"

    def worker(event, ctx):
        return BatchResult.of(r for r in event.records if r.text() == "fail")

    mod.api, mod.worker = api, worker
    monkeypatch.setitem(sys.modules, "hw_app", mod)
    set_manifest(
        BundleManifest(
            provider="huawei",
            functions={
                "api": FunctionSpec("api", "hw_app.api", [Route("ANY", "/hello/{name}")]),
                "worker": FunctionSpec("worker", "hw_app.worker"),
            },
        )
    )
    return mod


def test_handler_end_to_end(app_module, monkeypatch):
    monkeypatch.setenv("PSKIT_FUNCTION", "api")
    out = huawei.handler(APIG, FakeCtx())
    assert out == {
        "statusCode": 200,
        "isBase64Encoded": False,
        "headers": {"content-type": "text/plain; charset=utf-8"},
        "body": "hi ada",
    }
    monkeypatch.setenv("PSKIT_FUNCTION", "worker")
    with pytest.raises(BatchFailure):
        huawei.handler(SMN, FakeCtx())
