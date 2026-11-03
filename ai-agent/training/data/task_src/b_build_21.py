"""Category B (build / add), batch 21 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 401
    B(401, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: aws
  region: eu-central-1
functions:
  bill:
    handler: app.billing.bill
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """from py_serverless_kit import BatchResult


def bill(event, ctx):
    result = BatchResult()
    for record in event.records:
        job = record.json(default={}) or {}
        if not job.get("customer"):
            result.fail(record)
    return result
""",
          "requirements.txt": ""}),
      user="In our SAM template `bill` had an SQS event on the queue billing-jobs, BatchSize 5. That queue is still owned by the old CloudFormation stack, so pskit must not create it. Can you wire that up?",
      steps=[
          S("get_project"),
          S("search_docs", query="SAM SQS BatchSize existing queue",
            docs=[D("docs/migrating-from-aws.md", "step-2-translate-the-sam-serverless-cdk-definition", end="Use `existing: true`")]),
          S("propose_plan", steps=["Add `- queue: {name: billing-jobs, batch_size: 5, existing: true}` to `bill`",
                                   "Validate for aws and run two messages locally (one good, one without customer)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.bill.events",
            value=[{"queue": {"name": "billing-jobs", "batch_size": 5, "existing": True}}]),
          S("invoke_local", function="bill", type="queue", data=[{"customer": "c-17"}, {"amount": 4}]),
      ],
      final="""Wired up. `bill` now reads the existing queue:

```yaml
functions:
  bill:
    handler: app.billing.bill
    events:
      - queue: {name: billing-jobs, batch_size: 5, existing: true}
```

- `existing: true` means pskit only adds the event source mapping. It never creates or deletes `billing-jobs` [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition].
- `pskit validate` (aws): valid.
- Local run with one good and one bad message: `batchItemFailures` lists only the message without `customer`, the same as `ReportBatchItemFailures` in SAM.

Run it again: `pskit invoke -f bill -t queue -d '[{"customer": "c-1"}]'` or **Test** > **▶ Run locally**. Deploy: **Deploy** page or `pskit deploy -s dev`. Once the old stack is gone, drop `existing: true` if you want pskit to own the queue."""),

    # ------------------------------------------------------------------ 402
    B(402, provider="gcp", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#variables", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: inventory
provider:
  name: gcp
  region: europe-west3
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, acme-inventory}
functions: {}
""",
          "requirements.txt": ""}),
      user="gcp: fn `meta` with GET /health and GET /version. version comes from env APP_VERSION (CI sets it), default 0.0.0-dev",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/meta.py`: /health -> {ok}, /version -> APP_VERSION from ctx.env",
                                   "Add function `meta` with both routes and environment APP_VERSION: ${env:APP_VERSION, 0.0.0-dev}",
                                   "Validate for gcp (staging), invoke /version"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/meta.py", content=FUTURE + """

def meta(event, ctx):
    if event.http.path == "/version":
        return {"version": ctx.env.get("APP_VERSION", "unknown")}
    return {"ok": True}
"""),
          S("set_config", path="functions.meta",
            value={"handler": "app.meta.meta",
                   "environment": {"APP_VERSION": "${env:APP_VERSION, 0.0.0-dev}"},
                   "events": [{"http": "GET /health"}, {"http": "GET /version"}]}),
          S("invoke_local", function="meta", method="GET", path="/version"),
      ],
      final="""Added `meta`:

```yaml
functions:
  meta:
    handler: app.meta.meta
    environment:
      APP_VERSION: ${env:APP_VERSION, 0.0.0-dev}
    events:
      - http: GET /health
      - http: GET /version
