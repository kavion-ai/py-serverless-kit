"""Category D (fix a handler bug), batch 4. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"d_debug-{n:04d}", category="d_debug", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 61  aws http, Lambda event["body"]
    B(61, provider="aws", stage="dev", mode="auto", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: leads
provider:
  name: aws
  region: eu-west-1
functions:
  capture-lead:
    handler: app.handler.lambda_handler
    events:
      - http: POST /leads
""",
          "app/__init__.py": "",
          "app/handler.py": FUTURE + """import json


def lambda_handler(event, context):
    body = json.loads(event["body"])
    context.logger.info("lead", extra={"company": body.get("company")})
    return {"saved": True}, 201
""",
          "requirements.txt": ""}),
      user="Copied my Lambda handler 1:1. json.loads(event['body']) gives TypeError: 'Event' object is not subscriptable. What's the pskit equivalent of event['body']?",
      steps=[
          S("read_file", path="app/handler.py"),
          S("invoke_local", function="capture-lead", method="POST", path="/leads", data={"company": "Example Ltd"}),
          S("search_docs", query="request body json http event",
            docs=[D("docs/handlers.md", "httprequest", start="| `body`", end="| `json(default=...)`")]),
          S("propose_plan", steps=["Replace `json.loads(event[\"body\"])` with `event.http.json()` and drop the json import",
                                   "POST /leads locally, validate for aws"]),
          S("write_file", path="app/handler.py", content=FUTURE + """
def lambda_handler(event, context):
    body = event.http.json()
    context.logger.info("lead", extra={"company": body.get("company")})
    return {"saved": True}, 201
"""),
          S("invoke_local", function="capture-lead", method="POST", path="/leads", data={"company": "Example Ltd"}),
          S("validate"),
      ],
      final="""pskit passes a portable `Event`, not the API Gateway dict. The equivalent of `json.loads(event["body"])` is `event.http.json()` (`event.http.body` gives the raw bytes, `event.http.text()` the string) [docs/handlers.md#httprequest]. Bad JSON now gives a 400 instead of a crash.

- POST /leads `{"company": "Example Ltd"}`: 201, `{"saved": true}`.
- validate (aws): valid.

The name `lambda_handler` and the `context` parameter can stay; pskit only needs the `handler:` path to match."""),

    # ------------------------------------------------------------------ 62  gcp schedule, input value is a string
    B(62, provider="gcp", stage="staging", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: rollups
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  rollup:
    handler: app.rollup.rollup
    events:
      - schedule:
          cron: "0 2 * * *"
          input:
            days: "7"
""",
          "app/__init__.py": "",
          "app/rollup.py": FUTURE + """
def rollup(event, ctx):
    days = [f"day-{i}" for i in range(event.data["days"])]
    return {"rolled_up": len(days)}
""",
          "requirements.txt": ""}),
      user="rollup: TypeError 'str' object cannot be interpreted as an integer. config issue?",
      steps=[
          S("get_project"),
          S("invoke_local", function="rollup", type="schedule"),
          S("propose_plan", steps=["Make the schedule input a number: `functions.rollup.events.0.schedule.input.days: 7`",
                                   "Validate for gcp, run rollup as a schedule event"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.rollup.events.0.schedule.input.days", value=7),
          S("invoke_local", function="rollup", type="schedule"),
      ],
      final="""Yes. `input.days` is quoted (`"7"`), so the handler gets a string and `range("7")` fails. Schedule `input` arrives as `event.data` unchanged [docs/events.md#schedule]. I set it to the integer `7`:

```yaml
events:
  - schedule:
      cron: "0 2 * * *"
      input: {days: 7}
```

- validate (gcp, staging): valid.
- invoke: `{"rolled_up": 7}`."""),

    # ------------------------------------------------------------------ 63  azure http, iterating a dict body
    B(63, provider="azure", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: carts
provider:
  name: azure
  region: centralus
functions:
  cart-total:
    handler: app.cart.total
    events:
      - http: POST /cart/total
""",
          "app/__init__.py": "",
          "app/cart.py": FUTURE + """
def total(event, ctx):
    body = event.http.json()
    qty = sum(item["qty"] for item in body)
    return {"items": qty}
""",
          "requirements.txt": ""}),
      user="""TypeError: string indices must be integers, not 'str'
cart-total, request body is {"items": [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 1}]}""",
      steps=[
          S("read_file", path="app/cart.py"),
          S("invoke_local", function="cart-total", method="POST", path="/cart/total",
            data={"items": [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 1}]}),
          S("propose_plan", steps=["Iterate `body[\"items\"]` instead of `body` (looping over a dict gives its keys)",
                                   "POST the same body locally and validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/cart.py", content=FUTURE + """
def total(event, ctx):
    body = event.http.json()
    qty = sum(item["qty"] for item in body.get("items", []))
    return {"items": qty}
"""),
          S("invoke_local", function="cart-total", method="POST", path="/cart/total",
            data={"items": [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 1}]}),
          S("validate"),
      ],
      final="""The body is a dict, and `for item in body` loops over its **keys**. So `item` was the string `"items"`, and `"items"["qty"]` failed. Now it loops over `body.get("items", [])`.

- POST /cart/total with your body: status 200, `{"items": 3}`.
- `pskit validate` for azure, prod: valid."""),

    # ------------------------------------------------------------------ 64  onprem queue, event.json() only first record
    B(64, provider="onprem", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#event", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: label-printer
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8150
functions:
  print-label:
    handler: app.labels.print_label
    events:
      - queue:
          name: labels
          batch_size: 5
""",
          "app/__init__.py": "",
          "app/labels.py": FUTURE + """
def print_label(event, ctx):
    job = event.json()
    ctx.logger.info("printing", extra={"order": job["order"]})
    return {"printed": 1}
""",
          "requirements.txt": ""}),
      user="With batch_size 5 the label printer sometimes gets several messages at once, but only one label is printed per batch and the rest are lost (they don't come back). Every message must print exactly one label. Please test with three messages.",
      steps=[
          S("read_file", path="app/labels.py"),
          S("invoke_local", function="print-label", type="queue", data=[{"order": 1}, {"order": 2}, {"order": 3}]),
          S("search_docs", query="event json first record batch records",
            docs=[D("docs/handlers.md", "event", start="Helpers:", end="- `json()`")]),
          S("propose_plan", steps=["Loop over `event.records` and print one label per `record.json()`; report failures with `BatchResult` so they are retried",
                                   "Invoke print-label with three messages and validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/labels.py", content=FUTURE + """from py_serverless_kit import BatchResult


def print_label(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            job = record.json()
            ctx.logger.info("printing", extra={"order": job["order"]})
        except Exception:
            result.fail(record)
    return result
"""),
          S("invoke_local", function="print-label", type="queue", data=[{"order": 1}, {"order": 2}, {"order": 3}]),
          S("validate"),
      ],
      final="""`event.json()` returns only **the first record's** body [docs/handlers.md#event]. The batch then counted as done, so the other messages were acknowledged without printing.

Now the handler loops over `event.records`, so there is one label per message. It returns a `BatchResult`, so a message that fails is retried by the on-prem host and goes to a dead-letter queue after `max_receive` [docs/events.md#queue].

- Before (3 messages): one "printing" line, `{"printed": 1}`.
- After: three "printing" lines (orders 1, 2, 3), `{"batchItemFailures": []}`.
- `pskit validate` for onprem, staging: valid."""),

    # ------------------------------------------------------------------ 65  alibaba topic, fail() with the payload
    B(65, provider="alibaba", stage="prod", mode="auto", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: sms-gateway
provider:
  name: alibaba
  region: cn-hangzhou
functions:
  send-sms:
    handler: app.sms.send
    events:
      - topic: sms-out
""",
          "app/__init__.py": "",
          "app/sms.py": FUTURE + """from py_serverless_kit import BatchResult


def send(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json()
        if not str(msg.get("phone", "")).startswith("+"):
            result.fail(msg)
            continue
        ctx.logger.info("sms sent", extra={"phone": msg["phone"]})
    return result
""",
          "requirements.txt": ""}),
      user="send-sms: batchItemFailures shows {\"itemIdentifier\": {\"phone\": ...}} instead of an id. bug?",
      steps=[
          S("read_file", path="app/sms.py"),
          S("invoke_local", function="send-sms", type="topic", data=[{"phone": "+8613800000000"}, {"phone": "12345"}]),
          S("propose_plan", steps=["Call `result.fail(record)` (the Record), not `result.fail(msg)` (the decoded body)",
                                   "Invoke with a good and a bad phone; validate for alibaba"]),
          S("write_file", path="app/sms.py", content=FUTURE + """from py_serverless_kit import BatchResult


def send(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json()
        if not str(msg.get("phone", "")).startswith("+"):
            result.fail(record)
            continue
        ctx.logger.info("sms sent", extra={"phone": msg["phone"]})
    return result
"""),
          S("invoke_local", function="send-sms", type="topic", data=[{"phone": "+8613800000000"}, {"phone": "12345"}]),
          S("validate"),
      ],
      final="""Yes. `fail()` takes the `Record` (or its id), and you passed the decoded body [docs/handlers.md#batchresult]. Fixed: `result.fail(record)`.

- invoke: `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`.
- validate (alibaba, prod): valid.

On Alibaba there is no partial retry. Any failure raises `BatchFailure`, so the whole delivery retries, and the good SMS may be sent twice. Make sending idempotent."""),

    # ------------------------------------------------------------------ 66  cloudflare http, error dict with 200
    B(66, provider="cloudflare", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: waitlist
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, demo-account}
functions:
  join:
    handler: app.waitlist.join
    events:
      - http: POST /join
