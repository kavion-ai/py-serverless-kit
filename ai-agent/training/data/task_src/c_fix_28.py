"""Category C (fix a validation error), batch 28 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 541  aws resource keys clash after adding a cache
    C(541, provider="aws", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#fields"],
      project=proj("""service: order-desk
provider:
  name: aws
  region: eu-central-1
resources:
  orders-db:
    type: database
    external: true
    connection:
      host: orders.db.example.com
      port: 5432
  orders_db:
    type: cache
    external: true
    connection:
      host: orders.cache.example.com
      port: 6379
functions:
  orders:
    handler: app.orders.list_orders
    events:
      - http: GET /orders
""", "orders", "list_orders"),
      user="""Just added the Redis cache on the Resources page and now:

Error: pskit.yml is invalid:
  - resources: Value error, resources 'orders-db' and 'orders_db' map to the same variable prefix ORDERS_DB""",
      steps=[
          S("get_validation"),
          S("search_docs", query="resource key variable prefix PSKIT_RESOURCE",
            docs=[D("docs/resources.md", "fields", start="| `functions` |")]),
          S("propose_plan", steps=["Rename the cache resource `orders_db` to `orders-cache` (same type and connection)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.orders_db", value=None),
          S("set_config", path="resources.orders-cache",
            value={"type": "cache", "external": True,
                   "connection": {"host": "orders.cache.example.com", "port": 6379}}),
      ],
      final="""Handlers get each resource as `PSKIT_RESOURCE_<KEY>_*`, and both `orders-db` and `orders_db` become `ORDERS_DB`, so the keys must differ after that conversion [docs/resources.md#fields].

I renamed the cache to `orders-cache` (same host and port); handlers now read it as `PSKIT_RESOURCE_ORDERS_CACHE_HOST`. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 542  gcp queue event lost its name in the form
    C(542, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=proj("""service: sms-sender
provider:
  name: gcp
  region: asia-south1
  options:
    project: sms-sender-dev
functions:
  send-sms:
    handler: app.sms.send
    events:
      - queue:
          batch_size: 5
""", "sms", "send"),
      user="i edit trigger of send-sms and now red: queue event needs name or resource. what name i must put??",
      steps=[
          S("get_validation"),
          S("ask_user", question="The trigger lost its queue name. Which queue (on GCP: Pub/Sub topic) should `send-sms` read from? Is it created by this service or does it exist already?",
            options=["sms-outbox, create it", "sms-outbox, already exists", "another name"],
            answer="sms-outbox, already exists"),
          S("propose_plan", steps=["Set the queue event of `send-sms` to `name: sms-outbox`, `existing: true` (keep batch_size 5)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send-sms.events.0.queue",
            value={"name": "sms-outbox", "existing": True, "batch_size": 5}),
      ],
      final="""A queue trigger must say which queue it reads, with `name` or `resource`; the edit left only `batch_size` [docs/events.md#queue].

Now `queue: {name: sms-outbox, existing: true, batch_size: 5}`, so pskit uses your topic and does not create it. Validate: valid. Note: on GCP `batch_size` is ignored [docs/events.md#queue]."""),

    # ------------------------------------------------------------------ 543  azure storage event without container
    C(543, provider="azure", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage"],
      project=proj("""service: invoice-ocr
provider:
  name: azure
  region: westeurope
functions:
  read-invoice:
    handler: app.ocr.read_invoice
    events:
      - storage:
          prefix: incoming/
          suffix: .pdf
""", "ocr", "read_invoice"),
      user="I want read-invoice to run when a PDF is uploaded. I set the prefix and suffix but it says storage event needs bucket or resource. Isn't the bucket automatic on Azure?",
      steps=[
          S("get_validation"),
          S("ask_user", question="Which blob container should it watch? (3-63 lowercase letters, digits or dashes)",
            answer="invoices"),
          S("propose_plan", steps=["Add `bucket: invoices` to the storage event of `read-invoice` (keep prefix and suffix)",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.read-invoice.events.0.storage.bucket", value="invoices"),
      ],
      final="""The storage account is automatic on Azure, but the container is not: a storage event needs `bucket` (the container) or a `resource` [docs/events.md#storage].

Added `bucket: invoices`; `incoming/` and `.pdf` still filter the blobs. `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 544  aws wait state without seconds
    C(544, provider="aws", stage="dev", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: signup-drip
provider:
  name: aws
  region: us-east-1
functions:
  welcome:
    handler: app.drip.welcome
  tips:
    handler: app.drip.tips
workflows:
  drip:
    start_at: Welcome
    states:
      Welcome: {type: task, function: welcome, next: Pause}
      Pause: {type: wait, next: Tips}
      Tips: {type: task, function: tips, end: true}
""", "drip", "welcome", "tips"),
      user="wait state needs seconds or seconds_path. Pause should be 1 day",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.drip.states.Pause.seconds` to 86400",
                                   "Validate for aws"]),
          S("set_config", path="workflows.drip.states.Pause.seconds", value=86400),
      ],
      final="""A `wait` state needs `seconds` (fixed) or `seconds_path` (read from the data) [docs/workflows.md#state-types].

Set `seconds: 86400` (1 day) on `Pause`. Validate for aws: valid (Step Functions)."""),

    # ------------------------------------------------------------------ 545  gcp parallel state without branches
    C(545, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: photo-pipeline
provider:
  name: gcp
  region: europe-west1
  options:
    project: photo-pipeline-dev
functions:
  resize:
    handler: app.photos.resize
  tag:
    handler: app.photos.tag
  publish:
    handler: app.photos.publish
workflows:
  process-photo:
    start_at: Fan
    states:
      Fan: {type: parallel, next: Publish}
      Publish: {type: task, function: publish, end: true}
""", "photos", "resize", "tag", "publish"),
      user="In process-photo I added a parallel state `Fan` but didn't get to the branches yet. It should run `resize` and `tag` at the same time, then `Publish`. Now the workflow won't validate: parallel state needs branches.",
      steps=[
          S("get_validation"),
          S("search_docs", query="parallel state branches",
            docs=[D("docs/workflows.md", "state-types", end="| `map` |")]),
          S("propose_plan", steps=["Give `Fan` two branches: `Resize` (task resize) and `Tag` (task tag)",
                                   "Keep `next: Publish`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.process-photo.states.Fan",
            value={"type": "parallel", "next": "Publish", "branches": [
                {"start_at": "Resize", "states": {"Resize": {"type": "task", "function": "resize", "end": True}}},
                {"start_at": "Tag", "states": {"Tag": {"type": "task", "function": "tag", "end": True}}}]}),
      ],
      final="""A `parallel` state must list its `branches`, each a small `{start_at, states}` machine [docs/workflows.md#state-types].

`Fan` now has two branches, `Resize` and `Tag`, then goes to `Publish`. `Publish` receives a list with one result per branch. Validate for gcp: valid (Cloud Workflows)."""),

    # ------------------------------------------------------------------ 546  gcp resource + second bucket
    C(546, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/resources.md#using-a-resource-from-an-event", "docs/events.md#storage"],
      project=proj("""service: media-index
provider:
  name: gcp
  region: us-central1
  options:
    project: media-index-staging
resources:
  uploads:
    type: storage
functions:
  index-upload:
    handler: app.index.on_upload
    events:
      - storage: {resource: uploads}
  index-archive:
    handler: app.index.on_archive
    events:
      - storage: {resource: uploads, bucket: media-archive-staging}
""", "index", "on_upload", "on_archive"),
      user="index-archive should watch our existing archive bucket media-archive-staging (made by another team). I wrote it as resource: uploads + bucket, because on-prem that worked. GCP staging says use one of them.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Change the storage event of `index-archive` to `bucket: media-archive-staging`, `existing: true` (no resource)",
                                   "Leave `index-upload` on the `uploads` resource",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.index-archive.events.0.storage",
            value={"bucket": "media-archive-staging", "existing": True}),
      ],
      final="""Another bucket on a resource's service is an on-premises feature; on GCP a storage event uses either the resource or a bucket [docs/resources.md#using-a-resource-from-an-event].

`index-archive` now has `storage: {bucket: media-archive-staging, existing: true}`, so pskit only adds the trigger and never creates or deletes that bucket [docs/events.md#storage]. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 547  azure resource + bucket = resource key
    C(547, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/resources.md#using-a-resource-from-an-event"],
      project=proj("""service: scan-intake
provider:
  name: azure
  region: northeurope
resources:
  scans:
    type: storage
    name: scans-raw
functions:
  ingest-scan:
    handler: app.scans.ingest
    events:
      - storage: {resource: scans, bucket: scans}
""", "scans", "ingest"),
      user="storage event sets both resource: scans and bucket: scans ?? it is same thing, why error",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `bucket` from the storage event of `ingest-scan`; the resource gives the container `scans-raw`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest-scan.events.0.storage", value={"resource": "scans"}),
      ],
      final="""It is not the same: `scans` is the resource key, but the resource's container name is `scans-raw` (its `name`), so `bucket: scans` pointed at a different container [docs/resources.md#using-a-resource-from-an-event].

Now the event is just `storage: {resource: scans}`, which means container `scans-raw`. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 548  aws prod-only stages.providers typo
    C(548, provider="aws", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/configuration.md#precedence-later-wins"],
      project=proj("""service: ledger-api
provider:
  name: aws
  region: eu-west-1
stages:
  prod:
    provider:
      memory: 1024
    providers:
      amazon:
        state:
          backend: s3
          config:
            bucket: ledger-tfstate
            key: ledger-api/prod.tfstate
            region: eu-west-1
functions:
  entries:
    handler: app.ledger.entries
    events:
      - http: GET /entries
""", "ledger", "entries"),
      user="""dev deploys fine, prod validate:

Error: `stages.prod.providers` has unknown keys ['amazon']; supported: alibaba, aws, azure, cloudflare, digitalocean, gcp, huawei, ibm, onprem, oracle, tencent""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `stages.prod.providers.amazon` to `stages.prod.providers.aws` (same state backend)",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.providers",
            value={"aws": {"state": {"backend": "s3", "config": {
                "bucket": "ledger-tfstate", "key": "ledger-api/prod.tfstate", "region": "eu-west-1"}}}}),
      ],
      final="""`stages.prod.providers` is only read for the prod stage, which is why dev passed; its keys must be provider names, and AWS is `aws` [docs/configuration.md#precedence-later-wins].

Renamed `amazon` to `aws`; the S3 state backend is unchanged. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 549  aws retry max_attempts 100, note changes it
    C(549, provider="aws", stage="staging", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#retry-and-catch"],
      project=proj("""service: payout-flow
provider:
  name: aws
  region: us-east-2
functions:
  pay:
    handler: app.payout.pay
  alert:
    handler: app.payout.alert
workflows:
  payout:
    start_at: Pay
    states:
      Pay:
        type: task
        function: pay
        retry:
          - errors: [ConnectionError]
            max_attempts: 100
        next: Done
      Alert: {type: task, function: alert, end: true}
      Done: {type: succeed}
""", "payout", "pay", "alert"),
      user="In Step Functions I had MaxAttempts 100 on the payment call. pskit says max_attempts must be <= 99. What's the closest?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `max_attempts` of the `Pay` retry to 99 (the maximum)",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved",
                    "note": "Use 10 instead, and when retries run out go to Alert (catch everything)."}),
          S("set_config", path="workflows.payout.states.Pay.retry.0.max_attempts", value=10),
          S("set_config", path="workflows.payout.states.Pay.catch", value=[{"errors": ["*"], "next": "Alert"}]),
      ],
      final="""pskit allows 0-99 retry attempts [docs/workflows.md#retry-and-catch].

As you asked: `max_attempts: 10` for `ConnectionError`, plus `catch: [{errors: ["*"], next: Alert}]`, so a payment that still fails goes to `Alert`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 550  gcp tab in YAML mode
    C(550, provider="gcp", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#top-level"],
      project=dict(files={
          "pskit.yml": "service: shift-planner\nprovider:\n  name: gcp\n  region: europe-west3\n  options:\n\tproject: shift-planner-dev\nfunctions:\n  plan:\n    handler: app.shifts.plan\n    events:\n      - http: GET /plan\n",
          "app/__init__.py": "",
          "app/shifts.py": handlers("plan"),
      }),
      user="I edited the project id in YAML mode and now nothing works: invalid YAML, found character '\\t' that cannot start any token. What did I break?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace the tab before `project:` with 4 spaces (pskit.yml must be indented with spaces)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="pskit.yml",
            content="service: shift-planner\nprovider:\n  name: gcp\n  region: europe-west3\n  options:\n    project: shift-planner-dev\nfunctions:\n  plan:\n    handler: app.shifts.plan\n    events:\n      - http: GET /plan\n"),
          S("validate"),
      ],
      final="""Line 6 started with a Tab key character; YAML only accepts spaces for indentation.

I replaced it with 4 spaces under `options:`; nothing else changed. Validate for gcp: valid. Tip: in YAML mode indent with the space bar, not Tab."""),

    # ------------------------------------------------------------------ 551  azure topic event emptied
    C(551, provider="azure", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic"],
      project=proj("""service: loyalty-points
provider:
  name: azure
  region: westeurope
functions:
  award:
    handler: app.points.award
    events:
      - topic:
""", "points", "award"),
      user="award: topic event needs name or resource. it's purchase-completed, created by this service",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the trigger of `award` to `topic: purchase-completed`",
                                   "Validate for azure"]),
          S("set_config", path="functions.award.events.0", value={"topic": "purchase-completed"}),
      ],
      final="""`- topic:` had no value, and a topic trigger needs `name` or `resource` [docs/events.md#topic].

Set `- topic: purchase-completed`; pskit creates the Service Bus topic and a subscription for `award`. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 552  azure -> aws switch, auth key
    C(552, provider="aws", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=proj("""service: partner-feed
provider:
  name: aws
  region: us-east-1
functions:
  feed:
    handler: app.feed.get_feed
    events:
      - http:
          path: /feed
          method: GET
          auth: key
""", "feed", "get_feed"),
      user="We're moving partner-feed from Azure to AWS. I changed the provider to aws on the Overview page and now validate says API keys are not available on API Gateway HTTP APIs. On Azure partners sent a function key. What are my options?",
      steps=[
          S("get_validation"),
          S("search_docs", query="http auth options aws iam jwt",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", question="On AWS `/feed` can use `jwt` (partners send a token from your identity provider; I need its issuer and audience) or `iam` (partners sign requests with AWS credentials). Which one?",
            options=["jwt", "iam"], answer="iam, they all have AWS accounts"),
          S("propose_plan", steps=["Set `auth: iam` on `/feed`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.feed.events.0.http.auth", value="iam"),
      ],
      final="""Azure function keys have no equivalent on API Gateway HTTP APIs, so `auth: key` is rejected on AWS [docs/events.md#http].

Set `auth: iam` on `/feed`; partners must now sign requests (SigV4) with AWS credentials that may invoke it. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 553  gcp sqs -> queue reveals the 540 s limit
    C(553, provider="gcp", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: video-transcode
provider:
  name: gcp
  region: us-central1
  options:
    project: video-transcode-dev
functions:
  transcode:
    handler: app.video.transcode
    timeout: 900
    events:
      - sqs: transcode-jobs
""", "video", "transcode"),
      user="Porting a Lambda: `- sqs: transcode-jobs` with timeout 900. pskit says unknown event type 'sqs'.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `sqs: transcode-jobs` with the portable `queue: transcode-jobs`",
                                   "Validate for gcp and fix anything that shows up next"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.transcode.events.0", value={"queue": "transcode-jobs"}),
          S("propose_plan", say="The trigger is fixed, but now GCP rejects the 900 s timeout for a queue-triggered function.",
            steps=["Set `functions.transcode.timeout` to 540 (GCP maximum for event-triggered functions)",
                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.transcode.timeout", value=540),
      ],
      final="""Two things: the trigger is `queue` on every cloud (`sqs` is the AWS service), and once it was a real trigger, GCP's limit for event-triggered functions applied: 540 s, not 900 [docs/events.md#queue].

- `- queue: transcode-jobs` (a Pub/Sub topic with a push trigger on GCP)
- `timeout: 540`

Validate for gcp: valid. If a video can take longer than 9 minutes, split the work into smaller jobs."""),

    # ------------------------------------------------------------------ 554  azure logicapps engine reveals glob
    C(554, provider="azure", stage="staging", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#compiler-notes-and-limits"],
      project=proj("""service: sku-router
provider:
  name: azure
  region: westeurope
functions:
  eu-orders:
    handler: app.router.eu
  other-orders:
    handler: app.router.other
workflows:
  route:
    engine: logicapp
    start_at: Check
    states:
      Check:
        type: choice
        choices:
          - {variable: $.sku, matches: "SKU-*-EU", next: Eu}
        default: Other
      Eu: {type: task, function: eu-orders, end: true}
      Other: {type: task, function: other-orders, end: true}
""", "router", "eu", "other"),
      user="route: engine logicapp invalid. want it on Logic Apps",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.route.engine` to `native` (Logic App on Azure)", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.route.engine", value="native"),
          S("search_docs", say="Engine accepted; the Logic Apps compiler now rejects the `SKU-*-EU` pattern.",
            query="logic apps matches pattern limits",
            docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="- **Azure (Logic Apps):**", words=400)]),
          S("ask_user", question="Logic Apps can only do prefix, suffix or contains patterns. `SKU-*-EU` means \"starts with SKU- and ends with -EU\". Can I check just the ending `*-EU`?",
            options=["yes, *-EU is enough", "no, keep both checks"], answer="yes, *-EU is enough"),
          S("set_config", path="workflows.route.states.Check.choices.0.matches", value="*-EU"),
      ],
      final="""`engine` takes `auto`, `native` or `embedded`; on Azure, `native` means a Logic App [docs/workflows.md#workflow-keys]. Logic Apps can't do a `*` in the middle of a pattern, only `abc*`, `*abc` or `*abc*` [docs/workflows.md#compiler-notes-and-limits].

- `engine: native`
- `Check` rule: `matches: "*-EU"`

`pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 555  aws duplicated function, same route
    C(555, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=proj("""service: bookshop-api
