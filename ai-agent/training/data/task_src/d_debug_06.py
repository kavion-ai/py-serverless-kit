"""Category D (fix a handler bug), batch 6. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 101 onprem http, import without the package
    B(101, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": "service: badges\n" + ONPREM.format(port=8211) + """functions:
  badge:
    handler: app.badge.make_badge
    events:
      - http: GET /badge/{name}
""",
          "app/__init__.py": "",
          "app/helpers.py": FUTURE + """
def initials(name):
    return "".join(part[0].upper() for part in name.split("-") if part)
""",
          "app/badge.py": FUTURE + """from helpers import initials


def make_badge(event, ctx):
    name = event.http.path_params["name"]
    return {"name": name, "initials": initials(name)}
""",
          "requirements.txt": ""}),
      user="I moved a function into helpers.py next to badge.py and now the badge page says No module named 'helpers'. The file is right there in the same folder!",
      steps=[
          S("read_file", path="app/badge.py"),
          S("invoke_local", function="badge", path="/badge/ada-lovelace"),
          S("propose_plan", steps=["Import with the package name: `from app.helpers import initials`",
                                   "GET /badge/ada-lovelace locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/badge.py", content=FUTURE + """from app.helpers import initials


def make_badge(event, ctx):
    name = event.http.path_params["name"]
    return {"name": name, "initials": initials(name)}
