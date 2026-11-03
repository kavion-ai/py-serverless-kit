"""Category D (fix a handler bug), batch 10. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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


CONVERSATIONS = [
    # ------------------------------------------------------------------ 181 onprem http, // truncates the average
    B(181, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: recipe-stars\n" + ONPREM.format(port=8601) + """functions:
  rating:
    handler: app.stars.average
    events:
      - http: GET /recipes/{id}/rating
""",
          "app/__init__.py": "",
          "app/stars.py": FUTURE + """from py_serverless_kit import NotFound

VOTES = {"pancakes": [5, 4, 5, 4], "soup": [3, 4]}


def average(event, ctx):
    votes = VOTES.get(event.http.path_params["id"])
    if not votes:
        raise NotFound("no votes yet")
    return {"rating": sum(votes) // len(votes), "votes": len(votes)}
""",
          "requirements.txt": ""}),
      user="my pancakes have votes 5, 4, 5, 4 so the rating should be 4.5 but the page always shows 4. what am i doing wrong?",
      steps=[
          S("read_file", path="app/stars.py"),
          S("invoke_local", function="rating", path="/recipes/pancakes/rating"),
          S("propose_plan", steps=["Use true division `/` and round to one decimal instead of `//`",
                                   "GET /recipes/pancakes/rating locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/stars.py", content=FUTURE + """from py_serverless_kit import NotFound

VOTES = {"pancakes": [5, 4, 5, 4], "soup": [3, 4]}


def average(event, ctx):
    votes = VOTES.get(event.http.path_params["id"])
    if not votes:
        raise NotFound("no votes yet")
    return {"rating": round(sum(votes) / len(votes), 1), "votes": len(votes)}
"""),
          S("invoke_local", function="rating", path="/recipes/pancakes/rating"),
          S("validate"),
      ],
      final="""The code used `//`, which is *floor* division: `18 // 4` is `4`, the decimals are thrown away. A single `/` keeps them, and `round(..., 1)` gives one decimal.

- Before: `{"rating": 4, "votes": 4}`.
- After: `{"rating": 4.5, "votes": 4}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 182 aws storage, unquote_plus twice
    B(182, provider="aws", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#record", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: invoices-ocr
provider:
  name: aws
  region: eu-central-1
functions:
  scan:
    handler: app.scan.on_upload
    events:
      - storage:
          bucket: invoice-drop
          events: [created]
""",
          "app/__init__.py": "",
          "app/scan.py": FUTURE + """from urllib.parse import unquote_plus


def on_upload(event, ctx):
    keys = []
    for record in event.records:
        # S3 sends keys URL-encoded
        keys.append(unquote_plus(record.key))
    ctx.logger.info("scanning", extra={"keys": keys})
    return {"keys": keys}
""",
          "requirements.txt": ""}),
      user="Ported my S3 Lambda. I kept the unquote_plus(key) line from the old code because S3 URL-encodes keys. Now a file called 'q3+summary.pdf' fails with NoSuchKey because the function looks for 'q3 summary.pdf'. Do I still need the unquote?",
      steps=[
          S("read_file", path="app/scan.py"),
          S("invoke_local", function="scan", type="storage", data=[{"bucket": "invoice-drop", "key": "q3+summary.pdf"}]),
          S("search_docs", query="storage record key bucket",
            docs=[D("docs/handlers.md", "record", end="| `raw` |")]),
          S("propose_plan", steps=["Remove `unquote_plus`: `record.key` is already the real object key",
                                   "Invoke with key `q3+summary.pdf`; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/scan.py", content=FUTURE + """
def on_upload(event, ctx):
    keys = [record.key for record in event.records]
    ctx.logger.info("scanning", extra={"keys": keys})
    return {"keys": keys}
"""),
          S("invoke_local", function="scan", type="storage", data=[{"bucket": "invoice-drop", "key": "q3+summary.pdf"}]),
          S("validate"),
      ],
      final="""No. pskit's AWS adapter already decodes the S3 key before your handler runs, so `record.key` is the real name [docs/handlers.md#record]. Decoding it a second time turns the literal `+` into a space. I removed the `unquote_plus` call.

- Before: `{"keys": ["q3 summary.pdf"]}`.
- After: `{"keys": ["q3+summary.pdf"]}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 183 gcp http, 204 with a body
    B(183, provider="gcp", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: wishlist\n" + GCP.format(region="europe-west1") + """functions:
  remove-item:
    handler: app.wish.remove
    events:
      - http: DELETE /wishlist/{item}
""",
          "app/__init__.py": "",
          "app/wish.py": FUTURE + """from py_serverless_kit import Response

WISHLIST = ["lamp", "kettle", "rug"]


def remove(event, ctx):
    item = event.http.path_params["item"]
    if item in WISHLIST:
        WISHLIST.remove(item)
    return Response.json({"removed": item, "left": len(WISHLIST)}, status=204)
""",
          "requirements.txt": ""}),
      user="DELETE /wishlist/{item} should return JSON with the removed item and how many are left, so the frontend can update the counter. The frontend always gets an empty body, and res.json() throws. Please make it return the JSON and keep the delete working.",
      steps=[
          S("read_file", path="app/wish.py"),
          S("invoke_local", function="remove-item", method="DELETE", path="/wishlist/lamp"),
          S("propose_plan", steps=["Return the JSON with status 200: a 204 response can't carry a body",
                                   "DELETE /wishlist/lamp locally and validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/wish.py", content=FUTURE + """WISHLIST = ["lamp", "kettle", "rug"]


def remove(event, ctx):
    item = event.http.path_params["item"]
    if item in WISHLIST:
        WISHLIST.remove(item)
    return {"removed": item, "left": len(WISHLIST)}
"""),
          S("invoke_local", function="remove-item", method="DELETE", path="/wishlist/lamp"),
          S("validate"),
      ],
      final="""Status `204` means *No Content*: browsers and HTTP clients drop the body of a 204, so `res.json()` has nothing to parse. If you want to send data back, use 200. A plain dict return is already JSON with status 200 [docs/handlers.md#returning-a-response].

- Before: `"status": 204` (the body is lost on the way to the browser).
- After: `"status": 200`, `{"removed": "lamp", "left": 2}`.
- validate (gcp, staging): valid.

If you ever want a delete with no body, return `None` (204) and have the frontend skip `res.json()`."""),

    # ------------------------------------------------------------------ 184 onprem queue, mutable default argument
    B(184, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: photo-tags\n" + ONPREM.format(port=8602) + """functions:
  tagger:
    handler: app.tags.handle
    events:
      - queue: photos
""",
          "app/__init__.py": "",
          "app/tags.py": FUTURE + """
def add_tag(tag, tags=[]):
    if tag not in tags:
        tags.append(tag)
    return tags


def handle(event, ctx):
    out = {}
    for record in event.records:
        photo = record.json()
        tags = None
        for tag in photo["tags"]:
            tags = add_tag(tag.lower())
        out[photo["id"]] = tags
    return out
""",
          "requirements.txt": ""}),
      user="tagger is weird. photo 2 get also the tags of photo 1, like the tags never reset. pls check",
      steps=[
          S("read_file", path="app/tags.py"),
          S("invoke_local", function="tagger", type="queue",
            data=[{"id": "p1", "tags": ["Beach", "Sun"]}, {"id": "p2", "tags": ["Snow"]}]),
          S("propose_plan", steps=["Remove the shared default list `tags=[]`; build a fresh list for every photo",
                                   "Invoke with two photos; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tags.py", content=FUTURE + """
def clean_tags(raw):
    tags = []
    for tag in raw:
        tag = tag.lower()
        if tag not in tags:
            tags.append(tag)
    return tags


def handle(event, ctx):
    out = {}
    for record in event.records:
        photo = record.json()
        out[photo["id"]] = clean_tags(photo["tags"])
    return out
"""),
          S("invoke_local", function="tagger", type="queue",
            data=[{"id": "p1", "tags": ["Beach", "Sun"]}, {"id": "p2", "tags": ["Snow"]}]),
          S("validate"),
      ],
      final="""`def add_tag(tag, tags=[])`: Python creates that default list **once**, when the module loads, and every call shares it. So photo 2 kept adding to photo 1's list. On a server it would even keep growing across messages, until the process restarts. Now each photo gets a new list.

- Before: p1 and p2 both `["beach", "sun", "snow"]`.
- After: p1 `["beach", "sun"]`, p2 `["snow"]`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 185 azure http, 200 instead of 201 + Location
    B(185, provider="azure", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: notes-api
provider:
  name: azure
  region: westeurope
functions:
  create-note:
    handler: app.notes.create
    events:
      - http: POST /notes
""",
          "app/__init__.py": "",
          "app/notes.py": FUTURE + """import uuid


def create(event, ctx):
    note = event.http.json()
    note_id = uuid.uuid4().hex[:8]
    return {"id": note_id, "title": note.get("title", "")}
""",
          "requirements.txt": ""}),
      user="Our API contract test fails on POST /notes: it expects status 201 Created and a Location header pointing to /notes/<id>, but create-note answers 200 with no Location. The body itself is right. Can you fix the response?",
      steps=[
          S("read_file", path="app/notes.py"),
          S("invoke_local", function="create-note", method="POST", path="/notes", data={"title": "groceries"}),
          S("propose_plan", steps=["Return `Response.json(body, status=201, headers={\"location\": f\"/notes/{id}\"})`",
                                   "POST a note locally and validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/notes.py", content=FUTURE + """import uuid

from py_serverless_kit import Response


def create(event, ctx):
    note = event.http.json()
    note_id = uuid.uuid4().hex[:8]
    body = {"id": note_id, "title": note.get("title", "")}
    return Response.json(body, status=201, headers={"location": f"/notes/{note_id}"})
"""),
          S("invoke_local", function="create-note", method="POST", path="/notes", data={"title": "groceries"}),
          S("validate"),
      ],
      final="""A plain dict always becomes JSON with status 200 [docs/handlers.md#returning-a-response]. To set the status and headers, return `Response.json(body, status=201, headers={"location": ...})`.

- POST /notes: `"status": 201`, `location: /notes/<id>`, same body as before.
- validate (azure): valid.

The tuple form `return body, 201, {"location": ...}` would work too."""),

    # ------------------------------------------------------------------ 186 onprem http, CSV with a BOM
    B(186, provider="onprem", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: stock-import\n" + ONPREM.format(port=8603) + """functions:
  import-csv:
    handler: app.stock.upload
    events:
      - http: POST /stock/upload
""",
          "app/__init__.py": "",
          "app/stock.py": FUTURE + """import csv
import io


def upload(event, ctx):
    rows = csv.DictReader(io.StringIO(event.http.text()))
    items = {row["sku"]: int(row["qty"]) for row in rows}
    return {"imported": len(items), "items": items}
""",
          "requirements.txt": ""}),
      user="""KeyError: 'sku'
only when the file is saved from Excel. same columns, sku,qty in the first line""",
      steps=[
          S("read_file", path="app/stock.py"),
          S("invoke_local", function="import-csv", method="POST", path="/stock/upload",
            data="﻿sku,qty\nA-100,4\nB-200,7"),
          S("propose_plan", steps=["Decode the body with `utf-8-sig` so the byte-order mark Excel writes is dropped",
                                   "POST a CSV that starts with a BOM locally and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/stock.py", content=FUTURE + """import csv
import io


def upload(event, ctx):
    text = event.http.body.decode("utf-8-sig")
    rows = csv.DictReader(io.StringIO(text))
    items = {row["sku"]: int(row["qty"]) for row in rows}
    return {"imported": len(items), "items": items}
"""),
          S("invoke_local", function="import-csv", method="POST", path="/stock/upload",
            data="﻿sku,qty\nA-100,4\nB-200,7"),
          S("validate"),
      ],
      final="""Excel saves "CSV UTF-8" with a byte-order mark (BOM, `\\ufeff`) at the start of the file. `text()` keeps it, so the first column is named `\\ufeffsku`, not `sku`. `event.http.body` is bytes [docs/handlers.md#httprequest]. Decoding it with `utf-8-sig` drops the BOM, and files without one still work.

- Before: 500, `KeyError: 'sku'`.
- After: `{"imported": 2, "items": {"A-100": 4, "B-200": 7}}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 187 gcp schedule, iterating the input dict
    B(187, provider="gcp", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: nightly-export\n" + GCP.format(region="us-east1") + """functions:
  export:
    handler: app.export.run
    events:
      - schedule:
          cron: "0 2 * * *"
          input:
            tables: [orders, customers]
""",
          "app/__init__.py": "",
          "app/export.py": FUTURE + """
def run(event, ctx):
    exported = []
    for table in event.data:
        exported.append(f"gs://exports/{table}.csv")
    ctx.logger.info("export done", extra={"files": len(exported)})
    return {"files": exported}
""",
          "requirements.txt": ""}),
      user="export writes tables.csv instead of orders.csv + customers.csv. input is tables: [orders, customers]",
      steps=[
          S("read_file", path="app/export.py"),
          S("invoke_local", function="export", type="schedule"),
          S("propose_plan", steps=["Loop over `event.data[\"tables\"]`, not over the dict itself",
                                   "Run the schedule with its configured input; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/export.py", content=FUTURE + """
def run(event, ctx):
    exported = []
    for table in event.data.get("tables", []):
        exported.append(f"gs://exports/{table}.csv")
    ctx.logger.info("export done", extra={"files": len(exported)})
    return {"files": exported}
"""),
          S("invoke_local", function="export", type="schedule"),
          S("validate"),
      ],
      final="""`event.data` is the whole `input` mapping [docs/events.md#schedule], and looping over a dict gives its keys, so the only "table" was `tables`. The loop now reads `event.data.get("tables", [])`.

- Before: `["gs://exports/tables.csv"]`.
- After: `["gs://exports/orders.csv", "gs://exports/customers.csv"]`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 188 onprem http, re.match without an end anchor
    B(188, provider="onprem", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: catalog\n" + ONPREM.format(port=8604) + """functions:
  add-product:
    handler: app.catalog.add
    events:
      - http: POST /products
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """import re

from py_serverless_kit import BadRequest

SKU = re.compile(r"[A-Z]{3}-\\d{4}")


def add(event, ctx):
    sku = event.http.json().get("sku", "")
    if not SKU.match(sku):
        raise BadRequest("sku must look like ABC-1234")
    return {"sku": sku}, 201
""",
          "requirements.txt": ""}),
      user="sku check lets ABC-12345-old through. should be exactly ABC-1234",
      steps=[
          S("read_file", path="app/catalog.py"),
          S("invoke_local", function="add-product", method="POST", path="/products", data={"sku": "ABC-12345-old"}),
          S("propose_plan", steps=["Use `SKU.fullmatch(sku)`: `match()` only anchors the start",
                                   "POST `ABC-12345-old` (must be 400) and `ABC-1234` (201); validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/catalog.py", content=FUTURE + """import re

from py_serverless_kit import BadRequest

SKU = re.compile(r"[A-Z]{3}-\\d{4}")


def add(event, ctx):
    sku = event.http.json().get("sku", "")
    if not SKU.fullmatch(sku):
        raise BadRequest("sku must look like ABC-1234")
    return {"sku": sku}, 201
"""),
          S("invoke_local", function="add-product", method="POST", path="/products", data={"sku": "ABC-12345-old"}),
          S("invoke_local", function="add-product", method="POST", path="/products", data={"sku": "ABC-1234"}),
          S("validate"),
      ],
      final="""`re.match` anchors only the start: `ABC-1234` matched the first 8 characters and the rest was ignored. `fullmatch` requires the whole string to match.

- `ABC-12345-old`: was 201, now 400 `sku must look like ABC-1234` [docs/handlers.md#errors].
- `ABC-1234`: 201.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 189 aws http, naive utcfromtimestamp
    B(189, provider="aws", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: parcel-track
provider:
  name: aws
  region: ap-southeast-2
functions:
  eta:
    handler: app.eta.get_eta
    events:
      - http: GET /parcels/{id}/eta
""",
          "app/__init__.py": "",
          "app/eta.py": FUTURE + """from datetime import datetime

ETAS = {"P-77": 1793520000}


def get_eta(event, ctx):
    ts = ETAS.get(event.http.path_params["id"], 0)
    return {"eta": datetime.utcfromtimestamp(ts).isoformat()}
""",
          "requirements.txt": ""}),
      user="eta time is wrong in the app for users in sydney, it show 08:00 but delivery is 19:00 local. backend send utc no?",
      steps=[
          S("read_file", path="app/eta.py"),
          S("invoke_local", function="eta", path="/parcels/P-77/eta"),
          S("propose_plan", steps=["Build an aware UTC datetime: `datetime.fromtimestamp(ts, tz=timezone.utc)`, so the ISO string ends with `+00:00`",
                                   "GET /parcels/P-77/eta locally and validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/eta.py", content=FUTURE + """from datetime import datetime, timezone

ETAS = {"P-77": 1793520000}


def get_eta(event, ctx):
    ts = ETAS.get(event.http.path_params["id"], 0)
    return {"eta": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()}
"""),
          S("invoke_local", function="eta", path="/parcels/P-77/eta"),
          S("validate"),
      ],
      final="""The time is UTC, but the string doesn't say so. `utcfromtimestamp()` gives a *naive* datetime, so the ISO text has no offset and the app reads `08:00` as local time. With `tz=timezone.utc` the value ends with `+00:00`, and the app converts it to Sydney time (19:00).

- Before: `"2026-11-01T08:00:00"`.
- After: `"2026-11-01T08:00:00+00:00"`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 190 onprem queue, millisecond timestamps
    B(190, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: iot-ingest\n" + ONPREM.format(port=8605) + """functions:
  readings:
    handler: app.readings.store
    events:
      - queue: sensor-readings
""",
          "app/__init__.py": "",
          "app/readings.py": FUTURE + """from datetime import datetime, timezone


def store(event, ctx):
    stored = []
    for record in event.records:
        msg = record.json()
        at = datetime.fromtimestamp(msg["ts"], tz=timezone.utc)
        stored.append({"sensor": msg["sensor"], "at": at.isoformat(), "value": msg["value"]})
    return {"stored": stored}
""",
          "requirements.txt": ""}),
      user="""readings: OSError: [Errno 22] Invalid argument
at datetime.fromtimestamp(msg["ts"], tz=timezone.utc). the sensors send ts like 1793520000000""",
      steps=[
          S("read_file", path="app/readings.py"),
          S("invoke_local", function="readings", type="queue",
            data=[{"sensor": "t-1", "ts": 1793520000000, "value": 21.5}]),
          S("propose_plan", steps=["The sensors send milliseconds: divide `ts` by 1000 before `fromtimestamp`",
                                   "Invoke with a millisecond timestamp; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/readings.py", content=FUTURE + """from datetime import datetime, timezone


def store(event, ctx):
    stored = []
    for record in event.records:
        msg = record.json()
        at = datetime.fromtimestamp(msg["ts"] / 1000, tz=timezone.utc)
        stored.append({"sensor": msg["sensor"], "at": at.isoformat(), "value": msg["value"]})
    return {"stored": stored}
"""),
          S("invoke_local", function="readings", type="queue",
            data=[{"sensor": "t-1", "ts": 1793520000000, "value": 21.5}]),
          S("validate"),
      ],
      final="""`1793520000000` is in **milliseconds**, but `fromtimestamp()` expects seconds, so Python computed a date in the year 58804, which the OS can't convert (`OSError` here; on Linux the same input gives `ValueError: year ... is out of range`). The handler now divides by 1000.

- After: `"at": "2026-11-01T08:00:00+00:00"`.
- validate (onprem, prod): valid.

On premises a message that raises is retried and then goes to the dead-letter queue if one is set, so messages that failed before the fix may be waiting there."""),

    # ------------------------------------------------------------------ 191 azure queue, nested JSON string
    B(191, provider="azure", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: shop-sync
provider:
  name: azure
  region: eastus
functions:
  sync-order:
    handler: app.sync.handle
    events:
      - queue: shop-orders
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """
def handle(event, ctx):
    skus = []
    for record in event.records:
        msg = record.json()
        skus.append(msg["payload"]["sku"])
    return {"skus": skus}
""",
          "requirements.txt": ""}),
      user="the shop puts messages like {\"type\": \"order\", \"payload\": \"{\\\"sku\\\": \\\"KX-1\\\"}\"} in the queue and my function says string indices must be integers. what does that mean?",
      steps=[
          S("read_file", path="app/sync.py"),
          S("invoke_local", function="sync-order", type="queue",
            data=[{"type": "order", "payload": "{\"sku\": \"KX-1\"}"}]),
          S("propose_plan", steps=["`payload` is JSON inside a string: parse it with `json.loads` (and accept a dict too)",
                                   "Invoke with the shop's message; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sync.py", content=FUTURE + """import json


def handle(event, ctx):
    skus = []
    for record in event.records:
        msg = record.json()
        payload = msg["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        skus.append(payload["sku"])
    return {"skus": skus}
"""),
          S("invoke_local", function="sync-order", type="queue",
            data=[{"type": "order", "payload": "{\"sku\": \"KX-1\"}"}]),
          S("validate"),
      ],
      final="""`record.json()` parses the message once [docs/handlers.md#record]. But the shop wrapped `payload` in quotes, so it is still a **string** of JSON. `"..."["sku"]` asks for a letter by name, and Python only allows numbers there. That's the error. The handler now parses `payload` with `json.loads` when it is a string.

- Before: `TypeError: string indices must be integers`.
- After: `{"skus": ["KX-1"]}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 192 gcp http, page numbers start at 1
    B(192, provider="gcp", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: movie-list\n" + GCP.format(region="asia-northeast1") + """functions:
  movies:
    handler: app.movies.list_movies
    events:
      - http: GET /movies
""",
          "app/__init__.py": "",
          "app/movies.py": FUTURE + """MOVIES = [f"movie-{n}" for n in range(1, 8)]
PAGE_SIZE = 3


def list_movies(event, ctx):
    page = int(event.http.query.get("page", "1"))
    start = page * PAGE_SIZE
    return {"page": page, "items": MOVIES[start:start + PAGE_SIZE]}
""",
          "requirements.txt": ""}),
      user="page=1 show movie-4,5,6. movie 1 to 3 never show in app",
      steps=[
          S("read_file", path="app/movies.py"),
          S("invoke_local", function="movies", path="/movies?page=1"),
          S("propose_plan", steps=["Pages start at 1, so the offset is `(page - 1) * PAGE_SIZE`; reject page < 1 with 400",
                                   "GET /movies?page=1 locally and validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/movies.py", content=FUTURE + """from py_serverless_kit import BadRequest

MOVIES = [f"movie-{n}" for n in range(1, 8)]
PAGE_SIZE = 3


def list_movies(event, ctx):
    page = int(event.http.query.get("page", "1"))
    if page < 1:
        raise BadRequest("page starts at 1")
    start = (page - 1) * PAGE_SIZE
    return {"page": page, "items": MOVIES[start:start + PAGE_SIZE]}
"""),
          S("invoke_local", function="movies", path="/movies?page=1"),
          S("validate"),
      ],
      final="""Page 1 started at `1 * 3 = 3`, the 4th movie, because the code counted pages from 0. Now the offset is `(page - 1) * 3`, and `page=0` gives 400.

- Before: page 1 = `movie-4, movie-5, movie-6`.
- After: page 1 = `movie-1, movie-2, movie-3`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 193 onprem queue, retry loop swallows the error
    B(193, provider="onprem", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": "service: invoice-mailer\n" + ONPREM.format(port=8606) + """functions:
  mailer:
    handler: app.mailer.handle
    events:
      - queue:
          name: invoices
          dead_letter: invoices-dlq
          max_receive: 3
""",
          "app/__init__.py": "",
          "app/mailer.py": FUTURE + """
def send(invoice):
    if "@" not in invoice["email"]:
        raise ValueError(f"bad address {invoice['email']!r}")


def handle(event, ctx):
    for record in event.records:
        invoice = record.json()
        for attempt in range(3):
            try:
                send(invoice)
                break
            except ValueError:
                ctx.logger.warning("send failed", extra={"attempt": attempt})
""",
          "requirements.txt": ""}),
      user="The mailer queue has dead_letter: invoices-dlq and max_receive: 3, but invoices-dlq stays empty even though some invoices have broken addresses and never get sent. I want messages that keep failing to land in the DLQ so we can look at them. Valid invoices in the same batch must not be re-sent.",
      steps=[
          S("read_file", path="app/mailer.py"),
          S("invoke_local", function="mailer", type="queue",
            data=[{"id": 1, "email": "ana@example.com"}, {"id": 2, "email": "broken"}]),
          S("search_docs", query="batchresult onprem dead letter max_receive",
            docs=[D("docs/handlers.md", "batchresult", start="| Provider |", end="after `max_receive` |")]),
          S("propose_plan", steps=["Remove the in-handler retry loop; mark a failing message with `result.fail(record)` and return the `BatchResult`",
                                   "Invoke with one good and one broken invoice; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/mailer.py", content=FUTURE + """from py_serverless_kit import BatchResult


def send(invoice):
    if "@" not in invoice["email"]:
        raise ValueError(f"bad address {invoice['email']!r}")


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            send(record.json())
        except ValueError:
            ctx.logger.warning("send failed", extra={"message_id": record.id})
            result.fail(record)
    return result
"""),
          S("invoke_local", function="mailer", type="queue",
            data=[{"id": 1, "email": "ana@example.com"}, {"id": 2, "email": "broken"}]),
          S("validate"),
      ],
      final="""The retry loop caught the error three times and then ended normally, so the host saw a successful delivery and deleted the message. It never reached `max_receive`. Now the handler reports the failing message with `BatchResult.fail(record)`. On premises the host retries only that id and moves it to `dead_letter` after `max_receive` attempts [docs/handlers.md#batchresult]. The good invoice in the same batch is not re-sent.

- Before: `null` (everything looked fine).
- After: `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 194 aws http, str in bytes
    B(194, provider="aws", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: mail-hooks
provider:
  name: aws
  region: us-west-2
functions:
  inbound:
    handler: app.inbound.handle
    events:
      - http: POST /hooks/inbound
""",
          "app/__init__.py": "",
          "app/inbound.py": FUTURE + """
def handle(event, ctx):
    wants_out = "unsubscribe" in event.http.body.lower()
    return {"unsubscribe": wants_out}
""",
          "requirements.txt": ""}),
      user="""TypeError: a bytes-like object is required, not 'str'
on POST /hooks/inbound, body is plain text from the mail provider""",
      steps=[
          S("read_file", path="app/inbound.py"),
          S("invoke_local", function="inbound", method="POST", path="/hooks/inbound", data="Please UNSUBSCRIBE me"),
          S("propose_plan", steps=["Search the decoded text: `event.http.text()` instead of the raw `body` bytes",
                                   "POST a plain-text body locally and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/inbound.py", content=FUTURE + """
def handle(event, ctx):
    wants_out = "unsubscribe" in event.http.text().lower()
    return {"unsubscribe": wants_out}
"""),
          S("invoke_local", function="inbound", method="POST", path="/hooks/inbound", data="Please UNSUBSCRIBE me"),
          S("validate"),
      ],
      final="""`event.http.body` is `bytes` [docs/handlers.md#httprequest], and Python can't look for a `str` inside bytes. `event.http.text()` decodes the body to a string first.

- Before: 500 (TypeError).
- After: `{"unsubscribe": true}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 195 onprem http, set_cookie positional max_age
    B(195, provider="onprem", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: portal-login\n" + ONPREM.format(port=8607) + """functions:
  login:
    handler: app.login.login
    events:
      - http: POST /login
""",
          "app/__init__.py": "",
          "app/login.py": FUTURE + """import secrets

from py_serverless_kit import Response, Unauthorized


def login(event, ctx):
    body = event.http.json()
    if not body.get("user"):
        raise Unauthorized("missing user")
    sid = secrets.token_urlsafe(16)
    return Response.json({"ok": True}).set_cookie("sid", sid, 3600)
""",
          "requirements.txt": ""}),
      user="login 500s. TypeError set_cookie() takes 3 positional arguments but 4 were given",
      steps=[
          S("read_file", path="app/login.py"),
          S("invoke_local", function="login", method="POST", path="/login", data={"user": "kim"}),
          S("propose_plan", steps=["Pass `max_age=3600` as a keyword: the options of `set_cookie` are keyword-only",
                                   "POST /login locally and validate for onprem"]),
          S("write_file", path="app/login.py", content=FUTURE + """import secrets

from py_serverless_kit import Response, Unauthorized


def login(event, ctx):
    body = event.http.json()
    if not body.get("user"):
        raise Unauthorized("missing user")
    sid = secrets.token_urlsafe(16)
    return Response.json({"ok": True}).set_cookie("sid", sid, max_age=3600)
"""),
          S("invoke_local", function="login", method="POST", path="/login", data={"user": "kim"}),
          S("validate"),
      ],
      final="""`set_cookie(name, value, *, max_age=..., ...)`: everything after the value is keyword-only [docs/handlers.md#returning-a-response]. Fixed to `max_age=3600`.

- POST /login: 200 `{"ok": true}`, with the `sid` cookie set (`HttpOnly`, `Secure`, `SameSite=Lax` are the defaults).
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 196 azure http, hard-coded wildcard CORS header
    B(196, provider="azure", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: profile-api
provider:
  name: azure
  region: westeurope
functions:
  me:
    handler: app.me.me
    events:
      - http:
          path: /me
          method: GET
          cors:
            origins: ["https://app.example.com"]
            allow_credentials: true
""",
          "app/__init__.py": "",
          "app/me.py": FUTURE + """
def me(event, ctx):
    user = event.http.cookies.get("sid", "anonymous")
    return {"user": user}, 200, {"access-control-allow-origin": "*"}
""",
          "requirements.txt": ""}),
      user="""Access to fetch at '.../me' from origin 'https://app.example.com' has been blocked by CORS policy: The value of the 'Access-Control-Allow-Origin' header in the response must not be the wildcard '*' when the request's credentials mode is 'include'.
cors in pskit.yml has our origin + allow_credentials, so where does the * come from?""",
      steps=[
          S("read_file", path="app/me.py"),
          S("invoke_local", function="me", path="/me"),
          S("search_docs", query="cors origins allow_credentials",
            docs=[D("docs/events.md", "http", start="**CORS**", end="AWS additionally configures CORS on the HTTP API.")]),
          S("propose_plan", steps=["Remove the hand-written `access-control-allow-origin: *` header; the `cors:` config adds the right headers",
                                   "GET /me locally and validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/me.py", content=FUTURE + """
def me(event, ctx):
    user = event.http.cookies.get("sid", "anonymous")
    return {"user": user}
"""),
          S("invoke_local", function="me", path="/me"),
          S("validate"),
      ],
      final="""The `*` comes from the handler: it returns its own `access-control-allow-origin: *` header, and pskit's CORS step doesn't overwrite a header that is already there. The runtime adds the `Access-Control-*` headers from your `cors:` config by itself [docs/events.md#http]. I removed the hand-written header.

- Before: the local response had `access-control-allow-origin: *`.
- After: no CORS headers locally, because the test request has no `Origin` header. In the browser, a request from `https://app.example.com` gets that origin back plus `access-control-allow-credentials: true`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 197 gcp queue, chunk loop misses the last item
    B(197, provider="gcp", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: push-sender\n" + GCP.format(region="europe-west4") + """functions:
  push:
    handler: app.push.handle
    events:
      - queue: push-jobs
""",
          "app/__init__.py": "",
          "app/push.py": FUTURE + """CHUNK = 3


def handle(event, ctx):
    devices = event.json()["tokens"]
    batches = []
    for i in range(0, len(devices) - 1, CHUNK):
        batches.append(devices[i:i + CHUNK])
    sent = sum(len(b) for b in batches)
    ctx.logger.info("push sent", extra={"batches": len(batches), "sent": sent})
    return {"sent": sent, "batches": batches}
""",
          "requirements.txt": ""}),
      user="push job w/ 7 tokens sends 6. last one dropped",
      steps=[
          S("read_file", path="app/push.py"),
          S("invoke_local", function="push", type="queue",
            data=[{"tokens": ["t1", "t2", "t3", "t4", "t5", "t6", "t7"]}]),
          S("propose_plan", steps=["Chunk with `range(0, len(devices), CHUNK)`: the `- 1` stops before the last chunk",
                                   "Invoke with 7 tokens; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/push.py", content=FUTURE + """CHUNK = 3


def handle(event, ctx):
    devices = event.json()["tokens"]
    batches = [devices[i:i + CHUNK] for i in range(0, len(devices), CHUNK)]
    sent = sum(len(b) for b in batches)
    ctx.logger.info("push sent", extra={"batches": len(batches), "sent": sent})
    return {"sent": sent, "batches": batches}
"""),
          S("invoke_local", function="push", type="queue",
            data=[{"tokens": ["t1", "t2", "t3", "t4", "t5", "t6", "t7"]}]),
          S("validate"),
      ],
      final="""`range(0, 7 - 1, 3)` is `0, 3`: the chunk at index 6 never starts. Fixed to `range(0, len(devices), CHUNK)`; slicing past the end is safe.

- Before: `sent: 6`, 2 batches.
- After: `sent: 7`, 3 batches (`["t7"]` last).
- validate (gcp): valid.

`event.json()` reads only the first message; fine with one job per message, otherwise loop over `event.records`."""),

    # ------------------------------------------------------------------ 198 onprem schedule, %M vs %m
    B(198, provider="onprem", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: month-report\n" + ONPREM.format(port=8608) + """functions:
  report:
    handler: app.report.run
    events:
      - schedule:
          cron: "0 6 1 * *"
          input:
            day: "2026-11-01"
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """from datetime import date


def run(event, ctx):
    day = date.fromisoformat(event.data["day"])
    name = day.strftime("reports/%Y-%M-%d.csv")
    ctx.logger.info("writing report", extra={"file": name})
    return {"file": name}
""",
          "requirements.txt": ""}),
      user="the monthly report file is called reports/2026-00-01.csv. why 00, it is november?",
      steps=[
          S("read_file", path="app/report.py"),
          S("invoke_local", function="report", type="schedule"),
          S("propose_plan", steps=["Use `%m` (month) instead of `%M` (minutes) in the file name",
                                   "Run the schedule with its input; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/report.py", content=FUTURE + """from datetime import date


def run(event, ctx):
    day = date.fromisoformat(event.data["day"])
    name = day.strftime("reports/%Y-%m-%d.csv")
    ctx.logger.info("writing report", extra={"file": name})
    return {"file": name}
"""),
          S("invoke_local", function="report", type="schedule"),
          S("validate"),
      ],
      final="""In `strftime`, `%M` is **minutes** (a date has none, so `00`) and `%m` is the month. Changed to `%Y-%m-%d`.

- Before: `reports/2026-00-01.csv`.
- After: `reports/2026-11-01.csv`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 199 azure topic, findall with a group
    B(199, provider="azure", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: support-links
provider:
  name: azure
  region: uksouth
functions:
  link-tickets:
    handler: app.links.handle
    events:
      - topic: chat-messages
""",
          "app/__init__.py": "",
          "app/links.py": FUTURE + """import re

TICKET = re.compile(r"\\b(OPS|DEV)-\\d+\\b")


def handle(event, ctx):
    refs = []
    for record in event.records:
        refs.extend(TICKET.findall(record.text()))
    return {"tickets": refs}
""",
          "requirements.txt": ""}),
      user="link-tickets should pull ticket ids like OPS-12 or DEV-7 out of chat messages published on chat-messages. It finds the right number of tickets, but the list only has the prefixes (\"OPS\", \"DEV\") without the numbers. Please make it return the full ids.",
      steps=[
          S("read_file", path="app/links.py"),
          S("invoke_local", function="link-tickets", type="topic",
            data=["deploy blocked by OPS-12", "see DEV-7 and OPS-3"]),
          S("propose_plan", steps=["Make the group non-capturing `(?:OPS|DEV)`, so `findall` returns the whole match",
                                   "Invoke with two chat messages; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/links.py", content=FUTURE + """import re

TICKET = re.compile(r"\\b(?:OPS|DEV)-\\d+\\b")


def handle(event, ctx):
    refs = []
    for record in event.records:
        refs.extend(TICKET.findall(record.text()))
    return {"tickets": refs}
"""),
          S("invoke_local", function="link-tickets", type="topic",
            data=["deploy blocked by OPS-12", "see DEV-7 and OPS-3"]),
          S("validate"),
      ],
      final="""When a pattern has a capturing group, `re.findall` returns only what the **group** matched (`OPS`), not the whole match. A non-capturing group `(?:OPS|DEV)` keeps the alternation without capturing, so `findall` returns the full ids.

- Before: `["OPS", "DEV", "OPS"]`.
- After: `["OPS-12", "DEV-7", "OPS-3"]`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 200 aws http, Node.js snake_case pathParams
    B(200, provider="aws", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: orders-js
provider:
  name: aws
  region: us-east-1
  runtime: nodejs20
functions:
  get-order:
    handler: src.orders.getOrder
    events:
      - http: GET /orders/{id}
""",
          "src/orders.js": """const ORDERS = { "41": { id: "41", total: 18.5 } };

exports.getOrder = async (event, ctx) => {
  const id = event.http.path_params.id;
  return ORDERS[id] ?? { error: "not found" };
};
"""}),
      user="""TypeError: Cannot read properties of undefined (reading 'id')
    at exports.getOrder (src/orders.js:4)
GET /orders/41""",
      steps=[
          S("read_file", path="src/orders.js"),
          S("invoke_local", function="get-order", path="/orders/41"),
          S("search_docs", query="nodejs handler pathParams camelCase",
            docs=[D("docs/nodejs.md", "handlers", start="The API mirrors", end="`resource(\"orders\")`.")]),
          S("propose_plan", steps=["Use `event.http.pathParams` (camelCase in Node.js); throw `NotFound` for an unknown id",
                                   "GET /orders/41 locally and validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/orders.js", content="""const { NotFound } = require("pskit");

const ORDERS = { "41": { id: "41", total: 18.5 } };

exports.getOrder = async (event, ctx) => {
  const order = ORDERS[event.http.pathParams.id];
  if (!order) throw new NotFound("no such order");
  return order;
};
"""),
          S("invoke_local", function="get-order", path="/orders/41"),
          S("validate"),
      ],
      final="""In Node.js the handler API is camelCase: `event.http.pathParams`, not `path_params` [docs/nodejs.md#handlers]. `path_params` is `undefined`, so reading `.id` from it throws. I also made an unknown id throw `NotFound` (404) instead of returning an error object with status 200.

- GET /orders/41: 200, `{"id": "41", "total": 18.5}`.
- validate (aws, staging): valid."""),
]
