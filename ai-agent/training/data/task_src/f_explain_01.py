"""Category F (explain a config or handler), batch 1. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def F(n, **kw):
    return dict(id=f"f_explain-{n:04d}", category="f_explain", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 1 queue worker config
    F(1, provider="aws", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/events.md#queue"],
      project=dict(base="examples/04-queue-worker"),
      user="what does this config do? i'm new to this",
      steps=[S("get_project"), S("validate")],
      final="""It's a small job system with three functions. Validate for aws says it's valid.

1. **enqueue**: a web endpoint, `POST /jobs`. You call it to add a job.
2. **process-jobs**: reads the `jobs` queue. It gets up to 10 messages at a time (`batch_size: 10`) and waits up to 5 seconds to fill a batch (`batch_window`). A message that fails 5 times (`max_receive`) moves to the `jobs-dlq` queue (`dead_letter`).
3. **audit-dead-letters**: reads `jobs-dlq`, so failed jobs are logged and not forgotten.

Other parts:
- `provider`: AWS in `us-east-1`, 60 s timeout, and every function gets the variable `JOBS_QUEUE=jobs`.
- `providers`: settings used only when you target gcp, azure or onprem (region, GCP project, Azure subscription, on-prem host and port).

More about queue options: [docs/events.md#queue]."""),

    # ------------------------------------------------------------------ 2 schedules on gcp
    F(2, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(base="examples/03-scheduled-jobs"),
      user="explain me this yml, what run when?",
      steps=[S("get_project"), S("validate")],
      final="""Three scheduled functions, nothing called from the web. Validate for gcp/staging: valid.

| Function | When | Notes |
|---|---|---|
| `heartbeat` | every 5 minutes | `schedule: 5 minutes` is short for `rate` |
| `daily-report` | 09:00 Mon-Fri, Berlin time | `input` (`report: sales`, `days: 1`, recipients) arrives as `event.data` |
| `daily-report` (`weekly`) | 07:00 every Monday | no `timezone`, so UTC; input `sales-weekly`, 7 days |
| `cleanup` | once a day | `input: {retention_days: 90}`; `enabled` comes from `CLEANUP_ENABLED` (default true) |

On gcp the `providers.gcp` block applies: region `europe-west3`, the GCP project from `GOOGLE_CLOUD_PROJECT`, and `cleanup` gets a 540 s timeout instead of 900, since that's GCP's limit for event-triggered functions. See [docs/events.md#schedule]."""),

    # ------------------------------------------------------------------ 3 storage events on azure
    F(3, provider="azure", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#storage"],
      project=dict(base="examples/05-storage-events"),
      user="Coming from S3 notifications in SAM. Walk me through this pskit.yml, especially what changes on Azure.",
      steps=[S("get_project"), S("validate")],
      final="""Three functions react to bucket events. On Azure, a "bucket" is a blob container. Validate for azure: valid.

**Base config (S3-style)**
- `custom.bucket`: one name, reused with `${self:custom.bucket}`. It's `DATA_BUCKET` (or a demo default) plus `-${opt:stage}`, so dev and prod get different buckets.
- `import-csv`: runs on **created** objects under `incoming/` ending in `.csv`. pskit creates this bucket.
- `purge-index`: runs on **deleted** objects in the same bucket.
- `audit-existing`: listens to a bucket that already exists (`existing: true`). pskit looks it up but never creates or deletes it.

**What `providers.azure` changes**
- Region `eastus`, and the subscription from `ARM_SUBSCRIPTION_ID`.
- `purge-index` gets `events: []`. Azure blob triggers only fire on created/updated blobs, so this function is deployed without a trigger [docs/events.md#storage].
- `audit-existing` listens to an app-owned container `audit-uploads` (created only) instead of the shared bucket.

The handler code is the same everywhere; only these overrides differ."""),

    # ------------------------------------------------------------------ 4 explain a BatchResult handler + show it
    F(4, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#batchresult"],
      project=dict(base="examples/04-queue-worker"),
      user="can you explain my worker handler? what is this BatchResult thing",
      steps=[
          S("read_file", path="app/worker.py"),
          S("invoke_local", function="process-jobs", type="queue",
            data=[{"kind": "email", "id": 1}, {"kind": "email", "id": 2, "simulate_failure": True},
                  {"kind": "fax", "id": 3}],
            say="Let me run it with three messages so you can see each case."),
      ],
      final="""`process_jobs` gets a batch of queue messages in `event.records` and handles each one:

- **Works**: logs `job done`.
- **Bad payload** (an unknown `kind`, which raises `PermanentError`): logs `dropping message` and doesn't retry. Retrying wouldn't help.
- **Any other error**: logs it and calls `result.fail(record)`.

`BatchResult` is the list of messages that failed. On premises and on AWS SQS, only those come back for another try; the others count as done [docs/handlers.md#batchresult].

The local run shows all three cases. Message 1 is done. Message 3 (`fax`) is dropped. Message 2 (`simulate_failure`) raised `RuntimeError`, so the output is `{"batchItemFailures": [...]}` with that one message. After `max_receive: 5` failed tries it goes to `jobs-dlq`, and `audit_dead_letters` logs it there."""),

    # ------------------------------------------------------------------ 5 config that can't run on cloudflare
    F(5, provider="cloudflare", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#cloudflare-workers"],
      project=dict(files={
          "pskit.yml": """service: edge-orders
provider:
  name: cloudflare
  options:
    account_id: 0123456789abcdef0123456789abcdef
functions:
  api:
    handler: app.orders.api
    events:
      - http: POST /orders
  worker:
    handler: app.orders.worker
    events:
      - queue: orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + "def api(event, ctx):\n    return {\"queued\": True}, 202\n\n\ndef worker(event, ctx):\n    return None\n"}),
      user="what this config do? and its ok for cloudflare?",
      steps=[S("get_project"), S("validate")],
      final="""It's meant to be an API plus a background worker:
- `api`: `POST /orders`, answers 202.
- `worker`: reads messages from a queue named `orders`.

But it's **not ok for Cloudflare**. Validate fails with: `Cloudflare Workers does not support `queue` events in pskit (supported: http, schedule)`. Workers in pskit only do HTTP and schedules [docs/providers.md#cloudflare-workers].

Options:
1. Keep `api` on Cloudflare and switch `worker` off there (`providers.cloudflare.functions.worker.enabled: false`).
2. Deploy the whole service to a provider with queues (aws, gcp, azure, onprem).

Tell me which one and I'll make the change."""),

    # ------------------------------------------------------------------ 6 huawei missing APIG
    F(6, provider="huawei", stage="dev", mode="ask", page="Overview", persona="terse_expert",
      sources=["docs/providers.md#huawei-functiongraph"],
      project=dict(files={
          "pskit.yml": """service: points
provider:
  name: huawei
  region: cn-north-4
  memory: 512
functions:
  balance:
    handler: app.points.balance
    events:
      - http: GET /points/{user_id}
  expire:
    handler: app.points.expire
    events:
      - schedule: "0 2 * * *"
""",
          "app/__init__.py": "",
          "app/points.py": FUTURE + "def balance(event, ctx):\n    return {\"user\": event.http.path_params[\"user_id\"], \"points\": 0}\n\n\ndef expire(event, ctx):\n    return None\n"}),
      user="summarize this config + anything wrong for huawei?",
      steps=[S("get_project"), S("validate")],
      final="""Summary:
- FunctionGraph in `cn-north-4`, 512 MB for every function.
- `balance`: `GET /points/{user_id}`; the id lands in `event.http.path_params["user_id"]`.
- `expire`: cron `0 2 * * *`, every day at 02:00 UTC.

Problem: validate fails with `HTTP events need a dedicated API Gateway instance: set provider.options.apig_instance_id`. That comes from `balance`: Huawei HTTP triggers need a dedicated APIG instance [docs/providers.md#huawei-functiongraph]. `expire` alone would be fine.

Fix: add `provider.options.apig_instance_id: <your instance id>`. Give me the id and I'll set it."""),

    # ------------------------------------------------------------------ 7 workflow walkthrough
    F(7, provider="aws", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#engines"],
      project=dict(base="examples/07-workflow-orders"),
      user="Explain the order-pipeline workflow state by state, and which engine runs it on AWS.",
      steps=[S("get_project"), S("validate")],
      final="""`order-pipeline` starts at `Validate`. With `engine: auto`, on AWS it runs as a Step Functions state machine (native) [docs/workflows.md#engines]. Validate: valid, 5 functions and 1 workflow.

1. **Validate** (task `validate-order`): a `ValueError` goes to `Rejected`, with the error stored at `$.error`.
2. **Route** (choice): total > 1000 and the customer is not VIP → `ManualReview`. Channel `b2b` or currency `CHF` → `Invoice`. Anything else → `Reserve`.
3. **ManualReview** (wait 30 s) → `Reserve`.
4. **Invoice** (pass): writes `{status: invoiced}` to `$.payment` → `Fulfil`.
5. **Reserve** (map): runs `reserve-item` for each entry of `$.items`, 5 at a time, and stores the results in `$.reservations`. `OutOfStock` → `Rejected`.
6. **Charge** (task `charge-payment`): `PaymentGatewayTimeout` is retried 3 times (2 s, then backoff ×2). `PaymentDeclined` → `Declined`.
7. **Fulfil** (parallel): `send-confirmation` and `create-shipment` run at the same time → `Done`.
8. **Done** succeeds. **Declined** and **Rejected** fail with their error and cause.

The whole run times out after 3600 s. State types: [docs/workflows.md#state-types]."""),

    # ------------------------------------------------------------------ 8 fan-out handler on gcp
    F(8, provider="gcp", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(base="examples/06-pubsub-topic"),
      user="On AWS the SNS filter policy handles this. Explain app/subscribers.py and whether the filter still works on GCP.",
      steps=[S("read_file", path="app/subscribers.py"), S("validate")],
      final="""Two subscribers on the same topic `order-events` (fan-out: each gets every message):

- `update_analytics`: counts messages per `event_type` attribute, logs each one, and returns `{"counts": {...}}`.
- `notify_customer`: should only see `order.shipped`. For those it reads the JSON body and logs the order id and email, then returns the ids it notified.

On GCP the `filter` in pskit.yml is not applied by Pub/Sub triggers [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. `notify_customer` would receive every event, but `_wants()` checks the `event_type` attribute again in code and skips the others. So the behaviour matches AWS, where SNS filters first.

Validate for gcp: valid. No change needed."""),

    # ------------------------------------------------------------------ 9 stages + variables
    F(9, provider="aws", stage="staging", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#variables", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(base="examples/10-stages-and-config", files={
          "config/limits.json": """{
  "dev": {"memory": 256, "concurrency": 2},
  "staging": {"memory": 512, "concurrency": 10},
  "prod": {"memory": 1024, "concurrency": 100}
}
"""}),
      user="what do the variables resolve to on staging?",
      steps=[S("get_project"), S("read_file", path="config/limits.json"), S("validate")],
      final="""For `-s staging` (validate: valid):

| Key | Value on staging | From |
|---|---|---|
| `custom.table` / `TABLE_NAME` | `shop-config-staging-orders` | `${self:service}-${opt:stage}-orders` |
| `provider.region` | `AWS_REGION`, else `eu-west-1` | `${env:AWS_REGION, eu-west-1}` |
| `provider.memory` | 512 | `stages.staging` → `limits.staging.memory` in config/limits.json |
| `LOG_LEVEL` | `INFO` | `stages.staging.provider.environment` |
| `FEATURE_NEW_CHECKOUT` | `"true"` | base (only prod sets `"false"`) |
| `API_BASE_URL` | `https://api-staging.example.com` | `${opt:stage}` |
| `PAYMENT_API_KEY` | `PAYMENT_API_KEY` from the environment, else empty | `${env:PAYMENT_API_KEY, }` |

The `stages.prod` block (eu-central-1, S3 state, concurrency 100) doesn't apply. `${self:...}`, `${opt:...}`, `${env:...}` and `${file(...)}` are explained in [docs/configuration.md#variables]; stage overrides in [docs/configuration.md#stages-per-stage-overrides]."""),

    # ------------------------------------------------------------------ 10 invoke() handler, with a run
    F(10, provider="aws", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(base="examples/09-function-invoke"),
      user="how does quote get the price? i don't see any URL in the code",
      steps=[
          S("read_file", path="app/quotes.py"),
          S("invoke_local", function="quote", method="POST", path="/quote",
            data={"items": [{"sku": "lamp", "qty": 2, "unit_price": 10}], "country": "DE"}),
      ],
      final="""`quote` doesn't need a URL. It calls the other function by its pskit name:

```python
price = invoke("price-calculator", {"items": body["items"], "country": body.get("country", "US")})
```

pskit finds the deployed function for you on each cloud [docs/handlers.md#invoke-calling-another-function]. `price-calculator` gets an event with `event.type == "invoke"`, adds tax for the country, and returns the totals. `quote` then calls `audit-log` with `asynchronous=True` (fire-and-forget on AWS) and returns the price.

Locally, `invoke()` runs in the same process. With 2 lamps at 10 for DE, the call returned status 200 with subtotal 20.0, tax 3.8 (19%) and total 23.8.

On AWS this needs `lambda:InvokeFunction`, which is why `provider.iam.statements` is in pskit.yml."""),

    # ------------------------------------------------------------------ 11 async handlers
    F(11, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#context"],
      project=dict(base="examples/12-async-and-context"),
      user="why some functions here are async def? its ok for lambda?",
      steps=[
          S("read_file", path="app/handlers.py"),
          S("invoke_local", function="aggregate", method="GET", path="/aggregate"),
      ],
      final="""Yes, it's fine. pskit awaits `async def` handlers for you (with `asyncio.run` on most clouds), so Lambda never sees the coroutine.

- `aggregate` is async so it can wait for three "services" at the same time with `asyncio.gather`. The local run returned 200 with the three results; `elapsed_ms` is close to the slowest call, not the sum.
- `batch_job` is async and checks `ctx.remaining_time_ms()` in its loop. It stops early when less than 3 s are left before the timeout [docs/handlers.md#context].
- `inspect` is a normal `def`: it only returns what the runtime knows (event summary, request id, stage, memory...), so it doesn't need async.

Mixing both kinds in one service is ok."""),

    # ------------------------------------------------------------------ 12 tencent PATCH
    F(12, provider="tencent", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: profile-api
provider:
  name: tencent
  region: ap-guangzhou
functions:
  get-profile:
    handler: app.profile.get
    events:
      - http: GET /profile/{id}
  update-profile:
    handler: app.profile.update
    events:
      - http: PATCH /profile/{id}
""",
          "app/__init__.py": "",
          "app/profile.py": FUTURE + "def get(event, ctx):\n    return {\"id\": event.http.path_params[\"id\"]}\n\n\ndef update(event, ctx):\n    return {\"updated\": True}\n"}),
      user="""Tencent API Gateway does not support PATCH; use ANY
^ got this. what is my config doing and why is PATCH a problem?""",
      steps=[S("get_project"), S("validate")],
      final="""Your config has two routes on one path:
- `get-profile`: `GET /profile/{id}`. It reads the id from `event.http.path_params["id"]`.
- `update-profile`: `PATCH /profile/{id}`.

Tencent's API Gateway has no `PATCH` method [docs/events.md#http], so validate rejects `update-profile`. That's the error you pasted.

Ways out:
1. Change it to `PUT /profile/{id}` (client sends PUT).
2. Or use `ANY /profile/{id}`, as the error suggests. Then `update-profile` accepts any method, so it should check `event.http.method` and refuse what it doesn't handle.

Option 1 is the smaller, clearer change. Want me to do it?"""),

    # ------------------------------------------------------------------ 13 ibm runtime
    F(13, provider="ibm", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/providers.md#ibm-code-engine-functions"],
      project=dict(files={
          "pskit.yml": """service: rates
provider:
  name: ibm
  region: us-south
  runtime: python3.12
  timeout: 60
functions:
  rates:
    handler: app.rates.latest
    events:
      - http: GET /rates
""",
          "app/__init__.py": "",
          "app/rates.py": FUTURE + "def latest(event, ctx):\n    return {\"EUR\": 1.0}\n"}),
      user="quick review of this yml for ibm",
      steps=[S("get_project"), S("validate")],
      final="""One HTTP function, `rates` on `GET /rates`, 60 s timeout, in `us-south`. The timeout is fine (IBM max is 120 s).

The problem is `runtime: python3.12`. Validate: `IBM Cloud Code Engine does not support python3.12; use one of: python3.11`. Code Engine functions only run Python 3.11 [docs/providers.md#ibm-code-engine-functions].

Fix: `provider.runtime: python3.11`. Your handler has nothing 3.12-specific, so it runs unchanged."""),

    # ------------------------------------------------------------------ 14 digitalocean memory out of range
    F(14, provider="digitalocean", stage="prod", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#digitalocean-functions"],
      project=dict(files={
          "pskit.yml": """service: digest
provider:
  name: digitalocean
  region: ams3
  memory: 2048
  options:
    namespace: fn-00000000-0000-0000-0000-000000000000
functions:
  weekly-digest:
    handler: app.digest.send
    events:
      - schedule: "0 8 * * 1"
""",
          "app/__init__.py": "",
          "app/digest.py": FUTURE + "def send(event, ctx):\n    ctx.logger.info(\"sending digest\")\n"}),
      user="can you tell me what this does before i deploy it?",
      steps=[S("get_project"), S("validate")],
      final="""It runs one function, `weekly-digest`, every Monday at 08:00 (cron `0 8 * * 1`). It logs `sending digest`; nothing calls it from the web.

Validate for digitalocean/prod found one error, so don't deploy yet: `memory 2048 MB is outside DigitalOcean's 128-1024 MB range`. DigitalOcean Functions allow 128-1024 MB [docs/providers.md#digitalocean-functions]. There's also a warning that `doctl` isn't on PATH; deploys need it.

Fix: set `provider.memory` to 1024 or less. A small job like this is fine with 256. Shall I change it?"""),

    # ------------------------------------------------------------------ 15 embedded workflow on alibaba
    F(15, provider="alibaba", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: kyc
provider:
  name: alibaba
  region: cn-hangzhou
functions:
  check-id: {handler: app.kyc.check_id}
  notify: {handler: app.kyc.notify}
workflows:
  onboarding:
    start_at: Check
    states:
      Check: {type: task, function: check-id, next: Pause}
      Pause: {type: wait, seconds: 10, next: Notify}
      Notify: {type: task, function: notify, end: true}
""",
          "app/__init__.py": "",
          "app/kyc.py": FUTURE + "def check_id(event, ctx):\n    return {\"ok\": True}\n\n\ndef notify(event, ctx):\n    return {\"sent\": True}\n"}),
      user="Explain what the onboarding workflow does and how it runs on Alibaba, since Alibaba has no Step Functions.",
      steps=[S("get_project"), S("validate"),
             S("search_docs", query="embedded orchestrator workflow function",
               docs=[D("docs/workflows.md", "embedded-orchestrator", words=120)])],
      final="""`onboarding` runs three states in order:
1. **Check**: task `check-id`.
2. **Pause**: waits 10 seconds.
3. **Notify**: task `notify`, then ends.

Validate for alibaba is valid and reports `workflow onboarding: embedded engine`. Alibaba has no native workflow service in pskit, so the states run inside one extra function, the orchestrator, which calls `check-id` and `notify` for you [docs/workflows.md#embedded-orchestrator]:
- Start a run with `POST /workflows/onboarding` and the JSON input as the body, or invoke it directly.
- The answer is synchronous: `execution_id`, `status` (`SUCCEEDED` or `FAILED`) and the `output`.

Validate also warns that the whole run is capped by that function's timeout (3600 s max on Alibaba). The 10 s wait counts toward it.

Try it locally: `pskit workflow run onboarding -i '{"user": 1}'`."""),

    # ------------------------------------------------------------------ 16 jwt on gcp
    F(16, provider="gcp", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: admin-api
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  admin:
    handler: app.admin.handle
    events:
      - http:
          path: /admin/users
          method: GET
          cors:
            origins: ["https://admin.example.com"]
            allow_credentials: true
          auth: jwt
          authorizer:
            issuer: https://login.example.com/
            audience: [admin-api]
""",
          "app/__init__.py": "",
          "app/admin.py": FUTURE + "def handle(event, ctx):\n    return {\"users\": []}\n"}),
      user="explain the http block on admin",
      steps=[S("get_project"), S("validate")],
      final="""`admin` is `GET /admin/users` with:
- `cors`: only `https://admin.example.com` may call it from a browser, with cookies/credentials allowed (`allow_credentials: true`).
- `auth: jwt` + `authorizer`: the platform should only let requests through that carry a JWT from `https://login.example.com/` for audience `admin-api`.

The auth part doesn't work on GCP. Validate fails with `http auth 'jwt' is not supported on GCP; use none or iam`. JWT auth is AWS only in pskit [docs/events.md#http].

Choices:
1. `auth: iam` (callers need a Google identity), or
2. `auth: none` and check the token in the handler (read `event.http.headers["authorization"]`).

Tell me which and I'll update it."""),

    # ------------------------------------------------------------------ 17 multi-cloud overrides
    F(17, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=dict(base="examples/08-multi-cloud"),
      user="With serverless.yml I had one file per cloud. How does this single pskit.yml cover all of them?",
      steps=[S("get_project"), S("validate", provider="oracle")],
      final="""One base config, plus a `providers:` block per cloud that's merged on top only when that cloud is selected [docs/configuration.md#providers-per-cloud-overrides].

- **Base**: AWS, us-east-1, python3.12, 256 MB, 30 s, `APP_NAME`. Three functions: `whoami` (GET /whoami), `echo` (POST /echo with CORS) and `ticker` (every hour, `input: {source: multi-cloud}`).
- **Per cloud**: mostly region plus the required options: GCP `project`, Azure `subscription_id`, Huawei `apig_instance_id`, Oracle compartment/subnets/image repo, DigitalOcean `namespace`, Cloudflare `account_id`. The values come from env variables with demo defaults.
- **Runtime changes**: tencent python3.10; oracle, ibm and digitalocean python3.11.
- **Feature gaps**: on oracle and ibm, `ticker` gets `events: []` because neither runs schedules in pskit, so it's deployed without its trigger.

I checked one of the overridden clouds: validate with `-p oracle` is valid, with one warning that API Gateway needs an IAM policy to call the functions. You pick the cloud with `pskit deploy -p gcp`, or the provider select in studio's top bar. The handler code never changes. The folder also has `pskit.gcp.yml` etc. if you prefer one file per cloud."""),

    # ------------------------------------------------------------------ 18 hooks + package
    F(18, provider="onprem", stage="staging", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#hooks", "docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": """service: reports
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8095}
package:
  source: .
  exclude: ["docs/**", "*.ipynb"]
  requirements: requirements.txt
hooks:
  before_package: ["python scripts/build_templates.py"]
  after_deploy: ["python scripts/smoke_test.py"]
functions:
  render:
    handler: app.render.handle
    events:
      - http: GET /reports/{name}
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + "def handle(event, ctx):\n    return {\"report\": event.http.path_params[\"name\"]}\n",
          "scripts/build_templates.py": "print('templates built')\n",
          "scripts/smoke_test.py": "print('ok')\n",
          "requirements.txt": ""}),
      user="Please explain the package and hooks sections: what gets bundled, and when do the two scripts run?",
      steps=[S("get_project"), S("validate")],
      final="""**package** [docs/configuration.md#package]
- `source: .` bundles the project folder.
- `exclude` adds `docs/**` and notebooks to the default excludes (`.git`, `.venv`, `.pskit`, `tests`, `.env`, `pskit*.yml` and more), so they're not in the artifact.
- `requirements: requirements.txt` lists the dependencies (yours is empty).

**hooks** [docs/configuration.md#hooks]
- `before_package` runs `python scripts/build_templates.py` before every package, so also before a deploy.
- `after_deploy` runs `python scripts/smoke_test.py` once a deploy has finished.
Both run in the project root with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set. A non-zero exit aborts the command.

The function itself is `render` on `GET /reports/{name}`. Validate for onprem/staging: valid."""),

    # ------------------------------------------------------------------ 19 jwt on aws (works)
    F(19, provider="aws", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: aws
  region: eu-west-1
functions:
  invoices:
    handler: app.billing.invoices
    events:
      - http:
          method: GET
          path: /invoices
          auth: jwt
          authorizer:
            issuer: https://auth.example.com/
            audience: [billing]
  health:
    handler: app.billing.health
    events:
      - http: GET /health
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + "def invoices(event, ctx):\n    return {\"invoices\": []}\n\n\ndef health(event, ctx):\n    return {\"ok\": True}\n"}),
      user="what is auth jwt doing here? who can call my invoices?",
      steps=[S("get_project"), S("validate")],
      final="""Only callers with a valid login token can reach `GET /invoices`:

- `auth: jwt` puts a JWT authorizer on the API Gateway route.
- `issuer: https://auth.example.com/` means the token must come from that login server.
- `audience: [billing]` means it must be issued for this API.

Requests without such a token (`Authorization: Bearer <token>`) are refused before your code runs. `GET /health` has no `auth`, so it's public. JWT auth is AWS only in pskit, and it needs both `issuer` and `audience` [docs/events.md#http].

Validate for aws/prod: valid."""),

    # ------------------------------------------------------------------ 20 handler reads event.http in a queue function
    F(20, provider="azure", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: mailer
provider:
  name: azure
  region: westeurope
functions:
  send-mail:
    handler: app.mail.send
    events:
      - queue: outbox
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """

def send(event, ctx):
    msg = event.http.json()
    ctx.logger.info("sending", extra={"to": msg.get("to")})
    return {"sent": True}
"""}),
      user="explain my send function pls, i think something wrong",
      steps=[
          S("read_file", path="app/mail.py"),
          S("invoke_local", function="send-mail", type="queue", data=[{"to": "a@example.com"}]),
      ],
      final="""It should read a mail from the `outbox` queue, log the recipient, and return `{"sent": true}`.

You're right, something is wrong: it reads the message with `event.http.json()`. But `send-mail` is a queue function, so `event.http` is `None`. The local run with one message crashed with an `AttributeError` traceback.

Queue messages are in `event.records` [docs/handlers.md#event]:

```python
def send(event, ctx):
    for record in event.records:
        msg = record.json()
        ctx.logger.info("sending", extra={"to": msg.get("to")})
```

Want me to apply that fix and run it again?"""),
]
