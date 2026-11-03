"""Category C (fix a validation error), batch 26 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 501  aws storage event on a queue resource
    C(501, provider="aws", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/events.md#events-backed-by-a-resource", "docs/configuration.md#resources"],
      project=proj("""service: receipt-box
provider:
  name: aws
  region: us-east-1
resources:
  jobs: {type: queue}
functions:
  read-receipt:
    handler: app.receipts.read
    events:
      - storage: {resource: jobs}
""", "receipts", "read"),
      user="I want read-receipt to run when a photo is uploaded. I picked my resource 'jobs' in the trigger, and now it says jobs is a queue.",
      steps=[
          S("get_validation"),
          S("ask_user", question="A storage trigger needs a bucket, and `jobs` is a queue. Should I add a new bucket resource for the photos?",
            options=["Yes, add a bucket called receipts", "No, I'll pick another resource"],
            answer="Yes, add a bucket called receipts"),
          S("propose_plan", steps=["Add `resources.receipts: {type: storage}`",
                                   "Point the trigger of `read-receipt` at it: `storage: {resource: receipts}`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.receipts", value={"type": "storage"}),
          S("set_config", path="functions.read-receipt.events.0", value={"storage": {"resource": "receipts"}}),
      ],
      final="""A file trigger (`storage`) has to point at a bucket, but `jobs` is a queue [docs/events.md#events-backed-by-a-resource].

- New resource `receipts: {type: storage}` (pskit creates the S3 bucket) [docs/configuration.md#resources]
- `read-receipt` now has `storage: {resource: receipts}`

Validate: valid. The `jobs` queue is unchanged. Upload a photo to the `receipts` bucket after deploy and the function runs."""),

    # ------------------------------------------------------------------ 502  aws path param with a space
    C(502, provider="aws", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: order-status
provider:
  name: aws
  region: eu-west-1
functions:
  status:
    handler: app.status.get_status
    events:
      - http: GET /orders/{order id}/status
""",
          "app/__init__.py": "",
          "app/status.py": FUTURE + """

def get_status(event, ctx):
    order_id = event.http.path_params["order_id"]
    return {"order": order_id, "status": "shipped"}
"""}),
      user="""Error: pskit.yml is invalid:
  - functions.status.events.0.path: Value error, invalid path template '/orders/{order id}/status'; use /users/{id} or /files/{path+}""",
      steps=[
          S("get_validation"),
          S("read_file", path="app/status.py"),
          S("propose_plan", steps=["Change the route to `GET /orders/{order_id}/status` (the name the handler reads)",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.status.events.0.http", value="GET /orders/{order_id}/status"),
          S("invoke_local", function="status", method="GET", path="/orders/A-17/status"),
      ],
      final="""A path parameter name must be an identifier, so `{order id}` with a space is invalid [docs/events.md#http].

The handler already reads `path_params["order_id"]`, so the route is now `GET /orders/{order_id}/status`.
- `pskit validate -p aws -s staging`: valid.
- Local call on `/orders/A-17/status`: 200, `{"order": "A-17", "status": "shipped"}`."""),

    # ------------------------------------------------------------------ 503  aws stages.prod runtime 3.14
    C(503, provider="aws", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/providers.md#providers"],
      project=proj("""service: rates-api
provider:
  name: aws
  region: us-east-1
  runtime: python3.12
stages:
  prod:
    provider: {runtime: python3.14}
functions:
  rates:
    handler: app.rates.current
    events:
      - http: GET /rates
""", "rates", "current"),
      user="dev and staging validate fine, but prod fails with AWS Lambda does not support python3.14. Someone added a prod override to 'test the newest Python'. Prod should use the newest Python Lambda actually supports.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `stages.prod.provider.runtime` to python3.13 (newest on AWS Lambda in pskit)",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.provider.runtime", value="python3.13"),
      ],
      final="""The `stages.prod` override set `runtime: python3.14` for prod only, and AWS Lambda supports python3.9-3.13 [docs/providers.md#providers].

Changed the override to `python3.13`; dev and staging stay on 3.12 [docs/configuration.md#stages-per-stage-overrides]. `pskit validate -p aws -s prod`: valid. Run your tests on 3.13 before deploying prod, since the other stages don't use it."""),

    # ------------------------------------------------------------------ 504  aws hook entries as mappings
    C(504, provider="aws", stage="dev", mode="auto", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#hooks"],
      project=proj("""service: pricing-api
provider:
  name: aws
  region: eu-west-1
hooks:
  before_deploy:
    - run: pytest -q
functions:
  price:
    handler: app.pricing.price
    events:
      - http: GET /price
""", "pricing", "price"),
      user="hooks.before_deploy.0: Input should be a valid string. Had it as {run: ...} like a CI step.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Write the hook as a plain command string: `before_deploy: [\"pytest -q\"]`",
                                   "Validate for aws"]),
          S("set_config", path="hooks.before_deploy", value=["pytest -q"]),
      ],
      final="""Each hook is a list of plain shell command strings, no `run:` keys [docs/configuration.md#hooks].

Set `before_deploy: ["pytest -q"]`. `pskit validate` for aws: valid. A failing test run (non-zero exit) now stops the deploy."""),

    # ------------------------------------------------------------------ 505  aws nested tags
    C(505, provider="aws", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: hr-portal
provider:
  name: aws
  region: eu-north-1
  tags:
    team:
      name: people-ops
      cost_center: 4410
functions:
  portal:
    handler: app.hr.portal
    events:
      - http: GET /
""", "hr", "portal"),
      user="tags team Input should be a valid string. i want team name and cost center in tags",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Flatten the tags: `team: people-ops`, `cost_center: \"4410\"`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.tags", value={"team": "people-ops", "cost_center": "4410"}),
      ],
      final="""Tags are flat `name: value` pairs; a value can't be another mapping [docs/configuration.md#provider].

Now `tags: {team: people-ops, cost_center: "4410"}`. Validate: valid. pskit adds its own `pskit-service`, `pskit-stage` and `managed-by` tags next to yours."""),

    # ------------------------------------------------------------------ 506  aws task state without function
    C(506, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: signup-steps
provider:
  name: aws
  region: us-east-2
functions:
  create-user:
    handler: app.signup.create_user
  send-welcome:
    handler: app.signup.send_welcome
workflows:
  signup:
    start_at: Create
    states:
      Create: {type: task, function: create-user, next: Welcome}
      Welcome: {type: task, end: true}
""", "signup", "create_user", "send_welcome"),
      user="I added a Welcome step on the Workflows page with Add state, and now it says task state needs `function`.",
      steps=[
          S("get_validation"),
          S("ask_user", question="The new `Welcome` step doesn't say which function to run. Which one should it call?",
            options=["send-welcome", "create-user"], answer="send-welcome"),
          S("propose_plan", steps=["Set `workflows.signup.states.Welcome.function: send-welcome`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.signup.states.Welcome.function", value="send-welcome"),
      ],
      final="""A `task` step must name the function it calls, and `Welcome` had none [docs/workflows.md#state-types].

`Welcome` now calls `send-welcome`. Validate: valid. On the Workflows page this is the *Function* field of the step."""),

    # ------------------------------------------------------------------ 507  aws python3.8 -> default
    C(507, provider="aws", stage="staging", mode="auto", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#default-runtime"],
      project=proj("""service: invoice-pdf
provider:
  name: aws
  region: us-east-1
  runtime: python3.8
functions:
  render:
    handler: app.pdf.render
    events:
      - http: POST /invoices/{id}/pdf
""", "pdf", "render"),
      user="Lambda forced us off python3.8 anyway. pskit rejects 3.8. use whatever pskit defaults to.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `provider.runtime` (pskit picks python3.12 on AWS)",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="provider.runtime", value=None),
      ],
      final="""pskit supports python3.9 and newer, so 3.8 fails the schema check. Without a pin it uses python3.12 on AWS [docs/configuration.md#default-runtime].

Removed `provider.runtime`. `pskit validate -p aws -s staging`: valid. Test the 3.8 code on 3.12 locally first (`pskit invoke -f render -t http --method POST --path /invoices/1/pdf`)."""),

    # ------------------------------------------------------------------ 508  gcp queue event on storage resource
    C(508, provider="gcp", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#events-backed-by-a-resource"],
      project=proj("""service: scan-queue
provider:
  name: gcp
  region: europe-west1
  options:
    project: scan-queue-dev
resources:
  scans: {type: storage}
  scan-jobs: {type: queue}
functions:
  process:
    handler: app.scan.process
    events:
      - queue: {resource: scans}
""", "scan", "process"),
      user="process: queue event on resource 'scans', which is storage. meant scan-jobs",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Point the queue event of `process` at `scan-jobs`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.process.events.0.queue.resource", value="scan-jobs"),
      ],
      final="""A `queue` event must point at a queue resource; `scans` is storage [docs/events.md#events-backed-by-a-resource].

Changed it to `queue: {resource: scan-jobs}`. `pskit validate` for gcp: valid."""),

    # ------------------------------------------------------------------ 509  gcp stages.prod provider timeout 900 with a topic fn
    C(509, provider="gcp", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=proj("""service: settlement
provider:
  name: gcp
  region: europe-west1
  options:
    project: settlement-prod
stages:
  prod:
    provider: {timeout: 900}
functions:
  api:
    handler: app.settle.api
    events:
      - http: POST /settle
  on-payment:
    handler: app.settle.on_payment
    events:
      - topic: payments
""", "settle", "api", "on_payment"),
      user="Prod validation fails: on-payment is limited to 540s on GCP. The 900 s prod timeout is meant for the HTTP api only. Fix it without changing dev.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace the prod override `provider.timeout: 900` with `functions.api.timeout: 900`",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod", value={"functions": {"api": {"timeout": 900}}}),
      ],
      final="""The prod override raised the timeout for every function, including the topic-triggered `on-payment`, and event functions on GCP max out at 540 s [docs/events.md#gcp-multi-trigger-functions-are-split-automatically].

The prod override is now `stages.prod.functions.api.timeout: 900`, so only `api` gets 900 s; `on-payment` keeps the 30 s default, and dev is unchanged [docs/configuration.md#stages-per-stage-overrides]. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 510  gcp parallel branch start_at wrong
    C(510, provider="gcp", stage="staging", mode="auto", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: profile-build
provider:
  name: gcp
  region: us-central1
  options:
    project: profile-build-staging
functions:
  fetch-orders:
    handler: app.profile.fetch_orders
  fetch-reviews:
    handler: app.profile.fetch_reviews
workflows:
  build:
    start_at: Gather
    states:
      Gather:
        type: parallel
        branches:
          - start_at: Orders
            states:
              FetchOrders: {type: task, function: fetch-orders, end: true}
          - start_at: FetchReviews
            states:
              FetchReviews: {type: task, function: fetch-reviews, end: true}
        end: true
""", "profile", "fetch_orders", "fetch_reviews"),
      user="""Error: pskit.yml is invalid:
  - workflows.build.states.Gather.branches.0: Value error, start_at 'Orders' is not a defined state""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `Gather.branches.0.start_at` to `FetchOrders`",
                                   "Validate for gcp, stage staging"]),
          S("set_config", path="workflows.build.states.Gather.branches.0.start_at", value="FetchOrders"),
      ],
      final="""Branch 0 starts at `Orders`, but its only state is `FetchOrders`. A branch's `start_at` must name a state inside that branch [docs/workflows.md#state-types].

