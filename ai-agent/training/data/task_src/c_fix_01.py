"""Category C (fix a validation error), batch 1. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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


CONVERSATIONS = [
    # ------------------------------------------------------------------ 1  aws timeout > 900
    C(1, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#aws-aws-lambda", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: report-builder
provider:
  name: aws
  region: eu-west-1
functions:
  build-report:
    handler: app.reports.build
    timeout: 1200
    memory: 1024
    events:
      - schedule: "0 4 * * *"
""",
          "app/__init__.py": "",
          "app/reports.py": handlers("build")}),
      user="""ERROR: [functions.build-report] timeout 1200s exceeds AWS Lambda max 900s

the report job takes around 12 min, why is 1200 not allowed?""",
      steps=[
          S("get_validation"),
          S("search_docs", query="AWS Lambda max timeout",
            docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| [`gcp`]")]),
          S("propose_plan", steps=["Set `functions.build-report.timeout` to 900 (the AWS Lambda maximum)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.build-report.timeout", value=900),
      ],
      final="""AWS Lambda stops a function after at most 900 s (15 min), and pskit checks this before Terraform runs [docs/providers.md#providers]. A job of about 12 minutes still fits in 900 s.

Changed: `functions.build-report.timeout: 1200` → `900`. `pskit validate` for aws now says **Configuration is valid.**

If the report ever needs more than 15 minutes, split it into steps (a workflow runs natively on Step Functions on AWS), or run it on a provider with a longer limit, such as gcp or onprem (3600 s)."""),

    # ------------------------------------------------------------------ 2  gcp missing project
    C(2, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: photo-share
provider:
  name: gcp
  region: europe-west1
functions:
  list-photos:
    handler: app.photos.list_photos
    events:
      - http: GET /photos
""",
          "app/__init__.py": "",
          "app/photos.py": handlers("list_photos")}),
      user="the deploy page shows a red error when i press validate, something about project. i only changed the provider to google",
      steps=[
          S("get_validation"),
          S("search_docs", query="gcp provider options project required",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="```yaml", end="service_account:")]),
          S("ask_user", question="Google Cloud needs your project id (the id, not the display name, e.g. `my-shop-123456`). What is it?",
            answer="photo-share-dev-4821"),
          S("propose_plan", steps=["Set `provider.options.project` to `photo-share-dev-4821`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.project", value="photo-share-dev-4821"),
      ],
      final="""Fixed. Google Cloud always needs to know which project to deploy into, and your file didn't say yet [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

I added this to pskit.yml:

```yaml
provider:
  options:
    project: photo-share-dev-4821
```

**Validate** now says the configuration is valid. You can press **Deploy** on the Deploy page when you're ready (you need to be logged in with `gcloud auth application-default login` first)."""),

    # ------------------------------------------------------------------ 3  huawei apig_instance_id
    C(3, provider="huawei", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#huawei-functiongraph", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: kiosk-api
provider:
  name: huawei
  region: ap-southeast-1
  iam:
    role: kiosk-fgs-agency
functions:
  menu:
    handler: app.kiosk.menu
    events:
      - http: GET /menu
  order:
    handler: app.kiosk.order
    events:
      - http: POST /orders
""",
          "app/__init__.py": "",
          "app/kiosk.py": handlers("menu", "order")}),
      user="validate red on huawei prod. fix",
      steps=[
          S("get_validation"),
          S("ask_user", question="Huawei HTTP events need a dedicated API Gateway instance. What is its instance id (`provider.options.apig_instance_id`)?",
            answer="it's 5f3c0d2e9b7a4c18a6e2d4b1f0c9e8a7"),
          S("propose_plan", steps=["Set `provider.options.apig_instance_id` to the given instance id",
                                   "Validate for huawei, stage prod"]),
          S("set_config", path="provider.options.apig_instance_id", value="5f3c0d2e9b7a4c18a6e2d4b1f0c9e8a7"),
      ],
      final="""Cause: both functions have `http` events, and on Huawei those need a dedicated API Gateway instance [docs/providers.md#huawei-functiongraph].

Set `provider.options.apig_instance_id: 5f3c0d2e9b7a4c18a6e2d4b1f0c9e8a7`. `pskit validate -p huawei -s prod`: valid."""),

    # ------------------------------------------------------------------ 4  digitalocean namespace
    C(4, provider="digitalocean", stage="staging", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#digitalocean-functions"],
      project=dict(files={
          "pskit.yml": """service: link-shortener
provider:
  name: digitalocean
  region: nyc1
functions:
  shorten:
    handler: app.links.shorten
    events:
      - http: POST /shorten
  resolve:
    handler: app.links.resolve
    events:
      - http: GET /r/{code}
""",
          "app/__init__.py": "",
          "app/links.py": handlers("shorten", "resolve")}),
      user="hi, digitalocean validate say namespace is required?? what namespace mean, i dont have k8s",
      steps=[
          S("get_validation"),
          S("search_docs", query="digitalocean namespace option",
            docs=[D("docs/providers.md", "digitalocean-functions", start="```yaml", end="api_host:")]),
          S("ask_user", question="It is not Kubernetes: it is your DigitalOcean Functions namespace. Run `doctl serverless namespaces list` and paste the id (it starts with `fn-`).",
            answer="ok it show fn-7d1e4b2a-0c3f-4a9e-b6d5-2f8a1c0e9b34"),
          S("propose_plan", steps=["Set `provider.options.namespace` to `fn-7d1e4b2a-0c3f-4a9e-b6d5-2f8a1c0e9b34`",
                                   "Validate for digitalocean, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.namespace", value="fn-7d1e4b2a-0c3f-4a9e-b6d5-2f8a1c0e9b34"),
      ],
      final="""Done. A namespace on DigitalOcean is the place where your functions live (nothing to do with k8s). pskit needs it in `options.namespace` [docs/providers.md#digitalocean-functions].

Now `pskit validate` has no error any more. It still shows one WARNING: `doctl` is not found on this machine. Validate passes, but deploy runs `doctl serverless`, so install `doctl` and run `doctl auth init` before you deploy."""),

    # ------------------------------------------------------------------ 5  cloudflare queue
    C(5, provider="cloudflare", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/providers.md#cloudflare-workers", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=dict(files={
          "pskit.yml": """service: signup-flow
provider:
  name: aws
  region: us-east-1
providers:
  cloudflare:
    options:
      account_id: ${env:CLOUDFLARE_ACCOUNT_ID, 0123456789abcdef0123456789abcdef}
functions:
  signup:
    handler: app.signup.create
    events:
      - http: POST /signup
  welcome-mail:
    handler: app.signup.send_welcome
    events:
      - queue: welcome-mails
""",
          "app/__init__.py": "",
          "app/signup.py": handlers("create", "send_welcome")}),
      user="On Lambda this exact file works (API Gateway + an SQS consumer). Switched the target to Cloudflare and validate fails. What's the Workers equivalent of the SQS trigger?",
      steps=[
          S("get_validation"),
          S("search_docs", query="cloudflare workers supported triggers queue",
            docs=[D("docs/providers.md", "cloudflare-workers", start="| Trigger |", end="**Limits:**")]),
          S("ask_user", question="pskit has no queue trigger on Cloudflare Workers, so `welcome-mail` can't run there. What should I do?",
            options=["Turn `welcome-mail` off on Cloudflare only (stays on AWS)",
                     "Keep deploying this service to AWS instead"],
            answer="Turn `welcome-mail` off on Cloudflare only (stays on AWS)"),
          S("propose_plan", steps=["Add `providers.cloudflare.functions.welcome-mail.enabled: false`",
                                   "Validate for cloudflare (and keep the AWS config unchanged)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.cloudflare.functions.welcome-mail.enabled", value=False),
      ],
      final="""There is no Workers equivalent in pskit: Cloudflare supports only `http` and `schedule` triggers [docs/providers.md#cloudflare-workers].

Changed, as you chose:

```yaml
providers:
  cloudflare:
    functions:
      welcome-mail: {enabled: false}
```

`pskit validate` for cloudflare now passes. It shows two warnings: `welcome-mail` is disabled there, and Python Workers can only use Pyodide packages. On AWS nothing changed, so the SQS consumer still deploys there [docs/configuration.md#switch-something-off-on-one-cloud].

Note: on Cloudflare, `signup` can no longer hand work to the queue. Send the welcome mail directly in `signup`, or keep the whole service on AWS."""),

    # ------------------------------------------------------------------ 6  hander typo
    C(6, provider="aws", stage="dev", mode="auto", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: notes-api
provider:
  name: aws
  region: us-west-2
functions:
  api:
    hander: app.notes.handler
    events:
      - http: ANY /notes/{path+}
""",
          "app/__init__.py": "",
          "app/notes.py": handlers("handler")}),
      user="""Error: pskit.yml is invalid:
  - functions.api.handler: Field required
  - functions.api.hander: Extra inputs are not permitted

but handler IS there??""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove the misspelled key `functions.api.hander`",
                                   "Add `functions.api.handler: app.notes.handler`",
                                   "Validate for aws"]),
          S("set_config", path="functions.api.hander", value=None),
          S("set_config", path="functions.api.handler", value="app.notes.handler"),
      ],
      final="""It was a typo: the key was spelled `hander` (no "l"), so pskit saw an unknown key and no `handler` [docs/configuration.md#functions].

I renamed it to `handler: app.notes.handler`. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 7  evnets typo, azure
    C(7, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#events-triggers"],
      project=dict(files={
          "pskit.yml": """service: invoice-mailer
provider:
  name: azure
  region: westeurope
functions:
  send-invoice:
    handler: app.mailer.send_invoice
    evnets:
      - queue: invoices
  health:
    handler: app.mailer.health
    events:
      - http: GET /health
""",
          "app/__init__.py": "",
          "app/mailer.py": handlers("send_invoice", "health")}),
      user="functions page say my send-invoice have problem and i cant see the queue trigger there. azure. pls fix",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Move the trigger list from the misspelled `evnets` to `events` on `send-invoice` (queue `invoices`)",
                                   "Remove `evnets`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send-invoice.events", value=[{"queue": "invoices"}]),
          S("set_config", path="functions.send-invoice.evnets", value=None),
      ],
      final="""Fixed. In pskit.yml the key was written `evnets` instead of `events`, so the queue trigger was not read at all [docs/events.md#events-triggers].

Now `send-invoice` has:

```yaml
events:
  - queue: invoices
```

`pskit validate` for azure: valid. The queue trigger shows again on the Functions page (the queue name `invoices` is lowercase, as Azure needs)."""),

    # ------------------------------------------------------------------ 8  batch_size 0
    C(8, provider="aws", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: payments-sync
provider:
  name: aws
  region: eu-central-1
functions:
  sync:
    handler: app.sync.handle
    timeout: 60
    events:
      - queue:
          name: payment-events
          batch_size: 0
          dead_letter: payment-events-dlq
""",
          "app/__init__.py": "",
          "app/sync.py": handlers("handle")}),
      user="batch_size 0 rejected? I want no batching, one msg per invoke",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.sync.events.0.queue.batch_size` to 1 (one message per invocation)",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="functions.sync.events.0.queue.batch_size", value=1),
      ],
      final="""`batch_size` is 1-10000; "no batching" is `batch_size: 1` [docs/events.md#queue].

Set `functions.sync.events.0.queue.batch_size: 1`. `pskit validate -p aws -s staging`: valid. Leave `batch_window` unset (0) so SQS doesn't wait to fill a batch."""),

    # ------------------------------------------------------------------ 9  4-field cron on gcp
    C(9, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: stock-alerts
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, stock-alerts-dev}
functions:
  morning-digest:
    handler: app.digest.send
    events:
      - schedule:
          cron: "0 6 * *"
          timezone: America/New_York
""",
          "app/__init__.py": "",
          "app/digest.py": handlers("send")}),
      user="""Error: pskit.yml is invalid:
  - functions.morning-digest.events.0: Value error, cron must be a standard 5-field expression: 'min hour dom month dow'

It should send the digest every day at 6am New York time""",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule cron 5-field expression",
            docs=[D("docs/events.md", "schedule", end="The handler gets")]),
          S("propose_plan", steps=["Change the cron of `morning-digest` from `0 6 * *` to `0 6 * * *` (every day 06:00); keep timezone America/New_York",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.morning-digest.events.0.schedule.cron", value="0 6 * * *"),
      ],
      final="""The cron had only four fields; pskit needs standard 5-field cron: minute, hour, day of month, month, day of week [docs/events.md#schedule].

Changed `cron: "0 6 * *"` → `"0 6 * * *"` (every day at 06:00). The `timezone: America/New_York` stays, and Cloud Scheduler honours it on GCP. `pskit validate` for gcp: valid."""),

    # ------------------------------------------------------------------ 10  ${self:custom.table} missing
    C(10, provider="aws", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: orders-api
provider:
  name: aws
  region: us-east-1
  environment:
    ORDERS_TABLE: ${self:custom.table}
custom:
  region_short: use1
functions:
  get-order:
    handler: app.orders.get_order
    events:
      - http: GET /orders/{id}
""",
          "app/__init__.py": "",
          "app/orders.py": handlers("get_order")}),
      user="Validation for prod fails with `Error: unresolved variables: self:custom.table`. The DynamoDB table is called `orders-prod` and it should come from `custom` so other keys can reuse it. Please fix it without hardcoding the name in `environment`.",
      steps=[
          S("get_validation"),
          S("search_docs", query="self variable custom unresolved",
            docs=[D("docs/configuration.md", "variables", end="| `${file(path.json)}`")]),
          S("propose_plan", steps=["Add `custom.table: orders-prod` (environment keeps `${self:custom.table}`)",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="custom.table", value="orders-prod"),
      ],
      final="""`${self:custom.table}` pointed at a key that didn't exist: `custom` only had `region_short` [docs/configuration.md#variables].

Added `custom.table: orders-prod`. `ORDERS_TABLE: ${self:custom.table}` stays as it is, so other keys can reuse the same name. `pskit validate -p aws -s prod`: valid.

If the name should differ per stage, you could write `table: orders-${opt:stage}` instead."""),

    # ------------------------------------------------------------------ 11  workflow next -> missing state
    C(11, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": """service: order-flow
provider:
  name: aws
  region: eu-west-1
functions:
  check-stock:
    handler: app.flow.check_stock
  charge:
    handler: app.flow.charge
  notify:
    handler: app.flow.notify
workflows:
  place-order:
    start_at: CheckStock
    states:
      CheckStock:
        type: task
        function: check-stock
        next: Charge
      Charge:
        type: task
        function: charge
        next: Notfy
      Notify:
        type: task
        function: notify
        end: true
""",
          "app/__init__.py": "",
          "app/flow.py": handlers("check_stock", "charge", "notify")}),
      user="I made my first workflow on the Workflows page but it won't validate. I don't understand the message",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["In workflow `place-order`, change `Charge.next` from `Notfy` to `Notify`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.place-order.states.Charge.next", value="Notify"),
      ],
      final="""Small typo. The `Charge` step said "go to `Notfy` next", but your step is called `Notify`. pskit checks that every `next` points to a step that exists [docs/workflows.md#workflow-keys].

I changed `Charge` → next: `Notify`. Validate now says the configuration is valid, and the workflow runs CheckStock → Charge → Notify.

You can try it without deploying: **Deploy** page, panel *Run a workflow locally*."""),

    # ------------------------------------------------------------------ 12  onprem unknown resource
    C(12, provider="onprem", stage="dev", mode="auto", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#troubleshooting", "docs/events.md#events-backed-by-a-resource"],
      project=dict(files={
          "pskit.yml": """service: thumb-worker
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8095
functions:
  make-thumb:
    handler: app.thumbs.make
    events:
      - queue: {resource: thumbs, batch_size: 5}
""",
          "app/__init__.py": "",
          "app/thumbs.py": handlers("make")}),
      user="it say uses unknown resource thumbs. but i want pskit make the queue for me, onprem",
      steps=[
          S("get_validation"),
          S("search_docs", query="unknown resource queue event resource key",
            docs=[D("docs/resources.md", "troubleshooting", end="| `function 'x' uses unknown resource 'y'`")]),
          S("propose_plan", steps=["Add a managed queue resource `resources.thumbs: {type: queue}`",
                                   "Validate for onprem"]),
          S("set_config", path="resources.thumbs", value={"type": "queue"}),
      ],
      final="""The queue event says `resource: thumbs`, but there was no `thumbs` under `resources:` [docs/resources.md#troubleshooting].

I added:

```yaml
resources:
  thumbs: {type: queue}
```

No `external`, so pskit creates the queue itself. `pskit validate` for onprem: valid. You also see it now on the **Resources** page."""),

    # ------------------------------------------------------------------ 13  method FETCH, alibaba
    C(13, provider="alibaba", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: alibaba
  region: cn-shanghai
functions:
  products:
    handler: app.catalog.products
    events:
      - http:
          path: /products
          method: FETCH
""",
          "app/__init__.py": "",
          "app/catalog.py": handlers("products")}),
      user="alibaba validate fails on the products route, method field",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.products.events.0.http.method` to GET",
                                   "Validate for alibaba"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.products.events.0.http.method", value="GET"),
      ],
      final="""`FETCH` isn't an HTTP method; pskit accepts GET POST PUT PATCH DELETE HEAD OPTIONS ANY [docs/events.md#http].

Set `method: GET` on `products`. `pskit validate -p alibaba`: valid. Use `ANY` if the route should take every method."""),

    # ------------------------------------------------------------------ 14  {user-id} path, tencent
    C(14, provider="tencent", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: profile-svc
provider:
  name: tencent
  region: ap-guangzhou
functions:
  get-profile:
    handler: app.profiles.get_profile
    events:
      - http: GET /users/{user-id}/profile
""",
          "app/__init__.py": "",
          "app/profiles.py": FUTURE + """

def get_profile(event, ctx):
    user_id = event.http.path_params["user_id"]
    return {"user": user_id}
"""}),
      user="Tencent staging: the route `GET /users/{user-id}/profile` on get-profile is rejected by validate. The handler already reads `event.http.path_params[\"user_id\"]`, so please align the route with the code, not the other way round.",
      steps=[
          S("get_validation"),
          S("read_file", path="app/profiles.py"),
          S("propose_plan", steps=["Change the route to `GET /users/{user_id}/profile` (matches `path_params[\"user_id\"]`)",
                                   "Validate for tencent, stage staging",
                                   "Call get-profile locally with /users/42/profile"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.get-profile.events.0.http", value="GET /users/{user_id}/profile"),
          S("invoke_local", function="get-profile", method="GET", path="/users/42/profile"),
      ],
      final="""Path parameter names must be identifiers, so `{user-id}` (with a dash) is invalid; `{user_id}` is fine [docs/events.md#http].

Changed the route to `GET /users/{user_id}/profile`, matching what the handler reads. Code unchanged.

- `pskit validate -p tencent -s staging`: valid.
- Local call on `/users/42/profile`: status 200, body `{"user": "42"}`."""),

    # ------------------------------------------------------------------ 15  tencent memory 200
    C(15, provider="tencent", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#tencent-serverless-cloud-function-scf"],
      project=dict(files={
          "pskit.yml": """service: pdf-export
provider:
  name: tencent
  region: ap-shanghai
functions:
  export:
    handler: app.export.run
    memory: 200
    timeout: 120
    events:
      - http: POST /export
""",
          "app/__init__.py": "",
          "app/export.py": handlers("run")}),
      user="tencent dont like my memory 200?? on aws it was ok",
      steps=[
          S("get_validation"),
          S("search_docs", query="tencent scf memory sizes",
            docs=[D("docs/providers.md", "tencent-serverless-cloud-function-scf", start="**Limits:**")]),
          S("propose_plan", steps=["Set `functions.export.memory` to 256 (next allowed size above 200)",
                                   "Validate for tencent"]),
          S("set_config", path="functions.export.memory", value=256),
      ],
      final="""Yes, Tencent SCF only allows 64, 128 or a multiple of 128 MB. 200 is none of them [docs/providers.md#tencent-serverless-cloud-function-scf].

I set `memory: 256` for `export` (the next size above 200, so it doesn't get less memory). `pskit validate` for tencent: valid."""),

    # ------------------------------------------------------------------ 16  ibm timeout 300
    C(16, provider="ibm", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#ibm-code-engine-functions"],
      project=dict(files={
          "pskit.yml": """service: ocr-api
provider:
  name: ibm
  region: us-south
functions:
  scan:
    handler: app.ocr.scan
    timeout: 300
    memory: 2048
    events:
      - http: POST /scan
""",
          "app/__init__.py": "",
          "app/ocr.py": handlers("scan")}),
      user="""ocr-api -> IBM Cloud Code Engine [beta] stage=dev region=us-south
  1 function(s), 0 workflow(s)
  ERROR: [functions.scan] timeout 300s exceeds IBM Cloud Code Engine max 120s

can you just bump the limit?""",
      steps=[
          S("get_validation"),
          S("search_docs", query="ibm code engine max timeout",
            docs=[D("docs/providers.md", "ibm-code-engine-functions", start="**Limits:**")]),
          S("propose_plan", steps=["Set `functions.scan.timeout` to 120, the Code Engine maximum",
                                   "Validate for ibm"],
            result={"decision": "approved", "note": "ok, 120 then"}),
          S("set_config", path="functions.scan.timeout", value=120),
      ],
      final="""The limit isn't pskit's to raise: IBM Code Engine functions run for at most 120 s [docs/providers.md#ibm-code-engine-functions].

Set `functions.scan.timeout: 120`. `pskit validate` for ibm: valid.

If a scan can take longer than 2 minutes, the request will be cut off on IBM. Then the options are to make the scan faster or move this function to a provider with a longer limit (for example aws 900 s, gcp 3600 s)."""),

    # ------------------------------------------------------------------ 17  oracle schedule
    C(17, provider="oracle", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#oracle-oci-functions"],
      project=dict(files={
          "pskit.yml": """service: ledger-close
provider:
  name: oracle
  region: eu-frankfurt-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..aaaa}
    subnet_ids:
      - ${env:OCI_SUBNET_ID, ocid1.subnet.oc1..aaaa}
    image_repository: ${env:OCI_IMAGE_REPO, fra.ocir.io/mytenancy/ledger}
functions:
  close-day:
    handler: app.ledger.close_day
    timeout: 240
    events:
      - schedule: "30 23 * * *"
""",
          "app/__init__.py": "",
          "app/ledger.py": handlers("close_day")}),
      user="In serverless.yml this was a Lambda with an EventBridge cron. Ported it to pskit for OCI and prod validation fails on the schedule. Is there an OCI alarm/cron equivalent I should use?",
      steps=[
          S("get_validation"),
          S("search_docs", query="oracle oci functions triggers schedule",
            docs=[D("docs/providers.md", "oracle-oci-functions", start="| Trigger |")]),
          S("ask_user", question="pskit has no schedule trigger on OCI Functions (only http and storage). How do you want `close-day` started?",
            options=["Replace the schedule with an HTTP route that our own cron/ops job calls",
                     "Keep the schedule and deploy this service to another provider"],
            answer="Replace the schedule with an HTTP route that our own cron/ops job calls"),
          S("propose_plan", steps=["Replace the `close-day` trigger with `http: POST /jobs/close-day`",
                                   "Validate for oracle, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.close-day.events", value=[{"http": "POST /jobs/close-day"}]),
      ],
      final="""There's no schedule equivalent in pskit for OCI: Oracle Cloud Functions support only `http` and `storage` triggers [docs/providers.md#oracle-oci-functions].

As you chose, `close-day` now has `- http: POST /jobs/close-day` instead of the cron. `pskit validate -p oracle -s prod` has no errors. The remaining WARNING is the usual Oracle one: you must add an IAM policy so API Gateway may invoke the function.

Two things before your ops job calls it:
- The route is public (`auth` must be `none` on Oracle), so check a token in the handler.
- Read it from an env var, e.g. `environment: {JOB_TOKEN: ${env:JOB_TOKEN}}`, never a literal value."""),

    # ------------------------------------------------------------------ 18  azure python3.13
    C(18, provider="azure", stage="staging", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/troubleshooting.md#configuration", "docs/configuration.md#default-runtime"],
      project=dict(files={
          "pskit.yml": """service: geo-lookup
provider:
  name: azure
  region: northeurope
  runtime: python3.13
functions:
  lookup:
    handler: app.geo.lookup
    events:
      - http: GET /geo/{ip}
""",
          "app/__init__.py": "",
          "app/geo.py": handlers("lookup")}),
      user="azure staging: runtime error on validate. Keep it as new as azure allows.",
      steps=[
          S("get_validation"),
          S("search_docs", query="provider does not support python runtime pinned",
            docs=[D("docs/troubleshooting.md", "configuration", start="**`<provider> does not support python3.12`**",
                    end="(`pskit providers --json`)")]),
          S("propose_plan", steps=["Remove the pinned `provider.runtime: python3.13`, so pskit picks python3.12 (newest on Azure)",
                                   "Validate for azure, stage staging"]),
          S("set_config", path="provider.runtime", value=None),
      ],
      final="""Azure Functions run python3.9-3.12, so the pinned `python3.13` is rejected [docs/troubleshooting.md#configuration].

Removed `provider.runtime`. Without a pin pskit uses python3.12, the newest Azure supports [docs/configuration.md#default-runtime]. `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 19  onprem auth iam
    C(19, provider="onprem", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: admin-api
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8102
functions:
  admin-stats:
    handler: app.admin.stats
    events:
      - http:
          path: /admin/stats
          method: GET
          auth: iam
""",
          "app/__init__.py": "",
          "app/admin.py": handlers("stats")}),
      user="We moved admin-api from AWS to our own server (onprem, staging). The route /admin/stats had `auth: iam` on AWS and now validate refuses it. I still need the endpoint protected. What is the correct setup on-prem?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem auth none check token",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("propose_plan", steps=["Set `functions.admin-stats.events.0.http.auth` to `none` (what on-prem supports)",
                                   "Validate for onprem, stage staging",
                                   "Then: protect the route with a token check in the handler (separate change)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.admin-stats.events.0.http.auth", value="none"),
      ],
      final="""On-premises pskit can't enforce `auth: iam` (there is no IAM on your server), so validate asks for `auth: none` and a token check in the handler. `iam` works only on aws, gcp and huawei [docs/events.md#http].

Changed: `auth: iam` → `auth: none` on `/admin/stats`. `pskit validate -p onprem -s staging`: valid.

The route is **public now**, so add the protection next:
1. Set `environment: {ADMIN_TOKEN: ${env:ADMIN_TOKEN}}` on the function.
2. In `app/admin.py`, compare `event.http.headers.get("authorization")` with `ctx.env["ADMIN_TOKEN"]` and raise `Unauthorized` when they differ.

Shall I make that change?"""),

    # ------------------------------------------------------------------ 20  literal password (security fix)
    C(20, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/configuration.md#variables", "docs/troubleshooting.md#security-notes"],
      project=dict(files={
          "pskit.yml": """service: club-members
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, club-members-dev}
functions:
  members:
    handler: app.members.list_members
    environment:
      DB_HOST: db.example.com
      DB_PASSWORD: changeme-123
    events:
      - http: GET /members
""",
          "app/__init__.py": "",
          "app/members.py": handlers("list_members")}),
      user="validate is green so can i push my project to github now? my friend said check first",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Replace the literal database password in `functions.members.environment.DB_PASSWORD` with `${env:DB_PASSWORD, }` (read from your environment)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.members.environment.DB_PASSWORD", value="${env:DB_PASSWORD, }"),
      ],
      final="""Your friend was right. Validate was green, but pskit.yml had the database password written in it, so it would have gone to GitHub. Secrets should not be in YAML [docs/troubleshooting.md#security-notes].

Changed:

```yaml
environment:
  DB_HOST: db.example.com
  DB_PASSWORD: ${env:DB_PASSWORD, }
```

pskit now reads the password from the `DB_PASSWORD` environment variable [docs/configuration.md#variables]. Validate is still valid.

Before you deploy, set it: **Setup & credentials** > *Environment variables* > **Set for this session**. If you forget, the value is empty. Also change the database password, because the old one was in the file (and in your git history, if you already committed it)."""),
]
