"""Category B (build / add), batch 27 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 521
    B(521, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: tracker
provider:
  name: aws
  region: us-east-1
functions: {}
""",
          "requirements.txt": ""}),
      user="I want a tiny invisible image I can put in emails, so I know when someone opened it. Can my function return an image?",
      steps=[
          S("get_project"),
          S("search_docs", query="return binary image response",
            docs=[D("docs/handlers.md", "returning-a-response", start="```python", end="Response.binary")]),
          S("propose_plan", steps=["Write `app/pixel.py`: log the open, return a 1x1 transparent GIF with Response.binary",
                                   "Add function `pixel` on GET /open/{campaign}",
                                   "Validate for aws and open it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/pixel.py", content=FUTURE + """import base64

from py_serverless_kit import Response

GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def pixel(event, ctx):
    ctx.logger.info("email opened", extra={"campaign": event.http.path_params["campaign"]})
    return Response.binary(GIF, "image/gif")
"""),
          S("set_config", path="functions.pixel", value={"handler": "app.pixel.pixel", "events": [{"http": "GET /open/{campaign}"}]}),
          S("invoke_local", function="pixel", method="GET", path="/open/november-news"),
      ],
      final="""Yes. `pixel` on `GET /open/{campaign}` returns a 1x1 transparent GIF and writes an `email opened` log line with the campaign name.

- `Response.binary(data, "image/gif")` sends bytes; pskit base64-encodes them for the API gateway automatically [docs/handlers.md#returning-a-response].
- `pskit validate` (aws): valid.
- Local test: 200 with `content-type: image/gif` (the body is shown base64-encoded).

After deploy (**Deploy** page or `pskit deploy -s dev`), put `<img src="<your address>/open/november-news">` in the email; `pskit info` shows the address. The opens appear on the **Logs** page. Many mail apps block images by default, so the count is a lower bound."""),

    # ------------------------------------------------------------------ 522
    B(522, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: partner-portal
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, partner-portal-staging}
functions: {}
""",
          "requirements.txt": ""}),
      user="Add GET /reports for partners. They log in with our OIDC provider and send a JWT bearer token; use auth: jwt with issuer https://login.example.com/ like on AWS.",
      steps=[
          S("get_project"),
          S("search_docs", query="jwt auth gcp supported",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", question="`auth: jwt` is AWS-only; validate rejects it on GCP. Which do you want?",
            options=["auth: none, and the handler rejects requests without a bearer token (verify it later with a JWT library)",
                     "auth: iam (callers need Google identities)"],
            answer="auth: none, and the handler rejects requests without a bearer token (verify it later with a JWT library)"),
          S("propose_plan", steps=["Write `app/reports.py`: 401 when the Authorization header isn't `Bearer <token>`",
                                   "Add function `reports` on GET /reports (auth none)",
                                   "Validate for gcp (staging), invoke without a token (expect 401)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/reports.py", content=FUTURE + """from py_serverless_kit import Unauthorized


def reports(event, ctx):
    auth = event.http.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise Unauthorized("missing bearer token")
    # TODO: verify the token's signature, issuer https://login.example.com/ and audience with a JWT library
    return {"reports": []}
"""),
          S("set_config", path="functions.reports", value={"handler": "app.reports.reports", "events": [{"http": "GET /reports"}]}),
          S("invoke_local", function="reports", method="GET", path="/reports"),
      ],
      final="""On GCP, `auth: jwt` isn't available; only AWS has it [docs/events.md#http]. As you chose, the route is public and the handler checks the token:

- `reports` on `GET /reports` answers 401 without `Authorization: Bearer ...`.
- `pskit validate` (gcp, staging): valid.
- Local call without a token: **401** `missing bearer token`.

