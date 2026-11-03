"""Category B (build / add), batch 37 (aws / gcp / azure): pasted errors, informal requests, AWS migrators. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 721
    B(721, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: order-desk
provider:
  name: aws
  region: eu-west-1
functions:
  create-order:
    handler: app.orders.create
    events:
    - http: POST /orders
  orders:
    handler: app.orders.list_orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """
ORDERS = [{"id": "o-1", "total": 12.5}, {"id": "o-2", "total": 40.0}]


def create(event, ctx):
    return {"created": True}, 201


def list_orders(event, ctx):
    return {"orders": ORDERS}
""",
          "requirements.txt": ""}),
      user="""GET https://k3x9.execute-api.eu-west-1.amazonaws.com/orders
{"message":"Not Found"}

got 404 on /orders after adding it, add the route properly""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.orders has no events, so API Gateway has no GET /orders route: add `- http: GET /orders`",
                                   "Validate for aws, invoke GET /orders"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.orders.events", value=[{"http": "GET /orders"}]),
          S("invoke_local", function="orders", method="GET", path="/orders"),
      ],
      final="""Cause: `orders` was added without an `events` list, so it got no route. The HTTP API only knew `POST /orders` (from `create-order`), and API Gateway answered GET with its own `{"message":"Not Found"}`.

Change:

```yaml
functions:
  orders:
    handler: app.orders.list_orders
    events:
      - http: GET /orders
```

GET and POST on the same path in two functions is fine; only the same `METHOD /path` twice is an error [docs/events.md#http].

- `pskit validate` (aws): valid.
- Local GET /orders → 200 with both orders.

The route exists in AWS after **Deploy** or `pskit deploy -s dev`. Next time, add the route in **Functions > + Create function** (step `Triggers`)."""),

    # ------------------------------------------------------------------ 722
    B(722, provider="gcp", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: health-tools
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, health-tools-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="need GET /bmi?weight=70&height=175 give bmi number and category (under, normal, over). wrong input 400",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/bmi.py: read weight (kg) and height (cm) from the query, BadRequest when missing or not numbers",
                                   "functions.bmi on GET /bmi", "Validate gcp, invoke a good and a bad request"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/bmi.py", content=FUTURE + """from py_serverless_kit import BadRequest


def bmi(event, ctx):
    query = event.http.query
    try:
        weight = float(query["weight"])
        height_cm = float(query["height"])
    except (KeyError, ValueError):
        raise BadRequest("send ?weight=<kg>&height=<cm> as numbers")
    if weight <= 0 or height_cm <= 0:
        raise BadRequest("weight and height must be greater than 0")
    value = round(weight / (height_cm / 100) ** 2, 1)
    if value < 18.5:
        category = "under"
    elif value < 25:
        category = "normal"
    else:
        category = "over"
    return {"bmi": value, "category": category}
"""),
          S("set_config", path="functions.bmi", value={"handler": "app.bmi.bmi", "events": [{"http": "GET /bmi"}]}),
          S("invoke_local", function="bmi", method="GET", path="/bmi?weight=70&height=175"),
          S("invoke_local", function="bmi", method="GET", path="/bmi?weight=abc"),
      ],
      final="""Done, `GET /bmi` is added:

```yaml
functions:
  bmi:
    handler: app.bmi.bmi
    events:
      - http: GET /bmi
```

- Values come from `event.http.query` (strings, so the code converts them) [docs/handlers.md#httprequest].
- Missing or not-a-number values raise `BadRequest` → 400 [docs/handlers.md#errors].

Checks: `pskit validate` (gcp) valid; `?weight=70&height=175` → `{"bmi": 22.9, "category": "normal"}`; `?weight=abc` → 400.

Test again: **Test** > **▶ Run locally** or `pskit invoke -f bmi --method GET --path "/bmi?weight=90&height=180"`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 723
    B(723, provider="azure", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: newsletter
provider:
  name: azure
  region: westeurope
functions:
  subscribe:
    handler: app.subscribe.subscribe
    events:
    - http: POST /subscribe
""",
          "app/__init__.py": "",
          "app/subscribe.py": FUTURE + """

def subscribe(event, ctx):
    body = event.http.json()
    email = body["email"]
    ctx.logger.info("subscribed", extra={"email": email})
    return {"subscribed": email}, 201
""",
          "requirements.txt": ""}),
      user="""POST /subscribe with {"name": "Ana"} gives
{"error": "Internal Server Error", "status": 500, "request_id": "5f2c0e9a-1b7d-4c1e-9a77-0c4e2b6d1f10"}
and Logs say KeyError: 'email'

must be 400 that says email is missing, not 500. also check it look like an email""",
      steps=[
          S("get_project"),
          S("read_file", path="app/subscribe.py"),
          S("propose_plan", steps=["app/subscribe.py: missing email -> BadRequest (400); no '@' or no dot after it -> BadRequest",
                                   "Validate for azure (staging), invoke without and with an email"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/subscribe.py", content=FUTURE + """from py_serverless_kit import BadRequest


def subscribe(event, ctx):
    body = event.http.json(default={}) or {}
    email = str(body.get("email") or "").strip()
    if not email:
        raise BadRequest("email is missing")
    name, _, domain = email.partition("@")
    if not name or "." not in domain:
        raise BadRequest("email does not look like an email address")
    ctx.logger.info("subscribed", extra={"email": email})
    return {"subscribed": email}, 201
"""),
          S("validate"),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe", data={"name": "Ana"}),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe", data={"email": "ana@example.com"}),
      ],
      final="""Cause: `body["email"]` raised `KeyError`, and any exception that isn't an `HttpError` becomes a 500 [docs/handlers.md#errors].

Change in `app/subscribe.py`: missing email → `BadRequest("email is missing")`; a value without `@` or without a dot in the domain → `BadRequest("email does not look like an email address")`. Both are 400 with that message. An empty body no longer fails either (`json(default={})`).

- `pskit validate` (azure, staging): valid.
- `{"name": "Ana"}` → 400 `email is missing`.
- `{"email": "ana@example.com"}` → 201.

Test again on **Test** or `pskit invoke -f subscribe --method POST --path /subscribe -d '{"email": "x"}' -s staging`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 724
    B(724, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: photo-tools
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "app/__init__.py": "",
          "app/resize.py": FUTURE + """

def resize(event, ctx):
    done = []
    for record in event.records:
        ctx.logger.info("resize", extra={"bucket": record.bucket, "key": record.key})
        done.append(record.key)
    return {"resized": done}
""",
          "requirements.txt": ""}),
      user="""moving from serverless.yml, code is already in app/resize.py:

functions:
  resize:
    handler: handler.resize
    memorySize: 1024
    events:
      - s3:
          bucket: photos-in-4410
          event: s3:ObjectCreated:*
          rules:
            - prefix: uploads/
            - suffix: .png
          existing: true""",
      steps=[
          S("get_project"),
          S("search_docs", query="serverless s3 event existing bucket prefix suffix",
            docs=[D("docs/migrating-from-aws.md", "step-2-translate-the-sam-serverless-cdk-definition", start="| `Type: S3`", end="| `Type: SNS` | `- topic: {name: t, existing: true}` |")]),
          S("propose_plan", steps=["functions.resize: handler app.resize.resize, memory 1024",
                                   "storage event: bucket photos-in-4410, existing: true, events [created], prefix uploads/, suffix .png",
                                   "Validate for aws, invoke with uploads/cat.png"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.resize",
            value={"handler": "app.resize.resize", "memory": 1024,
                   "events": [{"storage": {"bucket": "photos-in-4410", "existing": True, "events": ["created"],
                                           "prefix": "uploads/", "suffix": ".png"}}]}),
          S("invoke_local", function="resize", type="storage", data={"bucket": "photos-in-4410", "key": "uploads/cat.png", "size": 20480}),
      ],
      final="""```yaml
functions:
  resize:
    handler: app.resize.resize
    memory: 1024
    events:
      - storage:
          bucket: photos-in-4410
          existing: true
          events: [created]
          prefix: uploads/
          suffix: .png
```

- `memorySize` → `memory`; `s3` + `s3:ObjectCreated:*` + `rules` → `storage` with `events: [created]`, `prefix`, `suffix`; `existing: true` keeps the bucket untouched [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition].
- The handler is `app.resize.resize` (pskit's `package.module.function` form), and the records give you `bucket` and `key` [docs/events.md#storage].
- `pskit validate` (aws): valid; a created `uploads/cat.png` → `{"resized": ["uploads/cat.png"]}`.

An S3 bucket has one notification configuration, so remove the trigger from the old Serverless stack before you deploy here. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 725
    B(725, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: files-svc
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, files-svc-dev}
functions:
  upload:
    handler: app.files.upload
    events:
    - http: POST /files
  cleanup:
    handler: app.files.cleanup
""",
          "app/__init__.py": "",
          "app/files.py": FUTURE + """

def upload(event, ctx):
    return {"stored": True}, 201


def cleanup(event, ctx):
    ctx.logger.info("cleanup run")
    return {"deleted": 0}
""",
          "requirements.txt": ""}),
      user="cleanup fn should run every 6 hour by itself pls. and also give it 512mb memory",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.cleanup.events: schedule 6 hours", "functions.cleanup.memory: 512",
                                   "Validate for gcp, run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.cleanup.events", value=[{"schedule": "6 hours"}]),
          S("set_config", path="functions.cleanup.memory", value=512),
          S("invoke_local", function="cleanup", type="schedule"),
      ],
      final="""Both done on `cleanup`:

```yaml
functions:
  cleanup:
    handler: app.files.cleanup
    memory: 512
    events:
      - schedule: 6 hours
```

- On GCP the rate becomes a Cloud Scheduler cron (every 6 hours from midnight UTC) [docs/events.md#schedule].
- `upload` keeps the default memory.
- `pskit validate` (gcp): valid; a scheduled run → `{"deleted": 0}`.

Run it again on **Test** (schedule event) or `pskit invoke -f cleanup -t schedule`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 726
    B(726, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: text-tools
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="word counter. i POST plain text (not json!) to /count and want back how many words, chars and lines",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/count.py: read the raw body with event.http.text(), count words / chars / lines",
                                   "functions.count on POST /count", "Validate for azure, invoke with two lines of text"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/count.py", content=FUTURE + """

