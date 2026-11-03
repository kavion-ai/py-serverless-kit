"""Category B (build / add), batch 22 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 421
    B(421, provider="aws", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: order-lookup
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="make GET /orders/{id} it return the order, if id not exist give 404. use some fake orders for now",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/orders.py` with a small fake ORDERS dict; NotFound when the id is unknown",
                                   "Add function `get-order` on GET /orders/{id}",
                                   "Validate for aws, invoke with a known and an unknown id"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/orders.py", content=FUTURE + """from py_serverless_kit import NotFound

ORDERS = {
    "1001": {"id": "1001", "item": "keyboard", "status": "shipped"},
    "1002": {"id": "1002", "item": "mouse", "status": "packing"},
}


def get_order(event, ctx):
    order_id = event.http.path_params["id"]
    order = ORDERS.get(order_id)
    if order is None:
        raise NotFound(f"order {order_id} not found")
    return order
"""),
          S("set_config", path="functions.get-order",
            value={"handler": "app.orders.get_order", "events": [{"http": "GET /orders/{id}"}]}),
          S("invoke_local", function="get-order", method="GET", path="/orders/1001"),
          S("invoke_local", function="get-order", method="GET", path="/orders/9999"),
      ],
      final="""Done. `get-order` is on `GET /orders/{id}`, and `{id}` arrives in `event.http.path_params["id"]` [docs/events.md#http].

- validate (aws): valid.
- `/orders/1001`: 200 with the keyboard order.
- `/orders/9999`: **404** `order 9999 not found` (from `NotFound`) [docs/handlers.md#errors].

Replace the `ORDERS` dict with your database later. Retest: `pskit invoke -f get-order --method GET --path /orders/1002`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 422
    B(422, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=dict(files={
          "pskit.yml": """service: tickets
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, tickets-staging}
functions:
  intake:
    handler: app.tickets.intake
    events:
    - http: POST /tickets
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """

def intake(event, ctx):
    ticket = event.http.json(default={}) or {}
    return {"accepted": ticket.get("title")}, 201
""",
          "requirements.txt": ""}),
      user="`intake` should also consume the queue `ticket-imports` (bulk imports from our old helpdesk) with the same code. HTTP returns 201 with the title; the queue path should return the list of imported titles.",
      steps=[
          S("get_project"),
          S("search_docs", query="gcp function http and queue trigger split",
            docs=[D("docs/events.md", "gcp-multi-trigger-functions-are-split-automatically")]),
          S("propose_plan", steps=["Add `- queue: ticket-imports` to `intake`",
                                   "Handler: branch on event.type (http -> 201, queue -> titles)",
                                   "Validate for gcp (staging), invoke both ways"],
            result={"decision": "approved", "note": "also log how many tickets each queue delivery had"}),
          S("set_config", path="functions.intake.events",
            value=[{"http": "POST /tickets"}, {"queue": "ticket-imports"}]),
          S("write_file", path="app/tickets.py", content=FUTURE + """

def intake(event, ctx):
    if event.type == "queue":
        titles = [(r.json(default={}) or {}).get("title") for r in event.records]
        ctx.logger.info("ticket import", extra={"count": len(titles)})
        return {"imported": titles}
    ticket = event.http.json(default={}) or {}
    return {"accepted": ticket.get("title")}, 201
"""),
          S("validate"),
          S("invoke_local", function="intake", method="POST", path="/tickets", data={"title": "printer broken"}),
          S("invoke_local", function="intake", type="queue", data=[{"title": "old-1"}, {"title": "old-2"}]),
      ],
      final="""`intake` now has both triggers and logs the count per delivery, as you asked:

```yaml
functions:
  intake:
    handler: app.tickets.intake
    events:
      - http: POST /tickets
      - queue: ticket-imports
```

- A Cloud Function can't mix HTTP and events, so pskit deploys `intake` (HTTP) plus `intake-queue0` (Pub/Sub), sharing the same code. `pskit info` still shows one function [docs/events.md#gcp-multi-trigger-functions-are-split-automatically].
- validate (gcp, staging): valid.
- HTTP: 201 `{"accepted": "printer broken"}`. Queue: `{"imported": ["old-1", "old-2"]}` with a `ticket import` log line, count 2.

The queue deployment is limited to 540 s timeout. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 423
    B(423, provider="azure", stage="prod", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#compiler-notes-and-limits"],
      project=dict(files={
          "pskit.yml": """service: archive-jobs
provider:
  name: azure
  region: westeurope
functions:
  collect:
    handler: app.archive.collect
  compress:
    handler: app.archive.compress
""",
          "app/__init__.py": "",
          "app/archive.py": FUTURE + """

def collect(event, ctx):
    job = dict(event.data or {})
    return {**job, "files": 120}


def compress(event, ctx):
    return {**(event.data or {}), "archive": "done"}
""",
          "requirements.txt": ""}),
      user="On AWS we started this with StartExecution and didn't wait for the result, the job can take 10+ minutes. On Azure I want it as a real Logic App: Collect then Compress, and the caller should get an immediate response, not wait.",
      steps=[
          S("get_project"),
          S("search_docs", query="azure logic app sync false long workflow",
            docs=[D("docs/workflows.md", "workflow-keys", start="| `options.sync`", end="| `options.sync`"),
                  D("docs/workflows.md", "compiler-notes-and-limits", start="- **Azure (Logic Apps):**", words=120)]),
          S("propose_plan", steps=["Add workflow `archive` with engine: native and options.sync: false: Collect (collect) -> Compress (compress, end)",
                                   "Validate for azure (prod), run collect locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.archive",
            value={"engine": "native", "options": {"sync": False}, "start_at": "Collect",
                   "states": {"Collect": {"type": "task", "function": "collect", "next": "Compress"},
                              "Compress": {"type": "task", "function": "compress", "end": True}}}),
          S("invoke_local", function="collect", type="workflow", data={"job": "nov-2026"}),
      ],
      final="""Added as a Logic App that answers at once:

```yaml
workflows:
  archive:
    engine: native
    options: {sync: false}
    start_at: Collect
    states:
      Collect:  {type: task, function: collect, next: Compress}
      Compress: {type: task, function: compress, end: true}
```

- `engine: native` → Azure Logic App. `options.sync: false` drops the `Response` actions, so the caller gets `202` immediately, like `StartExecution` [docs/workflows.md#workflow-keys].
- That matters here: a synchronous Logic App response must come within about 2 minutes [docs/workflows.md#compiler-notes-and-limits].
- `pskit validate` (azure, prod): valid. `collect` locally: returned `"files": 120`.

Note that each task call times out after 120 s, so `compress` itself must finish within 120 s. The whole run can be longer. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`; `pskit info` then shows the trigger URL (treat it like a secret)."""),

    # ------------------------------------------------------------------ 424
    B(424, provider="aws", stage="staging", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: ledger-writer
provider:
  name: aws
  region: us-east-2
functions:
  post-entry:
    handler: app.ledger.post_entry
    timeout: 20
""",
          "app/__init__.py": "",
          "app/ledger.py": FUTURE + """from py_serverless_kit import BatchResult


def post_entry(event, ctx):
    result = BatchResult()
    for record in event.records:
        entry = record.json(default={}) or {}
        if "account" not in entry:
            result.fail(record)
    return result
""",
          "requirements.txt": ""}),
      user="post-entry: fifo sqs `ledger-entries`, batch 1, dlq ledger-dlq after 3",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add queue {name: ledger-entries, fifo: true, batch_size: 1, dead_letter: ledger-dlq, max_receive: 3} to post-entry",
                                   "Validate aws (staging), invoke one message"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.post-entry.events",
            value=[{"queue": {"name": "ledger-entries", "fifo": True, "batch_size": 1,
                              "dead_letter": "ledger-dlq", "max_receive": 3}}]),
          S("invoke_local", function="post-entry", type="queue", data=[{"account": "4000", "amount": 25}]),
      ],
      final="""```yaml
functions:
  post-entry:
    events:
      - queue: {name: ledger-entries, fifo: true, batch_size: 1, dead_letter: ledger-dlq, max_receive: 3}
```

- `fifo: true` gives the SQS queue the `.fifo` suffix and content-based dedup; redrive goes to `ledger-dlq` after 3 receives [docs/events.md#queue].
- validate (aws, staging): valid.
- invoke: `{"batchItemFailures": []}`.

Retest: `pskit invoke -f post-entry -t queue -d '[{"amount": 1}]'` (should list one failure). Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 425
    B(425, provider="gcp", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#provider-support", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: school-reports
provider:
  name: gcp
  region: europe-west2
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, school-reports-dev}
functions:
  make-report:
    handler: app.reports.make
    events:
    - http: POST /reports
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + """

def make(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="I need somewhere to keep the PDF reports my function makes. Can pskit make a storage bucket for that and tell my function about it?",
      steps=[
          S("get_project"),
          S("search_docs", query="create bucket resource storage gcp handler resource()",
            docs=[D("docs/resources.md", "provider-support", start="| | Managed, used by an event", end="| gcp |"),
                  D("docs/resources.md", "runtime-api", end="jobs.external")]),
          S("propose_plan", steps=["Add resource `report-files`: type storage, name school-reports-files-dev, bound to make-report",
                                   "`make-report` returns the bucket name from resource(\"report-files\") so you can see the link",
                                   "Validate for gcp and call it locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.report-files",
            value={"type": "storage", "name": "school-reports-files-dev", "functions": ["make-report"]}),
          S("write_file", path="app/reports.py", content=FUTURE + """from py_serverless_kit import resource


def make(event, ctx):
    bucket = resource("report-files")
    return {"ok": True, "bucket": bucket.native_name}
"""),
          S("validate"),
          S("invoke_local", function="make-report", method="POST", path="/reports", data={"class": "5B"}),
      ],
      final="""Yes. pskit now creates a Cloud Storage bucket for your reports and tells `make-report` about it:

```yaml
resources:
  report-files:
    type: storage
    name: school-reports-files-dev
    functions: [make-report]
```

- In the code, `resource("report-files").native_name` gives the bucket's name [docs/resources.md#runtime-api].
- `pskit validate` (gcp): valid.
- Local test: `{"ok": true, "bucket": "school-reports-files-dev"}`.

Bucket names are global on Google Cloud, so if deploy says the name is taken, pick another `name`. To save the PDFs, use the `google-cloud-storage` library with that bucket name (add it to requirements.txt). The bucket is created when you deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 426
    B(426, provider="azure", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/providers.md", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: catalog-import
provider:
  name: azure
  region: swedencentral
functions:
  nightly-import:
    handler: app.importer.run
    timeout: 300
    events:
    - schedule: 0 2 * * *
""",
          "app/__init__.py": "",
          "app/importer.py": FUTURE + """

def run(event, ctx):
    return {"imported": 0}
""",
          "requirements.txt": ""}),
      user="""2026-10-31T02:05:00.112Z [Error] Timeout value of 00:05:00 exceeded by function 'Functions.nightly-import' (Id: '5f3c...'). Initiating cancellation.
the import is just getting bigger, give it the most time azure allows""",
      steps=[
          S("get_project"),
          S("search_docs", query="azure max timeout",
            docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| [`azure`]")]),
          S("propose_plan", steps=["Raise functions.nightly-import.timeout from 300 to 600 (the Azure maximum in pskit)",
                                   "Validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.nightly-import.timeout", value=600),
      ],
      final="""The function hit its 5-minute limit (`timeout: 300`). I raised it to the Azure maximum:

```yaml
functions:
  nightly-import:
    timeout: 600
```

- 600 s is the max timeout for Azure in pskit's provider table [docs/providers.md].
- `pskit validate` (azure, staging): valid.

If the import keeps growing past 10 minutes, split it, for example a schedule that puts one message per batch on a queue and a queue worker that imports one batch each. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 427
    B(427, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions", "docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: aws
  region: us-east-1
functions:
  create-order:
    handler: app.orders.create
    events:
    - http: POST /orders
  list-orders:
    handler: app.orders.list_all
    events:
    - http: GET /orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def create(event, ctx):
    return {"ok": True}, 201


def list_all(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="`create-order` will write to the existing DynamoDB table `orders-prod` (arn:aws:dynamodb:us-east-1:123456789012:table/orders-prod). Give only that function dynamodb:PutItem on that table, and pass the table name in an env var TABLE_NAME. `list-orders` must not get write access.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.create-order.iam.statements: Allow dynamodb:PutItem on the orders-prod table ARN",
                                   "functions.create-order.environment: TABLE_NAME=orders-prod",
                                   "Validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.create-order.iam",
            value={"statements": [{"actions": ["dynamodb:PutItem"],
                                   "resources": ["arn:aws:dynamodb:us-east-1:123456789012:table/orders-prod"]}]}),
          S("set_config", path="functions.create-order.environment", value={"TABLE_NAME": "orders-prod"}),
      ],
      final="""Configured `create-order` only:

```yaml
functions:
  create-order:
    environment:
      TABLE_NAME: orders-prod
    iam:
      statements:
        - actions: ["dynamodb:PutItem"]
          resources: ["arn:aws:dynamodb:us-east-1:123456789012:table/orders-prod"]
```

- A function-level `iam` block gets a dedicated role on AWS, so `list-orders` keeps its own role without this permission [docs/configuration.md#functions].
- `pskit validate` (aws, prod) passed after both changes.

In the handler, read `ctx.env["TABLE_NAME"]` and write with boto3 (add `boto3` to requirements.txt). Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 428
    B(428, provider="gcp", stage="prod", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: search-api
provider:
  name: gcp
  region: us-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, search-prod}
functions:
  search:
    handler: app.search.query
    events:
    - http: GET /search
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """

def query(event, ctx):
    return {"hits": []}
""",
          "requirements.txt": ""}),
      user="run functions as search-runtime@search-prod.iam.gserviceaccount.com, not the default SA",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.service_account = search-runtime@search-prod.iam.gserviceaccount.com",
                                   "Validate gcp (prod)"]),
          S("set_config", path="provider.options.service_account", value="search-runtime@search-prod.iam.gserviceaccount.com"),
      ],
      final="""```yaml
provider:
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, search-prod}
    service_account: search-runtime@search-prod.iam.gserviceaccount.com
```

validate (gcp, prod): valid. `options.service_account` is the runtime identity for every function [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. `iam.statements` are ignored on GCP, so grant that service account its roles in GCP IAM. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 429
    B(429, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: price-watch
provider:
  name: azure
  region: centralus
functions:
  check-prices:
    handler: app.watch.check
""",
          "app/__init__.py": "",
          "app/watch.py": FUTURE + """

def check(event, ctx):
    ctx.logger.info("checking prices")
    return {"checked": 3}
""",
          "requirements.txt": ""}),
      user="how do i make check-prices run by itself every 5 minutes? please just do it for me",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `- schedule: 5 minutes` to check-prices",
                                   "Validate for azure and run it once locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.check-prices.events", value=[{"schedule": "5 minutes"}]),
          S("invoke_local", function="check-prices", type="schedule"),
      ],
      final="""Done. `check-prices` now runs by itself every 5 minutes:

```yaml
functions:
  check-prices:
    events:
      - schedule: 5 minutes
```

- On Azure this becomes a timer trigger (`0 */5 * * * *`, UTC) [docs/events.md#schedule].
- `pskit validate` (azure): valid.
- One local run: `{"checked": 3}`.

It starts running on its own after you deploy: **Deploy** page or `pskit deploy -s dev`. To run it once by hand: **Test** > **▶ Run locally** with a schedule event, or `pskit invoke -f check-prices -t schedule`."""),

    # ------------------------------------------------------------------ 430
    B(430, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: order-alerts
provider:
  name: aws
  region: eu-north-1
functions:
  send-email:
    handler: app.alerts.email
  send-sms:
    handler: app.alerts.sms
  send-push:
    handler: app.alerts.push
""",
          "app/__init__.py": "",
          "app/alerts.py": FUTURE + """

def email(event, ctx):
    return {"email": "sent"}


def sms(event, ctx):
    return {"sms": "sent"}


def push(event, ctx):
    return {"push": "sent"}
""",
          "requirements.txt": ""}),
      user="when an order comes in I want to send the email and the sms at the same time, not one after the other. can you make a workflow for that?",
      steps=[
          S("get_project"),
          S("search_docs", query="parallel branches workflow",
            docs=[D("docs/workflows.md", "state-types", start="| `type` | Fields |", end="| `parallel` |")]),
          S("propose_plan", steps=["Add workflow `notify-order` with one parallel state `SendAll`: branch 1 send-email, branch 2 send-sms",
                                   "Validate for aws and run send-email locally"],
            result={"decision": "approved", "note": "add the push notification as a third branch too"}),
          S("set_config", path="workflows.notify-order",
            value={"start_at": "SendAll",
                   "states": {"SendAll": {"type": "parallel", "end": True, "branches": [
                       {"start_at": "Email", "states": {"Email": {"type": "task", "function": "send-email", "end": True}}},
                       {"start_at": "Sms", "states": {"Sms": {"type": "task", "function": "send-sms", "end": True}}},
                       {"start_at": "Push", "states": {"Push": {"type": "task", "function": "send-push", "end": True}}}]}}},
            say="Adding push as a third branch, as you asked."),
          S("invoke_local", function="send-email", type="workflow", data={"order_id": "o-77"}),
      ],
      final="""Done. The workflow `notify-order` sends email, SMS **and push** at the same time (three parallel branches):

```yaml
workflows:
  notify-order:
    start_at: SendAll
    states:
      SendAll:
        type: parallel
        end: true
        branches:
          - {start_at: Email, states: {Email: {type: task, function: send-email, end: true}}}
          - {start_at: Sms,   states: {Sms:   {type: task, function: send-sms, end: true}}}
          - {start_at: Push,  states: {Push:  {type: task, function: send-push, end: true}}}
```

- A `parallel` state runs its branches at the same time; the result is a list with one item per branch [docs/workflows.md#state-types].
- `pskit validate` (aws): valid. On AWS it becomes a Step Functions state machine.
- `send-email` locally: `{"email": "sent"}`.

Try the whole thing: `pskit workflow run notify-order -i '{"order_id": "o-77"}'`, or the `Run a workflow locally` panel on the Deploy page. Deploy: the **Deploy** button there, or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 431
    B(431, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#data-flow"],
      project=dict(files={
          "pskit.yml": """service: translator
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, translator-staging}
functions:
  translate-doc:
    handler: app.translate.one
""",
          "app/__init__.py": "",
          "app/translate.py": FUTURE + """

def one(event, ctx):
    doc = dict(event.data or {})
    return {"doc": doc.get("path"), "lang": doc.get("lang", "de"), "done": True}
""",
          "requirements.txt": ""}),
      user="Workflow `translate-batch`: the input has `docs`, a list of {path, lang}. Run translate-doc for each item, at most 5 at a time, and store the results under `$.results` so the original input stays.",
      steps=[
          S("get_project"),
          S("search_docs", query="map items_path iterator max_concurrency result_path",
            docs=[D("docs/workflows.md", "state-types", start="| `map` |", end="| `map` |"),
                  D("docs/workflows.md", "data-flow", start="- `result_path`")]),
          S("propose_plan", steps=["Add workflow `translate-batch`: one map state EachDoc, items_path $.docs, max_concurrency 5, result_path $.results, iterator = task translate-doc",
                                   "Validate for gcp (staging), run translate-doc locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.translate-batch",
            value={"start_at": "EachDoc",
                   "states": {"EachDoc": {"type": "map", "items_path": "$.docs", "max_concurrency": 5,
                                          "result_path": "$.results", "end": True,
                                          "iterator": {"start_at": "Translate", "states": {
                                              "Translate": {"type": "task", "function": "translate-doc", "end": True}}}}}}),
          S("invoke_local", function="translate-doc", type="workflow", data={"path": "docs/a.md", "lang": "fr"}),
      ],
      final="""Added:

```yaml
workflows:
  translate-batch:
    start_at: EachDoc
    states:
      EachDoc:
        type: map
        items_path: $.docs
        max_concurrency: 5
        result_path: $.results
        end: true
        iterator:
          start_at: Translate
          states:
            Translate: {type: task, function: translate-doc, end: true}
```

- `map` runs the iterator for each item of `$.docs` and returns a list; `result_path: $.results` keeps the original input next to it [docs/workflows.md#data-flow].
- validate (gcp, staging): valid (Cloud Workflows).
- `translate-doc` locally: `{"doc": "docs/a.md", "lang": "fr", "done": true}`.

Full run: `pskit workflow run translate-batch -i '{"docs": [{"path": "a.md", "lang": "fr"}]}' --history`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 432
    B(432, provider="azure", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: partner-intake
provider:
  name: azure
  region: eastus2
functions: {}
""",
          "requirements.txt": ""}),
      user="blob trigger on existing container `partner-uploads` in the partner's storage account (conn string in app setting PARTNER_STORAGE). fn `intake`, only .json",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.storage_connection = PARTNER_STORAGE",
                                   "Write app/intake.py; function intake with storage {bucket: partner-uploads, existing: true, suffix: .json}",
                                   "Validate azure (staging), invoke one blob"]),
          S("set_config", path="provider.options.storage_connection", value="PARTNER_STORAGE"),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/intake.py", content=FUTURE + """

def intake(event, ctx):
    keys = []
    for record in event.records:
        ctx.logger.info("partner blob", extra={"key": record.key, "size": record.size})
        keys.append(record.key)
    return {"received": keys}
"""),
          S("set_config", path="functions.intake",
            value={"handler": "app.intake.intake",
                   "events": [{"storage": {"bucket": "partner-uploads", "existing": True, "suffix": ".json"}}]}),
          S("invoke_local", function="intake", type="storage", data={"bucket": "partner-uploads", "key": "batch-17.json", "size": 812}),
      ],
      final="""```yaml
provider:
  options:
    storage_connection: PARTNER_STORAGE
functions:
  intake:
    handler: app.intake.intake
    events:
      - storage: {bucket: partner-uploads, existing: true, suffix: .json}
```

- `existing` containers in another account need `options.storage_connection`, the app setting that holds that account's connection string [docs/providers.md#azure-azure-functions].
- validate (azure, staging): valid. invoke: `{"received": ["batch-17.json"]}`.

Fires on created/updated blobs only. The `PARTNER_STORAGE` app setting must exist on the Function App. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 433
    B(433, provider="aws", stage="staging", mode="auto", page="Functions", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: standup-bot
provider:
  name: aws
  region: us-east-1
functions:
  remind:
    handler: app.bot.remind
""",
          "app/__init__.py": "",
          "app/bot.py": FUTURE + """

def remind(event, ctx):
    channel = (event.data or {}).get("channel", "general")
    return {"reminded": channel}
""",
          "requirements.txt": ""}),
      user="EventBridge rule was cron(0 12 ? * MON-FRI *) in New York time, with input {\"channel\": \"standup\"}. port it to remind",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["schedule {cron: \"0 12 * * 1-5\", timezone: America/New_York, input: {channel: standup}} on remind",
                                   "Validate aws (staging), invoke schedule"]),
          S("set_config", path="functions.remind.events",
            value=[{"schedule": {"cron": "0 12 * * 1-5", "timezone": "America/New_York", "input": {"channel": "standup"}}}]),
          S("invoke_local", function="remind", type="schedule"),
      ],
      final="""Ported:

```yaml
functions:
  remind:
    events:
      - schedule:
          cron: "0 12 * * 1-5"
          timezone: America/New_York
          input: {channel: standup}
```

pskit takes standard 5-field cron (no `?`, no year) and converts it to EventBridge Scheduler's `cron(...)` form itself (day-of-week renumbered, `?` inserted). Scheduler honours `timezone` [docs/events.md#schedule].

- validate (aws, staging): valid.
- invoke: `{"reminded": "standup"}`.

Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 434
    B(434, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: feedback
provider:
  name: gcp
  region: southamerica-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, feedback-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="my react app on https://app.example.com need send feedback POST to gcp function. browser block cors always, make it work from start pls",
      steps=[
          S("get_project"),
          S("search_docs", query="cors origins preflight",
            docs=[D("docs/events.md", "http", start="**CORS**", end="AWS additionally configures CORS")]),
          S("propose_plan", steps=["Write `app/feedback.py`: take {rating, text}, return 201",
                                   "Add function `feedback` on POST /feedback with cors origins [https://app.example.com], methods [POST]",
                                   "Validate for gcp, invoke a POST"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/feedback.py", content=FUTURE + """

def feedback(event, ctx):
    body = event.http.json(default={}) or {}
    ctx.logger.info("feedback", extra={"rating": body.get("rating")})
    return {"thanks": True}, 201
"""),
          S("set_config", path="functions.feedback",
            value={"handler": "app.feedback.feedback",
                   "events": [{"http": {"path": "/feedback", "method": "POST",
                                        "cors": {"origins": ["https://app.example.com"], "methods": ["POST"]}}}]}),
          S("invoke_local", function="feedback", method="POST", path="/feedback", data={"rating": 5, "text": "nice"}),
      ],
      final="""Done. `feedback` takes `POST /feedback` and allows your React app's origin:

```yaml
functions:
  feedback:
    handler: app.feedback.feedback
    events:
      - http:
          path: /feedback
          method: POST
          cors:
            origins: ["https://app.example.com"]
            methods: [POST]
```

- The pskit runtime answers the browser's `OPTIONS` preflight with 204 and adds `Access-Control-*` headers, also on GCP [docs/events.md#http].
- validate (gcp): valid.
- local POST: 201 `{"thanks": true}`.

Deploy with **Deploy** or `pskit deploy -s dev`, then use the URL from `pskit info` in your app."""),

    # ------------------------------------------------------------------ 435
    B(435, provider="azure", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: crm-api
provider:
  name: azure
  region: westeurope
functions:
  customers:
    handler: app.crm.customers
    events:
    - http: GET /customers
""",
          "app/__init__.py": "",
          "app/crm.py": FUTURE + """

def customers(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="We have an Azure Database for PostgreSQL that is managed by the DBA team. Register it as `crm-db` (host from env PG_HOST, port 5432, database crm, user crm_app, password in env PG_PASSWORD) and bind it to `customers`. The handler should return host and database (never the password) so we can check the binding.",
      steps=[
          S("get_project"),
          S("search_docs", query="external database resource connection password_env",
            docs=[D("docs/resources.md", "resources-storage-queues-topics-databases-any-service", start="  orders-db:", end="functions: [api, worker]")]),
          S("propose_plan", steps=["resources.crm-db: type database, external, connection {host: ${env:PG_HOST, ...}, port 5432, database crm, user crm_app, password_env PG_PASSWORD}, functions [customers]",
                                   "customers returns host and database from resource(\"crm-db\")",
                                   "Validate for azure (prod), invoke GET /customers"],
            result={"decision": "approved", "note": "use crm-db.example.com as the local default host"}),
          S("set_config", path="resources.crm-db",
            value={"type": "database", "external": True, "functions": ["customers"],
                   "connection": {"host": "${env:PG_HOST, crm-db.example.com}", "port": 5432, "database": "crm",
                                  "user": "crm_app", "password_env": "PG_PASSWORD"}}),
          S("write_file", path="app/crm.py", content=FUTURE + """from py_serverless_kit import resource


def customers(event, ctx):
    db = resource("crm-db")
    return {"host": db.get("host"), "database": db.get("database")}
"""),
          S("validate"),
          S("invoke_local", function="customers", method="GET", path="/customers"),
      ],
      final="""Registered the existing database (pskit never creates or changes it):

```yaml
resources:
  crm-db:
    type: database
    external: true
    connection:
      host: ${env:PG_HOST, crm-db.example.com}
      port: 5432
      database: crm
      user: crm_app
      password_env: PG_PASSWORD
    functions: [customers]
```

- `password_env` holds the **name** of the secret variable, not the secret [docs/resources.md]. The handler reads the password with `ctx.env[db["password_env"]]` when it connects.
- `pskit validate` (azure, prod): valid.
- invoke `GET /customers`: `{"host": "crm-db.example.com", "database": "crm"}` (the default host from your note).

Set `PG_HOST` and `PG_PASSWORD` where you deploy; on Azure they become app settings of the Function App. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 436
    B(436, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: gh-hooks
provider:
  name: aws
  region: us-east-1
functions: {}
""",
          "requirements.txt": ""}),
      user="brand new project. I want GitHub to call my code whenever someone pushes. what do I need?",
      steps=[
          S("get_project"),
          S("search_docs", query="http request headers json body",
            docs=[D("docs/handlers.md", "httprequest", words=160)]),
          S("propose_plan", steps=["Write `app/github.py`: read the X-GitHub-Event header and the JSON body, log the repository name",
                                   "Add function `github-webhook` on POST /webhooks/github",
                                   "Validate for aws and send a fake push locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/github.py", content=FUTURE + """

def webhook(event, ctx):
    kind = event.http.headers.get("x-github-event", "unknown")
    payload = event.http.json(default={}) or {}
    repo = (payload.get("repository") or {}).get("full_name")
    ctx.logger.info("github event", extra={"kind": kind, "repo": repo})
    return {"received": kind, "repo": repo}
"""),
          S("set_config", path="functions.github-webhook",
            value={"handler": "app.github.webhook", "events": [{"http": "POST /webhooks/github"}]}),
          S("invoke_local", function="github-webhook", method="POST", path="/webhooks/github",
            data={"repository": {"full_name": "acme/website"}}),
      ],
      final="""You need one function with a web address that GitHub can call. I made it:

- `github-webhook` on `POST /webhooks/github`. It reads the `X-GitHub-Event` header and the repository name from the JSON body [docs/handlers.md#httprequest].
- `pskit validate` (aws): valid.
- Fake push locally: `{"received": "unknown", "repo": "acme/website"}`. The kind is `unknown` because the local test sent no header; GitHub always sends it.

Next steps:
1. Deploy: **Deploy** page or `pskit deploy -s dev`.
2. `pskit info` shows the address. In GitHub: repository Settings > Webhooks > Add webhook, paste the address + `/webhooks/github`, content type `application/json`.
3. Before using it for real, check GitHub's signature header with a secret from `${env:...}`. I can add that next."""),

    # ------------------------------------------------------------------ 437
    B(437, provider="gcp", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#topic", "docs/migrating-from-aws.md#step-5-move-to-another-cloud"],
      project=dict(files={
          "pskit.yml": """service: invoicing
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, invoicing-staging}
functions:
  make-invoice:
    handler: app.invoices.make
""",
          "app/__init__.py": "",
          "app/invoices.py": FUTURE + """

def make(event, ctx):
    made = []
    for record in event.records:
        made.append((record.json(default={}) or {}).get("order_id"))
    return {"invoices": made}
""",
          "requirements.txt": ""}),
      user="On AWS make-invoice was subscribed to an SNS topic. On GCP the billing team already runs a Pub/Sub topic `billing-events` in this project, we must not create or delete it. Subscribe make-invoice to it.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `- topic: {name: billing-events, existing: true}` to make-invoice",
                                   "Validate for gcp (staging), invoke two messages"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.make-invoice.events",
            value=[{"topic": {"name": "billing-events", "existing": True}}]),
          S("invoke_local", function="make-invoice", type="topic", data=[{"order_id": "A-1"}, {"order_id": "A-2"}]),
      ],
      final="""Subscribed to the billing team's topic:

```yaml
functions:
  make-invoice:
    events:
      - topic: {name: billing-events, existing: true}
```

- With `existing: true` pskit only adds the Eventarc trigger; the topic `billing-events` is never created or deleted by your stack [docs/events.md#topic].
- validate (gcp, staging): valid.
- invoke with two messages: `{"invoices": ["A-1", "A-2"]}`. The handler code is unchanged from AWS.

If you used an SNS filter policy before: `filter` isn't applied on Pub/Sub, so filter in the handler. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 438
    B(438, provider="azure", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#provider", "docs/events.md#azure-one-function-app-per-service"],
      project=dict(files={
          "pskit.yml": """service: beta-features
provider:
  name: azure
  region: australiaeast
functions:
  home:
    handler: app.site.home
    events:
    - http: GET /
  search:
    handler: app.site.search
    events:
    - http: GET /search
""",
          "app/__init__.py": "",
          "app/site.py": FUTURE + """

def home(event, ctx):
    return {"new_ui": ctx.env.get("NEW_UI", "off") == "on"}


def search(event, ctx):
    return {"new_ui": ctx.env.get("NEW_UI", "off") == "on", "results": []}
""",
          "requirements.txt": ""}),
      user="add env NEW_UI=on for all functions, not one by one",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.environment.NEW_UI = \"on\"",
                                   "Validate azure, invoke home"]),
          S("set_config", path="provider.environment", value={"NEW_UI": "on"}),
          S("invoke_local", function="home", method="GET", path="/"),
      ],
      final="""Set once for every function:

```yaml
provider:
  environment:
    NEW_UI: "on"
```

- validate (azure): valid.
- invoke `GET /`: `{"new_ui": true}`.

On Azure all functions share one Function App, so environment is app-wide anyway [docs/events.md#azure-one-function-app-per-service]. Quote `"on"`, otherwise YAML reads it as `true`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 439
    B(439, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#aws-aws-lambda", "docs/configuration.md#escape-hatches"],
      project=dict(files={
          "pskit.yml": """service: risk-engine
provider:
  name: aws
  region: eu-west-1
functions:
  score:
    handler: app.risk.score
    events:
    - http: POST /score
""",
          "app/__init__.py": "",
          "app/risk.py": FUTURE + """

def score(event, ctx):
    return {"score": 0.1}
""",
          "requirements.txt": ""}),
      user="`score` has to run inside our VPC (subnets subnet-0a1b2c3d and subnet-4e5f6a7b, security group sg-0123abcd) to reach the internal model service, and it needs our shared layer arn:aws:lambda:eu-west-1:123456789012:layer:ml-deps:7. pskit has no keys for those, right? How do we add them?",
      steps=[
          S("get_project"),
          S("search_docs", query="aws function options layers vpc_config escape hatch",
            docs=[D("docs/providers.md", "aws-aws-lambda", start="functions:", end="vpc_config:")]),
          S("propose_plan", steps=["Set functions.score.options = {layers: [the ml-deps:7 ARN], vpc_config: {subnet_ids: [...], security_group_ids: [sg-0123abcd]}}",
                                   "Validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.score.options",
            value={"layers": ["arn:aws:lambda:eu-west-1:123456789012:layer:ml-deps:7"],
                   "vpc_config": {"subnet_ids": ["subnet-0a1b2c3d", "subnet-4e5f6a7b"],
                                  "security_group_ids": ["sg-0123abcd"]}}),
      ],
      final="""Right, there are no dedicated keys. `functions.<fn>.options` is the escape hatch: it's merged into the `aws_lambda_function` resource [docs/providers.md#aws-aws-lambda]:

```yaml
functions:
  score:
    options:
      layers: ["arn:aws:lambda:eu-west-1:123456789012:layer:ml-deps:7"]
      vpc_config:
        subnet_ids: [subnet-0a1b2c3d, subnet-4e5f6a7b]
        security_group_ids: [sg-0123abcd]
```

- `pskit validate` (aws, prod): valid. validate doesn't check these values against AWS, so the IDs must be right.
- These keys are AWS-only, so keep them under `providers.aws` if this project ever targets another cloud [docs/configuration.md#escape-hatches].

Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 440
    B(440, provider="gcp", stage="dev", mode="auto", page="Functions", persona="beginner",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: contracts
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, contracts-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="I want to keep a log every time somebody deletes a file from the contracts-archive bucket",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/audit.py`: log bucket, key and action for each record",
                                   "Add function `deletion-audit` with storage {bucket: contracts-archive, events: [deleted]}",
                                   "Validate for gcp and test one delete event"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/audit.py", content=FUTURE + """

def deletion_audit(event, ctx):
    gone = []
    for record in event.records:
        ctx.logger.warning("file deleted", extra={"bucket": record.bucket, "key": record.key, "action": record.action})
        gone.append(record.key)
    return {"deleted": gone}
"""),
          S("set_config", path="functions.deletion-audit",
            value={"handler": "app.audit.deletion_audit",
                   "events": [{"storage": {"bucket": "contracts-archive", "events": ["deleted"]}}]}),
          S("invoke_local", function="deletion-audit", type="storage",
            data={"bucket": "contracts-archive", "key": "2025/acme-nda.pdf", "action": "deleted"}),
      ],
      final="""Done. The function `deletion-audit` writes a log line every time a file is deleted from `contracts-archive`:

```yaml
functions:
  deletion-audit:
    handler: app.audit.deletion_audit
    events:
      - storage: {bucket: contracts-archive, events: [deleted]}
```

- `pskit validate` (gcp): valid. On GCP this uses the Cloud Storage `deleted` event [docs/events.md#storage].
- Test delete event: `{"deleted": ["2025/acme-nda.pdf"]}`, plus a warning log line with the file name.

pskit creates the bucket `contracts-archive` when you deploy (add `existing: true` if it already exists). See the log lines on the **Logs** page after deploy. Deploy: **Deploy** page or `pskit deploy -s dev`."""),
]
