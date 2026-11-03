import base64
import json
import sys
import types

import pytest

from py_serverless_kit import BatchResult, Response
from py_serverless_kit.runtime import dispatch
from py_serverless_kit.runtime.adapters import aws
from py_serverless_kit.runtime.adapters.base import envelope
from py_serverless_kit.runtime.manifest import BundleManifest, set_manifest

HTTP_V2 = {
    "version": "2.0",
    "routeKey": "GET /users/{id}",
    "rawPath": "/users/42",
    "rawQueryString": "a=1",
    "cookies": ["sid=1"],
    "headers": {"content-type": "application/json", "x-forwarded-for": "1.2.3.4"},
    "queryStringParameters": {"a": "1,2"},
    "pathParameters": {"id": "42"},
    "requestContext": {"http": {"method": "GET", "path": "/users/42", "sourceIp": "1.2.3.4"}},
    "body": base64.b64encode(b'{"x": 1}').decode(),
    "isBase64Encoded": True,
}

HTTP_V1 = {
    "resource": "/users/{id}",
    "path": "/users/42",
    "httpMethod": "POST",
    "headers": {"Content-Type": "application/json"},
    "multiValueHeaders": {"Content-Type": ["application/json"]},
    "queryStringParameters": {"a": "2"},
    "multiValueQueryStringParameters": {"a": ["1", "2"]},
    "pathParameters": {"id": "42"},
    "requestContext": {"identity": {"sourceIp": "5.6.7.8"}},
    "body": '{"y": 2}',
    "isBase64Encoded": False,
}

SQS = {
    "Records": [
        {
            "messageId": "m1",
            "body": '{"job": 1}',
            "attributes": {"ApproximateReceiveCount": "1"},
            "messageAttributes": {"kind": {"stringValue": "a", "dataType": "String"}},
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:us-east-1:1:jobs",
        },
        {"messageId": "m2", "body": "fail", "eventSource": "aws:sqs", "eventSourceARN": "arn:aws:sqs:us-east-1:1:jobs"},
    ]
}

SNS = {
    "Records": [
        {
            "EventSource": "aws:sns",
            "Sns": {
                "MessageId": "s1",
                "TopicArn": "arn:aws:sns:us-east-1:1:events",
                "Message": "hello",
                "Timestamp": "2024-01-01T00:00:00.000Z",
                "MessageAttributes": {"k": {"Type": "String", "Value": "v"}},
            },
        }
    ]
}

S3 = {
    "Records": [
        {
            "eventSource": "aws:s3",
            "eventName": "ObjectRemoved:Delete",
            "eventTime": "2024-01-01T00:00:00.000Z",
            "s3": {"bucket": {"name": "b"}, "object": {"key": "dir/my+file.csv", "size": 10, "eTag": "e"}},
        }
    ]
}


class FakeCtx:
    aws_request_id = "req-123"
    function_name = "demo-dev-hello"
    memory_limit_in_mb = "256"

    def get_remaining_time_in_millis(self):
        return 5000


def test_http_v2():
    ev = aws.to_event(HTTP_V2, FakeCtx())
    assert ev.type == "http"
    assert ev.http.method == "GET" and ev.http.path == "/users/42"
    assert ev.http.json() == {"x": 1}
    assert ev.http.path_params == {"id": "42"}
    assert ev.http.multi_query == {"a": ["1", "2"]}
    assert ev.http.cookies == {"sid": "1"}
    assert ev.http.source_ip == "1.2.3.4"


def test_http_v1():
    ev = aws.to_event(HTTP_V1)
    assert ev.http.method == "POST"
    assert ev.http.json() == {"y": 2}
    assert ev.http.multi_query == {"a": ["1", "2"]}
    assert ev.http.source_ip == "5.6.7.8"


def test_sqs_sns_s3():
    q = aws.to_event(SQS)
    assert q.type == "queue" and [r.id for r in q.records] == ["m1", "m2"]
    assert q.records[0].json() == {"job": 1} and q.records[0].attributes["kind"] == "a"
    t = aws.to_event(SNS)
    assert t.type == "topic" and t.records[0].body == "hello" and t.records[0].attributes == {"k": "v"}
    s = aws.to_event(S3)
    assert s.type == "storage"
    rec = s.records[0]
    assert (rec.bucket, rec.key, rec.size, rec.action) == ("b", "dir/my file.csv", 10, "deleted")


def test_envelopes_and_invoke():
    sched = aws.to_event(envelope("schedule", {"report": "x"}, source="aws.scheduler"))
    assert sched.type == "schedule" and sched.data == {"report": "x"} and sched.source == "aws.scheduler"
    wf = aws.to_event({"__pskit": "workflow", "data": {"n": 1}})
    assert wf.type == "workflow" and wf.data == {"n": 1}
    raw = aws.to_event({"anything": True})
    assert raw.type == "invoke" and raw.data == {"anything": True}
    eb = aws.to_event({"source": "aws.events", "detail-type": "Scheduled Event", "detail": {}})
    assert eb.type == "schedule"


def test_context():
    ctx = aws.to_context(FakeCtx(), "hello")
    assert ctx.request_id == "req-123" and ctx.memory_mb == 256 and ctx.remaining_time_ms() == 5000


def test_native_http_response_with_cookies():
    ev = aws.to_event(HTTP_V2)
    out = aws.to_native(Response.json({"a": 1}).set_cookie("s", "1"), ev)
    assert out["statusCode"] == 200 and json.loads(out["body"]) == {"a": 1}
    assert out["cookies"][0].startswith("s=1")
    v1 = aws.to_native(Response.text("x").set_cookie("s", "1"), aws.to_event(HTTP_V1))
    assert v1["multiValueHeaders"]["set-cookie"]


def test_batch_failures():
    out = aws.to_native(BatchResult(["m2"]), aws.to_event(SQS))
    assert out == {"batchItemFailures": [{"itemIdentifier": "m2"}]}


@pytest.fixture
def app_module(monkeypatch):
    mod = types.ModuleType("aws_app")

    def hello(event, ctx):
        return {"id": event.http.path_params["id"], "req": ctx.request_id}

    def worker(event, ctx):
        return BatchResult.of(r for r in event.records if r.body == "fail")

    mod.hello, mod.worker = hello, worker
    monkeypatch.setitem(sys.modules, "aws_app", mod)
    dispatch._HANDLERS.clear()
    set_manifest(
        BundleManifest.from_dict(
            {
                "functions": {
                    "hello": {"handler": "aws_app.hello", "routes": [{"method": "GET", "path": "/users/{id}"}]},
                    "worker": {"handler": "aws_app.worker"},
                }
            }
        )
    )


def test_handler_end_to_end(app_module, monkeypatch):
    monkeypatch.setenv("PSKIT_FUNCTION", "hello")
    out = aws.handler(HTTP_V2, FakeCtx())
    assert out["statusCode"] == 200
    assert json.loads(out["body"]) == {"id": "42", "req": "req-123"}
    monkeypatch.setenv("PSKIT_FUNCTION", "worker")
    assert aws.handler(SQS, FakeCtx()) == {"batchItemFailures": [{"itemIdentifier": "m2"}]}
