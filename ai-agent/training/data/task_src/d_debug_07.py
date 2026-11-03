"""Category D (fix a handler bug), batch 7. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 121 onprem http, await in a sync def
    B(121, provider="onprem", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": "service: weather-proxy\n" + ONPREM.format(port=8221) + """functions:
  forecast:
    handler: app.forecast.get_forecast
    events:
      - http: GET /forecast
""",
          "app/__init__.py": "",
          "app/forecast.py": FUTURE + """import asyncio


async def lookup(city):
    await asyncio.sleep(0)
    return {"city": city, "max_c": 14}


def get_forecast(event, ctx):
    city = event.http.query.get("city", "Oslo")
    return await lookup(city)
""",
          "requirements.txt": ""}),
      user="""SyntaxError: 'await' outside async function (forecast.py, line 13)
what? the await is inside get_forecast""",
      steps=[
          S("read_file", path="app/forecast.py"),
          S("invoke_local", function="forecast", path="/forecast?city=Bergen"),
          S("propose_plan", steps=["Declare the handler `async def get_forecast(...)`; pskit awaits it",
                                   "GET /forecast?city=Bergen locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/forecast.py", content=FUTURE + """import asyncio


async def lookup(city):
    await asyncio.sleep(0)
    return {"city": city, "max_c": 14}


async def get_forecast(event, ctx):
    city = event.http.query.get("city", "Oslo")
    return await lookup(city)
"""),
          S("invoke_local", function="forecast", path="/forecast?city=Bergen"),
          S("validate"),
      ],
      final="""`await` is only allowed inside an `async def`, and `get_forecast` was a plain `def`. Python rejects that when it loads the file, so no request could run. Now the handler is `async def get_forecast`. pskit awaits coroutine handlers [docs/handlers.md#handler-signatures].

- GET /forecast?city=Bergen: 200, `{"city": "Bergen", "max_c": 14}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 122 aws storage, suffix compare after lower()
    B(122, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: ledger-import
provider:
  name: aws
  region: eu-north-1
functions:
  import-csv:
    handler: app.ledger.import_csv
    events:
      - storage:
          bucket: ledger-drop
          events: [created]
""",
          "app/__init__.py": "",
          "app/ledger.py": FUTURE + """
def import_csv(event, ctx):
    imported, skipped = [], []
    for record in event.records:
        if record.key.lower().endswith(".CSV"):
            imported.append(record.key)
        else:
            skipped.append(record.key)
    ctx.logger.info("import done", extra={"imported": len(imported), "skipped": len(skipped)})
    return {"imported": imported, "skipped": skipped}
""",
          "requirements.txt": ""}),
      user="import-csv must import every .csv file dropped in the bucket, whatever the case of the extension (bank exports use .CSV, ours use .csv), and skip everything else. Right now it skips all files, including the CSVs. Please fix and test with ledger.CSV, ledger2.csv and notes.txt.",
      steps=[
          S("read_file", path="app/ledger.py"),
          S("invoke_local", function="import-csv", type="storage",
            data=[{"key": "ledger.CSV"}, {"key": "ledger2.csv"}, {"key": "notes.txt"}]),
          S("propose_plan", steps=["Compare the lower-cased key with a lower-case suffix: `.endswith(\".csv\")`",
                                   "Invoke with the three test files and validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/ledger.py", content=FUTURE + """
def import_csv(event, ctx):
    imported, skipped = [], []
    for record in event.records:
        if record.key.lower().endswith(".csv"):
            imported.append(record.key)
        else:
            skipped.append(record.key)
    ctx.logger.info("import done", extra={"imported": len(imported), "skipped": len(skipped)})
    return {"imported": imported, "skipped": skipped}
"""),
          S("invoke_local", function="import-csv", type="storage",
            data=[{"key": "ledger.CSV"}, {"key": "ledger2.csv"}, {"key": "notes.txt"}]),
          S("validate"),
      ],
      final="""The key was lower-cased and then compared with `".CSV"` in upper case, which can never match. So every file was skipped. Now both sides are lower case: `record.key.lower().endswith(".csv")`. `record.key` itself is unchanged [docs/handlers.md#record].

- Before: all three skipped.
- After: `{"imported": ["ledger.CSV", "ledger2.csv"], "skipped": ["notes.txt"]}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 123 gcp queue, BadRequest in a queue worker
    B(123, provider="gcp", stage="prod", mode="ask", page="Logs", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: events-sink\n" + GCP.format(region="europe-west4") + """functions:
  sink:
    handler: app.sink.handle
    events:
      - queue: raw-events
""",
          "app/__init__.py": "",
          "app/sink.py": FUTURE + """from py_serverless_kit import BadRequest


def handle(event, ctx):
    stored = 0
    for record in event.records:
        msg = record.json()
        if "type" not in msg:
            raise BadRequest("event without type")
        stored += 1
    return {"stored": stored}