""",
          "app/__init__.py": "",
          "app/waitlist.py": FUTURE + """
def join(event, ctx):
    data = event.http.json(default={})
    if not data.get("email"):
        return {"error": "email is required"}
    return {"joined": data["email"]}, 201
""",
          "requirements.txt": ""}),
      user="when the email is missing my page still shows success, because the status is 200 even if there's an error message. how do I send a real error?",
      steps=[
          S("read_file", path="app/waitlist.py"),
          S("invoke_local", function="join", method="POST", path="/join", data={"name": "Rae"}),
          S("search_docs", query="return error status 400",
            docs=[D("docs/handlers.md", "errors", end="| `Unauthorized`")]),
          S("propose_plan", steps=["Raise `BadRequest(\"email is required\")` instead of returning an error dict",
                                   "Test POST /join without email and validate for cloudflare"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/waitlist.py", content=FUTURE + """from py_serverless_kit import BadRequest


def join(event, ctx):
    data = event.http.json(default={})
    if not data.get("email"):
        raise BadRequest("email is required")
    return {"joined": data["email"]}, 201
"""),
          S("invoke_local", function="join", method="POST", path="/join", data={"name": "Rae"}),
          S("validate"),
      ],
      final="""A returned dict is always a normal answer (status 200), even if it contains the word "error". To send a real error, **raise** one of pskit's errors [docs/handlers.md#errors]. `BadRequest` means 400.