Important: right now it only checks that a token is present. Before partners use it, verify the signature, issuer and audience in the TODO (for example with `PyJWT`, added to requirements.txt). Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 523
    B(523, provider="azure", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#events-triggers"],
      project=dict(files={
          "pskit.yml": """service: search-index
provider:
  name: azure
  region: westeurope
functions:
  reindex:
    handler: app.index.reindex
""",
          "app/__init__.py": "",
          "app/index.py": FUTURE + """

def reindex(event, ctx):
    return {"reindexed": True, "trigger": event.type}
""",
          "requirements.txt": ""}),
      user="reindex: nightly 03:00 UTC + manual POST /reindex",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["reindex.events = [schedule \"0 3 * * *\", http POST /reindex]", "Validate azure, invoke both"]),
          S("set_config", path="functions.reindex.events", value=[{"schedule": "0 3 * * *"}, {"http": "POST /reindex"}]),
          S("invoke_local", function="reindex", type="schedule"),
          S("invoke_local", function="reindex", type="http", method="POST", path="/reindex"),
      ],
      final="""```yaml
functions:
  reindex:
    events:
      - schedule: "0 3 * * *"
      - http: POST /reindex
```

- validate (azure): valid. One function can have several triggers [docs/events.md#events-triggers]; Azure timers are UTC, so 03:00 is exact.
- invoke: schedule → `"trigger": "schedule"`; POST → 200 `"trigger": "http"`.

Consider `auth: key` on the POST so only you can trigger it. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 524
    B(524, provider="aws", stage="staging", mode="auto", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#what-handlers-receive", "docs/events.md#events-backed-by-a-resource"],
      project=dict(files={
          "pskit.yml": """service: returns
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="The SQS queue `returns-inbound` exists in this account (created by the warehouse team's Terraform). Register it as an external resource by name only, and add a consumer `handle-return` through the resource, batch size 5.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.returns-inbound: {type: queue, external: true} (name = key)",
                                   "Write app/returns.py; function handle-return with queue {resource: returns-inbound, batch_size: 5}",
                                   "Validate aws (staging), invoke two messages"]),
          S("set_config", path="resources.returns-inbound", value={"type": "queue", "external": True}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/returns.py", content=FUTURE + """

def handle_return(event, ctx):
    rmas = [(r.json(default={}) or {}).get("rma") for r in event.records]
    return {"returns": rmas}
"""),
          S("set_config", path="functions.handle-return",
            value={"handler": "app.returns.handle_return", "events": [{"queue": {"resource": "returns-inbound", "batch_size": 5}}]}),
          S("invoke_local", function="handle-return", type="queue", data=[{"rma": "R-1"}, {"rma": "R-2"}]),
      ],
      final="""```yaml
resources:
  returns-inbound:
    type: queue
    external: true
functions:
  handle-return:
    handler: app.returns.handle_return
    events:
      - queue: {resource: returns-inbound, batch_size: 5}
```

- Without `name`, the native name is the key. On AWS, external resources bound by name are looked up with a Terraform data source, so the queue must exist at deploy time [docs/resources.md#what-handlers-receive].
- The event becomes `name: returns-inbound` + `existing: true`; pskit only adds the event source mapping.
- validate (aws, staging): valid. invoke: `{"returns": ["R-1", "R-2"]}`.

Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 525
    B(525, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: price-compare
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, price-compare-dev}
functions:
  supplier-a:
    handler: app.prices.supplier_a
  supplier-b:
    handler: app.prices.supplier_b
  pick-cheapest:
    handler: app.prices.pick
""",
          "app/__init__.py": "",
          "app/prices.py": FUTURE + """

def supplier_a(event, ctx):
    return {"supplier": "a", "price": 12.0}


def supplier_b(event, ctx):
    return {"supplier": "b", "price": 9.5}


def pick(event, ctx):
    offers = event.data or []
    return min(offers, key=lambda o: o["price"])
""",
          "requirements.txt": ""}),
      user="ask supplier-a and supplier-b price same time, then pick-cheapest get both answers",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add workflow `best-price`: Ask (parallel: branch supplier-a, branch supplier-b) -> Pick (pick-cheapest, end)",
                                   "The parallel result is a list with one item per branch, which pick-cheapest receives",
                                   "Validate for gcp, run pick-cheapest locally with two offers"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.best-price",
            value={"start_at": "Ask",
                   "states": {"Ask": {"type": "parallel", "next": "Pick", "branches": [
                       {"start_at": "A", "states": {"A": {"type": "task", "function": "supplier-a", "end": True}}},
                       {"start_at": "B", "states": {"B": {"type": "task", "function": "supplier-b", "end": True}}}]},
                              "Pick": {"type": "task", "function": "pick-cheapest", "end": True}}}),
          S("invoke_local", function="pick-cheapest", type="workflow",
            data=[{"supplier": "a", "price": 12.0}, {"supplier": "b", "price": 9.5}]),
      ],
      final="""Done. Workflow `best-price`:

```yaml
workflows:
  best-price:
    start_at: Ask
    states:
      Ask:
        type: parallel
        next: Pick
        branches:
          - {start_at: A, states: {A: {type: task, function: supplier-a, end: true}}}
          - {start_at: B, states: {B: {type: task, function: supplier-b, end: true}}}
      Pick: {type: task, function: pick-cheapest, end: true}
```

- Both suppliers are asked at the same time; the `parallel` result is a list (one item per branch) that goes to `pick-cheapest` [docs/workflows.md#state-types].
- validate (gcp): valid (Cloud Workflows).
- pick-cheapest with both offers: `{"supplier": "b", "price": 9.5}`.

Run all: `pskit workflow run best-price -i '{}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 526
    B(526, provider="azure", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#azure-one-function-app-per-service"],
      project=dict(files={
          "pskit.yml": """service: back-office
provider:
  name: azure
  region: westeurope
functions:
  orders:
    handler: app.office.orders
    events:
    - http: GET /orders
  billing:
    handler: app.office.billing
    events:
    - http: GET /billing
""",
          "app/__init__.py": "",
          "app/office.py": FUTURE + """

def orders(event, ctx):
    return {"db": ctx.env.get("ORDERS_DB")}


def billing(event, ctx):
    return {"db": ctx.env.get("BILLING_DB")}
""",
          "requirements.txt": ""}),
      user="On Lambda each function had its own DB_NAME env var: orders -> orders_db, billing -> billing_db. How do I do that on Azure?",
      steps=[
          S("get_project"),
          S("search_docs", query="azure environment app-wide conflicting values",
            docs=[D("docs/events.md", "azure-one-function-app-per-service")]),
          S("propose_plan", steps=["On Azure all functions share one Function App, so one DB_NAME with two values would conflict",
                                   "Use distinct names (the handlers already read them): orders.environment.ORDERS_DB = orders_db, billing.environment.BILLING_DB = billing_db",
                                   "Validate for azure (prod), invoke both"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.orders.environment", value={"ORDERS_DB": "orders_db"}),
          S("set_config", path="functions.billing.environment", value={"BILLING_DB": "billing_db"}),
          S("invoke_local", function="orders", method="GET", path="/orders"),
          S("invoke_local", function="billing", method="GET", path="/billing"),
      ],
      final="""On Azure, `environment` is app-wide: every function of the service runs in one Function App, and pskit warns when two functions set the same key to different values [docs/events.md#azure-one-function-app-per-service]. So I used one name per function (your handlers already read these):

```yaml
functions:
  orders:
    environment: {ORDERS_DB: orders_db}
  billing:
    environment: {BILLING_DB: billing_db}
```

- `pskit validate` (azure, prod): valid, no conflict warning.
- invoke: orders → `{"db": "orders_db"}`, billing → `{"db": "billing_db"}`.

Both functions will see both variables on Azure; that's harmless here. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 527
    B(527, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: backfill
provider:
  name: aws
  region: eu-west-1
functions:
  backfill:
    handler: app.backfill.run
    timeout: 300
    events:
    - schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/backfill.py": FUTURE + """

def run(event, ctx):
    done = 0
    for _ in range(1000):
        done += 1
    return {"done": done}
""",
          "requirements.txt": ""}),
      user="backfill sometimes killed by timeout in the middle. can it stop by itself when little time left and say how far it got?",
      steps=[
          S("get_project"),
          S("search_docs", query="remaining time context",
            docs=[D("docs/handlers.md", "context")]),
          S("propose_plan", steps=["In the loop, check ctx.remaining_time_ms(); stop when under 10 s (it can be None locally)",
                                   "Return how many items were done and whether it stopped early",
                                   "Validate for aws, run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/backfill.py", content=FUTURE + """
SAFETY_MS = 10000


def run(event, ctx):
    done = 0
    stopped_early = False
    for _ in range(1000):
        left = ctx.remaining_time_ms()
        if left is not None and left < SAFETY_MS:
            stopped_early = True
            break
        done += 1
    ctx.logger.info("backfill progress", extra={"done": done, "stopped_early": stopped_early})
    return {"done": done, "stopped_early": stopped_early}
"""),
          S("validate"),
          S("invoke_local", function="backfill", type="schedule"),
      ],
      final="""Yes. The loop now asks `ctx.remaining_time_ms()` before each item and stops when less than 10 seconds are left [docs/handlers.md#context]. It returns how far it got:

- `pskit validate` (aws): valid.
- Local run: `{"done": 1000, "stopped_early": false}` (no time pressure locally).

Next step: save the position (for example in a table) so the next hourly run continues from there. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 528
    B(528, provider="gcp", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule", "docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: team-bot
provider:
  name: gcp
  region: europe-west2
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, team-bot-prod}
functions: {}
""",
          "requirements.txt": ""}),
      user="every friday at 5pm london time I want my team to get a 'have a nice weekend' message in our chat. the chat webhook address is secret",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/weekend.py`: build the message and post it to the webhook from CHAT_WEBHOOK_URL (skip the post when it isn't set)",
                                   "Add function `weekend-message` with schedule {cron: \"0 17 * * 5\", timezone: Europe/London} and environment CHAT_WEBHOOK_URL: ${env:CHAT_WEBHOOK_URL, \"\"}",
                                   "Validate for gcp (prod) and run it once locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/weekend.py", content=FUTURE + """import json
import urllib.request

MESSAGE = "Have a nice weekend, everyone!"


def weekend_message(event, ctx):
    url = ctx.env.get("CHAT_WEBHOOK_URL", "")
    if not url:
        ctx.logger.warning("CHAT_WEBHOOK_URL is not set, message not sent")
        return {"sent": False, "message": MESSAGE}
    req = urllib.request.Request(url, data=json.dumps({"text": MESSAGE}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)
    return {"sent": True, "message": MESSAGE}
"""),
          S("set_config", path="functions.weekend-message",
            value={"handler": "app.weekend.weekend_message",
                   "environment": {"CHAT_WEBHOOK_URL": "${env:CHAT_WEBHOOK_URL, \"\"}"},
                   "events": [{"schedule": {"cron": "0 17 * * 5", "timezone": "Europe/London"}}]}),
          S("invoke_local", function="weekend-message", type="schedule"),
      ],
      final="""Done. `weekend-message` runs every Friday at 17:00 London time and posts "Have a nice weekend, everyone!" to your chat.

- The webhook address isn't in pskit.yml: it comes from the environment variable `CHAT_WEBHOOK_URL` when you deploy [docs/configuration.md#variables].
- GCP Cloud Scheduler honours `timezone`, so summer time is handled [docs/events.md#schedule].
- `pskit validate` (gcp, prod): valid.
- Local run: `{"sent": false, ...}` with a warning, because the variable isn't set here. That's the safe behaviour.

Before deploying, set `CHAT_WEBHOOK_URL` (for example **Setup & credentials** > Environment variables > **Set for this session**), then **Deploy** (typed confirmation for prod) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 529
    B(529, provider="azure", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#compiler-notes-and-limits", "docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: access-requests
provider:
  name: azure
  region: westeurope
functions:
  grant-internal:
    handler: app.access.internal
  request-approval:
    handler: app.access.approval
""",
          "app/__init__.py": "",
          "app/access.py": FUTURE + """

def internal(event, ctx):
    return {**(event.data or {}), "granted": True}


def approval(event, ctx):
    return {**(event.data or {}), "approval": "requested"}
""",
          "requirements.txt": ""}),
      user="Logic App `access`: if $.email matches *@example.com grant-internal directly, otherwise request-approval. Is glob matching supported on Logic Apps?",
      steps=[
          S("get_project"),
          S("search_docs", query="logic apps matches glob",
            docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="- **Azure (Logic Apps):**", words=170)]),
          S("propose_plan", steps=["Add workflow `access` with engine: native: Route (choice $.email matches \"*@example.com\" -> Grant, default Approval)",
                                   "Grant: grant-internal, end; Approval: request-approval, end",
                                   "Validate for azure (staging), run grant-internal locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.access",
            value={"engine": "native", "start_at": "Route",
                   "states": {"Route": {"type": "choice",
                                        "choices": [{"variable": "$.email", "matches": "*@example.com", "next": "Grant"}],
                                        "default": "Approval"},
                              "Grant": {"type": "task", "function": "grant-internal", "end": True},
                              "Approval": {"type": "task", "function": "request-approval", "end": True}}}),
          S("invoke_local", function="grant-internal", type="workflow", data={"email": "kim@example.com"}),
      ],
      final="""Yes, in a limited form: on Logic Apps `matches` accepts `abc`, `abc*`, `*abc`, `*abc*` and `*`; other globs are a validation error [docs/workflows.md#compiler-notes-and-limits]. `*@example.com` is the `*abc` form, so it works:

```yaml
workflows:
  access:
    engine: native
    start_at: Route
    states:
      Route:
        type: choice
        choices: [{variable: $.email, matches: "*@example.com", next: Grant}]
        default: Approval
      Grant:    {type: task, function: grant-internal, end: true}
      Approval: {type: task, function: request-approval, end: true}
```

- `pskit validate` (azure, staging): valid.
- `grant-internal` locally: `"granted": true`.

Deploy: **Deploy** or `pskit deploy -s staging`; `pskit info` shows the Logic App trigger URL (treat it as a secret)."""),

    # ------------------------------------------------------------------ 530
    B(530, provider="aws", stage="prod", mode="ask", page="Overview", persona="terse_expert",
      sources=["docs/configuration.md#provider", "docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: edge-api
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.api.handler
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def handler(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="whole service on graviton (arm64), pin python3.12",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.architecture = arm64", "provider.runtime = python3.12", "Validate aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.architecture", value="arm64"),
          S("set_config", path="provider.runtime", value="python3.12"),
      ],
      final="""```yaml
provider:
  architecture: arm64
  runtime: python3.12
```

validate (aws, prod) passed after both. `architecture` is used by Lambda and for pip wheel selection, so dependencies are installed as arm64 wheels [docs/providers.md#aws-aws-lambda]. Check that every package in requirements.txt has arm64 wheels. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 531
    B(531, provider="gcp", stage="staging", mode="auto", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: account-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, account-api-staging}
functions:
  me:
    handler: app.me.me
    events:
    - http: GET /me
""",
          "app/__init__.py": "",
          "app/me.py": FUTURE + """

def me(event, ctx):
    return {"user": "anonymous"}
""",
          "requirements.txt": ""}),
      user="SAM HttpApi CorsConfiguration had AllowOrigins [https://app.example.com, https://admin.example.com], AllowCredentials true, MaxAge 600. same on /me",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["me event -> long form with cors {origins: [app, admin], allow_credentials: true, max_age: 600}",
                                   "Validate gcp (staging), invoke"]),
          S("set_config", path="functions.me.events.0",
            value={"http": {"path": "/me", "method": "GET",
                            "cors": {"origins": ["https://app.example.com", "https://admin.example.com"],
                                     "allow_credentials": True, "max_age": 600}}}),
          S("invoke_local", function="me", method="GET", path="/me"),
      ],
      final="""```yaml
functions:
  me:
    events:
      - http:
          path: /me
          method: GET
          cors:
            origins: ["https://app.example.com", "https://admin.example.com"]
            allow_credentials: true
            max_age: 600
```

- `AllowOrigins` → `origins`, `AllowCredentials` → `allow_credentials`, `MaxAge` → `max_age` [docs/events.md#http]. On GCP the pskit runtime sends the headers and answers preflights (there's no gateway).
- validate (gcp, staging): valid. invoke: 200 `{"user": "anonymous"}`.

Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 532
    B(532, provider="azure", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: greeting
provider:
  name: azure
  region: westeurope
functions:
  hello:
    handler: app.hello.hello
    events:
    - http: GET /hello
""",
          "app/__init__.py": "",
          "app/hello.py": FUTURE + """

def hello(event, ctx):
    return {"message": "Hello there"}
""",
          "requirements.txt": ""}),
      user="my hello page shows {\"message\": ...} with brackets. I just want the plain words to show up",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Return a string instead of a dict in app/hello.py (a str becomes text/plain)",
                                   "Validate for azure and open it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/hello.py", content=FUTURE + """

def hello(event, ctx):
    return "Hello there"
"""),
          S("validate"),
          S("invoke_local", function="hello", method="GET", path="/hello"),
      ],
      final="""Fixed. The function now returns plain text instead of JSON. In pskit a `dict` becomes JSON, and a `str` becomes `text/plain` [docs/handlers.md#returning-a-response].

- `pskit validate` (azure): valid.
- Local test: 200, `text/plain`, body `Hello there`.

Check it on **Test** > **▶ Run locally**. Deploy to see it online: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 533
    B(533, provider="aws", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: sync-jobs
provider:
  name: aws
  region: eu-west-1
functions:
  check-changes:
    handler: app.sync.check
  apply-changes:
    handler: app.sync.apply
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """

