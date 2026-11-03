"""Category D (fix a handler bug), batch 15. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

ONPREM = """provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: {port}
"""

GCP = """provider:
  name: gcp
  region: {region}
  options:
    project: ${{env:GOOGLE_CLOUD_PROJECT, demo-project}}
"""


def B(n, **kw):
    return dict(id=f"d_debug-{n:04d}", category="d_debug", **kw)


def AWS(service, region="us-east-1", extra=""):
    return f"service: {service}\nprovider:\n  name: aws\n  region: {region}\n{extra}"


def AZ(service, region="westeurope"):
    return f"service: {service}\nprovider:\n  name: azure\n  region: {region}\n"


def OP(service, port):
    return f"service: {service}\n" + ONPREM.format(port=port)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 281 onprem http, [:-1] drops the last row
    B(281, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": OP("shift-export", 8651) + """functions:
  shifts:
    handler: app.shifts.export
    events:
      - http: GET /shifts
""",
          "app/__init__.py": "",
          "app/shifts.py": FUTURE + """SHIFTS = ["mon-early", "mon-late", "tue-early"]


def export(event, ctx):
    lines = [f"{n},{s}" for n, s in enumerate(SHIFTS, 1)]
    return "\\n".join(lines[:-1])
""",
          "requirements.txt": ""}),
      user="shift export always miss the last shift. 3 shifts, export show 2",
      steps=[
          S("read_file", path="app/shifts.py"),
          S("invoke_local", function="shifts", path="/shifts"),
          S("propose_plan", steps=["Join all lines: `lines[:-1]` leaves out the last one",
                                   "GET /shifts locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/shifts.py", content=FUTURE + """SHIFTS = ["mon-early", "mon-late", "tue-early"]


def export(event, ctx):
    lines = [f"{n},{s}" for n, s in enumerate(SHIFTS, 1)]
    return "\\n".join(lines) + "\\n"
"""),
          S("invoke_local", function="shifts", path="/shifts"),
          S("validate"),
      ],
      final="""`lines[:-1]` means "everything except the last item", so `tue-early` was cut. Now all lines are joined (and the export ends with a newline, which most CSV tools expect).

