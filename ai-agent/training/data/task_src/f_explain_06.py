"""Category F (explain a config or handler), batch 6. Hand-written; assembled by tools/assemble.py.

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
    # ------------------------------------------------------------------ 101 load balancer setting
    F(101, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="detailed_spec",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    advertise: http://192.0.2.50:8080
    balancer: {name: edge, path: shop, algorithm: sticky_round_robin}
functions:
  cart:
    handler: app.shop.cart
    events:
      - http: GET /cart
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + "def cart(event, ctx):\n    return {\"items\": []}\n"}),
      user="Explain the balancer line: which URL will customers use for the cart, what does the algorithm do, and is anything missing before I deploy?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 102 node runtime on prem
    F(102, provider="onprem", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(base="examples/21-nodejs-typescript"),
      user="this project is typescript. how on-prem run it if host is python?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 103 deploy.server unsaved
    F(103, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("tracker", 8120, """functions:
  ping:
    handler: app.tr.ping
    events:
      - http: GET /ping
""", extra_opts="""    deploy:
      server: app-2
      path: /opt/pskit/tracker
"""),
          "app/__init__.py": "",
          "app/tr.py": FUTURE + "def ping(event, ctx):\n    return {\"pong\": True}\n"}),
      user="""Error: no saved SSH server 'app-2'
explain what my deploy block says and why this""",
      steps=[S("get_validation"), S("get_project")]),

    # ------------------------------------------------------------------ 104 pskit_host queue driver
    F(104, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={
          "pskit.yml": onprem_yml("reports-worker", 8121, """resources:
  report-jobs:
    type: queue
    external: true
    options:
      driver: pskit_host
      endpoint: http://192.0.2.60:8080
      queue: reports
      token_env: CORE_ADMIN_TOKEN
functions:
  build:
    handler: app.rep.build
    events:
      - queue: {resource: report-jobs, batch_size: 2}
"""),
          "app/__init__.py": "",
          "app/rep.py": FUTURE + "def build(event, ctx):\n    return None\n"}),
      user="explain pskit_host driver on report-jobs",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 105 onprem Conflict error handler
    F(105, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": onprem_yml("rooms", 8122, """functions:
  book:
    handler: app.rooms.book
    events:
      - http: POST /rooms/{room}/book
"""),
          "app/__init__.py": "",
          "app/rooms.py": FUTURE + """from py_serverless_kit import Conflict, UnprocessableEntity

TAKEN = {"blue"}


def book(event, ctx):
    room = event.http.path_params["room"]
    slot = event.http.json(default={}).get("slot")
    if not slot:
        raise UnprocessableEntity("slot is required", details={"field": "slot"})
    if room in TAKEN:
        raise Conflict(f"room {room} is already booked")
    return {"room": room, "slot": slot}, 201
"""}),
      user="what answers can book give? i see Conflict and UnprocessableEntity",
      steps=[S("read_file", path="app/rooms.py"),
             S("invoke_local", function="book", method="POST", path="/rooms/blue/book", data={"slot": "10:00"})]),

    # ------------------------------------------------------------------ 106 onprem fifo queue
    F(106, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("stock", 8123, """functions:
  apply-move:
    handler: app.stock.apply
    events:
      - queue: {name: stock-moves, fifo: true, batch_size: 1, visibility_timeout: 60}
providers:
  gcp:
    region: europe-west1
    options: {project: "${env:GOOGLE_CLOUD_PROJECT, demo-project}"}
"""),
          "app/__init__.py": "",
          "app/stock.py": FUTURE + "def apply(event, ctx):\n    return None\n"}),
      user="We relied on SQS FIFO. Explain apply-move's queue on-prem, and tell me what changes if we later target GCP with this file.",
      steps=[S("get_project"), S("validate"), S("validate", provider="gcp")]),

    # ------------------------------------------------------------------ 107 package section
    F(107, provider="onprem", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": onprem_yml("ml-api", 8124, """package:
  source: .
  include: ["app/**", "models/*.json"]
  exclude: ["models/raw/**"]
  requirements: requirements.txt
  pip_args: ["--only-binary=:all:"]
  vendor: true