""",
          "requirements.txt": ""}),
      user="sink: one message without 'type' gets redelivered forever. I raise BadRequest, thought that drops it (400)",
      steps=[
          S("read_file", path="app/sink.py"),
          S("invoke_local", function="sink", type="queue", data=[{"type": "click"}, {"page": "/home"}]),
          S("search_docs", query="exceptions non-HTTP events retry",
            docs=[D("docs/handlers.md", "errors", start="For **non-HTTP** events")]),
          S("propose_plan", steps=["Don't raise for a malformed message: log a warning and skip it, so the delivery is acknowledged",
                                   "Invoke with one good and one malformed message; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sink.py", content=FUTURE + """
def handle(event, ctx):
    stored, dropped = 0, 0
    for record in event.records:
        msg = record.json(default=None)
        if not isinstance(msg, dict) or "type" not in msg:
            ctx.logger.warning("dropping malformed event", extra={"record": record.id})
            dropped += 1
            continue
        stored += 1
    return {"stored": stored, "dropped": dropped}
"""),
          S("invoke_local", function="sink", type="queue", data=[{"type": "click"}, {"page": "/home"}]),
          S("validate"),
      ],
      final="""`BadRequest` is a 400 only for HTTP. For queue events every exception is re-raised so the platform retries [docs/handlers.md#errors]; on Pub/Sub that means the same bad message comes back again and again. A message that can never succeed should be logged and skipped. The handler now does that (bad JSON included) and returns the counts.

- invoke: logs "dropping malformed event" for `local-1`, `{"stored": 1, "dropped": 1}`.
- validate (gcp, prod): valid.

If you want to keep the bad ones, set `dead_letter` on the queue event instead of dropping them."""),

    # ------------------------------------------------------------------ 124 onprem schedule, naive vs aware datetime
    B(124, provider="onprem", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": "service: maintenance\n" + ONPREM.format(port=8222) + """functions:
  window-check:
    handler: app.window.check
    events:
      - schedule:
          rate: 10 minutes
          input: {window_end: "2026-11-02T06:00:00+00:00"}
""",
          "app/__init__.py": "",
          "app/window.py": FUTURE + """from datetime import datetime


def check(event, ctx):
    end = datetime.fromisoformat(event.data["window_end"])
    active = datetime.now() < end
    return {"maintenance": active}
""",
          "requirements.txt": ""}),
      user="window-check say can't compare offset-naive and offset-aware datetimes. the window_end have +00:00 inside",
      steps=[
          S("read_file", path="app/window.py"),
          S("invoke_local", function="window-check", type="schedule"),
          S("propose_plan", steps=["Compare with an aware time: `event.time` (UTC) instead of `datetime.now()`",
                                   "Run window-check as a schedule event and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/window.py", content=FUTURE + """from datetime import datetime


def check(event, ctx):
    end = datetime.fromisoformat(event.data["window_end"])
    active = event.time < end
    return {"maintenance": active}
"""),
          S("invoke_local", function="window-check", type="schedule"),
          S("validate"),
      ],
      final="""Yes, `window_end` has a time zone (`+00:00`), but `datetime.now()` has none, and Python won't compare the two. `event.time` is the event time **in UTC with a time zone** [docs/handlers.md#event], so the handler compares with that now.

- schedule run: `{"maintenance": true}` (the window ends 2026-11-02 06:00 UTC).
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 125 azure http, quantity sent as a string
    B(125, provider="azure", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: quotes
provider:
  name: azure
  region: swedencentral
functions:
  quote:
    handler: app.quote.quote
    events:
      - http: POST /quote
""",
          "app/__init__.py": "",
          "app/quote.py": FUTURE + """PRICE = 4.5


def quote(event, ctx):
    data = event.http.json(default={})
    total = data["qty"] * PRICE
    return {"qty": data["qty"], "total": total}
""",
          "requirements.txt": ""}),
      user="mobile app send {\"qty\": \"3\"} and quote crash can't multiply sequence by non-int of type 'float'. web app send 3 and work. can handler accept both? bad value should be 400",
      steps=[
          S("read_file", path="app/quote.py"),
          S("invoke_local", function="quote", method="POST", path="/quote", data={"qty": "3"}),
          S("propose_plan", steps=["Convert `qty` with `int()`; raise `BadRequest` when it is missing or not a whole number",
                                   "POST `{\"qty\": \"3\"}` and `{\"qty\": \"many\"}`; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/quote.py", content=FUTURE + """from py_serverless_kit import BadRequest

PRICE = 4.5


def quote(event, ctx):
    data = event.http.json(default={})
    try:
        qty = int(data["qty"])
    except (KeyError, TypeError, ValueError):
        raise BadRequest("qty must be a whole number") from None
    return {"qty": qty, "total": qty * PRICE}
"""),
          S("invoke_local", function="quote", method="POST", path="/quote", data={"qty": "many"}),
          S("invoke_local", function="quote", method="POST", path="/quote", data={"qty": "3"}),
          S("validate"),
      ],
      final="""`"3"` is a string, and in Python `"3" * 4.5` is not allowed. The handler now converts with `int()`, so both `3` and `"3"` work. A missing or non-numeric `qty` raises `BadRequest` (400) [docs/handlers.md#errors].

- `{"qty": "many"}`: 400, `{"error": "qty must be a whole number", "status": 400}`.
- `{"qty": "3"}`: 200, `{"qty": 3, "total": 13.5}`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 126 onprem queue, BatchResult wrapped in a dict
    B(126, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": "service: webhooks-out\n" + ONPREM.format(port=8223) + """functions:
  deliver:
    handler: app.deliver.handle
    events:
      - queue:
          name: webhooks
          max_receive: 4
          dead_letter: webhooks-dead
""",
          "app/__init__.py": "",
          "app/deliver.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        hook = record.json()
        if not str(hook.get("url", "")).startswith("https://"):
            result.fail(record)
    return {"delivered": len(event.records) - len(result.failed), "result": result}
""",
          "requirements.txt": ""}),
      user="Failed webhook messages are never retried and never reach the webhooks-dead queue, they just disappear. I do call result.fail(record). Failed ones must be retried and end up in the dead-letter queue after 4 tries. Please fix and test with one https and one http URL.",
      steps=[
          S("read_file", path="app/deliver.py"),
          S("invoke_local", function="deliver", type="queue",
            data=[{"url": "https://hooks.example.com/a"}, {"url": "http://hooks.example.com/b"}]),
          S("search_docs", query="return BatchResult onprem retry dead letter",
            docs=[D("docs/handlers.md", "batchresult", start="| Provider |", end="| local |")]),
          S("propose_plan", steps=["Return the `BatchResult` itself (log the delivered count instead of returning a dict)",
                                   "Invoke with an https and an http URL; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/deliver.py", content=FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        hook = record.json()
        if not str(hook.get("url", "")).startswith("https://"):
            result.fail(record)
    ctx.logger.info("delivered", extra={"count": len(event.records) - len(result.failed)})
    return result
"""),
          S("invoke_local", function="deliver", type="queue",
            data=[{"url": "https://hooks.example.com/a"}, {"url": "http://hooks.example.com/b"}]),
          S("validate"),
      ],
      final="""The host only looks at failures when the handler **returns a `BatchResult`** [docs/handlers.md#batchresult]. Your handler put it inside a dict, so the dict counted as a normal success and every message was acknowledged. Now `handle` returns `result` directly and logs the delivered count.

- Before: a plain dict (`"result"` held the BatchResult as text), no `batchItemFailures`.
- After: logs "delivered" (count 1), `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`.
- validate (onprem, prod): valid. The http message is retried and moves to `webhooks-dead` after `max_receive: 4`."""),

    # ------------------------------------------------------------------ 127 aws http, Response.json(body=...)
    B(127, provider="aws", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: links
provider:
  name: aws
  region: us-west-1
functions:
  shorten:
    handler: app.links.shorten
    events:
      - http: POST /links
""",
          "app/__init__.py": "",
          "app/links.py": FUTURE + """from py_serverless_kit import Response


def shorten(event, ctx):
    url = event.http.json()["url"]
    code = format(abs(hash(url)) % 1_000_000, "06d")
    return Response.json(body={"code": code, "url": url}, status=201)
""",
          "requirements.txt": ""}),
      user="shorten: TypeError Response.json() got an unexpected keyword argument 'body'",
      steps=[
          S("read_file", path="app/links.py"),
          S("invoke_local", function="shorten", method="POST", path="/links", data={"url": "https://example.com/a"}),
          S("propose_plan", steps=["Pass the data positionally: `Response.json({...}, status=201)`"]),
          S("write_file", path="app/links.py", content=FUTURE + """from py_serverless_kit import Response


def shorten(event, ctx):
    url = event.http.json()["url"]
    code = format(abs(hash(url)) % 1_000_000, "06d")
    return Response.json({"code": code, "url": url}, status=201)
"""),
          S("invoke_local", function="shorten", method="POST", path="/links", data={"url": "https://example.com/a"}),
          S("validate"),
      ],
      final="""`Response.json(data, status=200, headers=None)`: the first parameter is `data`, not `body` [docs/handlers.md#returning-a-response]. Now: `Response.json({...}, status=201)`.

- POST /links: 201 with `code` and `url`.
- validate (aws): valid.

Note: `hash()` of a str changes between processes, so the code differs per cold start. Use `hashlib` if codes must be stable."""),

    # ------------------------------------------------------------------ 128 gcp workflow task, generic Exception vs retry
    B(128, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": "service: kyc-check\n" + GCP.format(region="us-central1") + """functions:
  verify-id:
    handler: app.verify.verify
workflows:
  verify:
    start_at: Verify
    states:
      Verify:
        type: task
        function: verify-id
        retry: [{errors: [TimeoutError], max_attempts: 3, interval_seconds: 5}]
        end: true
""",
          "app/__init__.py": "",
          "app/verify.py": FUTURE + """
def verify(event, ctx):
    if event.data.get("simulate") == "timeout":
        raise Exception("id provider timed out")
    return {"person": event.data["person"], "verified": True}
""",
          "requirements.txt": ""}),
      user="The Verify state has a retry for TimeoutError, but when the ID provider times out the workflow fails at once with no retry. The handler should signal timeouts so the retry rule matches; other errors must keep failing right away. Test with {\"simulate\": \"timeout\"} and with a normal input.",
      steps=[
          S("read_file", path="app/verify.py"),
          S("invoke_local", function="verify-id", type="workflow", data={"person": "p-1", "simulate": "timeout"}),
          S("search_docs", query="retry errors exception class name",
            docs=[D("docs/workflows.md", "retry-and-catch", start="Error names are")]),
          S("propose_plan", steps=["Raise `TimeoutError(...)` for provider timeouts instead of a bare `Exception`",
                                   "Invoke verify-id with the timeout input and a normal input; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/verify.py", content=FUTURE + """
def verify(event, ctx):
    if event.data.get("simulate") == "timeout":
        raise TimeoutError("id provider timed out")
    return {"person": event.data["person"], "verified": True}
"""),
          S("invoke_local", function="verify-id", type="workflow", data={"person": "p-1", "simulate": "timeout"}),
          S("invoke_local", function="verify-id", type="workflow", data={"person": "p-1"}),
          S("validate"),
      ],
      final="""Retry rules match on the **Python exception class name** [docs/workflows.md#retry-and-catch]. The handler raised a plain `Exception`, so `errors: [TimeoutError]` never matched. It now raises `TimeoutError`; other exceptions are unchanged and still fail right away.

- timeout input: now raises `TimeoutError: id provider timed out`, so the retry rule applies (3 attempts, 5 s apart).
- normal input: `{"person": "p-1", "verified": true}`.
- validate (gcp, staging): valid; the workflow uses the native engine."""),

    # ------------------------------------------------------------------ 129 onprem storage, PSKIT_ONPREM_ROOT missing locally
    B(129, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": "service: photo-sort\n" + ONPREM.format(port=8224) + """functions:
  sort-photo:
    handler: app.sort.handle
    events:
      - storage: camera-roll
""",
          "app/__init__.py": "",
          "app/sort.py": FUTURE + """import os


def handle(event, ctx):
    root = ctx.env["PSKIT_ONPREM_ROOT"]
    moved = []
    for record in event.records:
        year = record.key.split("-")[0]
        moved.append(os.path.join(root, "sorted", year, record.key))
    return {"targets": moved}
""",
          "requirements.txt": ""}),
      user="sort-photo works after deploy, but when I click Run locally on the Test page I get KeyError: 'PSKIT_ONPREM_ROOT'. Did I break something?",
      steps=[
          S("read_file", path="app/sort.py"),
          S("invoke_local", function="sort-photo", type="storage", data=[{"key": "2025-07-14-beach.jpg"}]),
          S("search_docs", query="PSKIT_ONPREM_ROOT environment variables",
            docs=[D("docs/handlers.md", "environment-variables", end="| `PSKIT_GCP_PROJECT` |")]),
          S("propose_plan", steps=["Read `PSKIT_ONPREM_ROOT` with `.get()` and fall back to the current folder for local runs",
                                   "Run sort-photo locally with a test photo and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sort.py", content=FUTURE + """import os


def handle(event, ctx):
    root = ctx.env.get("PSKIT_ONPREM_ROOT", ".")
    moved = []
    for record in event.records:
        year = record.key.split("-")[0]
        moved.append(os.path.join(root, "sorted", year, record.key))
    return {"targets": moved}
"""),
          S("invoke_local", function="sort-photo", type="storage", data=[{"key": "2025-07-14-beach.jpg"}]),
          S("validate"),
      ],
      final="""You didn't break anything. `PSKIT_ONPREM_ROOT` is set **only on the on-premises host** (it is the host's directory) [docs/handlers.md#environment-variables]. Run locally runs the function on your machine without the host, so the variable is missing. The handler now uses `ctx.env.get("PSKIT_ONPREM_ROOT", ".")`: the host directory on the server, the current folder locally.

- Local run with `2025-07-14-beach.jpg`: the target is `sorted/2025/2025-07-14-beach.jpg` under the current folder (shown with backslashes on Windows).
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 130 azure topic, Decimal not imported
    B(130, provider="azure", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: payouts
provider:
  name: azure
  region: australiaeast
functions:
  sum-payouts:
    handler: app.payouts.total
    events:
      - topic: payouts
""",
          "app/__init__.py": "",
          "app/payouts.py": FUTURE + """
def total(event, ctx):
    amount = Decimal("0")
    for record in event.records:
        amount += Decimal(str(record.json()["amount"]))
    ctx.logger.info("payout total", extra={"total": str(amount)})
    return {"total": str(amount)}
""",
          "requirements.txt": ""}),
      user="""NameError: name 'Decimal' is not defined
sum-payouts""",
      steps=[
          S("read_file", path="app/payouts.py"),
          S("invoke_local", function="sum-payouts", type="topic", data=[{"amount": 10.10}, {"amount": 0.2}]),
          S("propose_plan", steps=["Add `from decimal import Decimal`",
                                   "Invoke with two payouts; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/payouts.py", content=FUTURE + """from decimal import Decimal


def total(event, ctx):
    amount = Decimal("0")
    for record in event.records:
        amount += Decimal(str(record.json()["amount"]))
    ctx.logger.info("payout total", extra={"total": str(amount)})
    return {"total": str(amount)}
"""),
          S("invoke_local", function="sum-payouts", type="topic", data=[{"amount": 10.10}, {"amount": 0.2}]),
          S("validate"),
      ],
      final="""`Decimal` lives in the `decimal` module and was never imported. Added `from decimal import Decimal`.

- invoke (10.10 + 0.2): logs "payout total", returns `{"total": "10.3"}`. Exact, unlike float math.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 131 azure http, slice with a str limit
    B(131, provider="azure", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: news
provider:
  name: azure
  region: japaneast
functions:
  latest:
    handler: app.news.latest
    events:
      - http: GET /news
""",
          "app/__init__.py": "",
          "app/news.py": FUTURE + """NEWS = [f"story-{i}" for i in range(1, 31)]


def latest(event, ctx):
    limit = event.http.query.get("limit", 10)
    return {"items": NEWS[:limit]}
""",
          "requirements.txt": ""}),
      user="/news work but /news?limit=3 give 500 'slice indices must be integers'. 3 is integer??",
      steps=[
          S("read_file", path="app/news.py"),
          S("invoke_local", function="latest", path="/news?limit=3"),
          S("propose_plan", steps=["Convert with `int(...)` (default \"10\"), cap it at 30, and answer 400 for a bad value",
                                   "GET /news?limit=3 locally and validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/news.py", content=FUTURE + """from py_serverless_kit import BadRequest

NEWS = [f"story-{i}" for i in range(1, 31)]


def latest(event, ctx):
    raw = event.http.query.get("limit", "10")
    if not raw.isdigit():
        raise BadRequest("limit must be a number")
    return {"items": NEWS[:min(int(raw), 30)]}
"""),
          S("invoke_local", function="latest", path="/news?limit=3"),
          S("validate"),
      ],
      final="""In the URL it is `"3"`, a **string**: query values are always strings [docs/handlers.md#httprequest]. Without `?limit` the default `10` was a real int, so that case worked. Now the handler converts with `int()`, caps the limit at 30 and returns 400 for something like `?limit=abc`.

- GET /news?limit=3: 200, `{"items": ["story-1", "story-2", "story-3"]}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 132 aws queue, SQS attribute missing locally
    B(132, provider="aws", stage="staging", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: order-events
provider:
  name: aws
  region: eu-west-1
functions:
  apply-event:
    handler: app.apply.handle
    events:
      - queue:
          name: order-events.fifo
          fifo: true
""",
          "app/__init__.py": "",
          "app/apply.py": FUTURE + """
def handle(event, ctx):
    groups = {}
    for record in event.records:
        group = record.attributes["MessageGroupId"]
        groups.setdefault(group, []).append(record.json()["seq"])
    return {"groups": groups}
""",
          "requirements.txt": ""}),
      user="On Lambda this FIFO consumer works with record.attributes['MessageGroupId'], but pskit invoke on my laptop fails with KeyError: 'MessageGroupId'. How do I test it locally?",
      steps=[
          S("read_file", path="app/apply.py"),
          S("invoke_local", function="apply-event", type="queue", data=[{"seq": 1}, {"seq": 2}]),
          S("search_docs", query="record attributes queue",
            docs=[D("docs/handlers.md", "record")]),
          S("propose_plan", steps=["Read the group with `record.attributes.get(\"MessageGroupId\", \"default\")` so local test messages (no attributes) still work",
                                   "Invoke apply-event with two messages; validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/apply.py", content=FUTURE + """
def handle(event, ctx):
    groups = {}
    for record in event.records:
        group = record.attributes.get("MessageGroupId", "default")
        groups.setdefault(group, []).append(record.json()["seq"])
    return {"groups": groups}
"""),
          S("invoke_local", function="apply-event", type="queue", data=[{"seq": 1}, {"seq": 2}]),
          S("validate"),
      ],
      final="""`record.attributes` holds the platform's message metadata [docs/handlers.md#record]. On SQS that includes `MessageGroupId`. Test messages from `pskit invoke` have **no** attributes, so `["MessageGroupId"]` raised `KeyError`. The handler now uses `.get("MessageGroupId", "default")`, so it works the same on Lambda and in local tests.

- invoke (seq 1, 2): `{"groups": {"default": [1, 2]}}`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 133 gcp http, list body with .get
    B(133, provider="gcp", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: survey\n" + GCP.format(region="southamerica-east1") + """functions:
  answers:
    handler: app.survey.answers
    events:
      - http: POST /answers
""",
          "app/__init__.py": "",
          "app/survey.py": FUTURE + """
def answers(event, ctx):
    data = event.http.json()
    score = data.get("score", 0)
    return {"received": 1, "score": score}
""",
          "requirements.txt": ""}),
      user="the survey page now sends all answers at once, like [{\"score\": 4}, {\"score\": 5}], and I get 'list' object has no attribute 'get'. One answer at a time worked. Can it take both?",
      steps=[
          S("read_file", path="app/survey.py"),
          S("invoke_local", function="answers", method="POST", path="/answers", data=[{"score": 4}, {"score": 5}]),
          S("propose_plan", steps=["Wrap a single object in a list, then add up the scores of every answer",
                                   "POST a list of two answers locally and validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/survey.py", content=FUTURE + """
def answers(event, ctx):
    data = event.http.json()
    items = data if isinstance(data, list) else [data]
    scores = [item.get("score", 0) for item in items]
    return {"received": len(items), "score": sum(scores)}
"""),
          S("invoke_local", function="answers", method="POST", path="/answers", data=[{"score": 4}, {"score": 5}]),
          S("validate"),
      ],
      final="""`event.http.json()` returns whatever JSON was sent. Now that is a **list**, and lists have no `.get()`. The handler now accepts both: a single object is wrapped in a list, then every answer is counted.

- POST /answers `[{"score": 4}, {"score": 5}]`: 200, `{"received": 2, "score": 9}`.
- validate (gcp): valid.

`score` is now the total; divide by `received` if you want the average."""),

    # ------------------------------------------------------------------ 134 onprem workflow map, item is the data
    B(134, provider="onprem", stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": "service: restock\n" + ONPREM.format(port=8225) + """functions:
  reorder-sku:
    handler: app.restock.reorder
workflows:
  restock:
    start_at: EachSku
    states:
      EachSku:
        type: map
        items_path: $.skus
        iterator:
          start_at: Reorder
          states:
            Reorder: {type: task, function: reorder-sku, end: true}
        end: true
""",
          "app/__init__.py": "",
          "app/restock.py": FUTURE + """
def reorder(event, ctx):
    sku = event.data["sku"]
    return {"sku": sku, "ordered": 24}
""",
          "requirements.txt": ""}),
      user="restock map: Reorder fails, string indices must be integers. input {\"skus\": [\"A1\", \"B2\"]}",
      steps=[
          S("read_file", path="app/restock.py"),
          S("invoke_local", function="reorder-sku", type="workflow", data="A1"),
          S("search_docs", query="map state iterator item input",
            docs=[D("docs/workflows.md", "state-types", start="| `map` |", end="| `map` |")]),
          S("propose_plan", steps=["In `reorder`, the map item is `event.data` itself (here a SKU string); accept a dict too"]),
          S("write_file", path="app/restock.py", content=FUTURE + """
def reorder(event, ctx):
    item = event.data
    sku = item["sku"] if isinstance(item, dict) else item
    return {"sku": sku, "ordered": 24}
"""),
          S("invoke_local", function="reorder-sku", type="workflow", data="A1"),
          S("validate"),
      ],
      final="""A `map` state runs the iterator once **per item** of `$.skus` [docs/workflows.md#state-types], so `Reorder` gets `"A1"`, not `{"sku": "A1"}`. Fixed: the item itself is the SKU; a `{"sku": ...}` dict is also accepted.

- reorder-sku with `"A1"`: `{"sku": "A1", "ordered": 24}`.
- validate (onprem, staging): valid. The workflow result is a list with one entry per SKU."""),

    # ------------------------------------------------------------------ 135 azure http, custom class in the response
    B(135, provider="azure", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: products
provider:
  name: azure
  region: canadacentral
functions:
  product:
    handler: app.products.get_product
    events:
      - http: GET /products/{sku}
""",
          "app/__init__.py": "",
          "app/products.py": FUTURE + """
class Product:
    def __init__(self, sku, name, price):
        self.sku = sku
        self.name = name
        self.price = price


def get_product(event, ctx):
    sku = event.http.path_params["sku"]
    return Product(sku, "Desk lamp", 39.0)
""",
          "requirements.txt": ""}),
      user="""TypeError: Object of type Product is not JSON serializable
GET /products/L-1""",
      steps=[
          S("read_file", path="app/products.py"),
          S("invoke_local", function="product", path="/products/L-1"),
          S("search_docs", query="return dataclass json response",
            docs=[D("docs/handlers.md", "returning-a-response", end="JSON serialisation handles")]),
          S("propose_plan", steps=["Make `Product` a `@dataclass`; pskit serialises dataclasses to JSON",
                                   "GET /products/L-1 locally and validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/products.py", content=FUTURE + """from dataclasses import dataclass


@dataclass
class Product:
    sku: str
    name: str
    price: float


def get_product(event, ctx):
    sku = event.http.path_params["sku"]
    return Product(sku, "Desk lamp", 39.0)
"""),
          S("invoke_local", function="product", path="/products/L-1"),
          S("validate"),
      ],
      final="""pskit turns dicts, lists, dataclasses, pydantic models and objects with `to_dict()` into JSON [docs/handlers.md#returning-a-response]. A plain class is none of those. I made `Product` a `@dataclass`; the call site stays the same.

- GET /products/L-1: 200, `{"sku": "L-1", "name": "Desk lamp", "price": 39.0}`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 136 onprem http, lru_cache on the handler
    B(136, provider="onprem", stage="prod", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": "service: tariffs\n" + ONPREM.format(port=8226) + """functions:
  tariff:
    handler: app.tariff.get_tariff
    events:
      - http: GET /tariff/{zone}
""",
          "app/__init__.py": "",
          "app/tariff.py": FUTURE + """from functools import lru_cache

RATES = {"north": 0.21, "south": 0.18}


@lru_cache(maxsize=128)
def get_tariff(event, ctx):
    zone = event.http.path_params["zone"]
    return {"zone": zone, "rate": RATES.get(zone)}
""",
          "requirements.txt": ""}),
      user="In Lambda I put @lru_cache on handlers to cache between warm calls. Here it fails with TypeError: unhashable type: 'Event'. How do I cache in pskit?",
      steps=[
          S("read_file", path="app/tariff.py"),
          S("invoke_local", function="tariff", path="/tariff/north"),
          S("propose_plan", steps=["Cache a helper keyed by the zone string, not the handler (Event and Context can't be cache keys)",
                                   "GET /tariff/north locally and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tariff.py", content=FUTURE + """from functools import lru_cache

RATES = {"north": 0.21, "south": 0.18}


@lru_cache(maxsize=128)
def rate_for(zone):
    return RATES.get(zone)


def get_tariff(event, ctx):
    zone = event.http.path_params["zone"]
    return {"zone": zone, "rate": rate_for(zone)}
"""),
          S("invoke_local", function="tariff", path="/tariff/north"),
          S("validate"),
      ],
      final="""`lru_cache` uses the arguments as the cache key. The handler's arguments are `(event, ctx)`, and `Event` can't be hashed (each event is new anyway, so it would never hit). Cache the expensive part instead, keyed by simple values. `rate_for(zone)` is now cached; the handler stays plain [docs/handlers.md#handler-signatures].

- GET /tariff/north: 200, `{"zone": "north", "rate": 0.21}`.
- validate (onprem, prod): valid.

On-premises the host process stays up, so the cache lasts between requests, like a warm Lambda."""),

    # ------------------------------------------------------------------ 137 aws schedule, date method not called
    B(137, provider="aws", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: daily-quote
provider:
  name: aws
  region: us-east-1
functions:
  quote-of-day:
    handler: app.quote.pick
    events:
      - schedule: "0 8 * * *"
""",
          "app/__init__.py": "",
          "app/quote.py": FUTURE + """QUOTES = ["Keep going.", "Small steps.", "Ship it."]


def pick(event, ctx):
    day = str(event.time.date)
    return {"day": day, "quote": QUOTES[event.time.day % len(QUOTES)]}
""",
          "requirements.txt": ""}),
      user="my quote job works but the day in the result looks like '<built-in method date of datetime.datetime object at 0x...>' instead of a date. what did I do?",
      steps=[
          S("read_file", path="app/quote.py"),
          S("invoke_local", function="quote-of-day", type="schedule"),
          S("propose_plan", steps=["Call the method: `event.time.date().isoformat()`",
                                   "Run quote-of-day as a schedule event and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/quote.py", content=FUTURE + """QUOTES = ["Keep going.", "Small steps.", "Ship it."]


def pick(event, ctx):
    day = event.time.date().isoformat()
    return {"day": day, "quote": QUOTES[event.time.day % len(QUOTES)]}
"""),
          S("invoke_local", function="quote-of-day", type="schedule"),
          S("validate"),
      ],
      final="""`date` is a method of `datetime`, so `event.time.date` without `()` is the method itself, and `str()` printed its description. Now it is `event.time.date().isoformat()`, for example `2026-11-01`. `event.time` is the run time in UTC [docs/handlers.md#event].

- schedule run: `{"day": "2026-11-01", ...}` with the quote for the day.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 138 gcp storage, size None on delete
    B(138, provider="gcp", stage="prod", mode="ask", page="Logs", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: quota\n" + GCP.format(region="europe-west2") + """functions:
  track-usage:
    handler: app.quota.track
    events:
      - storage:
          bucket: team-files
          events: [created, deleted]
""",
          "app/__init__.py": "",
          "app/quota.py": FUTURE + """
def track(event, ctx):
    delta = 0
    for record in event.records:
        kb = record.size / 1024
        delta += kb if record.action == "created" else -kb
    return {"delta_kb": round(delta, 1)}
""",
          "requirements.txt": ""}),
      user="track-usage fail when file deleted: unsupported operand type(s) for /: 'NoneType' and 'int'. upload is ok",
      steps=[
          S("read_file", path="app/quota.py"),
          S("invoke_local", function="track-usage", type="storage",
            data=[{"key": "a.zip", "size": 204800, "action": "created"}, {"key": "old.zip", "size": None, "action": "deleted"}]),
          S("search_docs", query="storage record size action deleted",
            docs=[D("docs/handlers.md", "record")]),
          S("propose_plan", steps=["Treat a missing size as 0 (`record.size or 0`); delete events may not carry a size",
                                   "Invoke with a created and a deleted file; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/quota.py", content=FUTURE + """
def track(event, ctx):
    delta = 0
    for record in event.records:
        kb = (record.size or 0) / 1024
        delta += kb if record.action == "created" else -kb
    return {"delta_kb": round(delta, 1)}
"""),
          S("invoke_local", function="track-usage", type="storage",
            data=[{"key": "a.zip", "size": 204800, "action": "created"}, {"key": "old.zip", "size": None, "action": "deleted"}]),
          S("validate"),
      ],
      final="""A delete notification can come without a size, so `record.size` is `None` [docs/handlers.md#record], and `None / 1024` fails. Now the handler uses `record.size or 0`.

- invoke (200 KB created + deleted file without size): `{"delta_kb": 200.0}`.
- validate (gcp, prod): valid.

To subtract the right amount for deletes, store each file's size when it is created (in a database, for example) and look it up by `record.key`."""),

    # ------------------------------------------------------------------ 139 onprem queue, resource key typo
    B(139, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": "service: thumbnails\n" + ONPREM.format(port=8227) + """resources:
  images:
    type: storage
    name: thumb-images
functions:
  make-thumb:
    handler: app.thumbs.handle
    events:
      - queue: thumb-jobs
""",
          "app/__init__.py": "",
          "app/thumbs.py": FUTURE + """from py_serverless_kit import resource


def handle(event, ctx):
    bucket = resource("image").native_name
    return {"bucket": bucket, "jobs": len(event.records)}
""",
          "requirements.txt": ""}),
      user="""KeyError: "resource 'image' is not bound to this function; bound: images. Check `resources:` and its `functions:` list in pskit.yml."
make-thumb""",
      steps=[
          S("read_file", path="app/thumbs.py"),
          S("invoke_local", function="make-thumb", type="queue", data=[{"file": "cat.png"}]),
          S("propose_plan", steps=["Use the resource key from pskit.yml: `resource(\"images\")`",
                                   "Invoke make-thumb and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/thumbs.py", content=FUTURE + """from py_serverless_kit import resource


def handle(event, ctx):
    bucket = resource("images").native_name
    return {"bucket": bucket, "jobs": len(event.records)}
"""),
          S("invoke_local", function="make-thumb", type="queue", data=[{"file": "cat.png"}]),
          S("validate"),
      ],
      final="""Typo: the key under `resources:` is `images`; the code asked for `image`. The error lists the bound names (`bound: images`) [docs/resources.md#runtime-api]. Fixed to `resource("images")`.

- invoke: `{"bucket": "thumb-images", "jobs": 1}`; `native_name` is the `name:` from pskit.yml.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 140 onprem http, datetime.date.today
    B(140, provider="onprem", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: canteen\n" + ONPREM.format(port=8228) + """functions:
  today-menu:
    handler: app.canteen.today
    events:
      - http: GET /today
""",
          "app/__init__.py": "",
          "app/canteen.py": FUTURE + """from datetime import datetime

MENU = ["pasta", "curry", "fish", "soup", "pizza", "salad", "stew"]


def today(event, ctx):
    day = datetime.date.today()
    return {"date": day, "dish": MENU[day.weekday()]}
""",
          "requirements.txt": ""}),
      user="today endpoint error 'method_descriptor' object has no attribute 'today'. i copy from stackoverflow",
      steps=[
          S("read_file", path="app/canteen.py"),
          S("invoke_local", function="today-menu", path="/today"),
          S("propose_plan", steps=["Import `date` and call `date.today()` (with `from datetime import datetime`, `datetime.date` is a method)",
                                   "GET /today locally and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/canteen.py", content=FUTURE + """from datetime import date

MENU = ["pasta", "curry", "fish", "soup", "pizza", "salad", "stew"]


def today(event, ctx):
    day = date.today()
    return {"date": day, "dish": MENU[day.weekday()]}
"""),
          S("invoke_local", function="today-menu", path="/today"),
          S("validate"),
      ],
      final="""The Stack Overflow code expects `import datetime` (the module). Your file has `from datetime import datetime` (the class), and on the class, `datetime.date` is a method. Now the file imports `date` and calls `date.today()`. Returning a `date` is fine: pskit turns it into ISO text [docs/handlers.md#returning-a-response].

- GET /today: 200, `{"date": "2026-11-01", "dish": "stew"}`.
- validate (onprem, staging): valid."""),
]
