"""Category F (explain a config or handler), batch 5. Hand-written; assembled by tools/assemble.py.

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


def onprem_yml(service, port, body, extra_opts=""):
    return f"""service: {service}
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: {port}
{extra_opts}{body}"""


CONVERSATIONS = [
    # ------------------------------------------------------------------ 81 submit_queue from a handler
    F(81, provider="onprem", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("orders", 8112, """functions:
  accept:
    handler: app.orders.accept
    events:
      - http: POST /orders
  pack:
    handler: app.orders.pack
    events:
      - queue: packing
"""),
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """from py_serverless_kit.runtime.onprem_host import submit_queue


def accept(event, ctx):
    order = event.http.json()
    submit_queue("packing", order)
    return {"accepted": order["id"]}, 202


def pack(event, ctx):
    for record in event.records:
        ctx.logger.info("packing", extra={"order": record.json().get("id")})
"""}),
      user="Explain how accept hands work to pack, and run accept once locally so I can see if that path works outside the host.",
      steps=[S("read_file", path="app/orders.py"),
             S("invoke_local", function="accept", method="POST", path="/orders", data={"id": 77})]),

    # ------------------------------------------------------------------ 82 onprem auth iam
    F(82, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("vault-api", 8113, """functions:
  read-config:
    handler: app.cfg.read
    events:
      - http: {path: /config, method: GET, auth: iam}
"""),
          "app/__init__.py": "",
          "app/cfg.py": FUTURE + "def read(event, ctx):\n    return {\"config\": {}}\n"}),
      user="On Lambda this route used AWS_IAM auth. What does my config do on-prem and is auth: iam honoured?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 83 onprem port out of range
    F(83, provider="onprem", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("kiosk", 80800, """functions:
  menu:
    handler: app.kiosk.menu
    events:
      - http: GET /menu
"""),
          "app/__init__.py": "",
          "app/kiosk.py": FUTURE + "def menu(event, ctx):\n    return {\"items\": [\"tea\", \"coffee\"]}\n"}),
      user="explain my kiosk config, studio shows red error and i dont understand",
      steps=[S("get_validation"), S("get_project")]),

    # ------------------------------------------------------------------ 84 onprem weekday cron with timezone
    F(84, provider="onprem", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("standup", 8114, """functions:
  remind:
    handler: app.standup.remind
    events:
      - schedule:
          cron: "45 9 * * 1-5"
          timezone: Asia/Kolkata
          enabled: ${env:STANDUP_REMINDER_ON, true}
          input: {channel: dev-team}
"""),
          "app/__init__.py": "",
          "app/standup.py": FUTURE + "def remind(event, ctx):\n    return {\"channel\": event.data[\"channel\"]}\n"}),
      user="when remind run exactly? and what is enabled with env there",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 85 onprem existing bucket folder
    F(85, provider="onprem", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/events.md#storage", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("scans", 8115, """functions:
  ocr:
    handler: app.scans.ocr
    events:
      - storage: {bucket: scanner-drop, existing: true, suffix: .tif}
""", extra_opts="""    services:
      storage: {use: directory, path: /srv/shares}
"""),
          "app/__init__.py": "",
          "app/scans.py": FUTURE + "def ocr(event, ctx):\n    return {\"files\": [r.key for r in event.records]}\n"}),
      user="ocr: which folder is watched, and will the 2000 tifs already there fire on first start?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 86 get_secret without value
    F(86, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#get_secret-secrets-on-every-provider"],
      project=dict(files={
          "pskit.yml": onprem_yml("crm-push", 8116, """functions:
  push:
    handler: app.crm.push
    events:
      - http: POST /push
"""),
          "app/__init__.py": "",
          "app/crm.py": FUTURE + """from py_serverless_kit import get_secret


def push(event, ctx):
    api_token = get_secret("crm_token")
    return {"pushed": True, "token_length": len(api_token)}
