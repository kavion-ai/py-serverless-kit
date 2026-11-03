"""Category F (explain a config or handler), batch 4. Hand-written; assembled by tools/assemble.py.

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
    # ------------------------------------------------------------------ 61 cluster config
    F(61, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    port: 8080
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"
    cluster:
      name: prod
      replicas: 3
      cpu: 0.5
      memory: 512
functions:
  catalog:
    handler: app.shop.catalog
    events:
      - http: GET /catalog
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + "def catalog(event, ctx):\n    return {\"items\": []}\n"}),
      user="Explain the cluster block: how many copies of catalog run, what they reserve, and anything that blocks a deploy right now.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 62 placement groups
    F(62, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/placement.md"],
      project=dict(files={
          "pskit.yml": """service: media
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    placement:
      default: api
      groups:
        api: {local: true}
        gpu: {server: gpu-box, functions: [thumbnail]}
functions:
  upload:
    handler: app.media.upload
    events:
      - http: POST /upload
  thumbnail:
    handler: app.media.thumbnail
""",
          "app/__init__.py": "",
          "app/media.py": FUTURE + "def upload(event, ctx):\n    return {\"ok\": True}\n\n\ndef thumbnail(event, ctx):\n    return {\"thumb\": True}\n"}),
      user="what is placement here? thumbnail run where?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 63 smtp handler
    F(63, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": """service: helpdesk
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8106}
resources:
  support-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.25, port: 25, domains: support.example.com, hostname: mail.support.example.com}
functions:
  new-ticket:
    handler: app.mail.new_ticket
    events:
      - smtp: {resource: support-mail}
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """

def new_ticket(event, ctx):
    mail = event.data
    ticket = {
        "from": mail["from"],
        "subject": mail["subject"] or "(no subject)",
        "attachments": len(mail.get("attachments", [])),
    }
    ctx.logger.info("ticket", extra=ticket)
    return ticket
"""}),
      user="how does new-ticket get the email? explain the code",
      steps=[S("read_file", path="app/mail.py"),
             S("invoke_local", function="new-ticket", type="smtp",
               data={"from": "ana@example.com", "to": ["help@support.example.com"], "subject": "Printer broken",
                     "text": "It jams.", "attachments": []})]),

    # ------------------------------------------------------------------ 64 minio storage resource
    F(64, provider="onprem", stage="staging", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#storage-drivers", "docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": """service: invoices
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8107, poll_seconds: 2}
resources:
  archive:
    type: storage
    external: true
    options:
      driver: minio
      endpoint: http://minio.internal.example:9000
      bucket: invoices
      access_key_env: MINIO_ACCESS_KEY
      secret_key_env: MINIO_SECRET_KEY
functions:
  on-invoice:
    handler: app.inv.on_invoice
    events:
      - storage: {resource: archive, suffix: .pdf}
""",
          "app/__init__.py": "",
          "app/inv.py": FUTURE + "def on_invoice(event, ctx):\n    return {\"keys\": [r.key for r in event.records]}\n"}),
      user="This replaces an S3 notification. How does on-invoice get triggered by MinIO here, and where do the keys come from?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 65 redis queue resource
    F(65, provider="onprem", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={
          "pskit.yml": """service: render
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8108}
resources:
  jobs:
    type: queue
    external: true
    options: {driver: redis, url: "redis://127.0.0.1:6379/0"}
functions:
  render:
    handler: app.render.run
    events:
      - queue: {resource: jobs, batch_size: 4, max_receive: 3, dead_letter: jobs-failed}
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + "def run(event, ctx):\n    return None\n"}),
      user="explain redis driver semantics for render. retries, dlq",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 66 invoke async handler on onprem
    F(66, provider="onprem", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: signup
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8109}
functions:
  register:
    handler: app.users.register
    events:
      - http: POST /register
  welcome-mail:
    handler: app.users.welcome_mail
""",
          "app/__init__.py": "",
          "app/users.py": FUTURE + """from py_serverless_kit import invoke


