"""Tracked workflow executions: executor, stores and orchestrator responses."""

from __future__ import annotations

import json
import threading
import time

import pytest

from py_serverless_kit.runtime import workflow as wf_mod
from py_serverless_kit.runtime.context import Context
from py_serverless_kit.runtime.event import Event, EventType, Headers, HttpRequest
from py_serverless_kit.runtime.executions import (
    Executor,
    FileExecutionStore,
    MemoryExecutionStore,
    valid_id,
)
from py_serverless_kit.runtime.manifest import BundleManifest, set_manifest
from py_serverless_kit.runtime.response import Response

ONE_TASK = {"start_at": "A", "states": {"A": {"type": "task", "function": "f", "end": True}}}
WAIT = {
    "start_at": "A",
    "states": {
        "A": {"type": "task", "function": "f", "next": "W"},
        "W": {"type": "wait", "seconds": 60, "next": "B"},
        "B": {"type": "pass", "end": True},
    },
}


def _wait(fn, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("timed out")


def _executor(store=None, runner=None, **workflows):
    return Executor(store or MemoryExecutionStore(), workflows, runner or (lambda fn, data: {"ran": fn, "in": data}))


def test_ids_are_sortable_and_validated():
    first = wf_mod.new_execution_id()
    time.sleep(0.002)
    second = wf_mod.new_execution_id()
    assert first < second and valid_id(first)
    assert not valid_id("../x") and not valid_id("") and not valid_id("ABC")


def test_wait_returns_the_finished_record():
    ex = _executor(flow={"definition": ONE_TASK})
    record = ex.start("flow", {"x": 1}, wait=True)
    assert record["status"] == "SUCCEEDED"
    assert record["output"] == {"ran": "f", "in": {"x": 1}}
    assert record["input"] == {"x": 1} and record["duration_ms"] is not None
    assert "_started" not in record and "_started" not in ex.get(record["execution_id"])
    assert ex.result_body(record)["output"] == {"ran": "f", "in": {"x": 1}}


def test_background_run_failure_and_unknown_workflow():
    def boom(fn, data):
        raise ValueError("bad input")

    ex = _executor(runner=boom, flow={"definition": ONE_TASK})
    started = ex.start("flow", None)
    assert started["status"] == "RUNNING" and set(started) >= {"execution_id", "workflow", "started_at"}
    record = _wait(lambda: (lambda r: r if r["status"] != "RUNNING" else None)(ex.get(started["execution_id"])))
    assert record["status"] == "FAILED" and record["error"] == "ValueError" and record["cause"] == "bad input"
    assert "output" not in ex.result_body(record) and ex.result_body(record)["error"] == "ValueError"
    with pytest.raises(KeyError, match="unknown workflow"):
        ex.start("nope")
    ex.shutdown()


def test_timeout_marks_timed_out():
    ex = _executor(flow={"definition": WAIT, "timeout": 0.2})
    record = ex.start("flow", {}, wait=True)
    assert record["status"] == "TIMED_OUT" and record["error"] == wf_mod.TIMEOUT_ERROR


def test_cancel_stops_a_waiting_run():
    ex = _executor(flow={"definition": WAIT})
    started = ex.start("flow", {})
    eid = started["execution_id"]
    _wait(lambda: (ex.get(eid) or {}).get("current_state") == "W")
    assert ex.cancel(eid)["cancel_requested"] is True
    record = _wait(lambda: (lambda r: r if r["status"] != "RUNNING" else None)(ex.get(eid)))
    assert record["status"] == "CANCELLED"
    assert ex.cancel(eid)["status"] == "CANCELLED"  # idempotent once finished
    assert ex.cancel("0" * 28) is None


def test_list_filters_and_pages_newest_first():
    ex = _executor(a={"definition": ONE_TASK}, b={"definition": ONE_TASK})
    ids = [ex.start(name, i, wait=True)["execution_id"] for i, name in enumerate("abab")]
    listed = ex.list(workflow="a")
    assert listed["total"] == 2 and [i["execution_id"] for i in listed["items"]] == [ids[2], ids[0]]
    page = ex.list(limit=1, offset=1)
    assert page["total"] == 4 and page["items"][0]["execution_id"] == ids[2]
    assert ex.list(status="failed")["total"] == 0
    assert set(listed["items"][0]) == {
        "execution_id",
        "workflow",
        "status",
        "started_at",
        "stopped_at",
        "duration_ms",
        "current_state",
        "source",
        "console",
    }


def test_retention_prunes_finished_runs_only():
    store = MemoryExecutionStore(retention=2)
    ex = _executor(store=store, flow={"definition": ONE_TASK})
    for i in range(4):
        ex.start("flow", i, wait=True)
    assert ex.list()["total"] == 2


def test_file_store_survives_reload_and_prunes(tmp_path):
    store = FileExecutionStore(tmp_path, retention=3)
    ex = _executor(store=store, flow={"definition": ONE_TASK})
    ids = [ex.start("flow", {"n": i}, wait=True)["execution_id"] for i in range(5)]
    assert len(list(tmp_path.glob("*.json"))) == 3
    (tmp_path / "junk.json").write_text("{not json", "utf-8")
    (tmp_path / ("f" * 20 + ".json")).write_text("{not json", "utf-8")
    again = FileExecutionStore(tmp_path)
    items, total = again.list()
    assert total == 3 and [i["execution_id"] for i in items] == ids[:1:-1]
    assert again.get(ids[-1])["output"] == {"ran": "f", "in": {"n": 4}}
    assert again.get("../../etc/passwd") is None and again.get(ids[0]) is None


def test_recover_marks_stale_running_records(tmp_path):
    store = FileExecutionStore(tmp_path)
    record = {"execution_id": wf_mod.new_execution_id(), "workflow": "flow", "status": "RUNNING", "history": []}
    store.save(record)
    ex = _executor(store=FileExecutionStore(tmp_path), flow={"definition": ONE_TASK})
    assert ex.recover() == 1
    assert ex.get(record["execution_id"])["status"] == "ABORTED"
    assert ex.recover() == 0


def test_parallel_branches_record_history_safely():
    definition = {
        "start_at": "P",
        "states": {
            "P": {
                "type": "map",
                "items_path": "$.items",
                "iterator": ONE_TASK,
                "end": True,
            }
        },
    }
    calls = []
    lock = threading.Lock()

    def runner(fn, data):
        with lock:
            calls.append(data)
        return data * 2

    ex = _executor(runner=runner, flow={"definition": definition})
    record = ex.start("flow", {"items": list(range(50))}, wait=True)
    assert record["status"] == "SUCCEEDED" and record["output"] == [i * 2 for i in range(50)]
    assert len(calls) == 50 and sum(1 for h in record["history"] if h["event"] == "enter") == 51


def test_history_is_capped(monkeypatch):
    from py_serverless_kit.runtime import executions

    monkeypatch.setattr(executions, "MAX_HISTORY", 5)
    definition = {
        "start_at": "P",
        "states": {"P": {"type": "map", "items_path": "$", "iterator": ONE_TASK, "end": True}},
    }
    ex = _executor(flow={"definition": definition})
    record = ex.start("flow", list(range(10)), wait=True)
    assert len(record["history"]) == 5 and record["history_truncated"] > 0


# ------------------------------------------------------------------ orchestrate


@pytest.fixture
def manifest():
    set_manifest(
        BundleManifest(
            functions={},
            workflows={"flow": {"orchestrator": "flow-orchestrator", "definition": ONE_TASK}},
        )
    )
    yield
    set_manifest(None)
    wf_mod.install_executor(None)


def _http(body=b"{}", query=None, headers=None):
    req = HttpRequest(
        method="POST", path="/workflows/flow", headers=Headers(headers or {}), query=query or {}, body=body
    )
    return Event(type=EventType.HTTP, function="flow-orchestrator", http=req)


def test_cloud_orchestrator_returns_execution_id(manifest, monkeypatch):
    monkeypatch.setattr(wf_mod, "in_process_runner", lambda provider: lambda fn, data: {"ok": True})
    body = wf_mod.orchestrate(_http(), Context(function="flow-orchestrator"))
    assert body["status"] == "SUCCEEDED" and valid_id(body["execution_id"]) and body["output"] == {"ok": True}

    def boom(fn, data):
        raise RuntimeError("no")

    monkeypatch.setattr(wf_mod, "in_process_runner", lambda provider: boom)
    resp = wf_mod.orchestrate(_http(), Context(function="flow-orchestrator"))
    assert isinstance(resp, Response) and resp.status == 500
    failure = json.loads(resp.render()[2])
    assert failure["status"] == "FAILED" and valid_id(failure["execution_id"])


def test_orchestrator_with_executor_is_async_unless_waiting(manifest, monkeypatch):
    monkeypatch.setattr(wf_mod, "in_process_runner", lambda provider: lambda fn, data: {"sync": True})
    ex = _executor(runner=lambda fn, data: {"async": True}, flow={"definition": ONE_TASK})
    wf_mod.install_executor(ex)
    resp = wf_mod.orchestrate(_http(), Context(function="flow-orchestrator"))
    assert isinstance(resp, Response) and resp.status == 202
    eid = json.loads(resp.render()[2])["execution_id"]
    assert _wait(lambda: (ex.get(eid) or {}).get("status") == "SUCCEEDED")
    assert ex.get(eid)["output"] == {"async": True}

    for event in (_http(query={"wait": "true"}), _http(headers={"prefer": "respond-async, wait=10"})):
        body = wf_mod.orchestrate(event, Context(function="flow-orchestrator"))
        assert body["status"] == "SUCCEEDED" and body["output"] == {"sync": True}  # in-thread runner
    invoked = wf_mod.orchestrate(
        Event(type=EventType.INVOKE, function="flow-orchestrator", data={"a": 1}), Context(function="flow-orchestrator")
    )
    assert invoked["status"] == "SUCCEEDED"
    assert ex.list()["total"] == 4