functions:
  predict:
    handler: app.ml.predict
    events:
      - http: POST /predict
"""),
          "app/__init__.py": "",
          "app/ml.py": FUTURE + "def predict(event, ctx):\n    return {\"score\": 0.5}\n",
          "models/weights.json": "{\"w\": [0.1, 0.2]}\n",
          "requirements.txt": "py-serverless-kit\n"}),
      user="package part confuse me. what go in the bundle? and why requirements has py-serverless-kit",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 108 onprem source_ip + headers
    F(108, provider="onprem", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": onprem_yml("audit-api", 8125, """functions:
  hit:
    handler: app.audit.hit
    events:
      - http: GET /hit
"""),
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """

def hit(event, ctx):
    req = event.http
    return {
        "ip": req.source_ip,
        "agent": req.headers.get("user-agent", "unknown"),
        "method": req.method,
        "path": req.path,
    }
"""}),
      user="Explain what hit records about each request and what the values look like in a local test versus behind the on-prem host.",
      steps=[S("read_file", path="app/audit.py"),
             S("invoke_local", function="hit", method="GET", path="/hit")]),

    # ------------------------------------------------------------------ 109 onprem mode auto explain
    F(109, provider="onprem", stage="dev", mode="auto", page="Network map", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("chat", 8126, """functions:
  post:
    handler: app.chat.post
    events:
      - http: POST /messages
  fanout:
    handler: app.chat.fanout
    events:
      - topic: messages
  archive:
    handler: app.chat.archive
    events:
      - queue: archive