def register(event, ctx):
    user = event.http.json()
    invoke("welcome-mail", {"email": user["email"]}, asynchronous=True)
    return {"registered": user["email"]}, 201


def welcome_mail(event, ctx):
    ctx.logger.info("welcome", extra={"email": event.data["email"]})
    return {"sent": True}
"""}),
      user="register call welcome-mail with asynchronous=True. what is that mean, it wait or not?",
      steps=[S("read_file", path="app/users.py"),
             S("invoke_local", function="register", method="POST", path="/register", data={"email": "li@example.com"})]),

    # ------------------------------------------------------------------ 67 workflow host options
    F(67, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: exports
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8110
    workflow_workers: 2
    execution_retention: 50
functions:
  build-export: {handler: app.exp.build}
  upload-export: {handler: app.exp.upload}
workflows:
  export:
    start_at: Build
    states:
      Build: {type: task, function: build-export, next: Upload}
      Upload: {type: task, function: upload-export, end: true}
""",
          "app/__init__.py": "",
          "app/exp.py": FUTURE + "def build(event, ctx):\n    return {\"file\": \"export.csv\"}\n\n\ndef upload(event, ctx):\n    return {\"uploaded\": event.data[\"file\"]}\n"}),
      user="Explain workflow_workers and execution_retention for the export workflow. What happens if ten exports are started at once?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 68 onprem stages local vs ssh
    F(68, provider="onprem", stage="prod", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: timesheet
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8111}
functions:
  submit:
    handler: app.ts.submit
    events:
      - http: POST /timesheets
stages:
  prod:
    provider:
      options:
        host: 0.0.0.0
        deploy:
          method: ssh
          host: 192.0.2.40
          user: pskit
          path: /opt/pskit/timesheet