```

- validate (gcp, staging): valid.
- invoke `GET /version`: 200 `{"version": "0.0.0-dev"}` (APP_VERSION isn't set here, so the default was used) [docs/configuration.md#variables].

`${env:...}` is resolved when you validate/deploy, so CI must export APP_VERSION before `pskit deploy -s staging` (or use the **Deploy** page). Retest: `pskit invoke -f meta --method GET --path /health`."""),

    # ------------------------------------------------------------------ 403
    B(403, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: temp-cleaner
provider:
  name: azure
  region: germanywestcentral
functions:
  cleanup:
    handler: app.cleanup.run
""",
          "app/__init__.py": "",
          "app/cleanup.py": FUTURE + """

def run(event, ctx):
    ctx.logger.info("cleanup started", extra={"source": event.type})
    return {"deleted": 0}
""",
          "requirements.txt": ""}),
      user="cleanup must run every night 2 oclock german time, on azure. how i do timezone?",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule timezone azure timer",
            docs=[D("docs/events.md", "schedule", start="pskit converts the portable syntax", end="Azure ignores it with a warning.")]),
          S("propose_plan", steps=["Azure timers run in UTC and ignore `timezone`, so add `- schedule: \"0 1 * * *\"` (02:00 German winter time = 01:00 UTC)",
                                   "Validate for azure and run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.cleanup.events", value=[{"schedule": "0 1 * * *"}]),
          S("invoke_local", function="cleanup", type="schedule"),
      ],
      final="""On Azure you can't set a timezone: timers always run in UTC, and pskit ignores `timezone` there with a warning [docs/events.md#schedule]. So I wrote the time in UTC:

```yaml
functions:
  cleanup:
    events:
      - schedule: "0 1 * * *"   # 01:00 UTC = 02:00 in Germany (winter)
```

- `pskit validate` (azure): valid.
- local schedule run: `{"deleted": 0}`.

Note: in summer (CEST) 01:00 UTC is 03:00 in Germany. If it must be exactly 02:00 all year, use `"0 0 * * *"` in summer, or check the hour in the handler. Retest: `pskit invoke -f cleanup -t schedule`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 404
    B(404, provider="aws", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#workflow-keys", "docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: telemetry
provider:
  name: aws
  region: us-west-2
functions:
  parse:
    handler: app.pipeline.parse
  store:
    handler: app.pipeline.store
""",
          "app/__init__.py": "",
          "app/pipeline.py": FUTURE + """

def parse(event, ctx):
    reading = dict(event.data or {})
    reading["celsius"] = round((reading.get("fahrenheit", 32) - 32) * 5 / 9, 1)
    return reading


def store(event, ctx):
    return {"stored": True, "device": (event.data or {}).get("device")}
""",
          "requirements.txt": ""}),
      user="Add a Step Functions workflow `ingest`: Parse (function parse) then Store (function store). It runs thousands of times a minute and each run is short, so it must be an EXPRESS state machine, with a 60 second timeout.",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow options type EXPRESS timeout",
            docs=[D("docs/workflows.md", "workflow-keys", end="| `options.type`")]),
          S("propose_plan", steps=["Add workflow `ingest`: Parse (parse) -> Store (store, end), timeout 60, options.type EXPRESS",
                                   "Validate for aws (prod) and run parse locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.ingest",
            value={"timeout": 60, "options": {"type": "EXPRESS"}, "start_at": "Parse",
                   "states": {"Parse": {"type": "task", "function": "parse", "next": "Store"},
                              "Store": {"type": "task", "function": "store", "end": True}}}),
          S("invoke_local", function="parse", type="workflow", data={"device": "t-9", "fahrenheit": 77}),
      ],
      final="""Added the EXPRESS state machine:

```yaml
workflows:
  ingest:
    timeout: 60
    options: {type: EXPRESS}
    start_at: Parse
    states:
      Parse: {type: task, function: parse, next: Store}
      Store: {type: task, function: store, end: true}
```

- `timeout` becomes Step Functions `TimeoutSeconds`, and `options.type` picks STANDARD or EXPRESS (AWS only) [docs/workflows.md#workflow-keys].
- `pskit validate` (aws, prod): valid.
- `parse` run locally with 77 °F: returned `"celsius": 25.0`.

Try the whole run: `pskit workflow run ingest -i '{"device": "t-9", "fahrenheit": 77}'`, and see the ASL with `pskit workflow show ingest --format asl`. Deploy prod: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 405
    B(405, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: family-album
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, family-album-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="when someone puts a photo in my google bucket i want my code to notice it. the bucket should be called family-album-photos",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/photos.py`: log the name and size of each new file",
                                   "Add function `on-photo` with a storage trigger on bucket family-album-photos, only .jpg files",
                                   "Validate for gcp and test it with one fake upload"],
            result={"decision": "approved", "note": "also accept .png files, not only .jpg"}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/photos.py", content=FUTURE + """
PHOTO_TYPES = (".jpg", ".jpeg", ".png")


def on_photo(event, ctx):
    seen = []
    for record in event.records:
        if not record.key.lower().endswith(PHOTO_TYPES):
            continue
        ctx.logger.info("new photo", extra={"key": record.key, "size": record.size})
        seen.append(record.key)
    return {"photos": seen}
""", say="A storage trigger takes one `suffix`, so I'll leave the suffix out and check for .jpg/.jpeg/.png in the code."),
          S("set_config", path="functions.on-photo",
            value={"handler": "app.photos.on_photo", "events": [{"storage": "family-album-photos"}]}),
          S("invoke_local", function="on-photo", type="storage",
            data={"bucket": "family-album-photos", "key": "beach.PNG", "size": 204800}),
      ],
      final="""Done. Your function `on-photo` runs every time a file is added to the bucket `family-album-photos`. pskit creates that bucket when you deploy.

As you asked, it accepts .png too. A trigger can filter only one ending (`suffix`), so the code checks for `.jpg`, `.jpeg` and `.png` and skips other files.

- `pskit validate` (gcp): valid.
- Test with a fake upload `beach.PNG`: `{"photos": ["beach.PNG"]}`.

