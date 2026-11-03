"""Category B (build / add), batch 33 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 641
    B(641, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/resources.md#runtime-api", "docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: table-booking
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, table-booking-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="people send me a table reservation from my restaurant website and i want to keep each one as a file in google cloud. how?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add a managed bucket resource `reservations` (name table-booking-reservations-2207)",
                                   "Write app/booking.py: POST /reservations checks name/date/people, saves reservations/<date>/<id>.json with google-cloud-storage",
                                   "Skip the real upload when running locally (ctx.provider == \"local\") so the test touches nothing",
                                   "Validate for gcp, try one reservation locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources",
            value={"reservations": {"type": "storage", "name": "table-booking-reservations-2207"}}),
          S("write_file", path="requirements.txt", content="google-cloud-storage>=2.10\n"),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/booking.py", content=FUTURE + """import json
import uuid

from py_serverless_kit import BadRequest, resource


def _upload(bucket: str, key: str, data: dict) -> None:
    from google.cloud import storage  # imported only in the cloud

    storage.Client().bucket(bucket).blob(key).upload_from_string(json.dumps(data), content_type="application/json")


def reserve(event, ctx):
    body = event.http.json(default={}) or {}
    missing = [f for f in ("name", "date", "people") if not body.get(f)]
    if missing:
        raise BadRequest("missing: " + ", ".join(missing))
    rid = uuid.uuid4().hex[:8]
    key = f"reservations/{body['date']}/{rid}.json"
    bucket = resource("reservations").native_name
    if ctx.provider == "local":
        ctx.logger.info("local run, not uploading", extra={"bucket": bucket, "key": key})
    else:
        _upload(bucket, key, body)
    return {"id": rid, "saved_as": key}, 201
"""),
          S("set_config", path="functions.reserve",
            value={"handler": "app.booking.reserve", "events": [{"http": "POST /reservations"}]}),
          S("invoke_local", function="reserve", method="POST", path="/reservations",
            data={"name": "Maria", "date": "2026-11-14", "people": 4}),
      ],
      final="""Your reservation box is set up:

- A Cloud Storage **bucket** `table-booking-reservations-2207`, created by pskit.
- **POST /reservations** with `{"name", "date", "people"}` saves each reservation as its own file, `reservations/<date>/<id>.json`, and answers 201 with the id. A missing field → 400.
- The function finds the bucket with `resource("reservations")` [docs/resources.md#runtime-api]. On your computer it only logs what it would save (`ctx.provider` is `local` there [docs/handlers.md#event]), so testing doesn't write to the cloud.

Checks: `pskit validate` (gcp) valid; a test booking for Maria (4 people) → 201, `saved_as: reservations/2026-11-14/<id>.json`.

Try it again on **Test** > **▶ Run locally**, then **Deploy** or `pskit deploy -s dev`. If your website is on another domain, ask me to add CORS."""),

    # ------------------------------------------------------------------ 642
    B(642, provider="azure", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: booking-api
provider:
  name: azure
  region: westeurope
functions:
  slots:
    handler: app.slots.handler
    events:
    - http: GET /slots
    - http: POST /slots
""",
          "app/__init__.py": "",
          "app/slots.py": FUTURE + """

def handler(event, ctx):
    if event.http.method == "POST":
        return {"booked": True}, 201
    return {"slots": ["09:00", "10:00"]}
""",
          "requirements.txt": ""}),
      user="""CORS for `slots`, both routes:
- only https://book.example.com and https://admin.example.com
- methods GET, POST only
- allow request headers Content-Type and X-Api-Version
- browsers cache the preflight for 1 hour""",
      steps=[
          S("get_project"),
          S("search_docs", query="cors origins methods headers max_age",
            docs=[D("docs/events.md", "http", start="**CORS**", end="AWS additionally configures CORS on the HTTP API.")]),
          S("propose_plan", steps=["Both events become mappings with the same cors block: origins (2), methods [GET, POST], headers [Content-Type, X-Api-Version], max_age 3600",
                                   "Validate azure staging, invoke GET /slots"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.slots.events",
            value=[{"http": {"path": "/slots", "method": method,
                             "cors": {"origins": ["https://book.example.com", "https://admin.example.com"],
                                      "methods": ["GET", "POST"], "headers": ["Content-Type", "X-Api-Version"],
                                      "max_age": 3600}}} for method in ("GET", "POST")]),
          S("invoke_local", function="slots", method="GET", path="/slots"),
      ],
      final="""```yaml
functions:
  slots:
    handler: app.slots.handler
    events:
      - http:
          path: /slots
          method: GET
          cors: &cors
            origins: [https://book.example.com, https://admin.example.com]
            methods: [GET, POST]
            headers: [Content-Type, X-Api-Version]
            max_age: 3600
      - http: {path: /slots, method: POST, cors: *cors}
```
(in your file the block is written out on both events; `&cors` is only shorthand here)

- `headers` replaces the default list, so `Authorization` / `X-Requested-With` are no longer allowed [docs/events.md#http]. Say if a client still sends them.
- `max_age: 3600` = preflight cached for one hour. The runtime answers `OPTIONS` itself with 204.
- `pskit validate` (azure, staging): valid; GET /slots → 200 `{"slots": ["09:00", "10:00"]}`.

Check the headers from a browser on book.example.com after **Deploy** (`pskit deploy -s staging`): local runs without an `Origin` get no CORS headers."""),

    # ------------------------------------------------------------------ 643
    B(643, provider="aws", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: aws
  region: eu-west-1
functions:
  charge:
    handler: app.billing.charge
    events:
    - queue: charges
  receipts:
    handler: app.billing.receipts
    events:
    - queue:
        name: receipts
        batch_size: 50
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """

def charge(event, ctx):
    return {"charged": len(event.records)}


def receipts(event, ctx):
    return {"sent": len(event.records)}
""",
          "requirements.txt": ""}),
      user="charge: one msg per invocation (batch 1), timeout 60, 512mb. receipts untouched",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.charge.events.0 -> queue {name: charges, batch_size: 1}",
                                   "functions.charge.timeout 60, memory 512",
                                   "Validate aws prod, invoke one message"]),
          S("set_config", path="functions.charge.events.0", value={"queue": {"name": "charges", "batch_size": 1}}),
          S("set_config", path="functions.charge.timeout", value=60),
          S("set_config", path="functions.charge.memory", value=512),
          S("invoke_local", function="charge", type="queue", data=[{"charge_id": "ch-1"}]),
      ],
      final="""```yaml
functions:
  charge:
    handler: app.billing.charge
    timeout: 60
    memory: 512
    events:
      - queue: {name: charges, batch_size: 1}
```

- `batch_size: 1` → one SQS message per invocation [docs/events.md#queue]. Visibility timeout follows the default `max(30, 6 x timeout)` = 360 s.
- `receipts` unchanged.
- `pskit validate` (aws, prod): valid; one message → `{"charged": 1}`.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 644
    B(644, provider="gcp", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#batchresult", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: label-printer
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, label-printer-dev}
functions:
  print-label:
    handler: app.labels.print_label
    events:
    - queue: label-jobs
""",
          "app/__init__.py": "",
          "app/labels.py": FUTURE + """

def print_label(event, ctx):
    for record in event.records:
        job = record.json()
        ctx.logger.info("printing", extra={"order": job["order"]})
    return None
""",
          "requirements.txt": ""}),
      user="On Lambda this worker returned batchItemFailures so only the bad SQS messages came back. A job without `order` currently crashes the whole thing. Make it report bad messages the pskit way. Does partial retry work on GCP too?",
      steps=[
          S("get_project"),
          S("search_docs", query="BatchResult partial failure gcp",
            docs=[D("docs/handlers.md", "batchresult", start="| Provider | Behaviour |", end="redelivery is normal on every cloud.")]),
          S("propose_plan", steps=["app/labels.py: BatchResult; jobs without `order` -> result.fail(record), others printed",
                                   "Validate for gcp, invoke with one good and one bad job"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/labels.py", content=FUTURE + """from py_serverless_kit import BatchResult


def print_label(event, ctx):
    result = BatchResult()
    for record in event.records:
        job = record.json(default={}) or {}
        if "order" not in job:
            ctx.logger.warning("job without order", extra={"id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("printing", extra={"order": job["order"]})
    return result
"""),
          S("validate"),
          S("invoke_local", function="print-label", type="queue", data=[{"order": "A-100"}, {"copies": 2}]),
      ],
      final="""The worker now returns a `BatchResult` and marks jobs without `order` as failed instead of crashing.

On GCP partial retry does **not** exist: a "queue" is a Pub/Sub push delivery, so any failure raises `BatchFailure` and the whole delivery is retried [docs/handlers.md#batchresult] [docs/events.md#queue]. Same code, different retry: on AWS only the bad message comes back. Keep the handler idempotent (printing a label twice is the risk here).

- `pskit validate` (gcp): valid.
- Local run with one good and one bad job: `printing` for A-100, a warning for the other, `{"batchItemFailures": [...]}` with the bad message id.

A job that can never succeed will keep coming back on GCP, so for bad input you may prefer to log and **skip** it rather than `fail()` it. Test again: `pskit invoke -f print-label -t queue -d '[{"order": "A-1"}]'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 645
    B(645, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: shop-events
provider:
  name: azure
  region: northeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="Every placed order is published to a Service Bus topic `order-placed` that pskit should create. Two functions must each receive every message: `email-receipt` (logs the customer email) and `update-stock` (logs the number of lines). Both return a small summary.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/orders.py with email_receipt and update_stock",
                                   "Add both functions with `- topic: order-placed` (Azure: one subscription per function, so both get every message)",
                                   "Validate for azure, invoke both with one order"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/orders.py", content=FUTURE + """

def email_receipt(event, ctx):
    emails = [r.json().get("email") for r in event.records]
    for email in emails:
        ctx.logger.info("receipt", extra={"email": email})
    return {"receipts": len(emails)}


def update_stock(event, ctx):
    lines = sum(len(r.json().get("lines", [])) for r in event.records)
    ctx.logger.info("stock update", extra={"lines": lines})
    return {"lines": lines}
"""),
          S("set_config", path="functions.email-receipt",
            value={"handler": "app.orders.email_receipt", "events": [{"topic": "order-placed"}]}),
          S("set_config", path="functions.update-stock",
            value={"handler": "app.orders.update_stock", "events": [{"topic": "order-placed"}]}),
          S("invoke_local", function="email-receipt", type="topic",
            data={"email": "li@example.com", "lines": [{"sku": "a"}, {"sku": "b"}]}),
          S("invoke_local", function="update-stock", type="topic",
            data={"email": "li@example.com", "lines": [{"sku": "a"}, {"sku": "b"}]}),
      ],
      final="""```yaml
functions:
  email-receipt:
    handler: app.orders.email_receipt
    events: [{topic: order-placed}]
  update-stock:
    handler: app.orders.update_stock
    events: [{topic: order-placed}]
```

- pskit creates the Service Bus namespace and topic, and **one subscription per function** [docs/providers.md#azure-azure-functions], so both functions get every order.
- `pskit validate` (azure): valid.
- One test order: `email-receipt` → `{"receipts": 1}`, `update-stock` → `{"lines": 2}`.

Topic `filter` isn't applied on Azure [docs/events.md#topic], so if one subscriber should skip some orders, check it in its handler. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 646
    B(646, provider="aws", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#aws-iam", "docs/resources.md#fields"],
      project=dict(files={
          "pskit.yml": """service: brochure
provider:
  name: aws
  region: eu-west-1
functions:
  render:
    handler: app.render.render
    events:
    - http: POST /brochures
  cleanup:
    handler: app.render.cleanup
    events:
    - schedule: 1 day
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + """

def render(event, ctx):
    return {"rendered": True}


def cleanup(event, ctx):
    return {"removed": 0}
""",
          "requirements.txt": ""}),
      user="I'm on the Resources page. The marketing team's bucket `acme-shared-assets` already exists (not ours, don't create or delete it). `render` reads logos from it; `cleanup` must not get access. Ideally read-only.",
      steps=[
          S("get_project"),
          S("search_docs", query="aws resource iam policy storage actions",
            docs=[D("docs/resources.md", "aws-iam", end="Narrow the grant by listing `functions:` on the resource.")]),
          S("propose_plan", steps=["resources.brand-assets: type storage, external true, name acme-shared-assets, functions [render]",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources",
            value={"brand-assets": {"type": "storage", "external": True, "name": "acme-shared-assets",
                                    "functions": ["render"]}}),
      ],
      final="""```yaml
resources:
  brand-assets:
    type: storage
    external: true
    name: acme-shared-assets
    functions: [render]
```

- `external: true`: pskit never creates, changes or destroys the bucket [docs/resources.md#fields].
- Only `render` gets the binding and IAM access; `cleanup` gets nothing.
- `pskit validate` (aws): valid.

About read-only: the `pskit-resources` policy pskit adds for a storage resource includes `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` and `s3:ListBucket` [docs/resources.md#aws-iam]; there is no read-only switch. If write access isn't acceptable, let the marketing team's bucket policy allow only reads for the role, or use your own `iam.role` with just `s3:GetObject`.

Next time: **Resources > + Add resource**. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 647
    B(647, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: theme-pref
provider:
  name: gcp
  region: us-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, theme-pref-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="want dark mode remember. GET /theme read cookie `theme` (default light), POST /theme {theme: dark|light} save it in cookie 1 year",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/theme.py: GET reads event.http.cookies, POST validates and sets the cookie (max_age 1 year)",
                                   "Add function theme with GET /theme and POST /theme",
                                   "Validate for gcp, invoke GET and POST"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/theme.py", content=FUTURE + """from py_serverless_kit import BadRequest, Response

ONE_YEAR = 365 * 24 * 3600


def theme(event, ctx):
    req = event.http
    if req.method == "GET":
        return {"theme": req.cookies.get("theme", "light")}
    choice = (req.json(default={}) or {}).get("theme")
    if choice not in ("dark", "light"):
        raise BadRequest("theme must be dark or light")
    return Response.json({"theme": choice}).set_cookie(
        "theme", choice, max_age=ONE_YEAR, path="/", http_only=False, secure=True, same_site="Lax")
"""),
          S("set_config", path="functions.theme",
            value={"handler": "app.theme.theme", "events": [{"http": "GET /theme"}, {"http": "POST /theme"}]}),
          S("invoke_local", function="theme", method="GET", path="/theme"),
          S("invoke_local", function="theme", method="POST", path="/theme", data={"theme": "dark"}),
      ],
      final="""Done, function `theme`:

- **GET /theme** reads the `theme` cookie from `event.http.cookies` [docs/handlers.md#httprequest]; without cookie → `{"theme": "light"}` (tested).
- **POST /theme** `{"theme": "dark"}` → 200 `{"theme": "dark"}` (tested) and sets the cookie for 1 year with `set_cookie(...)` [docs/handlers.md#returning-a-response]. Other value → 400.
- `pskit validate` (gcp): valid.

Local invoke doesn't print the `Set-Cookie` header, so check it in the browser dev tools after **Deploy** (`pskit deploy -s dev`). `http_only=False` so your page JS can read the theme too."""),

    # ------------------------------------------------------------------ 648
    B(648, provider="azure", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: ledger
provider:
  name: azure
  region: westeurope
functions:
  api:
    handler: app.ledger.api
    events:
    - http: POST /entries
""",
          "app/__init__.py": "",
          "app/ledger.py": FUTURE + """

def api(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="new fn post-entries on storage queue ledger-in, ops created it already in our app storage account, don't create. log entry ids",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/ledger.py: post_entries logs each record's entry id",
                                   "functions.post-entries: queue {name: ledger-in, existing: true}",
                                   "Validate azure prod, invoke 2 messages"]),
          S("write_file", path="app/ledger.py", content=FUTURE + """

def api(event, ctx):
    return {"ok": True}


def post_entries(event, ctx):
    ids = [r.json(default={}).get("entry_id") for r in event.records]
    ctx.logger.info("entries received", extra={"entry_ids": ids})
    return {"posted": ids}
"""),
          S("set_config", path="functions.post-entries",
            value={"handler": "app.ledger.post_entries", "events": [{"queue": {"name": "ledger-in", "existing": True}}]}),
          S("invoke_local", function="post-entries", type="queue", data=[{"entry_id": "e-1"}, {"entry_id": "e-2"}]),
      ],
      final="""```yaml
functions:
  post-entries:
    handler: app.ledger.post_entries
    events:
      - queue: {name: ledger-in, existing: true}
```

- `existing: true`: pskit uses the queue and doesn't create it [docs/events.md#queue]. It's in the app's own storage account, so no `storage_connection` is needed.
- `pskit validate` (azure, prod): valid; 2 messages → `{"posted": ["e-1", "e-2"]}`.
- Failing messages go to `ledger-in-poison` after the retries.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 649
    B(649, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: xmas
provider:
  name: aws
  region: us-east-1
functions: {}
""",
          "requirements.txt": ""}),
      user="my website should show how many days until christmas. can a function do that?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/countdown.py: days from today (UTC) to the next 25 December",
                                   "Add function countdown on GET /countdown",
                                   "Validate for aws, call it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/countdown.py", content=FUTURE + """from datetime import date, datetime, timezone


def countdown(event, ctx):
    today = datetime.now(timezone.utc).date()
    xmas = date(today.year, 12, 25)
    if today > xmas:
        xmas = date(today.year + 1, 12, 25)
    days = (xmas - today).days
    return {"days": days, "message": "Merry Christmas!" if days == 0 else f"{days} days until Christmas"}
"""),
          S("set_config", path="functions.countdown",
            value={"handler": "app.countdown.countdown", "events": [{"http": "GET /countdown"}]}),
          S("invoke_local", function="countdown", method="GET", path="/countdown"),
      ],
      final="""Yes! Your function `countdown` is ready at **GET /countdown**.

- It counts the days from today to the next 25 December (after Christmas it counts to next year's).
- Today it answered `{"days": 54, "message": "54 days until Christmas"}`.
- `pskit validate` (aws): valid.

Your website can fetch `/countdown` and show `message`. Run it again on **Test** > **▶ Run locally**; put it online with **Deploy** or `pskit deploy -s dev`. If the page is on another domain, ask me to add CORS."""),

    # ------------------------------------------------------------------ 650
    B(650, provider="gcp", stage="prod", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: warehouse
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, warehouse-prod-1}
functions:
  api:
    handler: app.wh.api
    events:
    - http: GET /stock
  restock:
    handler: app.wh.restock
    events:
    - topic: low-stock
  export:
    handler: app.wh.export
    events:
    - schedule:
        cron: "0 2 * * *"
        timezone: Europe/Berlin
        name: nightly-export
  purge:
    handler: app.wh.purge
    events:
    - schedule: "30 3 * * 0"
""",
          "app/__init__.py": "",
          "app/wh.py": FUTURE + """

def api(event, ctx):
    return {"stock": []}


def restock(event, ctx):
    return None


def export(event, ctx):
    return {"exported": 0}


def purge(event, ctx):
    return {"purged": 0}
""",
          "requirements.txt": ""}),
      user="nightly-export 02:00 -> 04:30 berlin. backups overlap. only that",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.export.events.0.schedule.cron: \"30 4 * * *\" (timezone and name stay)",
                                   "Validate gcp prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.export.events.0.schedule.cron", value="30 4 * * *"),
      ],
      final="""```yaml
functions:
  export:
    handler: app.wh.export
    events:
      - schedule:
          cron: "30 4 * * *"
          timezone: Europe/Berlin
          name: nightly-export
```

GCP Cloud Scheduler honours `timezone`, so it's 04:30 Berlin time all year [docs/events.md#schedule]. Nothing else changed (`purge` stays Sunday 03:30 UTC).

`pskit validate` (gcp, prod): valid. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 651
    B(651, provider="azure", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/configuration.md#precedence-later-wins"],
      project=dict(files={
          "pskit.yml": """service: feeds
provider:
  name: azure
  region: westeurope
functions:
  import-feed:
    handler: app.feeds.import_feed
    events:
    - queue: feed-items
""",
          "app/__init__.py": "",
          "app/feeds.py": FUTURE + """

def import_feed(event, ctx):
    return {"imported": len(event.records)}
""",
          "requirements.txt": ""}),
      user="In dev and staging, `import-feed` should keep its pskit-created queue `feed-items`. In prod it must read the existing queue `partner-feed-prod` instead (already in our storage account) and pskit must not create `feed-items` there.",
      steps=[
          S("get_project"),
          S("search_docs", query="stage override function events list",
            docs=[D("docs/configuration.md", "precedence-later-wins")]),
          S("propose_plan", steps=["stages.prod.functions.import-feed.events = [queue {name: partner-feed-prod, existing: true}] (lists replace)",
                                   "Validate for azure prod, invoke one message in prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages",
            value={"prod": {"functions": {"import-feed": {"events": [{"queue": {"name": "partner-feed-prod", "existing": True}}]}}}}),
          S("invoke_local", function="import-feed", type="queue", data=[{"item": 1}]),
      ],
      final="""```yaml
stages:
  prod:
    functions:
      import-feed:
        events:
          - queue: {name: partner-feed-prod, existing: true}
```

- In prod the event list is **replaced**, so `feed-items` is not part of the prod deployment at all [docs/configuration.md#precedence-later-wins]; dev and staging keep it.
- `existing: true` → pskit only reads `partner-feed-prod`.
- `pskit validate` (azure, prod): valid; one message in prod → `{"imported": 1}`.

Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 652
    B(652, provider="aws", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: checkout-flow
provider:
  name: aws
  region: eu-west-1
functions:
  apply-coupon:
    handler: app.flow.apply_coupon
  charge:
    handler: app.flow.charge
workflows:
  checkout:
    start_at: Charge
    states:
      Charge:
        type: task
        function: charge
        end: true
""",
          "app/__init__.py": "",
          "app/flow.py": FUTURE + """

def apply_coupon(event, ctx):
    data = dict(event.data or {})
    data["total"] = round(data.get("total", 0) * 0.9, 2)
    return data


def charge(event, ctx):
    return {"charged": (event.data or {}).get("total")}
""",
          "requirements.txt": ""}),
      user="checkout wf: if input have coupon field go apply-coupon first, then charge. no coupon direct charge",
      steps=[
          S("get_project"),
          S("search_docs", query="choice is_present", docs=[D("docs/workflows.md", "choice-rules", start="| Operator |", end="evaluates to false instead of failing.")]),
          S("propose_plan", steps=["start_at HasCoupon (choice): $.coupon is_present true -> ApplyCoupon, default Charge",
                                   "ApplyCoupon (apply-coupon) -> Charge",
                                   "Validate for aws, invoke apply-coupon"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.checkout",
            value={"start_at": "HasCoupon",
                   "states": {"HasCoupon": {"type": "choice",
                                            "choices": [{"variable": "$.coupon", "is_present": True, "next": "ApplyCoupon"}],
                                            "default": "Charge"},
                              "ApplyCoupon": {"type": "task", "function": "apply-coupon", "next": "Charge"},
                              "Charge": {"type": "task", "function": "charge", "end": True}}}),
          S("invoke_local", function="apply-coupon", type="workflow", data={"total": 50, "coupon": "AUTUMN10"}),
      ],
      final="""```yaml
workflows:
  checkout:
    start_at: HasCoupon
    states:
      HasCoupon:
        type: choice
        choices:
          - {variable: $.coupon, is_present: true, next: ApplyCoupon}
        default: Charge
      ApplyCoupon: {type: task, function: apply-coupon, next: Charge}
      Charge: {type: task, function: charge, end: true}
```

- `is_present` checks only that the field exists [docs/workflows.md#choice-rules]; `"coupon": null` would still go to ApplyCoupon. Add `is_null` in an `and` if that can happen.
- `pskit validate` (aws): valid (Step Functions).
- apply-coupon with total 50 → total 45.0, coupon kept.

Try both paths: `pskit workflow run checkout -i '{"total": 50, "coupon": "AUTUMN10"}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 653
    B(653, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: tax-engine
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, tax-engine-staging}
functions:
  dach-tax:
    handler: app.tax.dach
  intl-tax:
    handler: app.tax.intl
""",
          "app/__init__.py": "",
          "app/tax.py": FUTURE + """
RATES = {"DE": 0.19, "AT": 0.20, "CH": 0.081}


def dach(event, ctx):
    data = event.data or {}
    rate = RATES[data["country"]]
    return {**data, "rate": rate, "tax": round(data["net"] * rate, 2)}


def intl(event, ctx):
    data = event.data or {}
    return {**data, "rate": 0.0, "tax": 0.0}
""",
          "requirements.txt": ""}),
      user="Create workflow `tax`. If $.country is DE, AT or CH run dach-tax, everything else intl-tax. The output of the tax function is the workflow result.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["workflows.tax: start_at Region (choice: $.country in [DE, AT, CH] -> Dach, default Intl)",
                                   "Dach (dach-tax) and Intl (intl-tax) both end",
                                   "Validate gcp staging, invoke dach-tax with an AT order"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.tax",
            value={"start_at": "Region",
                   "states": {"Region": {"type": "choice",
                                         "choices": [{"variable": "$.country", "in": ["DE", "AT", "CH"], "next": "Dach"}],
                                         "default": "Intl"},
                              "Dach": {"type": "task", "function": "dach-tax", "end": True},
                              "Intl": {"type": "task", "function": "intl-tax", "end": True}}}),
          S("invoke_local", function="dach-tax", type="workflow", data={"country": "AT", "net": 100}),
      ],
      final="""```yaml
workflows:
  tax:
    start_at: Region
    states:
      Region:
        type: choice
        choices:
          - {variable: $.country, in: [DE, AT, CH], next: Dach}
        default: Intl
      Dach: {type: task, function: dach-tax, end: true}
      Intl: {type: task, function: intl-tax, end: true}
```

- `in` matches one value of a list [docs/workflows.md#choice-rules]; anything else, or a missing `country`, goes to Intl.
- `pskit validate` (gcp, staging): valid (Cloud Workflows).
- dach-tax with AT / 100 → `rate 0.2`, `tax 20.0`.

Run it: `pskit workflow run tax -i '{"country": "CH", "net": 50}' -s staging`, or **Deploy > Run a workflow locally**. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 654
    B(654, provider="azure", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#engines"],
      project=dict(files={
          "pskit.yml": """service: kyc
provider:
  name: azure
  region: westeurope
functions:
  verify-id:
    handler: app.kyc.verify
  open-account:
    handler: app.kyc.open_account
workflows:
  onboarding:
    start_at: Verify
    states:
      Verify:
        type: task
        function: verify-id
        next: Open
      Open:
        type: task
        function: open-account
        end: true
""",
          "app/__init__.py": "",
          "app/kyc.py": FUTURE + """

def verify(event, ctx):
    return {**(event.data or {}), "verified": True}


def open_account(event, ctx):
    return {**(event.data or {}), "account": "acc-1"}
""",
          "requirements.txt": ""}),
      user="In Step Functions this state machine had TimeoutSeconds 300. Here on Azure it runs on the embedded engine I think. Can I still limit the whole run to 5 minutes?",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow timeout embedded engine",
            docs=[D("docs/workflows.md", "workflow-keys", start="| `engine` |", end="| `timeout` |")]),
          S("propose_plan", steps=["workflows.onboarding.timeout: 300",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.onboarding.timeout", value=300),
      ],
      final="""Yes. Right, on Azure `engine: auto` uses the embedded engine (a generated orchestrator function) [docs/workflows.md#workflow-keys]. `timeout` works there too:

```yaml
workflows:
  onboarding:
    timeout: 300
    start_at: Verify
    # states unchanged
```

- It sets the orchestrator function's timeout (capped at Azure's max) and the engine itself stops the run with `TIMED_OUT` after 300 s.
- `pskit validate` (azure): valid (`workflow onboarding: embedded engine`), with a warning that the whole run is capped by the function timeout (600 s max on Azure Functions). 300 s is well inside that.

Try a run: `pskit workflow run onboarding -i '{"customer": "c-7"}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 655
    B(655, provider="aws", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: media
provider:
  name: aws
  region: eu-west-1
functions:
  transcode:
    handler: app.media.transcode
    timeout: 300
    events:
    - queue: transcode-jobs
  thumbnails:
    handler: app.media.thumbnails
    events:
    - queue: thumbnail-jobs
""",
          "app/__init__.py": "",
          "app/media.py": FUTURE + """

def transcode(event, ctx):
    return {"done": len(event.records)}


def thumbnails(event, ctx):
    return {"done": len(event.records)}
""",
          "requirements.txt": ""}),
      user="add dead letter queue pls, failed msg keep coming forever",
      steps=[
          S("get_project"),
          S("ask_user", say="There are two queue workers here.",
            question="Which queue should get a dead-letter queue, and after how many failed tries?",
            options=["transcode-jobs", "thumbnail-jobs", "both"],
            answer="both. after 3 tries"),
          S("propose_plan", steps=["transcode: queue {name: transcode-jobs, dead_letter: transcode-jobs-dlq, max_receive: 3}",
                                   "thumbnails: queue {name: thumbnail-jobs, dead_letter: thumbnail-jobs-dlq, max_receive: 3}",
                                   "Validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.transcode.events.0",
            value={"queue": {"name": "transcode-jobs", "dead_letter": "transcode-jobs-dlq", "max_receive": 3}}),
          S("set_config", path="functions.thumbnails.events.0",
            value={"queue": {"name": "thumbnail-jobs", "dead_letter": "thumbnail-jobs-dlq", "max_receive": 3}}),
      ],
      final="""Both queues have a DLQ now:

```yaml
functions:
  transcode:
    events:
      - queue: {name: transcode-jobs, dead_letter: transcode-jobs-dlq, max_receive: 3}
  thumbnails:
    events:
      - queue: {name: thumbnail-jobs, dead_letter: thumbnail-jobs-dlq, max_receive: 3}
```

- After 3 failed receives SQS moves the message to the `-dlq` queue instead of retrying forever [docs/events.md#queue].
- `pskit validate` (aws, staging): valid.

Look at the DLQ messages to find out why they fail. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 656
    B(656, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: first-steps
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, first-steps-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="I'm on the Functions page and it says Create your first function. I'm scared to click things. Can you make a first one that says hello with today's date?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/hello.py: returns a greeting with today's date (UTC)",
                                   "Add function hello on GET /hello",
                                   "Validate for gcp, run it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/hello.py", content=FUTURE + """from datetime import datetime, timezone


def hello(event, ctx):
    today = datetime.now(timezone.utc).strftime("%A %d %B %Y")
    return {"message": f"Hello! Today is {today}."}
"""),
          S("set_config", path="functions.hello", value={"handler": "app.hello.hello", "events": [{"http": "GET /hello"}]}),
          S("invoke_local", function="hello", method="GET", path="/hello"),
      ],
      final="""Done, nothing scary happened 🙂 — your first function `hello` exists:

- It answers **GET /hello** with `{"message": "Hello! Today is Sunday 01 November 2026."}` (that's what it said when I ran it).
- `pskit validate` (gcp): valid.
- Nothing is in the cloud yet; all of this ran on your computer.

Next steps:
1. **Test** > **▶ Run locally** runs it again.
2. **Functions** now lists `hello`; its row has **Open code** to see app/hello.py.
3. When you're ready, **Deploy** (or `pskit deploy -s dev`) puts it online.

For your next function you can use **Functions > + Create function**; the wizard walks you through it."""),

    # ------------------------------------------------------------------ 657
    B(657, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: newsroom
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="""Add GET /articles with pagination over 45 sample articles.
- query `page` (default 1) and `size` (default 20, max 100)
- non-numbers, page < 1, size < 1 or size > 100 -> 400 with a clear message
- response: {page, size, total, items}""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/articles.py: 45 sample articles, parse page/size from event.http.query with checks",
                                   "Add function articles on GET /articles",
                                   "Validate for azure, invoke page 3 size 20 (last 5 items)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/articles.py", content=FUTURE + """from py_serverless_kit import BadRequest

ARTICLES = [{"id": i, "title": f"Article {i}"} for i in range(1, 46)]


def _int_param(query, name: str, default: int, low: int, high: int) -> int:
    raw = query.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise BadRequest(f"{name} must be a whole number")
    if not low <= value <= high:
        raise BadRequest(f"{name} must be between {low} and {high}")
    return value


def articles(event, ctx):
    query = event.http.query
    page = _int_param(query, "page", 1, 1, 10**6)
    size = _int_param(query, "size", 20, 1, 100)
    start = (page - 1) * size
    return {"page": page, "size": size, "total": len(ARTICLES), "items": ARTICLES[start:start + size]}
"""),
          S("set_config", path="functions.articles", value={"handler": "app.articles.articles", "events": [{"http": "GET /articles"}]}),
          S("invoke_local", function="articles", method="GET", path="/articles?page=3&size=20"),
          S("invoke_local", function="articles", method="GET", path="/articles?size=500"),
      ],
      final="""`GET /articles` is added with pagination:

- `page` (default 1) and `size` (default 20, max 100) come from `event.http.query` [docs/handlers.md#httprequest].
- Bad values → 400 via `BadRequest` [docs/handlers.md#errors]: "page must be a whole number", "size must be between 1 and 100".
- A page past the end returns `items: []`.

Checks:
- `pskit validate` (azure): valid.
- `?page=3&size=20` → 200, `total: 45`, items 41–45.
- `?size=500` → 400 `size must be between 1 and 100`.

Try other values on **Test** or `pskit invoke -f articles --method GET --path "/articles?page=2"`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 658
    B(658, provider="aws", stage="prod", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: votes
provider:
  name: aws
  region: eu-central-1
functions:
  vote:
    handler: app.vote.vote
    environment:
      BLOCKED_IPS: ${env:BLOCKED_IPS, 203.0.113.7}
    events:
    - http: POST /vote
""",
          "app/__init__.py": "",
          "app/vote.py": FUTURE + """

def vote(event, ctx):
    return {"counted": True}
""",
          "requirements.txt": ""}),
      user="vote: reject callers whose IP is in BLOCKED_IPS (comma list) with 403, log ip",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/vote.py: parse BLOCKED_IPS, compare event.http.source_ip, raise Forbidden + warning log",
                                   "Validate aws prod, invoke POST /vote"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/vote.py", content=FUTURE + """from py_serverless_kit import Forbidden


def _blocked(ctx) -> set:
    return {ip.strip() for ip in ctx.env.get("BLOCKED_IPS", "").split(",") if ip.strip()}


def vote(event, ctx):
    ip = event.http.source_ip
    if ip and ip in _blocked(ctx):
        ctx.logger.warning("blocked vote", extra={"ip": ip})
        raise Forbidden("not allowed")
    return {"counted": True}
"""),
          S("validate"),
          S("invoke_local", function="vote", method="POST", path="/vote", data={"choice": "b"}),
      ],
      final="""Done:

- `vote` compares `event.http.source_ip` [docs/handlers.md#httprequest] with the comma list in `BLOCKED_IPS`; a match → warning log with the IP and 403 `Forbidden` [docs/handlers.md#errors].
- `pskit validate` (aws, prod): valid.
- Local POST /vote (local IP, not blocked) → 200 `{"counted": true}`. The 403 path needs a call from a listed IP.

The list is read per request, so changing `BLOCKED_IPS` needs only a redeploy, no code change. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 659
    B(659, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: notes
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, notes-dev-5}
functions:
  notes:
    handler: app.notes.handler
    events:
    - http: GET /notes/{id}
""",
          "app/__init__.py": "",
          "app/notes.py": FUTURE + """from py_serverless_kit import NotFound

NOTES = {"1": {"id": "1", "text": "buy milk"}, "2": {"id": "2", "text": "call mum"}}


def handler(event, ctx):
    note = NOTES.get(event.http.path_params["id"])
    if note is None:
        raise NotFound("note not found")
    return note
""",
          "requirements.txt": ""}),
      user="need delete note too. DELETE /notes/{id}",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["notes: add DELETE /notes/{id} route",
                                   "handler: DELETE removes the note and returns {deleted: id}; unknown id -> 404",
                                   "Validate for gcp, invoke DELETE /notes/1"],
            result={"decision": "approved",
                    "note": "return 204 with no body, and an unknown id is also 204 (delete should be idempotent)"}),
          S("write_file", say="Changing it as you asked: always 204, also for unknown ids.",
            path="app/notes.py", content=FUTURE + """from py_serverless_kit import NotFound

NOTES = {"1": {"id": "1", "text": "buy milk"}, "2": {"id": "2", "text": "call mum"}}


def handler(event, ctx):
    note_id = event.http.path_params["id"]
    if event.http.method == "DELETE":
        NOTES.pop(note_id, None)  # idempotent: unknown ids are fine too
        return None
    note = NOTES.get(note_id)
    if note is None:
        raise NotFound("note not found")
    return note
"""),
          S("set_config", path="functions.notes.events",
            value=[{"http": "GET /notes/{id}"}, {"http": "DELETE /notes/{id}"}]),
          S("invoke_local", function="notes", method="DELETE", path="/notes/1"),
          S("invoke_local", function="notes", method="DELETE", path="/notes/99"),
      ],
      final="""Added `DELETE /notes/{id}`, following your note:

- Always **204 No Content** (`None` → 204 [docs/handlers.md#returning-a-response]), also when the id doesn't exist, so repeating a delete is safe.
- GET still gives 404 for unknown notes.

Checks: `pskit validate` (gcp) valid; DELETE /notes/1 → 204, DELETE /notes/99 → 204.

The notes still live in memory, so a restart brings them back; a database comes later. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 660
    B(660, provider="azure", stage="staging", mode="auto", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#context", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: support-api
provider:
  name: azure
  region: westeurope
functions:
  tickets:
    handler: app.tickets.create
    events:
    - http: POST /tickets
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """import uuid


def create(event, ctx):
    return {"ticket": uuid.uuid4().hex[:6]}, 201
""",
          "requirements.txt": ""}),
      user="When customers report problems, support needs to find the matching log lines. Return the request id in an `X-Request-Id` response header on POST /tickets, and log it together with the ticket number.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/tickets.py: (body, 201, {\"X-Request-Id\": ctx.request_id}); info log with the ticket",
                                   "Validate azure staging, invoke POST /tickets"]),
          S("write_file", path="app/tickets.py", content=FUTURE + """import uuid


def create(event, ctx):
    ticket = uuid.uuid4().hex[:6]
    ctx.logger.info("ticket created", extra={"ticket": ticket})
    return {"ticket": ticket}, 201, {"X-Request-Id": ctx.request_id}
"""),
          S("validate"),
          S("invoke_local", function="tickets", method="POST", path="/tickets", data={"subject": "login broken"}),
      ],
      final="""Done:

- POST /tickets now answers 201 with `X-Request-Id: <ctx.request_id>` [docs/handlers.md#context] [docs/handlers.md#returning-a-response].
- The `ticket created` log line carries the ticket, and `ctx.logger` already adds `request_id` to every line, so support can search the logs by either.
- `pskit validate` (azure, staging): valid; a local POST returned 201 with an `x-request-id` header.

Locally the id is a generated UUID; on Azure it's the invocation id. Find lines on **Logs** or with `pskit logs -s staging -q <id>`. Deploy: **Deploy** or `pskit deploy -s staging`."""),
]
