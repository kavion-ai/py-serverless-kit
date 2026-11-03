"""Category B (build / add), batch 31 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 601
    B(601, provider="aws", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/nodejs.md#handlers", "docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: kyc-js
provider:
  name: aws
  region: eu-west-1
  runtime: nodejs20
functions: {}
""",
          "package.json": "{\n  \"name\": \"kyc-js\",\n  \"private\": true\n}\n"}),
      user="Node.js service. Create two JS task functions, `check-document` (adds documentOk: true) and `open-account` (adds accountId), and a Step Functions workflow `onboard` that runs them in order.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write src/kyc.js with exports checkDocument and openAccount (each returns the input plus its field)",
                                   "Add functions check-document and open-account (no triggers)",
                                   "Add workflow onboard: Check (check-document) -> Open (open-account, end)",
                                   "Validate for aws, run check-document with a workflow event"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/kyc.js", content="""exports.checkDocument = async function (event) {
  return { ...(event.data || {}), documentOk: true };
};

exports.openAccount = async function (event) {
  const input = event.data || {};
  return { ...input, accountId: `acc-${input.customer || "new"}` };
};
"""),
          S("set_config", path="functions.check-document", value={"handler": "src.kyc.checkDocument"}),
          S("set_config", path="functions.open-account", value={"handler": "src.kyc.openAccount"}),
          S("set_config", path="workflows.onboard",
            value={"start_at": "Check",
                   "states": {"Check": {"type": "task", "function": "check-document", "next": "Open"},
                              "Open": {"type": "task", "function": "open-account", "end": True}}}),
          S("invoke_local", function="check-document", type="workflow", data={"customer": "c-19"}),
      ],
      final="""Done:

```yaml
functions:
  check-document: {handler: src.kyc.checkDocument}
  open-account:   {handler: src.kyc.openAccount}
workflows:
  onboard:
    start_at: Check
    states:
      Check: {type: task, function: check-document, next: Open}
      Open:  {type: task, function: open-account, end: true}
```

