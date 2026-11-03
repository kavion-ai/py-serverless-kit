"""Category C (fix a validation error), batch 21 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def C(n, **kw):
    return dict(id=f"c_fix-{n:04d}", category="c_fix", **kw)


def handlers(*names):
    """A tiny handler module with the given function names (scaffolding only)."""
    body = FUTURE
    for name in names:
        body += f"\ndef {name}(event, ctx):\n    return {{\"ok\": True, \"fn\": \"{name}\"}}\n\n"
    return body.rstrip() + "\n"


def proj(yml, module, *names, extra=None):
    files = {"pskit.yml": yml, "app/__init__.py": "", f"app/{module}.py": handlers(*names)}
    files.update(extra or {})
    return dict(files=files)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 401  aws httpApi event
    C(401, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#http"],
      project=proj("""service: todo-api
provider:
  name: aws
  region: us-east-1
functions:
  list-todos:
    handler: app.todos.list_todos
    events:
      - httpApi:
          path: /todos
          method: get
""", "todos", "list_todos"),
      user="My serverless.yml used `httpApi` events for API Gateway HTTP APIs. pskit says unknown event type 'httpApi'. What's the pskit name?",
      steps=[
          S("get_validation"),
          S("search_docs", query="http event api gateway http api",
            docs=[D("docs/events.md", "http", end="# used by auth: jwt on AWS"),
                  D("docs/providers.md", "aws-aws-lambda", start="| Trigger | Implementation |", end="CORS on the API |")]),
          S("propose_plan", steps=["Replace the `httpApi` event of `list-todos` with `http: GET /todos`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.list-todos.events.0", value={"http": "GET /todos"}),
      ],
      final="""The pskit trigger is `http`, and on AWS it already deploys an API Gateway **HTTP API** [docs/providers.md#aws-aws-lambda].

Changed the event to `- http: GET /todos` [docs/events.md#http]. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 402  aws jwt missing audience
    C(402, provider="aws", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: billing-api
provider:
  name: aws
  region: eu-west-1
functions:
  invoices:
    handler: app.billing.invoices
    events:
      - http:
          path: /invoices
          method: GET
          auth: jwt
          authorizer:
            issuer: https://login.example.com/
""", "billing", "invoices"),
      user="""ERROR: [functions.invoices] jwt auth needs authorizer.issuer and authorizer.audience

issuer is there already""",
      steps=[
          S("get_validation"),
          S("ask_user", question="The issuer is set; the audience is missing. What audience (client id / API identifier) do your tokens carry in `aud`?",
            answer="billing-api-prod"),
          S("propose_plan", steps=["Set `functions.invoices.events.0.http.authorizer.audience` to `[billing-api-prod]`",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.invoices.events.0.http.authorizer.audience", value=["billing-api-prod"]),
      ],
      final="""A JWT authorizer on AWS needs both `issuer` and `audience`; only the issuer was set [docs/events.md#http].

Added `audience: [billing-api-prod]` to the authorizer of `/invoices`. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 403  aws exists typo
    C(403, provider="aws", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=proj("""service: ledger-sync
provider:
  name: aws
  region: us-east-2
functions:
  sync:
    handler: app.ledger.sync
    events:
      - queue:
          name: ledger-updates
          exists: true
          batch_size: 25
""", "ledger", "sync"),
      user="queue exists: Extra inputs are not permitted. queue is pre-made",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `exists` and set `existing: true` on the queue event of `sync`",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="functions.sync.events.0.queue.exists", value=None),
          S("set_config", path="functions.sync.events.0.queue.existing", value=True),
      ],
      final="""The key is `existing`, not `exists` [docs/events.md#queue].

Replaced it with `existing: true`, so pskit uses `ledger-updates` instead of creating it. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 404  gcp {id:int}
    C(404, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: product-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: product-api-dev
functions:
  product:
    handler: app.products.get_product
    events:
      - http: GET /products/{id:int}
""",
          "app/__init__.py": "",
          "app/products.py": FUTURE + """

def get_product(event, ctx):
    product_id = event.http.path_params["id"]
    return {"id": product_id}
"""}),
      user="""Error: pskit.yml is invalid:
  - functions.product.events.0.path: Value error, invalid path template '/products/{id:int}'; use /users/{id} or /files/{path+}

like flask, i want id to be int""",
      steps=[
          S("get_validation"),
          S("read_file", path="app/products.py"),
          S("propose_plan", steps=["Change the route to `GET /products/{id}`",
                                   "Convert the id with `int(...)` in `get_product` (answer 400 if it isn't a number)",
                                   "Validate for gcp and call the function locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.product.events.0.http", value="GET /products/{id}"),
          S("write_file", path="app/products.py", content=FUTURE + """from py_serverless_kit import BadRequest


def get_product(event, ctx):
    raw = event.http.path_params["id"]
    if not raw.isdigit():
        raise BadRequest("id must be a number")
    return {"id": int(raw)}
"""),
          S("validate"),
          S("invoke_local", function="product", method="GET", path="/products/42"),
      ],
      final="""pskit path templates have no type converters like Flask's `<int:id>`: `{id}` always gives a string [docs/events.md#http].

- Route is now `GET /products/{id}`.
- `get_product` converts it with `int(...)` and raises `BadRequest` (400) when it isn't a number.

`pskit validate` for gcp: valid. Local call to `/products/42`: status 200, body `{"id": 42}`."""),

    # ------------------------------------------------------------------ 405  gcp choice default -> missing state
    C(405, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#choice-rules"],
      project=proj("""service: loan-review
provider:
  name: gcp
  region: us-central1
  options:
    project: loan-review-staging
functions:
  score:
    handler: app.loans.score
  approve:
    handler: app.loans.approve
  manual:
    handler: app.loans.manual
workflows:
  review:
    start_at: Score
    states:
      Score: {type: task, function: score, next: Decide}
      Decide:
        type: choice
        choices:
          - {variable: "$.score", gte: 700, next: Approve}
        default: ManualReview
      Approve: {type: task, function: approve, end: true}
      Manual: {type: task, function: manual, end: true}
""", "loans", "score", "approve", "manual"),
      user="The review workflow fails validation on staging. Loans with a score below 700 should go to the manual check (the `manual` function). Please fix only the routing.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `Decide.default` to `Manual` (the state that runs `manual`)",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.review.states.Decide.default", value="Manual"),
      ],
      final="""The choice `Decide` sent everything below 700 to `ManualReview`, but the state is called `Manual`; pskit checks that every `default` target exists [docs/workflows.md#workflow-keys].

Changed `Decide.default` to `Manual`. Scores ≥ 700 still go to `Approve` [docs/workflows.md#choice-rules]. `pskit validate -p gcp -s staging`: valid (native Cloud Workflows)."""),

    # ------------------------------------------------------------------ 406  gcp batch_size 20000 -> ignored
    C(406, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=proj("""service: click-stream
provider:
  name: gcp
  region: europe-west3
  options:
    project: click-stream-dev
functions:
  collect:
    handler: app.clicks.collect
    events:
      - queue:
          name: clicks
          batch_size: 20000
""", "clicks", "collect"),
      user="i set batch_size 20000 so collect get many click at once, gcp say must be less 10000",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue batch_size gcp ignored",
            docs=[D("docs/events.md", "queue", start="| Option | aws (SQS) |", end="| partial batch failure |")]),
          S("propose_plan", steps=["Remove `batch_size` from the queue event of `collect` (GCP ignores it)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.collect.events.0.queue.batch_size", value=None),
      ],
      final="""`batch_size` can be at most 10000, and on GCP it does nothing anyway: a pskit queue on GCP is a Pub/Sub push trigger, so messages come one delivery at a time [docs/events.md#queue].

I removed `batch_size` from `collect`. Validate: valid. If you need big batches, collect clicks somewhere and process them with a schedule instead."""),

    # ------------------------------------------------------------------ 407  azure queue name too short
    C(407, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#queue"],
      project=proj("""service: sms-sender
provider:
  name: azure
  region: centralus
functions:
  send-sms:
    handler: app.sms.send
    events:
      - queue: q
""", "sms", "send"),
      user="I named my queue just q to keep it short. Azure says the name is wrong but it's already lowercase?",
      steps=[
          S("get_validation"),
          S("ask_user", question="Azure queue names need at least 3 characters. What should the queue be called?",
            options=["sms-queue", "sms"], answer="sms-queue"),
          S("propose_plan", steps=["Rename the queue of `send-sms` to `sms-queue`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send-sms.events.0", value={"queue": "sms-queue"}),
      ],
      final="""Lowercase was right, but Azure queue names must also be 3 to 63 characters long, and `q` is only one [docs/events.md#queue].

The queue is now `sms-queue`. Validate: valid. Send your messages to `sms-queue` from now on."""),

    # ------------------------------------------------------------------ 408  azure http+smtp -> only http on azure
    C(408, provider="azure", stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/events.md#events-triggers", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=proj("""service: support-inbox
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8133
providers:
  azure:
    region: westeurope
resources:
  support-mail: {type: smtp}
functions:
  inbox:
    handler: app.inbox.handle
    events:
      - http: POST /inbox
      - smtp: {resource: support-mail}
""", "inbox", "handle"),
      user="support-inbox runs on-prem with an HTTP route and an SMTP trigger on the same function. For a staging copy on Azure only the HTTP route is needed (a mail relay posts to it). Azure validation fails. Keep on-prem exactly as it is.",
      steps=[
          S("get_validation"),
          S("search_docs", query="override events per provider",
            docs=[D("docs/configuration.md", "switch-something-off-on-one-cloud")]),
          S("propose_plan", steps=["Add `providers.azure.functions.inbox.events: [{http: POST /inbox}]` (lists replace, so no smtp on Azure)",
                                   "Add `providers.azure.resources.support-mail.external: true` (pskit doesn't create the SMTP server on Azure)",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.functions.inbox.events", value=[{"http": "POST /inbox"}]),
          S("set_config", path="providers.azure.resources.support-mail.external", value=True),
      ],
      final="""`smtp` triggers and SMTP resources exist only on premises, so Azure rejected `inbox` [docs/events.md#events-triggers].

For Azure only:

```yaml
providers:
  azure:
    functions:
      inbox: {events: [{http: POST /inbox}]}
    resources:
      support-mail: {external: true}
```

A `providers:` list replaces the base list, so on Azure `inbox` has just the HTTP route [docs/configuration.md#switch-something-off-on-one-cloud]. `pskit validate -p azure -s staging`: valid. The on-prem config is unchanged."""),

    # ------------------------------------------------------------------ 409  aws nested variable -> stages:
    C(409, provider="aws", stage="staging", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/configuration.md#variables"],
      project=proj("""service: catalog-api
provider:
  name: aws
  region: eu-west-1
custom:
  sizes:
    dev: 256
    staging: 512
    prod: 1024
functions:
  catalog:
    handler: app.catalog.handler
    memory: ${self:custom.sizes.${opt:stage}}
    events:
      - http: GET /catalog
""", "catalog", "handler"),
      user="In serverless.yml I did `memory: ${self:custom.sizes.${opt:stage}}` and it worked. pskit staging says `unresolved variables: self:custom.sizes.${opt:stage`. Does pskit have a per-stage way?",
      steps=[
          S("get_validation"),
          S("search_docs", query="per stage overrides",
            docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["Set `functions.catalog.memory: 256` (dev value as the base)",
                                   "Add `stages.staging.functions.catalog.memory: 512` and `stages.prod.functions.catalog.memory: 1024`",
                                   "Remove `custom.sizes`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.catalog.memory", value=256),
          S("set_config", path="stages", value={"staging": {"functions": {"catalog": {"memory": 512}}},
                                                "prod": {"functions": {"catalog": {"memory": 1024}}}}),
          S("set_config", path="custom.sizes", value=None),
      ],
      final="""pskit doesn't resolve a variable inside another variable's name, so `${self:custom.sizes.${opt:stage}}` stays unresolved. Per-stage values go in `stages:` [docs/configuration.md#stages-per-stage-overrides].

Now:

```yaml
functions:
  catalog:
    memory: 256
stages:
  staging:
    functions: {catalog: {memory: 512}}
  prod:
    functions: {catalog: {memory: 1024}}
```

`pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 410  aws hooks string
    C(410, provider="aws", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#hooks"],
      project=proj("""service: menu-api
provider:
  name: aws
  region: eu-north-1
hooks:
  after_deploy: python scripts/smoke_test.py
functions:
  menu:
    handler: app.menu.get_menu
    events:
      - http: GET /menu
""", "menu", "get_menu"),
      user="hooks.after_deploy: Input should be a valid list. one command only",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Wrap the command in a list: `after_deploy: [\"python scripts/smoke_test.py\"]`",
                                   "Validate for aws"]),
          S("set_config", path="hooks.after_deploy", value=["python scripts/smoke_test.py"]),
      ],
      final="""Each hook is a list of shell commands, even with one command [docs/configuration.md#hooks].

Set `after_deploy: ["python scripts/smoke_test.py"]`. `pskit validate` for aws: valid. A non-zero exit of the script will make the deploy command fail."""),

    # ------------------------------------------------------------------ 411  gcp database password literal (security)
    C(411, provider="gcp", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#secrets", "docs/troubleshooting.md#security-notes"],
      project=proj("""service: orders-svc
provider:
  name: gcp
  region: europe-west1
  options:
    project: orders-svc-prod
resources:
  orders-db:
    type: database
    external: true
    connection:
      host: db.example.com
      port: 5432
      user: orders_app
      password: Winter2026!
functions:
  orders:
    handler: app.orders.list_orders
    events:
      - http: GET /orders
""", "orders", "list_orders"),
      user="Before the prod deploy, review the orders-db resource on the Resources page. Validation is green, but I'm not sure the connection block is safe.",
      steps=[
          S("get_validation"),
          S("search_docs", query="resource connection password secret",
            docs=[D("docs/resources.md", "secrets", end="from the platform's secret store or function environment.")]),
          S("propose_plan", steps=["Remove `resources.orders-db.connection.password`",
                                   "Add `password_env: ORDERS_DB_PASSWORD` (the handler reads the secret from that variable)",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.orders-db.connection.password", value=None),
          S("set_config", path="resources.orders-db.connection.password_env", value="ORDERS_DB_PASSWORD"),
      ],
      final="""It wasn't safe: the database password was written in pskit.yml, and connection values become function environment variables stored in Terraform state [docs/resources.md#secrets].

- Removed the written-out password from `orders-db.connection`.
- Added `password_env: ORDERS_DB_PASSWORD`; the handler reads `ctx.env[db["password_env"]]` at run time.

`pskit validate -p gcp -s prod`: still valid. Provide `ORDERS_DB_PASSWORD` to the function from your secret store, and change the database password, since the old one was in the file [docs/troubleshooting.md#security-notes]."""),

    # ------------------------------------------------------------------ 412  azure handler path-style
    C(412, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: order-intake
provider:
  name: azure
  region: southeastasia
functions:
  create-order:
    handler: app/orders.py:create
    events:
      - http: POST /orders
""", "orders", "create"),
      user="handler i write path of file app/orders.py:create, but it say must be package.module.function. how write it?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.create-order.handler` to `app.orders.create`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.create-order.handler", value="app.orders.create"),
      ],
      final="""The handler is a Python import path, not a file path: dots between folder, file (without `.py`) and function [docs/configuration.md#functions].

So `app/orders.py:create` becomes `handler: app.orders.create`. Validate: valid."""),

    # ------------------------------------------------------------------ 413  azure cors origins string
    C(413, provider="azure", stage="prod", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: booking-api
provider:
  name: azure
  region: westeurope
functions:
  slots:
    handler: app.booking.slots
    events:
      - http:
          path: /slots
          method: GET
          cors:
            origins: https://booking.example.com
""", "booking", "slots"),
      user="""Error: pskit.yml is invalid:
  - functions.slots.events.0.cors.bool: Input should be a valid boolean
  - functions.slots.events.0.cors.CorsConfig.origins: Input should be a valid list""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Make `cors.origins` of `slots` a list: `[\"https://booking.example.com\"]`",
                                   "Validate for azure, stage prod"]),
          S("set_config", path="functions.slots.events.0.http.cors.origins", value=["https://booking.example.com"]),
      ],
      final="""`cors.origins` must be a list, even with one origin; the first error line only means "not `true`/`false` either" [docs/events.md#http].

Set `origins: ["https://booking.example.com"]`. `pskit validate -p azure -s prod`: valid."""),

    # ------------------------------------------------------------------ 414  gcp tags as list
    C(414, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: blog-engine
provider:
  name: gcp
  region: us-east4
  options:
    project: blog-engine-dev
functions:
  posts:
    handler: app.blog.posts
    tags: [content-team]
    events:
      - http: GET /posts
""", "blog", "posts"),
      user="I added a tag content-team to the posts function and now it says tags should be a valid dictionary.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Change `functions.posts.tags` to a mapping: `{team: content-team}`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.posts.tags", value={"team": "content-team"}),
      ],
      final="""Tags are name: value pairs, not a list [docs/configuration.md#functions].

I wrote it as `tags: {team: content-team}`. Validate: valid. On GCP pskit adds these next to its own `pskit-service` and `pskit-stage` labels."""),

    # ------------------------------------------------------------------ 415  gcp log_retention_days string
    C(415, provider="gcp", stage="staging", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: audit-trail
provider:
  name: gcp
  region: europe-west1
  log_retention_days: two weeks
  options:
    project: audit-trail-staging
functions:
  record:
    handler: app.audit.record
    events:
      - topic: audit-events
""", "audit", "record"),
      user="log_retention_days two weeks give error, i want logs kept 14 day on gcp",
      steps=[
          S("get_validation"),
          S("search_docs", query="log_retention_days",
            docs=[D("docs/configuration.md", "provider", start="| `log_retention_days` |", end="AWS CloudWatch log group retention |")]),
          S("propose_plan", steps=["Remove `provider.log_retention_days` (it is only used for AWS CloudWatch)",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.log_retention_days", value=None),
      ],
      final="""It must be a number, and it only sets the AWS CloudWatch log group retention, so on GCP it does nothing [docs/configuration.md#provider].

I removed the line. Validate for staging: valid. To keep GCP logs 14 days, set the retention of the log bucket in Cloud Logging; pskit doesn't manage that."""),

    # ------------------------------------------------------------------ 416  aws two keys in one event
    C(416, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/troubleshooting.md#configuration", "docs/events.md#events-triggers"],
      project=proj("""service: stock-report
provider:
  name: aws
  region: us-east-1
functions:
  report:
    handler: app.report.build
    events:
      - http: GET /report
        schedule: "0 18 * * 1-5"
""", "report", "build"),
      user="I want my report to work from a link AND every weekday at 6pm. Validate says each event must be a single-key mapping. What's that?",
      steps=[
          S("get_validation"),
          S("search_docs", query="each event must be a single-key mapping",
            docs=[D("docs/troubleshooting.md", "configuration", start="**`each event must be a single-key mapping`**", end="not two keys in one item.")]),
          S("propose_plan", steps=["Split the event of `report` into two list items: `http: GET /report` and `schedule: \"0 18 * * 1-5\"`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.report.events", value=[{"http": "GET /report"}, {"schedule": "0 18 * * 1-5"}]),
      ],
      final="""Both triggers were in one list item. Each item under `events` may have only one trigger, so each needs its own `-` [docs/troubleshooting.md#configuration].

Now:

```yaml
events:
  - http: GET /report
  - schedule: "0 18 * * 1-5"
```

Validate: valid. The schedule is in UTC unless you add `timezone`."""),

    # ------------------------------------------------------------------ 417  gcp workflow task disabled on gcp
    C(417, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/configuration.md#switch-something-off-on-one-cloud"],
      project=proj("""service: onboarding
provider:
  name: aws
  region: us-east-1
providers:
  gcp:
    region: us-central1
    options:
      project: onboarding-dev-31
    functions:
      send-welcome: {enabled: false}
functions:
  create-account:
    handler: app.onboard.create_account
  send-welcome:
    handler: app.onboard.send_welcome
workflows:
  onboard:
    start_at: Create
    states:
      Create: {type: task, function: create-account, next: Welcome}
      Welcome: {type: task, function: send-welcome, end: true}
""", "onboard", "create_account", "send_welcome"),
      user="gcp: workflow onboard calls send-welcome, which is disabled. fix",
      steps=[
          S("get_validation"),
          S("ask_user", question="On GCP `send-welcome` is off, and `onboard` needs it. Turn it back on for GCP, or turn the `onboard` workflow off on GCP as well?",
            options=["Enable send-welcome on GCP", "Disable onboard on GCP"],
            answer="Enable send-welcome on GCP"),
          S("propose_plan", steps=["Remove `providers.gcp.functions` (send-welcome is enabled again on GCP)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.gcp.functions", value=None),
      ],
      final="""A workflow can't call a function that is disabled on that provider [docs/configuration.md#switch-something-off-on-one-cloud].

Removed the GCP override that disabled `send-welcome`. `pskit validate -p gcp`: valid; `onboard` runs natively on Cloud Workflows."""),

    # ------------------------------------------------------------------ 418  azure Logic Apps task timeout warning
    C(418, provider="azure", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#compiler-notes-and-limits"],
      project=proj("""service: quote-flow
provider:
  name: azure
  region: westeurope
functions:
  price:
    handler: app.quotes.price
    timeout: 300
  send:
    handler: app.quotes.send
workflows:
  quote:
    engine: native
    start_at: Price
    states:
      Price: {type: task, function: price, next: Send}
      Send: {type: task, function: send, end: true}
""", "quotes", "price", "send"),
      user="Validation for the native quote workflow on Azure warns about the price task and 120 seconds. Pricing normally takes about 20 s. What does the warning mean, and please clear it.",
      steps=[
          S("get_validation"),
          S("search_docs", query="logic apps task timeout 120",
            docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="Task calls time out after 120 s", end="when a task function's timeout is longer.")]),
          S("propose_plan", steps=["Set `functions.price.timeout` to 120 (the Logic Apps HTTP call limit)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.price.timeout", value=120),
      ],
      final="""A Logic App calls each task over HTTP and gives up after 120 s, so with `timeout: 300` a slow `price` could still be running when the workflow already failed [docs/workflows.md#compiler-notes-and-limits].

Set `functions.price.timeout: 120`. That leaves plenty of room for your 20 s runs. `pskit validate -p azure`: valid, no warning."""),

    # ------------------------------------------------------------------ 419  aws prefix under queue event
    C(419, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage", "docs/events.md#queue"],
      project=proj("""service: invoice-drop
provider:
  name: aws
  region: eu-west-3
functions:
  parse:
    handler: app.invoices.parse
    events:
      - queue:
          name: invoice-drop
          prefix: incoming/
""", "invoices", "parse"),
      user="parse must run when pdf put in invoice-drop bucket folder incoming/. it say prefix extra inputs not permitted",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage event prefix suffix",
            docs=[D("docs/events.md", "storage", start="```yaml", end="suffix: .csv")]),
          S("propose_plan", steps=["Change the trigger of `parse` from `queue` to `storage: {bucket: invoice-drop, prefix: incoming/, suffix: .pdf}`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.parse.events.0",
            value={"storage": {"bucket": "invoice-drop", "prefix": "incoming/", "suffix": ".pdf"}}),
      ],
      final="""It was a `queue` trigger, and queues have no `prefix`. A file landing in a bucket is a `storage` trigger [docs/events.md#storage].

Now `parse` has `storage: {bucket: invoice-drop, prefix: incoming/, suffix: .pdf}`. On AWS that is an S3 notification. Validate: valid. pskit creates the bucket; add `existing: true` if it is already there."""),

    # ------------------------------------------------------------------ 420  azure topic filter (warning)
    C(420, provider="azure", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#topic"],
      project=proj("""service: shipping-events
provider:
  name: azure
  region: northeurope
functions:
  on-shipped:
    handler: app.shipping.on_shipped
    events:
      - topic:
          name: order-events
          filter: {type: ["shipped"]}
""", "shipping", "on_shipped"),
      user="On AWS the SNS filter policy made on-shipped see only 'shipped' messages. Azure validation warns that topic.filter is not applied. What should I do so it doesn't process every order event?",
      steps=[
          S("get_validation"),
          S("search_docs", query="topic filter azure not applied",
            docs=[D("docs/events.md", "topic", start="| Provider | Service | `filter` |", end="| alibaba |")]),
          S("propose_plan", steps=["Remove `filter` from the topic event of `on-shipped` (Azure ignores it)",
                                   "Validate for azure, stage staging",
                                   "Next: skip records whose `type` attribute isn't `shipped` in the handler"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.on-shipped.events.0.topic.filter", value=None),
      ],
      final="""Azure Service Bus subscriptions created by pskit don't apply `filter`, so on Azure every message reaches `on-shipped` [docs/events.md#topic].

Removed the ignored `filter`. `pskit validate -p azure -s staging`: valid, no warning.

The filtering now has to be in the handler: skip any record in `event.records` whose `attributes.get("type")` isn't `"shipped"`. Shall I add that to `app/shipping.py`?"""),
]
