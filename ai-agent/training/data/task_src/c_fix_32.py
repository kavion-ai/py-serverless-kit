"""Category C (fix a validation error), batch 32 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 621  aws eventBridge schedule
    C(621, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=proj("""service: cert-check
provider:
  name: aws
  region: us-east-1
functions:
  check-certs:
    handler: app.certs.check
    events:
      - eventBridge:
          schedule: rate(10 minutes)
""", "certs", "check"),
      user="serverless.yml had `- eventBridge: {schedule: rate(10 minutes)}`. pskit: unknown event type 'eventBridge'.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace the trigger with `schedule: 10 minutes`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.check-certs.events.0", value={"schedule": "10 minutes"}),
      ],
      final="""Timers are the portable `schedule` event; on AWS pskit creates the EventBridge Scheduler entry and writes `rate(10 minutes)` itself [docs/events.md#schedule].

Now `- schedule: 10 minutes`. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 622  aws alb -> http
    C(622, provider="aws", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/providers.md#aws-aws-lambda"],
      project=proj("""service: legacy-proxy
provider:
  name: aws
  region: eu-west-1
functions:
  proxy:
    handler: app.proxy.handle
    events:
      - alb:
          listenerArn: arn:aws:elasticloadbalancing:eu-west-1:123456789012:listener/app/edge/abc/def
          priority: 10
          conditions:
            path: /legacy/*
""", "proxy", "handle"),
      user="proxy was behind an ALB listener rule (path /legacy/*). In pskit the alb event is unknown. All we need is that /legacy/... reaches this function.",
      steps=[
          S("get_validation"),
          S("search_docs", query="http path greedy aws api gateway",
            docs=[D("docs/events.md", "http", start="**Path templates**", end="Parameter names are identifiers")]),
          S("propose_plan", steps=["Replace the `alb` event with `http: ANY /legacy/{path+}`", "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.proxy.events.0", value={"http": "ANY /legacy/{path+}"}),
      ],
      final="""pskit has no ALB trigger; HTTP functions on AWS sit behind an API Gateway HTTP API. A greedy `{path+}` matches everything under a prefix [docs/events.md#http].

`proxy` now has `- http: ANY /legacy/{path+}`; the rest of the path is in `event.http.path_params["path"]`. `pskit validate -p aws -s staging`: valid. Point clients (or your ALB) at the API URL that `pskit info` shows after deploy."""),

    # ------------------------------------------------------------------ 623  aws websocket, no equivalent
    C(623, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#events-triggers"],
      project=proj("""service: live-scores
provider:
  name: aws
  region: us-east-1
functions:
  scores:
    handler: app.scores.latest
    events:
      - http: GET /scores
  on-connect:
    handler: app.scores.on_connect
    events:
      - websocket: $connect
""", "scores", "latest", "on_connect"),
      user="We used API Gateway WebSockets ($connect) for live scores. pskit says unknown event type 'websocket'. What can I do?",
      steps=[
          S("get_validation"),
          S("ask_user", question="pskit has no WebSocket trigger (only http, schedule, queue, storage, topic, smtp). Should `on-connect` become a plain HTTP endpoint the page polls (e.g. `GET /scores/live`), or should I just remove its trigger for now?",
            options=["HTTP endpoint for polling", "remove the trigger"], answer="HTTP endpoint for polling"),
          S("propose_plan", steps=["Replace the `websocket` event of `on-connect` with `http: GET /scores/live`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.on-connect.events.0", value={"http": "GET /scores/live"}),
      ],
      final="""WebSockets aren't one of pskit's event types, so the trigger can't be ported as is [docs/events.md#events-triggers].

`on-connect` now answers `GET /scores/live`, which the page can poll every few seconds. Validate for aws: valid. The handler gets an HTTP event now, so it should return the current scores instead of handling a connection."""),

    # ------------------------------------------------------------------ 624  aws ${self:provider.region} unresolved
    C(624, provider="aws", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: geo-lookup
provider:
  name: aws
functions:
  lookup:
    handler: app.geo.lookup
    environment:
      AWS_REGION_NAME: ${self:provider.region}
    events:
      - http: GET /lookup
""", "geo", "lookup"),
      user="""Error: unresolved variables: self:provider.region

it worked in serverless, region is us-east-1 by default??""",
      steps=[
          S("get_validation"),
          S("search_docs", query="self variable merged config",
            docs=[D("docs/configuration.md", "variables", end="| `${self:dotted.path}` |")]),
          S("propose_plan", steps=["Set `provider.region: us-east-1` explicitly so `${self:provider.region}` has a value", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.region", value="us-east-1"),
      ],
      final="""`${self:...}` reads values written in the config; the default region is filled in later, so `provider.region` didn't exist yet [docs/configuration.md#variables].

I wrote `region: us-east-1` under `provider`; `AWS_REGION_NAME` now resolves to it. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 625  aws handlr typo hides the timeout error
    C(625, provider="aws", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions", "docs/providers.md#aws-aws-lambda"],
      project=proj("""service: nightly-billing
provider:
  name: aws
  region: eu-west-1
functions:
  bill:
    handlr: app.billing.run
    timeout: 1200
    events:
      - schedule: "0 2 * * *"
""", "billing", "run"),
      user="prod validate red: handler field required and handlr extra. fix pls",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `handlr` to `handler` on `bill`", "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.bill",
            value={"handler": "app.billing.run", "timeout": 1200, "events": [{"schedule": "0 2 * * *"}]}),
          S("ask_user", say="The typo is fixed, and now AWS checks show the next problem: timeout 1200 s is over Lambda's 900 s.",
            question="Lambda stops at 900 s. Set `bill` to 900 s?", options=["yes 900", "no"], answer="yes 900"),
          S("set_config", path="functions.bill.timeout", value=900),
      ],
      final="""Two problems, one behind the other: `handlr` was a typo, so pskit found no `handler` [docs/configuration.md#functions]; after that, AWS reported `timeout 1200s exceeds AWS Lambda max 900s`.

`bill` now has `handler: app.billing.run` and `timeout: 900`. `pskit validate -p aws -s prod`: valid. If billing needs longer than 15 minutes, split it into smaller runs."""),

    # ------------------------------------------------------------------ 626  aws auth cognito
    C(626, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=proj("""service: notes-app
provider:
  name: aws
  region: eu-central-1
functions:
  notes:
    handler: app.notes.list_notes
    events:
      - http:
          path: /notes
          method: GET
          auth: cognito
""", "notes", "list_notes"),
      user="Our users log in with Cognito. I set auth: cognito and it says Input should be 'none', 'iam', 'jwt' or 'key'.",
      steps=[
          S("get_validation"),
          S("search_docs", query="jwt authorizer issuer audience aws",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", question="Cognito sign-in uses `auth: jwt`. I need the user pool id and the app client id (the token audience).",
            answer="pool eu-central-1_Q1w2E3r4T, client 4h5j6k7l8m9n0p1q2r3s4t5u6v"),
          S("propose_plan", steps=["Set `auth: jwt` on `/notes`",
                                   "Set `authorizer.issuer: https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Q1w2E3r4T` and `audience: [4h5j6k7l8m9n0p1q2r3s4t5u6v]`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.notes.events.0.http",
            value={"path": "/notes", "method": "GET", "auth": "jwt",
                   "authorizer": {"issuer": "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Q1w2E3r4T",
                                  "audience": ["4h5j6k7l8m9n0p1q2r3s4t5u6v"]}}),
      ],
      final="""There is no `cognito` value; Cognito tokens are JWTs, so on AWS you use `auth: jwt` with the pool as issuer and the app client as audience [docs/events.md#http].

`/notes` now has `auth: jwt`, issuer `https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_Q1w2E3r4T`, audience `4h5j6k7l8m9n0p1q2r3s4t5u6v`. Validate for aws: valid. Calls need `Authorization: Bearer <token>`."""),

    # ------------------------------------------------------------------ 627  aws sqs arn form
    C(627, provider="aws", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=proj("""service: order-sink
provider:
  name: aws
  region: us-east-1
functions:
  sink:
    handler: app.orders.sink
    events:
      - sqs:
          arn: arn:aws:sqs:us-east-1:123456789012:orders-in
          batchSize: 10
""", "orders", "sink"),
      user="sqs: {arn, batchSize} → unknown event type. queue exists already",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace with `queue: {name: orders-in, existing: true, batch_size: 10}`", "Validate for aws, stage staging"]),
          S("set_config", path="functions.sink.events.0",
            value={"queue": {"name": "orders-in", "existing": True, "batch_size": 10}}),
      ],
      final="""pskit's trigger is `queue`, keyed by queue name, with `existing: true` for a queue it shouldn't create [docs/events.md#queue].

`sink`: `queue: {name: orders-in, existing: true, batch_size: 10}`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 628  gcp cloudStorage event
    C(628, provider="gcp", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#storage", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: csv-loader
provider:
  name: gcp
  region: us-central1
  options:
    project: csv-loader-dev
functions:
  load-csv:
    handler: app.loader.load
    events:
      - cloudStorage:
          bucket: csv-drop-dev
          event: finalize
""", "loader", "load"),
      user="I named the trigger after the GCP service: cloudStorage with event finalize. pskit: unknown event type 'cloudStorage'.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace it with `storage: {bucket: csv-drop-dev}` (default event `created` = GCS finalized)", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.load-csv.events.0", value={"storage": {"bucket": "csv-drop-dev"}}),
      ],
      final="""The portable name is `storage`, and its `created` event is GCS `finalized` on GCP [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

`load-csv` now has `storage: {bucket: csv-drop-dev}` (`events` defaults to `[created]`) [docs/events.md#storage]. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 629  gcp firestore trigger, no equivalent
    C(629, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic"],
      project=proj("""service: user-profile
provider:
  name: gcp
  region: europe-west1
  options:
    project: user-profile-dev
functions:
  on-user-write:
    handler: app.users.on_write
    events:
      - firestore:
          document: users/{userId}
""", "users", "on_write"),
      user="on-user-write should run when a users/{userId} document changes in Firestore. pskit: unknown event type 'firestore'.",
      steps=[
          S("get_validation"),
          S("ask_user", question="pskit has no Firestore trigger. Options: (a) the code that writes users also publishes to a topic `user-changes`, and `on-user-write` gets a `topic` trigger; (b) remove the trigger for now (invoke-only). Which?",
            options=["a: topic", "b: invoke-only"], answer="a: topic"),
          S("propose_plan", steps=["Replace the trigger with `topic: user-changes`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.on-user-write.events.0", value={"topic": "user-changes"}),
      ],
      final="""Firestore isn't one of pskit's triggers, so the function needs a different event. You chose a topic [docs/events.md#topic].

`on-user-write` now has `- topic: user-changes` (a Pub/Sub topic pskit creates). Validate for gcp: valid. The writer must publish a message such as `{"user_id": ...}` after each change; in the handler read it with `event.records[0].json()`."""),

    # ------------------------------------------------------------------ 630  gcp region list
    C(630, provider="gcp", stage="prod", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: geo-api
provider:
  name: gcp
  region: [europe-west1, us-central1]
  options:
    project: geo-api-prod
functions:
  nearest:
    handler: app.geo.nearest
    events:
      - http: GET /nearest
""", "geo", "nearest"),
      user="i want api in europe and us both so region list, but error valid string",
      steps=[
          S("get_validation"),
          S("ask_user", question="One deploy goes to one region. I'll keep one region in pskit.yml; for the other you run a second deploy with `-r`. Which should be the default?",
            options=["europe-west1", "us-central1"], answer="europe-west1"),
          S("propose_plan", steps=["Set `provider.region: europe-west1`", "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.region", value="europe-west1"),
      ],
      final="""`region` is a single string; each deploy targets one region [docs/configuration.md#provider].

Set `region: europe-west1`. `pskit validate -p gcp -s prod`: valid. For the US copy use the region flag, e.g. `pskit deploy -s prod -r us-central1`."""),

    # ------------------------------------------------------------------ 631  gcp start_at typo reveals unknown function
    C(631, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: refund-flow
provider:
  name: gcp
  region: europe-west1
  options:
    project: refund-flow-staging
functions:
  check-refund:
    handler: app.refunds.check
  pay-refund:
    handler: app.refunds.pay
workflows:
  refund:
    start_at: Begin
    states:
      Check: {type: task, function: check-refund, next: Pay}
      Pay: {type: task, function: issue-refund, end: true}
""", "refunds", "check", "pay"),
      user="I copied the refund workflow from another project and adapted it. Staging says start_at 'Begin' is not a defined state. The first step is Check.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.refund.start_at` to `Check`", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.refund.start_at", value="Check"),
          S("propose_plan", say="That's fixed; now the next check runs: `Pay` calls `issue-refund`, which this project calls `pay-refund`.",
            steps=["Set `Pay.function` to `pay-refund`", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.refund.states.Pay.function", value="pay-refund"),
      ],
      final="""Two leftovers from the other project: `start_at` must name a state here (`Check`), and every task `function` must exist under `functions` [docs/workflows.md#workflow-keys].

- `start_at: Check`
- `Pay` calls `pay-refund`

`pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 632  gcp state backend bucket at the wrong level
    C(632, provider="gcp", stage="prod", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#state-remote-terraform-backend"],
      project=proj("""service: ledger-sync
provider:
  name: gcp
  region: europe-west1
  options:
    project: ledger-sync-prod
  state:
    backend: gcs
    bucket: ledger-tf-state
    prefix: ledger-sync/prod
functions:
  sync:
    handler: app.ledger.sync
    events:
      - schedule: 1 hour
""", "ledger", "sync"),
      user="provider.state.bucket / prefix: Extra inputs are not permitted. gcs backend",
      steps=[
          S("get_validation"),
          S("search_docs", query="state backend config",
            docs=[D("docs/configuration.md", "state-remote-terraform-backend", end="dynamodb_table: tf-locks")]),
          S("propose_plan", steps=["Move `bucket` and `prefix` under `provider.state.config`", "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.state",
            value={"backend": "gcs", "config": {"bucket": "ledger-tf-state", "prefix": "ledger-sync/prod"}}),
      ],
      final="""Backend settings go in `state.config`; `state` itself only has `backend` and `config` [docs/configuration.md#state-remote-terraform-backend].

Now `state: {backend: gcs, config: {bucket: ledger-tf-state, prefix: ledger-sync/prod}}`. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 633  gcp function-level region
    C(633, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: media-hub
provider:
  name: gcp
  region: europe-west1
  options:
    project: media-hub-dev
functions:
  upload:
    handler: app.media.upload
    events:
      - http: POST /upload
  transcode-us:
    handler: app.media.transcode
    region: us-central1
    events:
      - queue: transcode-us
""", "media", "upload", "transcode"),
      user="transcode-us should run in us-central1 (close to the GPUs), the rest in europe-west1. region on the function gives Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("ask_user", question="pskit has one region per deploy, not per function. I can remove `region` from `transcode-us` so everything deploys to europe-west1 now; for the US worker you'd later make a separate small service deployed with `-r us-central1`. OK to remove it?",
            options=["yes, remove it", "no"], answer="yes, remove it"),
          S("propose_plan", steps=["Remove `functions.transcode-us.region`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.transcode-us.region", value=None),
      ],
      final="""A function has no `region` key; the region belongs to `provider` and applies to the whole deploy [docs/configuration.md#functions].

Removed it, so `transcode-us` deploys with the rest to europe-west1. Validate for gcp: valid. For a real US worker, put it in its own service and deploy that with `-r us-central1`."""),

    # ------------------------------------------------------------------ 634  gcp retry errors as a string
    C(634, provider="gcp", stage="dev", mode="auto", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#retry-and-catch"],
      project=proj("""service: sms-flow
provider:
  name: gcp
  region: us-east1
  options:
    project: sms-flow-dev
functions:
  send:
    handler: app.sms.send
workflows:
  notify:
    start_at: Send
    states:
      Send:
        type: task
        function: send
        retry:
          - errors: ConnectionError
            max_attempts: 5
        end: true
""", "sms", "send"),
      user="""Error: pskit.yml is invalid:
  - workflows.notify.states.Send.retry.0.errors: Input should be a valid list""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `errors: [ConnectionError]` in the retry of `Send`", "Validate for gcp"]),
          S("set_config", path="workflows.notify.states.Send.retry.0.errors", value=["ConnectionError"]),
      ],
      final="""`errors` is a list of exception class names, even for one [docs/workflows.md#retry-and-catch].

Set `errors: [ConnectionError]`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 635  azure eventHub trigger
    C(635, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions"],
      project=proj("""service: meter-readings
provider:
  name: azure
  region: westeurope
functions:
  ingest:
    handler: app.meters.ingest
    events:
      - eventHub: meter-telemetry
""", "meters", "ingest"),
      user="Smart meters send to an Event Hub called meter-telemetry. pskit: unknown event type 'eventHub'. Is there another way to get the readings in?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure triggers queue topic",
            docs=[D("docs/providers.md", "azure-azure-functions", start="| Trigger | Implementation |", end="| topic |")]),
          S("ask_user", question="pskit on Azure has Storage Queue (`queue`) and Service Bus topic (`topic`) triggers, but no Event Hubs. Could the meters (or a forwarder) send to a queue `meter-readings` instead?",
            options=["yes, use a queue", "no, it must stay Event Hubs"], answer="yes, use a queue"),
          S("propose_plan", steps=["Replace the trigger with `queue: meter-readings`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest.events.0", value={"queue": "meter-readings"}),
      ],
      final="""Event Hubs isn't a pskit trigger; on Azure the event triggers are Storage Queues, blobs and Service Bus topics [docs/providers.md#azure-azure-functions].

`ingest` now has `- queue: meter-readings` (a Storage Queue pskit creates). Validate for azure: valid. The meters or a forwarder must now write to that queue."""),

    # ------------------------------------------------------------------ 636  azure auth at function level
    C(636, provider="azure", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=proj("""service: staff-api
provider:
  name: azure
  region: westeurope
functions:
  staff:
    handler: app.staff.list_staff
    auth: key
    events:
      - http: GET /staff
""", "staff", "list_staff"),
      user="I want the staff list to need a key, so I added auth: key to the function. It says functions.staff.auth: Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `auth` from the function", "Set the event to `http: {path: /staff, method: GET, auth: key}`",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.staff.auth", value=None),
          S("set_config", path="functions.staff.events.0", value={"http": {"path": "/staff", "method": "GET", "auth": "key"}}),
      ],
      final="""`auth` belongs to each `http` event, not to the function [docs/events.md#http].

`/staff` now has `auth: key` (an Azure function key). `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 637  azure optional route param {id?}
    C(637, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http"],
      project=proj("""service: catalog-api
provider:
  name: azure
  region: northeurope
functions:
  products:
    handler: app.catalog.products
    events:
      - http: GET /products/{id?}
""", "catalog", "products"),
      user="In Azure Functions I used route products/{id?} so the same function lists all or returns one. pskit: invalid path template '/products/{id?}'.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace it with two routes on `products`: `GET /products` and `GET /products/{id}`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.products.events", value=[{"http": "GET /products"}, {"http": "GET /products/{id}"}]),
      ],
      final="""pskit path parameters are `{name}` or a last `{name+}`; optional `?` parameters don't exist [docs/events.md#http].

`products` now has `GET /products` and `GET /products/{id}`. Validate for azure: valid. In the handler, `event.http.path_params.get("id")` is `None` for the list route."""),

    # ------------------------------------------------------------------ 638  azure {id:int}
    C(638, provider="azure", stage="prod", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: invoice-api
provider:
  name: azure
  region: westeurope
functions:
  invoice:
    handler: app.invoices.get_invoice
    events:
      - http: GET /invoices/{id:int}
""", "invoices", "get_invoice"),
      user="""Error: pskit.yml is invalid:
  - functions.invoice.events.0.path: Value error, invalid path template '/invoices/{id:int}'; use /users/{id} or /files/{path+}""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the route to `GET /invoices/{id}`", "Validate for azure, stage prod"]),
          S("set_config", path="functions.invoice.events.0", value={"http": "GET /invoices/{id}"}),
      ],
      final="""Route constraints like `:int` are Azure syntax; pskit only takes plain `{id}` [docs/events.md#http].

Now `GET /invoices/{id}`. `pskit validate -p azure -s prod`: valid. Check that `id` is a number in the handler and return `BadRequest` if not."""),

    # ------------------------------------------------------------------ 639  azure nodejs function in a python service
    C(639, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: forms-backend
provider:
  name: azure
  region: westeurope
  runtime: python3.12
functions:
  submit:
    handler: app.forms.submit
    events:
      - http: POST /forms
  render-pdf:
    handler: pdf.render
    runtime: nodejs20
    events:
      - queue: pdf-jobs
""", "forms", "submit"),
      user="render-pdf uses a Node library, so I set runtime nodejs20 on it. Validate: function 'render-pdf' uses nodejs20 but the service runtime is python3.12; a service is either Python or Node.js.",
      steps=[
          S("get_validation"),
          S("ask_user", question="One service is one language (on Azure it is one Function App). I can remove `render-pdf` from this service so you can create it in a separate Node.js service with the same `pdf-jobs` queue. OK?",
            options=["yes, move it out", "no, keep it Python"], answer="yes, move it out"),
          S("propose_plan", steps=["Remove `functions.render-pdf` from this service", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.render-pdf", value=None),
      ],
      final="""A pskit service has one language, taken from `provider.runtime`, so a Node.js function can't sit in this Python service.

Removed `render-pdf`; `forms-backend` is Python only. Validate for azure: valid. Next: create a separate service (e.g. `pdf-renderer`, `runtime: nodejs20`) with a `queue: pdf-jobs` trigger; `submit` keeps sending to that queue."""),

    # ------------------------------------------------------------------ 640  azure Functions page: two provider errors
    C(640, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/events.md#queue"],
      project=proj("""service: shop-backend
provider:
  name: azure
  region: westeurope
functions:
  cart:
    handler: app.shop.cart
    events:
      - http:
          path: /cart
          method: GET
          auth: jwt
          authorizer:
            issuer: https://login.example.com/
            audience: [shop]
  fulfil:
    handler: app.shop.fulfil
    events:
      - queue: Orders
""", "shop", "cart", "fulfil"),
      user="functions page show 2 red. fix all",
      steps=[
          S("get_validation"),
          S("ask_user", question="`cart` uses JWT, which Azure doesn't support in pskit. Use `key` (function key) or `none` (public; check the token in your code)?",
            options=["key", "none"], answer="none, we check token in code"),
          S("propose_plan", steps=["`cart`: `auth: none`, remove the authorizer", "`fulfil`: queue name `orders` (lowercase)", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.cart.events.0", value={"http": {"path": "/cart", "method": "GET", "auth": "none"}}),
          S("set_config", path="functions.fulfil.events.0", value={"queue": "orders"}),
      ],
      final="""1. `cart`: `auth: jwt` isn't supported on Azure [docs/events.md#http]. Now `auth: none`; your code checks the token.
2. `fulfil`: Azure queue names must be lowercase [docs/events.md#queue]. Now `queue: orders`.

Validate for azure: valid. Producers must send to `orders`."""),
]

