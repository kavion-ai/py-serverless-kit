"""Category D (fix a handler bug), batch 5. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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


def B(n, **kw):
    return dict(id=f"d_debug-{n:04d}", category="d_debug", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 81  onprem http, import of a name pskit doesn't have
    B(81, provider="onprem", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: stock-api\n" + ONPREM.format(port=8201) + """functions:
  stock:
    handler: app.stock.get_stock
    events:
      - http: GET /stock/{sku}
""",
          "app/__init__.py": "",
          "app/stock.py": FUTURE + """from py_serverless_kit import ServiceUnavailable

MAINTENANCE = False


def get_stock(event, ctx):
    if MAINTENANCE:
        raise ServiceUnavailable("stock service is in maintenance")
    return {"sku": event.http.path_params["sku"], "available": 12}
""",
          "requirements.txt": ""}),
      user="""ImportError: cannot import name 'ServiceUnavailable' from 'py_serverless_kit'
every call to /stock/{sku} is 500 now""",
      steps=[
          S("read_file", path="app/stock.py"),
          S("invoke_local", function="stock", path="/stock/A-100"),
          S("search_docs", query="http error classes status 503",
            docs=[D("docs/handlers.md", "errors", end="| `HttpError(message, status=..., details=..., headers=...)` | any |")]),
          S("propose_plan", steps=["Drop the `ServiceUnavailable` import; raise `HttpError(\"...\", status=503)` instead",
                                   "GET /stock/A-100 locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/stock.py", content=FUTURE + """from py_serverless_kit import HttpError

MAINTENANCE = False


def get_stock(event, ctx):
    if MAINTENANCE:
        raise HttpError("stock service is in maintenance", status=503)
    return {"sku": event.http.path_params["sku"], "available": 12}