"""),
          "app/__init__.py": "",
          "app/chat.py": FUTURE + "def post(event, ctx):\n    return {\"ok\": True}, 202\n\n\ndef fanout(event, ctx):\n    return None\n\n\ndef archive(event, ctx):\n    return None\n"}),
      user="i see three boxes on network map. explain what is connected to what",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 110 aws provider options
    F(110, provider="aws", stage="prod", mode="ask", page="Setup", persona="terse_expert",
      sources=["docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: aws
  region: eu-west-1
  options:
    profile: billing-deployer
    assume_role_arn: arn:aws:iam::123456789012:role/deployer
    allowed_account_ids: ["123456789012"]
    artifact_bucket: billing-deploy-artifacts
functions:
  invoice:
    handler: app.bill.invoice
    events:
      - http: POST /invoices
""",
          "app/__init__.py": "",
          "app/bill.py": FUTURE + "def invoice(event, ctx):\n    return {\"id\": 1}, 201\n"}),
      user="explain provider.options. what does each protect against?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 111 aws timeout 1200
    F(111, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/providers.md"],
      project=dict(files={
          "pskit.yml": """service: video
provider:
  name: aws
  region: us-east-1
functions:
  transcode:
    handler: app.video.transcode
    timeout: 1200
    memory: 3008
    events:
      - storage: {bucket: raw-videos-demo-1234, suffix: .mp4}
""",
          "app/__init__.py": "",
          "app/video.py": FUTURE + "def transcode(event, ctx):\n    return {\"files\": len(event.records)}\n"}),
      user="can you explain transcode settings? it should take 20 min per video",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 112 aws storage handler with size
    F(112, provider="aws", stage="staging", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: uploads
provider:
  name: aws
  region: eu-central-1
functions:
  check-size:
    handler: app.up.check_size
    events:
      - storage: {bucket: user-uploads-demo-1234, existing: true, prefix: avatars/}
""",
          "app/__init__.py": "",
          "app/up.py": FUTURE + """MAX_BYTES = 2 * 1024 * 1024


def check_size(event, ctx):
    too_big = [r.key for r in event.records if (r.size or 0) > MAX_BYTES]
    for key in too_big:
        ctx.logger.warning("avatar too big", extra={"key": key})
    return {"too_big": too_big}
"""}),
      user="what check-size do with big avatar? it delete it?",
      steps=[S("read_file", path="app/up.py"),
             S("invoke_local", function="check-size", type="storage",
               data={"bucket": "user-uploads-demo-1234", "key": "avatars/u7.png", "size": 5242880})]),

    # ------------------------------------------------------------------ 113 aws concurrency + enabled false
    F(113, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: notifications
provider:
  name: aws
  region: us-east-1
functions:
  send-sms:
    handler: app.notify.sms
    concurrency: 5
    events:
      - queue: sms-out
  send-push:
    handler: app.notify.push
    enabled: false
    events:
      - queue: push-out
""",
          "app/__init__.py": "",
          "app/notify.py": FUTURE + "def sms(event, ctx):\n    return None\n\n\ndef push(event, ctx):\n    return None\n"}),
      user="Explain concurrency: 5 on send-sms and enabled: false on send-push. What exists in AWS after a prod deploy?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 114 gcp delete-only storage
    F(114, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/events.md#storage", "docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: cleanup
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  drop-thumbs:
    handler: app.clean.drop_thumbs
    events:
      - storage: {bucket: photos-demo-1234, events: [deleted]}
""",
          "app/__init__.py": "",
          "app/clean.py": FUTURE + """

def drop_thumbs(event, ctx):
    gone = []
    for record in event.records:
        gone.append("thumbs/" + record.key)
        ctx.logger.info("drop thumb", extra={"photo": record.key, "action": record.action})
    return {"thumbs_to_delete": gone}
"""}),
      user="explain drop-thumbs, when it runs?",
      steps=[S("read_file", path="app/clean.py"),
             S("invoke_local", function="drop-thumbs", type="storage", data={"bucket": "photos-demo-1234", "key": "2026/cat.jpg"})]),

    # ------------------------------------------------------------------ 115 gcp memory schema error
    F(115, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: tiny
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  echo:
    handler: app.tiny.echo
    memory: 32
    events:
      - http: POST /echo
""",
          "app/__init__.py": "",
          "app/tiny.py": FUTURE + "def echo(event, ctx):\n    return event.http.json()\n"}),
      user="i put memory 32 to save money, explain why validate angry",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 116 gcp per-stage project
    F(116, provider="gcp", stage="prod", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#variables", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: catalog
custom:
  projects:
    dev: acme-catalog-dev
    prod: acme-catalog-prod
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${self:custom.projects.${opt:stage}}
functions:
  list:
    handler: app.cat.list_items
    events:
      - http: GET /items
""",
          "app/__init__.py": "",
          "app/cat.py": FUTURE + "def list_items(event, ctx):\n    return {\"items\": []}\n"}),
      user="does options.project resolve per stage? explain",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 117 gcp schedule input handler
    F(117, provider="gcp", stage="staging", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: digest
provider:
  name: gcp
  region: europe-west1
""" + GCP_OPTS + """functions:
  digest:
    handler: app.dig.send
    events:
      - schedule:
          cron: "0 18 * * 5"
          timezone: Europe/London
          input: {audience: all-staff, sections: [releases, incidents]}
""",
          "app/__init__.py": "",
          "app/dig.py": FUTURE + """

def send(event, ctx):
    cfg = event.data or {}
    ctx.logger.info("digest", extra={"audience": cfg.get("audience")})
    return {"audience": cfg.get("audience"), "sections": cfg.get("sections", [])}
"""}),
      user="With EventBridge I passed a constant Input JSON. Explain how digest gets its input here and when it fires.",
      steps=[S("read_file", path="app/dig.py"),
             S("invoke_local", function="digest", type="schedule")]),

    # ------------------------------------------------------------------ 118 azure existing queue
    F(118, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#queue", "docs/providers.md#azure-azure-functions"],
      project=dict(files={
          "pskit.yml": """service: erp-bridge
provider:
  name: azure
  region: westeurope
  options:
    storage_connection: ERP_STORAGE
functions:
  import-order:
    handler: app.erp.import_order
    events:
      - queue: {name: erp-orders, existing: true}
""",
          "app/__init__.py": "",
          "app/erp.py": FUTURE + "def import_order(event, ctx):\n    return None\n"}),
      user="The ERP team owns a Storage Queue named erp-orders in their own storage account. Explain how this config attaches to it and what ERP_STORAGE must contain.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 119 azure topic attributes handler
    F(119, provider="azure", stage="staging", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#record", "docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: alerts
provider:
  name: azure
  region: westeurope
functions:
  page-oncall:
    handler: app.alerts.page
    events:
      - topic: incidents
""",
          "app/__init__.py": "",
          "app/alerts.py": FUTURE + """

def page(event, ctx):
    paged = []
    for record in event.records:
        incident = record.json()
        if incident.get("severity") in ("critical", "high"):
            paged.append(incident["id"])
            ctx.logger.warning("paging on-call", extra={"incident": incident["id"]})
    return {"paged": paged}
"""}),
      user="explain page-oncall pls, who get paged",
      steps=[S("read_file", path="app/alerts.py"),
             S("invoke_local", function="page-oncall", type="topic",
               data=[{"id": "INC-1", "severity": "low"}, {"id": "INC-2", "severity": "critical"}])]),

    # ------------------------------------------------------------------ 120 azure cors preflight
    F(120, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: forms
provider:
  name: azure
  region: westeurope
functions:
  submit:
    handler: app.forms.submit
    events:
      - http:
          path: /forms
          method: POST
          cors:
            origins: ["https://www.example.com"]
            methods: [POST]
            headers: [Content-Type]
            max_age: 600
""",
          "app/__init__.py": "",
          "app/forms.py": FUTURE + "def submit(event, ctx):\n    return {\"received\": True}, 201\n"}),
      user="what does the cors part do? my website is www.example.com",
      steps=[S("get_project"),
             S("invoke_local", function="submit", method="OPTIONS", path="/forms")]),
]

