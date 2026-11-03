import base64
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from py_serverless_kit import BadRequest, BatchResult, Event, Headers, HttpRequest, Record, Response
from py_serverless_kit.runtime.batch import BatchFailure
from py_serverless_kit.runtime.event import parse_time
from py_serverless_kit.runtime.response import to_response


class TestHeaders:
    def test_case_insensitive(self):
        h = Headers({"Content-Type": "application/json", "X-A": ["1", "2"]})
        assert h["content-type"] == "application/json"
        assert h.get("CONTENT-TYPE") == "application/json"
        assert h["x-a"] == "1, 2"
        assert "X-A" in h
        assert len(h) == 2

    def test_from_pairs_merges_duplicates(self):
        h = Headers([("Accept", "a"), ("accept", "b")])
        assert h["accept"] == "a, b"

    def test_none_values_skipped(self):
        assert "x" not in Headers({"x": None})


class TestHttpRequest:
    def test_json_and_text(self):
        req = HttpRequest(method="post", body='{"a": 1}', headers={"Content-Type": "application/json; charset=utf-8"})
        assert req.method == "POST"
        assert req.json() == {"a": 1}
        assert req.text() == '{"a": 1}'
        assert req.content_type == "application/json"

    def test_invalid_json_raises_400(self):
        with pytest.raises(BadRequest) as exc:
            HttpRequest(body="nope").json()
        assert exc.value.status == 400

    def test_json_default(self):
        assert HttpRequest(body="").json(default={}) == {}

    def test_form_and_cookies(self):
        req = HttpRequest(body="a=1&b=two", headers={"cookie": "sid=abc; theme=dark"})
        assert req.form() == {"a": "1", "b": "two"}
        assert req.cookies == {"sid": "abc", "theme": "dark"}

    def test_query_populates_multi(self):
        assert HttpRequest(query={"a": "1"}).multi_query == {"a": ["1"]}

    def test_decode_body(self):
        assert HttpRequest.decode_body(base64.b64encode(b"hi").decode(), True) == b"hi"
        assert HttpRequest.decode_body({"a": 1}) == b'{"a": 1}'
        assert HttpRequest.decode_body(None) == b""


class TestRecordAndEvent:
    def test_record_json(self):
        assert Record(body='{"x": 2}').json() == {"x": 2}
        assert Record(body={"x": 3}).json() == {"x": 3}
        assert Record(body=b"raw").text() == "raw"
        assert Record(body="bad").json(default=None) is None

    def test_event_json_dispatch(self):
        assert Event(type="invoke", data={"a": 1}).json() == {"a": 1}
        assert Event(type="queue", records=[Record(body='{"b": 2}')]).json() == {"b": 2}
        assert Event(type="http", http=HttpRequest(body='{"c": 3}')).json() == {"c": 3}

    def test_iteration_and_dict(self):
        ev = Event(type="queue", records=[Record(id="1"), Record(id="2")])
        assert [r.id for r in ev] == ["1", "2"]
        assert ev.is_batch and not ev.is_http
        assert ev.to_dict()["records"] == 2


class TestResponse:
    def test_json(self):
        status, headers, body = Response.json(
            {"a": Decimal("1.5"), "t": datetime(2024, 1, 1, tzinfo=timezone.utc)}
        ).render()
        assert status == 200
        assert headers["content-type"] == "application/json"
        assert json.loads(body) == {"a": 1.5, "t": "2024-01-01T00:00:00+00:00"}

    def test_binary_is_base64_for_gateway(self):
        _, headers, body, b64 = Response.binary(b"\x89PNG", "image/png").render_for_gateway()
        assert b64 and base64.b64decode(body) == b"\x89PNG"

    def test_text_not_base64(self):
        _, _, body, b64 = Response.html("<p>x</p>").render_for_gateway()
        assert body == "<p>x</p>" and not b64

    def test_cookies_and_redirect(self):
        resp = Response.redirect("/x").set_cookie("sid", "1", max_age=60)
        assert resp.status == 302 and resp.headers["location"] == "/x"
        assert "Max-Age=60" in resp.cookies[0] and "HttpOnly" in resp.cookies[0]

    @pytest.mark.parametrize(
        "value,status,ctype",
        [
            (None, 204, ""),
            ({"a": 1}, 200, "application/json"),
            ([1, 2], 200, "application/json"),
            ("hi", 200, "text/plain; charset=utf-8"),
            (b"x", 200, "application/octet-stream"),
            (({"a": 1}, 201), 201, "application/json"),
            (("x", 202, {"x-h": "1"}), 202, "text/plain; charset=utf-8"),
        ],
    )
    def test_to_response(self, value, status, ctype):
        resp = to_response(value)
        assert resp.status == status
        assert resp.render()[1].get("content-type", "") == ctype


def test_batch_result():
    result = BatchResult.of([Record(id="a"), "b"])
    assert result.failed == ["a", "b"] and not result.ok
    with pytest.raises(BatchFailure):
        result.raise_if_failed()
    BatchResult().raise_if_failed()


@pytest.mark.parametrize(
    "value",
    ["2024-01-02T03:04:05Z", "2024-01-02T03:04:05+00:00", 1704164645, 1704164645000, "1704164645"],
)
def test_parse_time(value):
    assert parse_time(value) == datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_parse_time_fallback():
    assert parse_time("garbage").tzinfo is not None


def test_logger_merges_extra_and_never_crashes(capsys, monkeypatch):
    import json as _json
    import logging

    from py_serverless_kit.runtime.log import JsonFormatter, get_logger

    log = get_logger("pskit.test", function="f", request_id="r")
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Capture()
    log.logger.addHandler(handler)
    try:
        log.info("hello", extra={"name": "Ada", "message": "x", "status": 200})
    finally:
        log.logger.removeHandler(handler)
    out = _json.loads(JsonFormatter().format(records[0]))
    assert out["function"] == "f" and out["status"] == 200
    assert out["name_"] == "Ada" and out["message"] == "hello" and out["message_"] == "x"
