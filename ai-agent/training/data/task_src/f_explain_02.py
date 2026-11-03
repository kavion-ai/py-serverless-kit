"""Category F (explain a config or handler), batch 2. Hand-written; assembled by tools/assemble.py.

Scope: aws / azure / gcp / onprem only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402,F401

FUTURE = "from __future__ import annotations\n\n"
GCP_OPTS = """  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
"""


def F(n, **kw):
    return dict(id=f"f_explain-{n:04d}", category="f_explain", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 21 on-prem example walkthrough
    F(21, provider="onprem", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(base="examples/16-on-premises"),
      user="i copied this on-prem example. what is it doing? in simple words",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 22 explain worker with a failing job
    F(22, provider="onprem", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#batchresult", "docs/providers.md#onprem-on-premises"],
      project=dict(base="examples/16-on-premises"),
      user="what worker function do when job has fail in it? explain pls",
      steps=[
          S("read_file", path="app/handlers.py"),
          S("invoke_local", function="worker", type="queue", data=[{"id": 1}, {"id": 2, "fail": True}],
            say="I'll run it with one good job and one with `fail` so you can see both."),
      ],
      final="TODO"),

    # ------------------------------------------------------------------ 23 aws fifo + dlq
    F(23, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: ledger
provider:
  name: aws
  region: eu-central-1
  timeout: 20
functions:
  post-entry:
    handler: app.ledger.post
    events:
      - queue:
          name: entries
          fifo: true
          batch_size: 1
          dead_letter: entries-dlq
          max_receive: 3
""",
          "app/__init__.py": "",
          "app/ledger.py": FUTURE + "def post(event, ctx):\n    for r in event.records:\n        ctx.logger.info(\"entry\", extra={\"id\": r.id})\n"}),
      user="explain the queue block. what does fifo + batch_size 1 buy me on sqs?",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 24 gcp queue options ignored
    F(24, provider="gcp", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#queue", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: thumbs
provider:
  name: gcp
  region: europe-west1
""" + GCP_OPTS + """functions:
  resize:
    handler: app.images.resize
    timeout: 120
    events:
      - queue:
          name: resize-requests
          batch_size: 25
          batch_window: 10
""",
          "app/__init__.py": "",
          "app/images.py": FUTURE + "def resize(event, ctx):\n    return {\"resized\": len(event.records)}\n"}),
      user="Ported this from an SQS setup. Explain what resize does on GCP and whether batch_size/batch_window still mean anything.",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 25 azure schedule with timezone
    F(25, provider="azure", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: payroll
provider:
  name: azure
  region: westeurope
functions:
  monthly-run:
    handler: app.payroll.run
    events:
      - schedule:
          cron: "0 6 1 * *"
          timezone: Europe/Amsterdam
          input: {mode: full}
""",
          "app/__init__.py": "",
          "app/payroll.py": FUTURE + "def run(event, ctx):\n    return {\"mode\": (event.data or {}).get(\"mode\")}\n"}),
      user="Please explain when monthly-run fires on Azure. Our payroll team expects 06:00 Amsterdam time on the first of each month.",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 26 onprem ssh + systemd deploy block
    F(26, provider="onprem", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: inventory
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8085
    advertise: https://inventory.internal.example
    deploy:
      method: ssh
      host: 192.0.2.21
      user: pskit
      pem: ${env:PSKIT_SSH_KEY, }
      path: /opt/pskit/inventory
      python: bundle
      install: systemd
      sudo: true
functions:
  stock:
    handler: app.stock.get
    events:
      - http: GET /stock/{sku}
""",
          "app/__init__.py": "",
          "app/stock.py": FUTURE + "def get(event, ctx):\n    return {\"sku\": event.http.path_params[\"sku\"], \"qty\": 0}\n"}),
      user="Before I deploy to prod, explain the deploy block: where does this run, how does Python get there, and what does sudo do?",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 27 onprem storage handler
    F(27, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#record", "docs/events.md#storage"],
      project=dict(base="examples/16-on-premises"),
      user="what is record.key and record.action in on_upload? where do they come from",
      steps=[
          S("read_file", path="app/handlers.py"),
          S("invoke_local", function="on-upload", type="storage", data={"bucket": "uploads", "key": "in/orders.csv", "size": 512}),
      ],
      final="TODO"),

    # ------------------------------------------------------------------ 28 aws http handler with errors
    F(28, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: coupons
provider:
  name: aws
  region: us-east-1
functions:
  redeem:
    handler: app.coupons.redeem
    events:
      - http: POST /coupons/{code}/redeem
""",
          "app/__init__.py": "",
          "app/coupons.py": FUTURE + """from py_serverless_kit import BadRequest, NotFound

KNOWN = {"WELCOME10": 10, "SPRING5": 5}


def redeem(event, ctx):
    code = event.http.path_params["code"].upper()
    if code not in KNOWN:
        raise NotFound(f"coupon {code} not found")
    body = event.http.json(default={})
    if not body.get("cart_id"):
        raise BadRequest("cart_id is required")
    return {"code": code, "percent": KNOWN[code], "cart_id": body["cart_id"]}
"""}),
      user="explain redeem please, what client get if coupon wrong?",
      steps=[
          S("read_file", path="app/coupons.py"),
          S("invoke_local", function="redeem", method="POST", path="/coupons/NOPE/redeem", data={"cart_id": "c1"}),
      ],
      final="TODO"),

    # ------------------------------------------------------------------ 29 gcp native workflow
    F(29, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#engines", "docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": """service: signup
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  create-account: {handler: app.signup.create}
  send-welcome: {handler: app.signup.welcome}
workflows:
  onboard:
    start_at: Create
    states:
      Create:
        type: task
        function: create-account
        retry:
          - {errors: [TimeoutError], max_attempts: 2, interval_seconds: 5}
        next: Welcome
      Welcome: {type: task, function: send-welcome, end: true}
""",
          "app/__init__.py": "",
          "app/signup.py": FUTURE + "def create(event, ctx):\n    return {\"account\": 1}\n\n\ndef welcome(event, ctx):\n    return {\"sent\": True}\n"}),
      user="explain onboard + which engine on gcp",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 30 onprem existing queue directory
    F(30, provider="onprem", stage="staging", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/events.md#queue", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: billing-sync
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8091
    services:
      queue: {use: directory, path: /var/pskit/queues}
functions:
  sync:
    handler: app.sync.run
    events:
      - queue: {name: invoices, existing: true, batch_size: 20, visibility_timeout: 300}
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + "def run(event, ctx):\n    return {\"synced\": len(event.records)}\n"}),
      user="On AWS this was an SQS event source mapping. What's the on-prem equivalent here, and what does existing: true do?",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 31 aws iam statements
    F(31, provider="aws", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: aws
  region: eu-west-1
  iam:
    statements:
      - actions: ["dynamodb:GetItem", "dynamodb:Query"]
        resources: ["arn:aws:dynamodb:*:*:table/catalog"]
functions:
  search:
    handler: app.catalog.search
    events:
      - http: GET /catalog
  importer:
    handler: app.catalog.importer
    iam:
      statements:
        - actions: ["s3:GetObject"]
          resources: ["arn:aws:s3:::catalog-imports/*"]
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + "def search(event, ctx):\n    return {\"items\": []}\n\n\ndef importer(event, ctx):\n    return {\"imported\": 0}\n"}),
      user="what are these iam things? is my function allowed to do anything on aws?",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 32 azure auth key
    F(32, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: partner-api
provider:
  name: azure
  region: northeurope
functions:
  orders:
    handler: app.partner.orders
    events:
      - http: {path: /partner/orders, method: GET, auth: key}
  status:
    handler: app.partner.status
    events:
      - http: GET /status
""",
          "app/__init__.py": "",
          "app/partner.py": FUTURE + "def orders(event, ctx):\n    return {\"orders\": []}\n\n\ndef status(event, ctx):\n    return {\"ok\": True}\n"}),
      user="what mean auth key here? partner need something to call?",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 33 onprem admin token + env file
    F(33, provider="onprem", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: notify
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8093
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"
    env_file: .env.onprem
    log_level: WARNING
    capture_output: false
functions:
  push:
    handler: app.push.send
    events:
      - queue: pushes
""",
          "app/__init__.py": "",
          "app/push.py": FUTURE + "def send(event, ctx):\n    return None\n"}),
      user="explain admin_token, env_file, log_level, capture_output",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 34 gcp topic handler with attributes
    F(34, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#record", "docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: audit
provider:
  name: gcp
  region: europe-west4
""" + GCP_OPTS + """functions:
  record-change:
    handler: app.audit.record
    events:
      - topic: entity-changes
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """

def record(event, ctx):
    saved = []
    for rec in event.records:
        change = rec.json()
        actor = rec.attributes.get("actor", "system")
        ctx.logger.info("change", extra={"entity": change.get("entity"), "actor": actor})
        saved.append({"entity": change.get("entity"), "actor": actor})
    return {"saved": saved}
"""}),
      user="Explain what record-change does with each Pub/Sub message, including where `actor` comes from, and run it once so I can see the output.",
      steps=[
          S("read_file", path="app/audit.py"),
          S("invoke_local", function="record-change", type="topic", data=[{"entity": "customer/42", "op": "update"}]),
      ],
      final="TODO"),

    # ------------------------------------------------------------------ 35 onprem topic filter semantics
    F(35, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#topic", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: shop-events
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8097}
functions:
  ship-mail:
    handler: app.events.ship_mail
    events:
      - topic: {name: orders, filter: {status: ["shipped"]}}
  all-orders-log:
    handler: app.events.log_all
    events:
      - topic: orders
""",
          "app/__init__.py": "",
          "app/events.py": FUTURE + "def ship_mail(event, ctx):\n    return None\n\n\ndef log_all(event, ctx):\n    return None\n"}),
      user="2 function on same topic orders, which one get which message?",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 36 aws stages override
    F(36, provider="aws", stage="prod", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: pricing
provider:
  name: aws
  region: us-east-1
  memory: 256
  environment:
    LOG_LEVEL: DEBUG
functions:
  quote:
    handler: app.pricing.quote
    events:
      - http: POST /quote
stages:
  prod:
    provider:
      memory: 1024
      environment:
        LOG_LEVEL: INFO
    functions:
      quote:
        concurrency: 50
""",
          "app/__init__.py": "",
          "app/pricing.py": FUTURE + "def quote(event, ctx):\n    return {\"price\": 0}\n"}),
      user="diff between dev and prod in this file?",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 37 azure queue name uppercase
    F(37, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: tickets
provider:
  name: azure
  region: westeurope
functions:
  intake:
    handler: app.tickets.intake
    events:
      - http: POST /tickets
  triage:
    handler: app.tickets.triage
    events:
      - queue: NewTickets
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + "def intake(event, ctx):\n    return {\"queued\": True}, 202\n\n\ndef triage(event, ctx):\n    return None\n"}),
      user="can you explain my project? and tell me if something is wrong for azure",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 38 onprem remaining time
    F(38, provider="onprem", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#context", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: reindex
provider:
  name: onprem
  region: local
  timeout: 60
  options: {host: 127.0.0.1, port: 8099}
functions:
  reindex:
    handler: app.reindex.run
    events:
      - schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/reindex.py": FUTURE + """

def run(event, ctx):
    done = 0
    for _ in range(100):
        if ctx.remaining_time_ms() < 5000:
            ctx.logger.warning("stopping early", extra={"done": done})
            break
        done += 1
    return {"done": done, "left_ms": ctx.remaining_time_ms() > 0}
"""}),
      user="In Lambda I used context.get_remaining_time_in_millis() for this. Explain this loop and whether the timeout behaves the same on-prem.",
      steps=[
          S("read_file", path="app/reindex.py"),
          S("invoke_local", function="reindex", type="schedule"),
      ],
      final="TODO"),

    # ------------------------------------------------------------------ 39 gcp multi trigger split
    F(39, provider="gcp", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=dict(files={
          "pskit.yml": """service: rates
provider:
  name: gcp
  region: europe-west1
""" + GCP_OPTS + """functions:
  refresh:
    handler: app.rates.refresh
    events:
      - http: POST /rates/refresh
      - schedule: "0 * * * *"
""",
          "app/__init__.py": "",
          "app/rates.py": FUTURE + "def refresh(event, ctx):\n    return {\"by\": event.type}\n"}),
      user="refresh has two triggers. is that ok on google? what happens",
      steps=[S("get_project"), S("validate")],
      final="TODO"),

    # ------------------------------------------------------------------ 40 onprem docker deploy
    F(40, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: scanner
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8100
    deploy:
      method: docker
      host: 192.0.2.30
      user: deploy
      image: pskit/scanner:staging
      restart: unless-stopped
functions:
  scan:
    handler: app.scan.run
    events:
      - http: POST /scan
""",
          "app/__init__.py": "",
          "app/scan.py": FUTURE + "def run(event, ctx):\n    return {\"clean\": True}\n"}),
      user="this deploy method docker, it build where? server need docker before?",
      steps=[S("get_project"), S("validate")],
      final="TODO"),
]

