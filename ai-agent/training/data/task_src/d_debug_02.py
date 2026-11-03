"""Category D (fix a handler bug), batch 2. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"d_debug-{n:04d}", category="d_debug", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 21  aws storage, Record subscript
    B(21, provider="aws", stage="staging", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: csv-loader
provider:
  name: aws
  region: eu-west-2
functions:
  load-csv:
    handler: app.loader.load
    events:
      - storage:
          bucket: csv-drop
          suffix: .csv
""",
          "app/__init__.py": "",
          "app/loader.py": FUTURE + """
def load(event, ctx):
    key = event.records[0]["key"]
    ctx.logger.info("loading", extra={"key": key})
    return {"loaded": key}
""",
          "requirements.txt": ""}),
      user="load-csv crash: 'Record' object is not subscriptable. how i get the file name from record?",
      steps=[
          S("read_file", path="app/loader.py"),
          S("invoke_local", function="load-csv", type="storage", data={"bucket": "csv-drop", "key": "sales/2026-10.csv"}),
          S("search_docs", query="record key attribute storage",
            docs=[D("docs/handlers.md", "record", end="| `bucket`, `key`")]),
          S("propose_plan", steps=["Use the attribute `record.key` (not `record[\"key\"]`) and loop over all records, not only the first",
                                   "Run load-csv with a storage event and validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/loader.py", content=FUTURE + """
def load(event, ctx):
    loaded = []
    for record in event.records:
        ctx.logger.info("loading", extra={"key": record.key})
        loaded.append(record.key)
    return {"loaded": loaded}
"""),
          S("invoke_local", function="load-csv", type="storage", data={"bucket": "csv-drop", "key": "sales/2026-10.csv"}),
          S("validate"),
      ],
      final="""A `Record` is an object, not a dict, so use attributes: `record.key`, `record.bucket`, `record.size` [docs/handlers.md#record].

I also loop over all `event.records`. One S3 delivery can carry more than one file, and `[0]` would skip the rest.

- Local run with `sales/2026-10.csv`: `{"loaded": ["sales/2026-10.csv"]}`.
- `pskit validate` for aws (staging): valid.

Test again: `pskit invoke -f load-csv -t storage -d '{"bucket": "csv-drop", "key": "sales/2026-10.csv"}'`."""),

    # ------------------------------------------------------------------ 22  gcp http, path param name mismatch
    B(22, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: accounts
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  get-user:
    handler: app.users.get_user
    events:
      - http: GET /users/{id}
""",
          "app/__init__.py": "",
          "app/users.py": FUTURE + """from py_serverless_kit import NotFound

USERS = {"42": {"id": "42", "name": "Ada"}}


def get_user(event, ctx):
    user_id = event.http.path_params["user_id"]
    if user_id not in USERS:
        raise NotFound("no such user")
    return USERS[user_id]
""",
          "requirements.txt": ""}),
      user="GET /users/42 on get-user always returns 500, even though user 42 exists in the USERS dict. Expected: 200 with the user, and 404 for unknown ids. The route in pskit.yml is /users/{id}. Please find the bug and keep the route as it is.",
      steps=[
          S("get_project"),
          S("read_file", path="app/users.py"),
          S("invoke_local", function="get-user", method="GET", path="/users/42"),
          S("propose_plan", steps=["Read `event.http.path_params[\"id\"]`, the name used in the route `/users/{id}`",
                                   "Invoke GET /users/42 and GET /users/7 locally, then validate for gcp (prod)"],
            result={"decision": "approved", "note": "only test 42, skip the 404 call"}),
          S("write_file", path="app/users.py", content=FUTURE + """from py_serverless_kit import NotFound

USERS = {"42": {"id": "42", "name": "Ada"}}


def get_user(event, ctx):
    user_id = event.http.path_params["id"]
    if user_id not in USERS:
        raise NotFound("no such user")
    return USERS[user_id]
"""),
          S("invoke_local", function="get-user", method="GET", path="/users/42"),
          S("validate"),
      ],
      final="""Cause: `path_params` uses the names from the route template [docs/handlers.md#httprequest]. Your route is `/users/{id}`, so the key is `id`. `path_params["user_id"]` raised `KeyError`, which became the 500.

Fix (route unchanged): `user_id = event.http.path_params["id"]`.

- Local GET /users/42: status 200, `{"id": "42", "name": "Ada"}`.
- `pskit validate` for gcp, prod: valid.

As you asked, I skipped the 404 call. Unknown ids still go to the `NotFound` branch, which returns 404."""),

    # ------------------------------------------------------------------ 23  azure http, direct invoke has no http
    B(23, provider="azure", stage="dev", mode="auto", page="Test", persona="beginner",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: greet-app
provider:
  name: azure
  region: eastus
functions:
  greet:
    handler: app.greet.greet
    events:
      - http: GET /greet
""",
          "app/__init__.py": "",
          "app/greet.py": FUTURE + """
def greet(event, ctx):
    name = event.http.query.get("name", "friend")
    return {"message": f"Hello, {name}!"}
""",
          "requirements.txt": ""}),
      user="when I pick Direct invoke on the Test page my greet function crashes with 'NoneType' object has no attribute 'query'. As HTTP it works. I want other functions to call it with invoke() too",
      steps=[
          S("read_file", path="app/greet.py"),
          S("invoke_local", function="greet", type="invoke", data={"name": "Mia"}),
          S("search_docs", query="event http None invoke data",
            docs=[D("docs/handlers.md", "event", end="| `data` |")]),
          S("propose_plan", steps=["Read `name` from the query for HTTP calls and from `event.data` when `event.http` is None",
                                   "Run greet as a direct invoke and as HTTP, then validate for azure"]),
          S("write_file", path="app/greet.py", content=FUTURE + """
def greet(event, ctx):
    if event.http is not None:
        name = event.http.query.get("name", "friend")
    else:
        name = (event.data or {}).get("name", "friend")
    return {"message": f"Hello, {name}!"}
"""),
          S("invoke_local", function="greet", type="invoke", data={"name": "Mia"}),
          S("invoke_local", function="greet", method="GET", path="/greet?name=Mia"),
          S("validate"),
      ],
      final="""A direct invoke is not a web request, so `event.http` is `None` and the input is in `event.data` [docs/handlers.md#event]. Your code always used `event.http.query`.

Now `greet` handles both:
- web request: `?name=` from the query
- direct invoke / `invoke("greet", {"name": "Mia"})`: `event.data["name"]`

Checks:
- Direct invoke with `{"name": "Mia"}`: `{"message": "Hello, Mia!"}`.
- HTTP GET `/greet?name=Mia`: status 200, same message.
- `pskit validate` for azure: valid."""),

    # ------------------------------------------------------------------ 24  onprem queue, plain-text messages
    B(24, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: alerts
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8110
functions:
  page-oncall:
    handler: app.alerts.page
    events:
      - queue: alerts
""",
          "app/__init__.py": "",
          "app/alerts.py": FUTURE + """
def page(event, ctx):
    for record in event.records:
        alert = record.json()
        ctx.logger.warning("ALERT", extra={"alert": alert})
    return {"paged": len(event.records)}
""",
          "requirements.txt": ""}),
      user="""py_serverless_kit.runtime.errors.BadRequest: Record local-0 body is not valid JSON
our monitoring puts plain text lines in the alerts queue, like "disk full on node-3". page-oncall can't read them""",
      steps=[
          S("read_file", path="app/alerts.py"),
          S("invoke_local", function="page-oncall", type="queue", data=["disk full on node-3"]),
          S("search_docs", query="record text body decode",
            docs=[D("docs/handlers.md", "record", start="| `body`", end="| `text()`")]),
          S("propose_plan", steps=["Read each message with `record.text()` instead of `record.json()`",
                                   "Run page-oncall with a plain-text message and validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/alerts.py", content=FUTURE + """
def page(event, ctx):
    for record in event.records:
        alert = record.text()
        ctx.logger.warning("ALERT", extra={"alert": alert})
    return {"paged": len(event.records)}
"""),
          S("invoke_local", function="page-oncall", type="queue", data=["disk full on node-3"]),
          S("validate"),
      ],
      final="""`record.json()` expects a JSON body, and `disk full on node-3` isn't JSON. For plain text, use `record.text()` [docs/handlers.md#record].

Changed one line in `app/alerts.py`: `alert = record.text()`.

- Local run with `"disk full on node-3"`: logged the ALERT with the text, returned `{"paged": 1}`.
- `pskit validate` for onprem, prod: valid.

If the queue may get both kinds, `record.json(default=None)` returns None instead of raising, and you can fall back to `record.text()`."""),

    # ------------------------------------------------------------------ 25  cloudflare schedule, missing datetime import
    B(25, provider="cloudflare", stage="staging", mode="auto", page="Code", persona="terse_expert",
      sources=[],
      project=dict(files={
          "pskit.yml": """service: heartbeat
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, demo-account}
functions:
  beat:
    handler: app.beat.beat
    events:
      - schedule: 10 minutes
""",
          "app/__init__.py": "",
          "app/beat.py": FUTURE + """
def beat(event, ctx):
    now = datetime.now(timezone.utc)
    ctx.logger.info("heartbeat", extra={"at": now.isoformat()})
    return {"stage": ctx.stage, "minute": now.minute}
""",
          "requirements.txt": ""}),
      user="beat: NameError datetime. add the import",
      steps=[
          S("read_file", path="app/beat.py"),
          S("invoke_local", function="beat", type="schedule"),
          S("propose_plan", steps=["Add `from datetime import datetime, timezone` to `app/beat.py`",
                                   "Invoke beat, validate for cloudflare"]),
          S("write_file", path="app/beat.py", content=FUTURE + """from datetime import datetime, timezone


def beat(event, ctx):
    now = datetime.now(timezone.utc)
    ctx.logger.info("heartbeat", extra={"at": now.isoformat()})
    return {"stage": ctx.stage, "minute": now.minute}
"""),
          S("invoke_local", function="beat", type="schedule"),
          S("validate"),
      ],
      final="""Added `from datetime import datetime, timezone` (both names were missing).

- invoke: logged `heartbeat`, returned stage `staging` and the current minute.
- validate (cloudflare, staging): valid. The usual Pyodide WARNING is shown; `datetime` is standard library, so it's not affected."""),

    # ------------------------------------------------------------------ 26  digitalocean schedule, run by hand without input
    B(26, provider="digitalocean", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: cleaner
provider:
  name: digitalocean
  region: fra1
  options:
    namespace: ${env:DO_NAMESPACE, fn-cleaner}
functions:
  purge:
    handler: app.purge.purge
    events:
      - schedule:
          cron: "30 1 * * *"
          input: {days: 14}
""",
          "app/__init__.py": "",
          "app/purge.py": FUTURE + """
def purge(event, ctx):
    days = event.data["days"]
    ctx.logger.info("purging", extra={"older_than_days": days})
    return {"purged_older_than": days}
""",
          "requirements.txt": ""}),
      user="purge run fine by schedule but when i run it by hand with Direct invoke and empty payload it crash NoneType not subscriptable. can it use 14 days when nothing given?",
      steps=[
          S("read_file", path="app/purge.py"),
          S("invoke_local", function="purge", type="invoke"),
          S("propose_plan", steps=["Read `days` with a fallback: `(event.data or {}).get(\"days\", 14)`",
                                   "Run purge by hand without payload and as a schedule, then validate for digitalocean"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/purge.py", content=FUTURE + """
def purge(event, ctx):
    days = (event.data or {}).get("days", 14)
    ctx.logger.info("purging", extra={"older_than_days": days})
    return {"purged_older_than": days}
"""),
          S("invoke_local", function="purge", type="invoke"),
          S("invoke_local", function="purge", type="schedule"),
          S("validate"),
      ],
      final="""On a schedule run, `event.data` is the configured `input` (`{days: 14}`) [docs/events.md#schedule]. A direct invoke with an empty payload has `event.data = None`, so `event.data["days"]` crashed.

Now: `days = (event.data or {}).get("days", 14)`.

- Direct invoke, no payload: `{"purged_older_than": 14}`.
- Schedule run (uses the input): `{"purged_older_than": 14}`.
- `pskit validate` for digitalocean: valid (only the warning that `doctl` is not installed, needed for deploy)."""),

    # ------------------------------------------------------------------ 27  oracle http, HttpError(404) -> 500
    B(27, provider="oracle", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: docs-api
provider:
  name: oracle
  region: us-ashburn-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..example}
    subnet_ids: [ocid1.subnet.oc1..example]
    image_repository: iad.ocir.io/example/docs-api
functions:
  get-doc:
    handler: app.docs.get_doc
    events:
      - http: GET /docs/{slug}
""",
          "app/__init__.py": "",
          "app/docs.py": FUTURE + """from py_serverless_kit import HttpError

DOCS = {"intro": "Welcome"}


def get_doc(event, ctx):
    slug = event.http.path_params["slug"]
    if slug not in DOCS:
        raise HttpError(404)
    return {"slug": slug, "text": DOCS[slug]}
""",
          "requirements.txt": ""}),
      user="For an unknown slug, get-doc should return 404. Instead I get status 500 with the body {\"error\": 404, \"status\": 500}. So the 404 ends up in the message, not in the status. Please correct it and show me the local result for /docs/missing.",
      steps=[
          S("read_file", path="app/docs.py"),
          S("invoke_local", function="get-doc", method="GET", path="/docs/missing"),
          S("search_docs", query="HttpError message status keyword NotFound",
            docs=[D("docs/handlers.md", "errors", start="| `NotFound`", end="| `HttpError(message")]),
          S("propose_plan", steps=["Raise `NotFound(\"doc not found\")` instead of `HttpError(404)`",
                                   "Invoke GET /docs/missing and validate for oracle"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/docs.py", content=FUTURE + """from py_serverless_kit import NotFound

DOCS = {"intro": "Welcome"}


def get_doc(event, ctx):
    slug = event.http.path_params["slug"]
    if slug not in DOCS:
        raise NotFound("doc not found")
    return {"slug": slug, "text": DOCS[slug]}
"""),
          S("invoke_local", function="get-doc", method="GET", path="/docs/missing"),
          S("validate"),
      ],
      final="""Exactly: the first positional argument of `HttpError` is the **message**, so `HttpError(404)` is a 500 error whose message is 404. The status must be passed as `status=` or by using a subclass [docs/handlers.md#errors].

Now it raises `NotFound("doc not found")`.

- Local GET /docs/missing: status 404, body `{"error": "doc not found", "status": 404}`.
- `pskit validate` for oracle (staging): valid, with one WARNING. API Gateway needs an IAM policy to call functions, so add that policy in OCI before you deploy."""),

    # ------------------------------------------------------------------ 28  ibm http, bytes body .get
    B(28, provider="ibm", stage="staging", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: contact-form
provider:
  name: ibm
  region: us-south
  runtime: python3.11
functions:
  contact:
    handler: app.contact.submit
    events:
      - http: POST /contact
""",
          "app/__init__.py": "",
          "app/contact.py": FUTURE + """
def submit(event, ctx):
    name = event.http.body.get("name")
    ctx.logger.info("contact", extra={"name": name})
    return {"thanks": name}, 201
""",
          "requirements.txt": ""}),
      user="contact post fail 500 AttributeError bytes object has no attribute get. i send json from the form",
      steps=[
          S("read_file", path="app/contact.py"),
          S("invoke_local", function="contact", method="POST", path="/contact", data={"name": "Lena"}),
          S("propose_plan", steps=["Parse the JSON body with `event.http.json()` before reading `name`",
                                   "Invoke POST /contact locally and validate for ibm"]),
          S("write_file", path="app/contact.py", content=FUTURE + """
def submit(event, ctx):
    name = event.http.json().get("name")
    ctx.logger.info("contact", extra={"name": name})
    return {"thanks": name}, 201
"""),
          S("invoke_local", function="contact", method="POST", path="/contact", data={"name": "Lena"}),
          S("validate"),
      ],
      final="""`event.http.body` is raw `bytes`, not a dict [docs/handlers.md#httprequest]. `event.http.json()` parses it, and bad JSON gives a 400 instead of a 500.

Fix: `name = event.http.json().get("name")`

- Local POST /contact with `{"name": "Lena"}`: status 201, `{"thanks": "Lena"}`.
- `pskit validate` for ibm: valid."""),

    # ------------------------------------------------------------------ 29  aws topic, event.raw SNS dict
    B(29, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#event", "docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: notifier
provider:
  name: aws
  region: us-west-2
functions:
  on-order-event:
    handler: app.notify.on_event
    events:
      - topic: order-events
""",
          "app/__init__.py": "",
          "app/notify.py": FUTURE + """import json


def on_event(event, ctx):
    message = json.loads(event.raw["Records"][0]["Sns"]["Message"])
    ctx.logger.info("order event", extra={"order": message["order_id"]})
    return {"order": message["order_id"]}
""",
          "requirements.txt": ""}),
      user="My SNS handler reads event.raw['Records'][0]['Sns']['Message'] like in Lambda. pskit invoke fails with 'NoneType' object is not subscriptable. Isn't raw the original SNS event?",
      steps=[
          S("read_file", path="app/notify.py"),
          S("invoke_local", function="on-order-event", type="topic", data=[{"order_id": 501}]),
          S("search_docs", query="event raw native payload portable record body",
            docs=[D("docs/handlers.md", "event", start="| `records`", end="| `raw`")]),
          S("propose_plan", steps=["Read each SNS message with `record.json()` from `event.records` instead of `event.raw`",
                                   "Invoke on-order-event with a topic message and validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/notify.py", content=FUTURE + """
def on_event(event, ctx):
    orders = []
    for record in event.records:
        message = record.json()
        ctx.logger.info("order event", extra={"order": message["order_id"]})
        orders.append(message["order_id"])
    return {"orders": orders}
"""),
          S("invoke_local", function="on-order-event", type="topic", data=[{"order_id": 501}]),
          S("validate"),
      ],
      final="""On Lambda, `event.raw` is the SNS event. But `raw` is "the untouched native payload (use sparingly: it's not portable)" [docs/handlers.md#event]. A local run has no native payload, so it is `None`, and it would be different again on another cloud.

The portable way: each SNS message is a `Record` in `event.records`, and `record.json()` decodes the message.

- Local topic message `{"order_id": 501}`: `{"orders": [501]}`.
- `pskit validate` for aws: valid.

The same code now works on Lambda and locally, with no `json` import."""),

    # ------------------------------------------------------------------ 30  gcp topic, attributes KeyError
    B(30, provider="gcp", stage="staging", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#record", "docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: events-router
provider:
  name: gcp
  region: us-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  route-event:
    handler: app.router.route
    events:
      - topic: domain-events
""",
          "app/__init__.py": "",
          "app/router.py": FUTURE + """
def route(event, ctx):
    routed = []
    for record in event.records:
        kind = record.attributes["type"]
        routed.append(kind)
    return {"routed": routed}
""",
          "requirements.txt": ""}),
      user="route-event KeyError 'type' on record.attributes. publishers set type in the body too. fall back to body.type",
      steps=[
          S("read_file", path="app/router.py"),
          S("invoke_local", function="route-event", type="topic", data=[{"type": "user.created", "id": 3}]),
          S("propose_plan", steps=["Use `record.attributes.get(\"type\")`, falling back to `record.json().get(\"type\")`",
                                   "Invoke with a message without attributes; validate for gcp"]),
          S("write_file", path="app/router.py", content=FUTURE + """
def route(event, ctx):
    routed = []
    for record in event.records:
        kind = record.attributes.get("type") or record.json(default={}).get("type", "unknown")
        routed.append(kind)
    return {"routed": routed}
"""),
          S("invoke_local", function="route-event", type="topic", data=[{"type": "user.created", "id": 3}]),
          S("validate"),
      ],
      final="""Messages without a `type` attribute have none in `record.attributes`. Now the handler uses the attribute if it is there, else `type` from the JSON body, else `"unknown"` [docs/handlers.md#record].

- invoke (no attributes, body type `user.created`): `{"routed": ["user.created"]}`.
- validate (gcp, staging): valid.

On GCP the topic `filter` is not applied, so filtering by type in the handler like this is the right place [docs/events.md#topic]."""),

    # ------------------------------------------------------------------ 31  huawei storage, one-arg handler uses ctx
    B(31, provider="huawei", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: scans
provider:
  name: huawei
  region: cn-east-3
functions:
  on-scan:
    handler: app.scans.on_scan
    events:
      - storage: scanned-docs
""",
          "app/__init__.py": "",
          "app/scans.py": FUTURE + """
def on_scan(event):
    for record in event.records:
        ctx.logger.info("scan received", extra={"key": record.key})
    return {"files": len(event.records)}
""",
          "requirements.txt": ""}),
      user="I copied the logging line from the docs, now my scan function says name 'ctx' is not defined. Where does ctx come from?",
      steps=[
          S("read_file", path="app/scans.py"),
          S("invoke_local", function="on-scan", type="storage", data={"bucket": "scanned-docs", "key": "contract.pdf"}),
          S("search_docs", query="handler arguments event ctx context",
            docs=[D("docs/handlers.md", "handler-signatures")]),
          S("propose_plan", steps=["Add the second parameter: `def on_scan(event, ctx)`",
                                   "Run on-scan with a storage event and validate for huawei"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/scans.py", content=FUTURE + """
def on_scan(event, ctx):
    for record in event.records:
        ctx.logger.info("scan received", extra={"key": record.key})
    return {"files": len(event.records)}
"""),
          S("invoke_local", function="on-scan", type="storage", data={"bucket": "scanned-docs", "key": "contract.pdf"}),
          S("validate"),
      ],
      final="""`ctx` is the second argument pskit passes to your handler. Your function only takes `event`. pskit allows that, but then there is no `ctx` inside [docs/handlers.md#handler-signatures].

Fixed: `def on_scan(event, ctx):`

- Test with `contract.pdf`: logged "scan received" and returned `{"files": 1}`.
- `pskit validate` for huawei: valid."""),

    # ------------------------------------------------------------------ 32  alibaba schedule, asyncio.run inside async handler
    B(32, provider="alibaba", stage="staging", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: price-feeds
provider:
  name: alibaba
  region: cn-beijing
functions:
  refresh-prices:
    handler: app.feeds.refresh
    events:
      - schedule: 30 minutes
""",
          "app/__init__.py": "",
          "app/feeds.py": FUTURE + """import asyncio

FEEDS = ["fx", "metals", "energy"]


async def fetch(name):
    await asyncio.sleep(0)
    return {"feed": name, "ok": True}


async def fetch_all():
    return await asyncio.gather(*(fetch(n) for n in FEEDS))


async def refresh(event, ctx):
    results = asyncio.run(fetch_all())
    return {"refreshed": [r["feed"] for r in results]}
""",
          "requirements.txt": ""}),
      user="refresh-prices is an async handler that fetches three feeds in parallel with asyncio.gather. Locally it fails with \"asyncio.run() cannot be called from a running event loop\". I'd like to keep the handler async and keep the parallel fetch.",
      steps=[
          S("read_file", path="app/feeds.py"),
          S("invoke_local", function="refresh-prices", type="schedule"),
          S("propose_plan", steps=["Replace `asyncio.run(fetch_all())` with `await fetch_all()` (pskit already runs the event loop for async handlers)",
                                   "Run refresh-prices as a schedule event and validate for alibaba"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/feeds.py", content=FUTURE + """import asyncio

FEEDS = ["fx", "metals", "energy"]


async def fetch(name):
    await asyncio.sleep(0)
    return {"feed": name, "ok": True}


async def fetch_all():
    return await asyncio.gather(*(fetch(n) for n in FEEDS))


async def refresh(event, ctx):
    results = await fetch_all()
    return {"refreshed": [r["feed"] for r in results]}
"""),
          S("invoke_local", function="refresh-prices", type="schedule"),
          S("validate"),
      ],
      final="""For `async def` handlers, pskit runs the coroutine in an event loop for you ("coroutines are awaited" [docs/handlers.md#handler-signatures]). Inside it a loop is already running, so `asyncio.run()` is not allowed. Just `await`:

```python
results = await fetch_all()
```

The handler stays async and `asyncio.gather` still fetches the three feeds in parallel.

- Local schedule run: `{"refreshed": ["fx", "metals", "energy"]}`, no RuntimeWarning.
- `pskit validate` for alibaba (staging): valid."""),

    # ------------------------------------------------------------------ 33  azure http, 405 method mismatch
    B(33, provider="azure", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/troubleshooting.md#http"],
      project=dict(files={
          "pskit.yml": """service: feedback
provider:
  name: azure
  region: uksouth
functions:
  send-feedback:
    handler: app.feedback.send
    events:
      - http: GET /feedback
""",
          "app/__init__.py": "",
          "app/feedback.py": FUTURE + """
def send(event, ctx):
    data = event.http.json()
    ctx.logger.info("feedback", extra={"stars": data.get("stars")})
    return {"received": True}, 201
""",
          "requirements.txt": ""}),
      user="my feedback form do POST to /feedback and get 405 Method Not Allowed, the code is never run. what i miss?",
      steps=[
          S("get_project"),
          S("invoke_local", function="send-feedback", method="POST", path="/feedback", data={"stars": 5}),
          S("search_docs", query="405 method not allowed",
            docs=[D("docs/troubleshooting.md", "http", start="**405 Method Not Allowed**", end="Use `method: ANY`")]),
          S("propose_plan", steps=["Change the route of send-feedback from `GET /feedback` to `POST /feedback`",
                                   "Validate for azure and POST to /feedback locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send-feedback.events.0", value={"http": "POST /feedback"}),
          S("invoke_local", function="send-feedback", method="POST", path="/feedback", data={"stars": 5}),
      ],
      final="""The route was `GET /feedback`, but the form sends POST. The path matched, the method didn't, so pskit answered 405 before your code ran. The `allow` header in the answer said `GET` [docs/troubleshooting.md#http].

Changed in `pskit.yml`:

```yaml
events:
  - http: POST /feedback
```

- `pskit validate` for azure (staging): valid.
- Local POST /feedback with `{"stars": 5}`: status 201, `{"received": true}`.

The code itself was fine."""),

    # ------------------------------------------------------------------ 34  onprem workflow task, wrong input key
    B(34, provider="onprem", stage="dev", mode="auto", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#data-flow"],
      project=dict(files={
          "pskit.yml": """service: fulfil
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8120
functions:
  check-order:
    handler: app.flow.check
  ship-order:
    handler: app.flow.ship
workflows:
  fulfilment:
    start_at: Check
    states:
      Check:
        type: task
        function: check-order
        next: Ship
      Ship:
        type: task
        function: ship-order
        end: true
""",
          "app/__init__.py": "",
          "app/flow.py": FUTURE + """
def check(event, ctx):
    return {"order_id": event.data["order_id"], "valid": True}


def ship(event, ctx):
    order_id = event.data["order"]["id"]
    return {"order_id": order_id, "shipped": True}
""",
          "requirements.txt": ""}),
      user="""fulfilment workflow, Ship step:
KeyError: 'order'
Check returns {"order_id": ..., "valid": true}""",
      steps=[
          S("read_file", path="app/flow.py"),
          S("invoke_local", function="ship-order", type="workflow", data={"order_id": 7, "valid": True}),
          S("search_docs", query="workflow state output next state input",
            docs=[D("docs/workflows.md", "data-flow")]),
          S("propose_plan", steps=["In `ship`, read `event.data[\"order_id\"]`, the key Check returns",
                                   "Invoke ship-order with Check's output, validate for onprem"]),
          S("write_file", path="app/flow.py", content=FUTURE + """
def check(event, ctx):
    return {"order_id": event.data["order_id"], "valid": True}


def ship(event, ctx):
    order_id = event.data["order_id"]
    return {"order_id": order_id, "shipped": True}
"""),
          S("invoke_local", function="ship-order", type="workflow", data={"order_id": 7, "valid": True}),
          S("validate"),
      ],
      final="""Ship gets Check's output as its input (`event.data`), and that output has `order_id` at the top, not `order.id`. Fix in `ship`: `order_id = event.data["order_id"]`.

- invoke ship-order with `{"order_id": 7, "valid": true}`: `{"order_id": 7, "shipped": true}`.
- validate (onprem): valid; the workflow runs on the embedded engine.

Whole flow: `pskit workflow run fulfilment -i '{"order_id": 7}' --history`."""),

    # ------------------------------------------------------------------ 35  tencent http, int(None)
    B(35, provider="tencent", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: feed-api
provider:
  name: tencent
  region: ap-guangzhou
functions:
  feed:
    handler: app.feed.latest
    events:
      - http: GET /feed
""",
          "app/__init__.py": "",
          "app/feed.py": FUTURE + """POSTS = [{"id": i} for i in range(1, 31)]


def latest(event, ctx):
    limit = int(event.http.query.get("limit"))
    return {"posts": POSTS[:min(limit, 3)]}
""",
          "requirements.txt": ""}),
      user="/feed without ?limit -> 500 (int() arg NoneType). default 20",
      steps=[
          S("read_file", path="app/feed.py"),
          S("invoke_local", function="feed", method="GET", path="/feed"),
          S("propose_plan", steps=["Default `limit` to \"20\": `int(event.http.query.get(\"limit\", \"20\"))`",
                                   "Invoke GET /feed, validate for tencent"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/feed.py", content=FUTURE + """POSTS = [{"id": i} for i in range(1, 31)]


def latest(event, ctx):
    limit = int(event.http.query.get("limit", "20"))
    return {"posts": POSTS[:min(limit, 3)]}
"""),
          S("invoke_local", function="feed", method="GET", path="/feed"),
          S("validate"),
      ],
      final="""`query.get("limit")` is `None` when the param is missing, and `int(None)` raises [docs/handlers.md#httprequest]. Now it defaults to `"20"`.

- GET /feed: 200, posts 1-3.
- validate (tencent): valid.

Heads-up: `min(limit, 3)` caps the result at 3 posts whatever `limit` is. If that's a leftover from testing, the default of 20 has no effect yet."""),

    # ------------------------------------------------------------------ 36  aws http, missing header -> 500 instead of 401
    B(36, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#errors", "docs/local-development.md#pskit-invoke-and-pskit-workflow-run"],
      project=dict(files={
          "pskit.yml": """service: reports-api
provider:
  name: aws
  region: eu-north-1
functions:
  monthly:
    handler: app.reports.monthly
    events:
      - http: GET /reports/monthly
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + """
def monthly(event, ctx):
    auth = event.http.headers["authorization"]
    if not auth.startswith("Bearer "):
        return {"error": "bad token"}, 401
    return {"month": "2026-10", "total": 1830}
""",
          "requirements.txt": ""}),
      user="Requests to GET /reports/monthly without an Authorization header return 500 Internal Server Error. They should return 401 Unauthorized, like requests with a malformed token already do. Requests with a valid Bearer token must keep working.",
      steps=[
          S("read_file", path="app/reports.py"),
          S("invoke_local", function="monthly", method="GET", path="/reports/monthly"),
          S("search_docs", query="unauthorized 401 error header",
            docs=[D("docs/handlers.md", "errors", end="| `Forbidden`")]),
          S("propose_plan", steps=["Read the header with `headers.get(\"authorization\", \"\")` and raise `Unauthorized` when it is missing or not a Bearer token",
                                   "Invoke without the header (expect 401) and validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/reports.py", content=FUTURE + """from py_serverless_kit import Unauthorized


def monthly(event, ctx):
    auth = event.http.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise Unauthorized("missing or invalid bearer token")
    return {"month": "2026-10", "total": 1830}
"""),
          S("invoke_local", function="monthly", method="GET", path="/reports/monthly"),
          S("validate"),
      ],
      final="""`headers["authorization"]` raises `KeyError` when the header is absent, and any unexpected exception is a 500. Now the handler uses `.get("authorization", "")` and raises `Unauthorized`, which returns 401 [docs/handlers.md#errors]. Missing and malformed tokens now get the same answer.

- Local GET without the header: status 401, `{"error": "missing or invalid bearer token", "status": 401}`.
- `pskit validate` for aws, prod: valid.

I could not test the valid-token case here, because my local run can't send headers. Run it in a terminal: `pskit invoke -f monthly --path /reports/monthly -H "Authorization: Bearer test"` [docs/local-development.md#pskit-invoke-and-pskit-workflow-run]. That code path is unchanged."""),

    # ------------------------------------------------------------------ 37  gcp storage, fromtimestamp(datetime)
    B(37, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: backups
provider:
  name: gcp
  region: asia-northeast1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  on-backup:
    handler: app.backups.on_backup
    events:
      - storage: nightly-backups
""",
          "app/__init__.py": "",
          "app/backups.py": FUTURE + """from datetime import datetime


def on_backup(event, ctx):
    day = datetime.fromtimestamp(event.time).date().isoformat()
    for record in event.records:
        ctx.logger.info("backup stored", extra={"key": record.key, "day": day})
    return {"day": day, "files": len(event.records)}
""",
          "requirements.txt": ""}),
      user="my backup function says 'datetime.datetime' object cannot be interpreted as an integer. i just want the date of the event",
      steps=[
          S("read_file", path="app/backups.py"),
          S("invoke_local", function="on-backup", type="storage", data={"bucket": "nightly-backups", "key": "db.dump"}),
          S("search_docs", query="event time datetime",
            docs=[D("docs/handlers.md", "event", start="| `data`", end="| `time`")]),
          S("propose_plan", steps=["Use `event.time.date()` directly; it is already a datetime",
                                   "Run on-backup with a storage event and validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/backups.py", content=FUTURE + """
def on_backup(event, ctx):
    day = event.time.date().isoformat()
    for record in event.records:
        ctx.logger.info("backup stored", extra={"key": record.key, "day": day})
    return {"day": day, "files": len(event.records)}
"""),
          S("invoke_local", function="on-backup", type="storage", data={"bucket": "nightly-backups", "key": "db.dump"}),
          S("validate"),
      ],
      final="""`event.time` is already a `datetime` (in UTC) [docs/handlers.md#event]. `datetime.fromtimestamp()` wants a number, so it failed. Just use it:

```python
day = event.time.date().isoformat()
```

- Test with `db.dump`: returned today's date and `"files": 1`.
- `pskit validate` for gcp: valid."""),

    # ------------------------------------------------------------------ 38  digitalocean http, Response.json headers as str
    B(38, provider="digitalocean", stage="prod", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: recipes
provider:
  name: digitalocean
  region: nyc1
  options:
    namespace: ${env:DO_NAMESPACE, fn-recipes}
functions:
  add-recipe:
    handler: app.recipes.add
    events:
      - http: POST /recipes
""",
          "app/__init__.py": "",
          "app/recipes.py": FUTURE + """from py_serverless_kit import Response


def add(event, ctx):
    recipe = event.http.json()
    recipe["id"] = "r-1"
    return Response.json(recipe, 201, "application/json")
""",
          "requirements.txt": ""}),
      user="add-recipe 500 with TypeError 'str' object is not a mapping in Response.json. i only want 201 + json",
      steps=[
          S("read_file", path="app/recipes.py"),
          S("invoke_local", function="add-recipe", method="POST", path="/recipes", data={"title": "pancakes"}),
          S("search_docs", query="Response.json status headers arguments",
            docs=[D("docs/handlers.md", "returning-a-response", start="JSON serialisation handles", end="Response.text(")]),
          S("propose_plan", steps=["Drop the third argument: `Response.json(recipe, status=201)` (headers must be a dict, content-type is set already)",
                                   "Invoke POST /recipes, validate for digitalocean (prod)"]),
          S("write_file", path="app/recipes.py", content=FUTURE + """from py_serverless_kit import Response


def add(event, ctx):
    recipe = event.http.json()
    recipe["id"] = "r-1"
    return Response.json(recipe, status=201)
"""),
          S("invoke_local", function="add-recipe", method="POST", path="/recipes", data={"title": "pancakes"}),
          S("validate"),
      ],
      final="""The third argument of `Response.json` is `headers`, a dict like `{"x-request": "abc"}` [docs/handlers.md#returning-a-response]. You passed the string `"application/json"`, which can't be merged into the headers. `Response.json` sets `content-type: application/json` by itself, so just drop it:

```python
return Response.json(recipe, status=201)
```

- Local POST /recipes: status 201, `content-type: application/json`, body `{"title": "pancakes", "id": "r-1"}`.
- `pskit validate` for digitalocean (prod): valid (doctl warning only)."""),

    # ------------------------------------------------------------------ 39  cloudflare http, json.dumps -> text/plain
    B(39, provider="cloudflare", stage="prod", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: menu
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, demo-account}
functions:
  today:
    handler: app.menu.today
    events:
      - http: GET /menu
""",
          "app/__init__.py": "",
          "app/menu.py": FUTURE + """import json


def today(event, ctx):
    menu = {"soup": "tomato", "main": "risotto"}
    return json.dumps(menu)
""",
          "requirements.txt": ""}),
      user="my website does response.json() on /menu and complains the content type is text/plain, not JSON. but I do json.dumps??",
      steps=[
          S("read_file", path="app/menu.py"),
          S("invoke_local", function="today", method="GET", path="/menu"),
          S("search_docs", query="return dict json content type text plain",
            docs=[D("docs/handlers.md", "returning-a-response", end="| `bytes`")]),
          S("propose_plan", steps=["Return the dict itself instead of `json.dumps(menu)`; pskit sends it as JSON",
                                   "Test GET /menu and validate for cloudflare (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/menu.py", content=FUTURE + """
def today(event, ctx):
    menu = {"soup": "tomato", "main": "risotto"}
    return menu
"""),
          S("invoke_local", function="today", method="GET", path="/menu"),
          S("validate"),
      ],
      final="""`json.dumps()` turns your dict into a **string**, and pskit sends a returned string as `text/plain` [docs/handlers.md#returning-a-response]. Return the dict itself and pskit makes the JSON and sets `application/json`.

- Before: `content-type: text/plain; charset=utf-8`.
- After: GET /menu has status 200, `content-type: application/json`, body `{"soup": "tomato", "main": "risotto"}`.
- `pskit validate` for cloudflare (prod): valid (with the usual Pyodide packages warning)."""),

    # ------------------------------------------------------------------ 40  ibm http, module-level env KeyError
    B(40, provider="ibm", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/local-development.md#environment"],
      project=dict(files={
          "pskit.yml": """service: geo-lookup
provider:
  name: ibm
  region: jp-tok
  runtime: python3.11
functions:
  lookup:
    handler: app.geo.lookup
    events:
      - http: GET /geo
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + """import os

API_BASE = os.environ["API_BASE"]


def lookup(event, ctx):
    ip = event.http.query.get("ip", "203.0.113.5")
    return {"ip": ip, "url": f"{API_BASE}/v1/geo/{ip}"}
""",
          "requirements.txt": ""}),
      user="""KeyError: 'API_BASE'
  File ".\\app\\geo.py", line 5, in <module>
lookup function, every request 500. the variable is a plain URL, https://api.example.com""",
      steps=[
          S("get_project"),
          S("invoke_local", function="lookup", method="GET", path="/geo?ip=203.0.113.5"),
          S("search_docs", query="local environment function environment variables",
            docs=[D("docs/local-development.md", "environment", end="and finally load `.env`")]),
          S("propose_plan", steps=["Add `API_BASE: https://api.example.com` to `functions.lookup.environment` in pskit.yml",
                                   "Validate for ibm (prod) and call GET /geo locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.lookup.environment", value={"API_BASE": "https://api.example.com"}),
          S("invoke_local", function="lookup", method="GET", path="/geo?ip=203.0.113.5"),
      ],
      final="""`app/geo.py` reads `os.environ["API_BASE"]` when the module is imported, and nothing set it. So the import failed and every request returned 500. Local runs add the function's `environment` from pskit.yml [docs/local-development.md#environment], so I put it there:

```yaml
functions:
  lookup:
    environment:
      API_BASE: https://api.example.com
```

- `pskit validate` for ibm, prod: valid.
- Local GET /geo?ip=203.0.113.5: status 200, `url` = `https://api.example.com/v1/geo/203.0.113.5`.

The deployed function gets the same variable on the next deploy."""),
]
