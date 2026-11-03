"""Category B (build / add), batch 4. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 61
    B(61, provider="azure", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#engines", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: leave-requests
provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions:
  check-balance:
    handler: app.leave.check_balance
  book-leave:
    handler: app.leave.book
""",
          "app/__init__.py": "",
          "app/leave.py": FUTURE + """

def check_balance(event, ctx):
    req = dict(event.data or {})
    return {**req, "days_left": 12}


def book(event, ctx):
    req = dict(event.data or {})
    return {**req, "booked": req.get("days", 0) <= req.get("days_left", 0)}
""",
          "requirements.txt": ""}),
      user="my boss wants the leave steps to show up in Azure's own workflow designer thing, not hidden in a function. first check-balance, then book-leave",
      steps=[
          S("get_project"),
          S("search_docs", query="azure native workflow logic apps engine",
            docs=[D("docs/workflows.md", "engines")]),
          S("propose_plan", steps=["Add workflow `leave` with `engine: native` (an Azure Logic App): CheckBalance (check-balance) -> BookLeave (book-leave, end)",
                                   "Validate for azure and run check-balance locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.leave",
            value={"engine": "native", "start_at": "CheckBalance",
                   "states": {"CheckBalance": {"type": "task", "function": "check-balance", "next": "BookLeave"},
                              "BookLeave": {"type": "task", "function": "book-leave", "end": True}}}),
          S("invoke_local", function="check-balance", type="workflow", data={"employee": "sam", "days": 3}),
      ],
      final="""Done. The workflow `leave` now runs as an **Azure Logic App**, Azure's own workflow service, so your boss will see the steps there:

```yaml
workflows:
  leave:
    engine: native
    start_at: CheckBalance
    states:
      CheckBalance: {type: task, function: check-balance, next: BookLeave}
      BookLeave:    {type: task, function: book-leave, end: true}
```

On Azure, workflows normally run inside a helper function. `engine: native` switches to a Logic App [docs/workflows.md#engines].

- `pskit validate` for azure: valid.
- `check-balance` run locally: it returned the request with `"days_left": 12`.

After deploy, `pskit info` shows the workflow URL that starts it. That URL has a signature in it, so keep it private. Try the whole flow locally with `pskit workflow run leave -i '{"employee": "sam", "days": 3}'`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 62
    B(62, provider="aws", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#provider-support", "docs/resources.md#aws-iam"],
      project=dict(files={
          "pskit.yml": """service: finance-reports
provider:
  name: aws
  region: eu-west-1
functions:
  export:
    handler: app.export.run
    events:
    - schedule: 0 6 * * *
  api:
    handler: app.export.status
    events:
    - http: GET /status
""",
          "app/__init__.py": "",
          "app/export.py": FUTURE + """

def run(event, ctx):
    return {"exported": True}


def status(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="The daily `export` job should write its CSV into an S3 bucket that pskit creates for us (`finance-reports-exports-0001`). No trigger on the bucket. Only `export` should get access, not `api`. For now, have the handler return the bucket's real name so we can check the binding.",
      steps=[
          S("get_project"),
          S("search_docs", query="managed storage resource standalone aws iam functions",
            docs=[D("docs/resources.md", "aws-iam")]),
          S("propose_plan", steps=["Add resource `exports`: type storage, name finance-reports-exports-0001, functions [export]",
                                   "Change `run` to return resource(\"exports\").native_name",
                                   "Validate for aws (staging) and run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.exports",
            value={"type": "storage", "name": "finance-reports-exports-0001", "functions": ["export"]}),
          S("write_file", path="app/export.py", content=FUTURE + """from py_serverless_kit import resource


def run(event, ctx):
    bucket = resource("exports")
    return {"exported": True, "bucket": bucket.native_name}


def status(event, ctx):
    return {"ok": True}
"""),
          S("validate"),
          S("invoke_local", function="export", type="schedule"),
      ],
      final="""Added a managed bucket that only `export` is bound to:

```yaml
resources:
  exports:
    type: storage
    name: finance-reports-exports-0001
    functions: [export]
```

- pskit creates the S3 bucket. On AWS the `export` role gets a `pskit-resources` policy with `s3:GetObject`, `PutObject`, `DeleteObject` and `ListBucket` on it. `api` gets nothing, because of `functions: [export]` [docs/resources.md#aws-iam].
- `pskit validate` (aws, staging): valid.
- Local schedule run: `{"exported": true, "bucket": "finance-reports-exports-0001"}`.

To write the CSV, use boto3 with `bucket.native_name` (pskit has no portable upload helper for the clouds), and add `boto3` to requirements.txt. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 63
    B(63, provider="gcp", stage="staging", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: accounts
provider:
  name: gcp
  region: southamerica-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  signup:
    handler: app.accounts.signup
    events:
    - http: POST /signup
""",
          "app/__init__.py": "",
          "app/accounts.py": FUTURE + """

def signup(event, ctx):
    return {"ok": True}, 201
""",
          "requirements.txt": ""}),
      user="after signup we publish to pubsub topic user-signups. make welcome function listen it and log the email pls",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `welcome` to `app/accounts.py` (log email per message)",
                                   "Add function `welcome` with `- topic: user-signups`",
                                   "Validate for gcp (staging), run one message locally"]),
          S("write_file", path="app/accounts.py", content=FUTURE + """

def signup(event, ctx):
    return {"ok": True}, 201


def welcome(event, ctx):
    emails = []
    for record in event.records:
        user = record.json(default={}) or {}
        ctx.logger.info("welcome", extra={"email": user.get("email")})
        emails.append(user.get("email"))
    return {"welcomed": emails}
"""),
          S("set_config", path="functions.welcome",
            value={"handler": "app.accounts.welcome", "events": [{"topic": "user-signups"}]}),
          S("invoke_local", function="welcome", type="topic", data=[{"email": "new.user@example.com"}]),
      ],
      final="""Done. `welcome` listens to the Pub/Sub topic `user-signups` and logs the email.

- validate (gcp, staging): valid.
- local run: `{"welcomed": ["new.user@example.com"]}`.

Note: pskit creates the topic `user-signups` on deploy. If `signup` should publish to it, use the `google-cloud-pubsub` client in `signup`, and I can add that. Test: `pskit invoke -f welcome -t topic -d '[{"email": "a@example.com"}]'`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 64
    B(64, provider="onprem", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": """service: invoicing
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
functions:
  render-pdf:
    handler: app.render.render
    timeout: 20
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + """from py_serverless_kit import BatchResult


def render(event, ctx):
    result = BatchResult()
    for record in event.records:
        job = record.json(default={}) or {}
        if "invoice_id" not in job:
            result.fail(record)
            continue
        ctx.logger.info("render", extra={"invoice_id": job["invoice_id"]})
    return result
""",
          "requirements.txt": ""}),
      user="On AWS this was an SQS event source: queue invoice-render, BatchSize 10, VisibilityTimeout 120, redrive to invoice-render-dlq after 4 receives, ReportBatchItemFailures on. We're moving to our own server. Same behaviour please.",
      steps=[
          S("get_project"),
          S("search_docs", query="onprem queue visibility dead_letter max_receive BatchResult",
            docs=[D("docs/providers.md", "onprem-on-premises", start="| queue | one JSON file", end="| queue | one JSON file"),
                  D("docs/handlers.md", "batchresult", start="| Provider | Behaviour |", end="| onprem |")]),
          S("propose_plan", steps=["Add a queue event to `render-pdf`: name invoice-render, batch_size 10, visibility_timeout 120, dead_letter invoice-render-dlq, max_receive 4",
                                   "Keep the handler (it already returns BatchResult)",
                                   "Validate for onprem (prod) and run a good and a bad message locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.render-pdf.events",
            value=[{"queue": {"name": "invoice-render", "batch_size": 10, "visibility_timeout": 120,
                              "dead_letter": "invoice-render-dlq", "max_receive": 4}}]),
          S("invoke_local", function="render-pdf", type="queue", data=[{"invoice_id": "INV-1"}, {"oops": True}]),
      ],
      final="""Same behaviour on your server:

```yaml
functions:
  render-pdf:
    events:
      - queue:
          name: invoice-render
          batch_size: 10
          visibility_timeout: 120
          dead_letter: invoice-render-dlq
          max_receive: 4
```

The on-prem file broker honours all of these. Your `BatchResult` works like `ReportBatchItemFailures`: the host retries only the failed ids, and after 4 receives it moves the message to `invoice-render-dlq` [docs/handlers.md#batchresult].

- `pskit validate` (onprem, prod): valid.
- Local run with one good and one bad message: `batchItemFailures` lists only the bad one.

To feed it from outside, send `POST /__pskit/queues/invoice-render` to the host. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 65
    B(65, provider="huawei", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#events-triggers"],
      project=dict(files={
          "pskit.yml": """service: monitor
provider:
  name: huawei
  region: cn-east-3
functions:
  check:
    handler: app.check.run
""",
          "app/__init__.py": "",
          "app/check.py": FUTURE + """

def run(event, ctx):
    if event.type == "schedule":
        return {"mode": "hourly"}
    return {"mode": "alarm", "alarms": len(event.records)}
""",
          "requirements.txt": ""}),
      user="check: hourly + on SMN topic alarms",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Set check.events = [schedule: 1 hour, topic: alarms]",
                                   "Validate for huawei (prod); invoke as schedule and as topic"]),
          S("set_config", path="functions.check.events", value=[{"schedule": "1 hour"}, {"topic": "alarms"}]),
          S("invoke_local", function="check", type="schedule"),
          S("invoke_local", function="check", type="topic", data=[{"alarm": "cpu"}]),
      ],
      final="""`check` now has two triggers:

```yaml
events:
  - schedule: 1 hour
  - topic: alarms
```

- validate (huawei, prod): valid.
- invoke schedule: `{"mode": "hourly"}`. Invoke topic: `{"mode": "alarm", "alarms": 1}`. Your `event.type` branch works for both.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 66
    B(66, provider="cloudflare", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/providers.md#cloudflare-workers", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: daily-quote
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, 0123456789abcdef0123456789abcdef}
functions: {}
""",
          "requirements.txt": ""}),
      user="i'd like a little page on cloudflare that shows a random motivational quote each time",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/quote.py`: pick a random quote and return it as a small HTML page",
                                   "Add function `quote` on GET /",
                                   "Validate for cloudflare and open it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/quote.py", content=FUTURE + """import html
import random

from py_serverless_kit import Response

QUOTES = [
    "Small steps every day.",
    "Done is better than perfect.",
    "You are allowed to start again.",
]


def quote(event, ctx):
    text = html.escape(random.choice(QUOTES))
    return Response.html(f"<html><body><h1>{text}</h1></body></html>")
"""),
          S("set_config", path="functions.quote",
            value={"handler": "app.quote.quote", "events": [{"http": "GET /"}]}),
          S("invoke_local", function="quote", method="GET", path="/"),
      ],
      final="""Your quote page is ready. It is a function `quote` on `/`, and it returns a small HTML page with one random quote each time.

- `pskit validate` for cloudflare: valid. The warning only says that Python Workers get the standard library and Pyodide's packages. This page uses only `random` and `html`, so that's fine.
- Local test: status 200 with an HTML page showing one of the quotes.

Add your own quotes to the `QUOTES` list in `app/quote.py`. Try it on **Test** > **▶ Run locally**, or `pskit invoke -f quote`. Put it online with **Deploy** or `pskit deploy -s dev`. `pskit info` then shows the address."""),

    # ------------------------------------------------------------------ 67
    B(67, provider="aws", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: catalog-api
provider:
  name: aws
  region: us-east-1
functions:
  products:
    handler: app.catalog.products
    events:
    - http: GET /products
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """

def products(event, ctx):
    return [{"sku": "A1", "name": "mug"}]
""",
          "requirements.txt": ""}),
      user="Access to fetch at 'https://abc123.execute-api.us-east-1.amazonaws.com/products' from origin 'https://shop.example.com' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.\nallow our shop only",
      steps=[
          S("get_project"),
          S("search_docs", query="cors origins http event",
            docs=[D("docs/events.md", "http", start="**CORS**", end="AWS additionally configures CORS")]),
          S("propose_plan", steps=["Turn `GET /products` into the long form with cors.origins [https://shop.example.com], methods [GET]",
                                   "Validate for aws and call it locally (code unchanged)"]),
          S("set_config", path="functions.products.events.0",
            value={"http": {"path": "/products", "method": "GET",
                            "cors": {"origins": ["https://shop.example.com"], "methods": ["GET"]}}}),
          S("invoke_local", function="products", method="GET", path="/products"),
      ],
      final="""Added CORS for your shop only:

```yaml
events:
  - http:
      path: /products
      method: GET
      cors:
        origins: ["https://shop.example.com"]
        methods: [GET]
```

- validate (aws): valid.
- Local call to `/products`: still 200 with the product list.

The browser error goes away after deploy. The runtime adds `Access-Control-*` headers and answers preflights, and on AWS the HTTP API gets the same CORS config [docs/events.md#http]. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 68
    B(68, provider="azure", stage="prod", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: erp-sync
provider:
  name: azure
  region: germanywestcentral
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions: {}
""",
          "requirements.txt": ""}),
      user="The ERP writes nightly CSVs as blobs to container `exports` under `daily/`. Create `load-export` that fires for new `.csv` blobs there, logs the name and size, and returns the keys it saw (the actual load comes later). Timeout 300 s.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/erp.py`: log key and size per blob, return the keys",
                                   "Add `load-export`: timeout 300, storage {bucket: exports, prefix: daily/, suffix: .csv}",
                                   "Validate for azure (prod) and run one blob event locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/erp.py", content=FUTURE + """

def load_export(event, ctx):
    keys = []
    for record in event.records:
        ctx.logger.info("erp export", extra={"key": record.key, "size": record.size})
        keys.append(record.key)
    return {"loaded": keys}
"""),
          S("set_config", path="functions.load-export",
            value={"handler": "app.erp.load_export", "timeout": 300,
                   "events": [{"storage": {"bucket": "exports", "prefix": "daily/", "suffix": ".csv"}}]}),
          S("invoke_local", function="load-export", type="storage",
            data={"bucket": "exports", "key": "daily/2026-10-31.csv", "size": 734003}),
      ],
      final="""Created `load-export`:

```yaml
functions:
  load-export:
    handler: app.erp.load_export
    timeout: 300
    events:
      - storage: {bucket: exports, prefix: daily/, suffix: .csv}
```

- validate (azure, prod): valid. On Azure this is a blob trigger on container `exports` in the app's storage account, with the prefix/suffix as its path pattern. It fires on created and updated blobs [docs/events.md#storage].
- local run: `{"loaded": ["daily/2026-10-31.csv"]}`.

If the ERP writes to a container in **another** storage account, set `existing: true` and `provider.options.storage_connection` (the app setting that holds that account's connection string). Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 69
    B(69, provider="onprem", stage="staging", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#storage-drivers", "docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": """service: archive
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8105
functions: {}
""",
          "requirements.txt": ""}),
      user="minio at http://minio.example.com:9000, bucket incoming, keys from MINIO_ACCESS_KEY/MINIO_SECRET_KEY on the host. fn `archive` on new objects under docs/",
      steps=[
          S("get_project"),
          S("search_docs", query="minio storage driver access_key_env prefix",
            docs=[D("docs/resources.md", "storage-drivers", start="**One storage service, many buckets", end="`builtin` resources make it")]),
          S("propose_plan", steps=["resources.minio: storage, external, driver minio, endpoint, bucket incoming, access_key_env / secret_key_env",
                                   "Write `app/archive.py`; function `archive` with storage {resource: minio, prefix: docs/}",
                                   "Validate for onprem (staging), invoke one record"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.minio",
            value={"type": "storage", "external": True,
                   "options": {"driver": "minio", "endpoint": "http://minio.example.com:9000", "bucket": "incoming",
                               "access_key_env": "MINIO_ACCESS_KEY", "secret_key_env": "MINIO_SECRET_KEY"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/archive.py", content=FUTURE + """

def archive(event, ctx):
    done = []
    for record in event.records:
        ctx.logger.info("archive", extra={"bucket": record.bucket, "key": record.key, "action": record.action})
        done.append(record.key)
    return {"archived": done}
"""),
          S("set_config", path="functions.archive",
            value={"handler": "app.archive.archive", "events": [{"storage": {"resource": "minio", "prefix": "docs/"}}]}),
          S("invoke_local", function="archive", type="storage", data={"bucket": "incoming", "key": "contract.pdf"}),
      ],
      final="""Added:

```yaml
resources:
  minio:
    type: storage
    external: true
    options: {driver: minio, endpoint: "http://minio.example.com:9000", bucket: incoming,
              access_key_env: MINIO_ACCESS_KEY, secret_key_env: MINIO_SECRET_KEY}
functions:
  archive:
    handler: app.archive.archive
    events:
      - storage: {resource: minio, prefix: docs/}
```

- validate (onprem, staging): valid.
- invoke: `{"archived": ["contract.pdf"]}`. The host strips `prefix` from `record.key`, so `docs/contract.pdf` arrives as `contract.pdf` [docs/resources.md#storage-drivers].
- The host polls and diffs the bucket every `poll_seconds`. Objects that already exist at first start are recorded, not emitted.

Export `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` where the host runs, or the host won't start. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 70
    B(70, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#choice-rules", "docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": """service: kyc
provider:
  name: gcp
  region: europe-west2
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  score:
    handler: app.kyc.score
  approve:
    handler: app.kyc.approve
  review:
    handler: app.kyc.review
""",
          "app/__init__.py": "",
          "app/kyc.py": FUTURE + """

def score(event, ctx):
    applicant = dict(event.data or {})
    if "country" not in applicant:
        raise KeyError("country")
    return {**applicant, "risk": 80 if applicant["country"] not in ("DE", "FR") else 10}


def approve(event, ctx):
    return {**(event.data or {}), "status": "approved"}


def review(event, ctx):
    return {**(event.data or {}), "status": "in_review"}
""",
          "requirements.txt": ""}),
      user="Please add workflow `kyc-flow`: Score (function score). If $.risk >= 50, wait 300 seconds and then Review; otherwise Approve. If score raises KeyError, go straight to Review with the error stored under $.error.",
      steps=[
          S("get_project"),
          S("search_docs", query="choice gte wait catch result_path error",
            docs=[D("docs/workflows.md", "retry-and-catch", start="catch:", end="result_path: \"$.error\"")]),
          S("propose_plan", steps=["Add workflow `kyc-flow`: Score (task, catch [KeyError] -> Review, result_path $.error) -> Route",
                                   "Route: choice $.risk gte 50 -> Hold, default Approve; Hold: wait 300 s -> Review",
                                   "Review and Approve: tasks that end",
                                   "Validate for gcp (prod) and run score locally"],
            result={"decision": "approved", "note": "call it signup-check instead of kyc-flow"}),
          S("set_config", path="workflows.signup-check",
            value={"start_at": "Score",
                   "states": {"Score": {"type": "task", "function": "score", "next": "Route",
                                        "catch": [{"errors": ["KeyError"], "next": "Review", "result_path": "$.error"}]},
                              "Route": {"type": "choice",
                                        "choices": [{"variable": "$.risk", "gte": 50, "next": "Hold"}],
                                        "default": "Approve"},
                              "Hold": {"type": "wait", "seconds": 300, "next": "Review"},
                              "Review": {"type": "task", "function": "review", "end": True},
                              "Approve": {"type": "task", "function": "approve", "end": True}}},
            say="Naming it `signup-check`, as you asked."),
          S("invoke_local", function="score", type="workflow", data={"name": "Ana", "country": "BR"}),
      ],
      final="""Added the workflow as **`signup-check`** (renamed, per your note):

```yaml
workflows:
  signup-check:
    start_at: Score
    states:
      Score:
        type: task
        function: score
        catch: [{errors: [KeyError], next: Review, result_path: $.error}]
        next: Route
      Route:
        type: choice
        choices: [{variable: $.risk, gte: 50, next: Hold}]
        default: Approve
      Hold:    {type: wait, seconds: 300, next: Review}
      Review:  {type: task, function: review, end: true}
      Approve: {type: task, function: approve, end: true}
```

- `pskit validate` (gcp, prod): valid. It deploys as Cloud Workflows, so the 300 s wait is not billed as function time.
- `score` run locally for country BR: returned `"risk": 80`, so this applicant goes the Hold -> Review way.

Locally, `pskit workflow run signup-check -i '{"name": "Ana"}' --history` shows the KeyError -> Review path. Wait states are skipped unless you add `--sleep`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 71
    B(71, provider="alibaba", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#errors", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: tea-shop
provider:
  name: alibaba
  region: cn-shenzhen
functions: {}
""",
          "requirements.txt": ""}),
      user="make POST /orders for alibaba. need item and qty, qty must positive else error 400. give 512mb memory",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/orders.py`: check item and qty > 0, BadRequest (400) otherwise, return 201 with the order",
                                   "Add function `create-order` on POST /orders with memory 512",
                                   "Validate for alibaba and post one order locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/orders.py", content=FUTURE + """import uuid

from py_serverless_kit import BadRequest


def create_order(event, ctx):
    order = event.http.json(default={}) or {}
    qty = order.get("qty")
    if not order.get("item") or not isinstance(qty, int) or qty <= 0:
        raise BadRequest("need item and a positive qty")
    return {"order_id": uuid.uuid4().hex[:8], "item": order["item"], "qty": qty}, 201
"""),
          S("set_config", path="functions.create-order",
            value={"handler": "app.orders.create_order", "memory": 512, "events": [{"http": "POST /orders"}]}),
          S("invoke_local", function="create-order", method="POST", path="/orders", data={"item": "oolong", "qty": 2}),
      ],
      final="""Done. `create-order` is on `POST /orders` with 512 MB memory.

- Without `item`, or with `qty` 0 or below, it answers 400 `need item and a positive qty` [docs/handlers.md#errors].
- `pskit validate` for alibaba: valid.
- Local POST `{"item": "oolong", "qty": 2}`: status 201 with a new `order_id`.

Test the error: `pskit invoke -f create-order -d '{"item": "oolong", "qty": 0}'`, or use **Test** > **▶ Run locally**. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 72
    B(72, provider="tencent", stage="staging", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: stock-sync
provider:
  name: tencent
  region: ap-beijing
functions:
  sync:
    handler: app.sync.run
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """

def run(event, ctx):
    warehouse = (event.data or {}).get("warehouse", "main")
    ctx.logger.info("stock sync", extra={"warehouse": warehouse})
    return {"warehouse": warehouse, "synced": True}
""",
          "requirements.txt": ""}),
      user="`sync` must run every 30 minutes on SCF with input {\"warehouse\": \"north\"}, and give it a 60 s timeout because the sync can be slow.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Set functions.sync.timeout = 60",
                                   "Add schedule {rate: 30 minutes, input: {warehouse: north}} to `sync`",
                                   "Validate for tencent (staging) and run the schedule locally"]),
          S("set_config", path="functions.sync.timeout", value=60),
          S("set_config", path="functions.sync.events",
            value=[{"schedule": {"rate": "30 minutes", "input": {"warehouse": "north"}}}]),
          S("invoke_local", function="sync", type="schedule"),
      ],
      final="""Updated `sync`:

```yaml
functions:
  sync:
    timeout: 60
    events:
      - schedule: {rate: 30 minutes, input: {warehouse: north}}
```

- validate (tencent, staging): valid after both changes. pskit turns the rate into Tencent's 7-field timer cron [docs/events.md#schedule].
- local schedule run: `{"warehouse": "north", "synced": true}`.

Retest: `pskit invoke -f sync -t schedule`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 73
    B(73, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#engines"],
      project=dict(files={
          "pskit.yml": """service: trial-emails
provider:
  name: aws
  region: us-east-1
functions:
  send-reminder:
    handler: app.mail.reminder
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """

def reminder(event, ctx):
    user = event.data or {}
    ctx.logger.info("reminder", extra={"email": user.get("email")})
    return {"reminded": user.get("email")}
""",
          "requirements.txt": ""}),
      user="when someone starts a trial, I want them to get a reminder email one day later. how do I make it wait a day?",
      steps=[
          S("get_project"),
          S("search_docs", query="wait state seconds workflow",
            docs=[D("docs/workflows.md", "state-types", start="| `wait` |", end="| `wait` |"),
                  D("docs/workflows.md", "engines", start="| aws | native |", end="| aws | native |")]),
          S("propose_plan", steps=["Add workflow `trial-reminder`: WaitADay (wait 86400 seconds) -> Remind (task send-reminder, end)",
                                   "Validate for aws and run send-reminder locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.trial-reminder",
            value={"start_at": "WaitADay",
                   "states": {"WaitADay": {"type": "wait", "seconds": 86400, "next": "Remind"},
                              "Remind": {"type": "task", "function": "send-reminder", "end": True}}}),
          S("invoke_local", function="send-reminder", type="workflow", data={"email": "trial.user@example.com"}),
      ],
      final="""You make it wait with a **workflow**. Its first step waits one day (86400 seconds), and then it runs your `send-reminder` function:

```yaml
workflows:
  trial-reminder:
    start_at: WaitADay
    states:
      WaitADay: {type: wait, seconds: 86400, next: Remind}
      Remind:   {type: task, function: send-reminder, end: true}
```

On AWS this becomes a Step Functions state machine. The waiting happens there, so no function runs (or costs money) during the day [docs/workflows.md#engines].

- `pskit validate` for aws: valid.
- `send-reminder` run locally: `{"reminded": "trial.user@example.com"}`.

Start one run per new trial, with input like `{"email": "..."}`. Your signup code can start the state machine (AWS SDK `start_execution`). Try it locally with `pskit workflow run trial-reminder -i '{"email": "a@example.com"}'`; without `--sleep` it skips the wait. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 74
    B(74, provider="onprem", stage="dev", mode="auto", page="Resources", persona="beginner",
      sources=["docs/resources.md#fields", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: web-sessions
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8106
functions:
  login:
    handler: app.auth.login
    events:
    - http: POST /login
""",
          "app/__init__.py": "",
          "app/auth.py": FUTURE + """

def login(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="we have a memcached box at cache.example.com port 11211 for sessions. how does my login function know where it is?",
      steps=[
          S("get_project"),
          S("search_docs", query="cache resource connection resource() handler",
            docs=[D("docs/resources.md", "runtime-api", end="resources()                      #")]),
          S("propose_plan", steps=["Add resource `sessions`: type cache, external, connection host cache.example.com, port 11211",
                                   "Make `login` read it with resource(\"sessions\") and return the address (to check it)",
                                   "Validate for onprem and call /login locally"]),
          S("set_config", path="resources.sessions",
            value={"type": "cache", "external": True, "connection": {"host": "cache.example.com", "port": 11211}}),
          S("write_file", path="app/auth.py", content=FUTURE + """from py_serverless_kit import resource


def login(event, ctx):
    cache = resource("sessions")
    return {"ok": True, "session_store": f'{cache["host"]}:{cache["port"]}'}
"""),
          S("validate"),
          S("invoke_local", function="login", method="POST", path="/login"),
      ],
      final="""You describe the memcached box once in pskit.yml as a resource, and the function reads it with `resource("sessions")`:

```yaml
resources:
  sessions:
    type: cache
    external: true
    connection: {host: cache.example.com, port: 11211}
```

pskit never touches the cache. It only passes the host and port to your functions [docs/resources.md#runtime-api].

- `pskit validate` for onprem: valid.
- Local call to `/login`: 200, `"session_store": "cache.example.com:11211"`, so the function finds it.

Next you'd connect with a memcached client library (add it to requirements.txt). In studio, **Resources** > **How to use** shows code for each resource. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 75
    B(75, provider="digitalocean", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#errors", "docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: newsletter-signup
provider:
  name: digitalocean
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE, fn-00000000-0000-0000-0000-000000000000}
functions: {}
""",
          "requirements.txt": ""}),
      user="Build `subscribe` on POST /subscribe: body {\"email\": ..., \"list\": \"weekly\"|\"monthly\"}. 422 with details when email lacks @ or the list is unknown, otherwise 202. The mailing provider credential is in MAILING_API_KEY on the deploy machine; the function should only report whether it's configured for now.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/subscribe.py`: UnprocessableEntity with details for bad email/list, else 202 {queued, configured}",
                                   "Add function `subscribe` on POST /subscribe with MAILING_API_KEY: ${env:MAILING_API_KEY, }",
                                   "Validate for digitalocean (staging) and post a valid body locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/subscribe.py", content=FUTURE + """from py_serverless_kit import UnprocessableEntity

LISTS = ("weekly", "monthly")


def subscribe(event, ctx):
    body = event.http.json(default={}) or {}
    problems = {}
    if "@" not in str(body.get("email", "")):
        problems["email"] = "must contain @"
    if body.get("list") not in LISTS:
        problems["list"] = f"one of {', '.join(LISTS)}"
    if problems:
        raise UnprocessableEntity("invalid subscription", details=problems)
    configured = bool(ctx.env.get("MAILING_API_KEY"))
    return {"queued": body["email"], "list": body["list"], "configured": configured}, 202
"""),
          S("set_config", path="functions.subscribe",
            value={"handler": "app.subscribe.subscribe",
                   "environment": {"MAILING_API_KEY": "${env:MAILING_API_KEY, }"},
                   "events": [{"http": "POST /subscribe"}]}),
          S("invoke_local", function="subscribe", method="POST", path="/subscribe",
            data={"email": "reader@example.com", "list": "weekly"}),
      ],
      final="""Added `subscribe` on `POST /subscribe`:

- Bad input gives 422 `{"error": "invalid subscription", "details": {...}}`, with one entry per bad field [docs/handlers.md#errors].
- Good input gives 202 with `queued`, `list`, and `configured` (whether `MAILING_API_KEY` is set).

Checks:
- `pskit validate` (digitalocean, staging): valid, with the `doctl` warning. doctl isn't installed here, and deploy needs it.
- Local POST `{"email": "reader@example.com", "list": "weekly"}`: 202 with `"configured": false`, because the key isn't set on this machine.

pskit.yml holds only `${env:MAILING_API_KEY, }`. The value comes from the deploy machine's environment [docs/configuration.md#variables]. Test the 422 with `pskit invoke -f subscribe -d '{"email": "x", "list": "daily"}'`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 76
    B(76, provider="gcp", stage="prod", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: pricing
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  quote:
    handler: app.pricing.quote
    memory: 256
    events:
    - http: POST /quote
""",
          "app/__init__.py": "",
          "app/pricing.py": FUTURE + """

def quote(event, ctx):
    return {"memory_mb": ctx.memory_mb}
""",
          "requirements.txt": ""}),
      user="prod only: quote 1024 MB, timeout 60. dev/staging stay as is",
      steps=[
          S("get_project"),
          S("search_docs", query="stages per-stage overrides",
            docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["stages.prod.functions.quote: memory 1024, timeout 60",
                                   "Validate for gcp with stage prod"]),
          S("set_config", path="stages.prod.functions.quote", value={"memory": 1024, "timeout": 60}),
      ],
      final="""Added a prod-only override:

```yaml
stages:
  prod:
    functions:
      quote: {memory: 1024, timeout: 60}
```

- validate (gcp, prod): valid. dev and staging keep 256 MB and the default 30 s, because `stages.<stage>` is merged only for that stage [docs/configuration.md#stages-per-stage-overrides].

No code changed. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 77
    B(77, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=dict(files={
          "pskit.yml": """service: file-audit
provider:
  name: azure
  region: eastus
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions:
  on-upload:
    handler: app.audit.on_change
    events:
    - storage: {bucket: uploads, events: [created]}
providers:
  aws:
    region: us-east-1
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """

def on_change(event, ctx):
    return {"changes": [{"key": r.key, "action": r.action} for r in event.records]}
""",
          "requirements.txt": ""}),
      user="also want function when file is deleted from uploads. we deploy this to azure and aws both",
      steps=[
          S("get_project"),
          S("search_docs", query="azure blob deleted events storage",
            docs=[D("docs/events.md", "storage", start="| azure | Blob trigger", end="| azure | Blob trigger")]),
          S("ask_user", question="Azure blob triggers only fire on created/updated blobs, so a delete trigger can't run on Azure. What should I do?",
            options=["Add it for AWS only (switched off on Azure)", "Skip it"],
            answer="Add it for AWS only (switched off on Azure)"),
          S("propose_plan", steps=["Add function `on-delete` (same handler) with storage {bucket: uploads, events: [deleted]}",
                                   "Switch it off on Azure: providers.azure.functions.on-delete.enabled = false",
                                   "Validate for azure and aws (the handler is reused, no code change)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.on-delete",
            value={"handler": "app.audit.on_change", "events": [{"storage": {"bucket": "uploads", "events": ["deleted"]}}]},
            run_provider="aws"),
          S("set_config", path="providers.azure.functions.on-delete.enabled", value=False),
          S("validate", provider="aws"),
      ],
      final="""Added `on-delete` for AWS and switched it off on Azure:

```yaml
functions:
  on-delete:
    handler: app.audit.on_change
    events:
      - storage: {bucket: uploads, events: [deleted]}
providers:
  azure:
    functions:
      on-delete: {enabled: false}
```

- `pskit validate` for azure: valid, with the warning `on-delete` disabled (not deployed) [docs/configuration.md#switch-something-off-on-one-cloud].
- `pskit validate` for aws: valid. Both functions are deployed there.

It reuses `on_change`, which already reports `record.action` (`"deleted"` here), so no code changed. Local test against AWS: `pskit invoke -p aws -f on-delete -t storage -d '{"bucket": "uploads", "key": "old.txt"}'`. Deploy: `pskit deploy -p aws -s dev` and `pskit deploy -p azure -s dev`, or the **Deploy** page with each target provider."""),

    # ------------------------------------------------------------------ 78
    B(78, provider="huawei", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: partner-feed
provider:
  name: huawei
  region: cn-north-4
  options:
    apig_instance_id: ${env:HUAWEI_APIG_INSTANCE_ID, 00000000000000000000000000000000}
functions:
  feed:
    handler: app.feed.public_feed
    events:
    - http: GET /feed
""",
          "app/__init__.py": "",
          "app/feed.py": FUTURE + """

def public_feed(event, ctx):
    return {"items": ["public news"]}
""",
          "requirements.txt": ""}),
      user="our partners should get a special feed that normal visitors can't open. is there some kind of app key thing on huawei?",
      steps=[
          S("get_project"),
          S("search_docs", query="http auth key huawei app",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("propose_plan", steps=["Add `partner_feed` to `app/feed.py`",
                                   "Add function `partner-feed` on GET /partner/feed with auth: key (Huawei APP auth)",
                                   "Validate for huawei and call it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/feed.py", content=FUTURE + """

def public_feed(event, ctx):
    return {"items": ["public news"]}


def partner_feed(event, ctx):
    return {"items": ["public news", "partner price list"]}
"""),
          S("set_config", path="functions.partner-feed",
            value={"handler": "app.feed.partner_feed",
                   "events": [{"http": {"path": "/partner/feed", "method": "GET", "auth": "key"}}]}),
          S("invoke_local", function="partner-feed", method="GET", path="/partner/feed"),
      ],
      final="""Yes. On Huawei, `auth: key` uses API Gateway **APP** authentication, so only callers with app credentials can open it [docs/events.md#http].

I added `partner-feed` on `GET /partner/feed` with `auth: key`. The normal `/feed` stays public.

- `pskit validate` for huawei: valid.
- Local call: 200 with the partner items. Locally there is no key check, so that only happens after deploy.

After you deploy (**Deploy** page or `pskit deploy -s dev`), create an app for each partner in the Huawei API Gateway console and give them its credentials. Test locally again with `pskit invoke -f partner-feed`."""),

    # ------------------------------------------------------------------ 79
    B(79, provider="onprem", stage="dev", mode="auto", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: label-print
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8107
functions:
  print-label:
    handler: app.labels.print_label
""",
          "app/__init__.py": "",
          "app/labels.py": FUTURE + """

def print_label(event, ctx):
    parcel = event.data or {}
    ctx.logger.info("print", extra={"parcel": parcel.get("id")})
    return {"printed": parcel.get("id")}
""",
          "requirements.txt": ""}),
      user="workflow get list of parcels, print label each one, max 3 same time. input like {parcels:[{id:..}]}",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add workflow `print-all`: map state EachParcel over $.parcels, max_concurrency 3, iterator task print-label",
                                   "Validate for onprem, run print-label locally on one parcel"]),
          S("set_config", path="workflows.print-all",
            value={"start_at": "EachParcel",
                   "states": {"EachParcel": {"type": "map", "items_path": "$.parcels", "max_concurrency": 3,
                                             "iterator": {"start_at": "Print",
                                                          "states": {"Print": {"type": "task", "function": "print-label",
                                                                               "end": True}}},
                                             "end": True}}}),
          S("invoke_local", function="print-label", type="workflow", data={"id": "PX-881"}),
      ],
      final="""Added `print-all`:

```yaml
workflows:
  print-all:
    start_at: EachParcel
    states:
      EachParcel:
        type: map
        items_path: $.parcels
        max_concurrency: 3
        iterator:
          start_at: Print
          states:
            Print: {type: task, function: print-label, end: true}
        end: true
```

- validate (onprem): valid. It runs on the embedded engine in the host. The result is a list with one item per parcel [docs/workflows.md#state-types].
- `print-label` local run: `{"printed": "PX-881"}`.

Try all: `pskit workflow run print-all -i '{"parcels": [{"id": "A"}, {"id": "B"}]}'`. After deploy: `POST /workflows/print-all` on the host. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 80
    B(80, provider="aws", stage="dev", mode="ask", page="Overview", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: shorty
provider:
  name: aws
  region: eu-north-1
functions: {}
""",
          "requirements.txt": ""}),
      user="new project: url shortener. POST /links {url} -> code, GET /l/{code} -> 302. in-memory store fine for now",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/links.py`: create_link (201 {code}), follow (Response.redirect 302, NotFound otherwise), shared dict",
                                   "Add `create-link` POST /links and `follow` GET /l/{code}",
                                   "Validate for aws, invoke both"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/links.py", content=FUTURE + """import hashlib

from py_serverless_kit import BadRequest, NotFound, Response

LINKS = {"demo": "https://www.example.com/"}


def create_link(event, ctx):
    url = (event.http.json(default={}) or {}).get("url", "")
    if not url.startswith(("http://", "https://")):
        raise BadRequest("url must start with http:// or https://")
    code = hashlib.sha1(url.encode("utf-8")).hexdigest()[:7]
    LINKS[code] = url
    return {"code": code}, 201


def follow(event, ctx):
    url = LINKS.get(event.http.path_params["code"])
    if url is None:
        raise NotFound("unknown code")
    return Response.redirect(url, status=302)
"""),
          S("set_config", path="functions.create-link",
            value={"handler": "app.links.create_link", "events": [{"http": "POST /links"}]}),
          S("set_config", path="functions.follow",
            value={"handler": "app.links.follow", "events": [{"http": "GET /l/{code}"}]}),
          S("invoke_local", function="create-link", method="POST", path="/links", data={"url": "https://docs.example.com/guide"}),
          S("invoke_local", function="follow", method="GET", path="/l/demo"),
      ],
      final="""Scaffolded:

```yaml
functions:
  create-link:
    handler: app.links.create_link
    events: [{http: POST /links}]
  follow:
    handler: app.links.follow
    events: [{http: "GET /l/{code}"}]
```

- validate (aws): valid.
- invoke `POST /links`: 201 with a 7-char `code`. Invoke `GET /l/demo`: 302 with `location: https://www.example.com/`.

Caveat: `LINKS` is per-instance memory, and the two functions are separate Lambdas, so a code made by `create-link` is **not** visible to `follow` after deploy. Before real use, back it with a shared store (e.g. an external `database` resource). Deploy: **Deploy** or `pskit deploy -s dev`."""),
]