"""),
          S("invoke_local", function="stock", path="/stock/A-100"),
          S("validate"),
      ],
      final="""pskit has no `ServiceUnavailable` class, so the module could not be imported and every request failed before your code ran. For a status without its own class, use `HttpError(message, status=...)` [docs/handlers.md#errors]. I now raise `HttpError("stock service is in maintenance", status=503)`.

- GET /stock/A-100: 200, `{"sku": "A-100", "available": 12}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 82  aws http, ctx.aws_request_id
    B(82, provider="aws", stage="prod", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: tickets
provider:
  name: aws
  region: us-east-2
functions:
  open-ticket:
    handler: app.tickets.open_ticket
    events:
      - http: POST /tickets
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """
def open_ticket(event, context):
    data = event.http.json()
    ticket_id = "T-" + context.aws_request_id[:8]
    context.logger.info("ticket opened", extra={"ticket": ticket_id})
    return {"id": ticket_id, "title": data.get("title", "")}, 201
""",
          "requirements.txt": ""}),
      user="In Lambda I used context.aws_request_id for ticket ids. After moving to pskit, POST /tickets returns 500. Does the pskit context have a request id?",
      steps=[
          S("read_file", path="app/tickets.py"),
          S("invoke_local", function="open-ticket", method="POST", path="/tickets", data={"title": "VPN down"}),
          S("search_docs", query="context request id attributes",
            docs=[D("docs/handlers.md", "context")]),
          S("propose_plan", steps=["Use `context.request_id` instead of the Lambda-only `context.aws_request_id`",
                                   "POST /tickets locally and validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tickets.py", content=FUTURE + """
def open_ticket(event, context):
    data = event.http.json()
    ticket_id = "T-" + context.request_id[:8]
    context.logger.info("ticket opened", extra={"ticket": ticket_id})
    return {"id": ticket_id, "title": data.get("title", "")}, 201
"""),
          S("invoke_local", function="open-ticket", method="POST", path="/tickets", data={"title": "VPN down"}),
          S("validate"),
      ],
      final="""Yes: `context.request_id` [docs/handlers.md#context]. The pskit `Context` is the same on every cloud, so Lambda-only names like `aws_request_id` don't exist and raised `AttributeError`. On Lambda, `request_id` is the platform request id; locally it is a UUID.

- POST /tickets: 201 with `{"id": "T-...", "title": "VPN down"}`.
- validate (aws, prod): valid.

If you still need the Lambda object, `context.raw` has it, but that code is no longer portable."""),

    # ------------------------------------------------------------------ 83  gcp queue, env var name mismatch
    B(83, provider="gcp", stage="dev", mode="auto", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: thumbs
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  resize:
    handler: app.resize.handle
    environment:
      MAX_WIDTH: "800"
    events:
      - queue: resize-jobs
""",
          "app/__init__.py": "",
          "app/resize.py": FUTURE + """import os


def handle(event, ctx):
    limit = int(os.environ.get("MAX_SIZE"))
    done = []
    for record in event.records:
        job = record.json()
        done.append(min(job["width"], limit))
    return {"widths": done}
""",
          "requirements.txt": ""}),
      user="resize worker crash int() argument must be ... not 'NoneType'. but i set the width in yml environment??",
      steps=[
          S("get_project"),
          S("read_file", path="app/resize.py"),
          S("invoke_local", function="resize", type="queue", data=[{"width": 1200}, {"width": 640}]),
          S("propose_plan", steps=["Read `MAX_WIDTH` (the name in pskit.yml) instead of `MAX_SIZE`, with a default of 800",
                                   "Invoke resize with two jobs and validate for gcp"]),
          S("write_file", path="app/resize.py", content=FUTURE + """import os


def handle(event, ctx):
    limit = int(os.environ.get("MAX_WIDTH", "800"))
    done = []
    for record in event.records:
        job = record.json()
        done.append(min(job["width"], limit))
    return {"widths": done}
"""),
          S("invoke_local", function="resize", type="queue", data=[{"width": 1200}, {"width": 640}]),
          S("validate"),
      ],
      final="""The name is different: pskit.yml sets `MAX_WIDTH`, but the code reads `MAX_SIZE`. That variable doesn't exist, so `get()` gave `None` and `int(None)` failed. Now the code reads `MAX_WIDTH` (default `"800"`). Environment values are always strings, so the `int()` stays.

- invoke with widths 1200 and 640: `{"widths": [800, 640]}`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 84  onprem storage, record.name
    B(84, provider="onprem", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: scans\n" + ONPREM.format(port=8202) + """functions:
  on-scan:
    handler: app.scans.on_scan
    events:
      - storage:
          bucket: scanner-inbox
          events: [created]
""",
          "app/__init__.py": "",
          "app/scans.py": FUTURE + """
def on_scan(event, ctx):
    files = []
    for record in event.records:
        files.append(record.name)
        ctx.logger.info("new scan", extra={"file": record.name})
    return {"files": files}
""",
          "requirements.txt": ""}),
      user="I want to log the file name when a scan is dropped in the bucket but it says Record has no attribute name. what is the right name for the file name?",
      steps=[
          S("read_file", path="app/scans.py"),
          S("invoke_local", function="on-scan", type="storage", data=[{"key": "2026/11/scan-001.pdf", "size": 48213}]),
          S("search_docs", query="storage record file name key bucket",
            docs=[D("docs/handlers.md", "record")]),
          S("propose_plan", steps=["Use `record.key` (the object name) instead of `record.name`",
                                   "Invoke on-scan with a test file and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/scans.py", content=FUTURE + """
def on_scan(event, ctx):
    files = []
    for record in event.records:
        files.append(record.key)
        ctx.logger.info("new scan", extra={"file": record.key, "bucket": record.bucket})
    return {"files": files}
"""),
          S("invoke_local", function="on-scan", type="storage", data=[{"key": "2026/11/scan-001.pdf", "size": 48213}]),
          S("validate"),
      ],
      final="""The file name is `record.key` [docs/handlers.md#record]. It is the full name inside the bucket, folders included. `record.bucket` is the bucket and `record.size` the size in bytes. I also added the bucket to the log line.

- Test with `2026/11/scan-001.pdf`: logs "new scan" and returns `{"files": ["2026/11/scan-001.pdf"]}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 85  azure http, dict_keys in the response
    B(85, provider="azure", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: azure
  region: westeurope
functions:
  categories:
    handler: app.catalog.categories
    events:
      - http: GET /categories
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """PRODUCTS = [
    {"sku": "A1", "category": "garden"},
    {"sku": "B2", "category": "kitchen"},
    {"sku": "C3", "category": "garden"},
]


def categories(event, ctx):
    counts = {}
    for p in PRODUCTS:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    return {"names": counts.keys(), "counts": counts}
""",
          "requirements.txt": ""}),
      user="GET /categories give 500 and log say dict_keys is not JSON serializable. i thought pskit convert everything to json",
      steps=[
          S("read_file", path="app/catalog.py"),
          S("invoke_local", function="categories", path="/categories"),
          S("search_docs", query="json serialisation of return values",
            docs=[D("docs/handlers.md", "returning-a-response", end="JSON serialisation handles")]),
          S("propose_plan", steps=["Return `sorted(counts)` (a list) instead of `counts.keys()`",
                                   "GET /categories locally and validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/catalog.py", content=FUTURE + """PRODUCTS = [
    {"sku": "A1", "category": "garden"},
    {"sku": "B2", "category": "kitchen"},
    {"sku": "C3", "category": "garden"},
]


def categories(event, ctx):
    counts = {}
    for p in PRODUCTS:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    return {"names": sorted(counts), "counts": counts}
"""),
          S("invoke_local", function="categories", path="/categories"),
          S("validate"),
      ],
      final="""pskit converts many types: dicts, lists, numbers, `datetime`, `Decimal`, `UUID`, `set`, dataclasses and objects with `model_dump()`/`to_dict()` [docs/handlers.md#returning-a-response]. A `dict_keys` view is not on that list, so turning the result into JSON failed (a 500 for the caller). Now `names` is `sorted(counts)`, a normal list.

- GET /categories: 200, `{"names": ["garden", "kitchen"], "counts": {"garden": 2, "kitchen": 1}}`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 86  onprem queue, fail(index)
    B(86, provider="onprem", stage="prod", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": "service: geo\n" + ONPREM.format(port=8203) + """functions:
  geocode:
    handler: app.geo.geocode
    events:
      - queue:
          name: addresses
          batch_size: 10
          max_receive: 3
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + """from py_serverless_kit import BatchResult


def geocode(event, ctx):
    result = BatchResult()
    for i, record in enumerate(event.records):
        addr = record.json()
        if not addr.get("zip"):
            result.fail(str(i))
            continue
        ctx.logger.info("geocoded", extra={"zip": addr["zip"]})
    return result
""",
          "requirements.txt": ""}),
      user="geocode: retries hit the wrong messages. failures report \"0\", \"1\"... looks off",
      steps=[
          S("read_file", path="app/geo.py"),
          S("invoke_local", function="geocode", type="queue", data=[{"zip": "10115"}, {"street": "no zip"}]),
          S("propose_plan", steps=["Pass the record to `result.fail(record)` so the message id is reported, not the loop index",
                                   "Invoke with one good and one bad address; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/geo.py", content=FUTURE + """from py_serverless_kit import BatchResult


def geocode(event, ctx):
    result = BatchResult()
    for record in event.records:
        addr = record.json()
        if not addr.get("zip"):
            result.fail(record)
            continue
        ctx.logger.info("geocoded", extra={"zip": addr["zip"]})
    return result
"""),
          S("invoke_local", function="geocode", type="queue", data=[{"zip": "10115"}, {"street": "no zip"}]),
          S("validate"),
      ],
      final="""Right. `fail()` takes a `Record` or its **id** [docs/handlers.md#batchresult]. You passed the loop index, so the host retried ids `"0"`, `"1"`, ... instead of the failed messages. Now it is `result.fail(record)`.

- invoke (good + missing zip): `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`, the real id of the second message.
- validate (onprem, prod): valid. With `max_receive: 3`, a message that keeps failing goes to the dead-letter queue."""),

    # ------------------------------------------------------------------ 87  aws schedule, remaining_time_ms not called
    B(87, provider="aws", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: archiver
provider:
  name: aws
  region: eu-central-1
functions:
  archive:
    handler: app.archive.run
    timeout: 300
    events:
      - schedule:
          cron: "30 1 * * *"
          input: {tables: [orders, invoices, refunds]}
""",
          "app/__init__.py": "",
          "app/archive.py": FUTURE + """
def run(event, ctx):
    done = []
    for table in event.data["tables"]:
        if ctx.remaining_time_ms < 30_000:
            ctx.logger.warning("stopping early", extra={"left": len(event.data["tables"]) - len(done)})
            break
        done.append(table)
    return {"archived": done}
""",
          "requirements.txt": ""}),
      user="The nightly archive job should stop before the Lambda timeout: if less than 30 seconds are left, log a warning and return what it finished. Right now it crashes on the first table with a TypeError about '<'. Please fix it and keep it working locally, where there is no timeout.",
      steps=[
          S("read_file", path="app/archive.py"),
          S("invoke_local", function="archive", type="schedule"),
          S("search_docs", query="remaining time context",
            docs=[D("docs/handlers.md", "context")]),
          S("propose_plan", steps=["Call `ctx.remaining_time_ms()` (it is a method) and skip the check when it returns None",
                                   "Run archive as a schedule event and validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/archive.py", content=FUTURE + """
def run(event, ctx):
    done = []
    for table in event.data["tables"]:
        left = ctx.remaining_time_ms()
        if left is not None and left < 30_000:
            ctx.logger.warning("stopping early", extra={"left": len(event.data["tables"]) - len(done)})
            break
        done.append(table)
    return {"archived": done}
"""),
          S("invoke_local", function="archive", type="schedule"),
          S("validate"),
      ],
      final="""`remaining_time_ms` is a **method**, so the code compared the method object with `30_000` [docs/handlers.md#context]. It now calls `ctx.remaining_time_ms()` and skips the check when the result is `None`. That happens locally, where there is no deadline. On Lambda you get the real milliseconds left.

- Local schedule run (configured input): `{"archived": ["orders", "invoices", "refunds"]}`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 88  onprem workflow task, returns a JSON string
    B(88, provider="onprem", stage="dev", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflows-state-machines"],
      project=dict(files={
          "pskit.yml": "service: fulfil\n" + ONPREM.format(port=8204) + """functions:
  pack:
    handler: app.steps.pack
  ship:
    handler: app.steps.ship
workflows:
  fulfil:
    start_at: Pack
    states:
      Pack: {type: task, function: pack, next: Ship}
      Ship: {type: task, function: ship, end: true}
""",
          "app/__init__.py": "",
          "app/steps.py": FUTURE + """import json


def pack(event, ctx):
    order = dict(event.data)
    order["boxes"] = max(1, len(order.get("items", [])) // 3)
    return json.dumps(order)


def ship(event, ctx):
    return {"order": event.data["id"], "boxes": event.data["boxes"], "shipped": True}
""",
          "requirements.txt": ""}),
      user="fulfil wf: Ship fails, TypeError string indices must be integers. pack output looks fine in logs",
      steps=[
          S("read_file", path="app/steps.py"),
          S("invoke_local", function="pack", type="workflow", data={"id": "o-17", "items": ["a", "b", "c", "d"]}),
          S("propose_plan", steps=["Return the dict from `pack` instead of `json.dumps(order)`",
                                   "Invoke pack and ship as workflow tasks; validate for onprem"]),
          S("write_file", path="app/steps.py", content=FUTURE + """
def pack(event, ctx):
    order = dict(event.data)
    order["boxes"] = max(1, len(order.get("items", [])) // 3)
    return order


def ship(event, ctx):
    return {"order": event.data["id"], "boxes": event.data["boxes"], "shipped": True}
"""),
          S("invoke_local", function="pack", type="workflow", data={"id": "o-17", "items": ["a", "b", "c", "d"]}),
          S("invoke_local", function="ship", type="workflow", data={"id": "o-17", "items": ["a", "b", "c", "d"], "boxes": 1}),
          S("validate"),
      ],
      final="""`pack` returned `json.dumps(order)`, a **string**. A task's return value is passed to the next state as is [docs/workflows.md#workflows-state-machines], so `Ship` got a string and `event.data["id"]` failed. Now `pack` returns the dict and the engine handles the JSON.

- pack: returns the object with `"boxes": 1` (before: one quoted JSON string).
- ship with that output: `{"order": "o-17", "boxes": 1, "shipped": true}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 89  gcp http, text without ()
    B(89, provider="gcp", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: notes
provider:
  name: gcp
  region: us-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  save-note:
    handler: app.notes.save
    events:
      - http: POST /notes
""",
          "app/__init__.py": "",
          "app/notes.py": FUTURE + """
def save(event, ctx):
    text = event.http.text.strip()
    if not text:
        return {"error": "empty"}, 400
    return {"saved": len(text)}, 201
""",
          "requirements.txt": ""}),
      user="save-note take plain text body. error 'function' object has no attribute 'strip'. what wrong",
      steps=[
          S("read_file", path="app/notes.py"),
          S("invoke_local", function="save-note", method="POST", path="/notes", data="buy milk"),
          S("propose_plan", steps=["Call `event.http.text()`: `text` is a method that decodes the body",
                                   "POST a plain-text note locally and validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/notes.py", content=FUTURE + """
def save(event, ctx):
    text = event.http.text().strip()
    if not text:
        return {"error": "empty"}, 400
    return {"saved": len(text)}, 201
"""),
          S("invoke_local", function="save-note", method="POST", path="/notes", data="buy milk"),
          S("validate"),
      ],
      final="""`text` is a method of `HttpRequest`: `text(encoding="utf-8")` returns the body as a string [docs/handlers.md#httprequest]. Without `()` you get the method itself, which has no `.strip()`. Now it is `event.http.text().strip()`.

- POST /notes "buy milk": 201, `{"saved": 8}`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 90  onprem smtp, attachment key
    B(90, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": """service: invoices-in
""" + ONPREM.format(port=8205) + """resources:
  invoice-mail:
    type: smtp
    external: true
    connection: {host: 192.0.2.20, port: 25, domains: invoices.example.com}
functions:
  on-invoice:
    handler: app.inbox.on_invoice
    events:
      - smtp: invoice-mail
""",
          "app/__init__.py": "",
          "app/inbox.py": FUTURE + """import base64


def on_invoice(event, ctx):
    mail = event.data
    pdfs = []
    for att in mail["attachments"]:
        if att["content_type"] == "application/pdf":
            data = base64.b64decode(att["data"])
            pdfs.append({"file": att["filename"], "bytes": len(data)})
    ctx.logger.info("invoice mail", extra={"from": mail["from"], "pdfs": len(pdfs)})
    return {"pdfs": pdfs}
""",
          "requirements.txt": ""}),
      user="on-invoice should collect every PDF attachment of an incoming mail (file name and size in bytes) and ignore other attachments. With a test mail that has one PDF it raises KeyError: 'data'. Please fix it and test with a mail that has a PDF and a PNG.",
      steps=[
          S("read_file", path="app/inbox.py"),
          S("invoke_local", function="on-invoice", type="smtp",
            data={"from": "billing@example.org", "subject": "Invoice 42", "text": "attached",
                  "attachments": [{"filename": "inv-42.pdf", "content_type": "application/pdf", "content": "%PDF-1.4 test"},
                                  {"filename": "logo.png", "content_type": "image/png", "content": "png"}]}),
          S("search_docs", query="smtp attachments content base64",
            docs=[D("docs/smtp/README.md", "what-the-handler-receives", end="return {\"ok\": True}")]),
          S("propose_plan", steps=["Decode `att[\"content\"]` (base64) instead of the missing `att[\"data\"]`",
                                   "Invoke with a PDF and a PNG attachment; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/inbox.py", content=FUTURE + """import base64


def on_invoice(event, ctx):
    mail = event.data
    pdfs = []
    for att in mail["attachments"]:
        if att["content_type"] == "application/pdf":
            data = base64.b64decode(att["content"])
            pdfs.append({"file": att["filename"], "bytes": len(data)})
    ctx.logger.info("invoice mail", extra={"from": mail["from"], "pdfs": len(pdfs)})
    return {"pdfs": pdfs}
"""),
          S("invoke_local", function="on-invoice", type="smtp",
            data={"from": "billing@example.org", "subject": "Invoice 42", "text": "attached",
                  "attachments": [{"filename": "inv-42.pdf", "content_type": "application/pdf", "content": "%PDF-1.4 test"},
                                  {"filename": "logo.png", "content_type": "image/png", "content": "png"}]}),
          S("validate"),
      ],
      final="""Each attachment carries its bytes base64-encoded under `content`, next to `filename`, `content_type` and `size` [docs/smtp/README.md#what-the-handler-receives]. There is no `data` key. The handler now decodes `att["content"]`.

- Test mail with `inv-42.pdf` and `logo.png`: `{"pdfs": [{"file": "inv-42.pdf", "bytes": 13}]}`; the PNG is skipped.
- validate (onprem, prod): valid.

`att["size"]` already has the size, so you can skip the decoding if you only need the number."""),

    # ------------------------------------------------------------------ 91  azure queue, gather not awaited
    B(91, provider="azure", stage="staging", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: pricing
provider:
  name: azure
  region: northeurope
functions:
  reprice:
    handler: app.reprice.handle
    events:
      - queue: reprice-jobs
""",
          "app/__init__.py": "",
          "app/reprice.py": FUTURE + """import asyncio


async def price_of(sku):
    await asyncio.sleep(0)
    return {"sku": sku, "price": 9.99}


async def handle(event, ctx):
    skus = [r.json()["sku"] for r in event.records]
    prices = asyncio.gather(*(price_of(s) for s in skus))
    return {"count": len(prices), "prices": prices}
""",
          "requirements.txt": ""}),
      user="reprice async handler: TypeError object of type '_GatheringFuture' has no len()",
      steps=[
          S("read_file", path="app/reprice.py"),
          S("invoke_local", function="reprice", type="queue", data=[{"sku": "A1"}, {"sku": "B2"}]),
          S("propose_plan", steps=["`await asyncio.gather(...)` so `prices` is the list of results"]),
          S("write_file", path="app/reprice.py", content=FUTURE + """import asyncio


async def price_of(sku):
    await asyncio.sleep(0)
    return {"sku": sku, "price": 9.99}


async def handle(event, ctx):
    skus = [r.json()["sku"] for r in event.records]
    prices = await asyncio.gather(*(price_of(s) for s in skus))
    return {"count": len(prices), "prices": prices}
"""),
          S("invoke_local", function="reprice", type="queue", data=[{"sku": "A1"}, {"sku": "B2"}]),
          S("validate"),
      ],
      final="""Missing `await`: `asyncio.gather()` returns a future, not the results. Fixed: `prices = await asyncio.gather(...)`. pskit awaits async handlers itself [docs/handlers.md#handler-signatures].

- invoke (A1, B2): `{"count": 2, "prices": [{"sku": "A1", "price": 9.99}, {"sku": "B2", "price": 9.99}]}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 92  onprem http, instance method as handler
    B(92, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": "service: staff\n" + ONPREM.format(port=8206) + """functions:
  list-staff:
    handler: app.staff.Staff.list_all
    events:
      - http: GET /staff
""",
          "app/__init__.py": "",
          "app/staff.py": FUTURE + """
class Staff:
    PEOPLE = [{"name": "Mira", "team": "ops"}, {"name": "Jon", "team": "dev"}]

    def list_all(self, event, ctx):
        team = event.http.query.get("team")
        people = [p for p in self.PEOPLE if team is None or p["team"] == team]
        return {"staff": people}
""",
          "requirements.txt": ""}),
      user="I put my handler in a class like I do in Java (handler: app.staff.Staff.list_all). Test gives 500: Cannot import module 'app.staff.Staff'. Can pskit use classes?",
      steps=[
          S("read_file", path="app/staff.py"),
          S("invoke_local", function="list-staff", path="/staff?team=ops"),
          S("search_docs", query="handler signature class method",
            docs=[D("docs/handlers.md", "handler-signatures")]),
          S("propose_plan", steps=["Keep the class; add a module-level `list_all = Staff().list_all` (one instance, a plain callable)",
                                   "Point the handler at it: `functions.list-staff.handler: app.staff.list_all`",
                                   "GET /staff?team=ops locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/staff.py", content=FUTURE + """
class Staff:
    PEOPLE = [{"name": "Mira", "team": "ops"}, {"name": "Jon", "team": "dev"}]

    def list_all(self, event, ctx):
        team = event.http.query.get("team")
        people = [p for p in self.PEOPLE if team is None or p["team"] == team]
        return {"staff": people}


list_all = Staff().list_all
"""),
          S("set_config", path="functions.list-staff.handler", value="app.staff.list_all"),
          S("invoke_local", function="list-staff", path="/staff?team=ops"),
          S("validate"),
      ],
      final="""You can keep the class, but the handler must be a module-level callable. `handler:` is `package.module.function` [docs/handlers.md#handler-signatures]. pskit treats everything before the last dot as the module, so it looked for a module `app.staff.Staff`. It also never creates an instance for you.

Fix:
- `app/staff.py` now ends with `list_all = Staff().list_all`: one instance, created at import, and its bound method.
- `handler: app.staff.list_all` in pskit.yml.

- GET /staff?team=ops: 200, `{"staff": [{"name": "Mira", "team": "ops"}]}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 93  aws topic, SNS envelope key
    B(93, provider="aws", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: alerts
provider:
  name: aws
  region: us-west-2
functions:
  page-oncall:
    handler: app.alerts.page
    events:
      - topic: incidents
""",
          "app/__init__.py": "",
          "app/alerts.py": FUTURE + """import json


def page(event, ctx):
    paged = []
    for record in event.records:
        alert = json.loads(record.json()["Message"])
        if alert["severity"] == "critical":
            paged.append(alert["service"])
    return {"paged": paged}
""",
          "requirements.txt": ""}),
      user="My SNS handler did json.loads(record['Sns']['Message']). I changed it to record.json()['Message'] for pskit, but now KeyError: 'Message'. What does record.json() give for a topic?",
      steps=[
          S("read_file", path="app/alerts.py"),
          S("invoke_local", function="page-oncall", type="topic",
            data=[{"severity": "critical", "service": "checkout"}, {"severity": "low", "service": "search"}]),
          S("search_docs", query="record body topic message",
            docs=[D("docs/handlers.md", "record")]),
          S("propose_plan", steps=["Use `record.json()` directly: it is already the published message, without the SNS envelope",
                                   "Invoke with a critical and a low alert; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/alerts.py", content=FUTURE + """
def page(event, ctx):
    paged = []
    for record in event.records:
        alert = record.json()
        if alert["severity"] == "critical":
            paged.append(alert["service"])
    return {"paged": paged}
"""),
          S("invoke_local", function="page-oncall", type="topic",
            data=[{"severity": "critical", "service": "checkout"}, {"severity": "low", "service": "search"}]),
          S("validate"),
      ],
      final="""`record.body` is already the **message** you published; the SNS envelope is gone. So `record.json()` is your alert dict, and it has no `Message` key [docs/handlers.md#record]. The handler now uses `record.json()` directly and no longer needs `json`.

- invoke (critical + low): `{"paged": ["checkout"]}`.
- validate (aws): valid.

SNS message attributes are in `record.attributes`, and the native record is in `record.raw` if you really need it."""),

    # ------------------------------------------------------------------ 94  onprem http, missing header KeyError
    B(94, provider="onprem", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: tenants\n" + ONPREM.format(port=8207) + """functions:
  usage:
    handler: app.usage.get_usage
    events:
      - http: GET /usage
""",
          "app/__init__.py": "",
          "app/usage.py": FUTURE + """
def get_usage(event, ctx):
    tenant = event.http.headers["X-Tenant"]
    return {"tenant": tenant, "requests": 1532}
""",
          "requirements.txt": ""}),
      user="""ERROR   pskit.function: handler failed
KeyError: 'x-tenant'
a client without the header gets 500. should be a 400""",
      steps=[
          S("read_file", path="app/usage.py"),
          S("invoke_local", function="usage", path="/usage"),
          S("propose_plan", steps=["Read the header with `headers.get(\"X-Tenant\")` and raise `BadRequest` when it is missing",
                                   "GET /usage without the header locally; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/usage.py", content=FUTURE + """from py_serverless_kit import BadRequest


def get_usage(event, ctx):
    tenant = event.http.headers.get("X-Tenant")
    if not tenant:
        raise BadRequest("X-Tenant header is required")
    return {"tenant": tenant, "requests": 1532}
"""),
          S("invoke_local", function="usage", path="/usage"),
          S("validate"),
      ],
      final="""`headers["X-Tenant"]` raises `KeyError` when the header is missing (lookups ignore case, which is why the log shows `x-tenant`). Any uncaught exception is a 500. Now the code uses `headers.get("X-Tenant")` and raises `BadRequest` [docs/handlers.md#errors].

- GET /usage without the header: 400, `{"error": "X-Tenant header is required", "status": 400}`.
- validate (onprem, staging): valid.

To test the good path in the terminal: `pskit invoke -f usage --path /usage -H "X-Tenant: acme"`."""),

    # ------------------------------------------------------------------ 95  gcp workflow task, dict attribute access
    B(95, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#workflows-state-machines"],
      project=dict(files={
          "pskit.yml": """service: refunds
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  check-refund:
    handler: app.refund.check
  pay-refund:
    handler: app.refund.pay
workflows:
  refund:
    start_at: Check
    states:
      Check: {type: task, function: check-refund, next: Pay}
      Pay: {type: task, function: pay-refund, end: true}
""",
          "app/__init__.py": "",
          "app/refund.py": FUTURE + """
def check(event, ctx):
    req = event.data
    if req.amount > 500:
        raise ValueError("refund too large")
    return {**req, "approved": True}


def pay(event, ctx):
    return {"paid": event.data["amount"], "order": event.data["order_id"]}
""",
          "requirements.txt": ""}),
      user="the refund workflow fails at the first step: 'dict' object has no attribute 'amount'. the input is {\"order_id\": \"r-9\", \"amount\": 40}",
      steps=[
          S("read_file", path="app/refund.py"),
          S("invoke_local", function="check-refund", type="workflow", data={"order_id": "r-9", "amount": 40}),
          S("propose_plan", steps=["Read the amount with `req[\"amount\"]`: `event.data` is a plain dict",
                                   "Run check-refund with your input and validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/refund.py", content=FUTURE + """
def check(event, ctx):
    req = event.data
    if req["amount"] > 500:
        raise ValueError("refund too large")
    return {**req, "approved": True}


def pay(event, ctx):
    return {"paid": event.data["amount"], "order": event.data["order_id"]}
"""),
          S("invoke_local", function="check-refund", type="workflow", data={"order_id": "r-9", "amount": 40}),
          S("validate"),
      ],
      final="""A task gets the state input in `event.data` as a normal Python dict [docs/workflows.md#workflows-state-machines]. You read a dict with `req["amount"]`, not `req.amount`. I fixed that line in `check`; `pay` was already correct.

- check-refund with `{"order_id": "r-9", "amount": 40}`: `{"order_id": "r-9", "amount": 40, "approved": true}`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 96  onprem schedule, timedelta with a str
    B(96, provider="onprem", stage="prod", mode="ask", page="Logs", persona="informal_non_native",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": "service: log-cleaner\n" + ONPREM.format(port=8208) + """functions:
  purge-old:
    handler: app.purge.run
    environment:
      RETENTION_DAYS: "30"
    events:
      - schedule: "0 4 * * *"
""",
          "app/__init__.py": "",
          "app/purge.py": FUTURE + """import os
from datetime import datetime, timedelta, timezone


def run(event, ctx):
    days = os.getenv("RETENTION_DAYS", 30)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    ctx.logger.info("purging", extra={"before": cutoff.date().isoformat()})
    return {"cutoff": cutoff.date().isoformat()}
""",
          "requirements.txt": ""}),
      user="purge-old job fail every night: unsupported type for timedelta days component: str. the 30 is a number no?",
      steps=[
          S("read_file", path="app/purge.py"),
          S("invoke_local", function="purge-old", type="schedule"),
          S("propose_plan", steps=["Convert the variable: `int(os.getenv(\"RETENTION_DAYS\", \"30\"))`",
                                   "Run purge-old as a schedule event and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/purge.py", content=FUTURE + """import os
from datetime import datetime, timedelta, timezone


def run(event, ctx):
    days = int(os.getenv("RETENTION_DAYS", "30"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    ctx.logger.info("purging", extra={"before": cutoff.date().isoformat()})
    return {"cutoff": cutoff.date().isoformat()}
"""),
          S("invoke_local", function="purge-old", type="schedule"),
          S("validate"),
      ],
      final="""In the YAML it looks like a number, but environment variables are always **strings**. `os.getenv("RETENTION_DAYS")` gives `"30"`, and `timedelta(days="30")` fails. The default `30` only applied when the variable was missing, which is why it seemed fine. Now: `int(os.getenv("RETENTION_DAYS", "30"))`.

- schedule run: logs "purging" and returns the cutoff date 30 days back.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 97  aws http, return NotFound instead of raise
    B(97, provider="aws", stage="prod", mode="auto", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: aws
  region: ap-southeast-2
functions:
  get-order:
    handler: app.orders.get_order
    events:
      - http: GET /orders/{id}
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """from py_serverless_kit import NotFound

ORDERS = {"o-1": {"id": "o-1", "total": 18.5}}


def get_order(event, ctx):
    order = ORDERS.get(event.http.path_params["id"])
    if order is None:
        return NotFound("no such order")
    return order
""",
          "requirements.txt": ""}),
      user="GET /orders/nope -> 500, expected 404. NotFound is imported",
      steps=[
          S("read_file", path="app/orders.py"),
          S("invoke_local", function="get-order", path="/orders/nope"),
          S("propose_plan", steps=["`raise NotFound(...)` instead of `return NotFound(...)`"]),
          S("write_file", path="app/orders.py", content=FUTURE + """from py_serverless_kit import NotFound

ORDERS = {"o-1": {"id": "o-1", "total": 18.5}}


def get_order(event, ctx):
    order = ORDERS.get(event.http.path_params["id"])
    if order is None:
        raise NotFound("no such order")
    return order
"""),
          S("invoke_local", function="get-order", path="/orders/nope"),
          S("validate"),
      ],
      final="""It was `return NotFound(...)`, not `raise`. pskit tried to serialise the exception object as the response body and failed, so you got a 500. HTTP errors must be raised [docs/handlers.md#errors].

- GET /orders/nope: 404, `{"error": "no such order", "status": 404}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 98  onprem queue, resource not bound to the function
    B(98, provider="onprem", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#runtime-api", "docs/resources.md#fields"],
      project=dict(files={
          "pskit.yml": "service: mailer\n" + ONPREM.format(port=8209) + """resources:
  smtp-relay:
    type: custom
    external: true
    connection: {host: mail.example.com, port: 587}
    functions: [send-test]
functions:
  send-test:
    handler: app.mailer.send_test
    events:
      - http: POST /test-mail
  send-batch:
    handler: app.mailer.send_batch
    events:
      - queue: outgoing-mail
""",
          "app/__init__.py": "",
          "app/mailer.py": FUTURE + """from py_serverless_kit import resource


def relay():
    r = resource("smtp-relay")
    return {"host": r["host"], "port": int(r["port"])}


def send_test(event, ctx):
    return {"relay": relay()}


def send_batch(event, ctx):
    target = relay()
    ctx.logger.info("sending", extra={"count": len(event.records), "host": target["host"]})
    return {"sent": len(event.records)}
""",
          "requirements.txt": ""}),
      user="send-test reads the smtp-relay resource fine, but send-batch, which uses the same relay() helper, fails with KeyError: resource 'smtp-relay' is not bound to this function. Both functions must use the same relay. Please fix it without copying the host into the code, and test send-batch with two messages.",
      steps=[
          S("get_project"),
          S("invoke_local", function="send-batch", type="queue", data=[{"to": "a@example.com"}, {"to": "b@example.com"}]),
          S("search_docs", query="resource functions list binding",
            docs=[D("docs/resources.md", "fields", start="| `functions` |", end="| `functions` |")]),
          S("propose_plan", steps=["Add send-batch to `resources.smtp-relay.functions` ([send-test, send-batch])",
                                   "Invoke send-batch with two messages and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.smtp-relay.functions", value=["send-test", "send-batch"]),
          S("invoke_local", function="send-batch", type="queue", data=[{"to": "a@example.com"}, {"to": "b@example.com"}]),
      ],
      final="""The code was fine; the binding wasn't. `resources.smtp-relay.functions` listed only `send-test`, so pskit gave the relay's `PSKIT_RESOURCE_SMTP_RELAY_*` variables only to that function [docs/resources.md#fields]. I added `send-batch` to the list:

```yaml
resources:
  smtp-relay:
    functions: [send-test, send-batch]
```

- validate (onprem): valid.
- send-batch with two messages: logs "sending" and returns `{"sent": 2}`.

Without a `functions:` list at all, every function you wrote gets the binding."""),

    # ------------------------------------------------------------------ 99  azure http, Response.binary with a str
    B(99, provider="azure", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: exports
provider:
  name: azure
  region: eastus2
functions:
  export-csv:
    handler: app.export.csv_report
    events:
      - http: GET /export.csv
""",
          "app/__init__.py": "",
          "app/export.py": FUTURE + """from py_serverless_kit import Response

ROWS = [("sku", "qty"), ("A1", 4), ("B2", 0)]


def csv_report(event, ctx):
    text = "\\n".join(f"{a},{b}" for a, b in ROWS) + "\\n"
    return Response.binary(text, "text/csv", headers={"content-disposition": "attachment; filename=stock.csv"})
""",
          "requirements.txt": ""}),
      user="GET /export.csv should download a CSV file named stock.csv with a header row. It returns 500, and the log has TypeError: string argument without an encoding. Please fix it so the browser still downloads the file.",
      steps=[
          S("read_file", path="app/export.py"),
          S("invoke_local", function="export-csv", path="/export.csv"),
          S("propose_plan", steps=["Encode the CSV text before `Response.binary` (`text.encode(\"utf-8\")`), keep content type and content-disposition",
                                   "GET /export.csv locally and validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/export.py", content=FUTURE + """from py_serverless_kit import Response

ROWS = [("sku", "qty"), ("A1", 4), ("B2", 0)]


def csv_report(event, ctx):
    text = "\\n".join(f"{a},{b}" for a, b in ROWS) + "\\n"
    return Response.binary(text.encode("utf-8"), "text/csv",
                           headers={"content-disposition": "attachment; filename=stock.csv"})
"""),
          S("invoke_local", function="export-csv", path="/export.csv"),
          S("validate"),
      ],
      final="""`Response.binary()` expects **bytes**, and the CSV was a `str`. Python can't turn a str into bytes without an encoding, hence the TypeError. Now the handler passes `text.encode("utf-8")`. The content type `text/csv` and the `content-disposition: attachment; filename=stock.csv` header are unchanged, so the browser still downloads the file.

- GET /export.csv: 200, content-type `text/csv`, body `sku,qty / A1,4 / B2,0`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 100 onprem http, branching on event.provider
    B(100, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/local-development.md#environment"],
      project=dict(files={
          "pskit.yml": "service: kiosk\n" + ONPREM.format(port=8210) + """functions:
  menu:
    handler: app.menu.get_menu
    events:
      - http: GET /menu
""",
          "app/__init__.py": "",
          "app/menu.py": FUTURE + """
def get_menu(event, ctx):
    if event.provider == "onprem":
        source = "kitchen-db"
    else:
        raise RuntimeError(f"unsupported provider {event.provider}")
    return {"source": source, "items": ["soup", "salad"]}
""",
          "requirements.txt": ""}),
      user="on the server /menu work. on Test page run locally give 500 'unsupported provider local'. why local? i deploy onprem",
      steps=[
          S("read_file", path="app/menu.py"),
          S("invoke_local", function="menu", path="/menu"),
          S("search_docs", query="local run provider environment",
            docs=[D("docs/local-development.md", "environment", end="finally load `.env`")]),
          S("propose_plan", steps=["Remove the provider check that rejects `local`; the handler code is the same everywhere",
                                   "GET /menu locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/menu.py", content=FUTURE + """
def get_menu(event, ctx):
    source = "kitchen-db"
    return {"source": source, "items": ["soup", "salad"]}
"""),
          S("invoke_local", function="menu", path="/menu"),
          S("validate"),
      ],
      final="""**Run locally** does not use your server. It runs the function on your machine, and there the provider is `local` (`PSKIT_PROVIDER=local`) [docs/local-development.md#environment]. Your code only accepted `"onprem"`, so local runs raised the error.

The check did nothing useful (the same code runs on the server), so I removed it.

- GET /menu locally: 200, `{"source": "kitchen-db", "items": ["soup", "salad"]}`.
- validate (onprem): valid.

If something really must differ, put it in `environment:` in pskit.yml, not in a provider check."""),
]
