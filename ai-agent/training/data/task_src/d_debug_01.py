"""Category D (fix a handler bug), batch 1. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"d_debug-{n:04d}", category="d_debug", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 1  aws http, query KeyError
    B(1, provider="aws", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: aws
  region: eu-west-1
functions:
  list-items:
    handler: app.items.list_items
    events:
      - http: GET /items
""",
          "app/__init__.py": "",
          "app/items.py": FUTURE + """ITEMS = [{"id": i} for i in range(1, 13)]


def list_items(event, ctx):
    page = int(event.http.query["page"])
    size = 5
    start = (page - 1) * size
    return {"page": page, "items": ITEMS[start:start + size]}
""",
          "requirements.txt": ""}),
      user="list-items give 500 when i open /items without ?page , with page=2 it work. why",
      steps=[
          S("read_file", path="app/items.py"),
          S("invoke_local", say="Let me call it without `?page` to see the real error.",
            function="list-items", method="GET", path="/items"),
          S("search_docs", query="http query string parameters dict",
            docs=[D("docs/handlers.md", "httprequest", end="| `multi_query`")]),
          S("propose_plan", steps=["In `app/items.py`, read `page` with `event.http.query.get(\"page\", \"1\")` so a missing `?page` means page 1",
                                   "Run `list-items` locally on `/items` again and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/items.py", content=FUTURE + """ITEMS = [{"id": i} for i in range(1, 13)]


def list_items(event, ctx):
    page = int(event.http.query.get("page", "1"))
    size = 5
    start = (page - 1) * size
    return {"page": page, "items": ITEMS[start:start + size]}
"""),
          S("invoke_local", function="list-items", method="GET", path="/items"),
          S("validate"),
      ],
      final="""The cause: `event.http.query` is a normal dict, so `query["page"]` raises `KeyError: 'page'` when the URL has no `?page`. Any exception in an HTTP handler becomes a 500 [docs/handlers.md#httprequest].

Fixed in `app/items.py`:

```python
page = int(event.http.query.get("page", "1"))
```

- Local run on `/items`: status 200, page 1 with items 1-5.
- `pskit validate` for aws: valid.

Test again on **Test** > **▶ Run locally**, or `pskit invoke -f list-items --path /items`."""),

    # ------------------------------------------------------------------ 2  gcp queue, body is a str
    B(2, provider="gcp", stage="staging", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: mailer
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  send-mail:
    handler: app.mail.send
    events:
      - queue: outbox
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """
def send(event, ctx):
    for record in event.records:
        to = record.body["to"]
        ctx.logger.info("sending", extra={"to": to})
    return {"sent": len(event.records)}
""",
          "requirements.txt": ""}),
      user="send-mail dies on every message: TypeError string indices must be integers. payload is json. fix",
      steps=[
          S("read_file", path="app/mail.py"),
          S("invoke_local", function="send-mail", type="queue", data=[{"to": "ops@example.com"}]),
          S("propose_plan", steps=["Parse each message with `record.json()` instead of indexing `record.body`",
                                   "Re-run send-mail with one queue message, validate for gcp"]),
          S("write_file", path="app/mail.py", content=FUTURE + """
def send(event, ctx):
    for record in event.records:
        to = record.json()["to"]
        ctx.logger.info("sending", extra={"to": to})
    return {"sent": len(event.records)}
"""),
          S("invoke_local", function="send-mail", type="queue", data=[{"to": "ops@example.com"}]),
          S("validate"),
      ],
      final="""`record.body` is the raw message text (a JSON string), so `body["to"]` indexes a str. `record.json()` decodes it [docs/handlers.md#record].

Changed one line in `app/mail.py`: `to = record.json()["to"]`.

- invoke with one message: logged `sending`, returned `{"sent": 1}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 3  azure schedule, remaining_time_ms None
    B(3, provider="azure", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: sync-jobs
provider:
  name: azure
  region: westeurope
functions:
  sync:
    handler: app.sync.sync
    timeout: 300
    events:
      - schedule: 15 minutes
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """BATCHES = ["customers", "orders", "invoices"]


def sync(event, ctx):
    done = []
    for name in BATCHES:
        if ctx.remaining_time_ms() < 30000:
            ctx.logger.warning("stopping early", extra={"done": done})
            break
        done.append(name)
    return {"synced": done}
""",
          "requirements.txt": ""}),
      user="The `sync` function is supposed to stop early when less than 30 seconds of its timeout are left. In Azure it runs fine, but running it locally fails with `TypeError: '<' not supported between instances of 'NoneType' and 'int'`. Please make it run locally too, without changing how it behaves in the cloud.",
      steps=[
          S("read_file", path="app/sync.py"),
          S("invoke_local", function="sync", type="schedule"),
          S("search_docs", query="context remaining_time_ms None",
            docs=[D("docs/handlers.md", "context", end="| `logger`")]),
          S("propose_plan", steps=["Store `ctx.remaining_time_ms()` in a variable and only compare it when it is not None",
                                   "Run `sync` locally as a schedule event and validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sync.py", content=FUTURE + """BATCHES = ["customers", "orders", "invoices"]


