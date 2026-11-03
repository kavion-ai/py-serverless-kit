"""Category D (fix a handler bug), batch 9. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 161 onprem http, summing string prices
    B(161, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": "service: basket\n" + ONPREM.format(port=8241) + """functions:
  basket-total:
    handler: app.basket.total
    events:
      - http: POST /basket/total
""",
          "app/__init__.py": "",
          "app/basket.py": FUTURE + """
def total(event, ctx):
    items = event.http.json()["items"]
    return {"total": sum(i["price"] for i in items)}
""",
          "requirements.txt": ""}),
      user="basket total error unsupported operand type(s) for +: 'int' and 'str'. the shop send price like \"2.50\"",
      steps=[
          S("read_file", path="app/basket.py"),
          S("invoke_local", function="basket-total", method="POST", path="/basket/total",
            data={"items": [{"price": "2.50"}, {"price": "1.25"}]}),
          S("propose_plan", steps=["Convert each price with `Decimal(str(...))`; a price that isn't a number gives 400",
                                   "POST two string prices locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/basket.py", content=FUTURE + """from decimal import Decimal, InvalidOperation

from py_serverless_kit import BadRequest


def total(event, ctx):
    items = event.http.json()["items"]
    try:
        prices = [Decimal(str(i["price"])) for i in items]
    except (KeyError, InvalidOperation):
        raise BadRequest("every item needs a numeric price") from None
    return {"total": str(sum(prices, Decimal("0")))}
"""),
          S("invoke_local", function="basket-total", method="POST", path="/basket/total",
            data={"items": [{"price": "2.50"}, {"price": "1.25"}]}),
          S("validate"),
      ],
      final="""`sum()` starts at 0 and adds `"2.50"`, a **string**, so Python fails. Now every price is converted with `Decimal`, which reads both `"2.50"` and `2.5` and keeps money exact. A price that isn't a number gives 400 [docs/handlers.md#errors]. The total is returned as a string like `"3.75"`.