"""),
          S("invoke_local", function="badge", path="/badge/ada-lovelace"),
          S("validate"),
      ],
      final="""pskit imports your code from the project root (the folder with pskit.yml), the same way `handler: app.badge.make_badge` is written [docs/handlers.md#handler-signatures]. From there the file is `app.helpers`, not `helpers`. Being in the same folder is not enough. I changed the import to `from app.helpers import initials`.

- GET /badge/ada-lovelace: 200, `{"name": "ada-lovelace", "initials": "AL"}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 102 aws queue, BatchResult.of(all records)
    B(102, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: invoicing
provider:
  name: aws
  region: eu-west-2
functions:
  render-invoice:
    handler: app.render.handle
    events:
      - queue:
          name: invoices
          batch_size: 10
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    bad = []
    for record in event.records:
        inv = record.json()
        if "customer" not in inv:
            bad.append(record)
            continue
        ctx.logger.info("rendered", extra={"invoice": inv["id"]})
    return BatchResult.of(event.records)
""",
          "requirements.txt": ""}),
      user="Every invoice message is processed again and again (we see 'rendered' many times for the same id), even when all of them succeed. Only invoices without a customer should be retried. Please fix it and test with one good and one bad invoice.",
      steps=[
          S("read_file", path="app/render.py"),
          S("invoke_local", function="render-invoice", type="queue", data=[{"id": "INV-1", "customer": "c-9"}, {"id": "INV-2"}]),
          S("search_docs", query="BatchResult of failed records",
            docs=[D("docs/handlers.md", "batchresult", end="| local |")]),
          S("propose_plan", steps=["Return `BatchResult.of(bad)` (the failed records) instead of `BatchResult.of(event.records)`",
                                   "Invoke with INV-1 (good) and INV-2 (no customer); validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/render.py", content=FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    bad = []
    for record in event.records:
        inv = record.json()
        if "customer" not in inv:
            bad.append(record)
            continue
        ctx.logger.info("rendered", extra={"invoice": inv["id"]})
    return BatchResult.of(bad)
"""),
          S("invoke_local", function="render-invoice", type="queue", data=[{"id": "INV-1", "customer": "c-9"}, {"id": "INV-2"}]),
          S("validate"),
      ],
      final="""`BatchResult.of(...)` takes the records that **failed** [docs/handlers.md#batchresult]. The handler passed `event.records`, so every message was reported as failed and SQS sent them all again. Now it returns `BatchResult.of(bad)`.

- Before: `batchItemFailures` listed `local-0` and `local-1`.
- After: only `local-1` (INV-2, no customer); INV-1 logs "rendered" once.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 103 gcp http, int() of a bad path param
    B(103, provider="gcp", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: library\n" + GCP.format(region="us-central1") + """functions:
  book:
    handler: app.books.get_book
    events:
      - http: GET /books/{id}
""",
          "app/__init__.py": "",
          "app/books.py": FUTURE + """from py_serverless_kit import NotFound

BOOKS = {1: "Dune", 2: "Emma"}


def get_book(event, ctx):
    book_id = int(event.http.path_params["id"])
    if book_id not in BOOKS:
        raise NotFound("no such book")
    return {"id": book_id, "title": BOOKS[book_id]}
""",
          "requirements.txt": ""}),
      user="""ValueError: invalid literal for int() with base 10: 'dune'
GET /books/dune -> 500. should be 404 like /books/99""",
      steps=[
          S("read_file", path="app/books.py"),
          S("invoke_local", function="book", path="/books/dune"),
          S("propose_plan", steps=["Raise `NotFound` when the id is not a number (only digits), before `int()`",
                                   "GET /books/dune locally and validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/books.py", content=FUTURE + """from py_serverless_kit import NotFound

BOOKS = {1: "Dune", 2: "Emma"}


def get_book(event, ctx):
    raw = event.http.path_params["id"]
    if not raw.isdigit() or int(raw) not in BOOKS:
        raise NotFound("no such book")
    book_id = int(raw)
    return {"id": book_id, "title": BOOKS[book_id]}
"""),
          S("invoke_local", function="book", path="/books/dune"),
          S("validate"),
      ],
      final="""`int("dune")` raises `ValueError`, and any exception that isn't an `HttpError` becomes a 500 [docs/handlers.md#errors]. Now an id that isn't all digits gets the same `NotFound` as an unknown number.

- GET /books/dune: 404, `{"error": "no such book", "status": 404}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 104 onprem schedule, one-arg handler named ctx
    B(104, provider="onprem", stage="staging", mode="ask", page="Logs", persona="informal_non_native",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": "service: backups\n" + ONPREM.format(port=8212) + """functions:
  nightly-backup:
    handler: app.backup.run
    events:
      - schedule:
          cron: "15 2 * * *"
          input: {target: /srv/backups}
""",
          "app/__init__.py": "",
          "app/backup.py": FUTURE + """
def run(ctx):
    ctx.logger.info("backup start")
    return {"target": "/srv/backups", "ok": True}
""",
          "requirements.txt": ""}),
      user="backup job: 'Event' object has no attribute 'logger'. but i use ctx.logger not event??",
      steps=[
          S("read_file", path="app/backup.py"),
          S("invoke_local", function="nightly-backup", type="schedule"),
          S("search_docs", query="handler signature one argument",
            docs=[D("docs/handlers.md", "handler-signatures", end="async def handler")]),
          S("propose_plan", steps=["Take both arguments: `def run(event, ctx)`, and read the target from `event.data`",
                                   "Run nightly-backup as a schedule event and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/backup.py", content=FUTURE + """
def run(event, ctx):
    target = event.data["target"]
    ctx.logger.info("backup start", extra={"target": target})
    return {"target": target, "ok": True}
"""),
          S("invoke_local", function="nightly-backup", type="schedule"),
          S("validate"),
      ],
      final="""With **one** parameter, pskit passes the **event** to it, whatever you call it [docs/handlers.md#handler-signatures]. So your `ctx` was really the event, and the event has no `logger`. Now the handler is `def run(event, ctx)`. It also reads the folder from the schedule input (`event.data["target"]`) instead of hard-coding it.

- schedule run: logs "backup start" and returns `{"target": "/srv/backups", "ok": true}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 105 azure http, cookies() called
    B(105, provider="azure", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: prefs
provider:
  name: azure
  region: uksouth
functions:
  theme:
    handler: app.prefs.theme
    events:
      - http: GET /theme
""",
          "app/__init__.py": "",
          "app/prefs.py": FUTURE + """
def theme(event, ctx):
    cookies = event.http.cookies()
    return {"theme": cookies.get("theme", "light")}
""",
          "requirements.txt": ""}),
      user="/theme give 500 TypeError 'dict' object is not callable. i only read cookie",
      steps=[
          S("read_file", path="app/prefs.py"),
          S("invoke_local", function="theme", path="/theme"),
          S("propose_plan", steps=["Use `event.http.cookies` without `()`: it is a property that is already a dict",
                                   "GET /theme locally and validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/prefs.py", content=FUTURE + """
def theme(event, ctx):
    cookies = event.http.cookies
    return {"theme": cookies.get("theme", "light")}
"""),
          S("invoke_local", function="theme", path="/theme"),
          S("validate"),
      ],
      final="""`event.http.cookies` is already a `dict` (parsed from the `Cookie` header), not a method [docs/handlers.md#httprequest]. The `()` tried to call the dict. Removed.

- GET /theme without a cookie: 200, `{"theme": "light"}`.
- validate (azure): valid.

To test with a cookie in the terminal: `pskit invoke -f theme --path /theme -H "Cookie: theme=dark"`."""),

    # ------------------------------------------------------------------ 106 onprem queue, missing import time
    B(106, provider="onprem", stage="prod", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": "service: sensors\n" + ONPREM.format(port=8213) + """functions:
  ingest-reading:
    handler: app.ingest.handle
    events:
      - queue:
          name: readings
          batch_size: 50
""",
          "app/__init__.py": "",
          "app/ingest.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    stamp = int(time.time())
    for record in event.records:
        reading = record.json(default=None)
        if not isinstance(reading, dict) or "sensor" not in reading:
            result.fail(record)
            continue
        ctx.logger.info("reading", extra={"sensor": reading["sensor"], "at": stamp})
    return result
""",
          "requirements.txt": ""}),
      user="ingest-reading: NameError name 'time' is not defined",
      steps=[
          S("read_file", path="app/ingest.py"),
          S("invoke_local", function="ingest-reading", type="queue", data=[{"sensor": "t-1", "c": 21.5}, "garbage"]),
          S("propose_plan", steps=["Add `import time`"]),
          S("write_file", path="app/ingest.py", content=FUTURE + """import time

from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    stamp = int(time.time())
    for record in event.records:
        reading = record.json(default=None)
        if not isinstance(reading, dict) or "sensor" not in reading:
            result.fail(record)
            continue
        ctx.logger.info("reading", extra={"sensor": reading["sensor"], "at": stamp})
    return result
"""),
          S("invoke_local", function="ingest-reading", type="queue", data=[{"sensor": "t-1", "c": 21.5}, "garbage"]),
          S("validate"),
      ],
      final="""Missing `import time`. Added.

- invoke (one reading + one bad message): logs "reading" for `t-1`, `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`. On-prem retries only the bad message [docs/handlers.md#batchresult].
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 107 aws http, status as a string in the tuple
    B(107, provider="aws", stage="dev", mode="auto", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: signup
provider:
  name: aws
  region: us-east-1
functions:
  register:
    handler: app.users.register
    events:
      - http: POST /users
""",
          "app/__init__.py": "",
          "app/users.py": FUTURE + """
def register(event, ctx):
    user = event.http.json()
    return {"email": user["email"]}, "201"
""",
          "requirements.txt": ""}),
      user="POST /users returns 200 with body [{...}, \"201\"]. want 201 + object",
      steps=[
          S("read_file", path="app/users.py"),
          S("invoke_local", function="register", method="POST", path="/users", data={"email": "kim@example.com"}),
          S("propose_plan", steps=["Return the status as an int: `(body, 201)`"]),
          S("write_file", path="app/users.py", content=FUTURE + """
def register(event, ctx):
    user = event.http.json()
    return {"email": user["email"]}, 201
"""),
          S("invoke_local", function="register", method="POST", path="/users", data={"email": "kim@example.com"}),
          S("validate"),
      ],
      final="""The status was the string `"201"`. A tuple is only read as `(body, status)` when the status is an `int`; otherwise it is just a list and goes out as JSON with 200 [docs/handlers.md#returning-a-response]. Now: `return {...}, 201`.

- POST /users: 201, `{"email": "kim@example.com"}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 108 gcp storage, event.raw from the old GCS code
    B(108, provider="gcp", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#record", "docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": "service: media\n" + GCP.format(region="europe-west1") + """functions:
  on-upload:
    handler: app.media.on_upload
    events:
      - storage:
          bucket: media-uploads
          suffix: .mp4
""",
          "app/__init__.py": "",
          "app/media.py": FUTURE + """
def on_upload(event, ctx):
    name = event.raw["name"]
    size = int(event.raw["size"])
    ctx.logger.info("video uploaded", extra={"file": name, "mb": round(size / 1_000_000, 1)})
    return {"file": name}
""",
          "requirements.txt": ""}),
      user="This handler came from our old Cloud Function, where the GCS event had name and size. Under pskit, uploading a test video fails with TypeError: 'NoneType' object is not subscriptable. The function must log the file name and the size in MB for every uploaded .mp4, and it should work the same if we move clouds later.",
      steps=[
          S("read_file", path="app/media.py"),
          S("invoke_local", function="on-upload", type="storage", data=[{"key": "talks/keynote.mp4", "size": 734003200}]),
          S("search_docs", query="storage record key size",
            docs=[D("docs/handlers.md", "record")]),
          S("propose_plan", steps=["Loop over `event.records` and use `record.key` and `record.size` instead of the native `event.raw`",
                                   "Invoke on-upload with a test video and validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/media.py", content=FUTURE + """
def on_upload(event, ctx):
    files = []
    for record in event.records:
        size = record.size or 0
        ctx.logger.info("video uploaded", extra={"file": record.key, "mb": round(size / 1_000_000, 1)})
        files.append(record.key)
    return {"files": files}
"""),
          S("invoke_local", function="on-upload", type="storage", data=[{"key": "talks/keynote.mp4", "size": 734003200}]),
          S("validate"),
      ],
      final="""`event.raw` is the untouched native payload. It is not portable, and in a local run it is empty (`None`) [docs/handlers.md#event]. pskit already gives you each object as a `Record`: `record.key` is the file name and `record.size` the size in bytes [docs/handlers.md#record]. The handler now loops over `event.records`, so it also handles several files in one event and works the same on every cloud.

- Test upload `talks/keynote.mp4` (734003200 bytes): logs "video uploaded" with 734.0 MB, returns `{"files": ["talks/keynote.mp4"]}`.
- validate (gcp, prod): valid.

The return value changed from `file` to a `files` list; nothing reads it for storage events."""),

    # ------------------------------------------------------------------ 109 onprem http, async helper from a sync handler
    B(109, provider="onprem", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": "service: fx\n" + ONPREM.format(port=8214) + """functions:
  convert:
    handler: app.fx.convert
    events:
      - http: GET /convert
""",
          "app/__init__.py": "",
          "app/fx.py": FUTURE + """import asyncio


async def fetch_rates():
    await asyncio.sleep(0)
    return {"EUR": 0.92, "GBP": 0.79}


def convert(event, ctx):
    rates = fetch_rates()
    amount = float(event.http.query.get("amount", "1"))
    cur = event.http.query.get("to", "EUR")
    return {"to": cur, "amount": round(amount * rates[cur], 2)}
""",
          "requirements.txt": ""}),
      user="""TypeError: 'coroutine' object is not subscriptable
RuntimeWarning: coroutine 'fetch_rates' was never awaited
/convert?amount=10&to=GBP""",
      steps=[
          S("read_file", path="app/fx.py"),
          S("invoke_local", function="convert", path="/convert?amount=10&to=GBP"),
          S("propose_plan", steps=["Make `convert` an `async def` and `await fetch_rates()`",
                                   "GET /convert?amount=10&to=GBP locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/fx.py", content=FUTURE + """import asyncio


async def fetch_rates():
    await asyncio.sleep(0)
    return {"EUR": 0.92, "GBP": 0.79}


async def convert(event, ctx):
    rates = await fetch_rates()
    amount = float(event.http.query.get("amount", "1"))
    cur = event.http.query.get("to", "EUR")
    return {"to": cur, "amount": round(amount * rates[cur], 2)}
"""),
          S("invoke_local", function="convert", path="/convert?amount=10&to=GBP"),
          S("validate"),
      ],
      final="""Calling an `async def` without `await` only creates a coroutine; `fetch_rates()` never ran. I made `convert` async and added `await`. pskit awaits async handlers for you [docs/handlers.md#handler-signatures].

- GET /convert?amount=10&to=GBP: 200, `{"to": "GBP", "amount": 7.9}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 110 azure schedule, date minus int
    B(110, provider="azure", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: sales-report
provider:
  name: azure
  region: westus2
functions:
  daily-sales:
    handler: app.sales.daily
    events:
      - schedule: "0 6 * * *"
""",
          "app/__init__.py": "",
          "app/sales.py": FUTURE + """
def daily(event, ctx):
    yesterday = event.time.date() - 1
    ctx.logger.info("sales report", extra={"day": yesterday.isoformat()})
    return {"day": yesterday.isoformat()}
""",
          "requirements.txt": ""}),
      user="my daily sales report should be for yesterday, but it crashes with unsupported operand type(s) for -: 'datetime.date' and 'int'. how do I get yesterday?",
      steps=[
          S("read_file", path="app/sales.py"),
          S("invoke_local", function="daily-sales", type="schedule"),
          S("propose_plan", steps=["Subtract `timedelta(days=1)` from `event.time.date()` (import timedelta)",
                                   "Run daily-sales as a schedule event and validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sales.py", content=FUTURE + """from datetime import timedelta


def daily(event, ctx):
    yesterday = event.time.date() - timedelta(days=1)
    ctx.logger.info("sales report", extra={"day": yesterday.isoformat()})
    return {"day": yesterday.isoformat()}
"""),
          S("invoke_local", function="daily-sales", type="schedule"),
          S("validate"),
      ],
      final="""In Python you can't subtract a plain number from a date; you subtract a `timedelta`. Now it is `event.time.date() - timedelta(days=1)`. `event.time` is the run time in UTC [docs/handlers.md#event], so "yesterday" is the UTC day before.

- schedule run: logs "sales report" and returns yesterday's date.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 111 onprem storage, env str compared with float
    B(111, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": "service: uploads-guard\n" + ONPREM.format(port=8215) + """functions:
  size-check:
    handler: app.guard.check
    environment:
      MAX_MB: "20"
    events:
      - storage: user-uploads
""",
          "app/__init__.py": "",
          "app/guard.py": FUTURE + """
def check(event, ctx):
    too_big = []
    for record in event.records:
        size_mb = (record.size or 0) / 1_000_000
        if size_mb > ctx.env.get("MAX_MB", 50):
            too_big.append(record.key)
    return {"too_big": too_big}
""",
          "requirements.txt": ""}),
      user="size-check error '>' not supported between 'float' and 'str'. MAX_MB is 20 in the yml",
      steps=[
          S("read_file", path="app/guard.py"),
          S("invoke_local", function="size-check", type="storage", data=[{"key": "big.iso", "size": 52000000}, {"key": "cv.pdf", "size": 90000}]),
          S("propose_plan", steps=["Convert the limit once: `limit = float(ctx.env.get(\"MAX_MB\", \"50\"))`",
                                   "Invoke with a 52 MB and a small file; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/guard.py", content=FUTURE + """
def check(event, ctx):
    limit = float(ctx.env.get("MAX_MB", "50"))
    too_big = []
    for record in event.records:
        size_mb = (record.size or 0) / 1_000_000
        if size_mb > limit:
            too_big.append(record.key)
    return {"too_big": too_big}
"""),
          S("invoke_local", function="size-check", type="storage", data=[{"key": "big.iso", "size": 52000000}, {"key": "cv.pdf", "size": 90000}]),
          S("validate"),
      ],
      final="""`ctx.env` is `os.environ`, and every value there is a **string** [docs/handlers.md#environment-variables]. So `MAX_MB` is `"20"`, and a float can't be compared with a string. Now the limit is converted once with `float(...)`.

- invoke (52 MB `big.iso` + small `cv.pdf`): `{"too_big": ["big.iso"]}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 112 gcp http, hashing a str
    B(112, provider="gcp", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: config-api\n" + GCP.format(region="asia-northeast1") + """functions:
  settings:
    handler: app.settings.get_settings
    events:
      - http: GET /settings
""",
          "app/__init__.py": "",
          "app/settings.py": FUTURE + """import hashlib
import json

from py_serverless_kit import Response

SETTINGS = {"theme": "dark", "beta": False, "max_items": 50}


def get_settings(event, ctx):
    body = json.dumps(SETTINGS, sort_keys=True)
    etag = hashlib.sha256(body).hexdigest()[:16]
    if event.http.headers.get("if-none-match") == etag:
        return Response(304, "")
    return Response.json(SETTINGS, headers={"etag": etag})
""",
          "requirements.txt": ""}),
      user="GET /settings should send an ETag header (a short hash of the settings JSON) so clients can cache, and answer 304 when If-None-Match matches. Since I added the ETag it returns 500 with TypeError: Strings must be encoded before hashing. Please fix and show the response with the header.",
      steps=[
          S("read_file", path="app/settings.py"),
          S("invoke_local", function="settings", path="/settings"),
          S("propose_plan", steps=["Hash bytes: `hashlib.sha256(body.encode(\"utf-8\"))`; keep the 304 check",
                                   "GET /settings locally and validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/settings.py", content=FUTURE + """import hashlib
import json

from py_serverless_kit import Response

SETTINGS = {"theme": "dark", "beta": False, "max_items": 50}


def get_settings(event, ctx):
    body = json.dumps(SETTINGS, sort_keys=True)
    etag = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    if event.http.headers.get("if-none-match") == etag:
        return Response(304, "")
    return Response.json(SETTINGS, headers={"etag": etag})
"""),
          S("invoke_local", function="settings", path="/settings"),
          S("validate"),
      ],
      final="""`hashlib` works on **bytes**, and `json.dumps()` gives a `str`. Now the body is encoded first: `hashlib.sha256(body.encode("utf-8"))`. The 304 branch is unchanged.

- GET /settings: 200 with an `etag` header (16 hex characters) and the settings JSON.
- validate (gcp): valid.

To check the 304 in the terminal, send the tag back: `pskit invoke -f settings --path /settings -H "If-None-Match: <etag>"`."""),

    # ------------------------------------------------------------------ 113 onprem workflow, nested result vs choice path
    B(113, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#choice-rules", "docs/workflows.md#data-flow"],
      project=dict(files={
          "pskit.yml": "service: kyc\n" + ONPREM.format(port=8216) + """functions:
  screen:
    handler: app.kyc.screen
  approve:
    handler: app.kyc.approve
  review:
    handler: app.kyc.review
workflows:
  onboarding:
    start_at: Screen
    states:
      Screen: {type: task, function: screen, next: Decide}
      Decide:
        type: choice
        choices:
          - {variable: "$.status", equals: clear, next: Approve}
        default: Review
      Approve: {type: task, function: approve, end: true}
      Review: {type: task, function: review, end: true}
""",
          "app/__init__.py": "",
          "app/kyc.py": FUTURE + """BLOCKED = {"XX"}


def screen(event, ctx):
    person = event.data
    status = "hit" if person.get("country") in BLOCKED else "clear"
    return {"result": {"status": status}, "person": person}


def approve(event, ctx):
    return {"approved": True}


def review(event, ctx):
    return {"approved": False, "queued_for_review": True}
""",
          "requirements.txt": ""}),
      user="In the onboarding workflow every customer ends up in Review, even clean ones. The Decide state checks $.status == clear. Screen should return the status so that clean customers go to Approve; the workflow file is correct as it is. Please fix screen and show me its output for a customer from DE.",
      steps=[
          S("read_file", path="app/kyc.py"),
          S("invoke_local", function="screen", type="workflow", data={"name": "Lena", "country": "DE"}),
          S("search_docs", query="choice rule variable path missing",
            docs=[D("docs/workflows.md", "choice-rules", start="A rule whose variable is missing")]),
          S("propose_plan", steps=["Return `status` at the top level of screen's result: `{\"status\": ..., \"person\": ...}`",
                                   "Invoke screen for a DE customer; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/kyc.py", content=FUTURE + """BLOCKED = {"XX"}


def screen(event, ctx):
    person = event.data
    status = "hit" if person.get("country") in BLOCKED else "clear"
    return {"status": status, "person": person}


def approve(event, ctx):
    return {"approved": True}


def review(event, ctx):
    return {"approved": False, "queued_for_review": True}
"""),
          S("invoke_local", function="screen", type="workflow", data={"name": "Lena", "country": "DE"}),
          S("validate"),
      ],
      final="""`screen` put the status under `result`, so it was at `$.result.status`. `$.status` didn't exist, and a choice rule on a missing variable is simply false [docs/workflows.md#choice-rules], so every run took the `default: Review`. Now `screen` returns `status` at the top level and pskit.yml stays unchanged.

- screen for Lena (DE): `{"status": "clear", "person": {"name": "Lena", "country": "DE"}}`, so Decide goes to Approve.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 114 aws http, headers passed positionally
    B(114, provider="aws", stage="staging", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: reports-api
provider:
  name: aws
  region: ca-central-1
functions:
  report:
    handler: app.report.get_report
    events:
      - http: GET /report
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """from py_serverless_kit import Unauthorized


def get_report(event, ctx):
    auth = event.http.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise Unauthorized("token required", {"WWW-Authenticate": "Bearer"})
    return {"rows": 42}
""",
          "requirements.txt": ""}),
      user="In my Lambda I returned {'statusCode': 401, 'headers': {'WWW-Authenticate': 'Bearer'}}. With pskit I raise Unauthorized with the headers, but a request without a token gets 500, not 401. What's wrong?",
      steps=[
          S("read_file", path="app/report.py"),
          S("invoke_local", function="report", path="/report"),
          S("search_docs", query="HttpError headers argument",
            docs=[D("docs/handlers.md", "errors", end="# -> 422")]),
          S("propose_plan", steps=["Pass the headers by name: `Unauthorized(\"token required\", headers={...})`",
                                   "GET /report without a token locally; validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/report.py", content=FUTURE + """from py_serverless_kit import Unauthorized


def get_report(event, ctx):
    auth = event.http.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise Unauthorized("token required", headers={"WWW-Authenticate": "Bearer"})
    return {"rows": 42}
"""),
          S("invoke_local", function="report", path="/report"),
          S("validate"),
      ],
      final="""Only the message is positional; `status`, `details` and `headers` must be passed **by name** (`HttpError(message, status=..., details=..., headers=...)`) [docs/handlers.md#errors]. The extra positional argument made the constructor raise `TypeError`, and that became the 500. Now it is `Unauthorized("token required", headers={"WWW-Authenticate": "Bearer"})`.

- GET /report without a token: 401, header `www-authenticate: Bearer`, body `{"error": "token required", "status": 401}`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 115 onprem http, extra= with a string
    B(115, provider="onprem", stage="dev", mode="ask", page="Logs", persona="beginner",
      sources=["docs/handlers.md#logging"],
      project=dict(files={
          "pskit.yml": "service: members\n" + ONPREM.format(port=8217) + """functions:
  login:
    handler: app.auth.login
    events:
      - http: POST /login
""",
          "app/__init__.py": "",
          "app/auth.py": FUTURE + """
def login(event, ctx):
    data = event.http.json()
    user = data.get("user", "")
    ctx.logger.info("login", extra=user)
    return {"welcome": user}
""",
          "requirements.txt": ""}),
      user="I added one log line to login and now it always fails with 'str' object is not a mapping. How do I log the user name?",
      steps=[
          S("read_file", path="app/auth.py"),
          S("invoke_local", function="login", method="POST", path="/login", data={"user": "sam"}),
          S("search_docs", query="logger extra fields",
            docs=[D("docs/handlers.md", "logging", end="ctx.logger.info")]),
          S("propose_plan", steps=["Pass a dict to `extra`: `extra={\"user\": user}`",
                                   "POST /login locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/auth.py", content=FUTURE + """
def login(event, ctx):
    data = event.http.json()
    user = data.get("user", "")
    ctx.logger.info("login", extra={"user": user})
    return {"welcome": user}
"""),
          S("invoke_local", function="login", method="POST", path="/login", data={"user": "sam"}),
          S("validate"),
      ],
      final="""`extra` must be a **dict** of fields, like `extra={"order_id": 42}` [docs/handlers.md#logging]. You passed the user name string itself, and the logger can't merge a string into its fields. Now it is `extra={"user": user}`, so `user` appears as its own field in every log line.

- POST /login `{"user": "sam"}`: logs "login", returns 200 `{"welcome": "sam"}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 116 azure queue, record.json without ()
    B(116, provider="azure", stage="staging", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: shipping
provider:
  name: azure
  region: francecentral
functions:
  label:
    handler: app.labels.handle
    events:
      - queue: shipping-labels
""",
          "app/__init__.py": "",
          "app/labels.py": FUTURE + """
def handle(event, ctx):
    made = []
    for record in event.records:
        order = record.json
        made.append(f"label-{order['id']}")
    return {"labels": made}
""",
          "requirements.txt": ""}),
      user="""TypeError: 'method' object is not subscriptable
  File "app/labels.py", line 7, in handle""",
      steps=[
          S("read_file", path="app/labels.py"),
          S("invoke_local", function="label", type="queue", data=[{"id": 501}, {"id": 502}]),
          S("propose_plan", steps=["Call `record.json()`; without `()` it is the method, not the parsed body",
                                   "Invoke label with two orders; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/labels.py", content=FUTURE + """
def handle(event, ctx):
    made = []
    for record in event.records:
        order = record.json()
        made.append(f"label-{order['id']}")
    return {"labels": made}
"""),
          S("invoke_local", function="label", type="queue", data=[{"id": 501}, {"id": 502}]),
          S("validate"),
      ],
      final="""Line 7: `record.json` is a method; `record.json()` returns the parsed body [docs/handlers.md#record]. Added the `()`.

- invoke (ids 501, 502): `{"labels": ["label-501", "label-502"]}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 117 onprem http, returning headers.update()
    B(117, provider="onprem", stage="staging", mode="auto", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: portal\n" + ONPREM.format(port=8218) + """functions:
  session:
    handler: app.session.start
    events:
      - http: POST /session
""",
          "app/__init__.py": "",
          "app/session.py": FUTURE + """from py_serverless_kit import Response


def start(event, ctx):
    resp = Response.json({"ok": True}).set_cookie("sid", "abc123", max_age=3600)
    return resp.headers.update({"cache-control": "no-store"})
""",
          "requirements.txt": ""}),
      user="session endpoint return 204 empty, no cookie no body. it should be 200 with ok true",
      steps=[
          S("read_file", path="app/session.py"),
          S("invoke_local", function="session", method="POST", path="/session"),
          S("propose_plan", steps=["Update the headers first, then `return resp` (`dict.update()` returns None, which means 204)"]),
          S("write_file", path="app/session.py", content=FUTURE + """from py_serverless_kit import Response


def start(event, ctx):
    resp = Response.json({"ok": True}).set_cookie("sid", "abc123", max_age=3600)
    resp.headers.update({"cache-control": "no-store"})
    return resp
"""),
          S("invoke_local", function="session", method="POST", path="/session"),
          S("validate"),
      ],
      final="""`headers.update(...)` changes the dict and returns `None`, so the handler returned `None`, and `None` means 204 No Content [docs/handlers.md#returning-a-response]. Now it updates the headers and then returns `resp`.

- POST /session: 200, `cache-control: no-store`, body `{"ok": true}`. The `sid` cookie is set on the response.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 118 gcp schedule, sort with missing priority
    B(118, provider="gcp", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: batch-runner\n" + GCP.format(region="us-west1") + """functions:
  run-jobs:
    handler: app.jobs.run
    events:
      - schedule:
          cron: "0 * * * *"
          input:
            jobs:
              - {name: reindex, priority: 1}
              - {name: cleanup}
              - {name: export, priority: 2}
""",
          "app/__init__.py": "",
          "app/jobs.py": FUTURE + """
def run(event, ctx):
    jobs = sorted(event.data["jobs"], key=lambda j: j.get("priority"))
    return {"order": [j["name"] for j in jobs]}
""",
          "requirements.txt": ""}),
      user="my hourly job list crashes with '<' not supported between instances of 'NoneType' and 'int'. cleanup has no priority, it should just run last",
      steps=[
          S("read_file", path="app/jobs.py"),
          S("invoke_local", function="run-jobs", type="schedule"),
          S("propose_plan", steps=["Sort jobs without a priority last: key `(priority is None, priority or 0)`",
                                   "Run run-jobs as a schedule event and validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/jobs.py", content=FUTURE + """
def run(event, ctx):
    def order(job):
        p = job.get("priority")
        return (p is None, p or 0)

    jobs = sorted(event.data["jobs"], key=order)
    return {"order": [j["name"] for j in jobs]}
"""),
          S("invoke_local", function="run-jobs", type="schedule"),
          S("validate"),
      ],
      final="""`cleanup` has no `priority`, so `j.get("priority")` gave `None`, and Python can't compare `None` with a number while sorting. The sort key is now `(priority is None, priority)`, so jobs without a priority come after all the others.

- schedule run (configured input): `{"order": ["reindex", "export", "cleanup"]}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 119 onprem queue, connection key in upper case
    B(119, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": "service: metrics\n" + ONPREM.format(port=8219) + """resources:
  tsdb:
    type: database
    external: true
    connection: {host: tsdb.example.com, port: 8086, bucket: plant-a}
functions:
  write-points:
    handler: app.points.write
    events:
      - queue: points
""",
          "app/__init__.py": "",
          "app/points.py": FUTURE + """from py_serverless_kit import resource


def write(event, ctx):
    db = resource("tsdb")
    target = f"{db.connection['HOST']}:{db.connection['PORT']}/{db.connection['BUCKET']}"
    ctx.logger.info("writing", extra={"points": len(event.records), "target": target})
    return {"written": len(event.records), "target": target}
""",
          "requirements.txt": ""}),
      user="write-points: KeyError 'HOST'. env shows PSKIT_RESOURCE_TSDB_HOST is set",
      steps=[
          S("read_file", path="app/points.py"),
          S("invoke_local", function="write-points", type="queue", data=[{"m": "temp", "v": 21}]),
          S("search_docs", query="resource connection keys lower case",
            docs=[D("docs/resources.md", "runtime-api", end="jobs[\"region\"]")]),
          S("propose_plan", steps=["Read connection values with `db[\"host\"]` etc. (keys are lower case; `db[...]` / `db.get()` ignore case)",
                                   "Invoke write-points and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/points.py", content=FUTURE + """from py_serverless_kit import resource


def write(event, ctx):
    db = resource("tsdb")
    target = f"{db['host']}:{db['port']}/{db['bucket']}"
    ctx.logger.info("writing", extra={"points": len(event.records), "target": target})
    return {"written": len(event.records), "target": target}
"""),
          S("invoke_local", function="write-points", type="queue", data=[{"m": "temp", "v": 21}]),
          S("validate"),
      ],
      final="""The env var is upper case, but `Resource.connection` keys are **lower case** (`host`, `port`, `bucket`) [docs/resources.md#runtime-api]. `db["host"]` and `db.get("host")` ignore case; a raw `connection["HOST"]` doesn't. Switched to `db["host"]`, `db["port"]`, `db["bucket"]`.

- invoke: `{"written": 1, "target": "tsdb.example.com:8086/plant-a"}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 120 aws schedule, split() on a list input
    B(120, provider="aws", stage="prod", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: cost-watch
provider:
  name: aws
  region: us-east-1
functions:
  cost-scan:
    handler: app.costs.scan
    events:
      - schedule:
          rate: 6 hours
          input:
            regions: [us-east-1, eu-west-1]
""",
          "app/__init__.py": "",
          "app/costs.py": FUTURE + """
def scan(event, ctx):
    regions = [r.strip() for r in event.data["regions"].split(",")]
    return {"scanned": regions}
""",
          "requirements.txt": ""}),
      user="cost-scan crash 'list' object has no attribute 'split'. before regions was a string \"us-east-1,eu-west-1\", i changed yml to a list",
      steps=[
          S("read_file", path="app/costs.py"),
          S("invoke_local", function="cost-scan", type="schedule"),
          S("propose_plan", steps=["Use the list from the input directly; still accept the old comma string",
                                   "Run cost-scan as a schedule event and validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/costs.py", content=FUTURE + """
def scan(event, ctx):
    regions = event.data["regions"]
    if isinstance(regions, str):
        regions = regions.split(",")
    return {"scanned": [r.strip() for r in regions]}
"""),
          S("invoke_local", function="cost-scan", type="schedule"),
          S("validate"),
      ],
      final="""The schedule `input` reaches the handler unchanged as `event.data` [docs/events.md#schedule]. Your new YAML list is now a Python list, and lists have no `.split()`. The handler now uses the list as it is, and still splits the old comma string if one comes in.

- schedule run: `{"scanned": ["us-east-1", "eu-west-1"]}`.
- validate (aws, prod): valid."""),
]