def check(event, ctx):
    data = dict(event.data or {})
    return {**data, "changes": data.get("changes", 0)}


def apply(event, ctx):
    return {**(event.data or {}), "applied": True}
""",
          "requirements.txt": ""}),
      user="Workflow `sync`: CheckChanges first. If $.changes equals 0, finish successfully right away (state NothingToDo). Otherwise ApplyChanges.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add workflow `sync`: Check (check-changes) -> HasChanges (choice $.changes equals 0 -> NothingToDo, default Apply)",
                                   "NothingToDo: succeed; Apply: apply-changes, end",
                                   "Validate for aws (staging), run check-changes locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.sync",
            value={"start_at": "Check",
                   "states": {"Check": {"type": "task", "function": "check-changes", "next": "HasChanges"},
                              "HasChanges": {"type": "choice",
                                             "choices": [{"variable": "$.changes", "equals": 0, "next": "NothingToDo"}],
                                             "default": "Apply"},
                              "NothingToDo": {"type": "succeed"},
                              "Apply": {"type": "task", "function": "apply-changes", "end": True}}}),
          S("invoke_local", function="check-changes", type="workflow", data={"changes": 0}),
      ],
      final="""Added:

```yaml
workflows:
  sync:
    start_at: Check
    states:
      Check: {type: task, function: check-changes, next: HasChanges}
      HasChanges:
        type: choice
        choices: [{variable: $.changes, equals: 0, next: NothingToDo}]
        default: Apply
      NothingToDo: {type: succeed}
      Apply: {type: task, function: apply-changes, end: true}
```

