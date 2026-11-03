"""Category D (fix a handler bug), batch 3. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"d_debug-{n:04d}", category="d_debug", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 41  aws queue, BatchResult.fail on the class
    B(41, provider="aws", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: thumbnails
provider:
  name: aws
  region: us-east-2
functions:
  resize:
    handler: app.resize.resize
    events:
      - queue: resize-jobs
""",
          "app/__init__.py": "",
          "app/resize.py": FUTURE + """from py_serverless_kit import BatchResult


def resize(event, ctx):
    for record in event.records:
        job = record.json()
        if job.get("width", 0) <= 0:
            BatchResult.fail(record)
            continue
        ctx.logger.info("resized", extra={"image": job["image"], "width": job["width"]})
    return BatchResult
""",
          "requirements.txt": ""}),
      user="""TypeError: BatchResult.fail() missing 1 required positional argument: 'record'
resize worker, only when a job has width 0""",
      steps=[
          S("read_file", path="app/resize.py"),
          S("invoke_local", function="resize", type="queue",
            data=[{"image": "a.png", "width": 320}, {"image": "b.png", "width": 0}]),
          S("search_docs", query="BatchResult fail record example",
            docs=[D("docs/handlers.md", "batchresult", end="return result")]),
          S("propose_plan", steps=["Create one `result = BatchResult()` per call, call `result.fail(record)` on it and `return result`",
                                   "Invoke resize with a good and a bad job; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/resize.py", content=FUTURE + """from py_serverless_kit import BatchResult


def resize(event, ctx):
    result = BatchResult()
    for record in event.records:
        job = record.json()
        if job.get("width", 0) <= 0:
            result.fail(record)
            continue
        ctx.logger.info("resized", extra={"image": job["image"], "width": job["width"]})
    return result
"""),
          S("invoke_local", function="resize", type="queue",
            data=[{"image": "a.png", "width": 320}, {"image": "b.png", "width": 0}]),
          S("validate"),
      ],
      final="""`BatchResult.fail(...)` was called on the **class**, so Python took `record` as `self` and found no record argument. It must be an instance: `result = BatchResult()`, then `result.fail(record)`, then `return result` [docs/handlers.md#batchresult]. The old code also returned the class itself at the end.

- Local run (a.png width 320, b.png width 0): a.png resized, output `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`.
- `pskit validate` for aws: valid.

Only b.png goes back to SQS for retry."""),

    # ------------------------------------------------------------------ 42  azure topic, str + float
    B(42, provider="azure", stage="staging", mode="auto", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: invoicing
provider:
  name: azure
  region: westeurope
functions:
  add-fee:
    handler: app.fees.add_fee
    events:
      - topic: payments
""",
          "app/__init__.py": "",
          "app/fees.py": FUTURE + """FEE = 0.35


def add_fee(event, ctx):
    totals = []
    for record in event.records:
        payment = record.json()
        totals.append(payment["amount"] + FEE)
    return {"totals": totals}
""",
          "requirements.txt": ""}),
      user="add-fee crash: can only concatenate str (not \"float\") to str. the amount come like \"19.90\" from shop",
      steps=[
          S("read_file", path="app/fees.py"),
          S("invoke_local", function="add-fee", type="topic", data=[{"amount": "19.90"}]),
          S("propose_plan", steps=["Convert the amount with `float(payment[\"amount\"])` before adding the fee",
                                   "Invoke add-fee with an amount string; validate for azure"]),
          S("write_file", path="app/fees.py", content=FUTURE + """FEE = 0.35


def add_fee(event, ctx):
    totals = []
    for record in event.records:
        payment = record.json()
        totals.append(round(float(payment["amount"]) + FEE, 2))
    return {"totals": totals}
"""),
          S("invoke_local", function="add-fee", type="topic", data=[{"amount": "19.90"}]),
          S("validate"),
      ],
      final="""The shop sends `"amount": "19.90"` as a **string**. `record.json()` keeps it a string, and string + float fails. Now it does `float(payment["amount"])` and rounds to 2 decimals.

- Test with `{"amount": "19.90"}`: `{"totals": [20.25]}`.
- `pskit validate` for azure (staging): valid.

For real money, `decimal.Decimal` is safer than float; tell me if you want that."""),

    # ------------------------------------------------------------------ 43  gcp http, forgot return -> 204
    B(43, provider="gcp", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: tips
provider:
  name: gcp
  region: us-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  tip:
    handler: app.tips.tip
    events:
      - http: GET /tip
""",
          "app/__init__.py": "",
          "app/tips.py": FUTURE + """
def tip(event, ctx):
    bill = float(event.http.query.get("bill", "0"))
    result = {"bill": bill, "tip": round(bill * 0.15, 2)}
    ctx.logger.info("tip computed", extra=result)
""",
          "requirements.txt": ""}),
      user="my tip calculator shows nothing. the test says status 204 and there is no body. the log line says tip computed so it works?",
      steps=[
          S("read_file", path="app/tips.py"),
          S("invoke_local", function="tip", method="GET", path="/tip?bill=40"),
          S("search_docs", query="return None 204 no content",
            docs=[D("docs/handlers.md", "returning-a-response", end="| `None`")]),
          S("propose_plan", steps=["Add `return result` at the end of `tip` in `app/tips.py`",
                                   "Test /tip?bill=40 and validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tips.py", content=FUTURE + """
def tip(event, ctx):
    bill = float(event.http.query.get("bill", "0"))
    result = {"bill": bill, "tip": round(bill * 0.15, 2)}
    ctx.logger.info("tip computed", extra=result)
    return result
"""),
          S("invoke_local", function="tip", method="GET", path="/tip?bill=40"),
          S("validate"),
      ],
      final="""The calculation works, but the function never **returns** the result. A Python function without `return` gives `None`, and pskit turns `None` into `204 No Content` [docs/handlers.md#returning-a-response].

I added `return result` at the end.

- Test `/tip?bill=40`: status 200, `{"bill": 40.0, "tip": 6.0}`.
- `pskit validate` for gcp: valid."""),

    # ------------------------------------------------------------------ 44  onprem smtp, to is a list
    B(44, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": """service: helpdesk
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8130
resources:
  inbound-mail:
    type: smtp
    external: true
    connection: {host: 192.0.2.10, port: 25, domains: inbound.example.com}
functions:
  on-mail:
    handler: app.mail.on_mail
    events:
      - smtp: inbound-mail
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """QUEUES = {"help@inbound.example.com": "support", "billing@inbound.example.com": "finance"}


def on_mail(event, ctx):
    mail = event.data
    team = QUEUES.get(mail["to"].lower(), "triage")
    ctx.logger.info("ticket", extra={"team": team, "subject": mail["subject"]})
    return {"team": team}
""",
          "requirements.txt": ""}),
      user="on-mail should route each incoming mail to a team by its recipient address (case-insensitive): help@ -> support, billing@ -> finance, anything else -> triage. A test mail to Help@Inbound.example.com fails with AttributeError: 'list' object has no attribute 'lower'. Please fix and test with that address.",
      steps=[
          S("read_file", path="app/mail.py"),
          S("invoke_local", function="on-mail", type="smtp",
            data={"from": "ann@example.org", "to": ["Help@Inbound.example.com"], "subject": "Printer", "text": "broken"}),
          S("search_docs", query="smtp event data to cc list fields",
            docs=[D("docs/smtp/README.md", "what-the-handler-receives", start="| Field |", end="| `bcc`")]),
          S("propose_plan", steps=["Treat `mail[\"to\"]` as a list: use the first address that matches a team, else `triage`",
                                   "Invoke on-mail with a test mail to Help@Inbound.example.com; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/mail.py", content=FUTURE + """QUEUES = {"help@inbound.example.com": "support", "billing@inbound.example.com": "finance"}


def on_mail(event, ctx):
    mail = event.data
    team = "triage"
    for address in mail["to"]:
        if address.lower() in QUEUES:
            team = QUEUES[address.lower()]
            break
    ctx.logger.info("ticket", extra={"team": team, "subject": mail["subject"]})
    return {"team": team}
"""),
          S("invoke_local", function="on-mail", type="smtp",
            data={"from": "ann@example.org", "to": ["Help@Inbound.example.com"], "subject": "Printer", "text": "broken"}),
          S("validate"),
      ],
      final="""`to` is an **address list** (a mail can have several recipients), not a string [docs/smtp/README.md#what-the-handler-receives]. The handler now checks each address in lower case and takes the first one that maps to a team, else `triage`.

- Test mail to `Help@Inbound.example.com`: logged `ticket`, returned `{"team": "support"}`.
- `pskit validate` for onprem, prod: valid.

If you want to route on the addresses this server really received (including Bcc), use `mail["envelope"]["rcpt_to"]` instead of `to`."""),

    # ------------------------------------------------------------------ 45  alibaba storage, AWS action names
    B(45, provider="alibaba", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: media-index
provider:
  name: alibaba
  region: cn-shenzhen
functions:
  index-media:
    handler: app.media.index
    events:
      - storage:
          bucket: media-uploads
          events: [created, deleted]
""",
          "app/__init__.py": "",
          "app/media.py": FUTURE + """
def index(event, ctx):
    added, removed = [], []
    for record in event.records:
        if record.action == "ObjectCreated:Put":
            added.append(record.key)
        elif record.action == "ObjectRemoved:Delete":
            removed.append(record.key)
    return {"added": added, "removed": removed}
""",
          "requirements.txt": ""}),
      user="Ported from S3: I check record.action against 'ObjectCreated:Put' / 'ObjectRemoved:Delete'. No error, but nothing ever gets indexed, both lists come back empty. What are the action values in pskit?",
      steps=[
          S("read_file", path="app/media.py"),
          S("invoke_local", function="index-media", type="storage",
            data=[{"key": "video.mp4", "action": "created"}, {"key": "old.mp4", "action": "deleted"}]),
          S("search_docs", query="record action created deleted storage",
            docs=[D("docs/handlers.md", "record", start="| `bucket`, `key`", end="| `bucket`, `key`")]),
          S("propose_plan", steps=["Compare `record.action` with the portable values `\"created\"` and `\"deleted\"`",
                                   "Invoke index-media with one created and one deleted object; validate for alibaba"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/media.py", content=FUTURE + """
def index(event, ctx):
    added, removed = [], []
    for record in event.records:
        if record.action == "created":
            added.append(record.key)
        elif record.action == "deleted":
            removed.append(record.key)
    return {"added": added, "removed": removed}
"""),
          S("invoke_local", function="index-media", type="storage",
            data=[{"key": "video.mp4", "action": "created"}, {"key": "old.mp4", "action": "deleted"}]),
          S("validate"),
      ],
      final="""pskit normalises the S3/OSS/GCS event names: `record.action` is just `"created"` or `"deleted"` on every provider [docs/handlers.md#record]. Your S3 names never matched, so both lists stayed empty.

Now the handler compares with `"created"` / `"deleted"`.

- Before: `{"added": [], "removed": []}`.
- After (one created, one deleted object): `{"added": ["video.mp4"], "removed": ["old.mp4"]}`.
- `pskit validate` for alibaba: valid."""),

    # ------------------------------------------------------------------ 46  huawei topic, event.data instead of records
    B(46, provider="huawei", stage="prod", mode="auto", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: ops-events
provider:
  name: huawei
  region: cn-north-4
functions:
  on-alarm:
    handler: app.alarms.on_alarm
    events:
      - topic: alarms
""",
          "app/__init__.py": "",
          "app/alarms.py": FUTURE + """
def on_alarm(event, ctx):
    level = event.data.get("level", "info")
    ctx.logger.warning("alarm", extra={"level": level})
    return {"level": level}
""",
          "requirements.txt": ""}),
      user="""AttributeError: 'NoneType' object has no attribute 'get'
on-alarm, line: level = event.data.get("level", "info")""",
      steps=[
          S("read_file", path="app/alarms.py"),
          S("invoke_local", function="on-alarm", type="topic", data=[{"level": "critical", "host": "db-1"}]),
          S("propose_plan", steps=["Loop over `event.records` and read each message with `record.json()`; `event.data` is not used for topics",
                                   "Invoke on-alarm with one topic message, validate for huawei"]),
          S("write_file", path="app/alarms.py", content=FUTURE + """
def on_alarm(event, ctx):
    levels = []
    for record in event.records:
        level = record.json().get("level", "info")
        ctx.logger.warning("alarm", extra={"level": level})
        levels.append(level)
    return {"levels": levels}
"""),
          S("invoke_local", function="on-alarm", type="topic", data=[{"level": "critical", "host": "db-1"}]),
          S("validate"),
      ],
      final="""Topic messages arrive in `event.records`; `event.data` is only for schedule, invoke and workflow events [docs/handlers.md#event], so it is `None` here.

Now each record is read with `record.json()`.

- invoke with `{"level": "critical", "host": "db-1"}`: WARNING `alarm` logged, `{"levels": ["critical"]}`.
- validate (huawei, prod): valid."""),

    # ------------------------------------------------------------------ 47  tencent storage, key without folder
    B(47, provider="tencent", stage="staging", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: report-drop
provider:
  name: tencent
  region: ap-beijing
functions:
  on-report:
    handler: app.reports.on_report
    events:
      - storage: reports-1250000000
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + """
def on_report(event, ctx):
    names = []
    for record in event.records:
        names.append(record.key.split("/")[1])
    return {"files": names}
""",
          "requirements.txt": ""}),
      user="on-report takes the file name from the object key. Keys like `2026/q3.pdf` work, but a file uploaded to the bucket root (`q3.pdf`) crashes with `IndexError: list index out of range`. I need just the file name in both cases, and nested keys like `2026/10/q3.pdf` should give `q3.pdf` too.",
      steps=[
          S("read_file", path="app/reports.py"),
          S("invoke_local", function="on-report", type="storage", data={"bucket": "reports-1250000000", "key": "q3.pdf"}),
          S("propose_plan", steps=["Take the last part of the key with `record.key.rsplit(\"/\", 1)[-1]`",
                                   "Invoke on-report with `q3.pdf` and `2026/10/q3.pdf`; validate for tencent"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/reports.py", content=FUTURE + """
def on_report(event, ctx):
    names = []
    for record in event.records:
        names.append(record.key.rsplit("/", 1)[-1])
    return {"files": names}
"""),
          S("invoke_local", function="on-report", type="storage",
            data=[{"bucket": "reports-1250000000", "key": "q3.pdf"}, {"bucket": "reports-1250000000", "key": "2026/10/q3.pdf"}]),
          S("validate"),
      ],
      final="""`"q3.pdf".split("/")` has only one element, so `[1]` fails. For `2026/10/q3.pdf` it also returned `10`, not the file name. Now the handler takes the part after the last `/`:

```python
names.append(record.key.rsplit("/", 1)[-1])
```

- Local run with `q3.pdf` and `2026/10/q3.pdf`: `{"files": ["q3.pdf", "q3.pdf"]}`.
- `pskit validate` for tencent (staging): valid. The bucket name already has the required `<name>-<APPID>` form [docs/events.md#storage]."""),

    # ------------------------------------------------------------------ 48  digitalocean http, form() on JSON body
    B(48, provider="digitalocean", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: newsletter
provider:
  name: digitalocean
  region: sfo3
  options:
    namespace: ${env:DO_NAMESPACE, fn-news}
functions:
  subscribe:
    handler: app.news.subscribe
    events:
      - http: POST /subscribe
""",
          "app/__init__.py": "",
          "app/news.py": FUTURE + """
def subscribe(event, ctx):
    fields = event.http.form()
    return {"subscribed": fields["email"]}, 201
""",
          "requirements.txt": ""}),
      user="subscribe work from old html form but from our new app (it send json) give 500 KeyError email. can it accept both?",
      steps=[
          S("read_file", path="app/news.py"),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe", data={"email": "kai@example.com"}),
          S("search_docs", query="content_type form json body",
            docs=[D("docs/handlers.md", "httprequest", start="| `content_type`", end="| `form()`")]),
          S("propose_plan", steps=["Use `event.http.json()` when `content_type` is `application/json`, otherwise `form()`",
                                   "POST JSON to /subscribe locally, validate for digitalocean"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/news.py", content=FUTURE + """
def subscribe(event, ctx):
    if event.http.content_type == "application/json":
        fields = event.http.json()
    else:
        fields = event.http.form()
    return {"subscribed": fields["email"]}, 201
"""),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe", data={"email": "kai@example.com"}),
          S("validate"),
      ],
      final="""`form()` only understands `application/x-www-form-urlencoded`. A JSON body parsed as a form has no `email` key. Now the handler checks `event.http.content_type`: JSON goes through `json()`, everything else through `form()` [docs/handlers.md#httprequest].

- Local POST with JSON `{"email": "kai@example.com"}`: status 201, `{"subscribed": "kai@example.com"}`.
- `pskit validate` for digitalocean: valid (warning: `doctl` not installed, only needed to deploy).

I could only test the JSON case here. To test the form case in a terminal: `pskit invoke -f subscribe --method POST --path /subscribe -H "Content-Type: application/x-www-form-urlencoded" -d "email=kai@example.com"`."""),

    # ------------------------------------------------------------------ 49  oracle http, int path param vs str keys -> always 404
    B(49, provider="oracle", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: order-status
provider:
  name: oracle
  region: uk-london-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..example}
    subnet_ids: [ocid1.subnet.oc1..example]
    image_repository: lhr.ocir.io/example/order-status
functions:
  status:
    handler: app.status.get_status
    events:
      - http: GET /orders/{id}/status
""",
          "app/__init__.py": "",
          "app/status.py": FUTURE + """from py_serverless_kit import NotFound

ORDERS = {"7": "shipped", "8": "packing"}


def get_status(event, ctx):
    order_id = int(event.http.path_params["id"])
    status = ORDERS.get(order_id)
    if status is None:
        raise NotFound("unknown order")
    return {"order": order_id, "status": status}
""",
          "requirements.txt": ""}),
      user="GET /orders/7/status returns 404 \"unknown order\" although order 7 is in ORDERS. Every id returns 404. Expected 200 with {\"order\": 7, \"status\": \"shipped\"} for known ids and 404 only for unknown ones.",
      steps=[
          S("read_file", path="app/status.py"),
          S("invoke_local", function="status", method="GET", path="/orders/7/status"),
          S("search_docs", query="path_params type string",
            docs=[D("docs/handlers.md", "httprequest", start="| `path_params`", end="| `path_params`")]),
          S("propose_plan", steps=["Look up `ORDERS` with the string id from `path_params`, and convert to int only for the response",
                                   "Invoke GET /orders/7/status and /orders/99/status; validate for oracle (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/status.py", content=FUTURE + """from py_serverless_kit import NotFound

ORDERS = {"7": "shipped", "8": "packing"}


def get_status(event, ctx):
    order_id = event.http.path_params["id"]
    status = ORDERS.get(order_id)
    if status is None:
        raise NotFound("unknown order")
    return {"order": int(order_id), "status": status}
"""),
          S("invoke_local", function="status", method="GET", path="/orders/99/status"),
          S("invoke_local", function="status", method="GET", path="/orders/7/status"),
          S("validate"),
      ],
      final="""Type mismatch: `path_params` values are strings [docs/handlers.md#httprequest], and `ORDERS` has string keys (`"7"`). The code turned the id into `int` 7 **before** the lookup, so `ORDERS.get(7)` never matched.

Now the lookup uses the string, and `int()` is only applied in the response.

- GET /orders/99/status: 404 `{"error": "unknown order", "status": 404}`.
- GET /orders/7/status: 200 `{"order": 7, "status": "shipped"}`.
- `pskit validate` for oracle, prod: valid. It shows the API Gateway IAM policy WARNING, which you need to handle in OCI before deploy.

One thing to watch: a non-numeric id that happens to be a key would now fail in `int()`. With only numeric keys that can't happen."""),

    # ------------------------------------------------------------------ 50  ibm http, sort KeyError
    B(50, provider="ibm", stage="dev", mode="auto", page="Test", persona="beginner",
      sources=[],
      project=dict(files={
          "pskit.yml": """service: shop-list
provider:
  name: ibm
  region: eu-gb
  runtime: python3.11
functions:
  products:
    handler: app.shop.products
    events:
      - http: GET /products
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + """PRODUCTS = [
    {"name": "Lamp", "price": 30},
    {"name": "Gift card"},
    {"name": "Chair", "price": 85},
]


def products(event, ctx):
    items = sorted(PRODUCTS, key=lambda p: p["price"])
    return {"products": [p["name"] for p in items]}
""",
          "requirements.txt": ""}),
      user="I want my products sorted by price, cheapest first. But the page gives error 500 now. The gift card has no price, maybe that's it?",
      steps=[
          S("read_file", path="app/shop.py"),
          S("invoke_local", function="products", method="GET", path="/products"),
          S("propose_plan", steps=["Sort with a key that puts products without a price at the end instead of failing",
                                   "Test GET /products and validate for ibm"]),
          S("write_file", path="app/shop.py", content=FUTURE + """PRODUCTS = [
    {"name": "Lamp", "price": 30},
    {"name": "Gift card"},
    {"name": "Chair", "price": 85},
]


def products(event, ctx):
    items = sorted(PRODUCTS, key=lambda p: (p.get("price") is None, p.get("price") or 0))
    return {"products": [p["name"] for p in items]}
"""),
          S("invoke_local", function="products", method="GET", path="/products"),
          S("validate"),
      ],
      final="""Yes, that's it. `p["price"]` raised `KeyError: 'price'` for the gift card, and any error becomes a 500. Now products without a price are sorted to the end, and the others go cheapest first.

- Test GET /products: status 200, `["Lamp", "Chair", "Gift card"]`.
- `pskit validate` for ibm: valid."""),

    # ------------------------------------------------------------------ 51  aws schedule, memory_mb None
    B(51, provider="aws", stage="staging", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: exporter
provider:
  name: aws
  region: ca-central-1
functions:
  export:
    handler: app.export.export
    memory: 1024
    events:
      - schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/export.py": FUTURE + """
def export(event, ctx):
    chunk_rows = int(ctx.memory_mb * 0.8) * 100
    ctx.logger.info("export", extra={"chunk_rows": chunk_rows})
    return {"chunk_rows": chunk_rows}
""",
          "requirements.txt": ""}),
      user="export: unsupported operand NoneType * float on ctx.memory_mb under pskit invoke. fall back to 1024",
      steps=[
          S("read_file", path="app/export.py"),
          S("invoke_local", function="export", type="schedule"),
          S("propose_plan", steps=["Use `(ctx.memory_mb or 1024)`; memory_mb is None when the platform doesn't report it",
                                   "Invoke export, validate for aws"]),
          S("write_file", path="app/export.py", content=FUTURE + """
def export(event, ctx):
    memory = ctx.memory_mb or 1024
    chunk_rows = int(memory * 0.8) * 100
    ctx.logger.info("export", extra={"chunk_rows": chunk_rows})
    return {"chunk_rows": chunk_rows}
"""),
          S("invoke_local", function="export", type="schedule"),
          S("validate"),
      ],
      final="""`ctx.memory_mb` is only set "when the platform reports it" [docs/handlers.md#context]; under `pskit invoke` it is `None`. Fallback added: `memory = ctx.memory_mb or 1024`.

- invoke: `{"chunk_rows": 81900}`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 52  gcp queue, async helper never awaited
    B(52, provider="gcp", stage="prod", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#handler-signatures", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: webhooks-out
provider:
  name: gcp
  region: europe-west4
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  deliver:
    handler: app.deliver.deliver
    events:
      - queue: outgoing-hooks
""",
          "app/__init__.py": "",
          "app/deliver.py": FUTURE + """import asyncio

from py_serverless_kit import BatchResult


async def send(record, ctx):
    await asyncio.sleep(0)
    ctx.logger.info("delivered", extra={"url": record.json()["url"]})


def deliver(event, ctx):
    result = BatchResult()
    for record in event.records:
        send(record, ctx)
    return result
""",
          "requirements.txt": ""}),
      user="In Lambda I wrapped this in asyncio.run myself; here I removed that since the docs say coroutines are awaited. Now the queue worker 'succeeds' but nothing is delivered and I only see a RuntimeWarning about a coroutine never awaited. What did I miss?",
      steps=[
          S("read_file", path="app/deliver.py"),
          S("invoke_local", function="deliver", type="queue", data=[{"url": "https://hooks.example.com/a"}]),
          S("search_docs", query="async handler coroutine awaited",
            docs=[D("docs/handlers.md", "handler-signatures")]),
          S("propose_plan", steps=["Make `deliver` an `async def` and `await send(record, ctx)` for each message",
                                   "Invoke deliver with one message (expect a `delivered` log line) and validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/deliver.py", content=FUTURE + """import asyncio

from py_serverless_kit import BatchResult


async def send(record, ctx):
    await asyncio.sleep(0)
    ctx.logger.info("delivered", extra={"url": record.json()["url"]})


async def deliver(event, ctx):
    result = BatchResult()
    for record in event.records:
        await send(record, ctx)
    return result
"""),
          S("invoke_local", function="deliver", type="queue", data=[{"url": "https://hooks.example.com/a"}]),
          S("validate"),
      ],
      final="""pskit awaits the coroutine your **handler** returns [docs/handlers.md#handler-signatures]. Your handler was a plain `def`, though, and it called the async `send()` without `await`. That only creates a coroutine object, and it never runs.

Fix: `async def deliver(...)` and `await send(record, ctx)`.

- Before: no `delivered` log, just the RuntimeWarning, `batchItemFailures: []`.
- After: `delivered` is logged for the message, `batchItemFailures: []`, no warning.
- `pskit validate` for gcp, prod: valid.

On GCP a failed message retries the whole delivery anyway; partial batch retry is AWS/on-prem only [docs/events.md#queue]."""),

    # ------------------------------------------------------------------ 53  azure storage, Path not imported
    B(53, provider="azure", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[],
      project=dict(files={
          "pskit.yml": """service: doc-sorter
provider:
  name: azure
  region: swedencentral
functions:
  sort-doc:
    handler: app.sorter.sort_doc
    events:
      - storage: incoming-docs
""",
          "app/__init__.py": "",
          "app/sorter.py": FUTURE + """KINDS = {".pdf": "documents", ".jpg": "images", ".png": "images"}


def sort_doc(event, ctx):
    placed = {}
    for record in event.records:
        suffix = Path(record.key).suffix.lower()
        placed[record.key] = KINDS.get(suffix, "other")
    return placed
""",
          "requirements.txt": ""}),
      user="sort-doc error name 'Path' is not defined. pls fix",
      steps=[
          S("read_file", path="app/sorter.py"),
          S("invoke_local", function="sort-doc", type="storage", data={"bucket": "incoming-docs", "key": "scan.PDF"}),
          S("propose_plan", steps=["Add `from pathlib import PurePosixPath` and use it for the key (keys always use `/`)",
                                   "Run sort-doc with a storage event, validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sorter.py", content=FUTURE + """from pathlib import PurePosixPath

KINDS = {".pdf": "documents", ".jpg": "images", ".png": "images"}


def sort_doc(event, ctx):
    placed = {}
    for record in event.records:
        suffix = PurePosixPath(record.key).suffix.lower()
        placed[record.key] = KINDS.get(suffix, "other")
    return placed
"""),
          S("invoke_local", function="sort-doc", type="storage", data={"bucket": "incoming-docs", "key": "scan.PDF"}),
          S("validate"),
      ],
      final="""`Path` was used but never imported. I added `from pathlib import PurePosixPath` and use it, because blob keys always use `/` whatever OS runs the code.

- Test with `scan.PDF`: `{"scan.PDF": "documents"}`.
- `pskit validate` for azure: valid."""),

    # ------------------------------------------------------------------ 54  onprem http, lowercase method compare
    B(54, provider="onprem", stage="staging", mode="auto", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: events-signup
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8140
functions:
  rsvp:
    handler: app.rsvp.rsvp
    events:
      - http:
          path: /rsvp
          method: ANY
""",
          "app/__init__.py": "",
          "app/rsvp.py": FUTURE + """
def rsvp(event, ctx):
    if event.http.method == "post":
        guest = event.http.json()
        return {"confirmed": guest.get("name")}, 201
    return {"error": "use POST to sign up"}, 405
""",
          "requirements.txt": ""}),
      user="""POST /rsvp -> 405 {"error": "use POST to sign up"}
i AM using POST""",
      steps=[
          S("read_file", path="app/rsvp.py"),
          S("invoke_local", function="rsvp", method="POST", path="/rsvp", data={"name": "Jo"}),
          S("search_docs", query="http method upper case",
            docs=[D("docs/handlers.md", "httprequest", start="| `method`", end="| `method`")]),
          S("propose_plan", steps=["Compare with `\"POST\"`: `event.http.method` is upper case",
                                   "Invoke POST /rsvp, validate for onprem"]),
          S("write_file", path="app/rsvp.py", content=FUTURE + """
def rsvp(event, ctx):
    if event.http.method == "POST":
        guest = event.http.json()
        return {"confirmed": guest.get("name")}, 201
    return {"error": "use POST to sign up"}, 405
"""),
          S("invoke_local", function="rsvp", method="POST", path="/rsvp", data={"name": "Jo"}),
          S("validate"),
      ],
      final="""`event.http.method` is always upper case [docs/handlers.md#httprequest], so `== "post"` was never true and every request fell through to your own 405. Changed to `== "POST"`.

- invoke POST /rsvp `{"name": "Jo"}`: 201, `{"confirmed": "Jo"}`.
- validate (onprem, staging): valid.

Alternative: route `method: POST` instead of `ANY`, and pskit answers other methods with 405 itself."""),

    # ------------------------------------------------------------------ 55  alibaba http, json.loads on empty body -> 500
    B(55, provider="alibaba", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: todo-api
provider:
  name: alibaba
  region: ap-southeast-1
functions:
  add-todo:
    handler: app.todo.add
    events:
      - http: POST /todos
""",
          "app/__init__.py": "",
          "app/todo.py": FUTURE + """import json


def add(event, ctx):
    todo = json.loads(event.http.text())
    return {"added": todo["title"]}, 201
""",
          "requirements.txt": ""}),
      user="If someone sends an empty request to /todos my function crashes with 500. I'd like a normal error saying the body is wrong. How?",
      steps=[
          S("read_file", path="app/todo.py"),
          S("invoke_local", function="add-todo", method="POST", path="/todos"),
          S("search_docs", query="invalid json body 400",
            docs=[D("docs/handlers.md", "httprequest", start="| `json(default=...)`", end="| `json(default=...)`")]),
          S("propose_plan", steps=["Use `event.http.json()` instead of `json.loads(...)`: bad or empty JSON then gives a 400",
                                   "Test POST /todos with an empty body and with a real todo; validate for alibaba"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/todo.py", content=FUTURE + """
def add(event, ctx):
    todo = event.http.json()
    return {"added": todo["title"]}, 201
"""),
          S("invoke_local", function="add-todo", method="POST", path="/todos"),
          S("invoke_local", function="add-todo", method="POST", path="/todos", data={"title": "water plants"}),
          S("validate"),
      ],
      final="""`json.loads("")` raises a normal Python error, which pskit turns into 500. pskit's own `event.http.json()` raises `BadRequest` instead, so bad input gives a 400 [docs/handlers.md#httprequest].

- Empty POST /todos: status 400, `{"error": "Request body is empty, expected JSON", "status": 400}`.
- POST with `{"title": "water plants"}`: status 201, `{"added": "water plants"}`.
- `pskit validate` for alibaba (staging): valid.

A body without `title` would still be a 500. Tell me if you want a 400 for that too."""),

    # ------------------------------------------------------------------ 56  huawei http, {path+} param name
    B(56, provider="huawei", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: file-server
provider:
  name: huawei
  region: cn-south-1
  options:
    apig_instance_id: ${env:HUAWEI_APIG_ID, apig-demo}
functions:
  get-file:
    handler: app.files.get_file
    events:
      - http: "GET /files/{path+}"
""",
          "app/__init__.py": "",
          "app/files.py": FUTURE + """
def get_file(event, ctx):
    path = event.http.path_params["path+"]
    return {"path": path, "parts": path.split("/")}
""",
          "requirements.txt": ""}),
      user="GET /files/{path+}: KeyError 'path+' in path_params. key name?",
      steps=[
          S("read_file", path="app/files.py"),
          S("invoke_local", function="get-file", method="GET", path="/files/docs/2026/plan.pdf"),
          S("propose_plan", steps=["Use `path_params[\"path\"]`: the `+` is not part of the name",
                                   "Invoke GET /files/docs/2026/plan.pdf, validate for huawei"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/files.py", content=FUTURE + """
def get_file(event, ctx):
    path = event.http.path_params["path"]
    return {"path": path, "parts": path.split("/")}
"""),
          S("invoke_local", function="get-file", method="GET", path="/files/docs/2026/plan.pdf"),
          S("validate"),
      ],
      final="""The key is `path`; `{name+}` only marks the greedy tail [docs/handlers.md#httprequest]. Fix: `event.http.path_params["path"]`.

- GET /files/docs/2026/plan.pdf: 200, `path` = `docs/2026/plan.pdf`, parts `["docs", "2026", "plan.pdf"]`.
- validate (huawei): valid."""),

    # ------------------------------------------------------------------ 57  tencent http, tuple headers as str
    B(57, provider="tencent", stage="prod", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: rates
provider:
  name: tencent
  region: ap-hongkong
functions:
  fx-rate:
    handler: app.rates.fx
    events:
      - http: GET /fx
""",
          "app/__init__.py": "",
          "app/rates.py": FUTURE + """RATES = {"USD": 1.0, "EUR": 0.92}


def fx(event, ctx):
    cur = event.http.query.get("cur", "EUR")
    return {"cur": cur, "rate": RATES.get(cur)}, 200, "no-cache"
""",
          "requirements.txt": ""}),
      user="i want no cache header on fx-rate, i add \"no-cache\" as third in return and now ValueError dictionary update sequence element #0 has length 1",
      steps=[
          S("read_file", path="app/rates.py"),
          S("invoke_local", function="fx-rate", method="GET", path="/fx?cur=EUR"),
          S("search_docs", query="return body status headers tuple",
            docs=[D("docs/handlers.md", "returning-a-response", start="| `(body, status)`", end="| `(body, status)`")]),
          S("propose_plan", steps=["Pass the headers as a dict: `return {...}, 200, {\"cache-control\": \"no-cache\"}`",
                                   "Invoke GET /fx?cur=EUR, validate for tencent (prod)"]),
          S("write_file", path="app/rates.py", content=FUTURE + """RATES = {"USD": 1.0, "EUR": 0.92}


def fx(event, ctx):
    cur = event.http.query.get("cur", "EUR")
    return {"cur": cur, "rate": RATES.get(cur)}, 200, {"cache-control": "no-cache"}
"""),
          S("invoke_local", function="fx-rate", method="GET", path="/fx?cur=EUR"),
          S("validate"),
      ],
      final="""The third item of `(body, status, headers)` must be a **dict** of headers [docs/handlers.md#returning-a-response]. A plain string can't be merged into the headers, so you got that ValueError. Now:

```python
return {"cur": cur, "rate": RATES.get(cur)}, 200, {"cache-control": "no-cache"}
```

- Local GET /fx?cur=EUR: status 200, header `cache-control: no-cache`, body `{"cur": "EUR", "rate": 0.92}`.
- `pskit validate` for tencent (prod): valid."""),

    # ------------------------------------------------------------------ 58  digitalocean schedule, await on logger
    B(58, provider="digitalocean", stage="staging", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#logging"],
      project=dict(files={
          "pskit.yml": """service: uptime
provider:
  name: digitalocean
  region: lon1
  options:
    namespace: ${env:DO_NAMESPACE, fn-uptime}
functions:
  probe:
    handler: app.probe.probe
    events:
      - schedule: 5 minutes
""",
          "app/__init__.py": "",
          "app/probe.py": FUTURE + """import asyncio

SITES = ["https://www.example.com", "https://shop.example.com"]


async def check(url):
    await asyncio.sleep(0)
    return {"url": url, "up": True}


async def probe(event, ctx):
    results = await asyncio.gather(*(check(u) for u in SITES))
    await ctx.logger.info("probe done", extra={"sites": len(results)})
    return {"up": [r["url"] for r in results if r["up"]]}
""",
          "requirements.txt": ""}),
      user="The async `probe` handler checks two sites with asyncio.gather. The checks run and 'probe done' even appears in the log, but then the function fails with `TypeError: object NoneType can't be used in 'await' expression`. Please fix it without removing the parallel checks.",
      steps=[
          S("read_file", path="app/probe.py"),
          S("invoke_local", function="probe", type="schedule"),
          S("search_docs", query="ctx.logger info extra",
            docs=[D("docs/handlers.md", "logging", words=40)]),
          S("propose_plan", steps=["Remove `await` before `ctx.logger.info(...)`: logging is synchronous and returns None",
                                   "Run probe as a schedule event and validate for digitalocean (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/probe.py", content=FUTURE + """import asyncio

SITES = ["https://www.example.com", "https://shop.example.com"]


async def check(url):
    await asyncio.sleep(0)
    return {"url": url, "up": True}


async def probe(event, ctx):
    results = await asyncio.gather(*(check(u) for u in SITES))
    ctx.logger.info("probe done", extra={"sites": len(results)})
    return {"up": [r["url"] for r in results if r["up"]]}
"""),
          S("invoke_local", function="probe", type="schedule"),
          S("validate"),
      ],
      final="""`ctx.logger.info(...)` is a normal (synchronous) call. It writes the log line, which is why you saw "probe done", and returns `None`. `await None` then raised the TypeError. I removed that one `await`; the `asyncio.gather` checks are unchanged.

- Local schedule run: "probe done" logged, `{"up": ["https://www.example.com", "https://shop.example.com"]}`.
- `pskit validate` for digitalocean (staging): valid (only the `doctl` deploy warning).

Logger usage: [docs/handlers.md#logging]."""),

    # ------------------------------------------------------------------ 59  cloudflare http, string repetition
    B(59, provider="cloudflare", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: tiny-math
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, demo-account}
functions:
  double:
    handler: app.math.double
    events:
      - http: GET /double
""",
          "app/__init__.py": "",
          "app/math.py": FUTURE + """
def double(event, ctx):
    n = event.http.query.get("n", 1)
    return {"n": n, "double": n * 2}
""",
          "requirements.txt": ""}),
      user="lol /double?n=5 give me 55 not 10",
      steps=[
          S("read_file", path="app/math.py"),
          S("invoke_local", function="double", method="GET", path="/double?n=5"),
          S("propose_plan", steps=["Convert `n` to a number: `int(event.http.query.get(\"n\", \"1\"))`",
                                   "Test /double?n=5 and validate for cloudflare"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/math.py", content=FUTURE + """
def double(event, ctx):
    n = int(event.http.query.get("n", "1"))
    return {"n": n, "double": n * 2}
"""),
          S("invoke_local", function="double", method="GET", path="/double?n=5"),
          S("validate"),
      ],
      final="""Query values are always strings (`dict[str, str]` [docs/handlers.md#httprequest]), and in Python `"5" * 2` is `"55"`. Now `n` goes through `int()` first.

- Test /double?n=5: 200, `{"n": 5, "double": 10}`.
- `pskit validate` for cloudflare: valid (Pyodide note only).

`?n=abc` would still give a 500. Tell me if you want a 400 for that."""),

    # ------------------------------------------------------------------ 60  oracle storage, returns a generator
    B(60, provider="oracle", stage="staging", mode="auto", page="Test", persona="terse_expert",
      sources=["docs/events.md#storage", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: archive
provider:
  name: oracle
  region: ap-tokyo-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..example}
    subnet_ids: [ocid1.subnet.oc1..example]
    image_repository: nrt.ocir.io/example/archive
functions:
  on-archive:
    handler: app.archive.on_archive
    events:
      - storage: archive-in
""",
          "app/__init__.py": "",
          "app/archive.py": FUTURE + """
def on_archive(event, ctx):
    return (r.key for r in event.records if r.key.endswith(".zip"))
""",
          "requirements.txt": ""}),
      user="on-archive output is \"<generator object ...>\" instead of the zip keys. fix",
      steps=[
          S("read_file", path="app/archive.py"),
          S("invoke_local", function="on-archive", type="storage", data=[{"key": "a.zip"}, {"key": "b.txt"}]),
          S("propose_plan", steps=["Return a list (`[...]`) inside a dict instead of a generator expression",
                                   "Invoke with a .zip and a .txt key; validate for oracle"]),
          S("write_file", path="app/archive.py", content=FUTURE + """
def on_archive(event, ctx):
    return {"zips": [r.key for r in event.records if r.key.endswith(".zip")]}
"""),
          S("invoke_local", function="on-archive", type="storage", data=[{"key": "a.zip"}, {"key": "b.txt"}]),
          S("validate"),
      ],
      final="""`( ... for ... )` is a lazy generator, so it can't be serialised and only its repr was printed. For non-HTTP events the return value goes back to the caller as it is [docs/handlers.md#returning-a-response]. Now it returns `{"zips": [...]}`.

- invoke (a.zip, b.txt): `{"zips": ["a.zip"]}`.
- validate (oracle, staging): valid.

Filtering in the handler is right on Oracle, because storage `suffix` filters are not applied there [docs/events.md#storage]."""),
]