""",
          "app/__init__.py": "",
          "app/ts.py": FUTURE + "def submit(event, ctx):\n    return {\"saved\": True}, 201\n"}),
      user="where does my app run in dev and where in prod?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 69 migrated lambda project
    F(69, provider="aws", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-3-translate-step-functions", "docs/workflows.md#state-types"],
      project=dict(base="examples/13-migrate-from-aws-lambda/after"),
      user="This came from our SAM template plus an ASL file. Explain how each SAM piece maps to this pskit.yml.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 70 custom terraform example
    F(70, provider="aws", stage="staging", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#escape-hatches", "docs/configuration.md#state-remote-terraform-backend"],
      project=dict(base="examples/11-custom-terraform"),
      user="explain the tf: refs, state block and terraform.extra",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 71 aws handler returning datetime
    F(71, provider="aws", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: clock
provider:
  name: aws
  region: us-east-1
functions:
  now:
    handler: app.clock.now
    events:
      - http: GET /now
""",
          "app/__init__.py": "",
          "app/clock.py": FUTURE + """from datetime import datetime, timezone


def now(event, ctx):
    return {"utc": datetime.now(timezone.utc)}
"""}),
      user="can you explain now function? it looks simple but i'm not sure it works",
      steps=[S("read_file", path="app/clock.py"),
             S("invoke_local", function="now", method="GET", path="/now")]),

    # ------------------------------------------------------------------ 72 aws sns topic existing + filter
    F(72, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: fraud
provider:
  name: aws
  region: us-east-1
functions:
  screen:
    handler: app.fraud.screen
    events:
      - topic:
          name: payments-events
          existing: true
          filter: {kind: ["card"], country: ["US", "CA"]}
""",
          "app/__init__.py": "",
          "app/fraud.py": FUTURE + "def screen(event, ctx):\n    return {\"screened\": len(event.records)}\n"}),
      user="Explain the topic trigger on screen: which messages it receives and what existing: true means for the payments-events topic in prod.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 73 gcp service account + iam
    F(73, provider="gcp", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: ledger
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
    service_account: ledger-runtime@demo-project.iam.gserviceaccount.com
  iam:
    statements:
      - actions: ["datastore.entities.get"]
        resources: ["*"]
functions:
  balance:
    handler: app.ledger.balance
    events:
      - http: GET /balance/{account}
""",
          "app/__init__.py": "",
          "app/ledger.py": FUTURE + "def balance(event, ctx):\n    return {\"account\": event.http.path_params[\"account\"], \"balance\": 0}\n"}),
      user="I kept my IAM statements from the Lambda version. Explain what grants permissions to balance on GCP.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 74 gcp fifo + dlq warnings
    F(74, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  apply-order:
    handler: app.orders.apply
    events:
      - queue: {name: order-updates, fifo: true, dead_letter: order-updates-dlq, max_receive: 5}
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + "def apply(event, ctx):\n    return None\n"}),
      user="explain my queue settings for gcp, order is important for us",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 75 gcp query params handler
    F(75, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: search
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  find:
    handler: app.search.find
    events:
      - http: GET /search
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """

def find(event, ctx):
    q = event.http.query.get("q", "")
    limit = int(event.http.query.get("limit", "10"))
    return {"q": q, "limit": limit, "results": []}
"""}),
      user="what is event.http.query in find? what if no limit is sent?",
      steps=[S("read_file", path="app/search.py"),
             S("invoke_local", function="find", method="GET", path="/search")]),

    # ------------------------------------------------------------------ 76 gcp greedy path
    F(76, provider="gcp", stage="staging", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: files
provider:
  name: gcp
  region: europe-west2
""" + GCP_OPTS + """functions:
  download:
    handler: app.files.download
    events:
      - http: GET /files/{path+}
""",
          "app/__init__.py": "",
          "app/files.py": FUTURE + "def download(event, ctx):\n    return {\"path\": event.http.path_params[\"path\"]}\n"}),
      user="what does {path+} match",
      steps=[S("get_project"),
             S("invoke_local", function="download", method="GET", path="/files/reports/2026/q3.pdf")]),

    # ------------------------------------------------------------------ 77 queue example on azure
    F(77, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue", "docs/providers.md#azure-azure-functions"],
      project=dict(base="examples/04-queue-worker"),
      user="On SQS our redrive policy sends failures to jobs-dlq. Explain what this queue config does on Azure instead.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 78 azure auth iam
    F(78, provider="azure", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: hr
provider:
  name: azure
  region: westeurope
functions:
  salaries:
    handler: app.hr.salaries
    events:
      - http: {path: /salaries, method: GET, auth: iam}
""",
          "app/__init__.py": "",
          "app/hr.py": FUTURE + "def salaries(event, ctx):\n    return {\"rows\": []}\n"}),
      user="""ERROR: [functions.salaries] http auth 'iam' is not supported on Azure; use none or key (or put API Management / Easy Auth in front)
explain what my salaries config is trying to do and why""",
      steps=[S("get_validation"), S("get_project")]),

    # ------------------------------------------------------------------ 79 azure runtime 3.13
    F(79, provider="azure", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/providers.md"],
      project=dict(files={
          "pskit.yml": """service: newsletter
provider:
  name: azure
  region: francecentral
  runtime: python3.13
functions:
  weekly:
    handler: app.news.weekly
    events:
      - schedule: "0 8 * * 1"
""",
          "app/__init__.py": "",
          "app/news.py": FUTURE + "def weekly(event, ctx):\n    return {\"sent\": 0}\n"}),
      user="explain this project quick and is all ok?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 80 azure existing topic
    F(80, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: crm-listener
provider:
  name: azure
  region: westeurope
functions:
  on-contact:
    handler: app.crm.on_contact
    events:
      - topic: {name: crm-contacts, existing: true}
""",
          "app/__init__.py": "",
          "app/crm.py": FUTURE + "def on_contact(event, ctx):\n    return None\n"}),
      user="Our CRM team already publishes to a Service Bus topic called crm-contacts. Explain how on-contact attaches to it and whether the config is complete.",
      steps=[S("get_project"), S("validate")]),
]

FINALS = {
    61: """**The cluster block** [docs/cluster.md#set-up]
- `cluster.name: prod`: `catalog` runs on the scaling cluster `prod`, not on one machine.
- `replicas: 3`: three web replicas, plus 1 main replica, so 4 copies of the host serve `GET /catalog`.
- `cpu: 0.5` and `memory: 512`: each replica reserves half a CPU core and 512 MB. The defaults are 0.25 and 256.
- `port: 8080` is the port the cluster serves, and `admin_token` comes from `PSKIT_ADMIN_TOKEN` (empty when unset).

**What blocks a deploy now**: validate fails with
`Error: no cluster 'prod' (clusters: none yet). Create one: pskit cluster create NAME --master SERVER`

So there's no cluster called `prod` on this machine yet. Set it up first:
1. Save the servers: **Resources** > On-prem services > Servers.
2. Create the cluster: **Scaling cluster** > + New cluster, or `pskit cluster create prod --master <server>`.
3. Join more servers with `pskit cluster join prod <server>`.

Then validate again. The deploy builds the image here, so Docker must run on this machine.""",

    62: """`placement` splits the functions of one project over several machines. Each group runs on its own server, with only its own code and dependencies [docs/placement.md]:

- `api: {local: true}`: this machine. It's the `default` group, so `upload` (not listed anywhere) runs here, and so would any workflow.
- `gpu: {server: gpu-box, functions: [thumbnail]}`: `thumbnail` runs on the saved server `gpu-box`.

But validate fails right now:
`Error: no saved SSH server 'gpu-box' ... saved: none yet`

`gpu-box` must be a saved server on this machine first. Add it on **Resources** > On-prem services > Servers, or with `pskit resources onprem servers add gpu-box --ssh <user>@<host> --pem <key file>`, then validate again.

The **Deploy** page shows the same groups under "Where functions run".""",

    63: """The mail comes in through the `smtp` trigger. `support-mail` is an SMTP server resource for `support.example.com`. Every mail it receives is posted to the pskit host, which runs `new-ticket` with `event.type == "smtp"` and the mail in `event.data` [docs/smtp/README.md#what-the-handler-receives].

The code:
1. `mail = event.data`: a dict with `from`, `to`, `cc`, `subject`, `text`, `html`, `headers` and `attachments` (plus the same mail in Amazon SES shape).
2. It builds a ticket from the sender, the subject (or `(no subject)` when it's empty) and the number of attachments.
3. It logs `ticket` and returns it.

My local run with a sample mail from `ana@example.com` returned:
```json
{"from": "ana@example.com", "subject": "Printer broken", "attachments": 0}
```

For real mail, the SMTP server must exist (**Resources** > **+ SMTP server**) and your domain needs the A and MX records from its **DNS guide**. Note that a function may see the same mail twice, so make ticket creation safe to repeat.""",

    64: """Validate for onprem/staging: valid. Instead of S3 calling your function, the on-prem host **watches** the bucket [docs/resources.md#on-premises-drivers]:

- `archive` is an external storage resource with `driver: minio` at `http://minio.internal.example:9000`, bucket `invoices`.
- The host lists and compares the bucket every `poll_seconds` (2 s here). Each new object is an event for `on-invoice`, like a local file event.
- `storage: {resource: archive, suffix: .pdf}` only passes `.pdf` keys. With no `events`, only created objects count.

**The keys**: `access_key_env: MINIO_ACCESS_KEY` and `secret_key_env: MINIO_SECRET_KEY` are variable **names**. The host reads them from its own environment when it starts, so the keys never land in Terraform state or `pskit_host.json`. If one isn't set, the host stops with an error naming it [docs/resources.md#storage-drivers]. Set them where the host runs, for example with `options.env_file`.""",

    65: """`jobs` lives in Redis (`redis://127.0.0.1:6379/0`, key `jobs`) instead of a folder. Validate for onprem: valid [docs/resources.md#queue-drivers]:

- Each message is a JSON envelope in the Redis list `jobs`.
- The host claims up to `batch_size: 4` messages by moving them to `jobs:processing` and recording the claim time in `jobs:claims`.
- Success: the message is removed.
- Failure (an exception or a `BatchResult` fail): it goes back to `jobs` until it has failed `max_receive: 3` times, then moves to `jobs-failed`. That isn't a resource here, so it's a builtin (folder) queue.
- Crash safety: claims older than `visibility_timeout` are put back, so delivery is at-least-once. Make `render` safe to run twice.

Other producers can `LPUSH` plain strings onto `jobs`; they arrive as the record body.""",

    66: """`asynchronous=True` means "fire and forget": `register` asks for `welcome-mail` to run and doesn't use its result.

But on premises it **does wait**. On onprem and in local runs, `invoke()` calls the other handler in the same process, and with `asynchronous=True` it still finishes before `invoke()` returns [docs/handlers.md#invoke-calling-another-function]. Real fire-and-forget is an AWS feature.

The local run shows it: `welcome` (from `welcome-mail`) was logged **before** `register` answered 201 with `{"registered": "li@example.com"}`.

So a slow welcome mail makes `/register` slow on premises. If that matters, send the mail through a queue and give `welcome-mail` a queue trigger.""",

    67: """Validate for onprem/prod: valid, `workflow export: embedded engine`. The workflow runs **Build** (`build-export`) then **Upload** (`upload-export`), inside the host [docs/workflows.md#embedded-orchestrator].

- `workflow_workers: 2`: at most 2 workflow runs execute at once. Further starts wait for a free worker [docs/providers.md#onprem-on-premises].
- `execution_retention: 50`: the host keeps the last 50 finished runs under `<data_dir>/executions`, so you can still inspect them. Older ones are dropped.

**Ten exports at once**: each start gets its `execution_id` right away (202). Two run, eight wait and start as workers free up. All ten finish in the end, and you can list or cancel them with `GET /__pskit/executions`. With retention 50, you see about the last 50 runs; raise it if you need more history.""",

    68: """It depends on the stage. `stages.prod` is merged on top of the base config only for `-s prod` [docs/configuration.md#stages-per-stage-overrides]:

| | dev (base) | prod |
|---|---|---|
| where | this machine (default `method: local`) | the server `192.0.2.40` over SSH, user `pskit` |
| listens on | `127.0.0.1:8111` (only this machine) | `0.0.0.0:8111` (other machines can call it) |
| installed in | under `.pskit/` here | `/opt/pskit/timesheet` |

Validate for onprem/prod: valid, with one warning:
`the remote host must already have python3.12 on PATH. Set options.deploy.python: bundle to ship a portable interpreter, or method: docker.`

So make sure the server has Python 3.12, or add `python: bundle` under the prod `deploy` block. Want me to add it?""",

    69: """Validate for aws: valid, 5 functions and 1 workflow (`native engine`, so Step Functions on AWS). The SAM pieces map like this:

| SAM / ASL | pskit.yml |
|---|---|
| `CreateOrder`, `Events: Api POST /orders` | `create-order` with `- http: POST /orders` |
| `GetOrder`, `GET /orders/{id}` | `get-order` with `- http: GET /orders/{id}` |
| `EmailWorker` + `EmailQueue` + SQS `BatchSize: 10` | `email-worker` with `- queue: {name: orders-email, batch_size: 10}`. The queue is created for you; partial batch failures come from returning `BatchResult` |
| `Handler: lambda_function.x_handler` | `handler: app.orders.<fn>`, portable handlers |
| `OrderStateMachine` + `state_machine.asl.json` | `workflows.order-processing` |
| ASL `Resource: <Lambda ARN>` | `function: validate` / `charge`, the logical name |

The workflow [docs/workflows.md#state-types]: **Validate** (a `ValueError` goes to **Rejected**), **IsLarge** (a `total` over 500 waits 60 s in **Review**, otherwise straight on), **Charge** (any error retried 3 times, 2 s with backoff ×2). `validate` and `charge` have no events: they're invoke-only, called by the workflow.

The `providers:` block lets the same file deploy to gcp, azure or onprem later [docs/migrating-from-aws.md#step-3-translate-step-functions].""",

    70: """Validate for aws/staging: valid. Three escape hatches [docs/configuration.md#escape-hatches]:

**`terraform.extra`**: raw Terraform JSON merged into what pskit generates. Here it adds an `aws_dynamodb_table.orders` (`orders-ddb-staging-orders`, on-demand billing, PITR, encryption) and an output with its ARN.

**`${tf:...}` refs**: point pskit config at those resources. `ORDERS_TABLE: "${tf:aws_dynamodb_table.orders.name}"` becomes the table name at apply time. The IAM statement grants Get/Put/Query on `${tf:...arn}` and its indexes. Inside `extra` itself, plain `${aws_...}` Terraform syntax is used.

**`state`**: remote backend `s3`. State goes to `${TF_STATE_BUCKET}` (default `acme-terraform-state`), key `orders-ddb/staging/terraform.tfstate`, with `TF_LOCK_TABLE` for locking and encryption on [docs/configuration.md#state-remote-terraform-backend]. Without it, state is a local file under `.pskit/`.

Also: `required_version >= 1.5.0`, AWS provider pinned `~> 5.60`, and hooks that run the tests before deploy and a smoke test after. `providers.onprem` swaps the table name and turns the backend off (`backend: null`).""",

    71: """It works. `now` answers `GET /now` with the current UTC time:

```python
return {"utc": datetime.now(timezone.utc)}
```

A `datetime` isn't normally valid JSON, but pskit's serializer converts `datetime`/`date` to ISO 8601 for you [docs/handlers.md#returning-a-response]. The local run returned 200 with:
```json
{"utc": "2026-11-01T09:21:03.655859+00:00"}
```

Using `timezone.utc` is good: the string ends in `+00:00`, so clients know it's UTC.""",

    72: """`screen` subscribes to the SNS topic `payments-events` [docs/events.md#topic]. Validate for aws/prod: valid.

**Which messages**: the `filter` becomes an SNS filter policy on message attributes. A message is delivered only when:
- attribute `kind` is `card`, **and**
- attribute `country` is `US` or `CA`.

Inside one key the values are OR, and between keys it's AND. Messages without those attributes are not delivered to `screen` at all.

**`existing: true`**: the topic already exists, owned by someone else. pskit looks it up and only creates the subscription. It never creates, changes or deletes `payments-events`, so removing this service in prod leaves the topic and its other subscribers alone.""",

    73: """On GCP your `iam.statements` do nothing. Validate for gcp/prod is valid, with a warning:
`iam.statements are AWS-style and ignored on GCP; grant roles to options.service_account instead`

What grants permissions is `options.service_account` [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. `balance` runs as `ledger-runtime@demo-project.iam.gserviceaccount.com`, and it can do whatever roles that service account has in your project.

So for Datastore reads, grant that service account a role that includes `datastore.entities.get` (in IAM, outside pskit). You can delete the `iam` block, or keep it for when the same file deploys to AWS.""",

    74: """`apply-order` reads `order-updates` with `fifo`, `dead_letter: order-updates-dlq` and `max_receive: 5`. On GCP two of these don't work. Validate for gcp: valid, with two warnings:

- `queue.dead_letter is not applied on GCP (Eventarc manages the subscription)`
- `queue.fifo is not supported by Pub/Sub triggers and is ignored`

So on GCP **order is not guaranteed**, and failed messages don't move to a DLQ [docs/events.md#queue]. A queue on GCP is a Pub/Sub topic with a push trigger.

Since order matters for you:
1. Make `apply-order` order-safe: put a version or timestamp in each message and skip updates older than what you've stored.
2. Or run this function on aws (SQS FIFO) or onprem, where `fifo` and `dead_letter` are honoured.""",

    75: """`event.http.query` is the URL query string as a dict: for `/search?q=lamp&limit=5` it's `{"q": "lamp", "limit": "5"}` [docs/handlers.md#httprequest]. Values are always strings, which is why the code does `int(...)`.

With no `limit`, `.get("limit", "10")` uses `"10"`. My local run of `GET /search` without parameters returned:
```json
{"q": "", "limit": 10, "results": []}
```

One weak spot: `?limit=abc` would make `int()` raise `ValueError`, which becomes a 500. If you want a 400 instead, catch it and raise `BadRequest`.""",

    76: """`{path+}` is a **greedy** path parameter: it matches the rest of the path, slashes included. It's only allowed as the last segment [docs/events.md#http].

My local run of `GET /files/reports/2026/q3.pdf` returned:
```json
{"path": "reports/2026/q3.pdf"}
```

So `event.http.path_params["path"]` holds everything after `/files/`. A plain `{path}` would match only one segment, such as `/files/q3.pdf`.

Since the path comes from the client, check it before you use it to open files (no `..`).""",

    77: """On Azure the queue is a **Storage Queue**, and there's no redrive policy. Validate for azure: valid, with a warning:
`Storage Queues move poison messages to '<queue>-poison'; dead_letter is ignored`

What that means for this config [docs/events.md#queue]:
- `process-jobs` reads `jobs`. Messages that keep failing go to **`jobs-poison`**, Azure's own poison queue, not to `jobs-dlq`. `max_receive` is ignored too.
- `audit-dead-letters` listens to `jobs-dlq`, which nothing fills on Azure. To audit failures there, point it at `jobs-poison` under `providers.azure`.
- `batch_size` and `batch_window` are ignored, and a failed delivery is retried as a whole; `BatchResult` partial failures are an SQS feature.
- `enqueue` (`POST /jobs`) works the same.

All functions share one Function App on Azure, and the `providers.azure` block sets region `eastus` and the subscription [docs/providers.md#azure-azure-functions].""",

    78: """Your config has one function, `salaries`, on `GET /salaries`, with `auth: iam`. The idea: only callers with cloud credentials can read salaries, checked by the platform before the code runs.

The error is the one validate shows:
`http auth 'iam' is not supported on Azure; use none or key (or put API Management / Easy Auth in front)`

pskit's `iam` auth maps to AWS IAM or GCP's invoker rights; Azure Functions have no equivalent here [docs/events.md#http]. On Azure you can:
1. `auth: key`: callers must send the function key. Simple, but it's one shared secret.
2. `auth: none` plus Easy Auth or API Management in front, configured in Azure, for real user logins.

For salary data, option 2 is the safer choice. Which do you want?""",

    79: """Quick summary: one function, `weekly`, runs every Monday at 08:00 (cron `0 8 * * 1`) on Azure in `francecentral`. Azure timers run in UTC, so that's 08:00 UTC.

Not all ok: validate fails with
`Azure Functions does not support python3.13; use one of: python3.10, python3.11, python3.12, python3.9`

Fix: set `provider.runtime: python3.12`, or delete `runtime` and pskit picks the newest one Azure supports [docs/providers.md]. Your handler has nothing 3.13-specific. Shall I change it?""",

    80: """`on-contact` subscribes to the Service Bus topic `crm-contacts`, and `existing: true` says pskit should not create it, only add a subscription for this function [docs/events.md#topic].

The config isn't complete. Validate for azure fails:
`existing topics need options.servicebus_namespace_id and options.servicebus_connection (name of an app setting)`

An existing topic lives in the CRM team's namespace, so pskit needs:
- `provider.options.servicebus_namespace_id`: the namespace's resource id (`/subscriptions/.../namespaces/<name>`).
- `provider.options.servicebus_connection`: the **name** of an app setting that holds the namespace connection string. The connection string itself goes in that app setting, not in pskit.yml.

Send me the namespace id and the app setting name you want, and I'll add both.""",
}

for _c in CONVERSATIONS:
    _c["final"] = FINALS[int(_c["id"].split("-")[1])]