def sync(event, ctx):
    done = []
    for name in BATCHES:
        left = ctx.remaining_time_ms()
        if left is not None and left < 30000:
            ctx.logger.warning("stopping early", extra={"done": done})
            break
        done.append(name)
    return {"synced": done}
"""),
          S("invoke_local", function="sync", type="schedule"),
          S("validate"),
      ],
      final="""Cause: `ctx.remaining_time_ms()` returns the time left, **or `None` if unknown** [docs/handlers.md#context]. Under `pskit invoke` there is no platform deadline, so it is `None` and `None < 30000` fails.

Fix in `app/sync.py`:

```python
left = ctx.remaining_time_ms()
if left is not None and left < 30000:
```

In Azure the value is known, so the early stop works exactly as before. Locally the check is skipped.

- Local schedule run: `{"synced": ["customers", "orders", "invoices"]}`.
- `pskit validate` for azure, stage prod: valid."""),

    # ------------------------------------------------------------------ 4  onprem storage, record.json() on a storage record
    B(4, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/events.md#storage", "docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: photo-inbox
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8095
functions:
  on-photo:
    handler: app.photos.on_photo
    events:
      - storage: photos
""",
          "app/__init__.py": "",
          "app/photos.py": FUTURE + """
def on_photo(event, ctx):
    for record in event.records:
        info = record.json()
        ctx.logger.info("new photo", extra={"name": info["key"]})
    return {"count": len(event.records)}
""",
          "requirements.txt": ""}),
      user="when i test my photo function it says Record local-0 body is empty, expected JSON. i dont understand what body it wants??",
      steps=[
          S("read_file", path="app/photos.py"),
          S("invoke_local", function="on-photo", type="storage",
            data={"bucket": "photos", "key": "cat.jpg", "size": 2048}),
          S("search_docs", query="storage event record bucket key size",
            docs=[D("docs/events.md", "storage", start="Each record has"),
                  D("docs/handlers.md", "record", end="| `bucket`, `key`")]),
          S("propose_plan", steps=["In `app/photos.py`, read the file name from `record.key` instead of `record.json()`",
                                   "Test `on-photo` again with a storage event and validate"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/photos.py", content=FUTURE + """
def on_photo(event, ctx):
    for record in event.records:
        ctx.logger.info("new photo", extra={"name": record.key, "bytes": record.size})
    return {"count": len(event.records)}
"""),
          S("invoke_local", function="on-photo", type="storage",
            data={"bucket": "photos", "key": "cat.jpg", "size": 2048}),
          S("validate"),
      ],
      final="""A file event has no message body. Each record tells you **which** file arrived: `record.bucket`, `record.key` (the file name), `record.size` and `record.action` [docs/events.md#storage]. `record.json()` tries to read a body, finds none, and raises that error.

I changed the handler to use `record.key` and `record.size` directly.

- Test with `cat.jpg`: it logged "new photo" and returned `{"count": 1}`.
- `pskit validate`: valid.

Run it again on **Test** > **▶ Run locally** (event type storage). If you need the file's contents, read the file from the bucket using that key."""),

    # ------------------------------------------------------------------ 5  aws http, Lambda proxy return shape
    B(5, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: orders-api
provider:
  name: aws
  region: us-east-1
functions:
  create-order:
    handler: app.orders.create
    events:
      - http: POST /orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """import json


def create(event, ctx):
    order = event.http.json()
    order["status"] = "new"
    return {"statusCode": 201, "headers": {"Content-Type": "application/json"}, "body": json.dumps(order)}
""",
          "requirements.txt": ""}),
      user="Ported my Lambda handler from SAM. There it returned 201, but pskit invoke shows status 200 and the whole statusCode/headers/body dict comes back as the body. Doesn't pskit use the API Gateway proxy response format?",
      steps=[
          S("read_file", path="app/orders.py"),
          S("invoke_local", function="create-order", method="POST", path="/orders", data={"sku": "A-1", "qty": 2}),
          S("search_docs", query="return status code response tuple",
            docs=[D("docs/handlers.md", "returning-a-response", end="| `(body, status)`")]),
          S("propose_plan", steps=["Return `order, 201` (Flask-style tuple) instead of the proxy dict; drop the unused `json` import",
                                   "Invoke create-order with a POST body and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/orders.py", content=FUTURE + """
def create(event, ctx):
    order = event.http.json()
    order["status"] = "new"
    return order, 201
"""),
          S("invoke_local", function="create-order", method="POST", path="/orders", data={"sku": "A-1", "qty": 2}),
          S("validate"),
      ],
      final="""Right: pskit handlers don't return the proxy format. The adapter builds it for you, and a plain `dict` is treated as the JSON body with status 200 [docs/handlers.md#returning-a-response]. That is why your `statusCode` dict showed up as the body.

Now `create` returns `order, 201`; the content type is set to `application/json` automatically.

- Local POST /orders: status 201, body `{"sku": "A-1", "qty": 2, "status": "new"}`.
- `pskit validate` for aws: valid.

The same code works unchanged on the other clouds. Test again with `pskit invoke -f create-order --method POST --path /orders -d '{"sku": "A-1", "qty": 2}'`."""),

    # ------------------------------------------------------------------ 6  huawei http, ValueError -> 500, want 400
    B(6, provider="huawei", stage="staging", mode="auto", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: signup
provider:
  name: huawei
  region: ap-southeast-1
  options:
    apig_instance_id: ${env:HUAWEI_APIG_ID, apig-demo}
functions:
  register:
    handler: app.signup.register
    events:
      - http: POST /register
""",
          "app/__init__.py": "",
          "app/signup.py": FUTURE + """
def register(event, ctx):
    body = event.http.json()
    if "email" not in body:
        raise ValueError("email is required")
    return {"registered": body["email"]}, 201
""",
          "requirements.txt": ""}),
      user="""{"status": 500, "body": {"error": "Internal Server Error", "status": 500, "request_id": "..."}}
this is what register returns when the email is missing. it should be a 400 that says email is required""",
      steps=[
          S("read_file", path="app/signup.py"),
          S("invoke_local", function="register", method="POST", path="/register", data={"name": "Kim"}),
          S("search_docs", query="raise http error 400 bad request",
            docs=[D("docs/handlers.md", "errors", end="Any other exception in an HTTP handler")]),
          S("propose_plan", steps=["Raise `BadRequest(\"email is required\")` instead of `ValueError` in `app/signup.py`",
                                   "Invoke register without an email and validate for huawei"]),
          S("write_file", path="app/signup.py", content=FUTURE + """from py_serverless_kit import BadRequest


def register(event, ctx):
    body = event.http.json()
    if "email" not in body:
        raise BadRequest("email is required")
    return {"registered": body["email"]}, 201
"""),
          S("invoke_local", function="register", method="POST", path="/register", data={"name": "Kim"}),
          S("validate"),
      ],
      final="""A plain `ValueError` is an unexpected exception, so pskit answers 500 and logs the traceback. To choose the status, raise an `HttpError` subclass [docs/handlers.md#errors].

`app/signup.py` now raises `BadRequest("email is required")`.

- POST /register without email: status 400, body `{"error": "email is required", "status": 400}`.
- `pskit validate` for huawei (staging): valid."""),

    # ------------------------------------------------------------------ 7  alibaba topic, missing import
    B(7, provider="alibaba", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=[],
      project=dict(files={
          "pskit.yml": """service: audit-log
provider:
  name: alibaba
  region: cn-shanghai
functions:
  audit:
    handler: app.audit.audit
    events:
      - topic: audit-events
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """
def audit(event, ctx):
    for record in event.records:
        entry = json.loads(record.text())
        ctx.logger.info("audit", extra={"action": entry.get("action")})
    return None
""",
          "requirements.txt": ""}),
      user="""NameError: name 'json' is not defined
from the audit function, every message""",
      steps=[
          S("read_file", path="app/audit.py"),
          S("invoke_local", function="audit", type="topic", data=[{"action": "login"}]),
          S("propose_plan", steps=["Add `import json` at the top of `app/audit.py`",
                                   "Run audit with one topic message and validate for alibaba"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/audit.py", content=FUTURE + """import json


def audit(event, ctx):
    for record in event.records:
        entry = json.loads(record.text())
        ctx.logger.info("audit", extra={"action": entry.get("action")})
    return None
"""),
          S("invoke_local", function="audit", type="topic", data=[{"action": "login"}]),
          S("validate"),
      ],
      final="""`app/audit.py` uses `json.loads` but never imports `json`. I added `import json` at the top.

- Local run with one topic message: logged `audit`, result `null` (the handler returns None, which is fine for topic events).
- `pskit validate` for alibaba: valid.

Tip: `record.json()` would decode the message without the import."""),

    # ------------------------------------------------------------------ 8  tencent schedule, no input -> event.data None
    B(8, provider="tencent", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: daily-digest
provider:
  name: tencent
  region: ap-guangzhou
functions:
  digest:
    handler: app.digest.run
    events:
      - schedule: "0 7 * * *"
""",
          "app/__init__.py": "",
          "app/digest.py": FUTURE + """
def run(event, ctx):
    region = event.data["region"]
    ctx.logger.info("building digest", extra={"region": region})
    return {"region": region, "sent": True}
""",
          "requirements.txt": ""}),
      user="my morning job breaks, the error says 'NoneType' object is not subscriptable. i never wrote None anywhere??",
      steps=[
          S("get_project"),
          S("read_file", path="app/digest.py"),
          S("invoke_local", function="digest", type="schedule"),
          S("search_docs", query="schedule input event.data",
            docs=[D("docs/events.md", "schedule", end="The handler gets `event.type")]),
          S("ask_user", question="Your code expects a `region` in the schedule's input, but the schedule has no input. Which region should the 07:00 run use?",
            options=["ap-guangzhou", "ap-shanghai", "Let the code fall back to a default"],
            answer="ap-guangzhou"),
          S("propose_plan", steps=["Give the `digest` schedule an input: cron `0 7 * * *`, input {\"region\": \"ap-guangzhou\"}",
                                   "Validate for tencent (prod) and run the schedule event locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.digest.events.0",
            value={"schedule": {"cron": "0 7 * * *", "input": {"region": "ap-guangzhou"}}}),
          S("invoke_local", function="digest", type="schedule"),
      ],
      final="""The `None` comes from pskit: a schedule passes its `input` as `event.data` [docs/events.md#schedule]. Your schedule had no `input`, so `event.data` was `None`, and `event.data["region"]` failed.

I gave the schedule an input (the code is unchanged):

```yaml
events:
  - schedule:
      cron: "0 7 * * *"
      input: {region: ap-guangzhou}
```

- `pskit validate` for tencent, prod: valid.
- Local run: `{"region": "ap-guangzhou", "sent": true}`.

The change goes live on your next deploy (**Deploy** page, or `pskit deploy -s prod`)."""),

    # ------------------------------------------------------------------ 9  digitalocean http, reversed tuple
    B(9, provider="digitalocean", stage="staging", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: notes-api
provider:
  name: digitalocean
  region: ams3
  options:
    namespace: ${env:DO_NAMESPACE, fn-notes}
functions:
  add-note:
    handler: app.notes.add
    events:
      - http: POST /notes
""",
          "app/__init__.py": "",
          "app/notes.py": FUTURE + """import uuid


def add(event, ctx):
    text = event.http.json().get("text", "")
    note_id = uuid.uuid4().hex[:8]
    return 201, {"id": note_id, "text": text}
""",
          "requirements.txt": ""}),
      user="add-note should answer 201 Created with the new note as a JSON object. Locally I get status 200 and the body is a JSON array like [201, {...}]. Please fix the return statement so the status is 201; keep the rest as is.",
      steps=[
          S("read_file", path="app/notes.py"),
          S("invoke_local", function="add-note", method="POST", path="/notes", data={"text": "buy milk"}),
          S("search_docs", query="tuple body status return",
            docs=[D("docs/handlers.md", "returning-a-response", end="| `(body, status)`")]),
          S("propose_plan", steps=["Swap the tuple to `return {\"id\": note_id, \"text\": text}, 201` in `app/notes.py`",
                                   "Invoke add-note with a POST body and validate for digitalocean"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/notes.py", content=FUTURE + """import uuid


def add(event, ctx):
    text = event.http.json().get("text", "")
    note_id = uuid.uuid4().hex[:8]
    return {"id": note_id, "text": text}, 201
"""),
          S("invoke_local", function="add-note", method="POST", path="/notes", data={"text": "buy milk"}),
          S("validate"),
      ],
      final="""The tuple was in the wrong order. pskit reads `(body, status)`: the second item must be the int status [docs/handlers.md#returning-a-response]. `(201, {...})` is not that shape, so the whole tuple was sent as a JSON array with 200.

Changed only the return line: `return {"id": note_id, "text": text}, 201`.

- Local POST /notes: status 201, body `{"id": "...", "text": "buy milk"}`.
- `pskit validate` for digitalocean (staging): valid, with the usual warning that `doctl` is not on PATH (only needed for deploy)."""),

    # ------------------------------------------------------------------ 10  cloudflare http, json() on GET
    B(10, provider="cloudflare", stage="dev", mode="auto", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: quote-of-day
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, demo-account}
functions:
  quote:
    handler: app.quote.get_quote
    events:
      - http: GET /quote
""",
          "app/__init__.py": "",
          "app/quote.py": FUTURE + """QUOTES = {"en": "Simplicity is a prerequisite for reliability.", "de": "Weniger ist mehr."}


def get_quote(event, ctx):
    lang = event.http.json().get("lang", "en")
    return {"lang": lang, "quote": QUOTES.get(lang, QUOTES["en"])}
""",
          "requirements.txt": ""}),
      user="i open /quote in the browser and get 400 Request body is empty. i didnt send anything, its just a page",
      steps=[
          S("read_file", path="app/quote.py"),
          S("invoke_local", function="quote", method="GET", path="/quote?lang=de"),
          S("search_docs", query="request body json query parameters",
            docs=[D("docs/handlers.md", "httprequest", start="| `query`", end="| `json(default=...)`")]),
          S("propose_plan", steps=["Read `lang` from the query string (`event.http.query`) instead of the request body",
                                   "Test /quote?lang=de locally and validate for cloudflare"]),
          S("write_file", path="app/quote.py", content=FUTURE + """QUOTES = {"en": "Simplicity is a prerequisite for reliability.", "de": "Weniger ist mehr."}


def get_quote(event, ctx):
    lang = event.http.query.get("lang", "en")
    return {"lang": lang, "quote": QUOTES.get(lang, QUOTES["en"])}
"""),
          S("invoke_local", function="quote", method="GET", path="/quote?lang=de"),
          S("validate"),
      ],
      final="""A browser visit is a GET request with **no body**. Your code called `event.http.json()`, and an empty body raises `BadRequest`, which is the 400 you saw [docs/handlers.md#httprequest].

Now the language comes from the address instead: `/quote?lang=de` (default `en`).

- Local test of `/quote?lang=de`: status 200, `{"lang": "de", "quote": "Weniger ist mehr."}`.
- `pskit validate` for cloudflare: valid (plus the normal note that only standard-library and Pyodide packages are available).

Try it on **Test** > **▶ Run locally** with the path `/quote?lang=de`."""),

    # ------------------------------------------------------------------ 11  oracle storage, S3 event dict access
    B(11, provider="oracle", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#record", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: invoice-ingest
provider:
  name: oracle
  region: eu-frankfurt-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..example}
    subnet_ids: [ocid1.subnet.oc1..example]
    image_repository: fra.ocir.io/example/invoice-ingest
functions:
  on-invoice:
    handler: app.invoices.on_invoice
    events:
      - storage: invoices
""",
          "app/__init__.py": "",
          "app/invoices.py": FUTURE + """
def on_invoice(event, ctx):
    key = event["Records"][0]["s3"]["object"]["key"]
    ctx.logger.info("invoice uploaded", extra={"key": key})
    return {"key": key}
""",
          "requirements.txt": ""}),
      user="Moving our S3-triggered Lambda to OCI with pskit. Same code, but invoke says 'Event' object is not subscriptable. How do I read the object key the portable way?",
      steps=[
          S("read_file", path="app/invoices.py"),
          S("invoke_local", function="on-invoice", type="storage", data={"bucket": "invoices", "key": "2026/inv-001.pdf"}),
          S("search_docs", query="storage record key bucket portable",
            docs=[D("docs/handlers.md", "record", end="| `bucket`, `key`")]),
          S("propose_plan", steps=["Replace the S3 dict access with a loop over `event.records`, using `record.key`",
                                   "Run on-invoice with a storage event and validate for oracle"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/invoices.py", content=FUTURE + """
def on_invoice(event, ctx):
    keys = []
    for record in event.records:
        ctx.logger.info("invoice uploaded", extra={"bucket": record.bucket, "key": record.key})
        keys.append(record.key)
    return {"keys": keys}
"""),
          S("invoke_local", function="on-invoice", type="storage", data={"bucket": "invoices", "key": "2026/inv-001.pdf"}),
          S("validate"),
      ],
      final="""The handler gets a portable `Event`, not the S3 notification dict, so `event["Records"]` fails. Each object is a `Record` in `event.records` with `bucket`, `key`, `size` and `action` [docs/handlers.md#record].

`app/invoices.py` now loops over `event.records` and uses `record.key`. This also handles several objects in one delivery.

- Local storage event (`2026/inv-001.pdf`): `{"keys": ["2026/inv-001.pdf"]}`.
- `pskit validate` for oracle: valid.

Note from [docs/events.md#storage]: on Oracle, `prefix`/`suffix` filters are not applied, so filter by `record.key` in the handler if you need to."""),

    # ------------------------------------------------------------------ 12  ibm http, swapped parameters
    B(12, provider="ibm", stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: weather-proxy
provider:
  name: ibm
  region: eu-de
  runtime: python3.11
functions:
  forecast:
    handler: app.weather.forecast
    events:
      - http: GET /forecast
""",
          "app/__init__.py": "",
          "app/weather.py": FUTURE + """
def forecast(ctx, event):
    city = event.http.query.get("city", "Berlin")
    return {"city": city, "forecast": "sunny"}
""",
          "requirements.txt": ""}),
      user="forecast func error 'Context' object has no attribute 'http' but i use event.http not ctx??",
      steps=[
          S("read_file", path="app/weather.py"),
          S("invoke_local", function="forecast", method="GET", path="/forecast?city=Paris"),
          S("propose_plan", steps=["Change the signature to `def forecast(event, ctx)`: the event comes first",
                                   "Invoke forecast locally and validate for ibm"]),
          S("write_file", path="app/weather.py", content=FUTURE + """
def forecast(event, ctx):
    city = event.http.query.get("city", "Berlin")
    return {"city": city, "forecast": "sunny"}
"""),
          S("invoke_local", function="forecast", method="GET", path="/forecast?city=Paris"),
          S("validate"),
      ],
      final="""The arguments were swapped. pskit calls `handler(event, ctx)`, event first [docs/handlers.md#handler-signatures]. Your function named them `(ctx, event)`, so your `event` was really the Context.

Fixed: `def forecast(event, ctx):`

- Local GET /forecast?city=Paris: status 200, `{"city": "Paris", "forecast": "sunny"}`.
- `pskit validate` for ibm: valid."""),

    # ------------------------------------------------------------------ 13  aws queue, one bad message fails whole batch
    B(13, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: billing-worker
provider:
  name: aws
  region: eu-central-1
functions:
  charge:
    handler: app.billing.charge
    events:
      - queue:
          name: charges
          batch_size: 10
          dead_letter: charges-dlq
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """
def charge(event, ctx):
    for record in event.records:
        msg = record.json()
        cents = int(msg["amount_cents"])
        ctx.logger.info("charged", extra={"order": msg["order"], "cents": cents})
""",
          "requirements.txt": ""}),
      user="When one message in a batch has a bad amount, the whole SQS batch fails and the good messages get charged again on retry. Expected: only the bad message is retried and eventually goes to charges-dlq. Please test with one good and one bad message.",
      steps=[
          S("read_file", path="app/billing.py"),
          S("invoke_local", function="charge", type="queue",
            data=[{"order": 1, "amount_cents": "1250"}, {"order": 2, "amount_cents": "12.50"}]),
          S("search_docs", query="partial batch failure retry only failed messages",
            docs=[D("docs/handlers.md", "batchresult", end="| everyone else")]),
          S("propose_plan", steps=["Wrap each message in try/except and return a `BatchResult`, calling `result.fail(record)` for bad ones",
                                   "Invoke charge with one good and one bad message; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/billing.py", content=FUTURE + """from py_serverless_kit import BatchResult


def charge(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            msg = record.json()
            cents = int(msg["amount_cents"])
            ctx.logger.info("charged", extra={"order": msg["order"], "cents": cents})
        except (ValueError, KeyError):
            ctx.logger.warning("bad message", extra={"id": record.id})
            result.fail(record)
    return result
"""),
          S("invoke_local", function="charge", type="queue",
            data=[{"order": 1, "amount_cents": "1250"}, {"order": 2, "amount_cents": "12.50"}]),
          S("validate"),
      ],
      final="""Before: `int("12.50")` raised `ValueError`, the exception failed the whole invocation, and SQS redelivered all 10 messages.

Now `charge` catches `ValueError`/`KeyError` per message and returns a `BatchResult`. On AWS it becomes `batchItemFailures`, so only failed messages are retried [docs/handlers.md#batchresult]. After `max_receive` (default 5) they move to `charges-dlq`.

- Local run: order 1 charged (1250 cents), the second message logged "bad message", output `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`.
- `pskit validate` for aws, prod: valid.

Make sure charging is idempotent; redelivery can still happen."""),

    # ------------------------------------------------------------------ 14  gcp workflow task, records vs data
    B(14, provider="gcp", stage="dev", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: order-flow
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  validate-order:
    handler: app.steps.validate_order
workflows:
  checkout:
    start_at: Validate
    states:
      Validate:
        type: task
        function: validate-order
        end: true
""",
          "app/__init__.py": "",
          "app/steps.py": FUTURE + """
def validate_order(event, ctx):
    order = event.records[0].json()
    if order["total"] <= 0:
        raise ValueError("total must be positive")
    return {"order_id": order["order_id"], "valid": True}
""",
          "requirements.txt": ""}),
      user="validate-order task: IndexError list index out of range on event.records[0]. wf input is {order_id, total}",
      steps=[
          S("read_file", path="app/steps.py"),
          S("invoke_local", function="validate-order", type="workflow", data={"order_id": 7, "total": 30}),
          S("propose_plan", steps=["Read the state input from `event.data` instead of `event.records[0]`",
                                   "Invoke validate-order as a workflow event; validate for gcp"]),
          S("write_file", path="app/steps.py", content=FUTURE + """
def validate_order(event, ctx):
    order = event.data
    if order["total"] <= 0:
        raise ValueError("total must be positive")
    return {"order_id": order["order_id"], "valid": True}
"""),
          S("invoke_local", function="validate-order", type="workflow", data={"order_id": 7, "total": 30}),
          S("validate"),
      ],
      final="""Workflow tasks get their input in `event.data`; `records` is only filled for queue/topic/storage batches [docs/handlers.md#event].

Fix: `order = event.data`.

- invoke `-t workflow` with `{"order_id": 7, "total": 30}`: `{"order_id": 7, "valid": true}`.
- validate (gcp): valid.

Full run: `pskit workflow run checkout -i '{"order_id": 7, "total": 30}'`."""),

    # ------------------------------------------------------------------ 15  onprem http, async missing await
    B(15, provider="onprem", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: price-check
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8101
functions:
  price:
    handler: app.prices.price
    events:
      - http: GET /price/{sku}
""",
          "app/__init__.py": "",
          "app/prices.py": FUTURE + """import asyncio


async def lookup(sku):
    await asyncio.sleep(0)
    return {"sku": sku, "price": 9.99}


async def price(event, ctx):
    item = lookup(event.http.path_params["sku"])
    return {"sku": item["sku"], "price": item["price"]}
""",
          "requirements.txt": ""}),
      user="price endpoint give 500, in log 'coroutine' object is not subscriptable. async is supported no?",
      steps=[
          S("read_file", path="app/prices.py"),
          S("invoke_local", function="price", method="GET", path="/price/A-100"),
          S("search_docs", query="async handler coroutine awaited",
            docs=[D("docs/handlers.md", "handler-signatures")]),
          S("propose_plan", steps=["Add the missing `await` before `lookup(...)` in `app/prices.py`",
                                   "Call GET /price/A-100 locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/prices.py", content=FUTURE + """import asyncio


async def lookup(sku):
    await asyncio.sleep(0)
    return {"sku": sku, "price": 9.99}


async def price(event, ctx):
    item = await lookup(event.http.path_params["sku"])
    return {"sku": item["sku"], "price": item["price"]}
"""),
          S("invoke_local", function="price", method="GET", path="/price/A-100"),
          S("validate"),
      ],
      final="""Yes, async handlers are supported, pskit awaits them [docs/handlers.md#handler-signatures]. The bug is inside: `lookup()` is async, and without `await` you get a coroutine object, not the dict.

Fix: `item = await lookup(event.http.path_params["sku"])`

- Local GET /price/A-100: status 200, `{"sku": "A-100", "price": 9.99}`.
- `pskit validate` for onprem: valid."""),

    # ------------------------------------------------------------------ 16  azure queue, returns result.failed
    B(16, provider="azure", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: stock-sync
provider:
  name: azure
  region: northeurope
functions:
  restock:
    handler: app.stock.restock
    events:
      - queue: restock-requests
""",
          "app/__init__.py": "",
          "app/stock.py": FUTURE + """from py_serverless_kit import BatchResult


def restock(event, ctx):
    result = BatchResult()
    for record in event.records:
        item = record.json()
        if not item.get("sku"):
            result.fail(record)
            continue
        ctx.logger.info("restocked", extra={"sku": item["sku"]})
    return result.failed
""",
          "requirements.txt": ""}),
      user="I followed the docs for failed messages, but when I test, the output is just [\"local-1\"] and not batchItemFailures like in the docs. Is my code right?",
      steps=[
          S("read_file", path="app/stock.py"),
          S("invoke_local", function="restock", type="queue", data=[{"sku": "A-7"}, {"sku": ""}]),
          S("search_docs", query="BatchResult return failed records",
            docs=[D("docs/handlers.md", "batchresult")]),
          S("propose_plan", steps=["Return the `BatchResult` object itself (`return result`), not `result.failed`",
                                   "Test restock with one good and one bad message, then validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/stock.py", content=FUTURE + """from py_serverless_kit import BatchResult


def restock(event, ctx):
    result = BatchResult()
    for record in event.records:
        item = record.json()
        if not item.get("sku"):
            result.fail(record)
            continue
        ctx.logger.info("restocked", extra={"sku": item["sku"]})
    return result
"""),
          S("invoke_local", function="restock", type="queue", data=[{"sku": "A-7"}, {"sku": ""}]),
          S("validate"),
      ],
      final="""Almost. You return `result.failed`, which is only a plain list of ids. pskit doesn't recognise that as a failure report, so the bad message would count as done. Return the `BatchResult` itself [docs/handlers.md#batchresult].

Changed the last line to `return result`.

- Test with one good and one empty sku: `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`.
- `pskit validate` for azure: valid.

Good to know: on Azure there is no partial retry. Any failure in the `BatchResult` makes the whole delivery fail and retry, so keep the handler safe to run twice."""),

    # ------------------------------------------------------------------ 17  aws http, HttpError positional status
    B(17, provider="aws", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: aws
  region: ap-southeast-2
functions:
  get-product:
    handler: app.products.get_product
    events:
      - http: GET /products/{id}
""",
          "app/__init__.py": "",
          "app/products.py": FUTURE + """from py_serverless_kit import HttpError

PRODUCTS = {"1": {"id": "1", "name": "Mug"}}


def get_product(event, ctx):
    pid = event.http.path_params["id"]
    if pid not in PRODUCTS:
        raise HttpError("product not found", 404)
    return PRODUCTS[pid]
""",
          "requirements.txt": ""}),
      user="""TypeError: HttpError.__init__() takes from 1 to 2 positional arguments but 3 were given
get-product, only for ids that don't exist. Should be a 404.""",
      steps=[
          S("read_file", path="app/products.py"),
          S("invoke_local", function="get-product", method="GET", path="/products/999"),
          S("search_docs", query="HttpError status argument NotFound",
            docs=[D("docs/handlers.md", "errors", start="| `NotFound`", end="| `HttpError(message")]),
          S("propose_plan", steps=["Raise `NotFound(\"product not found\")` instead of `HttpError(\"...\", 404)`",
                                   "Call GET /products/999 and /products/1 locally; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/products.py", content=FUTURE + """from py_serverless_kit import NotFound

PRODUCTS = {"1": {"id": "1", "name": "Mug"}}


def get_product(event, ctx):
    pid = event.http.path_params["id"]
    if pid not in PRODUCTS:
        raise NotFound("product not found")
    return PRODUCTS[pid]
"""),
          S("invoke_local", function="get-product", method="GET", path="/products/999"),
          S("validate"),
      ],
      final="""`status` is keyword-only on `HttpError`: the signature is `HttpError(message, status=..., details=..., headers=...)` [docs/handlers.md#errors]. Passing `404` as a second positional argument raised a TypeError, which became a 500.

Now it raises `NotFound("product not found")` (`HttpError("product not found", status=404)` would work too).

- Local GET /products/999: status 404, body `{"error": "product not found", "status": 404}`.
- `pskit validate` for aws (staging): valid."""),

    # ------------------------------------------------------------------ 18  alibaba http, naive vs aware datetime
    B(18, provider="alibaba", stage="prod", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: token-tools
provider:
  name: alibaba
  region: cn-hangzhou
functions:
  token-age:
    handler: app.tokens.age
    events:
      - http: GET /age
""",
          "app/__init__.py": "",
          "app/tokens.py": FUTURE + """from datetime import datetime


def age(event, ctx):
    issued = datetime.fromisoformat(event.http.query.get("issued", "2026-01-01T00:00:00"))
    return {"age_days": (event.time - issued).days}
""",
          "requirements.txt": ""}),
      user="/age returns 500: can't subtract offset-naive and offset-aware datetimes. fix",
      steps=[
          S("read_file", path="app/tokens.py"),
          S("invoke_local", function="token-age", method="GET", path="/age?issued=2026-10-01T00:00:00"),
          S("propose_plan", steps=["Treat a timestamp without offset as UTC (`replace(tzinfo=timezone.utc)`) before subtracting from `event.time`",
                                   "Invoke /age locally, validate for alibaba"]),
          S("write_file", path="app/tokens.py", content=FUTURE + """from datetime import datetime, timezone


def age(event, ctx):
    issued = datetime.fromisoformat(event.http.query.get("issued", "2026-01-01T00:00:00"))
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=timezone.utc)
    return {"age_days": (event.time - issued).days}
"""),
          S("invoke_local", function="token-age", method="GET", path="/age?issued=2026-10-01T00:00:00"),
          S("validate"),
      ],
      final="""`event.time` is timezone-aware UTC [docs/handlers.md#event]; `fromisoformat("2026-10-01T00:00:00")` is naive. Naive inputs are now treated as UTC; inputs with an offset are used as they are.

- invoke `/age?issued=2026-10-01T00:00:00`: 200, `{"age_days": 31}`.
- validate (alibaba, prod): valid."""),

    # ------------------------------------------------------------------ 19  huawei schedule, handler name typo
    B(19, provider="huawei", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: weekly-report
provider:
  name: huawei
  region: cn-north-4
functions:
  report:
    handler: app.reports.build_report
    events:
      - schedule: "0 6 * * 1"
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + """
def build_reports(event, ctx):
    ctx.logger.info("weekly report", extra={"stage": ctx.stage})
    return {"report": "weekly", "ok": True}
""",
          "requirements.txt": ""}),
      user="validate says my config is valid, but when I run the report function it says Module 'app.reports' has no attribute 'build_report'. What is wrong?",
      steps=[
          S("get_project"),
          S("read_file", path="app/reports.py"),
          S("invoke_local", function="report", type="schedule"),
          S("propose_plan", steps=["Point `functions.report.handler` at the function that exists: `app.reports.build_reports`",
                                   "Validate for huawei and run `report` locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.report.handler", value="app.reports.build_reports"),
          S("invoke_local", function="report", type="schedule"),
      ],
      final="""A small name mismatch: `pskit.yml` says `app.reports.build_report`, but the function in `app/reports.py` is `build_reports` (with an **s**). `pskit validate` only checks that the module `app/reports.py` exists. It doesn't check the function name, so the error only shows up when the function runs.

I changed the handler in `pskit.yml` to `app.reports.build_reports` (the code is unchanged).

- `pskit validate` for huawei: valid.
- Local run: `{"report": "weekly", "ok": true}`.

You can also check it on **Test** > **▶ Run locally**."""),

    # ------------------------------------------------------------------ 20  tencent http, env var missing
    B(20, provider="tencent", stage="staging", mode="auto", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: uploader
provider:
  name: tencent
  region: ap-shanghai
functions:
  upload-url:
    handler: app.upload.make_url
    events:
      - http: GET /upload-url
""",
          "app/__init__.py": "",
          "app/upload.py": FUTURE + """
def make_url(event, ctx):
    bucket = ctx.env["BUCKET_NAME"]
    name = event.http.query.get("name", "file.bin")
    return {"bucket": bucket, "key": f"incoming/{name}"}
""",
          "requirements.txt": ""}),
      user="upload-url give 500, log say KeyError BUCKET_NAME. in the cloud i set it by hand in console and it work",
      steps=[
          S("get_project"),
          S("invoke_local", function="upload-url", method="GET", path="/upload-url?name=a.png"),
          S("search_docs", query="function environment variables ctx.env",
            docs=[D("docs/handlers.md", "environment-variables", end="Your own `provider.environment`")]),
          S("propose_plan", steps=["Set `functions.upload-url.environment.BUCKET_NAME: uploads-1250000000` in pskit.yml (not a secret)",
                                   "Validate for tencent and call /upload-url locally"]),
          S("set_config", path="functions.upload-url.environment", value={"BUCKET_NAME": "uploads-1250000000"}),
          S("invoke_local", function="upload-url", method="GET", path="/upload-url?name=a.png"),
      ],
      final="""Locally the variable only exists if pskit.yml (or `.env`) sets it. The one you typed in the console is unknown to pskit, and the next deploy can overwrite it. So I put it in the config:

```yaml
functions:
  upload-url:
    environment:
      BUCKET_NAME: uploads-1250000000
```

Change the value if your bucket has another name (Tencent COS names end with your APPID). Your own `functions.<fn>.environment` is added to what pskit injects [docs/handlers.md#environment-variables].

- `pskit validate` for tencent: valid.
- Local call `/upload-url?name=a.png`: 200, `{"bucket": "uploads-1250000000", "key": "incoming/a.png"}`.

Passwords or keys never go here; use `${env:NAME}` for them."""),
]