"""}),
      user="what is get_secret doing in push? where does it read from?",
      steps=[S("read_file", path="app/crm.py"),
             S("invoke_local", function="push", method="POST", path="/push", data={})]),

    # ------------------------------------------------------------------ 87 onprem choice + map workflow
    F(87, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#choice-rules", "docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": onprem_yml("batch-mail", 8117, """functions:
  load-list: {handler: app.mail.load_list}
  send-one: {handler: app.mail.send_one}
workflows:
  campaign:
    start_at: Load
    states:
      Load: {type: task, function: load-list, result_path: $.list, next: AnyoneLeft}
      AnyoneLeft:
        type: choice
        choices:
          - {variable: $.list.count, gt: 0, next: SendAll}
        default: Nothing
      SendAll:
        type: map
        items_path: $.list.recipients
        max_concurrency: 10
        iterator:
          start_at: Send
          states:
            Send: {type: task, function: send-one, end: true}
        end: true
      Nothing: {type: succeed}
"""),
          "app/__init__.py": "",
          "app/mail.py": FUTURE + "def load_list(event, ctx):\n    return {\"count\": 2, \"recipients\": [\"a@example.com\", \"b@example.com\"]}\n\n\ndef send_one(event, ctx):\n    return {\"sent\": event.data}\n"}),
      user="Walk me through the campaign workflow state by state, including what the map step receives.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 88 onprem env_file + resource secrets
    F(88, provider="onprem", stage="prod", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": onprem_yml("ingest", 8118, """resources:
  events-queue:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/ingest
      access_key_env: INGEST_AWS_KEY_ID
      secret_key_env: INGEST_AWS_SECRET
functions:
  ingest:
    handler: app.ingest.run
    events:
      - queue: {resource: events-queue, batch_size: 10}
