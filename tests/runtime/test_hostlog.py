"""On-prem host log buffer: querying, persistence, rotation and capture."""

from __future__ import annotations

import logging
import sys
import threading

from py_serverless_kit.runtime import hostlog
from py_serverless_kit.runtime.hostlog import LogBuffer


def _fill(buf: LogBuffer, n: int, **kw) -> None:
    for i in range(n):
        buf.append(kw.get("level", "INFO"), kw.get("source", "host"), f"line {i}", function=kw.get("function"))


def test_tail_since_and_before():
    buf = LogBuffer(capacity=100)
    _fill(buf, 10)
    tail = buf.query(limit=3)
    assert [e["message"] for e in tail["entries"]] == ["line 7", "line 8", "line 9"]
    assert tail["next"] == 10 and tail["more"] is True
    assert buf.query(since=10)["entries"] == [] and buf.query(since=10)["next"] == 10
    forward = buf.query(since=4, limit=2)
    assert [e["seq"] for e in forward["entries"]] == [5, 6] and forward["next"] == 6
    back = buf.query(before=5, limit=2)
    assert [e["seq"] for e in back["entries"]] == [3, 4] and back["more"] is True


def test_filters_level_function_source_and_text():
    buf = LogBuffer(capacity=100)
    buf.append("DEBUG", "function", "noisy", function="a")
    buf.append("INFO", "function", "Order Created", function="a")
    buf.append("ERROR", "invocation", "boom", function="b")
    buf.append("CRITICAL", "host", "disk full")
    assert [e["message"] for e in buf.query(level="warning")["entries"]] == ["boom", "disk full"]
    assert [e["message"] for e in buf.query(level="warn")["entries"]] == ["boom", "disk full"]
    assert [e["message"] for e in buf.query(function="a")["entries"]] == ["noisy", "Order Created"]
    assert [e["message"] for e in buf.query(source="invocation")["entries"]] == ["boom"]
    assert [e["message"] for e in buf.query(q="order")["entries"]] == ["Order Created"]


def test_since_advances_past_filtered_entries():
    buf = LogBuffer(capacity=100)
    _fill(buf, 5, function="x")
    result = buf.query(since=0, function="nope")
    assert result["entries"] == [] and result["next"] == 5
    assert buf.query(since=2, function="nope")["next"] == 5


def test_ring_buffer_reports_gaps():
    buf = LogBuffer(capacity=100)
    _fill(buf, 250)
    result = buf.query(since=10, limit=5)
    assert result["gap"] is True and result["entries"][0]["seq"] == 151 and result["oldest"] == 151


def test_invocation_tagging_is_per_thread():
    buf = LogBuffer(capacity=100)
    seen = {}

    def worker(name):
        with hostlog.invocation(name, f"req-{name}"):
            buf.append("INFO", "function", f"from {name}")
        seen[name] = True

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    buf.append("INFO", "host", "untagged")
    by_msg = {e["message"]: e for e in buf.query()["entries"]}
    assert by_msg["from b"]["function"] == "b" and by_msg["from b"]["request_id"] == "req-b"
    assert by_msg["untagged"]["function"] is None


def test_persistence_restore_and_rotation(tmp_path):
    path = tmp_path / "logs" / "host.jsonl"
    buf = LogBuffer(path, capacity=100, max_bytes=64 * 1024, backups=2)
    big = "x" * 2000
    for i in range(120):
        buf.append("INFO", "host", f"{i} {big}")
    buf.close()
    assert path.with_name("host.jsonl.1").exists()
    again = LogBuffer(path, capacity=100, max_bytes=64 * 1024, backups=2)
    assert again.last_seq == 120
    assert again.query(limit=1)["entries"][0]["message"].startswith("119 ")
    assert again.append("INFO", "host", "after restart") == 121
    again.close()


def test_long_messages_and_bad_fields_are_safe():
    buf = LogBuffer(capacity=100)
    buf.append("INFO", "host", "y" * 50000, fields={"obj": object()})
    entry = buf.query()["entries"][0]
    assert len(entry["message"]) < 17000 and "more characters" in entry["message"]
    assert isinstance(entry["fields"]["obj"], str)
    buf.append("weird", "nowhere", "z")
    assert buf.query()["entries"][-1]["level"] == "INFO" and buf.query()["entries"][-1]["source"] == "host"


def test_install_captures_logging_and_streams_once():
    buf = LogBuffer(capacity=100)
    original = sys.stdout
    hostlog.install(buf)
    try:
        hostlog.install(buf)  # idempotent
        logging.getLogger("thirdparty").warning("careful %s", 1)
        with hostlog.invocation("fn", "r1"):
            print("hello", "world")
            sys.stdout.write("partial ")
            sys.stdout.write("line\n")
    finally:
        hostlog.uninstall()
    assert sys.stdout is original
    messages = [(e["source"], e["message"], e["function"]) for e in buf.query()["entries"]]
    assert ("host", "careful 1", None) in messages
    assert ("stdout", "hello world", "fn") in messages
    assert ("stdout", "partial line", "fn") in messages
    assert sum(1 for m in messages if m[1] == "careful 1") == 1


def test_clear_and_function_summaries(tmp_path):
    path = tmp_path / "host.jsonl"
    buf = LogBuffer(path, capacity=100)
    _fill(buf, 3, function="a")
    _fill(buf, 2, function="b")
    _fill(buf, 1)
    summary = {s["function"]: s["count"] for s in buf.functions()}
    assert summary == {"a": 3, "b": 2, None: 1}
    assert buf.clear("a") == 3
    assert {e["function"] for e in buf.query()["entries"]} == {"b", None}
    assert buf.clear(hostlog.HOST_STREAM) == 1
    assert {e["function"] for e in buf.query()["entries"]} == {"b"}
    buf.append("INFO", "host", "after")
    last = buf.last_seq
    buf.close()
    again = LogBuffer(path, capacity=100)
    assert [e["message"] for e in again.query()["entries"]] == ["line 0", "line 1", "after"]
    assert again.clear() == 3 and again.query()["entries"] == []
    again.append("INFO", "host", "new")
    assert again.last_seq > last
    again.close()