- Workflows are the same for Node.js and Python; each task gets the previous result as `event.data` [docs/workflows.md#state-types] [docs/nodejs.md#handlers].
- `pskit validate` (aws): valid (Step Functions).
- check-document with `{"customer": "c-19"}` → `{"customer": "c-19", "documentOk": true}`.

Run the whole flow: `pskit workflow run onboard -i '{"customer": "c-19"}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 602
    B(602, provider="gcp", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: catalog-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, catalog-api-staging}
functions:
  products:
    handler: app.catalog.products
    events:
    - http:
        path: /products
        method: GET
        auth: iam
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """

def products(event, ctx):
    return {"products": []}
""",
          "requirements.txt": ""}),
      user="""browser shows this on our product page:

  Error: Forbidden
  Your client does not have permission to get URL /products from this server.

the product list is public data, everybody should see it""",
      steps=[
          S("get_project"),
          S("search_docs", query="gcp auth none allUsers iam",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="| http |", end="| http |")]),
          S("propose_plan", steps=["products event: auth iam -> none (adds the allUsers invoker binding)",
                                   "Validate for gcp (staging), invoke GET /products"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.products.events.0", value={"http": "GET /products"}),
          S("invoke_local", function="products", method="GET", path="/products"),
      ],
      final="""Cause: the route had `auth: iam`, so only callers with a Google identity may invoke it; browsers get that Forbidden page. On GCP `auth: none` adds an `allUsers` invoker binding, `auth: iam` doesn't [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Change: `- http: GET /products` (shorthand, auth defaults to `none`).

- `pskit validate` (gcp, staging): valid.
- invoke GET /products: 200 `{"products": []}`.

The fix takes effect on the next **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 603
    B(603, provider="azure", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: invoicing
provider:
  name: azure
  region: westeurope
functions:
  issue:
    handler: app.invoices.issue
    events:
    - queue: invoice-jobs
""",
          "app/__init__.py": "",
          "app/invoices.py": FUTURE + """

def issue(event, ctx):
    return {"issued": len(event.records)}
""",
          "requirements.txt": ""}),
      user="On AWS, failed invoice jobs went to a DLQ and a Lambda alerted us. On Azure, where do failed messages of invoice-jobs go, and can a function `failed-invoices` log each one?",
      steps=[
          S("get_project"),
          S("search_docs", query="azure poison queue dead letter",
            docs=[D("docs/events.md", "queue", start="| Option |", end="| `fifo` |")]),
          S("propose_plan", steps=["Write app/failed.py: log each poisoned message",
                                   "Add function failed-invoices on queue invoice-jobs-poison (the queue Azure moves failed messages to)",
                                   "Validate for azure (prod), invoke with one message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/failed.py", content=FUTURE + """

def failed(event, ctx):
    for record in event.records:
        ctx.logger.error("invoice job failed", extra={"id": record.id, "body": record.text()[:500]})
    # TODO: send the alert (mail / chat)
    return {"failed": len(event.records)}
"""),
          S("set_config", path="functions.failed-invoices",
            value={"handler": "app.failed.failed", "events": [{"queue": "invoice-jobs-poison"}]}),
          S("invoke_local", function="failed-invoices", type="queue", data=[{"invoice": "INV-77"}]),
      ],
      final="""On Azure there is no `dead_letter` setting: messages that keep failing go to the poison queue `<queue>-poison`, here `invoice-jobs-poison` [docs/events.md#queue].

Added `failed-invoices` on that queue:

```yaml
functions:
  failed-invoices:
    handler: app.failed.failed
    events:
      - queue: invoice-jobs-poison
```

- It logs each failed job at ERROR level (alerting is a TODO).
- `pskit validate` (azure, prod): valid.
- invoke with one message: an `invoice job failed` log, `{"failed": 1}`.

pskit now creates `invoice-jobs-poison` as a Storage Queue. If it already exists in the storage account from earlier failures, add `existing: true` to this queue event so pskit doesn't try to create it. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 604
    B(604, provider="aws", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/configuration.md#precedence-later-wins"],
      project=dict(files={
          "pskit.yml": """service: kpi
provider:
  name: aws
  region: eu-west-1
functions:
  kpi-report:
    handler: app.kpi.report
    events:
    - http: POST /kpi/report
""",
          "app/__init__.py": "",
          "app/kpi.py": FUTURE + """

def report(event, ctx):
    return {"report": "ok", "trigger": event.type}
""",
          "requirements.txt": ""}),
      user="`kpi-report` can be started by hand with POST /kpi/report in every stage. In prod only, it should also run automatically at 06:00 UTC every day. Dev and staging stay manual.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["stages.prod.functions.kpi-report.events = [http POST /kpi/report, schedule \"0 6 * * *\"] (lists replace, so the http event is repeated)",
                                   "Validate for aws (prod), invoke the schedule"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages",
            value={"prod": {"functions": {"kpi-report": {"events": [{"http": "POST /kpi/report"}, {"schedule": "0 6 * * *"}]}}}}),
          S("invoke_local", function="kpi-report", type="schedule"),
      ],
      final="""```yaml
stages:
  prod:
    functions:
      kpi-report:
        events:
          - http: POST /kpi/report
          - schedule: "0 6 * * *"
```

- Lists are replaced, not appended, so the prod list repeats the HTTP route [docs/configuration.md#precedence-later-wins]; dev and staging keep only the route.
- `pskit validate` (aws, prod): valid.
- Scheduled run in prod: `{"report": "ok", "trigger": "schedule"}`.

Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 605
    B(605, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: pub-quiz
provider:
  name: gcp
  region: europe-west2
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, pub-quiz-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="new project for our pub quiz: one address gives a random question, and another where you send your answer and it says right or wrong",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/quiz.py with a few questions, question() and answer()",
                                   "Add function question on GET /question and answer on POST /answer ({id, answer})",
                                   "Validate for gcp, try a right answer locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/quiz.py", content=FUTURE + """import random

from py_serverless_kit import BadRequest, NotFound

QUESTIONS = {
    "1": ("What is the capital of Australia?", "canberra"),
    "2": ("How many legs does a spider have?", "8"),
    "3": ("Which planet is known as the red planet?", "mars"),
}


def question(event, ctx):
    qid = random.choice(list(QUESTIONS))
    return {"id": qid, "question": QUESTIONS[qid][0]}


def answer(event, ctx):
    body = event.http.json(default={}) or {}
    qid = str(body.get("id", ""))
    if qid not in QUESTIONS:
        raise NotFound("unknown question id")
    given = str(body.get("answer", "")).strip().lower()
    if not given:
        raise BadRequest("answer is empty")
    return {"correct": given == QUESTIONS[qid][1]}
"""),
          S("set_config", path="functions.question", value={"handler": "app.quiz.question", "events": [{"http": "GET /question"}]}),
          S("set_config", path="functions.answer", value={"handler": "app.quiz.answer", "events": [{"http": "POST /answer"}]}),
          S("invoke_local", function="answer", method="POST", path="/answer", data={"id": 3, "answer": "Mars"}),
      ],
      final="""Your quiz project is ready:

- `GET /question` → a random question with its `id`.
- `POST /answer` with `{"id": 3, "answer": "Mars"}` → `{"correct": true}`. Unknown id → 404, empty answer → 400. Capital letters don't matter.

Checks: `pskit validate` (gcp) valid; the Mars answer gave `{"correct": true}`.

Add more questions in `QUESTIONS` in app/quiz.py. Try it on **Test** > **▶ Run locally**, then **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 606
    B(606, provider="azure", stage="dev", mode="ask", page="Overview", persona="terse_expert",
      sources=["docs/configuration.md#providers-per-cloud-overrides", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: aws
  region: eu-west-1
functions:
  cart:
    handler: app.shop.cart
    memory: 512
    events:
    - http: GET /cart
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + """

def cart(event, ctx):
    return {"items": []}
""",
          "requirements.txt": ""}),
      user="make this deployable to azure too: westeurope, existing rg-shop-dev, subscription from ARM_SUBSCRIPTION_ID. aws stays default",
      steps=[
          S("get_project"),
          S("search_docs", query="providers per-cloud overrides",
            docs=[D("docs/configuration.md", "providers-per-cloud-overrides", end="may be written directly")]),
          S("propose_plan", steps=["providers.azure = {region: westeurope, options: {resource_group: rg-shop-dev, subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}}}",
                                   "Validate with -p azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers",
            value={"azure": {"region": "westeurope",
                             "options": {"resource_group": "rg-shop-dev",
                                         "subscription_id": "${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}"}}}),
          S("validate", provider="azure"),
      ],
      final="""```yaml
providers:
  azure:
    region: westeurope
    options:
      resource_group: rg-shop-dev
      subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
```

- The block is merged only when the target is azure; AWS stays the default [docs/configuration.md#providers-per-cloud-overrides].
- validate `-p azure`: valid.
- `cart`'s `memory: 512` isn't applied on Azure (the Consumption Function App has no per-function memory size).

The zero UUID is only a placeholder; set `ARM_SUBSCRIPTION_ID` before deploying. Deploy: pick azure in the top bar, then **Deploy**, or `pskit deploy -p azure -s dev`."""),

    # ------------------------------------------------------------------ 607
    B(607, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: payments-core
provider:
  name: aws
  region: eu-west-1
functions:
  settle:
    handler: app.settle.settle
    events:
    - schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/settle.py": FUTURE + """

def settle(event, ctx):
    return {"settled": 0}
""",
          "requirements.txt": ""}),
      user="Our security team doesn't allow deployments to create IAM roles in prod. They created arn:aws:iam::123456789012:role/payments-core-lambda for us. Use that role in prod; dev may keep the generated one.",
      steps=[
          S("get_project"),
          S("search_docs", query="iam role existing", docs=[D("docs/configuration.md", "provider", start="| `iam.role` |", end="| `iam.role` |")]),
          S("propose_plan", steps=["stages.prod.provider.iam.role = arn:aws:iam::123456789012:role/payments-core-lambda",
                                   "Validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages",
            value={"prod": {"provider": {"iam": {"role": "arn:aws:iam::123456789012:role/payments-core-lambda"}}}}),
      ],
      final="""```yaml
stages:
  prod:
    provider:
      iam:
        role: arn:aws:iam::123456789012:role/payments-core-lambda
```

- `iam.role` uses an existing role instead of creating one [docs/configuration.md#provider]; only prod gets it, dev keeps the generated role.
- `pskit validate` (aws, prod): valid.

The security team's role must already allow everything the functions need (at least writing CloudWatch Logs) and trust `lambda.amazonaws.com`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 608
    B(608, provider="gcp", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: legal-docs
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, legal-docs-prod}
functions: {}
""",
          "requirements.txt": ""}),
      user="audit fn for deletions in existing gcs bucket legal-signed-0007, log key + time",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/audit.py: log record.key and event.time for each deleted object",
                                   "functions.audit-deletes: storage {bucket: legal-signed-0007, existing: true, events: [deleted]}",
                                   "Validate gcp prod, invoke"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/audit.py", content=FUTURE + """

def audit_deletes(event, ctx):
    keys = [r.key for r in event.records if r.action == "deleted"]
    for key in keys:
        ctx.logger.warning("object deleted", extra={"key": key, "time": str(event.time)})
    return {"deleted": keys}
"""),
          S("set_config", path="functions.audit-deletes",
            value={"handler": "app.audit.audit_deletes",
                   "events": [{"storage": {"bucket": "legal-signed-0007", "existing": True, "events": ["deleted"]}}]}),
          S("invoke_local", function="audit-deletes", type="storage",
            data={"bucket": "legal-signed-0007", "key": "2026/contract-9.pdf", "action": "deleted"}),
      ],
      final="""```yaml
functions:
  audit-deletes:
    handler: app.audit.audit_deletes
    events:
      - storage: {bucket: legal-signed-0007, existing: true, events: [deleted]}
```

- GCP: Eventarc `deleted` trigger on the existing bucket; pskit doesn't create or delete it [docs/events.md#storage].
- validate (gcp, prod): valid. invoke: WARNING `object deleted`, `{"deleted": ["2026/contract-9.pdf"]}`.

Deploy: `pskit deploy -s prod` (typed confirmation in studio)."""),

    # ------------------------------------------------------------------ 609
    B(609, provider="azure", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: parking
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="new project parking: driver send plate + minutes to start parking, other address check plate is ok or not, and every 15 min clean up expired ones",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/parking.py: start (POST /parking), check (GET /parking/{plate}), cleanup (schedule 15 minutes)",
                                   "Plate and minutes required (1-600), else 400; in-memory store for the first version",
                                   "Validate for azure, start and check one plate locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/parking.py", content=FUTURE + """import time

from py_serverless_kit import BadRequest

_SESSIONS = {}  # plate -> end time; first version only, not shared between instances


def start(event, ctx):
    body = event.http.json(default={}) or {}
    plate = str(body.get("plate", "")).upper().replace(" ", "")
    minutes = body.get("minutes")
    if not plate or not isinstance(minutes, int) or not 1 <= minutes <= 600:
        raise BadRequest("plate and minutes (1-600) are required")
    _SESSIONS[plate] = time.time() + minutes * 60
    return {"plate": plate, "minutes": minutes}, 201


def check(event, ctx):
    plate = event.http.path_params["plate"].upper()
    return {"plate": plate, "valid": _SESSIONS.get(plate, 0) > time.time()}


def cleanup(event, ctx):
    now = time.time()
    expired = [p for p, end in _SESSIONS.items() if end <= now]
    for p in expired:
        del _SESSIONS[p]
    return {"removed": len(expired)}
"""),
          S("set_config", path="functions.start-parking", value={"handler": "app.parking.start", "events": [{"http": "POST /parking"}]}),
          S("set_config", path="functions.check-parking", value={"handler": "app.parking.check", "events": [{"http": "GET /parking/{plate}"}]}),
          S("set_config", path="functions.cleanup", value={"handler": "app.parking.cleanup", "events": [{"schedule": "15 minutes"}]}),
          S("invoke_local", function="start-parking", method="POST", path="/parking", data={"plate": "ab 123", "minutes": 30}),
          S("invoke_local", function="check-parking", method="GET", path="/parking/AB123"),
      ],
      final="""Your parking project has three functions:

| Function | Trigger |
|---|---|
| `start-parking` | `POST /parking` with `{"plate", "minutes"}` → 201 |
| `check-parking` | `GET /parking/{plate}` → valid true/false |
| `cleanup` | every 15 minutes |

Checks: `pskit validate` (azure) valid; start `ab 123` for 30 min → **201** (plate stored as `AB123`); check `AB123` → 200 `valid: false`, because each local run starts with empty memory.

That last result shows the limit of this first version: sessions only live in one instance's memory. Before real use, save them in a table (for example Azure Table Storage). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 610
    B(610, provider="aws", stage="staging", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: bookings
provider:
  name: aws
  region: eu-west-1
functions:
  book:
    handler: app.book.book
    events:
    - http: POST /bookings
""",
          "app/__init__.py": "",
          "app/book.py": FUTURE + """

def book(event, ctx):
    return {"table": ctx.env.get("TABLE_NAME")}, 201
""",
          "requirements.txt": ""}),
      user="The DynamoDB table is named `<service>-<stage>-bookings` and created by another stack. Define the name once in custom, pass it as TABLE_NAME, and give `book` dynamodb:PutItem and GetItem on exactly that table.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["custom.table = ${self:service}-${opt:stage}-bookings",
                                   "book.environment.TABLE_NAME = ${self:custom.table}",
                                   "book.iam.statements: PutItem/GetItem on arn:aws:dynamodb:eu-west-1:*:table/${self:custom.table}",
                                   "Validate for aws (staging), invoke"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="custom", value={"table": "${self:service}-${opt:stage}-bookings"}),
          S("set_config", path="functions.book.environment", value={"TABLE_NAME": "${self:custom.table}"}),
          S("set_config", path="functions.book.iam",
            value={"statements": [{"actions": ["dynamodb:PutItem", "dynamodb:GetItem"],
                                   "resources": ["arn:aws:dynamodb:eu-west-1:*:table/${self:custom.table}"]}]}),
          S("invoke_local", function="book", method="POST", path="/bookings", data={"room": 4}),
      ],
      final="""```yaml
custom:
  table: ${self:service}-${opt:stage}-bookings
functions:
  book:
    environment:
      TABLE_NAME: ${self:custom.table}
    iam:
      statements:
        - actions: [dynamodb:PutItem, dynamodb:GetItem]
          resources: ["arn:aws:dynamodb:eu-west-1:*:table/${self:custom.table}"]
```

- `${self:...}` / `${opt:stage}` resolve before deploy, so the name is written once [docs/configuration.md#variables]; function-level statements apply to `book`'s own role.
- `pskit validate` (aws, staging): valid after each change.
- invoke: 201 `{"table": "bookings-staging-bookings"}`.

Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 611
    B(611, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: stock-watch
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, stock-watch-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="I don't need a website at all. I just want some code to run every 10 minutes and check if any product is low on stock. Is that possible?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/stock.py: check() compares a small product list with a minimum and logs low items",
                                   "Add function check-stock with schedule 10 minutes (no web address)",
                                   "Validate for gcp and run it once locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/stock.py", content=FUTURE + """MINIMUM = 5
# TODO: read real stock levels from your shop system
STOCK = {"blue mug": 12, "red mug": 3, "teapot": 0}


def check(event, ctx):
    low = sorted(name for name, qty in STOCK.items() if qty < MINIMUM)
    if low:
        ctx.logger.warning("low stock", extra={"products": low})
    return {"low": low}
"""),
          S("set_config", path="functions.check-stock", value={"handler": "app.stock.check", "events": [{"schedule": "10 minutes"}]}),
          S("invoke_local", function="check-stock", type="schedule"),
      ],
      final="""Yes. A function doesn't need a web address; this one only has a timer:

```yaml
functions:
  check-stock:
    handler: app.stock.check
    events:
      - schedule: 10 minutes
```

On GCP, Cloud Scheduler runs it every 10 minutes (pskit turns `10 minutes` into cron for you) [docs/events.md#schedule].

Checks: `pskit validate` (gcp) valid; one local run → `{"low": ["red mug", "teapot"]}` with a `low stock` warning.

Replace the example `STOCK` list with your real data later. Deploy with **Deploy** or `pskit deploy -s dev`; the warnings show up on the **Logs** page."""),

    # ------------------------------------------------------------------ 612
    B(612, provider="azure", stage="staging", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: class-files
provider:
  name: azure
  region: westeurope
functions:
  files:
    handler: app.files.files
    events:
    - http: GET /files
""",
          "app/__init__.py": "",
          "app/files.py": FUTURE + """

def files(event, ctx):
    return {"files": ["notes.txt", "homework.txt"]}
""",
          "requirements.txt": ""}),
      user="Instead of the list, can /files give the students one .zip download with notes.txt and homework.txt inside? The texts can be simple for now.",
      steps=[
          S("get_project"),
          S("search_docs", query="binary file download response",
            docs=[D("docs/handlers.md", "returning-a-response", start="```python", end="Response.binary")]),
          S("propose_plan", steps=["Build the zip in memory with zipfile and return Response.binary(..., \"application/zip\")",
                                   "Add content-disposition so the browser saves it as class-files.zip",
                                   "Validate for azure (staging), call GET /files locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/files.py", content=FUTURE + """import io
import zipfile

from py_serverless_kit import Response

FILES = {
    "notes.txt": "Lesson 1: fractions\\n",
    "homework.txt": "Exercises 1 to 5, page 12\\n",
}


def files(event, ctx):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in FILES.items():
            zf.writestr(name, text)
    resp = Response.binary(buf.getvalue(), "application/zip")
    resp.headers["content-disposition"] = 'attachment; filename="class-files.zip"'
    return resp
"""),
          S("validate"),
          S("invoke_local", function="files", method="GET", path="/files"),
      ],
      final="""Yes. `GET /files` now sends one zip file, `class-files.zip`, with `notes.txt` and `homework.txt` inside.

- The zip is built in memory and returned with `Response.binary(..., "application/zip")` [docs/handlers.md#returning-a-response]; `content-disposition: attachment` makes the browser download it.
- `pskit validate` (azure, staging): valid.
- Local test: 200, `application/zip` (the body is shown base64-encoded in the test output).

Change the texts in `FILES` in app/files.py. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 613
    B(613, provider="aws", stage="dev", mode="ask", page="Code", persona="pasted_error",
      sources=["docs/configuration.md#package", "docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: price-check
provider:
  name: aws
  region: eu-west-1
functions:
  check:
    handler: app.check.check
    events:
    - schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/check.py": FUTURE + """import requests


def check(event, ctx):
    return {"requests": requests.__version__}
""",
          "requirements.txt": ""}),
      user="""from CloudWatch after deploy:

[ERROR] Runtime.ImportModuleError: Unable to import module 'pskit_entry': No module named 'requests'

works on my laptop!""",
      steps=[
          S("get_project"),
          S("read_file", path="requirements.txt"),
          S("propose_plan", steps=["Add requests to requirements.txt (it's only installed on your laptop, not listed)",
                                   "Validate for aws, invoke locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="requirements.txt", content="requests>=2.31\n"),
          S("validate"),
          S("invoke_local", function="check", type="schedule"),
      ],
      final="""Cause: `requirements.txt` was empty. `requests` exists in your laptop's .venv, so local runs work, but pskit only installs what requirements.txt lists into the Lambda zip [docs/configuration.md#package] [docs/providers.md#aws-aws-lambda].

Change: requirements.txt now has `requests>=2.31`.

- `pskit validate` (aws): valid.
- Local run: `{"requests": "2.34.2"}`.

Deploy again with **Deploy** or `pskit deploy -s dev` (without `--skip-deps`, so the dependencies are installed)."""),

    # ------------------------------------------------------------------ 614
    B(614, provider="gcp", stage="staging", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: profile-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, profile-api-staging}
functions:
  profile:
    handler: app.profile.handler
    events:
    - http: GET /profile/{user}
""",
          "app/__init__.py": "",
          "app/profile.py": FUTURE + """import json


def handler(event, context):
    user = event["pathParameters"]["user"]
    if user == "ghost":
        return {"statusCode": 404, "body": json.dumps({"error": "not found"})}
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps({"user": user}),
    }
""",
          "requirements.txt": ""}),
      user="This is our Lambda proxy-integration code (statusCode/body with json.dumps, event['pathParameters']). It breaks on GCP. Rewrite it the pskit way, same behaviour.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Read the path parameter from event.http.path_params",
                                   "Return the dict (JSON 200) with the no-store header via a (body, status, headers) tuple; raise NotFound for ghost",
                                   "Validate for gcp (staging), invoke a user and ghost"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/profile.py", content=FUTURE + """from py_serverless_kit import NotFound