- POST with `"2.50"` and `"1.25"`: 200, `{"total": "3.75"}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 162 aws schedule, AWS_REGION env var locally
    B(162, provider="aws", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#context", "docs/local-development.md#environment"],
      project=dict(files={
          "pskit.yml": """service: snapshots
provider:
  name: aws
  region: eu-west-3
functions:
  snapshot:
    handler: app.snap.run
    events:
      - schedule: "0 1 * * *"
""",
          "app/__init__.py": "",
          "app/snap.py": FUTURE + """import os


def run(event, ctx):
    region = os.environ["AWS_REGION"]
    ctx.logger.info("snapshot", extra={"region": region})
    return {"region": region}
""",
          "requirements.txt": ""}),
      user="This Lambda code reads os.environ['AWS_REGION']. On Lambda it's fine, but 'pskit invoke -f snapshot' fails with KeyError: 'AWS_REGION'. Is there a pskit way to get the region?",
      steps=[
          S("read_file", path="app/snap.py"),
          S("invoke_local", function="snapshot", type="schedule"),
          S("search_docs", query="context region service stage",
            docs=[D("docs/handlers.md", "context", end="| `memory_mb` |")]),
          S("propose_plan", steps=["Use `ctx.region` (portable) instead of the Lambda-only `AWS_REGION` variable",
                                   "Run snapshot as a schedule event and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/snap.py", content=FUTURE + """
def run(event, ctx):
    region = ctx.region
    ctx.logger.info("snapshot", extra={"region": region})
    return {"region": region}
"""),
          S("invoke_local", function="snapshot", type="schedule"),
          S("validate"),
      ],
      final="""Yes: `ctx.region` [docs/handlers.md#context]. `AWS_REGION` is set by the Lambda platform only. A local run sets pskit's own variables instead, with `PSKIT_REGION=local` [docs/local-development.md#environment], so the AWS one is missing. `ctx.region` works everywhere: `eu-west-3` on Lambda, `local` on your laptop.

- local schedule run: `{"region": "local"}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 163 gcp http, math not imported
    B(163, provider="gcp", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: paging\n" + GCP.format(region="us-central1") + """functions:
  pages:
    handler: app.pages.count_pages
    events:
      - http: GET /pages
""",
          "app/__init__.py": "",
          "app/pages.py": FUTURE + """TOTAL_ITEMS = 101


def count_pages(event, ctx):
    size = int(event.http.query.get("size", "20"))
    return {"size": size, "pages": math.ceil(TOTAL_ITEMS / size)}
""",
          "requirements.txt": ""}),
      user="""NameError: name 'math' is not defined
GET /pages?size=25""",
      steps=[
          S("read_file", path="app/pages.py"),
          S("invoke_local", function="pages", path="/pages?size=25"),
          S("propose_plan", steps=["Add `import math`", "GET /pages?size=25 locally and validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/pages.py", content=FUTURE + """import math

TOTAL_ITEMS = 101


def count_pages(event, ctx):
    size = int(event.http.query.get("size", "20"))
    return {"size": size, "pages": math.ceil(TOTAL_ITEMS / size)}
"""),
          S("invoke_local", function="pages", path="/pages?size=25"),
          S("validate"),
      ],
      final="""`math` was never imported. Added `import math`.

- GET /pages?size=25: 200, `{"size": 25, "pages": 5}`.
- validate (gcp, prod): valid.

`?size=0` would still crash with a division by zero; say if you want a 400 for that."""),

    # ------------------------------------------------------------------ 164 onprem storage, splitext without the dot
    B(164, provider="onprem", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": "service: bank-import\n" + ONPREM.format(port=8242) + """functions:
  import-statement:
    handler: app.bank.handle
    events:
      - storage:
          bucket: statements
          events: [created]
""",
          "app/__init__.py": "",
          "app/bank.py": FUTURE + """import os


def handle(event, ctx):
    imported = []
    for record in event.records:
        ext = os.path.splitext(record.key)[1].lower()
        if ext in ("csv", "ofx"):
            imported.append(record.key)
    ctx.logger.info("statements", extra={"imported": len(imported)})
    return {"imported": imported}
""",
          "requirements.txt": ""}),
      user="import-statement should import .csv and .ofx bank statements dropped into the statements bucket and ignore other files. It runs without errors, but nothing is ever imported: the log always says imported 0. Please fix and test with may.csv, may.OFX and scan.pdf.",
      steps=[
          S("read_file", path="app/bank.py"),
          S("invoke_local", function="import-statement", type="storage",
            data=[{"key": "may.csv"}, {"key": "may.OFX"}, {"key": "scan.pdf"}]),
          S("propose_plan", steps=["Compare with the dot: `os.path.splitext()` returns `.csv`, so check `(\".csv\", \".ofx\")`",
                                   "Invoke with may.csv, may.OFX and scan.pdf; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/bank.py", content=FUTURE + """import os


def handle(event, ctx):
    imported = []
    for record in event.records:
        ext = os.path.splitext(record.key)[1].lower()
        if ext in (".csv", ".ofx"):
            imported.append(record.key)
    ctx.logger.info("statements", extra={"imported": len(imported)})
    return {"imported": imported}
"""),
          S("invoke_local", function="import-statement", type="storage",
            data=[{"key": "may.csv"}, {"key": "may.OFX"}, {"key": "scan.pdf"}]),
          S("validate"),
      ],
      final="""`os.path.splitext("may.csv")` returns `("may", ".csv")`: the extension **includes the dot**. Comparing with `"csv"` never matched. Now the check is `(".csv", ".ofx")`, still after `.lower()`, so `.OFX` counts too. `record.key` is the object name [docs/handlers.md#record].

- Before: `{"imported": []}`.
- After: `{"imported": ["may.csv", "may.OFX"]}`; scan.pdf is ignored.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 165 azure http, redirect to None
    B(165, provider="azure", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: go-links
provider:
  name: azure
  region: northeurope
functions:
  go:
    handler: app.go.go
    events:
      - http: GET /go
""",
          "app/__init__.py": "",
          "app/go.py": FUTURE + """from py_serverless_kit import Response


def go(event, ctx):
    target = event.http.query.get("to")
    return Response.redirect(target)
""",
          "requirements.txt": ""}),
      user="/go without ?to= send browser to a page called 'None' lol. should be error",
      steps=[
          S("read_file", path="app/go.py"),
          S("invoke_local", function="go", path="/go"),
          S("propose_plan", steps=["Raise `BadRequest` when `to` is missing; only redirect to paths that start with `/`",
                                   "GET /go without `to` locally and validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/go.py", content=FUTURE + """from py_serverless_kit import BadRequest, Response


def go(event, ctx):
    target = event.http.query.get("to")
    if not target or not target.startswith("/") or target.startswith("//"):
        raise BadRequest("`to` must be a path on this site, like /docs")
    return Response.redirect(target)
"""),
          S("invoke_local", function="go", path="/go"),
          S("validate"),
      ],
      final="""Without `?to=`, `target` is `None`, and the redirect's `location` header became the text `None`. Now a missing `to` is a 400. I also allow only paths on your own site (starting with `/`): redirecting to any URL a visitor passes in is an open-redirect hole.

- GET /go: 400, ``{"error": "`to` must be a path on this site, like /docs", "status": 400}``.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 166 onprem queue, new BatchResult per message
    B(166, provider="onprem", stage="prod", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": "service: ledger-sync\n" + ONPREM.format(port=8243) + """functions:
  sync-entry:
    handler: app.sync.handle
    events:
      - queue:
          name: ledger-entries
          batch_size: 10
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    for record in event.records:
        result = BatchResult()
        entry = record.json()
        if entry.get("amount") is None:
            result.fail(record)
    return result
""",
          "requirements.txt": ""}),
      user="sync-entry: only the last bad message gets retried, earlier bad ones vanish",
      steps=[
          S("read_file", path="app/sync.py"),
          S("invoke_local", function="sync-entry", type="queue", data=[{"id": 1}, {"id": 2, "amount": 5}, {"id": 3}]),
          S("propose_plan", steps=["Create the `BatchResult` once, before the loop"]),
          S("write_file", path="app/sync.py", content=FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        entry = record.json()
        if entry.get("amount") is None:
            result.fail(record)
    return result
"""),
          S("invoke_local", function="sync-entry", type="queue", data=[{"id": 1}, {"id": 2, "amount": 5}, {"id": 3}]),
          S("validate"),
      ],
      final="""A new `BatchResult` was created for every message, so only the last one survived the loop. Now it is created once, before the loop [docs/handlers.md#batchresult].

- invoke (ids 1, 2, 3; 1 and 3 have no amount): `{"batchItemFailures": [{"itemIdentifier": "local-0"}, {"itemIdentifier": "local-2"}]}` (before: only `local-2`).
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 167 aws http, str + int on a path param
    B(167, provider="aws", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: comics
provider:
  name: aws
  region: us-west-2
functions:
  issue:
    handler: app.comics.issue
    events:
      - http: GET /issues/{n}
""",
          "app/__init__.py": "",
          "app/comics.py": FUTURE + """
def issue(event, ctx):
    n = event.http.path_params["n"]
    return {"issue": n, "next": f"/issues/{n + 1}"}
""",
          "requirements.txt": ""}),
      user="/issues/7 crash 'can only concatenate str (not \"int\") to str'. i want next link /issues/8",
      steps=[
          S("read_file", path="app/comics.py"),
          S("invoke_local", function="issue", path="/issues/7"),
          S("propose_plan", steps=["Convert the path parameter with `int()` (404 when it isn't a number)",
                                   "GET /issues/7 locally and validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/comics.py", content=FUTURE + """from py_serverless_kit import NotFound


def issue(event, ctx):
    raw = event.http.path_params["n"]
    if not raw.isdigit():
        raise NotFound("no such issue")
    n = int(raw)
    return {"issue": n, "next": f"/issues/{n + 1}"}
"""),
          S("invoke_local", function="issue", path="/issues/7"),
          S("validate"),
      ],
      final="""Path parameters are always **strings** (`"7"`) [docs/handlers.md#httprequest], and `"7" + 1` isn't allowed. Now the handler converts with `int()`; something like `/issues/abc` gives 404.

- GET /issues/7: 200, `{"issue": 7, "next": "/issues/8"}`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 168 gcp queue, off-by-one index
    B(168, provider="gcp", stage="dev", mode="auto", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": "service: tiles\n" + GCP.format(region="europe-west1") + """functions:
  render-tile:
    handler: app.tiles.handle
    events:
      - queue: tile-jobs
""",
          "app/__init__.py": "",
          "app/tiles.py": FUTURE + """
def handle(event, ctx):
    rendered = []
    for i in range(len(event.records)):
        job = event.records[i + 1].json()
        rendered.append(f"{job['z']}/{job['x']}/{job['y']}")
    return {"rendered": rendered}
""",
          "requirements.txt": ""}),
      user="render-tile IndexError: list index out of range, any batch size",
      steps=[
          S("read_file", path="app/tiles.py"),
          S("invoke_local", function="render-tile", type="queue", data=[{"z": 3, "x": 1, "y": 2}, {"z": 3, "x": 2, "y": 2}]),
          S("propose_plan", steps=["Iterate the records directly (`for record in event.records`) instead of `records[i + 1]`"]),
          S("write_file", path="app/tiles.py", content=FUTURE + """
def handle(event, ctx):
    rendered = []
    for record in event.records:
        job = record.json()
        rendered.append(f"{job['z']}/{job['x']}/{job['y']}")
    return {"rendered": rendered}
"""),
          S("invoke_local", function="render-tile", type="queue", data=[{"z": 3, "x": 1, "y": 2}, {"z": 3, "x": 2, "y": 2}]),
          S("validate"),
      ],
      final="""Off by one: `records[i + 1]` skips the first message and runs past the end on the last. Now it loops `for record in event.records` [docs/handlers.md#event].

- invoke (2 jobs): `{"rendered": ["3/1/2", "3/2/2"]}`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 169 onprem schedule, weekday() compared with a name
    B(169, provider="onprem", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": "service: payroll\n" + ONPREM.format(port=8244) + """functions:
  payroll-check:
    handler: app.payroll.check
    events:
      - schedule: "0 7 * * *"
""",
          "app/__init__.py": "",
          "app/payroll.py": FUTURE + """
def check(event, ctx):
    if event.time.weekday() == "Mon":
        ctx.logger.info("weekly payroll check")
        return {"checked": True}
    return {"checked": False}
""",
          "requirements.txt": ""}),
      user="the payroll check should only do the work on Mondays. It never does it, even on Monday it says checked false. How do I test a Monday?",
      steps=[
          S("read_file", path="app/payroll.py"),
          S("invoke_local", function="payroll-check", type="schedule"),
          S("propose_plan", steps=["`weekday()` returns a number (Monday is 0): compare with `0`",
                                   "Run payroll-check as a schedule event and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/payroll.py", content=FUTURE + """MONDAY = 0


def check(event, ctx):
    if event.time.weekday() == MONDAY:
        ctx.logger.info("weekly payroll check")
        return {"checked": True}
    return {"checked": False, "weekday": event.time.weekday()}
"""),
          S("invoke_local", function="payroll-check", type="schedule"),
          S("validate"),
      ],
      final="""`weekday()` returns a **number**: Monday is 0 and Sunday is 6. A number is never equal to the text `"Mon"`, so the check was always false. Now it compares with `MONDAY = 0`. `event.time` is in UTC [docs/handlers.md#event].

- Run today (a Sunday): `{"checked": false, "weekday": 6}`, as expected.
- validate (onprem, prod): valid.

Simpler: let the schedule decide. With `schedule: "0 7 * * 1"` it only runs on Mondays, and the check isn't needed."""),

    # ------------------------------------------------------------------ 170 azure storage, resource name vs native_name
    B(170, provider="azure", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: archive
provider:
  name: azure
  region: westeurope
resources:
  uploads:
    type: storage
    external: true
    name: acmeuploads
functions:
  on-file:
    handler: app.archive.on_file
    events:
      - storage: {resource: uploads}
""",
          "app/__init__.py": "",
          "app/archive.py": FUTURE + """from py_serverless_kit import resource


def on_file(event, ctx):
    uploads = resource("uploads")
    mine = [r.key for r in event.records if r.bucket == uploads.name]
    return {"archived": mine}
""",
          "requirements.txt": ""}),
      user="on-file should archive files that arrive in the uploads resource (container acmeuploads) and ignore other containers. It archives nothing. A test event from bucket acmeuploads returns an empty list. Please fix the comparison and test with that bucket.",
      steps=[
          S("read_file", path="app/archive.py"),
          S("invoke_local", function="on-file", type="storage", data=[{"bucket": "acmeuploads", "key": "q3.pdf"}]),
          S("search_docs", query="resource name native name",
            docs=[D("docs/resources.md", "runtime-api", end="jobs.external")]),
          S("propose_plan", steps=["Compare `record.bucket` with `uploads.native_name` (the real container), not `uploads.name` (the key)",
                                   "Invoke with bucket acmeuploads and validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/archive.py", content=FUTURE + """from py_serverless_kit import resource


def on_file(event, ctx):
    uploads = resource("uploads")
    mine = [r.key for r in event.records if r.bucket == uploads.native_name]
    return {"archived": mine}
"""),
          S("invoke_local", function="on-file", type="storage", data=[{"bucket": "acmeuploads", "key": "q3.pdf"}]),
          S("validate"),
      ],
      final="""`Resource.name` is the **key** from pskit.yml (`uploads`); the real container name is `native_name` (`acmeuploads`) [docs/resources.md#runtime-api]. The handler compared the bucket with the key, which never matched. It now uses `uploads.native_name`.

- Before: `{"archived": []}`.
- After: `{"archived": ["q3.pdf"]}`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 171 onprem http, STAGE env var
    B(171, provider="onprem", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#environment-variables", "docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": "service: banner\n" + ONPREM.format(port=8245) + """functions:
  banner:
    handler: app.banner.get_banner
    events:
      - http: GET /banner
""",
          "app/__init__.py": "",
          "app/banner.py": FUTURE + """import os


def get_banner(event, ctx):
    stage = os.environ["STAGE"]
    text = "" if stage == "prod" else f"{stage.upper()} ENVIRONMENT"
    return {"banner": text}
""",
          "requirements.txt": ""}),
      user="I want a banner that says STAGING on the staging site. I read os.environ['STAGE'] and get KeyError. Where does pskit put the stage?",
      steps=[
          S("read_file", path="app/banner.py"),
          S("invoke_local", function="banner", path="/banner"),
          S("search_docs", query="stage environment variable",
            docs=[D("docs/handlers.md", "environment-variables", end="| `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_REGION` | deployment identity |")]),
          S("propose_plan", steps=["Use `ctx.stage` (pskit also sets `PSKIT_STAGE`) instead of the unset `STAGE`",
                                   "GET /banner locally (stage staging) and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/banner.py", content=FUTURE + """
def get_banner(event, ctx):
    stage = ctx.stage
    text = "" if stage == "prod" else f"{stage.upper()} ENVIRONMENT"
    return {"banner": text}
"""),
          S("invoke_local", function="banner", path="/banner"),
          S("validate"),
      ],
      final="""pskit sets the stage as `PSKIT_STAGE`, not `STAGE` [docs/handlers.md#environment-variables], and gives it to you as `ctx.stage` [docs/handlers.md#context]. The handler now uses `ctx.stage`.

- GET /banner with stage staging: 200, `{"banner": "STAGING ENVIRONMENT"}`.
- validate (onprem, staging): valid. On prod the banner is empty."""),

    # ------------------------------------------------------------------ 172 aws queue, forgot to return the BatchResult
    B(172, provider="aws", stage="prod", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: emails
provider:
  name: aws
  region: eu-central-1
functions:
  send-email:
    handler: app.emails.handle
    events:
      - queue:
          name: outbound-email
          batch_size: 10
          dead_letter: outbound-email-dlq
""",
          "app/__init__.py": "",
          "app/emails.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json()
        if "@" not in msg.get("to", ""):
            result.fail(record)
""",
          "requirements.txt": ""}),
      user="send-email: bad addresses never reach the DLQ. invoke prints null",
      steps=[
          S("read_file", path="app/emails.py"),
          S("invoke_local", function="send-email", type="queue", data=[{"to": "ok@example.com"}, {"to": "nobody"}]),
          S("propose_plan", steps=["`return result` at the end of the handler"]),
          S("write_file", path="app/emails.py", content=FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json()
        if "@" not in msg.get("to", ""):
            result.fail(record)
    return result
"""),
          S("invoke_local", function="send-email", type="queue", data=[{"to": "ok@example.com"}, {"to": "nobody"}]),
          S("validate"),
      ],
      final="""The `BatchResult` was built but never returned, so the handler returned `None` and SQS treated the whole batch as done. Added `return result` [docs/handlers.md#batchresult].

- invoke: `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}` (before: `null`).
- validate (aws, prod): valid. The bad message is retried and goes to `outbound-email-dlq` after `max_receive` (default 5)."""),

    # ------------------------------------------------------------------ 173 gcp http, builtin id in an f-string
    B(173, provider="gcp", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": "service: tasks-api\n" + GCP.format(region="us-east1") + """functions:
  create-task:
    handler: app.tasks.create
    events:
      - http: POST /tasks
""",
          "app/__init__.py": "",
          "app/tasks.py": FUTURE + """from py_serverless_kit import Response

NEXT_ID = 41


def create(event, ctx):
    data = event.http.json()
    task_id = NEXT_ID + 1
    body = {"id": task_id, "title": data["title"]}
    return Response.json(body, 201, {"location": f"/tasks/{id}"})
""",
          "requirements.txt": ""}),
      user="POST /tasks returns 201 and the right body, but the Location header is '/tasks/<built-in function id>' instead of '/tasks/42'. Clients follow that header, so it must point at the new task. Please fix and show me the headers.",
      steps=[
          S("read_file", path="app/tasks.py"),
          S("invoke_local", function="create-task", method="POST", path="/tasks", data={"title": "Write docs"}),
          S("propose_plan", steps=["Use `task_id` in the Location f-string; `id` is Python's built-in function",
                                   "POST /tasks locally and validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tasks.py", content=FUTURE + """from py_serverless_kit import Response

NEXT_ID = 41


def create(event, ctx):
    data = event.http.json()
    task_id = NEXT_ID + 1
    body = {"id": task_id, "title": data["title"]}
    return Response.json(body, 201, {"location": f"/tasks/{task_id}"})
"""),
          S("invoke_local", function="create-task", method="POST", path="/tasks", data={"title": "Write docs"}),
          S("validate"),
      ],
      final="""Typo: the f-string used `{id}`, which is Python's **built-in** `id` function, not your `task_id`. Fixed to `f"/tasks/{task_id}"`.

- POST /tasks: 201, headers `content-type: application/json` and `location: /tasks/42`, body `{"id": 42, "title": "Write docs"}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 174 onprem workflow, result_path to keep the input
    B(174, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#data-flow"],
      project=dict(files={
          "pskit.yml": "service: loans\n" + ONPREM.format(port=8246) + """functions:
  credit-check:
    handler: app.loans.credit_check
  offer:
    handler: app.loans.offer
workflows:
  loan:
    start_at: Credit
    states:
      Credit: {type: task, function: credit-check, next: Offer}
      Offer: {type: task, function: offer, end: true}
""",
          "app/__init__.py": "",
          "app/loans.py": FUTURE + """
def credit_check(event, ctx):
    return {"score": 710}


def offer(event, ctx):
    data = event.data
    rate = 4.9 if data["credit"]["score"] > 700 else 7.9
    return {"customer": data["customer"], "amount": data["amount"], "rate": rate}
""",
          "requirements.txt": ""}),
      user="loan workflow: Offer step KeyError 'customer'. the input has customer and amount, where they go?",
      steps=[
          S("get_project"),
          S("invoke_local", function="offer", type="workflow", data={"score": 710}),
          S("search_docs", query="result_path keep input",
            docs=[D("docs/workflows.md", "data-flow", start="- `result_path`")]),
          S("propose_plan", steps=["Set `result_path: $.credit` on the Credit state, so its result is stored next to the input instead of replacing it",
                                   "Invoke offer with the merged data and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.loan.states.Credit.result_path", value="$.credit"),
          S("invoke_local", function="offer", type="workflow", data={"customer": "c-7", "amount": 5000, "credit": {"score": 710}}),
      ],
      final="""They were replaced. Without `result_path`, a task's result **replaces** the whole state data (`$` is the default) [docs/workflows.md#data-flow]. So after Credit, the data was only `{"score": 710}`. I set `result_path: $.credit` on the Credit state (`workflows.loan.states.Credit.result_path`), so the score is added under `credit` and the input is kept.

- validate (onprem): valid.
- offer with `{"customer": "c-7", "amount": 5000, "credit": {"score": 710}}`: `{"customer": "c-7", "amount": 5000, "rate": 4.9}`."""),

    # ------------------------------------------------------------------ 175 azure http, HTML returned as a dict
    B(175, provider="azure", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: status-page
provider:
  name: azure
  region: eastus
functions:
  status:
    handler: app.status.page
    events:
      - http: GET /status
""",
          "app/__init__.py": "",
          "app/status.py": FUTURE + """
def page(event, ctx):
    html = "<h1>All systems normal</h1>"
    return {"html": html}
""",
          "requirements.txt": ""}),
      user="my status page shows {\"html\": \"<h1>All systems normal</h1>\"} in the browser instead of the heading. How do I send a real web page?",
      steps=[
          S("read_file", path="app/status.py"),
          S("invoke_local", function="status", path="/status"),
          S("search_docs", query="return html response",
            docs=[D("docs/handlers.md", "returning-a-response", start="```python", end="Response.html")]),
          S("propose_plan", steps=["Return `Response.html(html)` so the content type is text/html",
                                   "GET /status locally and validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/status.py", content=FUTURE + """from py_serverless_kit import Response


def page(event, ctx):
    html = "<h1>All systems normal</h1>"
    return Response.html(html)
"""),
          S("invoke_local", function="status", path="/status"),
          S("validate"),
      ],
      final="""A dict is always sent as JSON, so the browser showed the JSON text. For a web page, return `Response.html(...)` [docs/handlers.md#returning-a-response]. It sets `content-type: text/html; charset=utf-8`.

- GET /status: 200, `text/html; charset=utf-8`, body `<h1>All systems normal</h1>`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 176 onprem smtp, header name case
    B(176, provider="onprem", stage="prod", mode="auto", page="Code", persona="pasted_error",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": "service: priority-mail\n" + ONPREM.format(port=8247) + """resources:
  support-mail:
    type: smtp
    external: true
    connection: {host: 192.0.2.40, port: 25, domains: support.example.com}
functions:
  triage-mail:
    handler: app.triage.handle
    events:
      - smtp: support-mail
""",
          "app/__init__.py": "",
          "app/triage.py": FUTURE + """
def handle(event, ctx):
    mail = event.data
    subject = mail["headers"]["Subject"]
    urgent = "urgent" in subject.lower()
    return {"urgent": urgent}
""",
          "requirements.txt": ""}),
      user="""KeyError: 'Subject'
triage-mail, every mail""",
      steps=[
          S("read_file", path="app/triage.py"),
          S("invoke_local", function="triage-mail", type="smtp", data={"from": "a@example.org", "to": "help@support.example.com", "subject": "URGENT: login broken", "text": "help"}),
          S("propose_plan", steps=["Use `mail[\"subject\"]` (or lower-case header keys: `mail[\"headers\"][\"subject\"]`)"]),
          S("write_file", path="app/triage.py", content=FUTURE + """
def handle(event, ctx):
    mail = event.data
    subject = mail["subject"] or ""
    urgent = "urgent" in subject.lower()
    return {"urgent": urgent}
"""),
          S("invoke_local", function="triage-mail", type="smtp", data={"from": "a@example.org", "to": "help@support.example.com", "subject": "URGENT: login broken", "text": "help"}),
          S("validate"),
      ],
      final="""Keys in `mail["headers"]` are **lower case** (`subject`, not `Subject`). The subject also has its own field, `mail["subject"]` [docs/smtp/README.md#what-the-handler-receives]. Switched to that.

- test mail "URGENT: login broken": `{"urgent": true}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 177 aws http, decorator drops ctx
    B(177, provider="aws", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: secure-api
provider:
  name: aws
  region: eu-west-1
functions:
  profile:
    handler: app.api.profile
    events:
      - http: GET /profile
""",
          "app/__init__.py": "",
          "app/auth.py": FUTURE + """from functools import wraps


def logged(fn):
    @wraps(fn)
    def wrapper(event):
        print("request", event.http.path)
        return fn(event)
    return wrapper
""",
          "app/api.py": FUTURE + """from app.auth import logged


@logged
def profile(event, ctx):
    return {"user": "demo", "function": ctx.function}
""",
          "requirements.txt": ""}),
      user="I wrote a small @logged decorator in app/auth.py for all handlers. Since I put it on profile, GET /profile returns 500 with TypeError: profile() takes 1 positional argument but 2 were given. The decorator must keep working for handlers with (event, ctx). Please fix the decorator, not the handlers.",
      steps=[
          S("read_file", path="app/auth.py"),
          S("invoke_local", function="profile", path="/profile"),
          S("search_docs", query="handler arguments one or two",
            docs=[D("docs/handlers.md", "handler-signatures", end="async def handler")]),
          S("propose_plan", steps=["Make the wrapper take and pass on `(event, ctx)`, so pskit calls it with both",
                                   "GET /profile locally and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/auth.py", content=FUTURE + """from functools import wraps


def logged(fn):
    @wraps(fn)
    def wrapper(event, ctx):
        ctx.logger.info("request", extra={"path": event.http.path})
        return fn(event, ctx)
    return wrapper
"""),
          S("invoke_local", function="profile", path="/profile"),
          S("validate"),
      ],
      final="""pskit calls a handler as `handler(event, ctx)` or `handler(event)`, depending on its signature [docs/handlers.md#handler-signatures]. Because of `@wraps`, the signature it sees is the one of `profile`: `(event, ctx)`. So it passed two arguments, but the wrapper (which is named `profile` too, thanks to `@wraps`) only accepted `event`. The wrapper now takes `(event, ctx)` and passes both on. I also switched its `print` to `ctx.logger`, so the line is structured like your other logs.

- GET /profile: logs "request", 200 `{"user": "demo", "function": "profile"}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 178 gcp schedule, dict changed during iteration
    B(178, provider="gcp", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": "service: flags\n" + GCP.format(region="us-central1") + """functions:
  expire-flags:
    handler: app.flags.expire
    events:
      - schedule:
          rate: 1 hour
          input:
            flags: {new-ui: expired, dark-mode: active, beta-api: expired}
""",
          "app/__init__.py": "",
          "app/flags.py": FUTURE + """
def expire(event, ctx):
    flags = dict(event.data["flags"])
    for name, state in flags.items():
        if state == "expired":
            del flags[name]
    return {"active": flags}
""",
          "requirements.txt": ""}),
      user="""RuntimeError: dictionary changed size during iteration
expire-flags""",
      steps=[
          S("read_file", path="app/flags.py"),
          S("invoke_local", function="expire-flags", type="schedule"),
          S("propose_plan", steps=["Build a new dict of the active flags instead of deleting while looping",
                                   "Run expire-flags as a schedule event and validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/flags.py", content=FUTURE + """
def expire(event, ctx):
    flags = event.data["flags"]
    active = {name: state for name, state in flags.items() if state != "expired"}
    return {"active": active}
"""),
          S("invoke_local", function="expire-flags", type="schedule"),
          S("validate"),
      ],
      final="""You can't delete keys from a dict while looping over it. The handler now builds a new dict with only the flags that aren't expired.

- schedule run: `{"active": {"dark-mode": "active"}}`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 179 onprem http, comparing path with the route template
    B(179, provider="onprem", stage="staging", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": "service: users-api\n" + ONPREM.format(port=8248) + """functions:
  users:
    handler: app.users.handle
    events:
      - http: GET /users
      - http: GET /users/{id}
""",
          "app/__init__.py": "",
          "app/users.py": FUTURE + """from py_serverless_kit import NotFound

USERS = {"1": "ada", "2": "linus"}


def handle(event, ctx):
    if event.http.path == "/users":
        return {"users": sorted(USERS.values())}
    if event.http.path == "/users/{id}":
        return {"user": USERS.get(event.http.path_params["id"])}
    raise NotFound()
""",
          "requirements.txt": ""}),
      user="""GET /users/1 -> 404 {"error": "Not Found", "status": 404}
/users works""",
      steps=[
          S("read_file", path="app/users.py"),
          S("invoke_local", function="users", path="/users/1"),
          S("search_docs", query="route template path",
            docs=[D("docs/handlers.md", "httprequest", start="| `path` |", end="| `route` |")]),
          S("propose_plan", steps=["Branch on `event.http.route` (the template `/users/{id}`), not `event.http.path` (`/users/1`)",
                                   "GET /users/1 locally and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/users.py", content=FUTURE + """from py_serverless_kit import NotFound

USERS = {"1": "ada", "2": "linus"}


def handle(event, ctx):
    if event.http.route == "/users":
        return {"users": sorted(USERS.values())}
    if event.http.route == "/users/{id}":
        user = USERS.get(event.http.path_params["id"])
        if user is None:
            raise NotFound("no such user")
        return {"user": user}
    raise NotFound()
"""),
          S("invoke_local", function="users", path="/users/1"),
          S("validate"),
      ],
      final="""`event.http.path` is the real path (`/users/1`), so it never equals the template `/users/{id}`. The matched template is in `event.http.route` [docs/handlers.md#httprequest]. The handler now branches on `route`, and an unknown id is a 404 too.

- GET /users/1: 200, `{"user": "ada"}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 180 azure queue, str + int in a label
    B(180, provider="azure", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: kitchen
provider:
  name: azure
  region: centralus
functions:
  ticket:
    handler: app.kitchen.ticket
    events:
      - queue: kitchen-orders
""",
          "app/__init__.py": "",
          "app/kitchen.py": FUTURE + """
def ticket(event, ctx):
    tickets = []
    for record in event.records:
        order = record.json()
        tickets.append("order-" + order["id"])
    return {"tickets": tickets}
""",
          "requirements.txt": ""}),
      user="kitchen ticket error can only concatenate str (not \"int\") to str. the id is number 12",
      steps=[
          S("read_file", path="app/kitchen.py"),
          S("invoke_local", function="ticket", type="queue", data=[{"id": 12}, {"id": 13}]),
          S("propose_plan", steps=["Build the label with an f-string: `f\"order-{order['id']}\"`",
                                   "Invoke with ids 12 and 13; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/kitchen.py", content=FUTURE + """
def ticket(event, ctx):
    tickets = []
    for record in event.records:
        order = record.json()
        tickets.append(f"order-{order['id']}")
    return {"tickets": tickets}
"""),
          S("invoke_local", function="ticket", type="queue", data=[{"id": 12}, {"id": 13}]),
          S("validate"),
      ],
      final="""`record.json()` keeps JSON types, so `id` is the number `12` [docs/handlers.md#record], and `"order-" + 12` mixes text and a number. An f-string converts it: `f"order-{order['id']}"`.

- invoke (12, 13): `{"tickets": ["order-12", "order-13"]}`.
- validate (azure): valid."""),
]
