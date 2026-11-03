from __future__ import annotations

import base64
import json
from typing import Any, Dict

import pytest

from py_serverless_kit import Event, NotFound
from py_serverless_kit.runtime import manifest
from py_serverless_kit.runtime.adapters import ibm
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


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    SEEN.clear()
    monkeypatch.setenv("PSKIT_FUNCTION", "users")
    manifest.set_manifest(
        BundleManifest(
            provider="ibm",
            functions={
                "users": FunctionSpec(
                    name="users",
                    handler=f"{__name__}.echo",
                    routes=[Route("GET", "/users/{id}"), Route("POST", "/users/{id}")],
                )
            },
        )
    )


def test_http_get_with_query():
    out = ibm.main(
        {
            "__ce_method": "GET",
            "__ce_path": "/users/7",
            "__ce_headers": {"X-Request-Id": "abc"},
            "__ce_query": "a=1&a=2",
        }
    )
    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body == {"id": "7", "q": {"a": "2"}, "body": None}
    assert SEEN["event"].http.multi_query == {"a": ["1", "2"]}


def test_http_post_json_merged_into_params():
    # Code Engine merges JSON bodies into the params when no raw body is given.
    out = ibm.main({"__ce_method": "POST", "__ce_path": "/users/9", "__ce_headers": {}, "name": "ada"})
    assert json.loads(out["body"])["body"] == {"name": "ada"}


def test_openwhisk_prefix_and_base64_body():
    raw = base64.b64encode(b"\x00\x01").decode()
    ibm.main(
        {
            "__ow_method": "post",
            "__ow_path": "/users/1",
            "__ow_headers": {"content-type": "application/octet-stream"},
            "__ow_body": raw,
        }
    )
    assert SEEN["event"].http.body == b"\x00\x01"


def test_http_error_maps_to_status():
    out = ibm.main({"__ce_method": "GET", "__ce_path": "/users/missing", "__ce_headers": {}})
    assert out["statusCode"] == 404
    assert json.loads(out["body"])["error"] == "nope"


def test_envelope_over_http_is_invoke():
    out = ibm.main(
        {
            "__ce_method": "POST",
            "__ce_path": "/",
            "__ce_headers": {"content-type": "application/json"},
            "__ce_body": json.dumps({"__pskit": "invoke", "data": {"x": 1}}),
        }
    )
    assert out["statusCode"] == 200
    assert json.loads(out["body"]) == {"type": "invoke", "data": {"x": 1}}


def test_direct_params_and_errors():
    assert json.loads(ibm.main({"k": "v"})["body"]) == {"type": "invoke", "data": {"k": "v"}}
    wf = ibm.main({"__pskit": "workflow", "data": {"n": 1}})
    assert json.loads(wf["body"]) == {"type": "workflow", "data": {"n": 1}}
    failed = ibm.main({"__pskit": "invoke", "data": {"boom": True}})
    assert failed["statusCode"] == 500
    assert json.loads(failed["body"]) == {"errorType": "ValueError", "cause": "bad input"}
