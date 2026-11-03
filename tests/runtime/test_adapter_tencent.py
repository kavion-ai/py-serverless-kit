import json
import sys
import types

import pytest

from py_serverless_kit import Response
from py_serverless_kit.runtime.adapters import tencent
from py_serverless_kit.runtime.adapters.base import envelope
from py_serverless_kit.runtime.manifest import BundleManifest, FunctionSpec, Route, set_manifest

APIGW = {
    "requestContext": {
        "serviceId": "service-abc",
        "path": "/users/{id}",
        "httpMethod": "POST",
        "requestId": "req-1",
        "sourceIp": "10.0.0.1",
        "stage": "release",
    },
    "headers": {"Content-Type": "application/json", "Host": "service-abc.gz.apigw.tencentcs.com"},
    "body": '{"name": "ada"}',
    "pathParameters": {"id": "42"},
    "queryStringParameters": {"q": "1"},
    "queryString": {"q": "1", "tag": ["a", "b"]},
    "path": "/users/42",
    "httpMethod": "POST",
    "isBase64Encoded": False,
}

TIMER = {
    "Type": "Timer",
    "TriggerName": "timer-1",
    "Time": "2026-10-15T08:00:00Z",
    "Message": json.dumps(envelope("schedule", {"report": "weekly"})),
}

COS = {
    "Records": [
        {
            "cos": {
                "cosSchemaVersion": "1.0",
                "cosObject": {
                    "url": "http://uploads-1250000000.cos.ap-guangzhou.myqcloud.com/in/a%20b.csv",
                    "meta": {"x-cos-request-id": "r1"},
                    "key": "/1250000000/uploads/in/a%20b.csv",
                    "size": 7,
                },
                "cosBucket": {"region": "gz", "name": "uploads", "appid": "1250000000"},
            },
            "event": {"eventName": "cos:ObjectCreated:Put", "eventTime": 1760515200},
        }
    ]
}

CTX = {
    "callbackWaitsForEmptyEventLoop": True,
    "memory_limit_in_mb": 128,
    "time_limit_in_ms": 3000,
    "request_id": "req-ctx",
    "function_name": "demo-dev-api",
    "namespace": "default",
}


def test_apigw_event():
    event = tencent.to_event(APIGW, CTX)
    assert event.type == "http"
    req = event.http
    assert (req.method, req.path) == ("POST", "/users/42")
    assert req.path_params == {"id": "42"}
    assert req.query["tag"] == "b" and req.multi_query["tag"] == ["a", "b"]
    assert req.json() == {"name": "ada"}
    assert req.source_ip == "10.0.0.1"


def test_query_string_as_text():
    evt = dict(APIGW, queryString="a=1&a=2&b=x", queryStringParameters=None)
    req = tencent.to_event(evt).http
    assert req.query == {"a": "2", "b": "x"}
    assert req.multi_query["a"] == ["1", "2"]


def test_timer_and_cos():
    timer = tencent.to_event(TIMER)
    assert timer.type == "schedule" and timer.data == {"report": "weekly"}
    no_msg = tencent.to_event({"Type": "Timer", "TriggerName": "t", "Time": "2026-10-15T08:00:00Z", "Message": ""})
    assert no_msg.data is None
    cos = tencent.to_event(COS)
    assert cos.type == "storage"
    rec = cos.records[0]
    assert (rec.bucket, rec.key, rec.size, rec.action) == ("uploads", "in/a b.csv", 7, "created")


def test_envelope_invoke_and_context():
    assert tencent.to_event(envelope("workflow", [1])).data == [1]
    assert tencent.to_event({"a": 1}).type == "invoke"
    ctx = tencent.to_context(CTX, "api")
    assert ctx.request_id == "req-ctx" and ctx.memory_mb == 128
    assert 0 < ctx.remaining_time_ms() <= 3000


def test_native_response_base64_for_binary():
    event = tencent.to_event(APIGW)
    out = tencent.to_native(Response.binary(b"\x00\x01", "image/png"), event)
    assert out["isBase64Encoded"] is True and out["statusCode"] == 200


@pytest.fixture
def app_module(monkeypatch):
    mod = types.ModuleType("tc_app")

    def api(event, ctx):
        return Response.json({"id": event.http.path_params["id"], **event.http.json()}, 201)

    mod.api = api
    monkeypatch.setitem(sys.modules, "tc_app", mod)
    set_manifest(
        BundleManifest(
            provider="tencent",
            functions={"api": FunctionSpec("api", "tc_app.api", [Route("POST", "/users/{id}")])},
        )
    )
    return mod


def test_main_handler_end_to_end(app_module, monkeypatch):
    monkeypatch.setenv("PSKIT_FUNCTION", "api")
    out = tencent.main_handler(APIGW, CTX)
    assert out["statusCode"] == 201
    assert json.loads(out["body"]) == {"id": "42", "name": "ada"}
    # wrong method on a matched path -> 405 from the portable router
    out = tencent.main_handler(dict(APIGW, httpMethod="DELETE"), CTX)
    assert out["statusCode"] == 405