Try it again on **Test** > **▶ Run locally** with a `storage` event, or `pskit invoke -f on-photo -t storage -d '{"bucket": "family-album-photos", "key": "cat.jpg"}'`. To put it online: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 406
    B(406, provider="azure", stage="staging", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: shop-backend
provider:
  name: azure
  region: northeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions:
  checkout:
    handler: app.shop.checkout
    events:
    - http: POST /checkout
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + """

def checkout(event, ctx):
    return {"ok": True}, 201
""",
          "requirements.txt": ""}),
      user="Orders are published to a Service Bus topic `order-events`. Add a `notify-warehouse` function subscribed to it. For each message, log order_id and the number of items, and return the list of order ids. pskit should create the topic.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `notify_warehouse` to `app/shop.py`",
                                   "Add function `notify-warehouse` with `- topic: order-events`",
                                   "Validate for azure (staging), invoke with two messages"]),
          S("write_file", path="app/shop.py", content=FUTURE + """

def checkout(event, ctx):
    return {"ok": True}, 201


def notify_warehouse(event, ctx):
    ids = []
    for record in event.records:
        order = record.json(default={}) or {}
        ctx.logger.info("order for warehouse",
                        extra={"order_id": order.get("order_id"), "items": len(order.get("items", []))})
        ids.append(order.get("order_id"))
    return {"orders": ids}
"""),
          S("set_config", path="functions.notify-warehouse",
            value={"handler": "app.shop.notify_warehouse", "events": [{"topic": "order-events"}]}),
          S("invoke_local", function="notify-warehouse", type="topic",
            data=[{"order_id": "o-1", "items": ["a", "b"]}, {"order_id": "o-2", "items": ["c"]}]),
      ],
      final="""Added `notify-warehouse`:

```yaml
functions:
  notify-warehouse:
    handler: app.shop.notify_warehouse
    events:
      - topic: order-events
```

On Azure this becomes a Service Bus namespace and topic `order-events` with one subscription for this function [docs/providers.md#azure-azure-functions].

- validate (azure, staging): valid.
- invoke with two messages: `{"orders": ["o-1", "o-2"]}`, and one log line per order with `order_id` and `items`.

`topic.filter` isn't applied on Azure, so if you later need only some messages, filter in the handler. Retest: `pskit invoke -f notify-warehouse -t topic -d '[{"order_id": "o-9", "items": []}]'`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 407
    B(407, provider="aws", stage="dev", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#provider-support", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: report-api
provider:
  name: aws
  region: us-east-1
functions:
  api:
    handler: app.api.handler
    events:
    - http: POST /reports
  cron:
    handler: app.api.nightly
    events:
    - schedule: 0 4 * * *
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def handler(event, ctx):
    return {"queued": False}, 202


def nightly(event, ctx):
    return {"ran": True}
""",
          "requirements.txt": ""}),
      user="standalone sqs queue `exports` (no consumer yet), bind to api only. api returns its native name for now",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.exports: {type: queue, functions: [api]}",
                                   "api handler returns resource(\"exports\").native_name",
                                   "Validate for aws, invoke POST /reports"]),
          S("set_config", path="resources.exports", value={"type": "queue", "functions": ["api"]}),
          S("write_file", path="app/api.py", content=FUTURE + """from py_serverless_kit import resource


def handler(event, ctx):
    exports = resource("exports")
    return {"queued": False, "queue": exports.native_name}, 202


def nightly(event, ctx):
    return {"ran": True}
"""),
          S("validate"),
          S("invoke_local", function="api", method="POST", path="/reports", data={"kind": "monthly"}),
      ],
      final="""Done.

```yaml
resources:
  exports:
    type: queue
    functions: [api]
```

- AWS supports standalone managed queues; pskit creates the SQS queue, and only `api`'s role gets the `pskit-resources` SQS policy [docs/resources.md#provider-support].
- validate (aws): valid.
- invoke `POST /reports`: 202 `{"queued": false, "queue": "exports"}`. After deploy, `native_name` is the queue's real name, which the provider prefixes like event names.

Send to it with boto3 and `resource("exports").url` (the queue URL is set after deploy) [docs/resources.md#runtime-api]; add `boto3` to requirements.txt. Deploy: `pskit deploy -s dev` or **Deploy**."""),

    # ------------------------------------------------------------------ 408
    B(408, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#migrating-step-functions-asl", "docs/workflows.md#compiler-notes-and-limits"],
      project=dict(files={
          "pskit.yml": """service: claims
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, claims-prod}
functions:
  fetch-policy:
    handler: app.claims.fetch_policy
  notify-failure:
    handler: app.claims.notify_failure
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + """

def fetch_policy(event, ctx):
    claim = dict(event.data or {})
    return {**claim, "policy": {"id": claim.get("policy_id"), "active": True}}


def notify_failure(event, ctx):
    ctx.logger.warning("claim failed", extra={"error": (event.data or {}).get("error")})
    return {"notified": True}
""",
          "requirements.txt": ""}),
      user="""Porting this Step Functions state to GCP:
"FetchPolicy": {"Type": "Task", "Resource": "arn:aws:lambda:...:fetch-policy", "Retry": [{"ErrorEquals": ["TimeoutError"], "MaxAttempts": 3, "IntervalSeconds": 2, "BackoffRate": 2}], "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "NotifyFailure", "ResultPath": "$.error"}], "End": true}
NotifyFailure is a Lambda too. Workflow name `claim-intake`.""",
      steps=[
          S("get_project"),
          S("search_docs", query="ASL Retry Catch States.ALL mapping gcp",
            docs=[D("docs/workflows.md", "migrating-step-functions-asl", start="| `Retry` `ErrorEquals`", end="| `States.ALL`"),
                  D("docs/workflows.md", "compiler-notes-and-limits", start="- **GCP:**", end="- **GCP:**")]),
          S("propose_plan", steps=["Add workflow `claim-intake`: FetchPolicy (task fetch-policy, retry TimeoutError x3 / 2 s / 2.0, catch * -> NotifyFailure with result_path $.error, end)",
                                   "NotifyFailure: task notify-failure, end",
                                   "Validate for gcp (prod), run fetch-policy locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.claim-intake",
            value={"start_at": "FetchPolicy",
                   "states": {"FetchPolicy": {"type": "task", "function": "fetch-policy", "end": True,
                                              "retry": [{"errors": ["TimeoutError"], "max_attempts": 3,
                                                         "interval_seconds": 2, "backoff_rate": 2}],
                                              "catch": [{"errors": ["*"], "next": "NotifyFailure",
                                                         "result_path": "$.error"}]},
                              "NotifyFailure": {"type": "task", "function": "notify-failure", "end": True}}}),
          S("invoke_local", function="fetch-policy", type="workflow", data={"claim_id": "cl-1", "policy_id": "p-77"}),
      ],
      final="""Ported:

```yaml
workflows:
  claim-intake:
    start_at: FetchPolicy
    states:
      FetchPolicy:
        type: task
        function: fetch-policy
        retry: [{errors: [TimeoutError], max_attempts: 3, interval_seconds: 2, backoff_rate: 2}]
        catch: [{errors: ["*"], next: NotifyFailure, result_path: $.error}]
        end: true
      NotifyFailure: {type: task, function: notify-failure, end: true}
```

- `ErrorEquals` → `errors` (Python exception class names), `States.ALL` → `"*"` [docs/workflows.md#migrating-step-functions-asl].
- On GCP this deploys as Cloud Workflows. Only the first retry rule of a task is used, which is fine here because you have one [docs/workflows.md#compiler-notes-and-limits].
- `pskit validate` (gcp, prod): valid. `fetch-policy` locally: returned the claim with `policy.active: true`.

Compare with your old ASL: `pskit workflow show claim-intake --format asl`. Run it: `pskit workflow run claim-intake -i '{"policy_id": "p-77"}' --history`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 409
    B(409, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/getting-started.md", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: first-app
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="I just made a new empty project for azure. Can you add the simplest possible hello world web page thing so I can see it works?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/hello.py` that returns a greeting",
                                   "Add function `hello` on GET /hello",
                                   "Validate for azure and call it locally"],
            result={"decision": "approved", "note": "use /hi as the path instead of /hello"}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/hello.py", content=FUTURE + """

def hello(event, ctx):
    name = event.http.query.get("name", "world")
    return {"message": f"Hello, {name}!"}
"""),
          S("set_config", path="functions.hello",
            value={"handler": "app.hello.hello", "events": [{"http": "GET /hi"}]}, say="Using `/hi`, as you asked."),
          S("invoke_local", function="hello", method="GET", path="/hi"),
      ],
      final="""Your first function is ready. `hello` answers on **`/hi`** (the path you asked for).

- `pskit validate` (azure): valid.
- Local test: status 200, `{"message": "Hello, world!"}`. Add `?name=Ana` to the address to change the name.

Try it yourself: **Test** > **▶ Run locally**, or `pskit invoke -f hello --method GET --path /hi`.

To put it on Azure, open **Deploy** and click **Deploy** (or run `pskit deploy -s dev`). Azure needs a subscription id for deploy: log in with `az login` and set `ARM_SUBSCRIPTION_ID` first. After deploy, `pskit info` shows the address. On Azure the path stays exactly `/hi` (no `/api` in front)."""),

    # ------------------------------------------------------------------ 410
    B(410, provider="aws", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage", "docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition"],
      project=dict(files={
          "pskit.yml": """service: partner-feed
provider:
  name: aws
  region: ap-southeast-2
functions: {}
""",
          "requirements.txt": ""}),
      user="partner drop csv files in s3 bucket partner-drop-0042 folder incoming/. bucket is exist already, not create it. need function count rows of each file key",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/feed.py`: log bucket/key/size for each new object (row counting needs boto3 to read the file, so for now it returns the keys)",
                                   "Add function `ingest-csv` with storage {bucket: partner-drop-0042, existing: true, prefix: incoming/, suffix: .csv}",
                                   "Validate for aws (staging), test one file event"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/feed.py", content=FUTURE + """

def ingest_csv(event, ctx):
    files = []
    for record in event.records:
        ctx.logger.info("partner file", extra={"bucket": record.bucket, "key": record.key, "size": record.size})
        files.append(record.key)
    return {"files": files}
"""),
          S("set_config", path="functions.ingest-csv",
            value={"handler": "app.feed.ingest_csv",
                   "events": [{"storage": {"bucket": "partner-drop-0042", "existing": True,
                                           "prefix": "incoming/", "suffix": ".csv"}}]}),
          S("invoke_local", function="ingest-csv", type="storage",
            data={"bucket": "partner-drop-0042", "key": "incoming/2026-11-01.csv", "size": 5120}),
      ],
      final="""Done. Function `ingest-csv` runs for new `.csv` files under `incoming/` in your existing bucket:

```yaml
functions:
  ingest-csv:
    handler: app.feed.ingest_csv
    events:
      - storage: {bucket: partner-drop-0042, existing: true, prefix: incoming/, suffix: .csv}
```

- `existing: true`: pskit adds only the notification, it doesn't create the bucket.
- `pskit validate` (aws, staging): valid.
- Test event: `{"files": ["incoming/2026-11-01.csv"]}`.

The event gives you bucket, key and size, not the file content. To count rows, read the object with boto3 (`get_object`), add `boto3` to requirements.txt and an `s3:GetObject` statement in `iam.statements`. I can add that next. Retest: `pskit invoke -f ingest-csv -t storage -d '{"bucket": "partner-drop-0042", "key": "incoming/a.csv"}'`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 411
    B(411, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#queue", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: media
provider:
  name: gcp
  region: asia-northeast1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, media-staging}
functions: {}
""",
          "requirements.txt": ""}),
      user="Create a queue worker `resize` on the queue `resize-jobs`. Each message is {\"image\": \"path\", \"width\": int}. Batch size 50, and failed messages should go to a dead-letter queue `resize-dlq` after 3 tries. Return the processed image paths.",
      steps=[
          S("get_project"),
          S("search_docs", query="queue batch_size dead_letter gcp pubsub",
            docs=[D("docs/events.md", "queue", start="| Option | aws (SQS)", end="On GCP a \"queue\" is a Pub/Sub topic")]),
          S("ask_user", question="On GCP a queue is a Pub/Sub topic: batch_size, dead_letter and max_receive are ignored there (validate warns). Keep them in pskit.yml anyway, or leave them out?",
            options=["Keep them (warnings)", "Leave them out"], answer="Leave them out"),
          S("propose_plan", steps=["Write `app/resize.py`: read image/width per record, return processed paths",
                                   "Add function `resize` with `- queue: resize-jobs` (no batch_size / dead_letter)",
                                   "Validate for gcp (staging), invoke with two messages"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/resize.py", content=FUTURE + """

def resize(event, ctx):
    done = []
    for record in event.records:
        job = record.json(default={}) or {}
        ctx.logger.info("resize", extra={"image": job.get("image"), "width": job.get("width")})
        done.append(job.get("image"))
    return {"processed": done}
"""),
          S("set_config", path="functions.resize",
            value={"handler": "app.resize.resize", "events": [{"queue": "resize-jobs"}]}),
          S("invoke_local", function="resize", type="queue",
            data=[{"image": "img/a.png", "width": 320}, {"image": "img/b.png", "width": 640}]),
      ],
      final="""Created the worker without the options GCP can't honour:

```yaml
functions:
  resize:
    handler: app.resize.resize
    events:
      - queue: resize-jobs
```

- On GCP `resize-jobs` is a Pub/Sub topic with a push trigger. Batch size and dead-letter settings don't apply, and a failure retries the whole delivery [docs/events.md#queue].
- validate (gcp, staging): valid.
- invoke with two messages: `{"processed": ["img/a.png", "img/b.png"]}`.

Make the handler idempotent, since redelivery is normal. Retest: `pskit invoke -f resize -t queue -d '[{"image": "img/c.png", "width": 100}]'`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 412
    B(412, provider="azure", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#embedded-orchestrator", "docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: refunds
provider:
  name: azure
  region: uksouth
functions:
  check-refund:
    handler: app.refunds.check
  pay-refund:
    handler: app.refunds.pay
  escalate:
    handler: app.refunds.escalate
""",
          "app/__init__.py": "",
          "app/refunds.py": FUTURE + """

def check(event, ctx):
    req = dict(event.data or {})
    return {**req, "amount": float(req.get("amount", 0))}


def pay(event, ctx):
    return {**(event.data or {}), "paid": True}


def escalate(event, ctx):
    return {**(event.data or {}), "escalated": True}
""",
          "requirements.txt": ""}),
      user="wf `refund`: check-refund -> if amount > 500 escalate else pay-refund. default engine",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["workflows.refund: Check (check-refund) -> Route (choice $.amount gt 500 -> Escalate, default Pay)",
                                   "Escalate / Pay: tasks, end. engine left at auto (embedded on Azure)",
                                   "Validate azure (prod), invoke check-refund"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.refund",
            value={"start_at": "Check",
                   "states": {"Check": {"type": "task", "function": "check-refund", "next": "Route"},
                              "Route": {"type": "choice",
                                        "choices": [{"variable": "$.amount", "gt": 500, "next": "Escalate"}],
                                        "default": "Pay"},
                              "Escalate": {"type": "task", "function": "escalate", "end": True},
                              "Pay": {"type": "task", "function": "pay-refund", "end": True}}}),
          S("invoke_local", function="check-refund", type="workflow", data={"order": "o-5", "amount": "720"}),
      ],
      final="""Added:

```yaml
workflows:
  refund:
    start_at: Check
    states:
      Check: {type: task, function: check-refund, next: Route}
      Route:
        type: choice
        choices: [{variable: $.amount, gt: 500, next: Escalate}]
        default: Pay
      Escalate: {type: task, function: escalate, end: true}
      Pay: {type: task, function: pay-refund, end: true}
```

- validate (azure, prod): valid, with one warning: the embedded engine runs inside one function, so the whole run is capped at 600 s on Azure. With `engine: auto` Azure runs it in a generated `refund-orchestrator` function, started with `POST /workflows/refund` [docs/workflows.md#embedded-orchestrator].
- `check-refund` locally: `"amount": 720.0`, so this run goes to Escalate.

Whole run: `pskit workflow run refund -i '{"order": "o-5", "amount": "720"}' --history`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 413
    B(413, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: notes-api
provider:
  name: aws
  region: eu-west-2
functions:
  notes:
    handler: app.notes.list_notes
    events:
    - http: GET /notes
""",
          "app/__init__.py": "",
          "app/notes.py": FUTURE + """

def list_notes(event, ctx):
    return [{"id": 1, "text": "buy milk"}]
""",
          "requirements.txt": ""}),
      user="can you put an api key on my notes endpoint so random people can't call it?",
      steps=[
          S("get_project"),
          S("search_docs", query="http auth key aws",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", question="AWS HTTP APIs don't support API keys (`auth: key`). Which do you want instead?",
            options=["jwt (tokens from a login provider like Cognito or Auth0)", "iam (only callers with AWS credentials)"],
            answer="jwt. issuer https://login.example.com/ and audience notes-api"),
          S("propose_plan", steps=["Change `GET /notes` to the long form with auth: jwt and authorizer {issuer: https://login.example.com/, audience: [notes-api]}",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.notes.events.0",
            value={"http": {"path": "/notes", "method": "GET", "auth": "jwt",
                            "authorizer": {"issuer": "https://login.example.com/", "audience": ["notes-api"]}}}),
      ],
      final="""API keys don't exist on AWS HTTP APIs, so I used JWT login tokens, as you chose:

```yaml
functions:
  notes:
    events:
      - http:
          path: /notes
          method: GET
          auth: jwt
          authorizer:
            issuer: https://login.example.com/
            audience: [notes-api]
```

- `pskit validate` (aws): valid.
- After deploy, API Gateway rejects calls without a valid token from `https://login.example.com/` before your code runs. Callers send `Authorization: Bearer <token>`.

The handler didn't change. Deploy it with **Deploy** or `pskit deploy -s dev`. `jwt` works only on AWS, so if you move clouds later, `pskit validate` will flag it [docs/events.md#http]."""),

    # ------------------------------------------------------------------ 414
    B(414, provider="gcp", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: sales-digest
provider:
  name: gcp
  region: asia-south1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, sales-digest-dev}
functions:
  digest:
    handler: app.digest.run
""",
          "app/__init__.py": "",
          "app/digest.py": FUTURE + """

def run(event, ctx):
    report = (event.data or {}).get("report", "all")
    ctx.logger.info("digest", extra={"report": report})
    return {"report": report, "sent": True}
""",
          "requirements.txt": ""}),
      user="digest should run daily 6 morning india time, input report=sales",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add schedule {cron: \"0 6 * * *\", timezone: Asia/Kolkata, input: {report: sales}} to digest",
                                   "Validate for gcp, run the schedule locally"]),
          S("set_config", path="functions.digest.events",
            value=[{"schedule": {"cron": "0 6 * * *", "timezone": "Asia/Kolkata", "input": {"report": "sales"}}}]),
          S("invoke_local", function="digest", type="schedule"),
      ],
      final="""Done:

```yaml
functions:
  digest:
    events:
      - schedule:
          cron: "0 6 * * *"
          timezone: Asia/Kolkata
          input: {report: sales}
```

- GCP Cloud Scheduler honours `timezone`, so it runs at 06:00 India time [docs/events.md#schedule].
- validate (gcp): valid.
- local schedule run: `{"report": "sales", "sent": true}` (the `input` arrives as `event.data`).

Retest: `pskit invoke -f digest -t schedule`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 415
    B(415, provider="azure", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#provider-support", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: mailer
provider:
  name: azure
  region: francecentral
functions:
  api:
    handler: app.mail.api
    events:
    - http: POST /send
  stats:
    handler: app.mail.stats
    events:
    - http: GET /stats
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """

def api(event, ctx):
    return {"accepted": True}, 202


def stats(event, ctx):
    return {"sent": 0}
""",
          "requirements.txt": ""}),
      user="We need a storage queue called `email-outbox` that pskit creates. Nothing consumes it yet; `api` will push to it later with azure-storage-queue. Bind it only to `api` and make `api` return the queue's native name so I can see it.",
      steps=[
          S("get_project"),
          S("search_docs", query="azure standalone managed queue resource functions binding",
            docs=[D("docs/resources.md", "provider-support", start="| | Managed, used by an event", end="On Azure, app settings")]),
          S("propose_plan", steps=["resources.email-outbox: {type: queue, functions: [api]}",
                                   "`api` returns resource(\"email-outbox\").native_name",
                                   "Validate for azure (staging), invoke POST /send"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.email-outbox", value={"type": "queue", "functions": ["api"]}),
          S("write_file", path="app/mail.py", content=FUTURE + """from py_serverless_kit import resource


def api(event, ctx):
    outbox = resource("email-outbox")
    return {"accepted": True, "queue": outbox.native_name}, 202


def stats(event, ctx):
    return {"sent": 0}
"""),
          S("validate"),
          S("invoke_local", function="api", method="POST", path="/send", data={"to": "ops@example.com"}),
      ],
      final="""Added the managed queue:

```yaml
resources:
  email-outbox:
    type: queue
    functions: [api]
```

- Azure supports standalone managed queues; pskit creates a Storage Queue in the app's storage account.
- One caveat: on Azure app settings belong to the whole Function App, so `stats` will see the binding too, even with `functions: [api]` [docs/resources.md#provider-support].
- validate (azure, staging): valid.
- invoke `POST /send`: 202 `{"accepted": true, "queue": "email-outbox"}`. After deploy, `native_name` is the real (prefixed) queue name.

For sending, add `azure-storage-queue` to requirements.txt and use `resource("email-outbox").native_name` as the queue name. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 416
    B(416, provider="aws", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: transcode
provider:
  name: aws
  region: us-east-1
functions:
  worker:
    handler: app.worker.run
    events:
    - queue: transcode-jobs
""",
          "app/__init__.py": "",
          "app/worker.py": FUTURE + """

def run(event, ctx):
    return {"jobs": len(event.records)}
""",
          "requirements.txt": ""}),
      user="worker: 1024 MB, arm64, timeout 120, reserved concurrency 5",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.worker: memory 1024, architecture arm64, timeout 120, concurrency 5",
                                   "Validate aws (prod)"]),
          S("set_config", path="functions.worker.memory", value=1024),
          S("set_config", path="functions.worker.architecture", value="arm64"),
          S("set_config", path="functions.worker.timeout", value=120),
          S("set_config", path="functions.worker.concurrency", value=5),
      ],
      final="""Set on `worker`:

```yaml
functions:
  worker:
    memory: 1024
    architecture: arm64
    timeout: 120
    concurrency: 5
```

validate (aws, prod) passed after each change. `concurrency` is the reserved concurrency on Lambda [docs/configuration.md#functions]. The SQS visibility timeout defaults to max(30, 6 x timeout), so it becomes 720 s with the new timeout. Dependencies are installed as arm64 wheels. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 417
    B(417, provider="gcp", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#variables", "docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: payments
provider:
  name: gcp
  region: us-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, payments-staging}
functions:
  charge:
    handler: app.pay.charge
    events:
    - http: POST /charge
""",
          "app/__init__.py": "",
          "app/pay.py": FUTURE + """

def charge(event, ctx):
    return {"charged": True}
""",
          "requirements.txt": ""}),
      user="In serverless.yml I had `STRIPE_API_KEY: ${ssm:/payments/stripe-key}` under environment. What's the pskit equivalent here on GCP? Add it to `charge`, and have the handler fail with 500 if the key is missing instead of silently charging nothing.",
      steps=[
          S("get_project"),
          S("search_docs", query="environment variables secrets env variable syntax",
            docs=[D("docs/configuration.md", "variables", end="Variables can nest across passes")]),
          S("propose_plan", steps=["Add environment STRIPE_API_KEY: ${env:STRIPE_API_KEY, not-set} to `charge` (no ssm: in pskit; the value comes from the deploy environment)",
                                   "Handler: log an error and answer 500 when the key is missing or `not-set`",
                                   "Validate for gcp (staging), invoke POST /charge"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.charge.environment", value={"STRIPE_API_KEY": "${env:STRIPE_API_KEY, not-set}"}),
          S("write_file", path="app/pay.py", content=FUTURE + """

def charge(event, ctx):
    key = ctx.env.get("STRIPE_API_KEY", "")
    if not key or key == "not-set":
        ctx.logger.error("STRIPE_API_KEY is not configured")
        return {"error": "payment provider is not configured"}, 500
    return {"charged": True}
"""),
          S("validate"),
          S("invoke_local", function="charge", method="POST", path="/charge", data={"amount": 1200}),
      ],
      final="""pskit has no `${ssm:...}`. The equivalent is `${env:...}`, resolved from the environment when you validate or deploy:

```yaml
functions:
  charge:
    environment:
      STRIPE_API_KEY: ${env:STRIPE_API_KEY, not-set}
```

- validate (gcp, staging): valid.
- Local `POST /charge` without the variable: **500** `payment provider is not configured`, instead of charging. That's the behaviour you wanted (the message doesn't reveal the variable name to callers).

Set the real key where you deploy (CI secret, or **Setup & credentials** > Environment variables > **Set for this session**), then `pskit deploy -s staging` or **Deploy**. The value ends up in the function's environment, so for a stronger setup read it with `get_secret()` instead [docs/handlers.md#environment-variables]."""),

    # ------------------------------------------------------------------ 418
    B(418, provider="azure", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: website-forms
provider:
  name: azure
  region: eastus
functions: {}
""",
          "requirements.txt": ""}),
      user="need POST /contact on azure, protected with function key. body has email and message, if email missing give 400",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/contact.py`: BadRequest when email is missing, else 202",
                                   "Add function `contact` on POST /contact with auth: key",
                                   "Validate for azure, invoke with a body without email"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/contact.py", content=FUTURE + """from py_serverless_kit import BadRequest


def contact(event, ctx):
    form = event.http.json(default={}) or {}
    if not form.get("email"):
        raise BadRequest("email is required")
    ctx.logger.info("contact form", extra={"email": form["email"]})
    return {"received": True}, 202
"""),
          S("set_config", path="functions.contact",
            value={"handler": "app.contact.contact",
                   "events": [{"http": {"path": "/contact", "method": "POST", "auth": "key"}}]}),
          S("invoke_local", function="contact", method="POST", path="/contact", data={"message": "hi"}),
      ],
      final="""Done. `contact` is on `POST /contact` with `auth: key`, so Azure requires the function key (`AuthLevel.FUNCTION`) [docs/events.md#http].

- validate (azure): valid.
- invoke without email: **400** `email is required`. With an email it returns 202.

After deploy, callers must send the function key (the `x-functions-key` header). Retest: `pskit invoke -f contact --method POST --path /contact -d '{"email": "a@example.com", "message": "hi"}'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 419
    B(419, provider="aws", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: ledger
provider:
  name: aws
  region: ca-central-1
functions:
  record-refund:
    handler: app.ledger.record_refund
""",
          "app/__init__.py": "",
          "app/ledger.py": FUTURE + """

def record_refund(event, ctx):
    total = 0.0
    for record in event.records:
        total += float((record.json(default={}) or {}).get("amount", 0))
    return {"refunds": len(event.records), "total": total}
""",
          "requirements.txt": ""}),
      user="Subscribe `record-refund` to the SNS topic `payments` (pskit creates it), but only for messages whose `event_type` attribute is `refund`. Keep the handler as is.",
      steps=[
          S("get_project"),
          S("search_docs", query="topic filter policy sns",
            docs=[D("docs/events.md", "topic", end="| gcp | Pub/Sub")]),
          S("propose_plan", steps=["Add topic {name: payments, filter: {event_type: [refund]}} to `record-refund`",
                                   "Validate for aws (staging), invoke with two refund messages"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.record-refund.events",
            value=[{"topic": {"name": "payments", "filter": {"event_type": ["refund"]}}}]),
          S("invoke_local", function="record-refund", type="topic", data=[{"amount": 12.5}, {"amount": 7.5}]),
      ],
      final="""Subscribed with an SNS filter policy:

```yaml
functions:
  record-refund:
    events:
      - topic:
          name: payments
          filter: {event_type: [refund]}
```

- On AWS `filter` becomes the subscription's filter policy, so SNS only delivers messages whose `event_type` attribute is `refund` [docs/events.md#topic].
- `pskit validate` (aws, staging): valid.
- Local run with two messages: `{"refunds": 2, "total": 20.0}`. `pskit invoke` doesn't apply the filter; that happens in SNS.

Publishers must set `event_type` as a **message attribute**, not only in the body. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 420
    B(420, provider="gcp", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: pricing
provider:
  name: gcp
  region: europe-west4
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, pricing-prod}
functions:
  quote:
    handler: app.pricing.quote
    events:
    - http: POST /quote
""",
          "app/__init__.py": "",
          "app/pricing.py": FUTURE + """

def quote(event, ctx):
    return {"price": 42}
""",
          "requirements.txt": ""}),
      user="my quote api should only be used by our own services on google cloud, not by the public internet. how can I lock it?",
      steps=[
          S("get_project"),
          S("search_docs", query="gcp http auth iam public invoker",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="| Trigger | Implementation |", end="| http | function URL")]),
          S("propose_plan", steps=["Change `POST /quote` to the long form with auth: iam (no public allUsers binding)",
                                   "Validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.quote.events.0",
            value={"http": {"path": "/quote", "method": "POST", "auth": "iam"}}),
      ],
      final="""Locked. `quote` now uses `auth: iam`:

```yaml
functions:
  quote:
    events:
      - http: {path: /quote, method: POST, auth: iam}
```

- With `auth: none`, pskit gives the public (`allUsers`) permission to call the function. With `auth: iam` it doesn't, so only Google identities that you allow can call it [docs/providers.md#gcp-google-cloud-functions-2nd-gen].
- `pskit validate` (gcp, prod): valid.

Your other services must send a Google ID token (`Authorization: Bearer ...`) and be granted `roles/run.invoker` on it. Deploy prod: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),
]
