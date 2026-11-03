from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

import pytest

from py_serverless_kit import Event
from py_serverless_kit.runtime import manifest
from py_serverless_kit.runtime.adapters import cloudflare as cf
from py_serverless_kit.runtime.manifest import BundleManifest, FunctionSpec, Route

SEEN: Dict[str, Any] = {}


async def echo(event: Event, ctx):
    SEEN["event"] = event
    if event.http is not None:
        return {"id": event.http.path_params.get("id"), "body": event.http.json(default=None)}
    return {"type": event.type, "data": event.data}


class FakeHeaders:
    def __init__(self, data):
        self._data = data

    def items(self):
        return iter(self._data.items())


class FakeRequest:
    def __init__(self, method="GET", url="https://x.workers.dev/users/1", body="", headers=None):
        self.method = method
        self.url = url
        self.headers = FakeHeaders(headers or {})
        self._body = body

    async def text(self):
        return self._body


class Controller:
    cron = "*/5 * * * *"
    scheduledTime = 1_700_000_000_000


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    SEEN.clear()
    monkeypatch.setenv("PSKIT_FUNCTION", "users")
    manifest.set_manifest(
        BundleManifest(
            provider="cloudflare",
            functions={
                "users": FunctionSpec(name="users", handler=f"{__name__}.echo", routes=[Route("ANY", "/users/{id}")])
            },
        )
    )


def test_fetch_with_async_handler():
    req = FakeRequest("POST", "https://x.workers.dev/users/9?a=1", '{"k": 1}', {"CF-Ray": "ray1"})
    out = asyncio.run(cf.fetch(req))
    assert out["status"] == 200
    assert json.loads(out["body"]) == {"id": "9", "body": {"k": 1}}
    assert SEEN["event"].http.query == {"a": "1"}


def test_fetch_envelope():
    body = json.dumps({"__pskit": "invoke", "data": 3})
    out = asyncio.run(cf.fetch(FakeRequest("POST", "https://x/", body)))
    assert json.loads(out["body"]) == {"type": "invoke", "data": 3}


def test_scheduled_uses_configured_inputs(monkeypatch):
    monkeypatch.setenv("A", "0")  # restored by monkeypatch after configure() overwrites it
    cf.configure("users", {"A": "1"}, {"*/5 * * * *": {"job": "sync"}})
    try:
        result = asyncio.run(cf.scheduled(Controller()))
    finally:
        cf.SCHEDULE_INPUTS.clear()
    assert result == {"type": "schedule", "data": {"job": "sync"}}
    assert SEEN["event"].time.year == 2023
