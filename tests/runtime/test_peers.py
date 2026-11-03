"""Calls between placement groups (runtime/peers.py)."""

from __future__ import annotations

import pytest

from py_serverless_kit.runtime.batch import BatchResult
from py_serverless_kit.runtime.peers import PeerError, Peers, decode_result, encode_error, encode_result
from py_serverless_kit.runtime.response import Response

SPEC = {
    "group": "gpu", "default_group": "api", "peer_token": "t" * 40,
    "groups": {"api": {"url": "http://10.0.0.5:8080/"}, "gpu": {"url": "http://10.0.0.7:8080"}},
    "function_groups": {"hello": {"group": "api", "timeout": 10}, "resize": {"group": "gpu", "timeout": 60}},
    "owners": {"queue:jobs": "gpu", "storage:uploads": "api", "topic:events": ["api", "gpu"]},
}


def test_where_things_are():
    peers = Peers.from_spec(SPEC)
    assert peers is not None and Peers.from_spec({"functions": {}}) is None
    assert peers.urls["api"] == "http://10.0.0.5:8080"
    assert peers.remote("hello") == "api" and peers.remote("resize") is None and peers.remote("nope") is None
    assert peers.owner("queue", "jobs") is None and peers.owner("storage", "uploads") == "api"
    assert peers.owner("queue", "adhoc") is None  # not declared: kept where it is used
    assert peers.subscribers("topic", "events") == ["api", "gpu"] and peers.subscribers("topic", "other") == ["gpu"]
    assert peers.timeout("hello") == 40.0


def test_results_round_trip():
    resp = Response(201, b"made", {"content-type": "text/plain"})
    resp.cookies = ["a=1", "b=2"]
    back = decode_result(encode_result(resp))
    assert isinstance(back, Response) and back.status == 201 and back.body == b"made" and back.cookies == ["a=1", "b=2"]
    assert decode_result(encode_result(BatchResult(failed=["m1"]))).failed == ["m1"]
    assert decode_result(encode_result({"ok": 1})) == {"ok": 1}


def test_an_error_keeps_its_type_for_workflow_retry_and_catch():
    class OutOfStock(Exception):
        pass

    with pytest.raises(PeerError) as caught:
        decode_result(encode_error(OutOfStock("none left")), "gpu")
    assert caught.value.error == "OutOfStock" and str(caught.value) == "none left" and caught.value.group == "gpu"