FINALS = {
    101: """`balancer: {name: edge, path: shop, algorithm: sticky_round_robin}` puts this project on the load balancer `edge` [docs/load-balancers.md#create-one-and-put-projects-on-it]:

- **URL**: customers call `http://<edge's server>/shop/cart`. The balancer strips the `/shop` prefix, so `cart` still sees `GET /cart`, and it sends `X-Forwarded-Prefix: /shop`. `/shop` redirects to `/shop/`.
- **Where requests go**: to `advertise` (`http://192.0.2.50:8080`). With `host: 0.0.0.0` the service listens on all interfaces, so the balancer can reach it.
- **`sticky_round_robin`**: requests are spread over the servers in turn, and one client keeps going to the same server.

Each `pskit deploy` updates the route and `pskit remove` drops it.

Validate for onprem/prod: valid. It doesn't check that `edge` exists, though. If it isn't on **Load balancers** yet, create it first: save its server, then run `pskit lb create edge --server <server>`.""",

    102: """Validate for onprem: valid, 8 functions and 1 workflow (`order-pipeline`, embedded engine).

On premises the **host stays a Python process**. It handles HTTP, schedules, queues, storage, topics, workflow runs and logs exactly as for Python [docs/providers.md#onprem-on-premises]. Only your TypeScript handlers run in Node.js:

- Each function gets its own long-lived `node` worker process (`pskit_runtime/worker.js`), with that function's environment. It starts on the first call.
- `console` and `ctx.logger` output shows up in `pskit logs` and the dashboard.
- The workflow is still run by the host; only its task functions run in Node.js.

`node` must be on PATH for a local deploy (pskit stops with an installer link when it's missing). For a server, `deploy.node: bundle` ships Node.js for you. The `providers.onprem` block sets port 8082.""",

    103: """Your `deploy` block says: deploy `tracker` to the **saved server `app-2`**, into `/opt/pskit/tracker`. The SSH login, user and port come from that saved server, not from pskit.yml [docs/providers.md#onprem-on-premises].

Validate fails because there is no saved server called `app-2` on this machine:
`no saved SSH server 'app-2' ... saved: none yet`

Saved servers belong to this studio / machine, not to the project. So the file can name `app-2`, but someone has to save it here first. Two ways:
1. Save it: **Resources** > On-prem services > Servers, or `pskit resources onprem servers add app-2 --ssh <user>@<host> --pem <key file>`.
2. Or point `deploy.server` at a server that's already saved (**Overview** > Deploy to).

Then validate again.""",

    104: """`pskit_host` makes `report-jobs` a queue that lives on **another pskit host** [docs/resources.md#queue-drivers]:

- `endpoint: http://192.0.2.60:8080`: the other host.
- `queue: reports`: the queue name there.
- `token_env: CORE_ADMIN_TOKEN`: that host's `admin_token`, read from the variable `CORE_ADMIN_TOKEN` on this host when it starts. The token is not in pskit.yml or in state.

`build` leases up to 2 messages at a time from that host. The other host hides a leased message for `visibility_timeout` and counts failures. Leases that are never settled expire there, so a crash here doesn't lose messages; delivery is at-least-once.

Validate for onprem/prod: valid. This host must reach port 8080 on `192.0.2.60`.""",

    105: """`book` handles `POST /rooms/{room}/book` and can answer three ways [docs/handlers.md#errors]:

| Case | Raised | Answer |
|---|---|---|
| no `slot` in the body | `UnprocessableEntity` | 422 `{"error": "slot is required", "status": 422, "details": {"field": "slot"}}` |
| room is in `TAKEN` | `Conflict` | 409 `{"error": "room ... is already booked", "status": 409}` |
| otherwise | nothing | 201 with room and slot |

My local run booked `blue` at 10:00. `blue` is in `TAKEN`, so it returned **409** with `room blue is already booked`.

Any other exception would be a 500 with a generic message, and the traceback goes to the logs.""",

    106: """On premises, `apply-move`'s queue behaves like a FIFO queue. The file broker honours `fifo`, `batch_size`, `visibility_timeout`, `dead_letter` and `max_receive` [docs/providers.md#onprem-on-premises]:

- `fifo: true`: messages are handed out in order.
- `batch_size: 1`: one stock move per call, so one failure doesn't hold back others.
- `visibility_timeout: 60`: a message being processed is hidden for 60 s before it can come back.

Validate for onprem: valid.

On **GCP** it changes. Validate for gcp is valid, but warns:
`queue.fifo is not supported by Pub/Sub triggers and is ignored`

A queue there is a Pub/Sub topic with a push trigger, so order isn't guaranteed. `batch_size` is ignored too [docs/events.md#queue]. If you target GCP, make `apply` order-safe, for example by giving each move a sequence number and skipping old ones.""",

    107: """The `package` section decides what goes into the bundle [docs/configuration.md#package]:

- `source: .`: start from the project folder.
- `include: ["app/**", "models/*.json"]`: only your code and the JSON files directly in `models/`, so `models/weights.json` is in.
- `exclude: ["models/raw/**"]`: never the raw models. This is added to the default excludes (`.git`, `.venv`, `tests/**`, `.env`, `pskit*.yml` and more).
- `requirements`, `pip_args: ["--only-binary=:all:"]`: pip installs from `requirements.txt` and only accepts wheels, never builds from source.
- `vendor: true`: always pip-install the dependencies into the bundle instead of shipping `requirements.txt`.

**`py-serverless-kit` in requirements**: it's fine, pskit drops that line. The runtime is copied into every bundle, so it's never installed twice.

Validate for onprem: valid.""",

    108: """`hit` returns four things about the request [docs/handlers.md#httprequest]:
- `ip`: `event.http.source_ip`, the client address;
- `agent`: the `user-agent` header, or `unknown`;
- `method` and `path`.

Locally, `GET /hit` returned `{"ip": "127.0.0.1", "agent": "unknown", "method": "GET", "path": "/hit"}`. The local test sends no headers, so `agent` falls back to `unknown`, and the address is this machine.

Behind the on-prem host you'd see the caller's address and their real `User-Agent`. Two things to watch:
- If a load balancer or proxy is in front, `source_ip` is the proxy's address. The client's address then comes in a forwarding header.
- With `host: 127.0.0.1` only this machine can call it.""",

    109: """The network map shows your three functions and how messages flow between them. Validate for onprem: valid.

- **post**: the entry point, `POST /messages` on port 8126. It answers 202.
- **fanout**: subscribed to the topic `messages`. Every message published there reaches it.
- **archive**: reads the queue `archive`.

But pskit.yml doesn't connect them: nothing here publishes to `messages` or sends to `archive`. If `post` should feed the others, the handler has to publish or send in code, for example with the on-prem `submit_topic` / `submit_queue` [docs/providers.md#onprem-on-premises]. Right now `post` only returns `{"ok": true}`.

On premises the topic and the queue are directories the host creates at start.""",

    110: """Validate for aws/prod: valid. The options [docs/providers.md#aws-aws-lambda]:

- `profile: billing-deployer`: use this AWS CLI profile. Protects against deploying with whatever default credentials happen to be in your shell.
- `assume_role_arn`: Terraform assumes the `deployer` role. Your own user doesn't need wide rights; the role has them.
- `allowed_account_ids: ["123456789012"]`: the deploy refuses to run in any other account. Protects against a wrong profile hitting the wrong account, which matters for prod.
- `artifact_bucket: billing-deploy-artifacts`: upload the code zip to this existing bucket instead of a bucket pskit creates. The deploying identity then only needs `PutObject` on it.""",

    111: """`transcode` runs when an `.mp4` lands in `raw-videos-demo-1234`, with 3008 MB memory and `timeout: 1200` (20 minutes).

Validate for aws fails:
`timeout 1200s exceeds AWS Lambda max 900s`

Lambda can't run longer than 15 minutes [docs/providers.md]. Options:
1. Make each run shorter: split the video and transcode the parts, for example with a workflow `map` state, each part under 900 s.
2. Run `transcode` on premises, where the timeout goes up to 3600 s (GCP event-triggered functions stop at 540 s, so GCP does not help here).
3. Use a dedicated AWS service for video transcoding outside pskit, and keep the function as the trigger.

Which way fits?""",

    112: """No, it doesn't delete anything. `check-size` runs for new files under `avatars/` in the existing bucket `user-uploads-demo-1234`:

1. For each file, it compares `record.size` (bytes) with `MAX_BYTES`, 2 MB. `(r.size or 0)` handles a missing size [docs/handlers.md#record].
2. Each file that is too big gets a `WARNING` log, `avatar too big`.
3. It returns the list of too-big keys.

My local run with a 5 MB `avatars/u7.png` logged the warning and returned `{"too_big": ["avatars/u7.png"]}`. The file stays in the bucket.

To really remove it, the handler would need to delete the object with the S3 SDK, and the function would need `s3:DeleteObject` on that bucket in `iam.statements`.""",

    113: """Validate for aws/prod: valid, **1 function**, with a warning:
`disabled (enabled: false): not deployed`

- **`send-sms`, `concurrency: 5`**: reserved concurrency. At most 5 copies of the Lambda run at once, so SMS sending is throttled and can't eat the account's whole limit [docs/configuration.md#functions]. Messages wait in `sms-out` until a copy is free.
- **`send-push`, `enabled: false`**: it isn't deployed at all.

After a prod deploy, AWS has the `send-sms` Lambda, its `sms-out` SQS queue and event source mapping, a role and a log group. Nothing for `send-push`. Set `enabled: true` again and deploy to bring it back.""",

    114: """`drop-thumbs` runs when a photo is **deleted** from `photos-demo-1234` (`events: [deleted]`), not on upload [docs/events.md#storage].

For each deleted file it:
1. builds the thumbnail path `thumbs/<key>`,
2. logs `drop thumb` with the photo key and `record.action` [docs/handlers.md#record],
3. returns the list of thumbnails to delete.

My local run with `2026/cat.jpg` returned `{"thumbs_to_delete": ["thumbs/2026/cat.jpg"]}`. It only returns the list; nothing is actually deleted yet. On GCP that needs the Cloud Storage SDK, and the runtime service account needs delete rights on the bucket.""",

    115: """`echo` returns the JSON body you POST to `/echo`. The problem is `memory: 32`. Validate fails with:
`functions.echo.memory: Input should be greater than or equal to 64`

pskit's lowest memory is 64 MB, on every provider [docs/configuration.md#provider]. The default is 256. For a tiny echo function, 128 is a sensible low value. Shall I set it?""",

    116: """No. Nested variables don't resolve here. Validate fails with:
`Error: unresolved variables: self:custom.projects.${opt:stage`

pskit read `${self:custom.projects.${opt:stage` as one variable: it doesn't put `${opt:stage}` in first and then look up the result [docs/configuration.md#variables].

Use a `stages:` block instead [docs/configuration.md#stages-per-stage-overrides]:

```yaml
provider:
  options:
    project: acme-catalog-dev
stages:
  prod:
    provider:
      options:
        project: acme-catalog-prod
```

The rest is fine: one function, `list`, on `GET /items`. Want me to make that change?""",

    117: """`digest` fires at **18:00 every Friday**, London time (`0 18 * * 5`, `timezone: Europe/London`). GCP's Cloud Scheduler honours the timezone, so daylight saving is handled [docs/events.md#schedule].

The constant input works like EventBridge's `Input`: `input:` becomes `event.data`. The handler reads `audience` and `sections` from it, logs `digest` and returns both.

The local schedule run used the configured input and returned:
```json
{"audience": "all-staff", "sections": ["releases", "incidents"]}
```

`event.data or {}` keeps it safe if a run arrives without input.""",

    118: """Validate for azure: valid.

- `queue: {name: erp-orders, existing: true}`: pskit doesn't create `erp-orders`. It attaches the trigger to the queue that already exists [docs/events.md#queue].
- Normally a queue lives in the Function App's own storage account. `options.storage_connection: ERP_STORAGE` says to use **another account**: `ERP_STORAGE` is the name of an app setting [docs/providers.md#azure-azure-functions].

**What `ERP_STORAGE` must contain**: the connection string of the ERP team's storage account. It's a secret, so don't put it in pskit.yml. Set it as an app setting on the Function App, or give it through `${env:...}` when you deploy.

Ask the ERP team for read/delete access on that queue. Note that failed messages go to `erp-orders-poison` in their account.""",

    119: """`page-oncall` gets each message published to the topic `incidents` (a Service Bus topic on Azure). For each one it parses the JSON, and if `severity` is `critical` or `high` it logs `paging on-call` and adds the id to `paged`.

So only critical and high incidents page someone; `low`, `medium` or a missing severity are ignored [docs/handlers.md#record]. My local run with `INC-1` (low) and `INC-2` (critical) logged one warning and returned `{"paged": ["INC-2"]}`.

It only logs right now; the actual paging (SMS, chat...) still has to be added. The check is in code, which is right for Azure, where a topic `filter` isn't applied [docs/events.md#topic].""",

    120: """The `cors` part lets your website call `POST /forms` from the browser [docs/events.md#http]:

- `origins: ["https://www.example.com"]`: only your site may call it. Other sites are blocked by the browser.
- `methods: [POST]` and `headers: [Content-Type]`: what the browser may send.
- `max_age: 600`: the browser remembers the answer for 10 minutes and doesn't ask again each time.

Before the real POST, the browser sends an `OPTIONS` "preflight". pskit's runtime answers it with 204. My local `OPTIONS /forms` returned 204. It showed no `Access-Control-*` headers because the test sends no `Origin` header. A browser on `https://www.example.com` sends one, and then the runtime adds the allow headers.

Make sure the origin matches exactly: `https://example.com` without `www` would be refused.""",
}

for _c in CONVERSATIONS:
    _c["final"] = FINALS[int(_c["id"].split("-")[1])]