provider:
  name: aws
  region: eu-west-2
functions:
  books:
    handler: app.books.list_books
    events:
      - http: GET /books
  books-copy:
    handler: app.books.list_books_v2
    events:
      - http: GET /books
""", "books", "list_books", "list_books_v2"),
      user="I clicked Duplicate on books to make a new version and changed the handler. Now it says route GET /books is used by both 'books' and 'books-copy'.",
      steps=[
          S("get_validation"),
          S("ask_user", question="Duplicate copies the route too. Which path should the new version answer on?",
            options=["/v2/books", "something else"], answer="/v2/books"),
          S("propose_plan", steps=["Set the route of `books-copy` to `GET /v2/books`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.books-copy.events.0", value={"http": "GET /v2/books"}),
      ],
      final="""Each method + path can belong to only one function, and the duplicate kept `GET /books` [docs/events.md#http].

`books-copy` now answers `GET /v2/books`; `books` keeps `GET /books`. Validate for aws: valid. You can also rename `books-copy` (row button **Rename**) to something like `books-v2`."""),

    # ------------------------------------------------------------------ 556  gcp choice state without rules
    C(556, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#choice-rules"],
      project=proj("""service: ticket-triage
provider:
  name: gcp
  region: europe-west1
  options:
    project: ticket-triage-staging
functions:
  escalate:
    handler: app.tickets.escalate
  enqueue:
    handler: app.tickets.enqueue
workflows:
  triage:
    start_at: Route
    states:
      Route: {type: choice, default: Queue}
      Escalate: {type: task, function: escalate, end: true}
      Queue: {type: task, function: enqueue, end: true}
""", "tickets", "escalate", "enqueue"),
      user="i add state Route type choice and now: choice state needs choices. i not understand",
      steps=[
          S("get_validation"),
          S("ask_user", question="A choice state needs at least one rule. What should `Route` check to send a ticket to `Escalate`?",
            answer="if priority is high go Escalate, else Queue"),
          S("propose_plan", steps=["Add the rule `{variable: $.priority, equals: high, next: Escalate}` to `Route` (default stays `Queue`)",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.triage.states.Route.choices",
            value=[{"variable": "$.priority", "equals": "high", "next": "Escalate"}]),
      ],
      final="""A `choice` state picks the next state with rules in `choices`; `Route` had only a `default` [docs/workflows.md#choice-rules].

Added: `priority == "high"` goes to `Escalate`, everything else to `Queue`. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 557  azure prod-only queue override uppercase
    C(557, provider="azure", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/events.md#queue"],
      project=proj("""service: email-digest
provider:
  name: azure
  region: westeurope
stages:
  prod:
    functions:
      digest:
        events:
          - queue: Digest-Prod
functions:
  digest:
    handler: app.digest.build
    events:
      - queue: digest-dev
""", "digest", "build"),
      user="Staging and dev pass, but when I pick stage prod on the Deploy page Validate shows: queue name 'Digest-Prod' must be 3-63 lowercase letters, digits, dashes. Prod uses its own queue, that's why there's a stages override.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Change the prod override queue to `digest-prod` (lowercase)", "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.functions.digest.events", value=[{"queue": "digest-prod"}]),
      ],
      final="""The error only appears for prod because the `Digest-Prod` name comes from `stages.prod`, and Azure Storage Queue names must be lowercase [docs/events.md#queue].

The prod override is now `- queue: digest-prod`; dev still uses `digest-dev`. `pskit validate -p azure -s prod`: valid."""),

    # ------------------------------------------------------------------ 558  aws schedule with neither rate nor cron
    C(558, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=proj("""service: stock-alerts
provider:
  name: aws
  region: us-east-1
functions:
  low-stock:
    handler: app.stock.check
    events:
      - schedule:
          input: {threshold: 5}
          timezone: America/New_York
""", "stock", "check"),
      user="I made a schedule trigger with an input and time zone, but it says schedule needs exactly one of rate or cron. I thought the time zone was enough?",
      steps=[
          S("get_validation"),
          S("ask_user", question="The time zone only says how to read the time; the trigger still needs *when* to run. How often should `low-stock` run?",
            options=["every hour", "every day at 08:00", "other"], answer="every weekday at 8 in the morning"),
          S("propose_plan", steps=["Add `cron: \"0 8 * * 1-5\"` to the schedule of `low-stock` (input and time zone stay)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.low-stock.events.0.schedule.cron", value="0 8 * * 1-5"),
      ],
      final="""A schedule needs exactly one of `rate` or `cron`; `timezone` and `input` are extras [docs/events.md#schedule].

Added `cron: "0 8 * * 1-5"`: Monday to Friday at 08:00 New York time, with `event.data == {"threshold": 5}`. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 559  gcp topic event with only a filter
    C(559, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#topic"],
      project=proj("""service: billing-hooks
provider:
  name: gcp
  region: us-east1
  options:
    project: billing-hooks-dev
functions:
  on-invoice:
    handler: app.billing.on_invoice
    events:
      - topic:
          filter: {type: [invoice.paid]}
""", "billing", "on_invoice"),
      user="""Error: pskit.yml is invalid:
  - functions.on-invoice.events.0: Value error, topic event needs `name` or `resource`

the topic is billing-events, it exists already""",
      steps=[
          S("get_validation"),
          S("search_docs", query="topic filter gcp",
            docs=[D("docs/events.md", "topic", start="| Provider | Service | `filter` |", end="| azure |")]),
          S("propose_plan", steps=["Set `name: billing-events`, `existing: true` on the topic event of `on-invoice`",
                                   "Drop `filter` (not applied on GCP) and check `type` in the handler",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.on-invoice.events.0.topic",
            value={"name": "billing-events", "existing": True}),
      ],
      final="""The topic trigger had a filter but no `name`, which is required [docs/events.md#topic].

Now `topic: {name: billing-events, existing: true}`. I also removed `filter`, because Pub/Sub doesn't apply it on GCP; check `type == "invoice.paid"` in `on_invoice` instead [docs/events.md#topic]. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 560  gcp -> azure switch, auth iam
    C(560, provider="azure", stage="staging", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: hr-portal
provider:
  name: azure
  region: westeurope
functions:
  employees:
    handler: app.hr.employees
    events:
      - http:
          path: /employees
          method: GET
          auth: iam
""", "hr", "employees"),
      user="we move from gcp to azure, i change provider. now: http auth 'iam' is not supported on Azure. on gcp it was iam. what to do",
      steps=[
          S("get_validation"),
          S("ask_user", question="On Azure `/employees` can be `key` (callers send a function key) or `none` (public, check the login in your code or put Easy Auth / API Management in front). Which one?",
            options=["key", "none"], answer="key"),
          S("propose_plan", steps=["Set `auth: key` on `/employees`", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.employees.events.0.http.auth", value="key"),
      ],
      final="""Azure has no IAM-signed calls like GCP, so pskit allows only `none` or `key` there [docs/events.md#http].

Set `auth: key`; callers now need the function key. `pskit validate -p azure -s staging`: valid."""),
]