- Before: 2 lines. After: `1,mon-early`, `2,mon-late`, `3,tue-early`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 282 onprem queue, return inside finally
    B(282, provider="onprem", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": OP("print-jobs", 8652) + """functions:
  printer:
    handler: app.printer.handle
    events:
      - queue:
          name: print-jobs
          dead_letter: print-jobs-dlq
          max_receive: 3
""",
          "app/__init__.py": "",
          "app/printer.py": FUTURE + """
def render(job):
    return f"{job['copies']} x {job['doc']}"


def handle(event, ctx):
    done = []
    try:
        for record in event.records:
            done.append(render(record.json()))
    finally:
        ctx.logger.info("batch finished", extra={"done": len(done)})
        return {"done": done}
""",
          "requirements.txt": ""}),
      user="Jobs with a missing field silently disappear from print-jobs: no error in the logs, nothing in print-jobs-dlq. I expected a broken job to be retried and then dead-lettered. The finally block is only there to log how many jobs were done. What's swallowing the error?",
      steps=[
          S("read_file", path="app/printer.py"),
          S("invoke_local", function="printer", type="queue", data=[{"doc": "a.pdf", "copies": 2}, {"doc": "b.pdf"}]),
          S("propose_plan", steps=["Move the `return` out of `finally` (a return there discards the exception)",
                                   "Report a broken job with `BatchResult.fail(record)`, so only that job is retried and later dead-lettered",
                                   "Invoke with one good and one broken job; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/printer.py", content=FUTURE + """from py_serverless_kit import BatchResult


def render(job):
    return f"{job['copies']} x {job['doc']}"


def handle(event, ctx):
    result = BatchResult()
    done = 0
    for record in event.records:
        try:
            render(record.json())
            done += 1
        except KeyError as exc:
            ctx.logger.warning("bad job", extra={"message_id": record.id, "missing": str(exc)})
            result.fail(record)
    ctx.logger.info("batch finished", extra={"done": done})
    return result
"""),
          S("invoke_local", function="printer", type="queue", data=[{"doc": "a.pdf", "copies": 2}, {"doc": "b.pdf"}]),
          S("validate"),
      ],
      final="""`return` inside `finally` throws away any exception in flight. The `KeyError` for the missing `copies` vanished, the host saw a successful batch and deleted the messages. Now a broken job is logged and reported with `BatchResult.fail(record)`. On premises the host retries only that message and moves it to `print-jobs-dlq` after `max_receive` (3) attempts [docs/handlers.md#batchresult].

- Before: `{"done": ["2 x a.pdf"]}`, no error.
- After: `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`, with a `bad job` warning.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 283 onprem http, int() of "#FF8800"
    B(283, provider="onprem", stage="staging", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": OP("theme-api", 8653) + """functions:
  rgb:
    handler: app.colors.rgb
    events:
      - http: GET /colors/rgb
""",
          "app/__init__.py": "",
          "app/colors.py": FUTURE + """
def rgb(event, ctx):
    value = int(event.http.query.get("hex", "000000"), 16)
    return {"r": value >> 16, "g": (value >> 8) & 255, "b": value & 255}
""",
          "requirements.txt": ""}),
      user="""ValueError: invalid literal for int() with base 16: '#FF8800'
GET /colors/rgb?hex=%23FF8800 (the designer copies colors with the #)""",
      steps=[
          S("read_file", path="app/colors.py"),
          S("invoke_local", function="rgb", path="/colors/rgb?hex=%23FF8800"),
          S("propose_plan", steps=["Remove a leading `#`, require exactly 6 hex digits, and return 400 otherwise",
                                   "GET with `%23FF8800` (200) and `zz` (400) locally; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/colors.py", content=FUTURE + """import re

from py_serverless_kit import BadRequest

HEX = re.compile(r"[0-9a-fA-F]{6}")


def rgb(event, ctx):
    raw = event.http.query.get("hex", "000000").lstrip("#")
    if not HEX.fullmatch(raw):
        raise BadRequest("hex must be 6 hex digits, e.g. FF8800")
    value = int(raw, 16)
    return {"r": value >> 16, "g": (value >> 8) & 255, "b": value & 255}
"""),
          S("invoke_local", function="rgb", path="/colors/rgb?hex=%23FF8800"),
          S("invoke_local", function="rgb", path="/colors/rgb?hex=zz"),
          S("validate"),
      ],
      final="""`int(..., 16)` reads hex digits only, and `#` isn't one. The handler now strips a leading `#`, checks for exactly 6 hex digits, and returns 400 for anything else instead of a 500 [docs/handlers.md#errors].

- `#FF8800`: `{"r": 255, "g": 136, "b": 0}`.
- `zz`: 400 `hex must be 6 hex digits, e.g. FF8800`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 284 onprem schedule, x = x.append(...)
    B(284, provider="onprem", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": OP("disk-watch", 8654) + """functions:
  disk-check:
    handler: app.disk.check
    events:
      - schedule:
          rate: 30 minutes
          input:
            volumes: {data: 91, logs: 40, backup: 97}
""",
          "app/__init__.py": "",
          "app/disk.py": FUTURE + """
def check(event, ctx):
    alerts = []
    for name, used in event.data["volumes"].items():
        if used > 90:
            alerts = alerts.append(name)
    return {"alerts": alerts}
""",
          "requirements.txt": ""}),
      user="""AttributeError: 'NoneType' object has no attribute 'append'
disk-check, second volume over 90%""",
      steps=[
          S("read_file", path="app/disk.py"),
          S("invoke_local", function="disk-check", type="schedule"),
          S("propose_plan", steps=["Call `alerts.append(name)` without assigning: `append` returns `None`",
                                   "Run the schedule with its input; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/disk.py", content=FUTURE + """
def check(event, ctx):
    alerts = []
    for name, used in event.data["volumes"].items():
        if used > 90:
            alerts.append(name)
    return {"alerts": alerts}
"""),
          S("invoke_local", function="disk-check", type="schedule"),
          S("validate"),
      ],
      final="""`list.append()` changes the list and returns `None`. `alerts = alerts.append(name)` replaced the list with `None`, so the next volume over 90% crashed. Now `append` is called on its own.

- After: `{"alerts": ["data", "backup"]}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 285 onprem http, isdigit rejects negatives
    B(285, provider="onprem", stage="prod", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": OP("cold-store", 8655) + """functions:
  temperature:
    handler: app.temp.record
    events:
      - http: POST /temperature
""",
          "app/__init__.py": "",
          "app/temp.py": FUTURE + """from py_serverless_kit import BadRequest


def record(event, ctx):
    raw = str(event.http.json().get("celsius", ""))
    if not raw.isdigit():
        raise BadRequest("celsius must be a number")
    return {"celsius": int(raw)}, 201
""",
          "requirements.txt": ""}),
      user="our freezer sends -18 and the function says celsius must be a number. -18 is a number!",
      steps=[
          S("read_file", path="app/temp.py"),
          S("invoke_local", function="temperature", method="POST", path="/temperature", data={"celsius": -18}),
          S("propose_plan", steps=["Parse with `float()` inside `try` instead of `isdigit()`, which allows only the digits 0-9",
                                   "POST -18 (201) and \"cold\" (400) locally; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/temp.py", content=FUTURE + """from py_serverless_kit import BadRequest


def record(event, ctx):
    try:
        celsius = float(event.http.json().get("celsius"))
    except (TypeError, ValueError):
        raise BadRequest("celsius must be a number") from None
    return {"celsius": celsius}, 201
"""),
          S("invoke_local", function="temperature", method="POST", path="/temperature", data={"celsius": -18}),
          S("invoke_local", function="temperature", method="POST", path="/temperature", data={"celsius": "cold"}),
          S("validate"),
      ],
      final="""`"-18".isdigit()` is `False`: the minus sign isn't a digit (a decimal point isn't either). Now the value is converted with `float()`, and only things that really aren't numbers get the 400.

- `-18`: 201 `{"celsius": -18.0}`.
- `"cold"`: 400 `celsius must be a number`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 286 onprem storage, os.path.join on a Windows host
    B(286, provider="onprem", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": OP("thumb-paths", 8656) + """functions:
  plan-thumbs:
    handler: app.plan.handle
    events:
      - storage: originals
""",
          "app/__init__.py": "",
          "app/plan.py": FUTURE + """import os


def handle(event, ctx):
    return {"targets": [os.path.join("thumbs", "small", r.key) for r in event.records]}
""",
          "requirements.txt": ""}),
      user="Our on-prem host runs on Windows. plan-thumbs builds the target object keys for thumbnails, and the keys come out as thumbs\\small\\cat.jpg with backslashes, which our object store treats as one weird filename. Keys must always use forward slashes, whatever the host OS.",
      steps=[
          S("read_file", path="app/plan.py"),
          S("invoke_local", function="plan-thumbs", type="storage", data=[{"key": "cat.jpg"}, {"key": "2026/dog.png"}]),
          S("propose_plan", steps=["Build keys with `posixpath.join` (always `/`) instead of `os.path.join` (the host OS separator)",
                                   "Invoke with two keys; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/plan.py", content=FUTURE + """import posixpath


def handle(event, ctx):
    return {"targets": [posixpath.join("thumbs", "small", r.key) for r in event.records]}
"""),
          S("invoke_local", function="plan-thumbs", type="storage", data=[{"key": "cat.jpg"}, {"key": "2026/dog.png"}]),
          S("validate"),
      ],
      final="""`os.path.join` uses the separator of the machine it runs on, and on Windows that is `\\`. Object keys are not file paths: `record.key` always uses `/` [docs/handlers.md#record]. `posixpath.join` always joins with `/`, on any OS.

- Before (this Windows machine): `thumbs\\small\\cat.jpg`.
- After: `thumbs/small/cat.jpg`, `thumbs/small/2026/dog.png`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 287 onprem http, GeoJSON [lon, lat] order
    B(287, provider="onprem", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": OP("geo-pins", 8657) + """functions:
  pin:
    handler: app.geo.pin
    events:
      - http: POST /pins
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + """
def pin(event, ctx):
    feature = event.http.json()
    lat, lon = feature["geometry"]["coordinates"]
    return {"lat": lat, "lon": lon}
""",
          "requirements.txt": ""}),
      user="pins from geojson land in antarctica-ish. lat/lon swapped?",
      steps=[
          S("read_file", path="app/geo.py"),
          S("invoke_local", function="pin", method="POST", path="/pins",
            data={"type": "Feature", "geometry": {"type": "Point", "coordinates": [13.405, 52.52]}}),
          S("propose_plan", steps=["Unpack GeoJSON as `lon, lat = coordinates` (RFC 7946 order)",
                                   "POST a Berlin point locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/geo.py", content=FUTURE + """
def pin(event, ctx):
    feature = event.http.json()
    lon, lat = feature["geometry"]["coordinates"][:2]
    return {"lat": lat, "lon": lon}
"""),
          S("invoke_local", function="pin", method="POST", path="/pins",
            data={"type": "Feature", "geometry": {"type": "Point", "coordinates": [13.405, 52.52]}}),
          S("validate"),
      ],
      final="""Yes. GeoJSON coordinates are `[longitude, latitude]`. Fixed the unpacking; `[:2]` also ignores an optional altitude.

- Berlin `[13.405, 52.52]`: before `lat 13.405`, now `{"lat": 52.52, "lon": 13.405}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 288 onprem queue, fail() on the wrong record
    B(288, provider="onprem", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": OP("sms-sender", 8658) + """functions:
  sms:
    handler: app.sms.handle
    events:
      - queue: sms-out
""",
          "app/__init__.py": "",
          "app/sms.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for i, record in enumerate(event.records, 1):
        msg = record.json()
        if not msg.get("phone"):
            result.fail(event.records[i])
    return result
""",
          "requirements.txt": ""}),
      user="sms without phone should retry, but the retry is for the next sms, not the bad one. and when last sms is bad it crash",
      steps=[
          S("read_file", path="app/sms.py"),
          S("invoke_local", function="sms", type="queue",
            data=[{"phone": "+15550100"}, {"text": "no phone"}, {"phone": "+15550101"}]),
          S("propose_plan", steps=["Fail the record you are looking at: `result.fail(record)`; `enumerate(..., 1)` made the index one too high",
                                   "Invoke with the bad message in the middle; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sms.py", content=FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json()
        if not msg.get("phone"):
            result.fail(record)
    return result
"""),
          S("invoke_local", function="sms", type="queue",
            data=[{"phone": "+15550100"}, {"text": "no phone"}, {"phone": "+15550101"}]),
          S("validate"),
      ],
      final="""`enumerate(..., 1)` starts counting at 1, but list indexes start at 0, so `event.records[i]` was the *next* message. For the last one it was past the end (IndexError). Pass the record itself: `result.fail(record)` [docs/handlers.md#batchresult].

- Before: `local-2` marked as failed (the good one).
- After: `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`, the message without a phone.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 289 aws http, float("inf") passes validation
    B(289, provider="aws", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AWS("bids", "eu-west-1") + """functions:
  place-bid:
    handler: app.bids.place
    events:
      - http: POST /bids
""",
          "app/__init__.py": "",
          "app/bids.py": FUTURE + """from py_serverless_kit import BadRequest


def place(event, ctx):
    try:
        amount = float(event.http.json()["amount"])
    except (KeyError, ValueError):
        raise BadRequest("amount must be a number") from None
    if amount <= 0:
        raise BadRequest("amount must be positive")
    return {"bid": amount}, 201
""",
          "requirements.txt": ""}),
      user="Someone placed a bid with \"amount\": \"Infinity\" and it was accepted with 201. Now the auction page can't parse our JSON. Bids must be finite positive numbers; \"inf\", \"Infinity\" and \"nan\" must give 400.",
      steps=[
          S("read_file", path="app/bids.py"),
          S("invoke_local", function="place-bid", method="POST", path="/bids", data={"amount": "Infinity"}),
          S("propose_plan", steps=["Reject non-finite values with `math.isfinite(amount)` after `float()`",
                                   "POST `Infinity` and `nan` (400) and `12.5` (201) locally; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/bids.py", content=FUTURE + """import math

from py_serverless_kit import BadRequest


def place(event, ctx):
    try:
        amount = float(event.http.json()["amount"])
    except (KeyError, TypeError, ValueError):
        raise BadRequest("amount must be a number") from None
    if not math.isfinite(amount) or amount <= 0:
        raise BadRequest("amount must be a finite positive number")
    return {"bid": amount}, 201
"""),
          S("invoke_local", function="place-bid", method="POST", path="/bids", data={"amount": "Infinity"}),
          S("invoke_local", function="place-bid", method="POST", path="/bids", data={"amount": "nan"}),
          S("invoke_local", function="place-bid", method="POST", path="/bids", data={"amount": "12.5"}),
          S("validate"),
      ],
      final="""`float()` accepts `"inf"`, `"Infinity"` and `"nan"`. Infinity is greater than 0, so it passed. When Python writes it to JSON it becomes `Infinity`, which browsers can't parse. `math.isfinite()` rejects both infinity and NaN.

- `Infinity`: was 201, now 400 `amount must be a finite positive number` [docs/handlers.md#errors]. `nan`: 400.
- `12.5`: 201 `{"bid": 12.5}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 290 aws schedule, range end is exclusive
    B(290, provider="aws", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AWS("month-close", "us-east-2") + """functions:
  close-month:
    handler: app.close.run
    events:
      - schedule:
          cron: "0 2 1 * *"
          input: {year: 2026, month: 11}
""",
          "app/__init__.py": "",
          "app/close.py": FUTURE + """import calendar


def run(event, ctx):
    year, month = event.data["year"], event.data["month"]
    last = calendar.monthrange(year, month)[1]
    days = [f"{year}-{month:02d}-{d:02d}" for d in range(1, last)]
    return {"days": len(days), "last": days[-1]}
""",
          "requirements.txt": ""}),
      user="the month close report for november stops at 29 november. november has 30 days, right?",
      steps=[
          S("read_file", path="app/close.py"),
          S("invoke_local", function="close-month", type="schedule"),
          S("propose_plan", steps=["Use `range(1, last + 1)`: the end of `range` is not included",
                                   "Run with the November input; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/close.py", content=FUTURE + """import calendar


def run(event, ctx):
    year, month = event.data["year"], event.data["month"]
    last = calendar.monthrange(year, month)[1]
    days = [f"{year}-{month:02d}-{d:02d}" for d in range(1, last + 1)]
    return {"days": len(days), "last": days[-1]}
"""),
          S("invoke_local", function="close-month", type="schedule"),
          S("validate"),
      ],
      final="""Right, 30 days. `range(1, 30)` counts 1 to 29: the end number is never included. `range(1, last + 1)` includes the last day.

- Before: 29 days, last `2026-11-29`. After: 30 days, last `2026-11-30`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 291 aws http, list.index raises ValueError
    B(291, provider="aws", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AWS("playlist", "eu-south-1") + """functions:
  position:
    handler: app.playlist.position
    events:
      - http: GET /playlist/{song}
""",
          "app/__init__.py": "",
          "app/playlist.py": FUTURE + """SONGS = ["intro", "storm", "outro"]


def position(event, ctx):
    return {"position": SONGS.index(event.http.path_params["song"]) + 1}
""",
          "requirements.txt": ""}),
      user="""ValueError: 'bonus' is not in list
GET /playlist/bonus gives 500, should be 404""",
      steps=[
          S("read_file", path="app/playlist.py"),
          S("invoke_local", function="position", path="/playlist/bonus"),
          S("propose_plan", steps=["Check `song in SONGS` first and raise `NotFound`",
                                   "GET /playlist/bonus (404) and /playlist/storm (200); validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/playlist.py", content=FUTURE + """from py_serverless_kit import NotFound

SONGS = ["intro", "storm", "outro"]


def position(event, ctx):
    song = event.http.path_params["song"]
    if song not in SONGS:
        raise NotFound("no such song")
    return {"position": SONGS.index(song) + 1}
"""),
          S("invoke_local", function="position", path="/playlist/bonus"),
          S("invoke_local", function="position", path="/playlist/storm"),
          S("validate"),
      ],
      final="""`list.index()` raises `ValueError` when the item is missing, and pskit returns a 500 for an unexpected exception [docs/handlers.md#errors]. Now an unknown song raises `NotFound`.

- `bonus`: 404 `no such song`. `storm`: 200 `{"position": 2}`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 292 aws http, Node.js query string + 1
    B(292, provider="aws", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AWS("news-js", "us-east-1", "  runtime: nodejs20\n") + """functions:
  news:
    handler: src.news.list
    events:
      - http: GET /news
""",
          "src/news.js": """exports.list = async (event) => {
  const page = event.http.query.page ?? 1;
  return { page, next: page + 1 };
};
"""}),
      user="news api say next page is 21 when page is 2 lol. javascript",
      steps=[
          S("read_file", path="src/news.js"),
          S("invoke_local", function="news", path="/news?page=2"),
          S("propose_plan", steps=["Convert the query value with `Number(...)` before adding (query values are strings)",
                                   "GET /news?page=2 locally and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/news.js", content="""exports.list = async (event) => {
  const page = Number(event.http.query.page ?? 1) || 1;
  return { page, next: page + 1 };
};
"""),
          S("invoke_local", function="news", path="/news?page=2"),
          S("validate"),
      ],
      final="""Query values are **strings**, and in JavaScript `"2" + 1` joins text: `"21"`. `Number(...)` turns it into a number first, and `|| 1` covers `?page=abc`.

- Before: `{"page": "2", "next": "21"}`. After: `{"page": 2, "next": 3}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 293 gcp http, b64encode of a str
    B(293, provider="gcp", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: basic-auth-helper\n" + GCP.format(region="us-central1") + """functions:
  encode:
    handler: app.encode.encode
    events:
      - http: POST /encode
""",
          "app/__init__.py": "",
          "app/encode.py": FUTURE + """import base64


def encode(event, ctx):
    text = event.http.text()
    return {"base64": base64.b64encode(text)}
""",
          "requirements.txt": ""}),
      user="""TypeError: a bytes-like object is required, not 'str'
in base64.b64encode, POST /encode with body hello""",
      steps=[
          S("read_file", path="app/encode.py"),
          S("invoke_local", function="encode", method="POST", path="/encode", data="hello"),
          S("propose_plan", steps=["Encode the raw body bytes (`event.http.body`) and decode the result to `str` for JSON",
                                   "POST `hello` locally and validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/encode.py", content=FUTURE + """import base64


def encode(event, ctx):
    return {"base64": base64.b64encode(event.http.body).decode("ascii")}
"""),
          S("invoke_local", function="encode", method="POST", path="/encode", data="hello"),
          S("validate"),
      ],
      final="""`base64.b64encode` works on bytes and returns bytes. `event.http.body` already is bytes [docs/handlers.md#httprequest], so encode that, then `.decode("ascii")` to get a string for the JSON.

- After: `{"base64": "aGVsbG8="}`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 294 gcp schedule, dict.fromkeys with a list
    B(294, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: chore-rota\n" + GCP.format(region="europe-west2") + """functions:
  rota:
    handler: app.rota.run
    events:
      - schedule:
          cron: "0 8 * * 1"
          input:
            people: [ana, ben]
            chores: [dishes, trash, plants]
""",
          "app/__init__.py": "",
          "app/rota.py": FUTURE + """
def run(event, ctx):
    people = event.data["people"]
    plan = dict.fromkeys(people, [])
    for i, chore in enumerate(event.data["chores"]):
        plan[people[i % len(people)]].append(chore)
    return plan
""",
          "requirements.txt": ""}),
      user="The weekly rota should hand out chores in turn: ana gets dishes and plants, ben gets trash. Instead both people get all three chores. The input lists people and chores; please fix the assignment.",
      steps=[
          S("read_file", path="app/rota.py"),
          S("invoke_local", function="rota", type="schedule"),
          S("propose_plan", steps=["Create one list per person with `{p: [] for p in people}`; `dict.fromkeys(people, [])` shares one list",
                                   "Run with the configured input; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/rota.py", content=FUTURE + """
def run(event, ctx):
    people = event.data["people"]
    plan = {person: [] for person in people}
    for i, chore in enumerate(event.data["chores"]):
        plan[people[i % len(people)]].append(chore)
    return plan
"""),
          S("invoke_local", function="rota", type="schedule"),
          S("validate"),
      ],
      final="""`dict.fromkeys(people, [])` puts **the same list object** under every key, so appending for ana also appended for ben. A dict comprehension creates a new list per person.

- Before: both `["dishes", "trash", "plants"]`.
- After: ana `["dishes", "plants"]`, ben `["trash"]`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 295 gcp http, age before the birthday
    B(295, provider="gcp", stage="prod", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: age-check\n" + GCP.format(region="asia-southeast1") + """functions:
  age:
    handler: app.age.age
    events:
      - http: POST /age
""",
          "app/__init__.py": "",
          "app/age.py": FUTURE + """from datetime import date


def age(event, ctx):
    body = event.http.json()
    born = date.fromisoformat(body["born"])
    today = date.fromisoformat(body["today"])
    years = today.year - born.year
    return {"age": years, "adult": years >= 18}
""",
          "requirements.txt": ""}),
      user="someone born 2008-12-01 is 17 today (2026-11-01) but my check says 18 and adult true. how?",
      steps=[
          S("read_file", path="app/age.py"),
          S("invoke_local", function="age", method="POST", path="/age", data={"born": "2008-12-01", "today": "2026-11-01"}),
          S("propose_plan", steps=["Subtract one year when this year's birthday hasn't come yet: compare `(month, day)`",
                                   "POST the same dates locally and validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/age.py", content=FUTURE + """from datetime import date


def age(event, ctx):
    body = event.http.json()
    born = date.fromisoformat(body["born"])
    today = date.fromisoformat(body["today"])
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return {"age": years, "adult": years >= 18}
"""),
          S("invoke_local", function="age", method="POST", path="/age", data={"born": "2008-12-01", "today": "2026-11-01"}),
          S("validate"),
      ],
      final="""Subtracting only the years ignores whether the birthday has happened yet this year. On 1 November the December birthday is still ahead, so one year must be taken off. The fix compares `(month, day)`, and `True` counts as 1.

- Before: `{"age": 18, "adult": true}`. After: `{"age": 17, "adult": false}`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 296 gcp queue, list(set()) loses the order
    B(296, provider="gcp", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: breadcrumb\n" + GCP.format(region="us-east1") + """functions:
  trail:
    handler: app.trail.handle
    events:
      - queue: page-views
""",
          "app/__init__.py": "",
          "app/trail.py": FUTURE + """
def handle(event, ctx):
    pages = [record.json()["page"] for record in event.records]
    return {"trail": list(set(pages))}
""",
          "requirements.txt": ""}),
      user="trail dedupe scrambles order, different every run. keep first-seen order",
      steps=[
          S("read_file", path="app/trail.py"),
          S("invoke_local", function="trail", type="queue",
            data=[{"page": "home"}, {"page": "shop"}, {"page": "home"}, {"page": "cart"}, {"page": "checkout"}]),
          S("propose_plan", steps=["Dedupe with `list(dict.fromkeys(pages))`, which keeps first-seen order",
                                   "Invoke with 5 views; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/trail.py", content=FUTURE + """
def handle(event, ctx):
    pages = [record.json()["page"] for record in event.records]
    return {"trail": list(dict.fromkeys(pages))}
"""),
          S("invoke_local", function="trail", type="queue",
            data=[{"page": "home"}, {"page": "shop"}, {"page": "home"}, {"page": "cart"}, {"page": "checkout"}]),
          S("validate"),
      ],
      final="""A `set` has no order, and string hashing is randomised per process, so the order changed from run to run. Dict keys keep insertion order, so `dict.fromkeys` dedupes and keeps the first-seen order.

- After: `["home", "shop", "cart", "checkout"]`, the same on every run.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 297 azure http, == instead of =
    B(297, provider="azure", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AZ("audit-log", "westus2") + """functions:
  logs:
    handler: app.logs.list_logs
    events:
      - http: GET /logs
""",
          "app/__init__.py": "",
          "app/logs.py": FUTURE + """ENTRIES = [f"entry-{n}" for n in range(1, 301)]


def list_logs(event, ctx):
    limit = int(event.http.query.get("limit", "50"))
    if limit > 100:
        limit == 100
    return {"limit": limit, "count": len(ENTRIES[:limit])}
""",
          "requirements.txt": ""}),
      user="limit should max 100 but ?limit=300 give 300 entries",
      steps=[
          S("read_file", path="app/logs.py"),
          S("invoke_local", function="logs", path="/logs?limit=300"),
          S("propose_plan", steps=["Assign with `=`: `limit == 100` only compares and throws the result away",
                                   "GET /logs?limit=300 locally and validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/logs.py", content=FUTURE + """ENTRIES = [f"entry-{n}" for n in range(1, 301)]


def list_logs(event, ctx):
    limit = min(int(event.http.query.get("limit", "50")), 100)
    return {"limit": limit, "count": len(ENTRIES[:limit])}
"""),
          S("invoke_local", function="logs", path="/logs?limit=300"),
          S("validate"),
      ],
      final="""`limit == 100` is a comparison, not an assignment. It computes `False` and changes nothing. Now it is `limit = min(..., 100)`.

- Before: `{"limit": 300, "count": 300}`. After: `{"limit": 100, "count": 100}`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 298 azure queue, format() index out of range
    B(298, provider="azure", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AZ("ship-notify", "eastus") + """functions:
  shipped:
    handler: app.notify.handle
    events:
      - queue: shipments
""",
          "app/__init__.py": "",
          "app/notify.py": FUTURE + """TEMPLATE = "Hi {0}, order {1} ships with {2}."


def handle(event, ctx):
    texts = []
    for record in event.records:
        s = record.json()
        texts.append(TEMPLATE.format(s["name"], s["carrier"]))
    return {"texts": texts}
""",
          "requirements.txt": ""}),
      user="""IndexError: Replacement index 2 out of range for positional args tuple
shipped worker""",
      steps=[
          S("read_file", path="app/notify.py"),
          S("invoke_local", function="shipped", type="queue", data=[{"name": "Ida", "order": "A-17", "carrier": "DHL"}]),
          S("propose_plan", steps=["Use named fields (`{name}`, `{order}`, `{carrier}`) and pass the message with `format(**s)`; the order number was missing",
                                   "Invoke with one shipment; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/notify.py", content=FUTURE + """TEMPLATE = "Hi {name}, order {order} ships with {carrier}."


def handle(event, ctx):
    texts = []
    for record in event.records:
        s = record.json()
        texts.append(TEMPLATE.format(name=s["name"], order=s["order"], carrier=s["carrier"]))
    return {"texts": texts}
"""),
          S("invoke_local", function="shipped", type="queue", data=[{"name": "Ida", "order": "A-17", "carrier": "DHL"}]),
          S("validate"),
      ],
      final="""The template has three slots (`{0}`, `{1}`, `{2}`) but `format()` got two values, because the order number was missing. Named fields make that kind of mismatch obvious, so the template now uses `{name}`, `{order}` and `{carrier}`.

- After: `Hi Ida, order A-17 ships with DHL.`
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 299 azure schedule, timedelta(month=1)
    B(299, provider="azure", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("renewals", "uksouth") + """functions:
  renew:
    handler: app.renew.run
    events:
      - schedule:
          cron: "0 3 * * *"
          input: {renewed_on: "2026-01-31"}
""",
          "app/__init__.py": "",
          "app/renew.py": FUTURE + """from datetime import date, timedelta


def run(event, ctx):
    renewed = date.fromisoformat(event.data["renewed_on"])
    return {"next_renewal": (renewed + timedelta(month=1)).isoformat()}
""",
          "requirements.txt": ""}),
      user="""TypeError: 'month' is an invalid keyword argument for __new__()
renew job. want same day next month""",
      steps=[
          S("read_file", path="app/renew.py"),
          S("invoke_local", function="renew", type="schedule"),
          S("propose_plan", steps=["`timedelta` has no months: move to the next month by hand and clamp the day with `calendar.monthrange` (31 Jan -> 28 Feb)",
                                   "Run with 2026-01-31 locally and validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/renew.py", content=FUTURE + """import calendar
from datetime import date


def add_month(day):
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def run(event, ctx):
    renewed = date.fromisoformat(event.data["renewed_on"])
    return {"next_renewal": add_month(renewed).isoformat()}
"""),
          S("invoke_local", function="renew", type="schedule"),
          S("validate"),
      ],
      final="""`timedelta` only knows fixed lengths (days, seconds, ...). A month has no fixed length. `add_month` moves to the next month (December goes to January) and clamps the day to that month's last day.

- 2026-01-31: `{"next_renewal": "2026-02-28"}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 300 azure http, ** on a null field
    B(300, provider="azure", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AZ("export-api", "northeurope") + """functions:
  export:
    handler: app.export.start
    events:
      - http: POST /exports
""",
          "app/__init__.py": "",
          "app/export.py": FUTURE + """DEFAULTS = {"format": "csv", "zip": False}


def start(event, ctx):
    body = event.http.json()
    options = {**DEFAULTS, **body.get("options", {})}
    return {"options": options}, 202
""",
          "requirements.txt": ""}),
      user="POST /exports merges the client's options over our defaults. Our mobile app sends \"options\": null when the user didn't change anything, and that gives a 500 (TypeError: 'NoneType' object is not a mapping). A null or missing options should just mean the defaults.",
      steps=[
          S("read_file", path="app/export.py"),
          S("invoke_local", function="export", method="POST", path="/exports", data={"options": None}),
          S("propose_plan", steps=["Use `body.get(\"options\") or {}` so `null` and a missing key both mean no overrides",
                                   "POST options null and {\"zip\": true} locally; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/export.py", content=FUTURE + """DEFAULTS = {"format": "csv", "zip": False}


def start(event, ctx):
    body = event.http.json()
    options = {**DEFAULTS, **(body.get("options") or {})}
    return {"options": options}, 202
"""),
          S("invoke_local", function="export", method="POST", path="/exports", data={"options": None}),
          S("invoke_local", function="export", method="POST", path="/exports", data={"options": {"zip": True}}),
          S("validate"),
      ],
      final="""`body.get("options", {})` returns the default only when the key is missing. With `"options": null` it returns `None`, and `**None` fails. `or {}` covers both cases.

- `null`: 202 `{"options": {"format": "csv", "zip": false}}`.
- `{"zip": true}`: 202 `{"options": {"format": "csv", "zip": true}}`.
- validate (azure): valid."""),
]