- `succeed` ends the run successfully with the current data [docs/workflows.md#state-types].
- `pskit validate` (aws, staging): valid (Step Functions).
- check-changes with 0 changes: `{"changes": 0}`, so that run ends at NothingToDo.

Run it: `pskit workflow run sync -i '{"changes": 3}' --history`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 534
    B(534, provider="gcp", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, shop-dev}
functions:
  products:
    handler: app.shop.products
    events:
    - http: GET /products
  orders:
    handler: app.shop.orders
    events:
    - http: POST /orders
  report:
    handler: app.shop.report
    events:
    - schedule: 0 6 * * *
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + """from py_serverless_kit import resource


def products(event, ctx):
    return {"db": resource("shop-db").get("database")}


def orders(event, ctx):
    return {"db": resource("shop-db").get("database")}, 201


def report(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="we have cloud sql postgres. db shop, user shop_app, host in env SHOP_DB_HOST, password env SHOP_DB_PASSWORD. only products and orders need it, not report",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.shop-db: database, external, connection {host: ${env:SHOP_DB_HOST, db.example.com}, port 5432, database shop, user shop_app, password_env SHOP_DB_PASSWORD}, functions [products, orders]",
                                   "Validate gcp, invoke products"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.shop-db",
            value={"type": "database", "external": True, "functions": ["products", "orders"],
                   "connection": {"host": "${env:SHOP_DB_HOST, db.example.com}", "port": 5432, "database": "shop",
                                  "user": "shop_app", "password_env": "SHOP_DB_PASSWORD"}}),
          S("invoke_local", function="products", method="GET", path="/products"),
      ],
      final="""Done:

```yaml
resources:
  shop-db:
    type: database
    external: true
    connection:
      host: ${env:SHOP_DB_HOST, db.example.com}
      port: 5432
      database: shop
      user: shop_app
      password_env: SHOP_DB_PASSWORD
    functions: [products, orders]
```

- `functions:` limits the binding, so `report` doesn't get it [docs/resources.md#fields]. `password_env` is the variable's name, not the password.
- validate (gcp): valid.
- invoke products: `{"db": "shop"}`.

Set `SHOP_DB_HOST` and `SHOP_DB_PASSWORD` where you deploy, and add a Postgres driver (e.g. `psycopg2-binary`) to requirements.txt. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 535
    B(535, provider="azure", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: audit
provider:
  name: azure
  region: westeurope
functions:
  write-audit:
    handler: app.audit.write
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """

def write(event, ctx):
    return {"written": len(event.records)}
""",
          "requirements.txt": ""}),
      user="write-audit on fifo queue audit-log",
      steps=[
          S("get_project"),
          S("search_docs", query="fifo azure storage queue",
            docs=[D("docs/events.md", "queue", start="| `fifo` |", end="| `fifo` |")]),
          S("propose_plan", steps=["Storage Queues aren't FIFO (fifo is ignored with a warning), so add `- queue: audit-log` without fifo",
                                   "Validate azure (prod), invoke"]),
          S("set_config", path="functions.write-audit.events", value=[{"queue": "audit-log"}]),
          S("invoke_local", function="write-audit", type="queue", data=[{"e": 1}, {"e": 2}]),
      ],
      final="""```yaml
functions:
  write-audit:
    events:
      - queue: audit-log
```

No `fifo`: Azure Storage Queues aren't FIFO, so pskit would ignore it with a warning [docs/events.md#queue]. If order matters, put a sequence number or timestamp in each message and sort in the handler.

- validate (azure, prod): valid. invoke: `{"written": 2}`.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 536
    B(536, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: users-api
provider:
  name: aws
  region: us-east-1
functions:
  users:
    handler: app.users.list_users
    events:
    - http: GET /users
""",
          "app/__init__.py": "",
          "app/users.py": FUTURE + """

def list_users(event, ctx):
    return [{"id": 1}]
""",
          "requirements.txt": ""}),
      user="""GET https://abc.execute-api.us-east-1.amazonaws.com/api/users -> {"message":"Not Found"}
our frontend always calls /api/..., change it""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["The route is GET /users, so /api/users has no route. Change it to GET /api/users",
                                   "Validate for aws, invoke /api/users"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.users.events", value=[{"http": "GET /api/users"}]),
          S("invoke_local", function="users", method="GET", path="/api/users"),
      ],
      final="""The API only had `GET /users`, so `/api/users` matched nothing and API Gateway answered `Not Found`. Now the route is:

