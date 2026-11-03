"""Category B (build / add), batch 23 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 441
    B(441, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: clickstream
provider:
  name: aws
  region: us-west-2
functions:
  aggregate:
    handler: app.clicks.aggregate
    timeout: 60
""",
          "app/__init__.py": "",
          "app/clicks.py": FUTURE + """

def aggregate(event, ctx):
    pages = {}
    for record in event.records:
        page = (record.json(default={}) or {}).get("page", "?")
        pages[page] = pages.get(page, 0) + 1
    return {"pages": pages}
""",
          "requirements.txt": ""}),
      user="aggregate on sqs `click-events`: batch 100, wait up to 30s to fill the batch",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["queue {name: click-events, batch_size: 100, batch_window: 30} on aggregate",
                                   "Validate aws, invoke 3 clicks"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.aggregate.events",
            value=[{"queue": {"name": "click-events", "batch_size": 100, "batch_window": 30}}]),
          S("invoke_local", function="aggregate", type="queue",
            data=[{"page": "/"}, {"page": "/pricing"}, {"page": "/"}]),
      ],
      final="""```yaml
functions:
  aggregate:
    events:
      - queue: {name: click-events, batch_size: 100, batch_window: 30}
```

- `batch_window` (0-300 s) lets SQS wait to fill the batch; both options apply on AWS [docs/events.md#queue].
- validate (aws): valid.
- invoke with 3 clicks: `{"pages": {"/": 2, "/pricing": 1}}`.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 442
    B(442, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: docs-proxy
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, docs-proxy-staging}
functions: {}
""",
          "requirements.txt": ""}),
      user="i need one endpoint GET /files/ and then anything after, like /files/a/b/c.pdf, and code get the full a/b/c.pdf part",
      steps=[
          S("get_project"),
          S("search_docs", query="path template greedy rest of path",
            docs=[D("docs/events.md", "http", start="**Path templates**", end="Parameter names are identifiers")]),
          S("propose_plan", steps=["Write `app/files.py`: return path_params[\"path\"]",
                                   "Add function `files` on GET /files/{path+}",
                                   "Validate for gcp (staging), invoke /files/a/b/c.pdf"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/files.py", content=FUTURE + """

def files(event, ctx):
    rest = event.http.path_params.get("path", "")
    return {"file": rest}
"""),
          S("set_config", path="functions.files",
            value={"handler": "app.files.files", "events": [{"http": "GET /files/{path+}"}]}),
          S("invoke_local", function="files", method="GET", path="/files/a/b/c.pdf"),
      ],
      final="""Done. `{path+}` takes the rest of the path, so `files` gets everything after `/files/`:

```yaml
functions:
  files:
    handler: app.files.files
    events:
      - http: GET /files/{path+}
```

- `{name+}` is greedy and must be the last segment [docs/events.md#http].
- validate (gcp, staging): valid.
- invoke `/files/a/b/c.pdf`: 200 `{"file": "a/b/c.pdf"}`.

Retest: `pskit invoke -f files --method GET --path /files/x/y.txt`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 443
    B(443, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#queue", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: invoice-worker
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="Create `render-invoice`, triggered by an Azure Storage queue `invoice-jobs`. Each message is {\"invoice_id\": ...}. Messages without invoice_id are invalid and should be reported as failed. Return value can be whatever pskit expects for partial failures.",
      steps=[
          S("get_project"),
          S("search_docs", query="BatchResult partial failure azure storage queue poison",
            docs=[D("docs/handlers.md", "batchresult", start="| Provider | Behaviour |", end="Write idempotent handlers"),
                  D("docs/events.md", "queue", start="| `dead_letter`, `max_receive`", end="| partial batch failure")]),
          S("propose_plan", steps=["Write `app/invoices.py` returning a BatchResult with the invalid messages",
                                   "Add function `render-invoice` with `- queue: invoice-jobs`",
                                   "Validate for azure, invoke one good and one bad message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/invoices.py", content=FUTURE + """from py_serverless_kit import BatchResult


def render_invoice(event, ctx):
    result = BatchResult()
    for record in event.records:
        job = record.json(default={}) or {}
        if "invoice_id" not in job:
            result.fail(record)
            continue
        ctx.logger.info("render invoice", extra={"invoice_id": job["invoice_id"]})
    return result
"""),
          S("set_config", path="functions.render-invoice",
            value={"handler": "app.invoices.render_invoice", "events": [{"queue": "invoice-jobs"}]}),
          S("invoke_local", function="render-invoice", type="queue", data=[{"invoice_id": "INV-9"}, {"total": 3}]),
      ],
      final="""Created `render-invoice` on the Storage Queue `invoice-jobs`:

```yaml
functions:
  render-invoice:
    handler: app.invoices.render_invoice
    events:
      - queue: invoice-jobs
```

- validate (azure): valid.
- Local run: `batchItemFailures` lists only the message without `invoice_id`.

How it behaves on Azure: a `BatchResult` with failures raises `BatchFailure`, so the whole delivery is retried (only AWS and on-prem retry single messages). Messages that keep failing go to the poison queue `invoice-jobs-poison` [docs/handlers.md#batchresult]. Keep the handler idempotent. Retest: `pskit invoke -f render-invoice -t queue -d '[{"invoice_id": "INV-1"}]'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 444
    B(444, provider="aws", stage="staging", mode="auto", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md", "docs/resources.md#what-handlers-receive"],
      project=dict(files={
          "pskit.yml": """service: order-service
provider:
  name: aws
  region: us-east-1
functions:
  publisher:
    handler: app.events.publish
    events:
    - http: POST /orders
""",
          "app/__init__.py": "",
          "app/events.py": FUTURE + """

def publish(event, ctx):
    return {"published": False}
""",
          "requirements.txt": ""}),
      user="publisher must publish to the SNS topic from our old CloudFormation stack, arn:aws:sns:us-east-1:123456789012:billing-events. Attach it, don't create anything. Return the ARN from the binding for now.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.billing-events: topic, external: true, connection.arn = the stack's ARN, functions [publisher]",
                                   "publisher returns resource(\"billing-events\").arn",
                                   "Validate aws (staging), invoke POST /orders"]),
          S("set_config", path="resources.billing-events",
            value={"type": "topic", "external": True, "functions": ["publisher"],
                   "connection": {"arn": "arn:aws:sns:us-east-1:123456789012:billing-events"}}),
          S("write_file", path="app/events.py", content=FUTURE + """from py_serverless_kit import resource


def publish(event, ctx):
    topic = resource("billing-events")
    return {"published": False, "topic_arn": topic.arn}
"""),
          S("validate"),
          S("invoke_local", function="publisher", method="POST", path="/orders", data={"order_id": "o-1"}),
      ],
      final="""Attached the existing topic:

```yaml
resources:
  billing-events:
    type: topic
    external: true
    connection:
      arn: arn:aws:sns:us-east-1:123456789012:billing-events
    functions: [publisher]
```

- `external: true`: pskit never creates, changes or deletes it. With `connection.arn`, that ARN is used as-is, and `publisher`'s role gets `sns:Publish` on it [docs/resources.md#what-handlers-receive].
- validate (aws, staging): valid.
- invoke: `"topic_arn": "arn:aws:sns:us-east-1:123456789012:billing-events"`.

Publish with `boto3.client("sns").publish(TopicArn=topic.arn, ...)` and add `boto3` to requirements.txt. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 445
    B(445, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: reminders
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, reminders-prod}
functions:
  send-reminder:
    handler: app.remind.send
""",
          "app/__init__.py": "",
          "app/remind.py": FUTURE + """

def send(event, ctx):
    data = dict(event.data or {})
    return {"to": data.get("user"), "sent": True}
""",
          "requirements.txt": ""}),
      user="wf `delayed-reminder`: wait $.delay_seconds (from input), then send-reminder",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["workflows.delayed-reminder: Wait (seconds_path $.delay_seconds) -> Send (send-reminder, end)",
                                   "Validate gcp (prod), invoke send-reminder"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.delayed-reminder",
            value={"start_at": "Wait",
                   "states": {"Wait": {"type": "wait", "seconds_path": "$.delay_seconds", "next": "Send"},
                              "Send": {"type": "task", "function": "send-reminder", "end": True}}}),
          S("invoke_local", function="send-reminder", type="workflow", data={"user": "u-12", "delay_seconds": 3600}),
      ],
      final="""```yaml
workflows:
  delayed-reminder:
    start_at: Wait
    states:
      Wait: {type: wait, seconds_path: $.delay_seconds, next: Send}
      Send: {type: task, function: send-reminder, end: true}
```

- validate (gcp, prod): valid; native Cloud Workflows, so the wait isn't function time [docs/workflows.md#state-types].
- invoke send-reminder: `{"to": "u-12", "sent": true}`.

Local run skips waits unless `--sleep`: `pskit workflow run delayed-reminder -i '{"user": "u-12", "delay_seconds": 5}' --sleep`. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 446
    B(446, provider="azure", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: todo-app
provider:
  name: azure
  region: canadacentral
functions: {}
""",
          "requirements.txt": ""}),
      user="I want a todo list api. Looking at the list and adding a todo. Just keep them in memory for now, I'll add a database later.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/todos.py`: GET returns the list, POST adds {title} and answers 201",
                                   "Add function `todos` with GET /todos and POST /todos",
                                   "Validate for azure (staging), test adding and listing"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/todos.py", content=FUTURE + """from py_serverless_kit import BadRequest

TODOS = []


def todos(event, ctx):
    if event.http.method == "POST":
        body = event.http.json(default={}) or {}
        if not body.get("title"):
            raise BadRequest("title is required")
        todo = {"id": len(TODOS) + 1, "title": body["title"], "done": False}
        TODOS.append(todo)
        return todo, 201
    return {"todos": TODOS}
"""),
          S("set_config", path="functions.todos",
            value={"handler": "app.todos.todos", "events": [{"http": "GET /todos"}, {"http": "POST /todos"}]}),
          S("invoke_local", function="todos", method="POST", path="/todos", data={"title": "water the plants"}),
          S("invoke_local", function="todos", method="GET", path="/todos"),
      ],
      final="""Your todo API is ready. One function `todos` handles both:

- `GET /todos` shows the list.
- `POST /todos` with `{"title": "..."}` adds one and answers 201 (400 if the title is missing) [docs/handlers.md#returning-a-response].

Checks:
- `pskit validate` (azure, staging): valid.
- POST "water the plants": 201 with the new todo. GET right after: an empty list, because each `pskit invoke` is a new process.

That last point matters in the cloud too: memory is lost whenever Azure starts a new instance, so the list can disappear at any time. That's fine for trying it, but use a database before real users. Try it on **Test** > **▶ Run locally**. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 447
    B(447, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: billing-runs
provider:
  name: aws
  region: eu-west-1
functions:
  monthly-invoices:
    handler: app.billing.monthly
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """

def monthly(event, ctx):
    return {"run": (event.data or {}).get("run", "monthly")}
""",
          "requirements.txt": ""}),
      user="Add a schedule to `monthly-invoices`: 06:00 Europe/Dublin on the 1st of every month, schedule name `invoice-run`, input {\"run\": \"monthly\"}. Create it disabled for now; finance will switch it on after the first manual run.",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule enabled name timezone input",
            docs=[D("docs/events.md", "schedule", end="The handler gets")]),
          S("propose_plan", steps=["Add schedule {cron: \"0 6 1 * *\", timezone: Europe/Dublin, name: invoice-run, input: {run: monthly}, enabled: false}",
                                   "Validate for aws (prod), run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.monthly-invoices.events",
            value=[{"schedule": {"cron": "0 6 1 * *", "timezone": "Europe/Dublin", "name": "invoice-run",
                                 "input": {"run": "monthly"}, "enabled": False}}]),
          S("invoke_local", function="monthly-invoices", type="schedule"),
      ],
      final="""Added, created disabled:

```yaml
functions:
  monthly-invoices:
    events:
      - schedule:
          cron: "0 6 1 * *"
          timezone: Europe/Dublin
          name: invoice-run
          input: {run: monthly}
          enabled: false
```

- EventBridge Scheduler honours `timezone`; `name` is used in the resource name [docs/events.md#schedule].
- `pskit validate` (aws, prod): valid.
- Manual local run: `{"run": "monthly"}`.

For finance's first manual run after deploy: `pskit trigger -f monthly-invoices -s prod`. To switch it on, set `enabled: true` and deploy again. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 448
    B(448, provider="gcp", stage="dev", mode="auto", page="Code", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing"],
      project=dict(files={
          "pskit.yml": """service: greeter
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, greeter-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="""port this lambda to a pskit function on GET /greet/{name}:

def lambda_handler(event, context):
    name = event["pathParameters"]["name"]
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": json.dumps({"hello": name, "request": context.aws_request_id})}""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/greet.py`: path_params[\"name\"], ctx.request_id, return a dict",
                                   "Add function `greet` on GET /greet/{name}",
                                   "Validate gcp, invoke /greet/ana"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/greet.py", content=FUTURE + """

def greet(event, ctx):
    name = event.http.path_params["name"]
    return {"hello": name, "request": ctx.request_id}
"""),
          S("set_config", path="functions.greet",
            value={"handler": "app.greet.greet", "events": [{"http": "GET /greet/{name}"}]}),
          S("invoke_local", function="greet", method="GET", path="/greet/ana"),
      ],
      final="""Ported:

```python
def greet(event, ctx):
    name = event.http.path_params["name"]
    return {"hello": name, "request": ctx.request_id}
```

`event["pathParameters"]` → `event.http.path_params`, `context.aws_request_id` → `ctx.request_id`, and the `statusCode/headers/body` dict becomes a plain dict (JSON 200) [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing].

- validate (gcp): valid.
- invoke `/greet/ana`: 200 `{"hello": "ana", "request": "<id>"}`.

Same code runs on AWS or any other target. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 449
    B(449, provider="azure", stage="prod", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/configuration.md#default-runtime", "docs/providers.md"],
      project=dict(files={
          "pskit.yml": """service: legacy-reports
provider:
  name: azure
  region: northeurope
functions:
  report:
    handler: app.report.build
    events:
    - http: GET /report
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """

def build(event, ctx):
    return {"rows": 0}
""",
          "requirements.txt": ""}),
      user="pin python3.11 for the whole service, a dependency doesn't support 3.12 yet",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.runtime = python3.11", "Validate azure (prod)"]),
          S("set_config", path="provider.runtime", value="python3.11"),
      ],
      final="""```yaml
provider:
  runtime: python3.11
```

validate (azure, prod): valid. Azure supports 3.9-3.12, and without a pin pskit would pick python3.12 [docs/configuration.md#default-runtime]. Pinned at provider level, every function uses it. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 450
    B(450, provider="aws", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#retry-and-catch", "docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: partner-sync
provider:
  name: aws
  region: ap-south-1
functions:
  call-partner:
    handler: app.partner.call
""",
          "app/__init__.py": "",
          "app/partner.py": FUTURE + """

def call(event, ctx):
    req = dict(event.data or {})
    return {**req, "partner_ref": "P-" + str(req.get("id", 0))}
""",
          "requirements.txt": ""}),
      user="partner api sometimes down, ConnectionError. make workflow `sync`: call-partner, retry 5 times wait longer each time start 2 sec, after that mark status ok",
      steps=[
          S("get_project"),
          S("search_docs", query="retry backoff_rate interval_seconds max_attempts",
            docs=[D("docs/workflows.md", "retry-and-catch", end="max_delay_seconds: 60")]),
          S("propose_plan", steps=["Add workflow `sync`: Call (task call-partner, retry [ConnectionError] max_attempts 5, interval_seconds 2, backoff_rate 2) -> Done",
                                   "Done: pass state with result {status: ok} under $.result",
                                   "Validate aws, invoke call-partner"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.sync",
            value={"start_at": "Call",
                   "states": {"Call": {"type": "task", "function": "call-partner", "next": "Done",
                                       "retry": [{"errors": ["ConnectionError"], "max_attempts": 5,
                                                  "interval_seconds": 2, "backoff_rate": 2}]},
                              "Done": {"type": "pass", "result": {"status": "ok"}, "result_path": "$.result", "end": True}}}),
          S("invoke_local", function="call-partner", type="workflow", data={"id": 31}),
      ],
      final="""Done. Workflow `sync`:

```yaml
workflows:
  sync:
    start_at: Call
    states:
      Call:
        type: task
        function: call-partner
        retry: [{errors: [ConnectionError], max_attempts: 5, interval_seconds: 2, backoff_rate: 2}]
        next: Done
      Done: {type: pass, result: {status: ok}, result_path: $.result, end: true}
```

- Waits 2 s, then 4, 8, 16... between tries (`backoff_rate: 2`) [docs/workflows.md#retry-and-catch]. `errors` is the Python exception name your code raises.
- The `pass` state adds `{"status": "ok"}` under `$.result` and keeps the partner data.
- validate (aws): valid. invoke call-partner: `"partner_ref": "P-31"`.

If all 5 tries fail, the run fails; add a `catch` if you want another path. Run: `pskit workflow run sync -i '{"id": 31}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 451
    B(451, provider="gcp", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/events.md#events-backed-by-a-resource", "docs/resources.md#what-handlers-receive"],
      project=dict(files={
          "pskit.yml": """service: audit
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, audit-staging}
functions:
  api:
    handler: app.audit.api
    events:
    - http: POST /actions
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """

def api(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="Define a managed Pub/Sub topic resource `audit-events`. `api` publishes to it later (it should get the binding), and a new function `auditor` should consume it through the resource, not by repeating the topic name. auditor logs each action and returns the count.",
      steps=[
          S("get_project"),
          S("search_docs", query="event uses resource topic binding",
            docs=[D("docs/events.md", "events-backed-by-a-resource", end="The event uses the resource's native name")]),
          S("propose_plan", steps=["resources.audit-events: {type: topic} (bound to all user functions by default, incl. api)",
                                   "Add `auditor` to app/audit.py; function auditor with `- topic: {resource: audit-events}`",
                                   "Validate for gcp (staging), invoke auditor with two messages"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.audit-events", value={"type": "topic"}),
          S("write_file", path="app/audit.py", content=FUTURE + """

def api(event, ctx):
    return {"ok": True}


def auditor(event, ctx):
    for record in event.records:
        action = record.json(default={}) or {}
        ctx.logger.info("audit", extra={"action": action.get("action"), "user": action.get("user")})
    return {"count": len(event.records)}
"""),
          S("set_config", path="functions.auditor",
            value={"handler": "app.audit.auditor", "events": [{"topic": {"resource": "audit-events"}}]}),
          S("invoke_local", function="auditor", type="topic",
            data=[{"action": "login", "user": "u1"}, {"action": "delete", "user": "u2"}]),
      ],
      final="""Added:

```yaml
resources:
  audit-events:
    type: topic
functions:
  auditor:
    handler: app.audit.auditor
    events:
      - topic: {resource: audit-events}
```

- The event uses the resource's native name, so the topic name lives in one place [docs/events.md#events-backed-by-a-resource].
- Without `functions:`, every function you wrote gets the binding, so `api` gets it. On GCP the binding also carries `ID` (the Pub/Sub topic id) for publishing [docs/resources.md#what-handlers-receive].
- validate (gcp, staging): valid.
- invoke auditor with 2 messages: `{"count": 2}` and one log line each.

Publish from `api` with `google-cloud-pubsub` and `resource("audit-events").id`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 452
    B(452, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: payroll
provider:
  name: azure
  region: westeurope
functions:
  calc-salary:
    handler: app.payroll.calc
    events:
    - http: POST /salary
""",
          "app/__init__.py": "",
          "app/payroll.py": FUTURE + """

def calc(event, ctx):
    return {"net": 0}
""",
          "requirements.txt": ""}),
      user="finance team want see costs. put tag team=payroll and cost-center=cc-4410 on calc-salary, and description 'calculates net salary'",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.calc-salary.tags = {team: payroll, cost-center: cc-4410}",
                                   "functions.calc-salary.description = \"calculates net salary\"",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.calc-salary.tags", value={"team": "payroll", "cost-center": "cc-4410"}),
          S("set_config", path="functions.calc-salary.description", value="calculates net salary"),
      ],
      final="""Done:

```yaml
functions:
  calc-salary:
    description: calculates net salary
    tags:
      team: payroll
      cost-center: cc-4410
```

- `pskit validate` (azure): valid after both changes.
- Function tags are merged over the provider tags, and pskit adds `pskit-service`, `pskit-stage` and `managed-by` itself [docs/configuration.md#functions].

On Azure all functions share one Function App, so the cost shows per app. For tags on everything, put them under `provider.tags`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 453
    B(453, provider="aws", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: status-page
provider:
  name: aws
  region: eu-west-3
functions: {}
""",
          "requirements.txt": ""}),
      user="can i have a simple web page at /status that says all systems ok in green? a real page, not json",
      steps=[
          S("get_project"),
          S("search_docs", query="return html response",
            docs=[D("docs/handlers.md", "returning-a-response", words=180)]),
          S("propose_plan", steps=["Write `app/status.py` that returns an HTML page with Response.html",
                                   "Add function `status` on GET /status",
                                   "Validate for aws (staging) and open it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/status.py", content=FUTURE + """from py_serverless_kit import Response

PAGE = \"\"\"<!doctype html>
<html><head><title>Status</title></head>
<body style="font-family: sans-serif">
  <h1 style="color: green">All systems OK</h1>
</body></html>\"\"\"


def status(event, ctx):
    return Response.html(PAGE)
"""),
          S("set_config", path="functions.status",
            value={"handler": "app.status.status", "events": [{"http": "GET /status"}]}),
          S("invoke_local", function="status", method="GET", path="/status"),
      ],
      final="""Yes. `status` on `/status` returns a real HTML page with a green "All systems OK" heading. `Response.html(...)` sends it as `text/html` instead of JSON [docs/handlers.md#returning-a-response].

- `pskit validate` (aws, staging): valid.
- Local test: status 200, HTML body.

Try it on **Test** > **▶ Run locally**, or `pskit invoke -f status --method GET --path /status`. Put it online with **Deploy** or `pskit deploy -s staging`; `pskit info` shows the address to open in your browser."""),

    # ------------------------------------------------------------------ 454
    B(454, provider="gcp", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/providers.md", "docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=dict(files={
          "pskit.yml": """service: exporter
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, exporter-prod}
functions:
  export-csv:
    handler: app.export.run
    timeout: 60
    events:
    - http: POST /export
""",
          "app/__init__.py": "",
          "app/export.py": FUTURE + """

def run(event, ctx):
    return {"rows": 0}
""",
          "requirements.txt": ""}),
      user="""Function execution took 60002 ms, finished with status: 'timeout'
big exports need maybe 15 minutes. raise it""",
      steps=[
          S("get_project"),
          S("search_docs", query="gcp max timeout http event functions",
            docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| [`gcp`]")]),
          S("propose_plan", steps=["Raise functions.export-csv.timeout from 60 to 900 (HTTP functions on GCP allow up to 3600 s)",
                                   "Validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.export-csv.timeout", value=900),
      ],
      final="""It stopped at its 60 s `timeout`. I raised it to 15 minutes:

```yaml
functions:
  export-csv:
    timeout: 900
```

- GCP allows up to 3600 s for HTTP functions; only event-triggered ones are capped at 540 s [docs/providers.md]. `export-csv` is HTTP only, so 900 is fine.
- `pskit validate` (gcp, prod): valid.

If you later add a queue or schedule trigger to it, that event deployment is held to 540 s [docs/events.md#gcp-multi-trigger-functions-are-split-automatically]. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 455
    B(455, provider="azure", stage="staging", mode="auto", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: hr-offboarding
provider:
  name: azure
  region: westeurope
functions:
  revoke-access:
    handler: app.offboard.revoke
  archive-mailbox:
    handler: app.offboard.archive
""",
          "app/__init__.py": "",
          "app/offboard.py": FUTURE + """

def revoke(event, ctx):
    return {**(event.data or {}), "access": "revoked"}


def archive(event, ctx):
    return {**(event.data or {}), "mailbox": "archived"}
""",
          "requirements.txt": ""}),
      user="Workflow `offboard`: revoke-access then archive-mailbox. This is sensitive HR data, so it must NOT get a public HTTP route; we start it from an internal tool. Give the whole run a 300 second limit.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add workflow `offboard` (embedded on Azure): Revoke (revoke-access) -> Archive (archive-mailbox, end)",
                                   "options.http: false (no orchestrator HTTP route), timeout: 300",
                                   "Validate azure (staging), invoke revoke-access"]),
          S("set_config", path="workflows.offboard",
            value={"timeout": 300, "options": {"http": False}, "start_at": "Revoke",
                   "states": {"Revoke": {"type": "task", "function": "revoke-access", "next": "Archive"},
                              "Archive": {"type": "task", "function": "archive-mailbox", "end": True}}}),
          S("invoke_local", function="revoke-access", type="workflow", data={"employee": "e-301"}),
      ],
      final="""Added:

```yaml
workflows:
  offboard:
    timeout: 300
    options: {http: false}
    start_at: Revoke
    states:
      Revoke:  {type: task, function: revoke-access, next: Archive}
      Archive: {type: task, function: archive-mailbox, end: true}
```

- On Azure it runs on the embedded engine in `offboard-orchestrator`. `options.http: false` removes its `POST /workflows/offboard` route, which would otherwise be public [docs/workflows.md#embedded-orchestrator].
- `timeout: 300` sets the orchestrator's timeout, and the engine ends the run `TIMED_OUT` after it [docs/workflows.md#workflow-keys].
- validate (azure, staging): valid, with the embedded-engine warning that one run is capped by the function timeout (600 s max on Azure); 300 s is within that.
- invoke revoke-access: `"access": "revoked"`.

Your internal tool must call the orchestrator directly (without its HTTP route). Local test: `pskit workflow run offboard -i '{"employee": "e-301"}'`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 456
    B(456, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: checkout
provider:
  name: aws
  region: us-east-1
functions:
  checkout:
    handler: app.checkout.checkout
    events:
    - http: POST /checkout
  billing:
    handler: app.checkout.billing
""",
          "app/__init__.py": "",
          "app/checkout.py": FUTURE + """import json

import boto3


def checkout(event, ctx):
    order = event.http.json(default={}) or {}
    resp = boto3.client("lambda").invoke(FunctionName="checkout-dev-billing", Payload=json.dumps(order))
    return json.loads(resp["Payload"].read())


def billing(event, ctx):
    order = dict(event.data or {})
    return {"billed": order.get("total", 0)}
""",
          "requirements.txt": ""}),
      user="checkout still calls billing with boto3 lambda invoke and the hardcoded function name. Replace that with the pskit way and give it the permission it needs.",
      steps=[
          S("get_project"),
          S("search_docs", query="invoke another function lambda:InvokeFunction",
            docs=[D("docs/handlers.md", "invoke-calling-another-function")]),
          S("propose_plan", steps=["Rewrite checkout to `invoke(\"billing\", order)` (no boto3 client, no hardcoded name)",
                                   "Add functions.checkout.iam.statements: lambda:InvokeFunction; add boto3 to requirements.txt",
                                   "Validate for aws, invoke checkout locally (billing runs in-process)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/checkout.py", content=FUTURE + """from py_serverless_kit import invoke


def checkout(event, ctx):
    order = event.http.json(default={}) or {}
    return invoke("billing", order)


def billing(event, ctx):
    order = dict(event.data or {})
    return {"billed": order.get("total", 0)}
"""),
          S("write_file", path="requirements.txt", content="boto3\n"),
          S("set_config", path="functions.checkout.iam",
            value={"statements": [{"actions": ["lambda:InvokeFunction"], "resources": ["*"]}]}),
          S("invoke_local", function="checkout", method="POST", path="/checkout", data={"total": 49.9}),
      ],
      final="""Replaced:

```python
from py_serverless_kit import invoke

def checkout(event, ctx):
    order = event.http.json(default={}) or {}
    return invoke("billing", order)
```

- `invoke("billing", ...)` uses the logical name, so no `<service>-<stage>-` name is hardcoded. On AWS it calls `lambda:InvokeFunction` via boto3, so I added `boto3` to requirements.txt and this statement [docs/handlers.md#invoke-calling-another-function]:

```yaml
functions:
  checkout:
    iam:
      statements:
        - {actions: ["lambda:InvokeFunction"], resources: ["*"]}
```

- validate (aws): valid.
- Local POST `{"total": 49.9}`: `{"billed": 49.9}`. Locally, `invoke()` runs billing in-process.

You can narrow `resources` to the billing function's ARN after the first deploy (`pskit info`). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 457
    B(457, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: unit-converter
provider:
  name: gcp
  region: us-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, unit-converter-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="new project for school: send a temperature in celsius and get it back in fahrenheit",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/convert.py`: read {celsius} from the JSON body, answer {fahrenheit}; 400 if it's not a number",
                                   "Add function `to-fahrenheit` on POST /convert",
                                   "Validate for gcp and try 100 °C locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/convert.py", content=FUTURE + """from py_serverless_kit import BadRequest


def to_fahrenheit(event, ctx):
    body = event.http.json(default={}) or {}
    celsius = body.get("celsius")
    if not isinstance(celsius, (int, float)):
        raise BadRequest("send a number, e.g. {\\"celsius\\": 20}")
    return {"celsius": celsius, "fahrenheit": round(celsius * 9 / 5 + 32, 1)}
"""),
          S("set_config", path="functions.to-fahrenheit",
            value={"handler": "app.convert.to_fahrenheit", "events": [{"http": "POST /convert"}]}),
          S("invoke_local", function="to-fahrenheit", method="POST", path="/convert", data={"celsius": 100}),
      ],
      final="""Your converter is ready: function `to-fahrenheit` on `POST /convert`.

- Send `{"celsius": 100}` and you get `{"celsius": 100, "fahrenheit": 212.0}`. That's the local test result.
- If the value is not a number, it answers 400 with a short hint [docs/handlers.md#errors].
- `pskit validate` (gcp): valid.

Try other values on **Test** > **▶ Run locally** (edit the Payload), or `pskit invoke -f to-fahrenheit -d '{"celsius": 37}'`. To put it online: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 458
    B(458, provider="azure", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: fulfilment
provider:
  name: azure
  region: westeurope
functions:
  ship:
    handler: app.ship.handle
""",
          "app/__init__.py": "",
          "app/ship.py": FUTURE + """

def handle(event, ctx):
    return {"shipments": [(r.json(default={}) or {}).get("order_id") for r in event.records]}
""",
          "requirements.txt": ""}),
      user="`ship` must subscribe to the existing Service Bus topic `orders-paid` in the shared namespace /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/messaging-rg/providers/Microsoft.ServiceBus/namespaces/corp-bus. Its connection string will be in the app setting SB_CONNECTION. pskit must not create the topic.",
      steps=[
          S("get_project"),
          S("search_docs", query="azure existing service bus topic namespace connection",
            docs=[D("docs/events.md", "topic", start="| azure |", end="| azure |")]),
          S("propose_plan", steps=["provider.options.servicebus_namespace_id = the corp-bus id; provider.options.servicebus_connection = SB_CONNECTION",
                                   "functions.ship.events = [topic {name: orders-paid, existing: true}]",
                                   "Validate for azure (prod), invoke one message"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options",
            value={"servicebus_namespace_id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/messaging-rg/providers/Microsoft.ServiceBus/namespaces/corp-bus",
                   "servicebus_connection": "SB_CONNECTION"}),
          S("set_config", path="functions.ship.events", value=[{"topic": {"name": "orders-paid", "existing": True}}]),
          S("invoke_local", function="ship", type="topic", data=[{"order_id": "o-881"}]),
      ],
      final="""Subscribed to the shared topic:

```yaml
provider:
  options:
    servicebus_namespace_id: /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/messaging-rg/providers/Microsoft.ServiceBus/namespaces/corp-bus
    servicebus_connection: SB_CONNECTION
functions:
  ship:
    events:
      - topic: {name: orders-paid, existing: true}
```

- An `existing` topic on Azure needs both `servicebus_namespace_id` and `servicebus_connection` [docs/events.md#topic]. pskit adds only a subscription for `ship`.
- `pskit validate` (azure, prod): valid.
- invoke: `{"shipments": ["o-881"]}`.

Make sure the `SB_CONNECTION` app setting exists on the Function App. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 459
    B(459, provider="aws", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: media-index
provider:
  name: aws
  region: eu-central-1
functions: {}
""",
          "requirements.txt": ""}),
      user="new bucket media-originals-0099 (pskit create it). when file add or delete under raw/ , update index. index part later, now just say added or removed",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/index.py`: for each record, report added/removed from record.action",
                                   "Add function `index-media` with storage {bucket: media-originals-0099, events: [created, deleted], prefix: raw/}",
                                   "Validate for aws (staging), invoke a create and a delete"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/index.py", content=FUTURE + """

def index_media(event, ctx):
    changes = []
    for record in event.records:
        verb = "removed" if record.action == "deleted" else "added"
        changes.append(f"{verb} {record.key}")
    return {"changes": changes}
"""),
          S("set_config", path="functions.index-media",
            value={"handler": "app.index.index_media",
                   "events": [{"storage": {"bucket": "media-originals-0099", "events": ["created", "deleted"], "prefix": "raw/"}}]}),
          S("invoke_local", function="index-media", type="storage", data={"bucket": "media-originals-0099", "key": "raw/clip.mp4"}),
          S("invoke_local", function="index-media", type="storage",
            data={"bucket": "media-originals-0099", "key": "raw/old.mp4", "action": "deleted"}),
      ],
      final="""Done:

```yaml
functions:
  index-media:
    handler: app.index.index_media
    events:
      - storage:
          bucket: media-originals-0099
          events: [created, deleted]
          prefix: raw/
```

- pskit creates the S3 bucket (public access blocked) with a notification for both events [docs/events.md#storage].
- validate (aws, staging): valid.
- invoke: create → `{"changes": ["added raw/clip.mp4"]}`, delete → `{"changes": ["removed raw/old.mp4"]}`.

Retest: `pskit invoke -f index-media -t storage -d '{"bucket": "media-originals-0099", "key": "raw/a.mp4"}'`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 460
    B(460, provider="gcp", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#gcp-multi-trigger-functions-are-split-automatically", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: rates
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, rates-staging}
functions:
  fx:
    handler: app.fx.handle
    events:
    - http: GET /fx
""",
          "app/__init__.py": "",
          "app/fx.py": FUTURE + """

def handle(event, ctx):
    if event.type == "schedule":
        return {"refreshed": True}
    return {"eur_usd": 1.08}
""",
          "requirements.txt": ""}),
      user="fx: also refresh every 10 min via scheduler, same function",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["fx.events += schedule: 10 minutes", "Validate gcp (staging), invoke schedule + http"]),
          S("set_config", path="functions.fx.events", value=[{"http": "GET /fx"}, {"schedule": "10 minutes"}]),
          S("invoke_local", function="fx", type="schedule"),
          S("invoke_local", function="fx", method="GET", path="/fx"),
      ],
      final="""```yaml
functions:
  fx:
    events:
      - http: GET /fx
      - schedule: 10 minutes
```

- validate (gcp, staging): valid. Cloud Scheduler gets `*/10 * * * *` and sends an OIDC POST to the HTTP deployment `fx`, since there's no Pub/Sub trigger [docs/events.md#gcp-multi-trigger-functions-are-split-automatically].
- invoke schedule: `{"refreshed": true}`; GET /fx: 200 `{"eur_usd": 1.08}`.

Deploy: **Deploy** or `pskit deploy -s staging`."""),
]