"""),
          "app/__init__.py": "",
          "app/ingest.py": FUTURE + "def run(event, ctx):\n    return None\n"}),
      user="Our servers are on-prem but the queue is still SQS. Explain how ingest consumes it and where the AWS keys are read from.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 89 aws handler module:function form
    F(89, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: tools
provider:
  name: aws
  region: eu-west-2
functions:
  slugify:
    handler: "app.text:slugify"
    events:
      - http: POST /slugify
""",
          "app/__init__.py": "",
          "app/text.py": FUTURE + """import re


def slugify(event, ctx):
    title = event.http.json().get("title", "")
    return {"slug": re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")}
"""}),
      user="handler have colon app.text:slugify, is that ok? what function do",
      steps=[S("get_project"),
             S("invoke_local", function="slugify", method="POST", path="/slugify", data={"title": "Hello, Big World!"})]),

    # ------------------------------------------------------------------ 90 aws weekday cron conversion
    F(90, provider="aws", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: reports
provider:
  name: aws
  region: us-east-1
functions:
  weekday-report:
    handler: app.reports.weekday
    events:
      - schedule:
          cron: "0 7 * * 1-5"
          timezone: America/New_York
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + "def weekday(event, ctx):\n    return {\"ok\": True}\n"}),
      user="In CloudFormation I'd write cron(0 7 ? * MON-FRI *). Explain this schedule and what pskit generates for EventBridge.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 91 aws function options layers/vpc
    F(91, provider="aws", stage="staging", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/providers.md#aws-aws-lambda", "docs/configuration.md#escape-hatches"],
      project=dict(files={
          "pskit.yml": """service: reporting
provider:
  name: aws
  region: eu-west-1
functions:
  query:
    handler: app.rep.query
    timeout: 25
    options:
      layers: ["arn:aws:lambda:eu-west-1:123456789012:layer:pg:4"]
      vpc_config: {subnet_ids: [subnet-0a1b2c3d], security_group_ids: [sg-0a1b2c3d]}
      tracing_config: {mode: Active}
    events:
      - http: GET /report
""",
          "app/__init__.py": "",
          "app/rep.py": FUTURE + "def query(event, ctx):\n    return {\"rows\": []}\n"}),
      user="explain functions.query.options",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 92 aws worker with partial failure handler
    F(92, provider="aws", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#batchresult", "docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: payments
provider:
  name: aws
  region: us-east-1
functions:
  settle:
    handler: app.pay.settle
    events:
      - queue: {name: settlements, batch_size: 5}
""",
          "app/__init__.py": "",
          "app/pay.py": FUTURE + """from py_serverless_kit import BatchResult


def settle(event, ctx):
    result = BatchResult()
    for record in event.records:
        payment = record.json()
        if payment.get("amount", 0) <= 0:
            result.fail(record)
            continue
        ctx.logger.info("settled", extra={"id": payment["id"]})
    return result
"""}),
      user="explain settle. what happens to a payment with amount 0?",
      steps=[S("read_file", path="app/pay.py"),
             S("invoke_local", function="settle", type="queue", data=[{"id": "p1", "amount": 30}, {"id": "p2", "amount": 0}])]),

    # ------------------------------------------------------------------ 93 gcp binary response
    F(93, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: badges
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  badge:
    handler: app.badge.svg
    events:
      - http: GET /badge/{status}
""",
          "app/__init__.py": "",
          "app/badge.py": FUTURE + """from py_serverless_kit import Response

COLORS = {"passing": "#2e7d32", "failing": "#c62828"}


def svg(event, ctx):
    status = event.http.path_params["status"]
    color = COLORS.get(status, "#757575")
    body = f'<svg xmlns="http://www.w3.org/2000/svg" width="90" height="20"><rect width="90" height="20" fill="{color}"/></svg>'
    return Response.binary(body.encode("utf-8"), "image/svg+xml")
"""}),
      user="Explain the badge handler and what the response looks like on the wire, including how the binary body is carried.",
      steps=[S("read_file", path="app/badge.py"),
             S("invoke_local", function="badge", method="GET", path="/badge/passing")]),

    # ------------------------------------------------------------------ 94 gcp auth key
    F(94, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: webhooks
provider:
  name: gcp
  region: europe-west1
""" + GCP_OPTS + """functions:
  stripe-hook:
    handler: app.hooks.stripe
    events:
      - http: {path: /hooks/stripe, method: POST, auth: key}
""",
          "app/__init__.py": "",
          "app/hooks.py": FUTURE + "def stripe(event, ctx):\n    return None\n"}),
      user="explain stripe-hook. is auth key good for webhooks on gcp?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 95 gcp map workflow
    F(95, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#engines"],
      project=dict(files={
          "pskit.yml": """service: thumbs
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  list-images: {handler: app.t.list_images}
  make-thumb: {handler: app.t.make_thumb}
workflows:
  thumbnails:
    start_at: List
    states:
      List: {type: task, function: list-images, next: Each}
      Each:
        type: map
        items_path: $.images
        max_concurrency: 4
        iterator:
          start_at: Thumb
          states:
            Thumb: {type: task, function: make-thumb, end: true}
        result_path: $.thumbs
        end: true
""",
          "app/__init__.py": "",
          "app/t.py": FUTURE + "def list_images(event, ctx):\n    return {\"images\": [\"a.png\", \"b.png\"]}\n\n\ndef make_thumb(event, ctx):\n    return {\"thumb\": event.data}\n"}),
      user="explain thumbnails wf. how many thumbs at once",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 96 gcp own main.py at root
    F(96, provider="gcp", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: legacy-port
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  hello:
    handler: main.hello
    events:
      - http: GET /hello
""",
          "main.py": FUTURE + "def hello(event, ctx):\n    return {\"hello\": \"world\"}\n"}),
      user="I kept main.py at the root like a classic Cloud Function. Explain how pskit uses it here; anything to change?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 97 azure provider options
    F(97, provider="azure", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: claims-portal
provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
    resource_group: rg-claims-prod
    plan_sku: Y1
    app_insights: true
functions:
  submit:
    handler: app.claims.submit
    events:
      - http: POST /claims
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + "def submit(event, ctx):\n    return {\"id\": 1}, 201\n"}),
      user="Explain each provider.options key here and what Azure resources pskit will create versus reuse in prod.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 98 azure invoke() needs endpoint
    F(98, provider="azure", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: pricing
provider:
  name: azure
  region: westeurope
functions:
  quote:
    handler: app.price.quote
    events:
      - http: POST /quote
  tax:
    handler: app.price.tax
""",
          "app/__init__.py": "",
          "app/price.py": FUTURE + """from py_serverless_kit import invoke


def quote(event, ctx):
    net = event.http.json()["net"]
    tax = invoke("tax", {"net": net})
    return {"net": net, "tax": tax["tax"], "total": net + tax["tax"]}


def tax(event, ctx):
    return {"tax": round(event.data["net"] * 0.2, 2)}
"""}),
      user="quote call tax with invoke. explain, and it work same on azure?",
      steps=[S("read_file", path="app/price.py"),
             S("invoke_local", function="quote", method="POST", path="/quote", data={"net": 50})]),

    # ------------------------------------------------------------------ 99 azure greedy path + no /api
    F(99, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: assets
provider:
  name: azure
  region: northeurope
functions:
  serve:
    handler: app.assets.serve
    events:
      - http: GET /assets/{path+}
""",
          "app/__init__.py": "",
          "app/assets.py": FUTURE + "def serve(event, ctx):\n    return {\"asset\": event.http.path_params[\"path\"]}\n"}),
      user="Azure Functions usually put /api in front of routes. Explain what URL serve will have and how {path+} maps on Azure.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 100 azure 7 minute rate
    F(100, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: monitor
provider:
  name: azure
  region: westeurope
functions:
  check:
    handler: app.mon.check
    events:
      - schedule: 7 minutes
""",
          "app/__init__.py": "",
          "app/mon.py": FUTURE + "def check(event, ctx):\n    return {\"ok\": True}\n"}),
      user="my check runs every 7 minutes right? explain",
      steps=[S("get_project"), S("validate")]),
]

FINALS = {
    81: """`accept` takes the order from `POST /orders`, calls `submit_queue("packing", order)` and answers 202. `submit_queue` puts the order on the on-prem `packing` queue, and the host then runs `pack` for it, which logs each order id [docs/providers.md#onprem-on-premises].

Outside the host that path does **not** work. My local run failed with:
```
RuntimeError: not running inside an on-premises host (PSKIT_ONPREM_ROOT is unset)
```
and the request returned 500. `submit_queue`, `submit_topic`, `put_object` and `delete_object` only work in the deployed host process, where `PSKIT_ONPREM_ROOT` is set. `pskit invoke` runs the handler on its own, without a host.

So:
- After `pskit deploy`, `accept` → `packing` → `pack` works.
- To test `pack` locally, invoke it directly as a queue event with a sample order.
- This code is on-prem only; on a cloud you'd use that cloud's queue SDK instead.""",

    82: """The config has one route, `GET /config` on `read-config`, with `auth: iam`. On Lambda that meant API Gateway checked AWS signatures before your code ran.

On premises it is **not** honoured, and validate fails:
`auth `iam` is not enforced on-premises; use auth: none and check tokens in the handler`

The on-prem host has no cloud authorizer or IAM mapping [docs/providers.md#onprem-on-premises]. So:
1. Set `auth: none` on this route.
2. Check a token in the handler, for example the `authorization` header compared with a value from `get_secret()`, and raise `Unauthorized` when it's wrong.
3. Keep the host bound to `127.0.0.1` or behind your firewall.

If the same file also deploys to AWS, you can keep `auth: iam` there and use `none` only under `providers.onprem`. Want me to set that up?""",

    83: """Your config runs one function, `menu`, on `GET /menu`. It returns `{"items": ["tea", "coffee"]}`.

The red error is about the port:
`options.port must be an integer from 1 to 65535`

You wrote `port: 80800`. That's one zero too many; network ports only go up to 65535 [docs/providers.md#onprem-on-premises]. You probably meant `8080`. Each on-prem service needs its own port, so pick one nothing else uses. Shall I set it to 8080?""",

    84: """`remind` runs at **09:45, Monday to Friday** (`45 9 * * 1-5`), India time (`Asia/Kolkata`). It gets `{channel: dev-team}` as `event.data`.

`enabled: ${env:STANDUP_REMINDER_ON, true}` turns the schedule on or off from an environment variable. If `STANDUP_REMINDER_ON` isn't set, it's `true`. Set it to `false` before deploying and the reminder stays off, without editing the file.

Validate for onprem/prod: valid, with a warning:
`timezone Asia/Kolkata needs the IANA database; pskit deploy vendors tzdata. Until then this schedule is evaluated in UTC.`

That's about this machine only: `pskit deploy` bundles `tzdata`, so the deployed host knows Kolkata time [docs/providers.md#onprem-on-premises]. Before that, the time is treated as UTC [docs/events.md#schedule].""",

    85: """Validate for onprem: valid.

**Watched folder**: `services.storage: {use: directory, path: /srv/shares}` puts buckets under `/srv/shares`, so `scanner-drop` is a directory there. `existing: true` means pskit doesn't create it; the host waits until it appears [docs/providers.md#onprem-on-premises]. Only `.tif` files trigger `ocr` (`suffix`), and only created ones, the default.

**The 2000 existing files**: they will **not** fire. On the first start the host records the files already there and doesn't emit them [docs/events.md#storage]. Only files added after that run `ocr`. To process the backlog, move them out and back in after the first start, or run a one-off job over the folder.""",

    86: """`get_secret("crm_token")` reads a secret by name, so the token is not in your code or pskit.yml [docs/handlers.md#get_secret-secrets-on-every-provider]. The store is chosen by environment variables:

- default `env` store: the variable `PSKIT_SECRET_CRM_TOKEN`, then `CRM_TOKEN`;
- `PSKIT_SECRETS_DRIVER` set to `vault`: HashiCorp Vault / OpenBao;
- `aws`: AWS Secrets Manager.

Values are cached for 60 s.

My local run shows what happens when it's missing:
```
SecretNotFound: secret 'crm_token' not found: set PSKIT_SECRET_CRM_TOKEN (or CRM_TOKEN), or configure a store (PSKIT_SECRETS_URL / _TOKEN)
```
and `/push` answered 500. Set `PSKIT_SECRET_CRM_TOKEN` where the host runs (for example through `options.env_file`), or use `get_secret("crm_token", default="")` if the token is optional.""",

    87: """Validate for onprem/staging: valid, `workflow campaign: embedded engine`.

1. **Load** runs `load-list`. `result_path: $.list` puts its result next to the input, so the data becomes `{..., "list": {"count": 2, "recipients": [...]}}`.
2. **AnyoneLeft** (choice): if `$.list.count` is greater than 0, go to **SendAll**. Otherwise `default` goes to **Nothing** [docs/workflows.md#choice-rules]. A missing `count` evaluates to false, so that goes to Nothing too.
3. **SendAll** (map): `items_path: $.list.recipients` takes the list, and `Send` runs `send-one` once per entry, up to 10 at the same time (`max_concurrency`). Each run receives **one item**, here one email string, as `event.data` [docs/workflows.md#state-types]. The map's output is the list of results, and the run ends.
4. **Nothing** (succeed) ends the run without sending.

On premises the host runs it, so a long map isn't limited by a function timeout.""",

    88: """The queue stays in SQS; only the consumer runs on your servers. Validate for onprem/prod: valid [docs/resources.md#on-premises-drivers].

- `events-queue` is an external queue with `driver: sqs` and the `queue_url`.
- The host **polls** SQS for `ingest`, up to `batch_size: 10` messages each time, and runs the handler like any local queue event.
- SQS's own visibility timeout is the lease. A failed message becomes visible again at once; after `max_receive` failures it goes to a `dead_letter`, if you set one.

**The AWS keys**: `access_key_env: INGEST_AWS_KEY_ID` and `secret_key_env: INGEST_AWS_SECRET` are variable **names**. The host reads them from its own environment when it starts, so the keys never land in Terraform state or `pskit_host.json`. If one is missing, the host stops with an error naming it. Ship them with `provider.options.env_file` on the server.

Give that IAM user only the rights it needs on this one queue.""",

    89: """Yes, it's ok. `handler` can be `package.module.function` or `module:function`, so `app.text:slugify` means the function `slugify` in `app/text.py` [docs/configuration.md#functions].

What `slugify` does on `POST /slugify`:
1. Reads `title` from the JSON body (empty when it's missing).
2. Makes it lower case and replaces every run of other characters with one `-`.
3. Strips `-` from both ends.

My local run with `"Hello, Big World!"` returned `{"slug": "hello-big-world"}`.""",

    90: """`weekday-report` runs at 07:00 New York time, Monday to Friday. Validate for aws/prod: valid.

You write portable 5-field cron in pskit, and it converts it for EventBridge Scheduler [docs/events.md#schedule]:
- day-of-week becomes 1-7 (Sunday is 1), so `1-5` → `2-6`;
- `?` is inserted for day-of-month;
- the year field is added.

So pskit generates `cron(0 7 ? * 2-6 *)`, the same schedule as your `cron(0 7 ? * MON-FRI *)`. `timezone: America/New_York` is passed to EventBridge Scheduler, so it stays 07:00 local across daylight saving.""",

    91: """`functions.<fn>.options` is the escape hatch: pskit merges it as-is into that function's `aws_lambda_function` resource [docs/configuration.md#escape-hatches]. Validate for aws/staging: valid.

- `layers`: attaches the Lambda layer `pg` version 4, for example a Postgres driver.
- `vpc_config`: runs `query` inside your VPC, in `subnet-0a1b2c3d` with `sg-0a1b2c3d`, so it can reach a private database.
- `tracing_config: {mode: Active}`: turns on AWS X-Ray tracing.

Things to know [docs/providers.md#aws-aws-lambda]:
- In a VPC, the function needs a NAT or VPC endpoints to reach the internet or AWS APIs.
- `timeout: 25` fits under API Gateway's 30 s integration limit.
- These keys are AWS-only. If the file also targets another cloud, move them under `providers.aws`.""",

    92: """`settle` gets up to 5 payments from the `settlements` queue and checks each:

- `amount` is 0 or less (or missing): `result.fail(record)`.
- Otherwise: logs `settled` with the payment id.

It returns the `BatchResult`, so only failed messages go back to SQS for another try [docs/handlers.md#batchresult]. My local run with `p1` (30) and `p2` (0) logged `settled` once and returned `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`, which is `p2`.

So a payment with amount 0 is **retried**, and it fails the same way every time. There's no `dead_letter`, so SQS keeps redelivering it. Bad data like this is better sent to a DLQ: add `dead_letter: settlements-dlq` and `max_receive` to the queue [docs/handlers.md#record].""",

    93: """`badge` serves `GET /badge/{status}`:
1. Takes `{status}` from the path and picks a color: green for `passing`, red for `failing`, grey for anything else.
2. Builds a small SVG and returns `Response.binary(<bytes>, "image/svg+xml")`.

Locally, `GET /badge/passing` returned 200, `content-type: image/svg+xml`, and the SVG with the green fill.

On the wire: `Response.binary` sets the content type, and pskit **base64-encodes the body for gateways automatically** [docs/handlers.md#returning-a-response]. The client gets plain SVG bytes; you don't encode anything yourself.

Since SVG is text, a text response with that content type would work too. `binary` is the right choice for PNG or PDF.""",

    94: """`stripe-hook` receives Stripe's webhook calls on `POST /hooks/stripe` and returns nothing (204).

`auth: key` doesn't work on GCP. Validate fails with:
`http auth 'key' is not supported on GCP; use none or iam`

`key` is only on Azure in pskit [docs/events.md#http]. For a webhook, `iam` doesn't fit either, since Stripe can't send a Google identity token. The usual way:
1. `auth: none` (Stripe must reach it publicly).
2. In the handler, verify Stripe's signature header with your webhook signing secret, read with `get_secret()`, and refuse requests that don't match.

Want me to switch it to `auth: none`?""",

    95: """Validate for gcp: valid, `workflow thumbnails: native engine`, so it runs on Google Cloud Workflows [docs/workflows.md#engines].

1. **List** runs `list-images`, which returns `{"images": ["a.png", "b.png"]}`.
2. **Each** (map) takes `$.images` and runs `make-thumb` once per image. Each run gets one file name as `event.data` [docs/workflows.md#state-types].
3. `result_path: $.thumbs` stores the list of results next to the input, and the run ends.

**At once**: `max_concurrency: 4`, so at most 4 thumbnails are made at the same time; the rest wait for a free slot. On GCP each `make-thumb` call is an authenticated HTTP call to the function, so 4 also limits the load on it.

Try it locally with `pskit workflow run thumbnails`.""",

    96: """Validate for gcp: valid, but this layout will clash on GCP. `hello` uses `handler: main.hello`, the function `hello` in your root `main.py`, on `GET /hello`.

On GCP pskit **generates** the bundle's root `main.py` itself; it's the entry point that receives the request and calls your handler. The docs say: don't put your own `main.py` at the source root [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. Validate doesn't check this.

Fix: move the code into a package, for example `app/hello.py` with an empty `app/__init__.py`, and set `handler: app.hello.hello`. The handler code (`event, ctx`) stays the same. Want me to do that?""",

    97: """Validate for azure/prod: valid. The options [docs/providers.md#azure-azure-functions]:

- `subscription_id`: the Azure subscription to deploy into, from `ARM_SUBSCRIPTION_ID`. The default is all zeros, so set the real one before deploying.
- `resource_group: rg-claims-prod`: **reuse** this existing resource group instead of creating one.
- `plan_sku: Y1`: the Consumption plan (the default).
- `app_insights: true`: Application Insights for logs and metrics (the default).

**Created** by pskit, in that group: a storage account, the service plan, one Linux Function App for the whole service, and Application Insights with a Log Analytics workspace. `submit` is served at `POST /claims`, without an `/api` prefix.

**Reused**: only the resource group.""",

    98: """`quote` reads `net` from the body, calls `tax` with `invoke("tax", {"net": net})`, waits for the answer, and returns net, tax and total. `tax` is invoke-only (no trigger) and returns 20% of `net`.

Locally it works: `{"net": 50}` returned 200 with `tax: 10.0` and `total: 60.0`, because `pskit invoke` calls `tax` in the same process.

On Azure it does **not** work as written. There `invoke()` raises `InvokeError` unless `PSKIT_ENDPOINT_TAX` is set [docs/handlers.md#invoke-calling-another-function]. Azure gives invoke-only functions the route `POST /_pskit/invoke/tax`, which needs the function key. So after the first deploy, take `tax`'s URL from `pskit info` and set `PSKIT_ENDPOINT_TAX` to it.

For a simple 20% rule, a plain Python function shared by both handlers would be simpler. Should I change it that way?""",

    99: """Validate for azure: valid.

pskit sets Azure's `routePrefix` to empty, so there's **no `/api`**: `serve` is at `/assets/...` on the Function App's host, exactly as written [docs/providers.md#azure-azure-functions]. `pskit info` shows the real host name after deploy.

`{path+}` is pskit's greedy parameter and becomes Azure's `{*path}`. So `GET /assets/css/site.css` reaches `serve` with `event.http.path_params["path"] == "css/site.css"`. Your code is the same as on AWS.

All functions of the service share one Function App, so all routes live on that one host.""",

    100: """Almost, but not exactly. Validate for azure: valid. Azure timers use 6-field NCRONTAB, and pskit turns `7 minutes` into `0 */7 * * * *` [docs/events.md#schedule].

`*/7` counts within each hour, so `check` runs at minutes 0, 7, 14, 21, 28, 35, 42, 49 and 56. The next run is at :00, only **4 minutes** later, and every hour starts over.

If an even gap matters, use a rate that divides 60: `5 minutes`, `10 minutes` or `15 minutes`. Want me to change it?""",
}

for _c in CONVERSATIONS:
    _c["final"] = FINALS[int(_c["id"].split("-")[1])]