```yaml
functions:
  users:
    events:
      - http: GET /api/users
```

- `pskit validate` (aws): valid.
- invoke `/api/users`: 200 `[{"id": 1}]`.

Note that `/users` stops working after deploy; keep both events if old clients still use it [docs/events.md#http]. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 537
    B(537, provider="gcp", stage="staging", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#state-remote-terraform-backend"],
      project=dict(files={
          "pskit.yml": """service: geo
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, geo-staging}
functions:
  api:
    handler: app.geo.api
    events:
    - http: GET /geo
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + """

def api(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="CI and three developers deploy this service, so Terraform state must not stay on laptops. Store it in the GCS bucket `acme-tf-state` with one prefix per stage (geo/<stage>).",
      steps=[
          S("get_project"),
          S("search_docs", query="remote terraform backend state",
            docs=[D("docs/configuration.md", "state-remote-terraform-backend")]),
          S("propose_plan", steps=["provider.state = {backend: gcs, config: {bucket: acme-tf-state, prefix: geo/${opt:stage}}}",
                                   "Validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.state",
            value={"backend": "gcs", "config": {"bucket": "acme-tf-state", "prefix": "geo/${opt:stage}"}}),
      ],
      final="""Configured a remote backend:

```yaml
provider:
  state:
    backend: gcs
    config:
      bucket: acme-tf-state
      prefix: geo/${opt:stage}
```

- By default state lives in `.pskit/<provider>-<stage>/terraform.tfstate`; `backend` takes any Terraform backend type, and `${opt:stage}` gives one prefix per stage [docs/configuration.md#state-remote-terraform-backend].
- `pskit validate` (gcp, staging): valid.

The bucket must exist and every deployer needs access to it. If someone already deployed with local state, their next deploy needs the state moved first. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 538
    B(538, provider="azure", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: azure
  region: westeurope
functions:
  search:
    handler: app.search.search
    events:
    - http: GET /search
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """

def search(event, ctx):
    return {"tags": [event.http.query.get("tag")]}
""",
          "requirements.txt": ""}),
      user="url like /search?tag=red&tag=big only give me 1 tag. need all of them",
      steps=[
          S("get_project"),
          S("search_docs", query="query string repeated parameters multi_query",
            docs=[D("docs/handlers.md", "httprequest", words=170)]),
          S("propose_plan", steps=["Use event.http.multi_query.get(\"tag\", []) for repeated parameters",
                                   "Validate for azure (staging), invoke /search"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/search.py", content=FUTURE + """

def search(event, ctx):
    tags = event.http.multi_query.get("tag", [])
    return {"tags": tags}
"""),
          S("validate"),
          S("invoke_local", function="search", method="GET", path="/search"),
      ],
      final="""`event.http.query` keeps one value per name; `event.http.multi_query` keeps all of them as a list [docs/handlers.md#httprequest]. The handler now uses it:

```python
tags = event.http.multi_query.get("tag", [])
```

- `pskit validate` (azure, staging): valid.
- Local call to `/search` without parameters: `{"tags": []}`, so no crash when there are none.

With `?tag=red&tag=big` after deploy you get `["red", "big"]`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 539
    B(539, provider="aws", stage="staging", mode="auto", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: social
provider:
  name: aws
  region: eu-west-1
functions:
  post-tips:
    handler: app.tips.post
    events:
    - schedule:
        rate: 1 day
        input: {channel: tips}
""",
          "app/__init__.py": "",
          "app/tips.py": FUTURE + """

def post(event, ctx):
    return {"posted": (event.data or {}).get("channel")}
""",
          "requirements.txt": ""}),
      user="please stop the daily tips for a while, but don't delete them. we'll turn it back on next month",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Set enabled: false on the schedule of post-tips (the function stays)",
                                   "Validate for aws (staging)"]),
          S("set_config", path="functions.post-tips.events.0.schedule.enabled", value=False),
      ],
      final="""Paused. The schedule is switched off, and everything else stays as it was:

```yaml
functions:
  post-tips:
    events:
      - schedule:
          rate: 1 day
          input: {channel: tips}
          enabled: false
```

- `enabled` is a schedule setting [docs/events.md#schedule]. The function still exists and can be run by hand.
- `pskit validate` (aws, staging): valid.

It stops after you deploy: **Deploy** page or `pskit deploy -s staging`. Next month, set `enabled: true` (or delete the line) and deploy again."""),

    # ------------------------------------------------------------------ 540
    B(540, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=dict(files={
          "pskit.yml": """service: experiments
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, experiments-prod}
functions:
  step-one:
    handler: app.exp.one
workflows:
  beta-flow:
    start_at: One
    states:
      One: {type: task, function: step-one, end: true}
""",
          "app/__init__.py": "",
          "app/exp.py": FUTURE + """

def one(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="beta-flow: keep in dev/staging, off in prod",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["stages.prod.workflows.beta-flow.enabled = false", "Validate gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"prod": {"workflows": {"beta-flow": {"enabled": False}}}}),
      ],
      final="""```yaml
stages:
  prod:
    workflows:
      beta-flow: {enabled: false}
```

- Workflows take `enabled` too, and `stages.prod` is merged only for prod [docs/configuration.md#stages-per-stage-overrides].
- validate (gcp, prod): valid, with a warning that `beta-flow` is disabled (not deployed). Other stages are unchanged.

`step-one` is still deployed in prod; disable it too if it's only used by this workflow. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),
]