Set `start_at: FetchOrders`. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 511  gcp function-level python3.14
    C(511, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#providers"],
      project=proj("""service: text-tools
provider:
  name: gcp
  region: europe-west1
  options:
    project: text-tools-dev
functions:
  summarize:
    handler: app.text.summarize
    runtime: python3.14
    events:
      - http: POST /summarize
""", "text", "summarize"),
      user="summarize i set python 3.14 newest, gcp say not support. which is newest ok?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.summarize.runtime` to python3.13",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.summarize.runtime", value="python3.13"),
      ],
      final="""On Google Cloud Functions pskit supports python3.9 to 3.13, so 3.13 is the newest [docs/providers.md#providers].

Set `runtime: python3.13` on `summarize`. Validate: valid."""),

    # ------------------------------------------------------------------ 512  gcp providers.gcp.options string
    C(512, provider="gcp", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=proj("""service: feedback
provider:
  name: aws
  region: us-east-1
providers:
  gcp:
    region: us-central1
    options: project=feedback-gcp-221
functions:
  submit:
    handler: app.feedback.submit
    events:
      - http: POST /feedback
""", "feedback", "submit"),
      user="Adding GCP next to AWS. `options: project=feedback-gcp-221` in providers.gcp gives provider.options: Input should be a valid dictionary.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Write `providers.gcp.options` as a mapping: `{project: feedback-gcp-221}`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.gcp.options", value={"project": "feedback-gcp-221"}),
      ],
      final="""`options` is a mapping (`key: value`), not a `key=value` string. Inside `providers.gcp` it is shorthand for `provider.options` [docs/configuration.md#providers-per-cloud-overrides].

Now `providers.gcp.options: {project: feedback-gcp-221}`. `pskit validate -p gcp`: valid; AWS is unchanged."""),

    # ------------------------------------------------------------------ 513  gcp ${self:custom.mem} = "512MB"
    C(513, provider="gcp", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: batch-tools
provider:
  name: gcp
  region: europe-west4
  options:
    project: batch-tools-dev
custom:
  mem: 512MB
functions:
  split:
    handler: app.tools.split
    memory: ${self:custom.mem}
    events:
      - http: POST /split
  merge:
    handler: app.tools.merge
    memory: ${self:custom.mem}
    events:
      - http: POST /merge
""", "tools", "split", "merge"),
      user="Both functions take memory from custom.mem so we change it in one place. Validation says functions.split.memory is not a valid integer (merge too, I assume). Keep the shared custom value.",
      steps=[
          S("get_validation"),
          S("search_docs", query="variable type kept self",
            docs=[D("docs/configuration.md", "variables", start="When a value is exactly one variable", end="unresolved variables are reported together.")]),
          S("propose_plan", steps=["Set `custom.mem` to the number 512 (MB, no unit)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="custom.mem", value=512),
      ],
      final="""The variable resolved fine, but its value was the string `512MB`. A value that is exactly one variable keeps the type of what it points to, so `memory` got a string [docs/configuration.md#variables].

`custom.mem` is now the number `512`; both functions still read it with `${self:custom.mem}`. Validate: valid."""),

    # ------------------------------------------------------------------ 514  azure fifo warning -> ask
    C(514, provider="azure", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=proj("""service: ledger-writer
provider:
  name: aws
  region: us-east-1
providers:
  azure:
    region: westeurope
functions:
  write-entry:
    handler: app.ledger.write_entry
    events:
      - queue:
          name: ledger-entries
          fifo: true
""", "ledger", "write_entry"),
      user="On SQS this is a FIFO queue because entries must be written in order. Azure staging warns Storage Queues are not FIFO. What are my options?",
      steps=[
          S("get_validation"),
          S("search_docs", query="fifo azure storage queue",
            docs=[D("docs/events.md", "queue", start="| Option | aws (SQS) |", end="| partial batch failure |")]),
          S("ask_user", question="Azure Storage Queues don't keep order, so `fifo` does nothing there. Keep `write-entry` on Azure without ordering, or don't deploy it to Azure?",
            options=["Disable write-entry on Azure", "Keep it on Azure, order doesn't matter there"],
            answer="Disable write-entry on Azure"),
          S("propose_plan", steps=["Add `providers.azure.functions.write-entry.enabled: false` (AWS keeps the FIFO queue)",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.functions.write-entry.enabled", value=False),
      ],
      final="""Azure Storage Queues are not FIFO, so `fifo: true` would be ignored and entries could arrive out of order [docs/events.md#queue].

As you chose, `write-entry` is disabled on Azure only (`providers.azure.functions.write-entry.enabled: false`); on AWS it keeps its FIFO SQS queue [docs/configuration.md#switch-something-off-on-one-cloud]. `pskit validate -p azure -s staging`: valid, with only the "disabled" warning."""),

    # ------------------------------------------------------------------ 515  azure ARM_SUBSCRIPTION_ID unset
    C(515, provider="azure", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=["docs/configuration.md#variables", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: club-booking
provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID}
functions:
  book:
    handler: app.booking.book
    events:
      - http: POST /book
""", "booking", "book"),
      user="Validate says unresolved variables: env:ARM_SUBSCRIPTION_ID. I copied that line from the docs. Do I have to type my subscription id somewhere?",
      steps=[
          S("get_validation"),
          S("ask_user", question="The line reads your subscription id from the environment variable ARM_SUBSCRIPTION_ID, which isn't set here. Do you want to set the variable in studio (recommended), or should I put a default id in pskit.yml?",
            options=["I'll set the variable", "Put a default in pskit.yml"],
            answer="put a default, it's 00000000-1111-2222-3333-444444444444"),
          S("propose_plan", steps=["Set `provider.options.subscription_id` to `${env:ARM_SUBSCRIPTION_ID, 00000000-1111-2222-3333-444444444444}`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.subscription_id",
            value="${env:ARM_SUBSCRIPTION_ID, 00000000-1111-2222-3333-444444444444}"),
      ],
      final="""`${env:ARM_SUBSCRIPTION_ID}` reads an environment variable, and it isn't set on this machine, so validation stops [docs/configuration.md#variables].

Now `subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-1111-2222-3333-444444444444}`: the variable still wins when it's set, otherwise your id is used. Validate: valid.

To deploy you also need to be logged in with `az login` [docs/providers.md#azure-azure-functions]. You can set the variable later under **Setup & credentials** > *Environment variables* > **Set for this session**."""),

    # ------------------------------------------------------------------ 516  azure {*path} route
    C(516, provider="azure", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: spa-host
provider:
  name: azure
  region: westeurope
functions:
  files:
    handler: app.spa.files
    events:
      - http: GET /static/{*path}
""", "spa", "files"),
      user="invalid path template '/static/{*path}'. that's azure catch-all syntax",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Change the route of `files` to `GET /static/{path+}`",
                                   "Validate for azure"]),
          S("set_config", path="functions.files.events.0.http", value="GET /static/{path+}"),
      ],
      final="""pskit.yml uses the portable greedy form `{path+}`; pskit converts it to Azure's `{*path}` itself [docs/providers.md#azure-azure-functions] [docs/events.md#http].

Route is now `GET /static/{path+}`. `pskit validate` for azure: valid. The rest of the path arrives in `event.http.path_params["path"]`."""),

    # ------------------------------------------------------------------ 517  azure auth function
    C(517, provider="azure", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: admin-tools
provider:
  name: azure
  region: northeurope
functions:
  purge-cache:
    handler: app.admin.purge_cache
    events:
      - http:
          path: /admin/purge
          method: POST
          auth: function
""", "admin", "purge_cache"),
      user="in azure portal auth level is 'function', pskit say should be none iam jwt or key",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure auth key function level",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("propose_plan", steps=["Set `auth` of `/admin/purge` to `key` (= Azure AuthLevel.FUNCTION)",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.purge-cache.events.0.http.auth", value="key"),
      ],
      final="""In pskit the Azure "function" auth level is called `key`; it becomes `AuthLevel.FUNCTION` [docs/events.md#http].

Set `auth: key` on `/admin/purge`. `pskit validate -p azure -s prod`: valid. Callers must send the function key."""),

    # ------------------------------------------------------------------ 518  azure native retry warnings
    C(518, provider="azure", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#compiler-notes-and-limits"],
      project=proj("""service: sync-flow
provider:
  name: azure
  region: westeurope
functions:
  pull:
    handler: app.sync.pull
workflows:
  sync:
    engine: native
    start_at: Pull
    states:
      Pull:
        type: task
        function: pull
        retry:
          - errors: [TimeoutError]
            max_attempts: 2
          - errors: ["*"]
            max_attempts: 5
        end: true
""", "sync", "pull"),
      user="Validation passes for the native sync workflow but gives two retry warnings for Pull. I want the config to match what Logic Apps really does, so no warnings.",
      steps=[
          S("get_validation"),
          S("search_docs", query="logic apps retry first rule errors ignored",
            docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="Only the **first** retry rule of a task is used", end="at most 90 retries).")]),
          S("propose_plan", steps=["Replace the two retry rules of `Pull` with one rule `{errors: [\"*\"], max_attempts: 2}` (the attempts Logic Apps actually uses)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": "use 5 attempts, not 2"}),
          S("set_config", path="workflows.sync.states.Pull.retry", value=[{"errors": ["*"], "max_attempts": 5}]),
      ],
      final="""Logic Apps use only the first retry rule, and they retry HTTP 408/429/5xx responses, so the `errors` filter can't be honoured [docs/workflows.md#compiler-notes-and-limits].

Following your note, `Pull` now has one rule: `{errors: ["*"], max_attempts: 5}`. `pskit validate -p azure`: valid, no warnings."""),

    # ------------------------------------------------------------------ 519  azure native map max_concurrency warning
    C(519, provider="azure", stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#compiler-notes-and-limits"],
      project=proj("""service: image-batch
provider:
  name: azure
  region: westeurope
functions:
  resize:
    handler: app.images.resize
workflows:
  batch:
    engine: native
    start_at: Each
    states:
      Each:
        type: map
        items_path: $.images
        max_concurrency: 10
        iterator:
          start_at: Resize
          states:
            Resize: {type: task, function: resize, end: true}
        end: true
""", "images", "resize"),
      user="warning: map iterations run one at a time on Azure. drop the ignored key",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `max_concurrency` from `Each`",
                                   "Validate for azure, stage staging"]),
          S("set_config", path="workflows.batch.states.Each.max_concurrency", value=None),
      ],
      final="""On Logic Apps `map` iterations run one at a time, so `max_concurrency` is ignored [docs/workflows.md#compiler-notes-and-limits].

Removed it. `pskit validate -p azure -s staging`: valid; the native engine itself still processes images one by one."""),

    # ------------------------------------------------------------------ 520  azure stages.prod function timeout 900
    C(520, provider="azure", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/providers.md#providers"],
      project=proj("""service: nightly-etl
provider:
  name: azure
  region: westeurope
functions:
  etl:
    handler: app.etl.run
    timeout: 300
    events:
      - schedule: "0 2 * * *"
stages:
  prod:
    functions:
      etl: {timeout: 900}
""", "etl", "run"),
      user="""nightly-etl -> Azure Functions [stable] stage=prod region=westeurope
  1 function(s), 0 workflow(s)
  ERROR: [functions.etl] timeout 900s exceeds Azure Functions max 600s

only prod""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `stages.prod.functions.etl.timeout` to 600 (Azure max)",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.functions.etl.timeout", value=600),
      ],
      final="""Only prod failed because the `stages.prod` override sets 900 s, above Azure's 600 s limit [docs/providers.md#providers].

The prod override is now `timeout: 600`; other stages keep 300 [docs/configuration.md#stages-per-stage-overrides]. `pskit validate -p azure -s prod`: valid."""),
]