def count(event, ctx):
    text = event.http.text()
    return {
        "words": len(text.split()),
        "chars": len(text),
        "lines": len(text.splitlines()),
    }
"""),
          S("set_config", path="functions.count", value={"handler": "app.count.count", "events": [{"http": "POST /count"}]}),
          S("invoke_local", function="count", method="POST", path="/count", data="the quick brown fox\njumps over the dog"),
      ],
      final="""Done: `POST /count` takes any plain text.

- `event.http.text()` gives the body as a string, no JSON parsing [docs/handlers.md#httprequest].
- Answer is `{"words": ..., "chars": ..., "lines": ...}`. Test with 2 lines → `{"words": 8, "chars": 38, "lines": 2}`.
- `pskit validate` (azure): valid.

From a terminal after deploy: `curl -X POST --data-binary @notes.txt <url>/count`. Test locally on **Test** > **▶ Run locally**; deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 727
    B(727, provider="aws", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#queue", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: row-import
provider:
  name: aws
  region: eu-central-1
functions:
  import-rows:
    handler: app.rows.handle
    events:
    - queue:
        name: row-imports
        batch_size: 10
""",
          "app/__init__.py": "",
          "app/rows.py": FUTURE + """

def handle(event, ctx):
    return {"imported": len(event.records)}
""",
          "requirements.txt": ""}),
      user="""REPORT RequestId: 8c1d77e2-4f0b-4a52-9d1e-3b9f0e6a2c41 Duration: 30000.00 ms Billed Duration: 30000 ms Memory Size: 256 MB Max Memory Used: 97 MB
Task timed out after 30.03 seconds

import-rows dies like this on big batches, some batches need ~2 min. fix it""",
      steps=[
          S("get_project"),
          S("search_docs", query="queue visibility_timeout default function timeout",
            docs=[D("docs/events.md", "queue", words=130)]),
          S("propose_plan", steps=["functions.import-rows.timeout: 300 (2 min batches + headroom; default is 30)",
                                   "Keep visibility_timeout unset: the default follows the timeout (6 x)",
                                   "Validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.import-rows.timeout", value=300),
      ],
      final="""Cause: the function has no `timeout`, so it uses the default 30 s; `Duration: 30000.00 ms` + `Task timed out` is Lambda stopping it there. Memory is fine (97 of 256 MB).

Change:

```yaml
functions:
  import-rows:
    handler: app.rows.handle
    timeout: 300
    events:
      - queue: {name: row-imports, batch_size: 10}
```

- 300 s leaves room above your ~2 min batches.
- The SQS visibility timeout defaults to max(30, 6 x function timeout), so it grows to 1800 s by itself and messages aren't redelivered while a batch is still running [docs/events.md#queue].
- `pskit validate` (aws, prod): valid.

Deploy with **Deploy** (prod needs typed confirmation) or `pskit deploy -s prod`. If batches keep growing, lower `batch_size` instead of raising the timeout further."""),

    # ------------------------------------------------------------------ 728
    B(728, provider="gcp", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: media-svc
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, media-svc-dev}
functions:
  api:
    handler: app.media.api
    events:
    - http: GET /media
  thumbnail:
    handler: app.media.thumbnail
    events:
    - storage: media-originals-6620
""",
          "app/__init__.py": "",
          "app/media.py": FUTURE + """

def api(event, ctx):
    return {"items": []}


def thumbnail(event, ctx):
    return {"thumbnails": [r.key for r in event.records]}
""",
          "requirements.txt": ""}),
      user="""Memory limit of 256 MiB exceeded with 301 MiB used. Consider increasing the memory limit, see https://cloud.google.com/functions/docs/configuring/memory

only thumbnail fn has this, others fine with 256""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.thumbnail.memory: 512 (used 301 MiB, default 256)", "api keeps the default",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.thumbnail.memory", value=512),
      ],
      final="""Cause: `thumbnail` runs with the default 256 MB and the image work needs ~301 MiB, so Cloud Functions kills it.