- Test without email: status 400, body `{"error": "email is required", "status": 400}`.
- `pskit validate` for cloudflare (staging): valid.

Your page can now check the status (for example `response.ok` in JavaScript) to show the error."""),

    # ------------------------------------------------------------------ 67  tencent http, "false" is truthy
    B(67, provider="tencent", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: cleanup-api
provider:
  name: tencent
  region: ap-chengdu
functions:
  purge-cache:
    handler: app.cache.purge
    events:
      - http: POST /cache/purge
""",
          "app/__init__.py": "",
          "app/cache.py": FUTURE + """
def purge(event, ctx):
    dry_run = event.http.query.get("dry_run")
    if dry_run:
        return {"dry_run": True, "would_purge": 120}
    ctx.logger.warning("purging cache")
    return {"dry_run": False, "purged": 120}
""",
          "requirements.txt": ""}),
      user="POST /cache/purge?dry_run=false is supposed to really purge, but it only returns the dry-run answer. dry_run=true must stay a dry run, and no parameter should mean a real purge. Please fix the flag handling.",
      steps=[
          S("read_file", path="app/cache.py"),
          S("invoke_local", function="purge-cache", method="POST", path="/cache/purge?dry_run=false"),
          S("propose_plan", steps=["Treat dry_run as true only for `1`, `true` or `yes` (case-insensitive); everything else is a real purge",
                                   "Invoke with dry_run=false and dry_run=true; validate for tencent (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/cache.py", content=FUTURE + """
def purge(event, ctx):
    dry_run = event.http.query.get("dry_run", "").lower() in ("1", "true", "yes")
    if dry_run:
        return {"dry_run": True, "would_purge": 120}
    ctx.logger.warning("purging cache")
    return {"dry_run": False, "purged": 120}
"""),
          S("invoke_local", function="purge-cache", method="POST", path="/cache/purge?dry_run=true"),
          S("invoke_local", function="purge-cache", method="POST", path="/cache/purge?dry_run=false"),
          S("validate"),
      ],
      final="""Query values are strings [docs/handlers.md#httprequest], and any non-empty string, including `"false"`, is truthy in Python. So `if dry_run:` was true for `dry_run=false`.

Now only `1`, `true` or `yes` (any case) mean a dry run; anything else, or no parameter, purges.

- `?dry_run=true`: `{"dry_run": true, "would_purge": 120}`.
- `?dry_run=false`: logs "purging cache", `{"dry_run": false, "purged": 120}`.
- `pskit validate` for tencent, prod: valid."""),

    # ------------------------------------------------------------------ 68  digitalocean http, handler module typo
    B(68, provider="digitalocean", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: weather
provider:
  name: digitalocean
  region: tor1
  options:
    namespace: ${env:DO_NAMESPACE, fn-weather}
functions:
  current:
    handler: app.handler.get_weather
    events:
      - http: GET /weather
""",
          "app/__init__.py": "",
          "app/handlers.py": FUTURE + """
def get_weather(event, ctx):
    city = event.http.query.get("city", "Toronto")
    return {"city": city, "temp_c": 4}
""",
          "requirements.txt": ""}),
      user="my weather function gives 500 when I test it, and there's a warning about the handler. I didn't change anything in the code",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("invoke_local", function="current", method="GET", path="/weather?city=Ottawa"),
          S("propose_plan", steps=["Change `functions.current.handler` to `app.handlers.get_weather` (the file is `app/handlers.py`)",
                                   "Validate for digitalocean and test GET /weather"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.current.handler", value="app.handlers.get_weather"),
          S("invoke_local", function="current", method="GET", path="/weather?city=Ottawa"),
      ],
      final="""The code is fine, but `pskit.yml` points at the wrong file. The handler is `app.handler.get_weather` (module `app/handler.py`), while your file is `app/handlers.py`, with an **s**. pskit could not import it, so every request failed with 500. The validate warning said the same: module `app.handler` not found.

I changed the handler to `app.handlers.get_weather` [docs/handlers.md#handler-signatures].

- `pskit validate` for digitalocean: valid, and the handler warning is gone (only the `doctl` deploy warning is left).
- Test `/weather?city=Ottawa`: status 200, `{"city": "Ottawa", "temp_c": 4}`."""),

    # ------------------------------------------------------------------ 69  cloudflare schedule, event.type "cron"
    B(69, provider="cloudflare", stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: sitemap
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, demo-account}
functions:
  rebuild:
    handler: app.sitemap.rebuild
    events:
      - schedule: "0 * * * *"
      - http: POST /sitemap/rebuild
""",
          "app/__init__.py": "",
          "app/sitemap.py": FUTURE + """
def rebuild(event, ctx):
    if event.type == "cron":
        ctx.logger.info("scheduled rebuild")
        return {"rebuilt": True, "by": "schedule"}
    if event.is_http:
        return {"rebuilt": True, "by": "http"}
    return {"rebuilt": False}
""",
          "requirements.txt": ""}),
      user="cloudflare cron trigger run rebuild but it return rebuilt false. the http way work. why cron not detect",
      steps=[
          S("read_file", path="app/sitemap.py"),
          S("invoke_local", function="rebuild", type="schedule"),
          S("search_docs", query="schedule event type",
            docs=[D("docs/events.md", "schedule", start="The handler gets", end="The handler gets")]),
          S("propose_plan", steps=["Compare `event.type == \"schedule\"` (pskit's name for every cloud's cron/timer)",
                                   "Invoke rebuild as schedule, validate for cloudflare"]),
          S("write_file", path="app/sitemap.py", content=FUTURE + """
def rebuild(event, ctx):
    if event.type == "schedule":
        ctx.logger.info("scheduled rebuild")
        return {"rebuilt": True, "by": "schedule"}
    if event.is_http:
        return {"rebuilt": True, "by": "http"}
    return {"rebuilt": False}
"""),
          S("invoke_local", function="rebuild", type="schedule"),
          S("validate"),
      ],
      final="""Cloudflare calls it a Cron Trigger, but in pskit every timer event has `event.type == "schedule"` [docs/events.md#schedule]. `"cron"` never matched. Fixed the comparison.

- Schedule run: logged "scheduled rebuild", `{"rebuilt": true, "by": "schedule"}`.
- `pskit validate` for cloudflare: valid (Pyodide note only)."""),

    # ------------------------------------------------------------------ 70  oracle http, body is a list
    B(70, provider="oracle", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: bulk-import
provider:
  name: oracle
  region: eu-amsterdam-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..example}
    subnet_ids: [ocid1.subnet.oc1..example]
    image_repository: ams.ocir.io/example/bulk-import