def handler(event, ctx):
    user = event.http.path_params["user"]
    if user == "ghost":
        raise NotFound("not found")
    return {"user": user}, 200, {"cache-control": "no-store"}
"""),
          S("validate"),
          S("invoke_local", function="profile", method="GET", path="/profile/ana"),
          S("invoke_local", function="profile", method="GET", path="/profile/ghost"),
      ],
      final="""Rewritten without any API Gateway shapes [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing]:

| Lambda | pskit |
|---|---|
| `event["pathParameters"]["user"]` | `event.http.path_params["user"]` |
| `{"statusCode": 200, "body": json.dumps(...)}` | return the dict (JSON), or `(body, status, headers)` [docs/handlers.md#returning-a-response] |
| `statusCode: 404` | `raise NotFound(...)` |

- `pskit validate` (gcp, staging): valid.
- invoke: `/profile/ana` → 200 `{"user": "ana"}` with `cache-control: no-store`; `/profile/ghost` → 404 `not found`.

The same file now runs on AWS too. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 615
    B(615, provider="azure", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#package", "docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: tidy
provider:
  name: azure
  region: westeurope
functions:
  api:
    handler: src.app.api.handler
    events:
    - http: GET /tidy
""",
          "src/app/__init__.py": "",
          "src/app/api.py": FUTURE + """

def handler(event, ctx):
    return {"ok": True}
""",
          "README.md": "# tidy\n",
          "requirements.txt": ""}),
      user="code lives in src/. bundle only src (package.source), handler app.api.handler",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["package.source = src", "functions.api.handler = app.api.handler (relative to source)", "Validate azure, invoke"]),
          S("set_config", path="package", value={"source": "src"}),
          S("set_config", path="functions.api.handler", value="app.api.handler"),
          S("invoke_local", function="api", method="GET", path="/tidy"),
      ],
      final="""```yaml
package:
  source: src
functions:
  api:
    handler: app.api.handler
```

- Only `src/` is bundled now (README, tests etc. stay out) [docs/configuration.md#package]; handlers are resolved relative to `package.source`.
- validate (azure): valid. invoke GET /tidy: 200 `{"ok": true}`.

Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 616
    B(616, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: menu-js
provider:
  name: aws
  region: eu-south-1
  runtime: nodejs20
functions: {}
""",
          "package.json": "{\n  \"name\": \"menu-js\",\n  \"private\": true\n}\n"}),
      user="in js: GET /dishes give list of dishes, my vue site on https://trattoria.example.com call it from browser so need cors",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write src/dishes.js: export list with three dishes",
                                   "Add function dishes on GET /dishes with cors {origins: [https://trattoria.example.com]}",
                                   "Validate for aws, invoke GET /dishes"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/dishes.js", content="""const DISHES = [
  { name: "Margherita", price: 8.5 },
  { name: "Carbonara", price: 11 },
  { name: "Tiramisu", price: 5 },
];

exports.list = async function () {
  return { dishes: DISHES };
};
"""),
          S("set_config", path="functions.dishes",
            value={"handler": "src.dishes.list",
                   "events": [{"http": {"path": "/dishes", "method": "GET", "cors": {"origins": ["https://trattoria.example.com"]}}}]}),
          S("invoke_local", function="dishes", method="GET", path="/dishes"),
      ],
      final="""Done:

```yaml
functions:
  dishes:
    handler: src.dishes.list
    events:
      - http:
          path: /dishes
          method: GET
          cors: {origins: ["https://trattoria.example.com"]}
```

- On AWS the CORS rules are set on the API Gateway HTTP API, so only your Vue site's origin may call it from the browser [docs/events.md#http].
- `pskit validate` (aws): valid.
- invoke GET /dishes: 200 with the three dishes.

Deploy: **Deploy** or `pskit deploy -s dev`; `pskit info` shows the URL for your Vue `fetch()`."""),

    # ------------------------------------------------------------------ 617
    B(617, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic", "docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: fleet
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, fleet-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="Add `on-breakdown` on the Pub/Sub topic `vehicle-events`. Only messages whose attribute `kind` is `breakdown` matter; others should be ignored. I know topic filters aren't applied on GCP, so filter in code.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/fleet.py: skip records whose kind (attribute, or body field as fallback) isn't breakdown, log the vehicle for the rest",
                                   "Add function on-breakdown with topic vehicle-events (no filter key)",
                                   "Validate for gcp, invoke one breakdown message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/fleet.py", content=FUTURE + """

def on_breakdown(event, ctx):
    handled = []
    for record in event.records:
        body = record.json(default={}) or {}
        kind = (record.attributes or {}).get("kind") or body.get("kind")
        if kind != "breakdown":
            continue
        vehicle = body.get("vehicle")
        ctx.logger.warning("breakdown", extra={"vehicle": vehicle})
        handled.append(vehicle)
    return {"breakdowns": handled}
"""),
          S("set_config", path="functions.on-breakdown",
            value={"handler": "app.fleet.on_breakdown", "events": [{"topic": "vehicle-events"}]}),
          S("invoke_local", function="on-breakdown", type="topic",
            data=[{"vehicle": "VAN-12", "kind": "breakdown"}, {"vehicle": "CAR-3", "kind": "refuel"}]),
      ],
      final="""Added `on-breakdown` on `vehicle-events`, filtering in the handler:

- The handler reads `kind` from the message attributes (`record.attributes` [docs/handlers.md#record]), falling back to a `kind` field in the body; anything that isn't `breakdown` is skipped, breakdowns are logged as warnings.
- No `filter` in pskit.yml, since GCP wouldn't apply it anyway [docs/events.md#topic]. The function still runs (and is billed) for every message on the topic.
- `pskit validate` (gcp): valid.
- invoke with a breakdown and a refuel message: one `breakdown` warning, `{"breakdowns": ["VAN-12"]}`. Local test records carry no attributes, so this used the body fallback; publish with the `kind` attribute in the cloud.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 618
    B(618, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/studio.md#what-you-can-do"],
      project=dict(files={
          "pskit.yml": """service: club-site
provider:
  name: azure
  region: westeurope
functions:
  home:
    handler: app.site.home
    events:
    - http: GET /
  old-report:
    handler: app.site.old_report
    events:
    - schedule: 0 5 * * *
""",
          "app/__init__.py": "",
          "app/site.py": FUTURE + """

def home(event, ctx):
    return "Welcome to the club"


def old_report(event, ctx):
    return {"report": "old"}
""",
          "requirements.txt": ""}),
      user="I don't need the old-report thing anymore. Can you remove it?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Delete functions.old-report from pskit.yml",
                                   "Remove the old_report handler from app/site.py",
                                   "Validate for azure, check that home still works"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/site.py", content=FUTURE + """

def home(event, ctx):
    return "Welcome to the club"
"""),
          S("set_config", path="functions.old-report", value=None),
          S("invoke_local", function="home", method="GET", path="/"),
      ],
      final="""Removed. `old-report` is gone from pskit.yml, and its code is gone from app/site.py.

- `pskit validate` (azure): valid, 1 function left.
- `home` still answers 200 `Welcome to the club`.

It still runs in Azure until your next deploy: **Deploy** or `pskit deploy -s dev` removes its timer from the Function App. (Next time, the row button **Delete** on the **Functions** page does the YAML part for you.)"""),

    # ------------------------------------------------------------------ 619
    B(619, provider="aws", stage="staging", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": """service: reco
provider:
  name: aws
  region: eu-west-1
functions:
  recommend:
    handler: app.reco.recommend
    events:
    - http: GET /recommend
""",
          "app/__init__.py": "",
          "app/reco.py": FUTURE + """

def recommend(event, ctx):
    return {"items": []}
""",
          "scripts/train.py": FUTURE + "print('training')\n",
          "docs/design.md": "# design\n",
          "requirements.txt": ""}),
      user="whitelist the bundle: only app/** and requirements.txt",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["package.include = [\"app/**\", \"requirements.txt\"]", "Validate aws staging, invoke"]),
          S("set_config", path="package", value={"include": ["app/**", "requirements.txt"]}),
          S("invoke_local", function="recommend", method="GET", path="/recommend"),
      ],
      final="""```yaml
package:
  include: ["app/**", "requirements.txt"]
```

`include` replaces the default `["**/*"]`; the built-in excludes still apply [docs/configuration.md#package]. So `scripts/` and `docs/` stay out of the zip.

validate (aws, staging): valid. invoke GET /recommend: 200 `{"items": []}`. Check the bundle with `pskit package --skip-deps`, then `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 620
    B(620, provider="gcp", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: maps-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: maps-api-dev
functions:
  tiles:
    handler: app.maps.tiles
    events:
    - http: GET /tiles/{z}/{x}/{y}
""",
          "app/__init__.py": "",
          "app/maps.py": FUTURE + """

def tiles(event, ctx):
    return {"tile": event.http.path_params}
""",
          "requirements.txt": ""}),
      user="Prod lives in a separate GCP project `maps-api-prod-41` and must run as tiles-runtime@maps-api-prod-41.iam.gserviceaccount.com. Dev and staging keep maps-api-dev with the default service account.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["stages.prod.provider.options = {project: maps-api-prod-41, service_account: tiles-runtime@maps-api-prod-41.iam.gserviceaccount.com}",
                                   "Validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages",
            value={"prod": {"provider": {"options": {"project": "maps-api-prod-41",
                                                     "service_account": "tiles-runtime@maps-api-prod-41.iam.gserviceaccount.com"}}}}),
      ],
      final="""```yaml
stages:
  prod:
    provider:
      options:
        project: maps-api-prod-41
        service_account: tiles-runtime@maps-api-prod-41.iam.gserviceaccount.com
```

- `stages.prod` is deep-merged only for `-s prod`, so dev and staging keep `maps-api-dev` and the default identity [docs/configuration.md#stages-per-stage-overrides].
- `service_account` is the optional runtime identity on GCP [docs/providers.md#gcp-google-cloud-functions-2nd-gen]; grant it the roles tiles needs, since `iam.statements` are ignored on GCP.
- `pskit validate` (gcp, prod): valid.

Your gcloud credentials need deploy rights in maps-api-prod-41. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),
]