Change, on that function only:

```yaml
functions:
  thumbnail:
    handler: app.media.thumbnail
    memory: 512
    events:
      - storage: media-originals-6620
```

- A function's `memory` overrides the provider default for that function [docs/configuration.md#functions]; `api` stays at 256.
- `pskit validate` (gcp): valid.

Deploy: **Deploy** or `pskit deploy -s dev`. If big images still go over, try 1024 (more memory also gives more CPU on GCP)."""),

    # ------------------------------------------------------------------ 729
    B(729, provider="azure", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: sms-gateway
provider:
  name: azure
  region: northeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="worker for storage queue `sms-out`, msg is {phone, text}. log phone and text, if text longer 160 char log warning it will be split",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/sms.py: per record log phone + text; warning when len(text) > 160",
                                   "functions.sms-out-worker on queue sms-out", "Validate azure, invoke with a short and a long message"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/sms.py", content=FUTURE + """
LIMIT = 160


def send(event, ctx):
    sent = 0
    for record in event.records:
        msg = record.json(default={}) or {}
        phone, text = msg.get("phone"), str(msg.get("text", ""))
        ctx.logger.info("sms", extra={"phone": phone, "text": text})
        if len(text) > LIMIT:
            ctx.logger.warning("sms will be split", extra={"phone": phone, "length": len(text)})
        sent += 1
    return {"sent": sent}