functions:
  import-rows:
    handler: app.bulk.import_rows
    events:
      - http: POST /import
""",
          "app/__init__.py": "",
          "app/bulk.py": FUTURE + """
def import_rows(event, ctx):
    rows = event.http.json()["items"]
    return {"imported": len(rows)}, 202
""",
          "requirements.txt": ""}),
      user="""TypeError: list indices must be integers or slices, not str
import-rows. the client sends a plain JSON array: [{"id": 1}, {"id": 2}]. older clients send {"items": [...]}, both must work""",
      steps=[
          S("read_file", path="app/bulk.py"),
          S("invoke_local", function="import-rows", method="POST", path="/import", data=[{"id": 1}, {"id": 2}]),
          S("propose_plan", steps=["Accept both shapes: use the body if it is a list, else `body.get(\"items\", [])`",
                                   "POST a plain array and an {items: [...]} body locally; validate for oracle"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/bulk.py", content=FUTURE + """
def import_rows(event, ctx):
    body = event.http.json()
    rows = body if isinstance(body, list) else body.get("items", [])
    return {"imported": len(rows)}, 202
"""),
          S("invoke_local", function="import-rows", method="POST", path="/import", data={"items": [{"id": 3}]}),
          S("invoke_local", function="import-rows", method="POST", path="/import", data=[{"id": 1}, {"id": 2}]),
          S("validate"),
      ],
      final="""`event.http.json()` returns whatever the JSON is [docs/handlers.md#httprequest]. For a plain array that's a list, and `list["items"]` fails. Now the handler accepts both shapes:

```python
rows = body if isinstance(body, list) else body.get("items", [])
```

- POST `{"items": [{"id": 3}]}`: 202, `{"imported": 1}`.
- POST `[{"id": 1}, {"id": 2}]`: 202, `{"imported": 2}`.
- `pskit validate` for oracle: valid. The API Gateway IAM policy WARNING is about deploy setup, not this code."""),

    # ------------------------------------------------------------------ 71  ibm http, str > int
    B(71, provider="ibm", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#errors", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: logs-api
provider:
  name: ibm
  region: ca-tor
  runtime: python3.11
functions:
  recent:
    handler: app.logs.recent
    events:
      - http: GET /logs
""",
          "app/__init__.py": "",
          "app/logs.py": FUTURE + """from py_serverless_kit import BadRequest

LINES = [f"line {i}" for i in range(1, 501)]


def recent(event, ctx):
    limit = event.http.query.get("limit", 50)
    if limit > 100:
        raise BadRequest("limit max is 100")
    return {"lines": LINES[-limit:]}
""",
          "requirements.txt": ""}),
      user="?limit=20 give 500, TypeError '>' not supported between str and int. without limit it work",
      steps=[
          S("read_file", path="app/logs.py"),
          S("invoke_local", function="recent", method="GET", path="/logs?limit=20"),
          S("propose_plan", steps=["Convert `limit` with `int(...)`, and answer 400 if it is not a number",
                                   "Call /logs?limit=20 and /logs?limit=abc locally, then validate for ibm"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/logs.py", content=FUTURE + """from py_serverless_kit import BadRequest

LINES = [f"line {i}" for i in range(1, 501)]


def recent(event, ctx):
    try:
        limit = int(event.http.query.get("limit", "50"))
    except ValueError:
        raise BadRequest("limit must be a number") from None
    if limit > 100:
        raise BadRequest("limit max is 100")
    return {"lines": LINES[-limit:]}
"""),
          S("invoke_local", function="recent", method="GET", path="/logs?limit=abc"),
          S("invoke_local", function="recent", method="GET", path="/logs?limit=3"),
          S("validate"),
      ],
      final="""From the URL, `limit` is the string `"20"` (query values are always strings [docs/handlers.md#httprequest]). Only the default `50` was a number, which is why it worked without `?limit`. Now it is converted with `int()`, and a non-number gives a 400 with `BadRequest` [docs/handlers.md#errors].

- `/logs?limit=abc`: 400, `{"error": "limit must be a number", "status": 400}`.
- `/logs?limit=3`: 200, `["line 498", "line 499", "line 500"]`.
- `pskit validate` for ibm (staging): valid."""),

    # ------------------------------------------------------------------ 72  aws workflow task, returns a tuple
    B(72, provider="aws", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: payments-flow
provider:
  name: aws
  region: us-east-1
functions:
  reserve-funds:
    handler: app.pay.reserve
  capture:
    handler: app.pay.capture
workflows:
  payment:
    start_at: Reserve
    states:
      Reserve:
        type: task
        function: reserve-funds
        next: Capture
      Capture:
        type: task
        function: capture
        end: true
""",
          "app/__init__.py": "",
          "app/pay.py": FUTURE + """
def reserve(event, ctx):
    amount = event.data["amount"]
    return {"reservation": "res-1", "amount": amount}, 200


def capture(event, ctx):
    return {"captured": event.data["reservation"]}
""",
          "requirements.txt": ""}),
      user="In the `payment` workflow, the Capture step gets a JSON array like [{\"reservation\": ...}, 200] from Reserve instead of the object, so `event.data[\"reservation\"]` fails. Reserve should pass {reservation, amount} to Capture. Please fix reserve-funds and verify its output with amount 25.",
      steps=[
          S("read_file", path="app/pay.py"),
          S("invoke_local", function="reserve-funds", type="workflow", data={"amount": 25}),
          S("search_docs", query="non-HTTP return value workflow next state",
            docs=[D("docs/handlers.md", "returning-a-response", start="For non-HTTP events", end="For non-HTTP events")]),
          S("propose_plan", steps=["Return only the dict from `reserve` (drop `, 200`)",
                                   "Invoke reserve-funds as a workflow task with {\"amount\": 25}, then validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/pay.py", content=FUTURE + """
def reserve(event, ctx):
    amount = event.data["amount"]
    return {"reservation": "res-1", "amount": amount}


def capture(event, ctx):
    return {"captured": event.data["reservation"]}
"""),
          S("invoke_local", function="reserve-funds", type="workflow", data={"amount": 25}),
          S("validate"),
      ],
      final="""The `(body, 200)` tuple form only applies to HTTP handlers. For workflow tasks, the return value goes to the next state as it is [docs/handlers.md#returning-a-response], so the tuple became a JSON array. Reserve now returns just the dict.

- invoke reserve-funds `{"amount": 25}`: `{"reservation": "res-1", "amount": 25}`.
- `pskit validate` for aws, prod: valid; `payment` compiles to Step Functions (native engine).

Run the whole flow locally with `pskit workflow run payment -i '{"amount": 25}' --history`."""),

    # ------------------------------------------------------------------ 73  gcp http, content-type with charset compare
    B(73, provider="gcp", stage="prod", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: ingest-api
provider:
  name: gcp
  region: europe-west2
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  ingest:
    handler: app.ingest.ingest
    events:
      - http: POST /ingest
""",
          "app/__init__.py": "",
          "app/ingest.py": FUTURE + """
def ingest(event, ctx):
    if event.http.headers.get("content-type") != "application/json; charset=utf-8":
        return {"error": "send JSON"}, 415
    return {"accepted": len(event.http.json())}, 202
""",
          "requirements.txt": ""}),
      user="Our API Gateway clients always sent 'application/json; charset=utf-8', so I compared the header to that string. Now every JSON request gets my 415 'send JSON'. Is there a cleaner way to check for JSON?",
      steps=[
          S("read_file", path="app/ingest.py"),
          S("invoke_local", function="ingest", method="POST", path="/ingest", data={"a": 1, "b": 2}),
          S("search_docs", query="content type header without parameters",
            docs=[D("docs/handlers.md", "httprequest", start="| `content_type`", end="| `content_type`")]),
          S("propose_plan", steps=["Check `event.http.content_type == \"application/json\"` (it drops `; charset=...`) instead of comparing the raw header",
                                   "POST JSON to /ingest locally and validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/ingest.py", content=FUTURE + """
def ingest(event, ctx):
    if event.http.content_type != "application/json":
        return {"error": "send JSON"}, 415
    return {"accepted": len(event.http.json())}, 202
"""),
          S("invoke_local", function="ingest", method="POST", path="/ingest", data={"a": 1, "b": 2}),
          S("validate"),
      ],
      final="""Comparing the raw header only works if every client sends exactly that string. Plain `application/json` (what my local test sent) failed. `event.http.content_type` gives the type without parameters, e.g. `application/json` [docs/handlers.md#httprequest], so both forms pass:

```python
if event.http.content_type != "application/json":
```

- Local POST /ingest: 202, `{"accepted": 2}` (it was 415 before).
- `pskit validate` for gcp, prod: valid."""),

    # ------------------------------------------------------------------ 74  azure schedule, input key mismatch (ask)
    B(74, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: reminders
provider:
  name: azure
  region: australiaeast
functions:
  remind:
    handler: app.remind.remind
    events:
      - schedule:
          cron: "0 9 * * 1-5"
          input:
            target: [team-a, team-b]
""",
          "app/__init__.py": "",
          "app/remind.py": FUTURE + """
def remind(event, ctx):
    sent = []
    for team in event.data["targets"]:
        ctx.logger.info("reminder", extra={"team": team})
        sent.append(team)
    return {"sent": sent}
""",
          "requirements.txt": ""}),
      user="my reminder job says KeyError: 'targets'. I don't know where targets is supposed to come from",
      steps=[
          S("get_project"),
          S("read_file", path="app/remind.py"),
          S("invoke_local", function="remind", type="schedule"),
          S("ask_user", question="The schedule input calls the list `target`, but the code reads `targets`. Which name should I change?",
                options=["Rename it in pskit.yml to targets", "Change the code to read target"],
                answer="Rename it in pskit.yml to targets"),
          S("propose_plan", steps=["Set the schedule input to `{targets: [team-a, team-b]}` in pskit.yml (code unchanged)",
                                   "Validate for azure and run the schedule event locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.remind.events.0.schedule.input", value={"targets": ["team-a", "team-b"]}),
          S("invoke_local", function="remind", type="schedule"),
      ],
      final="""`targets` should come from the schedule's `input`, which the handler gets as `event.data` [docs/events.md#schedule]. In your pskit.yml the key was spelled `target`, so `event.data["targets"]` didn't exist.

As you chose, I renamed it in pskit.yml:

```yaml
events:
  - schedule:
      cron: "0 9 * * 1-5"
      input: {targets: [team-a, team-b]}
```

- `pskit validate` for azure: valid.
- Local run: reminders logged for team-a and team-b, `{"sent": ["team-a", "team-b"]}`."""),

    # ------------------------------------------------------------------ 75  onprem http, get_secret missing locally
    B(75, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#get_secret-secrets-on-every-provider"],
      project=dict(files={
          "pskit.yml": """service: partner-proxy
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8160
functions:
  quote:
    handler: app.partner.quote
    events:
      - http: GET /partner/quote
""",
          "app/__init__.py": "",
          "app/partner.py": FUTURE + """from py_serverless_kit import get_secret


def quote(event, ctx):
    partner_key = get_secret("partner-key")
    return {"configured": bool(partner_key), "quote": 42}
""",
          "requirements.txt": ""}),
      user="quote work on server but local test give 500 SecretNotFound partner-key. i dont want put the key in the code. what to do",
      steps=[
          S("read_file", path="app/partner.py"),
          S("invoke_local", function="quote", method="GET", path="/partner/quote"),
          S("search_docs", query="get_secret default SecretNotFound env driver",
            docs=[D("docs/handlers.md", "get_secret-secrets-on-every-provider", end="or `env` (default:")]),
          S("propose_plan", steps=["Call `get_secret(\"partner-key\", default=\"\")` and return a 503 \"partner key not configured\" when it is empty",
                                   "Test GET /partner/quote locally (expect 503 without the secret) and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/partner.py", content=FUTURE + """from py_serverless_kit import get_secret


def quote(event, ctx):
    partner_key = get_secret("partner-key", default="")
    if not partner_key:
        return {"error": "partner key not configured"}, 503
    return {"configured": True, "quote": 42}
"""),
          S("invoke_local", function="quote", method="GET", path="/partner/quote"),
          S("validate"),
      ],
      final="""Right, keep it out of the code. On the server the secret comes from its store. Locally no store is set, so `get_secret("partner-key")` raised `SecretNotFound`, which became a 500.

Change: `get_secret("partner-key", default="")` [docs/handlers.md#get_secret-secrets-on-every-provider], and a clear 503 answer if it's empty (returned, so no traceback is logged for a known setup problem).

- Local test without the key: status 503, `{"error": "partner key not configured"}`.
- `pskit validate` for onprem: valid.

To test with a real key locally, set the environment variable `PSKIT_SECRET_PARTNER_KEY` only for your session: **Setup & credentials** > **Environment variables** > **Set for this session**, or in a git-ignored `.env` file. Not in pskit.yml, not in code."""),

    # ------------------------------------------------------------------ 76  alibaba http, event.data on HTTP
    B(76, provider="alibaba", stage="dev", mode="auto", page="Test", persona="beginner",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: polls
provider:
  name: alibaba
  region: cn-qingdao
functions:
  vote:
    handler: app.polls.vote
    events:
      - http: POST /vote
""",
          "app/__init__.py": "",
          "app/polls.py": FUTURE + """
def vote(event, ctx):
    choice = event.data.get("choice")
    return {"voted": choice}, 201
""",
          "requirements.txt": ""}),
      user="I send {\"choice\": \"blue\"} to /vote and get 500, the log says 'NoneType' object has no attribute 'get'. I thought event.data is what I send?",
      steps=[
          S("read_file", path="app/polls.py"),
          S("invoke_local", function="vote", method="POST", path="/vote", data={"choice": "blue"}),
          S("search_docs", query="event data http body",
            docs=[D("docs/handlers.md", "event", start="| `http`", end="| `data`")]),
          S("propose_plan", steps=["Read the request body with `event.http.json()` instead of `event.data`",
                                   "Test POST /vote and validate for alibaba"]),
          S("write_file", path="app/polls.py", content=FUTURE + """
def vote(event, ctx):
    choice = event.http.json().get("choice")
    return {"voted": choice}, 201
"""),
          S("invoke_local", function="vote", method="POST", path="/vote", data={"choice": "blue"}),
          S("validate"),
      ],
      final="""Close, but not for web requests. `event.data` is only for schedule, invoke and workflow events. For HTTP the body is in `event.http`, and `event.http.json()` reads it [docs/handlers.md#event].

- Test POST /vote `{"choice": "blue"}`: status 201, `{"voted": "blue"}`.
- `pskit validate` for alibaba: valid.

Tip: `event.json()` also works for any type; for HTTP it returns the body."""),

    # ------------------------------------------------------------------ 77  huawei schedule, extra required parameter
    B(77, provider="huawei", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: billing-close
provider:
  name: huawei
  region: ap-southeast-3
functions:
  close-month:
    handler: app.close.close_month
    events:
      - schedule: "0 1 1 * *"
""",
          "app/__init__.py": "",
          "app/close.py": FUTURE + """
def close_month(event, ctx, dry_run):
    ctx.logger.info("closing month", extra={"dry_run": dry_run})
    return {"closed": not dry_run}
""",
          "requirements.txt": ""}),
      user="""TypeError: close_month() missing 1 required positional argument: 'dry_run'
close-month, monthly schedule. dry_run should be false normally, true only when we pass it""",
      steps=[
          S("read_file", path="app/close.py"),
          S("invoke_local", function="close-month", type="schedule"),
          S("search_docs", query="handler signature arguments",
            docs=[D("docs/handlers.md", "handler-signatures", end="async def handler")]),
          S("propose_plan", steps=["Keep the signature `(event, ctx)` and read `dry_run` from `event.data` (default false)",
                                   "Run close-month as a schedule event and as an invoke with {\"dry_run\": true}; validate for huawei"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/close.py", content=FUTURE + """
def close_month(event, ctx):
    dry_run = bool((event.data or {}).get("dry_run", False))
    ctx.logger.info("closing month", extra={"dry_run": dry_run})
    return {"closed": not dry_run}
"""),
          S("invoke_local", function="close-month", type="invoke", data={"dry_run": True}),
          S("invoke_local", function="close-month", type="schedule"),
          S("validate"),
      ],
      final="""pskit calls a handler with one or two arguments, `(event)` or `(event, ctx)` [docs/handlers.md#handler-signatures], never a third. Options travel in the event: `dry_run` now comes from `event.data` and defaults to false.

- Invoke with `{"dry_run": true}`: `{"closed": false}`.
- Monthly schedule run (no input): `{"closed": true}`.
- `pskit validate` for huawei (staging): valid."""),

    # ------------------------------------------------------------------ 78  tencent schedule, import of renamed module
    B(78, provider="tencent", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[],
      project=dict(files={
          "pskit.yml": """service: tidy-up
provider:
  name: tencent
  region: ap-nanjing
functions:
  tidy:
    handler: app.jobs.run
    events:
      - schedule: 1 day
""",
          "app/__init__.py": "",
          "app/jobs.py": FUTURE + """from app.helpers import tidy_names


def run(event, ctx):
    names = tidy_names(["  Report.PDF ", "notes.TXT"])
    return {"names": names}
""",
          "app/utils.py": FUTURE + """
def tidy_names(names):
    return [n.strip().lower() for n in names]
""",
          "requirements.txt": ""}),
      user="after i rename helpers.py to utils.py the tidy job say Cannot import module 'app.jobs'. but jobs.py is still there?!",
      steps=[
          S("get_project"),
          S("read_file", path="app/jobs.py"),
          S("invoke_local", function="tidy", type="schedule"),
          S("propose_plan", steps=["Change the import in `app/jobs.py` to `from app.utils import tidy_names`",
                                   "Run tidy as a schedule event, validate for tencent"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/jobs.py", content=FUTURE + """from app.utils import tidy_names


def run(event, ctx):
    names = tidy_names(["  Report.PDF ", "notes.TXT"])
    return {"names": names}
"""),
          S("invoke_local", function="tidy", type="schedule"),
          S("validate"),
      ],
      final="""`jobs.py` is there, but its first line still imports from `app.helpers`, which no longer exists. So importing `app.jobs` fails. The message ends with the real reason: `No module named 'app.helpers'`.

Fixed the import: `from app.utils import tidy_names`.

- Schedule run: `{"names": ["report.pdf", "notes.txt"]}`.
- `pskit validate` for tencent: valid.

Note: `pskit validate` only checks that the handler module file exists, not its imports. A local run (**Test** > **▶ Run locally**) catches this kind of error."""),

    # ------------------------------------------------------------------ 79  ibm http, cookie KeyError -> 401
    B(79, provider="ibm", stage="prod", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: account-api
provider:
  name: ibm
  region: us-east
  runtime: python3.11
functions:
  me:
    handler: app.me.me
    events:
      - http: GET /me
""",
          "app/__init__.py": "",
          "app/me.py": FUTURE + """
def me(event, ctx):
    session = event.http.cookies["session"]
    return {"session": session[:6], "user": "demo"}
""",
          "requirements.txt": ""}),
      user="GET /me without session cookie -> 500 KeyError. should be 401",
      steps=[
          S("read_file", path="app/me.py"),
          S("invoke_local", function="me", method="GET", path="/me"),
          S("propose_plan", steps=["Use `cookies.get(\"session\")` and raise `Unauthorized` when it is missing",
                                   "Invoke GET /me without a cookie (expect 401), validate for ibm"]),
          S("write_file", path="app/me.py", content=FUTURE + """from py_serverless_kit import Unauthorized


def me(event, ctx):
    session = event.http.cookies.get("session")
    if not session:
        raise Unauthorized("login required")
    return {"session": session[:6], "user": "demo"}
"""),
          S("invoke_local", function="me", method="GET", path="/me"),
          S("validate"),
      ],
      final="""`cookies` is a plain dict parsed from the `Cookie` header [docs/handlers.md#httprequest]. Now it uses `.get` and raises `Unauthorized` [docs/handlers.md#errors].

- invoke GET /me (no cookie): 401, `{"error": "login required", "status": 401}`.
- validate (ibm, prod): valid.

Cookie path not run here (no headers in my local call): `pskit invoke -f me --path /me -H "Cookie: session=abc123xyz"`."""),

    # ------------------------------------------------------------------ 80  cloudflare http, None.lower()
    B(80, provider="cloudflare", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: glossary
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, demo-account}
functions:
  lookup-term:
    handler: app.glossary.lookup
    events:
      - http: GET /terms
""",
          "app/__init__.py": "",
          "app/glossary.py": FUTURE + """TERMS = {"api": "Application Programming Interface", "cdn": "Content Delivery Network"}


def lookup(event, ctx):
    q = event.http.query.get("q").lower()
    return {"matches": {k: v for k, v in TERMS.items() if q in k}}
""",
          "requirements.txt": ""}),
      user="/terms?q=API work, but plain /terms give 500 'NoneType' has no attribute lower. without q it should list all terms",
      steps=[
          S("read_file", path="app/glossary.py"),
          S("invoke_local", function="lookup-term", method="GET", path="/terms"),
          S("propose_plan", steps=["Default `q` to an empty string: `event.http.query.get(\"q\", \"\").lower()` (an empty q matches every term)",
                                   "Test /terms and /terms?q=API, then validate for cloudflare (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/glossary.py", content=FUTURE + """TERMS = {"api": "Application Programming Interface", "cdn": "Content Delivery Network"}


def lookup(event, ctx):
    q = event.http.query.get("q", "").lower()
    return {"matches": {k: v for k, v in TERMS.items() if q in k}}
"""),
          S("invoke_local", function="lookup-term", method="GET", path="/terms?q=API"),
          S("invoke_local", function="lookup-term", method="GET", path="/terms"),
          S("validate"),
      ],
      final="""Without `?q`, `query.get("q")` is `None`, and `None.lower()` crashes [docs/handlers.md#httprequest]. Now `q` defaults to `""`, and an empty string matches every term.

- `/terms?q=API`: 200, only `api`.
- `/terms`: 200, both `api` and `cdn`.
- `pskit validate` for cloudflare (prod): valid (Pyodide note only)."""),
]
