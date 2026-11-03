"""Unit tests for handlers, run locally with the real dispatcher."""

import json

import pytest

from py_serverless_kit import Context, Event, Record
from py_serverless_kit.local import build_event, http_event

from app import handlers


def body(resp):
    status, headers, raw = resp.render()
    return status, json.loads(raw) if raw else None


@pytest.mark.parametrize(
    "payload,expected_total",
    [({"amount": 100}, 100), ({"amount": 100, "code": "welcome10"}, 90.0), ({"amount": 80, "code": "VIP25"}, 60.0)],
)
def test_price(runner, payload, expected_total):
    status, data = body(runner.invoke("price", http_event("POST", "/price", payload)))
    assert status == 200
    assert data["total"] == expected_total


def test_price_code_from_query(runner):
    _, data = body(runner.invoke("price", http_event("POST", "/price?code=VIP25", {"amount": 100})))
    assert data["code"] == "VIP25" and data["total"] == 75.0


@pytest.mark.parametrize("payload", [{"amount": -1}, {"amount": "ten"}, {}])
def test_price_validation(runner, payload):
    status, data = body(runner.invoke("price", http_event("POST", "/price", payload)))
    assert status == 400
    assert "amount" in data["error"]


def test_price_invalid_json(runner):
    event = http_event("POST", "/price", "{not json", headers={"content-type": "application/json"})
    status, _ = body(runner.invoke("price", event))
    assert status == 400


def test_queue_partial_failures(runner):
    event = build_event("queue", [{"id": 1}, "garbage", {"no_id": True}])
    result = runner.invoke("ingest", event)
    assert result.failed == ["local-1", "local-2"]


def test_topic_with_attributes():
    # Build the event yourself when you need fields build_event doesn't set.
    event = Event(
        type="topic",
        records=[
            Record(id="1", body='{"order_id": 7}', attributes={"event_type": "order.shipped"}),
            Record(id="2", body='{"order_id": 8}', attributes={"event_type": "order.created"}),
        ],
    )
    # Plain function call: handlers are ordinary Python functions.
    assert handlers.shipped_only(event, Context()) == [7]