"""),
          S("set_config", path="functions.sms-out-worker", value={"handler": "app.sms.send", "events": [{"queue": "sms-out"}]}),
          S("invoke_local", function="sms-out-worker", type="queue",
            data=[{"phone": "+15550100", "text": "Your code is 4821"}, {"phone": "+15550101", "text": "x" * 170}]),
      ],
      final="""Done: `sms-out-worker` reads the Storage Queue `sms-out` (pskit creates it):

```yaml
functions:
  sms-out-worker:
    handler: app.sms.send
    events:
      - queue: sms-out
```

- Each message logs phone + text; text over 160 chars adds a WARNING `sms will be split` with the length.
- On Azure a message that keeps failing goes to `sms-out-poison` [docs/events.md#queue].
- `pskit validate` (azure): valid. Test with 2 messages (one 170 chars) → 2 info lines, 1 warning, `{"sent": 2}`.

Test again on **Test** (queue event). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 730
    B(730, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: number-fun
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="i want GET /roman/{n} make number to roman, like 2024 -> MMXXIV. only 1 to 3999 ok, else 400",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/roman.py: n from path_params, BadRequest outside 1..3999 or not a number",
                                   "functions.roman on GET /roman/{n}", "Validate aws, invoke 2024 and 0"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/roman.py", content=FUTURE + """from py_serverless_kit import BadRequest

NUMERALS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def roman(event, ctx):
    raw = event.http.path_params["n"]
    if not raw.isdigit() or not 1 <= int(raw) <= 3999:
        raise BadRequest("n must be a whole number from 1 to 3999")
    n, out = int(raw), ""
    for value, letters in NUMERALS:
        while n >= value:
            out += letters
            n -= value
    return {"number": int(raw), "roman": out}
"""),
          S("set_config", path="functions.roman", value={"handler": "app.roman.roman", "events": [{"http": "GET /roman/{n}"}]}),
          S("invoke_local", function="roman", method="GET", path="/roman/2024"),
          S("invoke_local", function="roman", method="GET", path="/roman/0"),
      ],
      final="""Done: `GET /roman/{n}`.

- `{n}` comes in `event.http.path_params["n"]` [docs/events.md#http]; outside 1–3999 or not a number → `BadRequest` (400) [docs/handlers.md#errors].
- `pskit validate` (aws): valid.
- /roman/2024 → `{"number": 2024, "roman": "MMXXIV"}`; /roman/0 → 400.

Try more on **Test** or `pskit invoke -f roman --method GET --path /roman/1999`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 731
    B(731, provider="gcp", stage="staging", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#context", "docs/handlers.md#logging"],
      project=dict(files={
          "pskit.yml": """service: reporting
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, reporting-staging}
functions:
  report:
    handler: app.report.handler
    events:
    - schedule: "0 6 * * *"
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """import json


def handler(event, context):
    print(json.dumps({"request": context.aws_request_id, "fn": context.function_name, "msg": "report started"}))
    return {"status": "started"}
""",
          "requirements.txt": ""}),
      user="this came from Lambda, it logs context.aws_request_id and context.function_name with print. make it the pskit way so it works on GCP too",
      steps=[
          S("get_project"),
          S("read_file", path="app/report.py"),
          S("search_docs", query="context request_id function logger",
            docs=[D("docs/handlers.md", "context", start="| `request_id` |", end="| `logger` | structured logger with `function`, `request_id` and `provider` already bound |")]),
          S("propose_plan", steps=["app/report.py: ctx.logger.info(\"report started\") instead of print; request_id and function are bound by the logger",
                                   "Validate for gcp (staging), run the schedule"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/report.py", content=FUTURE + """

def handler(event, ctx):
    ctx.logger.info("report started", extra={"stage": ctx.stage})
    return {"status": "started", "request_id": ctx.request_id}
"""),
          S("validate"),
          S("invoke_local", function="report", type="schedule"),
      ],
      final="""`app/report.py` now uses the portable context:

| Lambda | pskit |
|---|---|
| `context.aws_request_id` | `ctx.request_id` |
| `context.function_name` | `ctx.function` (logical name, same on every cloud) |
| `print(json.dumps(...))` | `ctx.logger.info(...)`, JSON lines in the cloud with `function`, `request_id` and `provider` already added |

[docs/handlers.md#context] [docs/handlers.md#logging]

- `pskit validate` (gcp, staging): valid.
- Scheduled run → `report started` log line and `{"status": "started", "request_id": ...}`.

Read the lines on **Logs** after **Deploy** (`pskit deploy -s staging`)."""),

    # ------------------------------------------------------------------ 732
    B(732, provider="azure", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http", "docs/troubleshooting.md#http"],
      project=dict(files={
          "pskit.yml": """service: shop-api
provider:
  name: azure
  region: westeurope
functions:
  cart:
    handler: app.cart.cart
    events:
    - http: GET /cart
    - http: POST /cart
""",
          "app/__init__.py": "",
          "app/cart.py": FUTURE + """

def cart(event, ctx):
    if event.http.method == "POST":
        return {"added": True}, 201
    return {"items": []}
""",
          "requirements.txt": ""}),
      user="""Access to fetch at 'https://shop-api-x7f2.azurewebsites.net/cart' from origin 'https://shop.example.com' has been blocked by CORS policy: Response to preflight request doesn't pass access control check: No 'Access-Control-Allow-Origin' header is present on the requested resource.

GET and POST /cart both. only our shop site may call it""",
      steps=[
          S("get_project"),
          S("search_docs", query="cors origins preflight", docs=[D("docs/events.md", "http", start="**CORS**", end="AWS additionally configures CORS on the HTTP API.")]),
          S("propose_plan", steps=["Both cart routes: cors {origins: [https://shop.example.com]}",
                                   "Validate for azure (prod), invoke GET /cart"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.cart.events",
            value=[{"http": {"path": "/cart", "method": "GET", "cors": {"origins": ["https://shop.example.com"]}}},
                   {"http": {"path": "/cart", "method": "POST", "cors": {"origins": ["https://shop.example.com"]}}}]),
          S("invoke_local", function="cart", method="GET", path="/cart"),
      ],
      final="""Cause: the `/cart` routes had no `cors`, so the browser's preflight from https://shop.example.com got no `Access-Control-Allow-Origin` [docs/troubleshooting.md#http].

Change:

```yaml
functions:
  cart:
    handler: app.cart.cart
    events:
      - http: {path: /cart, method: GET, cors: {origins: ["https://shop.example.com"]}}
      - http: {path: /cart, method: POST, cors: {origins: ["https://shop.example.com"]}}
```

- The runtime answers `OPTIONS` preflights with 204 and adds the `Access-Control-*` headers, for that origin only [docs/events.md#http].
- `pskit validate` (azure, prod): valid; local GET /cart → 200 (no CORS headers locally because the test sends no `Origin`).

Deploy with **Deploy** (typed confirmation for prod) or `pskit deploy -s prod`, then reload the shop page."""),

    # ------------------------------------------------------------------ 733
    B(733, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: aws
  region: eu-west-1
functions:
  products:
    handler: app.products.handle
    events:
    - http: GET /products/{id}
""",
          "app/__init__.py": "",
          "app/products.py": FUTURE + """from py_serverless_kit import NotFound

PRODUCTS = {"p1": {"id": "p1", "name": "Mug", "price": 8.0}}


def handle(event, ctx):
    product = PRODUCTS.get(event.http.path_params["id"])
    if product is None:
        raise NotFound("no such product")
    return product
""",
          "requirements.txt": ""}),
      user="products fn now only GET /products/{id}. add PUT and DELETE same path, same function pls. fake data ok",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["products.events: GET, PUT and DELETE /products/{id}",
                                   "app/products.py: branch on event.http.method; PUT merges the body, DELETE returns None (204)",
                                   "Validate for aws, invoke PUT and DELETE"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/products.py", content=FUTURE + """from py_serverless_kit import NotFound

PRODUCTS = {"p1": {"id": "p1", "name": "Mug", "price": 8.0}}


def handle(event, ctx):
    product_id = event.http.path_params["id"]
    product = PRODUCTS.get(product_id)
    if product is None:
        raise NotFound("no such product")
    if event.http.method == "PUT":
        product.update(event.http.json(default={}) or {})
        product["id"] = product_id
        return product
    if event.http.method == "DELETE":
        del PRODUCTS[product_id]
        return None
    return product
"""),
          S("set_config", path="functions.products.events",
            value=[{"http": "GET /products/{id}"}, {"http": "PUT /products/{id}"}, {"http": "DELETE /products/{id}"}]),
          S("invoke_local", function="products", method="PUT", path="/products/p1", data={"price": 9.5}),
          S("invoke_local", function="products", method="DELETE", path="/products/p1"),
      ],
      final="""Done, one function with three routes:

```yaml
functions:
  products:
    handler: app.products.handle
    events:
      - http: GET /products/{id}
      - http: PUT /products/{id}
      - http: DELETE /products/{id}
```

- The code checks `event.http.method`. PUT merges the body into the product; DELETE returns `None` → 204 [docs/handlers.md#returning-a-response]. Unknown id → 404 for all three.
- `pskit validate` (aws): valid.
- PUT /products/p1 `{"price": 9.5}` → 200 with price 9.5; DELETE /products/p1 → 204.

Fake data is in memory, so it resets on every cold start. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 734
    B(734, provider="azure", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: quotes
provider:
  name: azure
  region: westeurope
functions:
  quotes:
    handler: app.quotes.quotes
    events:
    - http: GET /quotes
""",
          "app/__init__.py": "",
          "app/quotes.py": FUTURE + """

def quotes(event, ctx):
    return {"quotes": [{"id": 1, "text": "Keep going."}]}
""",
          "requirements.txt": ""}),
      user="""$ curl -i https://quotes-prod-9c1e.azurewebsites.net/v2/quotes
HTTP/1.1 404 Not Found
Content-Length: 0

new mobile app call /v2/quotes and get 404. add the route properly, but old app still use /quotes so keep it""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.quotes.events: keep GET /quotes, add GET /v2/quotes (same handler)",
                                   "Validate for azure (prod), invoke GET /v2/quotes"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.quotes.events", value=[{"http": "GET /quotes"}, {"http": "GET /v2/quotes"}]),
          S("invoke_local", function="quotes", method="GET", path="/v2/quotes"),
      ],
      final="""Cause: only `GET /quotes` was declared, so the Function App had no `/v2/quotes` route and Azure answered with an empty 404.

Change, both paths on the same function:

```yaml
functions:
  quotes:
    handler: app.quotes.quotes
    events:
      - http: GET /quotes
      - http: GET /v2/quotes
```

- A function can have several `http` events; on Azure the paths are served exactly as written (no `/api` prefix) [docs/events.md#http].
- `pskit validate` (azure, prod): valid; local GET /v2/quotes → 200 with the quotes.
- If v2 should answer differently later, check `event.http.route` (`/v2/quotes` or `/quotes`) in the handler.

Deploy with **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 735
    B(735, provider="azure", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: crm-sync
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "app/__init__.py": "",
          "app/crm.py": FUTURE + """

def sync(event, ctx):
    source = (event.data or {}).get("source")
    ctx.logger.info("sync", extra={"source": source})
    return {"synced": source}
""",
          "requirements.txt": ""}),
      user="""SAM template had:

  SyncCrm:
    Type: AWS::Serverless::Function
    Properties:
      Handler: app.crm.sync
      Timeout: 120
      Events:
        Every15:
          Type: Schedule
          Properties:
            Schedule: rate(15 minutes)
            Input: '{"source": "crm"}'

same thing on azure please, code is in app/crm.py""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.sync-crm: handler app.crm.sync, timeout 120",
                                   "schedule {rate: 15 minutes, input: {source: crm}}",
                                   "Validate for azure, run the schedule"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sync-crm",
            value={"handler": "app.crm.sync", "timeout": 120,
                   "events": [{"schedule": {"rate": "15 minutes", "input": {"source": "crm"}}}]}),
          S("invoke_local", function="sync-crm", type="schedule"),
      ],
      final="""```yaml
functions:
  sync-crm:
    handler: app.crm.sync
    timeout: 120
    events:
      - schedule:
          rate: 15 minutes
          input: {source: crm}
```

- `rate(15 minutes)` → `rate: 15 minutes`; the `Input` JSON becomes a real mapping under `input`, which your code reads as `event.data` [docs/events.md#schedule] [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition].
- On Azure it's a timer trigger (`0 */15 * * * *`, UTC).
- `pskit validate` (azure): valid; a scheduled run → `{"synced": "crm"}`.

Deploy: **Deploy** or `pskit deploy -s dev`. Azure deploys need your subscription id (`ARM_SUBSCRIPTION_ID`)."""),

    # ------------------------------------------------------------------ 736
    B(736, provider="aws", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: edge-api
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.api.handler
    events:
    - http: GET /items
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def handler(event, ctx):
    return {"items": []}
""",
          "requirements.txt": ""}),
      user="fn `echo` on ANY /debug/{path+}: return method, path, query, content_type. disabled in prod",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/echo.py: return request fields", "functions.echo: http {path: /debug/{path+}, method: ANY}",
                                   "stages.prod.functions.echo.enabled: false", "Validate aws, invoke"]),
          S("write_file", path="app/echo.py", content=FUTURE + """

def echo(event, ctx):
    req = event.http
    return {"method": req.method, "path": req.path, "query": req.query, "content_type": req.content_type}
"""),
          S("set_config", path="functions.echo",
            value={"handler": "app.echo.echo", "events": [{"http": {"path": "/debug/{path+}", "method": "ANY"}}]}),
          S("set_config", path="stages", value={"prod": {"functions": {"echo": {"enabled": False}}}}),
          S("invoke_local", function="echo", method="POST", path="/debug/a/b?x=1", data={"k": "v"}),
      ],
      final="""```yaml
functions:
  echo:
    handler: app.echo.echo
    events:
      - http: {path: "/debug/{path+}", method: ANY}
stages:
  prod:
    functions:
      echo: {enabled: false}
```

- `{path+}` is greedy, last segment only [docs/events.md#http]; prod skips the function on deploy [docs/configuration.md#stages-per-stage-overrides].
- `pskit validate` (aws, dev): valid. POST /debug/a/b?x=1 → method, path, `{"x": "1"}` and the content type.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 737
    B(737, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: accounts
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, accounts-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="pubsub topic `user-deleted`, pskit make it. fn purge-data log the user_id. and also fn audit-log on the same topic, log it too",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/users.py: purge() and audit(), both log user_id per message",
                                   "functions.purge-data and functions.audit-log, each with topic user-deleted",
                                   "Validate for gcp, invoke both"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/users.py", content=FUTURE + """

def _user_ids(event):
    return [(r.json(default={}) or {}).get("user_id") for r in event.records]


def purge(event, ctx):
    ids = _user_ids(event)
    ctx.logger.info("purge user data", extra={"user_ids": ids})
    return {"purged": ids}


def audit(event, ctx):
    ids = _user_ids(event)
    ctx.logger.info("user deleted", extra={"user_ids": ids})
    return {"audited": ids}
"""),
          S("set_config", path="functions.purge-data", value={"handler": "app.users.purge", "events": [{"topic": "user-deleted"}]}),
          S("set_config", path="functions.audit-log", value={"handler": "app.users.audit", "events": [{"topic": "user-deleted"}]}),
          S("invoke_local", function="purge-data", type="topic", data={"user_id": "u-77"}),
          S("invoke_local", function="audit-log", type="topic", data={"user_id": "u-77"}),
      ],
      final="""Done: one Pub/Sub topic `user-deleted`, two subscribers:

```yaml
functions:
  purge-data:
    handler: app.users.purge
    events:
      - topic: user-deleted
  audit-log:
    handler: app.users.audit
    events:
      - topic: user-deleted
```

- pskit creates the topic once; each function gets its own trigger, so both receive every message [docs/events.md#topic].
- `pskit validate` (gcp): valid.
- Message `{"user_id": "u-77"}` → purge-data `{"purged": ["u-77"]}`, audit-log `{"audited": ["u-77"]}`.

Test again on **Test** (topic event). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 738
    B(738, provider="aws", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: team-digest
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="every sunday 23:00 utc run fn `weekly`, for now only give back the week number of the year",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/weekly.py: ISO week number from event.time", "functions.weekly: schedule \"0 23 * * 0\"",
                                   "Validate aws, run the schedule"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/weekly.py", content=FUTURE + """

def weekly(event, ctx):
    year, week, _ = event.time.isocalendar()
    ctx.logger.info("weekly run", extra={"week": week})
    return {"year": year, "week": week}
"""),
          S("set_config", path="functions.weekly", value={"handler": "app.weekly.weekly", "events": [{"schedule": "0 23 * * 0"}]}),
          S("invoke_local", function="weekly", type="schedule"),
      ],
      final="""Done:

```yaml
functions:
  weekly:
    handler: app.weekly.weekly
    events:
      - schedule: "0 23 * * 0"
```

- `0 23 * * 0` = Sunday 23:00; schedules are UTC by default [docs/events.md#schedule].
- The week comes from `event.time` (UTC) [docs/handlers.md#event]; `isocalendar()` gives the ISO week.
- `pskit validate` (aws): valid. Test run → `{"year": 2026, "week": 44}`.

Run again: **Test** or `pskit invoke -f weekly -t schedule`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 739
    B(739, provider="aws", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/resources.md#aws-iam", "docs/resources.md#using-a-resource-from-an-event"],
      project=dict(files={
          "pskit.yml": """service: mailer
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.mail.api
    events:
    - http: POST /emails
  worker:
    handler: app.mail.worker
    events:
    - queue: email-jobs
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """

def api(event, ctx):
    return {"queued": True}, 202


def worker(event, ctx):
    return {"sent": len(event.records)}
""",
          "requirements.txt": ""}),
      user="""botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the SendMessage operation: User: arn:aws:sts::123456789012:assumed-role/mailer-dev-api/mailer-dev-api is not authorized to perform: sqs:sendmessage on resource: arn:aws:sqs:eu-west-1:123456789012:mailer-dev-email-jobs because no identity-based policy allows the sqs:sendmessage action

api puts jobs on the queue, worker reads it fine""",
      steps=[
          S("get_project"),
          S("search_docs", query="resource queue iam sendmessage functions",
            docs=[D("docs/resources.md", "aws-iam")]),
          S("propose_plan", steps=["resources.email-jobs: {type: queue, functions: [api, worker]} (api gets sqs:SendMessage)",
                                   "worker event: queue {resource: email-jobs}",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources", value={"email-jobs": {"type": "queue", "functions": ["api", "worker"]}}),
          S("set_config", path="functions.worker.events.0", value={"queue": {"resource": "email-jobs"}}),
      ],
      final="""Cause: the queue only existed as `worker`'s trigger, so only worker's role could use it. `api`'s role had no SQS permission.

Change: the queue is now a resource bound to both functions, and the worker trigger points at it:

```yaml
resources:
  email-jobs:
    type: queue
    functions: [api, worker]
functions:
  worker:
    handler: app.mail.worker
    events:
      - queue: {resource: email-jobs}
```

- Each bound function's role gets a `pskit-resources` policy with `sqs:SendMessage` (and receive/delete) for that queue [docs/resources.md#aws-iam]. It's the same queue as before (`mailer-dev-email-jobs`) [docs/resources.md#using-a-resource-from-an-event].
- `api` also gets the queue URL: use `resource("email-jobs").url` in `boto3.client("sqs").send_message(...)` instead of a hard-coded URL.
- `pskit validate` (aws): valid.

Deploy: **Deploy** or `pskit deploy -s dev`; check the plan first (**Deploy > Plan** or `pskit plan -s dev`)."""),

    # ------------------------------------------------------------------ 740
    B(740, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: class-greeter
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, class-greeter-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="my teacher wants a function that says good morning, good afternoon or good evening depending on the time. can you do it?",
      steps=[
          S("get_project"),
          S("ask_user", question="Functions run in UTC. Which time zone should the greeting use?",
            options=["UTC is fine", "My local time (tell me the hours difference from UTC)"],
            answer="we are UTC+1"),
          S("propose_plan", steps=["Write app/greet.py: GET /greeting, hour = UTC hour + offset (default 1, or ?utc_offset=)",
                                   "Morning before 12, afternoon before 18, else evening",
                                   "Validate for gcp, try it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/greet.py", content=FUTURE + """from datetime import timedelta

from py_serverless_kit import BadRequest


def greeting(event, ctx):
    try:
        offset = int(event.http.query.get("utc_offset", "1"))
    except ValueError:
        raise BadRequest("utc_offset must be a whole number, like 1 or -5")
    hour = (event.time + timedelta(hours=offset)).hour
    if hour < 12:
        text = "Good morning"
    elif hour < 18:
        text = "Good afternoon"
    else:
        text = "Good evening"
    return {"greeting": text, "local_hour": hour}
"""),
          S("set_config", path="functions.greeting", value={"handler": "app.greet.greeting", "events": [{"http": "GET /greeting"}]}),
          S("invoke_local", function="greeting", method="GET", path="/greeting"),
      ],
      final="""Yes, here it is: **GET /greeting**

- It takes the current time (UTC) and adds 1 hour for your time zone, then says "Good morning" (before 12), "Good afternoon" (before 18) or "Good evening".
- Another time zone: add `?utc_offset=-5` to the address [docs/handlers.md#httprequest].
- When I tried it (12:xx in UTC+1) it answered `{"greeting": "Good afternoon", "local_hour": 12}`.
- `pskit validate` (gcp): valid.

Note: the +1 doesn't change by itself for summer time; use `?utc_offset=2` then. Try it on **Test** > **▶ Run locally**; put it online with **Deploy** or `pskit deploy -s dev`."""),
]