FINALS = {
    21: """It's one Python process on this machine that runs all your functions. Validate for onprem: valid, 8 functions and 1 workflow.

What each function does:
- **hello**: a web page at `GET /hello` on port 8080.
- **tick**: runs every hour by itself. It gets `{source: on-prem}` as `event.data`.
- **worker**: reads jobs from the `jobs` queue, 5 at a time. A job that fails 3 times moves to `jobs-dlq`.
- **audit-dlq**: reads `jobs-dlq`, so you see the jobs that failed.
- **on-upload**: runs when a `.csv` file is added to or deleted from `in/` in the `uploads` bucket.
- **on-order**: gets messages on the `orders` topic, but only `order.shipped` ones (the `filter`).
- **mark**: no trigger. The `ping` workflow calls it.

On premises, queues, buckets and topics are just folders. `services` says where: most are `builtin` (created at start), and buckets live in `.onprem/buckets` [docs/providers.md#onprem-on-premises]. The `providers:` block at the bottom only matters if you target aws, gcp or azure.""",

    22: """`worker` gets a batch of queue messages and checks each one:

- If the job JSON has `"fail": true`, it logs `job failed` and calls `result.fail(record)`.
- Otherwise it logs `job done`.

At the end it returns the `BatchResult`, which is the list of failed messages. Only those are tried again; the good ones count as done [docs/handlers.md#batchresult].

The local run shows it: job 1 logged `job done`, job 2 logged `job failed`, and the result was `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`. That is the second message (local ids start at `local-0`).

In pskit.yml the queue has `max_receive: 3` and `dead_letter: jobs-dlq`. So a job that keeps failing is tried 3 times, then moves to `jobs-dlq`, where `audit-dlq` logs it. On premises the file broker does this retry and dead-letter work [docs/providers.md#onprem-on-premises].""",

    23: """`post-entry` reads the SQS queue `entries` (validate for aws: valid):

- `fifo: true`: a FIFO queue (`.fifo` suffix, content-based dedup) [docs/events.md#queue]. Messages keep their order and duplicates are dropped.
- `batch_size: 1`: one message per invocation. A failure then only holds back that single entry, and you don't need `BatchResult` to retry part of a batch.
- `dead_letter: entries-dlq` + `max_receive: 3`: after 3 failed receives, SQS moves the message to `entries-dlq` (redrive policy).

The cost of `batch_size: 1` is more invocations and lower throughput. For a ledger where order matters more than speed, that's a reasonable trade.

`visibility_timeout` isn't set, so on AWS it's `max(30, 6 x timeout)` = 120 s with your 20 s timeout.""",

    24: """`resize` is triggered by `resize-requests`. On GCP a queue is a Pub/Sub topic with a push trigger, because there's no SQS-style pull trigger. Each message arrives in `event.records` [docs/events.md#queue]. Validate for gcp: valid.

`batch_size: 25` and `batch_window: 10` do nothing on GCP. The docs' option table marks both as ignored for Pub/Sub, and validate prints no warning for them, so they're easy to miss. A failure retries the whole delivery; there's no partial batch failure like SQS `batchItemFailures`.

What still applies: `timeout: 120`, well under GCP's 540 s limit for event-triggered functions [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

You can keep the two keys for when you deploy the same file to AWS, or delete them to avoid confusion.""",

    25: """`monthly-run` has cron `0 6 1 * *`: minute 0, hour 6, day 1 of every month. It gets `{mode: full}` as `event.data`.

But on Azure it will **not** run at 06:00 Amsterdam time. Validate for azure/staging is valid, with a warning:
`Linux Consumption timers run in UTC; timezone is ignored`

So it fires at 06:00 **UTC**: 07:00 in Amsterdam in winter and 08:00 in summer [docs/events.md#schedule].

A single cron can't follow daylight saving on Azure. `0 5 1 * *` gives 06:00 in winter but 07:00 in summer. If the exact local hour matters all year, the handler would have to check the Amsterdam time itself. Want me to change the cron?""",

    26: """Validate for onprem/prod: valid. Here's what the `deploy` block means [docs/providers.md#onprem-on-premises]:

**Where it runs**
- `method: ssh` to `pskit@192.0.2.21`. pskit packs a `release.tar.gz`, copies it over SSH and unpacks it in `/opt/pskit/inventory`.
- `pem` is read from `PSKIT_SSH_KEY`. When that's empty, the SSH agent or your default key is used.
- `host: 0.0.0.0` makes the service listen on all interfaces of the server, port 8085, so other machines can call it. `advertise` is the URL `pskit info` will show.

**How Python gets there**
- `python: bundle`: the server doesn't need Python. A portable CPython is downloaded at apply and copied along with the app. The first deploy needs network for that, unless it's already cached.

**What sudo does**
- `install: systemd` writes a systemd unit to `/etc/systemd/system`, and deploy runs `systemctl restart`. `sudo: true` is needed to write there and to create `/opt/pskit/...`. It is non-interactive (`sudo -n`), so the `pskit` user needs passwordless sudo.

The deploy fails if `/__pskit/health` doesn't answer, and the error shows `systemctl status` and `journalctl`. Prod deploys ask you to type a confirmation on the **Deploy** page.""",

    27: """They come from pskit, not from your code. When a file changes in a bucket, pskit gives the handler one `Record` per file in `event.records`, with these fields [docs/handlers.md#record]:

- `record.bucket`: the bucket name (`uploads`)
- `record.key`: the file's path inside the bucket (`in/orders.csv`)
- `record.size`: its size in bytes
- `record.action`: `"created"` or `"deleted"`

`on_upload` logs the key and action of each file and returns the list of keys. My local run with `in/orders.csv` logged `object` and returned `{"keys": ["in/orders.csv"]}`.

On premises a bucket is a folder (here under `.onprem/buckets`). Your trigger only fires for files under `in/` ending in `.csv`, for both created and deleted files [docs/events.md#storage].""",

    28: """`redeem` handles `POST /coupons/{code}/redeem`:

1. It reads `{code}` from the URL and makes it upper case.
2. If the code isn't in `KNOWN`, it raises `NotFound`.
3. It reads the JSON body. If `cart_id` is missing, it raises `BadRequest`.
4. Otherwise it returns the code, the percent and the cart id (status 200).

pskit turns those errors into JSON answers for you [docs/handlers.md#errors]. With a wrong coupon (`NOPE`) the local run returned:

```json
{"status": 404, "body": {"error": "coupon NOPE not found", "status": 404}}
```

A missing `cart_id` gives 400 the same way. You don't need to build the error response yourself.""",

    29: """`onboard` has two task states. Validate for gcp: valid, and it says `workflow onboard: native engine`, so it's deployed as Google Cloud Workflows [docs/workflows.md#engines].

1. **Create** calls `create-account`. A `TimeoutError` is retried: `max_attempts: 2`, 5 s apart. Any other error fails the run, since there's no `catch` [docs/workflows.md#retry-and-catch].
2. **Welcome** calls `send-welcome` with Create's output, then ends.

On GCP each task calls the function's URL with OIDC. Neither function needs its own trigger. Test it locally with `pskit workflow run onboard -i '{"email": "a@example.com"}'`.""",

    30: """The equivalent is pskit's file broker. A queue on premises is a directory with one JSON file per message, and the host process reads from it like an event source mapping [docs/events.md#queue].

Validate for onprem/staging: valid. Here:
- `services.queue: {use: directory, path: /var/pskit/queues}`: queues live in that folder.
- `existing: true`: pskit does **not** create the `invoices` queue directory. It waits until it appears, like pointing `existing` at an SQS queue you already have [docs/providers.md#onprem-on-premises].
- `batch_size: 20`: up to 20 messages per call.
- `visibility_timeout: 300`: a message being processed is hidden for 300 s before it can be delivered again.

`BatchResult` works as on SQS: only failed message ids come back. Something else must write into that directory, or you post messages to the host with `POST /__pskit/queues/invoices`.""",

    31: """They're the AWS permissions your functions get, on top of what pskit adds for their own triggers and logs [docs/configuration.md#provider]:

- `provider.iam.statements` apply to **every** function: `dynamodb:GetItem` and `dynamodb:Query` on the `catalog` table.
- `functions.importer.iam.statements` apply to `importer` only: `s3:GetObject` on files in the `catalog-imports` bucket.

So `search` can read the table, and `importer` can read the table and the import files. Neither can write to the table or delete anything. pskit puts these into each function's IAM role.

Validate for aws/prod: valid. If a function needs more later, you'll see an `AccessDenied` error in its logs; then add that action here.""",

    32: """`auth: key` means `GET /partner/orders` is protected by an **Azure function key**. Requests without the key are refused before your code runs [docs/events.md#http]. `GET /status` has no auth, so anyone can call it.

So yes, your partner needs the function key. After deploy you find it on the Function App in the Azure portal, then share it with the partner over a safe channel and treat it like a password.

Validate for azure: valid. On Azure, `key` is the only auth option besides `none`; `iam` and `jwt` aren't supported there [docs/providers.md#azure-azure-functions].""",

    33: """All four are host options for the on-prem process [docs/providers.md#onprem-on-premises]:

- `admin_token`: callers must send this value in the `x-pskit-token` header for the `/__pskit/*` routes (logs, queues, invoke...); health doesn't need it. Yours comes from `PSKIT_ADMIN_TOKEN` with an empty default, so when that variable is unset there is no token.
- `env_file: .env.onprem`: a file of `KEY=VALUE` secrets, copied next to the host and loaded at start. It's never written to Terraform state.
- `log_level: WARNING`: only `logging` records at WARNING and above are captured.
- `capture_output: false`: `print()` and stdout/stderr lines are not recorded.

Validate: valid, with one warning: `options.env_file .env.onprem does not exist yet; the host starts without it`. Create the file before you deploy if `push` needs secrets. Also, with WARNING and no output capture, `pskit logs` will show very little for `push`.""",

    34: """For each Pub/Sub message in `event.records`, `record` does this:

1. `rec.json()` parses the message body, for example `{"entity": "customer/42", "op": "update"}`.
2. `rec.attributes.get("actor", "system")` reads the **message attribute** `actor`. Attributes are key/value pairs the publisher sets next to the body; they're not part of the JSON [docs/handlers.md#record].
3. It logs `change` with the entity and actor, and collects both.
4. It returns `{"saved": [...]}`.

The local run sent one body without attributes, so `actor` fell back to `system`:

```json
{"saved": [{"entity": "customer/42", "actor": "system"}]}
```

For a real actor, the publisher must set `actor` as an attribute [docs/events.md#topic].""",

    35: """Both subscribe to the `orders` topic, and a topic is fan-out: every subscriber gets its own copy [docs/events.md#topic].

- `all-orders-log`: no filter, so it gets **every** message.
- `ship-mail`: `filter: {status: ["shipped"]}`, so it only gets messages where `status` is `shipped`.

On premises the filter is an exact match on the message attributes, then on fields of the JSON body [docs/providers.md#onprem-on-premises]. So `{"status": "shipped", "order": 7}` reaches both functions, and `{"status": "paid"}` only reaches `all-orders-log`.

Validate for onprem: valid. After deploy you can try it by publishing to `POST /__pskit/topics/orders`.""",

    36: """The `stages.prod` block is merged on top of the base config only for `-s prod` [docs/configuration.md#stages-per-stage-overrides]:

| | dev (base) | prod |
|---|---|---|
| `provider.memory` | 256 MB | 1024 MB |
| `LOG_LEVEL` | `DEBUG` | `INFO` |
| `quote` concurrency | not set | 50 |

Everything else is the same: region `us-east-1`, `POST /quote`, the handler. Validate for aws/prod: valid.""",

    37: """Your project is a small ticket system:
- `intake`: `POST /tickets`. It answers 202 with `{"queued": true}`.
- `triage`: reads tickets from the queue `NewTickets`.

There's one problem for Azure. Validate fails with:
`queue name 'NewTickets' must be 3-63 lowercase letters, digits, dashes`

Azure Storage Queue names can't have capital letters [docs/events.md#queue]. Rename it, for example to `new-tickets`, and use the same name wherever code sends to it. Want me to make the change?""",

    38: """The loop does up to 100 steps and stops early when less than 5 s are left before the timeout. `ctx.remaining_time_ms()` is pskit's version of `get_remaining_time_in_millis()`.

But there's a bug: `remaining_time_ms()` returns `None` when the time left isn't known [docs/handlers.md#context]. My local run showed it:
```
TypeError: '<' not supported between instances of 'NoneType' and 'int'
```
`pskit invoke` has no deadline, so `None < 5000` crashes. Guard it:

```python
left = ctx.remaining_time_ms()
if left is not None and left < 5000:
```

On premises the timeout is not like Lambda: the host does **not** kill a handler at `timeout: 60`, but `remaining_time_ms()` still counts down [docs/providers.md#onprem-on-premises]. So this check is the only thing that stops a long run. Want me to apply the guard and run it again?""",

    39: """Yes, it's fine. `refresh` runs for `POST /rates/refresh` and every hour (`0 * * * *`), with the same code. Your handler returns `event.type`, so you can tell which trigger called it (`http` or `schedule`).

On Google, pskit **splits** a function with several triggers into several Cloud Functions behind the scenes, one per trigger, all with the same handler [docs/events.md#gcp-multi-trigger-functions-are-split-automatically]. In pskit.yml and in your code it stays one function.

Validate for gcp/staging: valid.""",

    40: """With `method: docker` and a `host`, the image is built **on your machine**, not on the server [docs/providers.md#onprem-on-premises]:

1. pskit builds the image here (you need a Docker CLI and OpenSSH locally).
2. It saves the image to a tar and copies it over SSH to `deploy@192.0.2.30`.
3. On the server it runs `docker load` and `docker run` (`restart: unless-stopped`), then deletes the tar.
4. The deploy waits until the container answers `/__pskit/health`.

The server doesn't need Docker beforehand: if `docker` is missing it's installed first (apt, dnf, yum or apk), since `install_docker` defaults to true. For that, the `deploy` user needs passwordless `sudo`. There's no `pem`, so the SSH agent or your default key is used.

`host: 0.0.0.0` with port 8100 lets other machines call `POST /scan`. Validate for onprem/staging: valid.""",
}

for _c in CONVERSATIONS:
    _c["final"] = FINALS[int(_c["id"].split("-")[1])]
