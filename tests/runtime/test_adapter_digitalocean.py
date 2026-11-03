from __future__ import annotations

import base64
import json
from typing import Any, Dict

import pytest

from py_serverless_kit import Event
from py_serverless_kit.runtime import manifest
from py_serverless_kit.runtime.adapters import digitalocean as do
from py_serverless_kit.runtime.manifest import BundleManifest, FunctionSpec, Route

SEEN: Dict[str, Any] = {}


def echo(event: Event, ctx):
    SEEN["event"] = event
    SEEN["ctx"] = ctx
    if event.http is not None:
        return {"id": event.http.path_params.get("id"), "q": event.http.query, "body": event.http.json(default=None)}
    return {"type": event.type, "data": event.data}


class FakeContext:
    activation_id = "act-1"

    def get_remaining_time_in_millis(self):
        return 5000


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    SEEN.clear()
    monkeypatch.setenv("PSKIT_FUNCTION", "users")
    manifest.set_manifest(
        BundleManifest(
            provider="digitalocean",
            functions={
                "users": FunctionSpec(name="users", handler=f"{__name__}.echo", routes=[Route("ANY", "/users/{id}")])
            },
        )
    )


def test_raw_web_request():
    event = {
        "http": {
            "method": "POST",
            "path": "/users/3",
            "headers": {"content-type": "application/json"},
            "queryString": "x=1",
            "body": json.dumps({"a": 1}),
            "isBase64Encoded": False,
        }
    }
    out = do.main(event, FakeContext())
    assert out["statusCode"] == 200
    assert json.loads(out["body"]) == {"id": "3", "q": {"x": "1"}, "body": {"a": 1}}
    assert SEEN["ctx"].request_id == "act-1"
    assert 0 < SEEN["ctx"].remaining_time_ms() <= 5000


def test_base64_body():
    payload = base64.b64encode(b"\xff\x00").decode()
    do.main({"http": {"method": "PUT", "path": "/users/1", "headers": {}, "body": payload, "isBase64Encoded": True}})
    assert SEEN["event"].http.body == b"\xff\x00"


def test_non_raw_web_merges_params():
    out = do.main({"http": {"method": "POST", "path": "/users/2", "headers": {}}, "name": "x"})
    assert json.loads(out["body"])["body"] == {"name": "x"}


def test_scheduled_trigger_envelope():
    out = do.main({"__pskit": "schedule", "data": {"r": 1}, "source": "digitalocean.scheduler"})
    assert json.loads(out["body"]) == {"type": "schedule", "data": {"r": 1}}
    assert SEEN["event"].source == "digitalocean.scheduler"


def test_plain_invoke():
    assert json.loads(do.main({"k": 2})["body"]) == {"type": "invoke", "data": {"k": 2}}
