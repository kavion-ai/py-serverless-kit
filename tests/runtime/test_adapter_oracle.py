from __future__ import annotations

import io
import json
from typing import Any, Dict

import pytest

from py_serverless_kit import Event
from py_serverless_kit.runtime import manifest
from py_serverless_kit.runtime.adapters import oracle
from py_serverless_kit.runtime.manifest import BundleManifest, FunctionSpec, Route

SEEN: Dict[str, Any] = {}


def echo(event: Event, ctx):
    SEEN["event"] = event
    if event.http is not None:
        http = event.http
        return {"id": http.path_params.get("id"), "q": http.query, "ua": http.headers.get("user-agent")}
    if event.records:
        return {"bucket": event.records[0].bucket, "key": event.records[0].key, "action": event.records[0].action}
    return {"type": event.type, "data": event.data}


class FakeCtx:
    def __init__(self, headers=None):
        self._headers = headers or {}

    def Headers(self):  # noqa: N802 - FDK naming
        return self._headers

    def CallID(self):  # noqa: N802
        return "call-1"


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    SEEN.clear()
    monkeypatch.setenv("PSKIT_FUNCTION", "users")
    manifest.set_manifest(
        BundleManifest(
            provider="oracle",
            functions={
                "users": FunctionSpec(name="users", handler=f"{__name__}.echo", routes=[Route("GET", "/users/{id}")])
            },
        )
    )


def test_api_gateway_request():
    ctx = FakeCtx(
        {
            "Fn-Http-Method": ["GET"],
            "Fn-Http-Request-Url": ["/demo/users/5?q=1"],
            "Fn-Http-H-User-Agent": ["curl"],
        }
    )
    out = oracle.handler(ctx, io.BytesIO(b""))
    # Without the FDK installed the adapter returns a plain dict.
    assert out["status"] == 200
    assert json.loads(out["body"]) == {"id": "5", "q": {"q": "1"}, "ua": "curl"}


def test_object_storage_cloud_event():
    payload = {
        "eventType": "com.oraclecloud.objectstorage.createobject",
        "eventID": "e1",
        "eventTime": "2024-01-01T00:00:00Z",
        "source": "ObjectStorage",
        "data": {"resourceName": "in/file.csv", "additionalDetails": {"bucketName": "uploads", "namespace": "ns"}},
    }
    out = oracle.handler(FakeCtx(), io.BytesIO(json.dumps(payload).encode()))
    assert json.loads(out["body"]) == {"bucket": "uploads", "key": "in/file.csv", "action": "created"}
    assert SEEN["event"].type == "storage"


def test_envelope_and_plain_invoke():
    out = oracle.handler(FakeCtx(), io.BytesIO(json.dumps({"__pskit": "workflow", "data": [1]}).encode()))
    assert json.loads(out["body"]) == {"type": "workflow", "data": [1]}
    out = oracle.handler(FakeCtx(), io.BytesIO(b'{"a": 1}'))
    assert json.loads(out["body"]) == {"type": "invoke", "data": {"a": 1}}
    out = oracle.handler(FakeCtx(), None)
    assert json.loads(out["body"]) == {"type": "invoke", "data": None}
