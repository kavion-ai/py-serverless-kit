"""Category F (explain a config or handler), batch 8. Hand-written; assembled by tools/assemble.py.

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
    # ------------------------------------------------------------------ 141 hello handler query
    F(141, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(base="examples/16-on-premises"),
      user="explain the hello function and show me what it answers",
      steps=[S("read_file", path="app/handlers.py"),
             S("invoke_local", function="hello", method="GET", path="/hello")]),

    # ------------------------------------------------------------------ 142 ping workflow start on entry
    F(142, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#embedded-orchestrator"],
      project=dict(base="examples/16-on-premises"),
      user="Explain the ping workflow and the mark function behind it. Can mark be called without starting a workflow run?",
      steps=[S("get_project"),
             S("search_docs", query="on premises workflow first state task starts when function runs",
               docs=[D("docs/workflows.md", "embedded-orchestrator",
                       start="- On premises, a workflow whose first state",
                       end="Other clouds don't do this: start the workflow itself there.")]),
             S("invoke_local", function="mark", type="invoke", data={"order": 5})]),

    # ------------------------------------------------------------------ 143 0.0.0.0 without advertise
    F(143, provider="onprem", stage="staging", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("kiosk-api", 8140, """functions:
  menu:
    handler: app.k.menu
    events:
      - http: GET /menu
""").replace("host: 127.0.0.1", "host: 0.0.0.0"),
          "app/__init__.py": "",
          "app/k.py": FUTURE + "def menu(event, ctx):\n    return {\"items\": []}\n"}),
      user="host 0.0.0.0 mean what? pskit info will show which url?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 144 engine native on onprem
    F(144, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#engines"],
      project=dict(files={
          "pskit.yml": onprem_yml("approvals", 8141, """functions:
  review: {handler: app.ap.review}
workflows:
  approve:
    engine: native
    start_at: Review
    states:
      Review: {type: task, function: review, end: true}
"""),
          "app/__init__.py": "",
          "app/ap.py": FUTURE + "def review(event, ctx):\n    return {\"ok\": True}\n"}),
      user="I set engine: native to get Step Functions-like behaviour. Explain what that means on-prem.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 145 known_hosts ignore
    F(145, provider="onprem", stage="prod", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("metrics", 8142, """functions:
  collect:
    handler: app.m.collect
    events:
      - schedule: 5 minutes
""", extra_opts="""    deploy:
      method: ssh
      host: 192.0.2.70
      user: ops
      known_hosts: ignore
      python: system
      install: process
""").replace("host: 127.0.0.1\n", "host: 127.0.0.1\n", 1),
          "app/__init__.py": "",
          "app/m.py": FUTURE + "def collect(event, ctx):\n    return {\"ok\": True}\n"}),
      user="explain deploy block. known_hosts ignore ok for prod?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 146 existing topic onprem
    F(146, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("listener", 8143, """functions:
  on-price:
    handler: app.l.on_price
    events:
      - topic: {name: price-changes, existing: true}
"""),
          "app/__init__.py": "",
          "app/l.py": FUTURE + "def on_price(event, ctx):\n    return None\n"}),
      user="what does existing true do here? who make the topic?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 147 smtp shorthand without resource
    F(147, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/smtp/README.md#create-it"],
      project=dict(files={
          "pskit.yml": onprem_yml("inbox", 8144, """functions:
  on-mail:
    handler: app.mail.on_mail
    events:
      - smtp: inbound-mail
"""),
          "app/__init__.py": "",
          "app/mail.py": FUTURE + "def on_mail(event, ctx):\n    return {\"ok\": True}\n"}),
      user="i want function run when email come. explain my config, it ok?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 148 onprem tick schedule run
    F(148, provider="onprem", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=dict(base="examples/16-on-premises"),
      user="Explain tick: where does its event.data come from, and what does a local schedule test return?",
      steps=[S("invoke_local", function="tick", type="schedule")]),

    # ------------------------------------------------------------------ 149 scheduled example on aws
    F(149, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(base="examples/03-scheduled-jobs"),
      user="explain me these schedules on aws, what aws service run them",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 150 pubsub example on aws
    F(150, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic"],
      project=dict(base="examples/06-pubsub-topic"),
      user="explain the 2 subscribers on aws. filter native?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 151 set_cookie response
    F(151, provider="aws", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: auth
provider:
  name: aws
  region: us-east-1
functions:
  login:
    handler: app.auth.login
    events:
      - http: POST /login
""",
          "app/__init__.py": "",
          "app/auth.py": FUTURE + """from py_serverless_kit import Response


def login(event, ctx):
    user = event.http.json(default={}).get("user", "guest")
    return Response.json({"user": user}).set_cookie(
        "sid", "demo-session-1", max_age=3600, path="/", http_only=True, secure=True, same_site="Lax")
"""}),
      user="what does set_cookie do in login? is the cookie safe?",
      steps=[S("read_file", path="app/auth.py"),
             S("invoke_local", function="login", method="POST", path="/login", data={"user": "ana"})]),

    # ------------------------------------------------------------------ 152 artifact_upload direct
    F(152, provider="aws", stage="dev", mode="ask", page="Setup", persona="detailed_spec",
      sources=["docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: tiny-api
provider:
  name: aws
  region: eu-north-1
  options:
    artifact_upload: direct
functions:
  ping:
    handler: app.t.ping
    events:
      - http: GET /ping
""",
          "app/__init__.py": "",
          "app/t.py": FUTURE + "def ping(event, ctx):\n    return {\"pong\": True}\n"}),
      user="Explain artifact_upload: direct. Our deploy role has no S3 permissions; is this the right setting and what are the risks?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 153 rest example on gcp
    F(153, provider="gcp", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http"],
      project=dict(base="examples/02-rest-api"),
      user="On AWS admin-stats is protected by a JWT authorizer. Explain how that route is protected when this file deploys to GCP.",
      steps=[S("validate"), S("read_file", path="app/handlers.py")]),

    # ------------------------------------------------------------------ 154 gcp bad path param
    F(154, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: users
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  get-user:
    handler: app.u.get_user
    events:
      - http: GET /users/{user-id}
""",
          "app/__init__.py": "",
          "app/u.py": FUTURE + "def get_user(event, ctx):\n    return {\"id\": event.http.path_params[\"user-id\"]}\n"}),
      user="explain get-user route, validate show error about path",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 155 gcp env vars handler
    F(155, provider="gcp", stage="staging", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: flags
provider:
  name: gcp
  region: europe-west1
""" + GCP_OPTS + """  environment:
    FEATURE_DARK_MODE: "true"
functions:
  flags:
    handler: app.flags.get
    environment:
      FEATURE_BETA: "false"
    events:
      - http: GET /flags
""",
          "app/__init__.py": "",
          "app/flags.py": FUTURE + """import os


def get(event, ctx):
    return {
        "dark_mode": os.environ.get("FEATURE_DARK_MODE") == "true",
        "beta": os.environ.get("FEATURE_BETA") == "true",
    }
"""}),
      user="where flags function get values from? explain",
      steps=[S("get_project"), S("invoke_local", function="flags", method="GET", path="/flags")]),

    # ------------------------------------------------------------------ 156 gcp choice with and
    F(156, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: loans
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  auto-approve: {handler: app.loan.auto}
  manual: {handler: app.loan.manual}
workflows:
  decide:
    start_at: Rules
    states:
      Rules:
        type: choice
        choices:
          - and:
              - {variable: $.amount, lte: 5000}
              - {variable: $.score, gte: 700}
            next: Auto
        default: Manual
      Auto: {type: task, function: auto-approve, end: true}
      Manual: {type: task, function: manual, end: true}
""",
          "app/__init__.py": "",
          "app/loan.py": FUTURE + "def auto(event, ctx):\n    return {\"approved\": True}\n\n\ndef manual(event, ctx):\n    return {\"queued\": True}\n"}),
      user="Explain the decide workflow's rule. What happens with amount 3000 and no score field at all?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 157 rest example on azure
    F(157, provider="azure", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#azure-azure-functions"],
      project=dict(base="examples/02-rest-api"),
      user="validate books api for azure, explain what's azure-specific",
      steps=[S("validate"), S("get_project")]),

    # ------------------------------------------------------------------ 158 orders workflow on azure
    F(158, provider="azure", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#embedded-orchestrator"],
      project=dict(base="examples/07-workflow-orders"),
      user="On AWS order-pipeline is Step Functions. Explain how it runs on Azure with this file and any limits I should know.",
      steps=[S("validate")]),

    # ------------------------------------------------------------------ 159 azure path param handler
    F(159, provider="azure", stage="staging", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: azure
  region: westeurope
functions:
  product:
    handler: app.shop.product
    events:
      - http: GET /products/{sku}
""",
          "app/__init__.py": "",
          "app/shop.py": FUTURE + """from py_serverless_kit import NotFound

PRODUCTS = {"tea-01": {"name": "Green tea", "price": 4.5}}


def product(event, ctx):
    sku = event.http.path_params["sku"]
    if sku not in PRODUCTS:
        raise NotFound(f"no product {sku}")
    return PRODUCTS[sku]
"""}),
      user="explain product function, what is sku and path_params",
      steps=[S("read_file", path="app/shop.py"),
             S("invoke_local", function="product", method="GET", path="/products/tea-01")]),

    # ------------------------------------------------------------------ 160 azure managed resources
    F(160, provider="azure", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#fields", "docs/resources.md#what-handlers-receive"],
      project=dict(files={
          "pskit.yml": """service: docs-hub
provider:
  name: azure
  region: westeurope
resources:
  files:
    type: storage
    name: docs-hub-files
  index-jobs:
    type: queue
functions:
  upload:
    handler: app.hub.upload
    events:
      - http: POST /docs
  indexer:
    handler: app.hub.indexer
    events:
      - queue: {resource: index-jobs}
""",
          "app/__init__.py": "",
          "app/hub.py": FUTURE + "def upload(event, ctx):\n    return {\"ok\": True}, 202\n\n\ndef indexer(event, ctx):\n    return None\n"}),
      user="Explain the resources section: what Azure creates in prod, which functions can use each resource, and how upload finds the container name.",
      steps=[S("get_project"), S("validate")]),
]

FINALS = {
    141: """`hello` answers `GET /hello`:
1. It reads `name` from the query string (`event.http.query`), or uses `world` [docs/handlers.md#httprequest].
2. It logs `greeting` with that name.
3. It returns a message, the provider and the stage.

My local run without a query returned 200:
```json
{"message": "Hello, world!", "provider": "local", "stage": "dev"}
```
`provider` is `local` in a test; on the deployed host it's `onprem`. With `/hello?name=Ana` the message would be `Hello, Ana!`.""",

    142: """`ping` is a one-state workflow: **Mark** runs the `mark` function, then ends. It uses the embedded engine, which runs inside the on-prem host.

`mark` copies its input, adds `"seen": true`, logs `marked` and returns it. A direct local invoke with `{"order": 5}` returned `{"order": 5, "seen": true}`.

**Calling mark without a run**: on the deployed host, no by default. Mark is a `task` and the first state, so when `mark` runs on its own (its HTTP route, `invoke()`, `pskit trigger`, a schedule...) the host also starts a `ping` run. The call's result is reused as that state's result, so `mark` doesn't run twice [docs/workflows.md#embedded-orchestrator]. To turn this off, set `options.start_on_entry: false` on the workflow. `pskit invoke` (what I just ran) calls the handler directly, without a host, so it starts nothing.""",

    143: """`host: 0.0.0.0` means the service listens on **all network interfaces** of the machine, so other computers can call `GET /menu` on port 8140. With `127.0.0.1` only this machine could.

For `pskit info`: `0.0.0.0` isn't a real address you can call, so it is advertised as `http://127.0.0.1:8140` unless you set `advertise` [docs/providers.md#onprem-on-premises]. Since you want others to use it, add the address they should use, for example:
```yaml
provider:
  options:
    advertise: http://kiosk.internal.example:8140
```
Validate for onprem/staging: valid. Remember to allow port 8140 in the machine's firewall.""",

    144: """On premises `engine: native` doesn't exist. Validate fails:
`On-premises has no native workflow service supported by pskit; use `engine: embedded` or `auto``

"Native" means the cloud's own workflow service: Step Functions on AWS, Cloud Workflows on GCP, Logic Apps on Azure [docs/workflows.md#engines]. On premises there's no such service, so the **embedded** engine is used. It still gives you Step Functions-like behaviour: the same state types, retry/catch, an `execution_id` per run, and runs you can list, follow and cancel on the host.

Fix: remove `engine: native` (the default `auto` picks embedded on onprem), or write `engine: embedded`. Shall I change it?""",

    145: """The deploy block ships `metrics` over SSH to `ops@192.0.2.70`, runs it with the server's own Python (`python: system`) as a plain process (`install: process`), and `collect` runs every 5 minutes. Validate for onprem/prod: valid, with two warnings:
- the server must already have python3.12 on PATH (or use `python: bundle`);
- the host binds to `127.0.0.1` on the server, so only that server can reach it. That's fine for a schedule-only service.

**`known_hosts: ignore`** is not ok for prod. It turns off SSH host key checking, so pskit would deploy to whatever machine answers on that address, which is a man-in-the-middle risk [docs/providers.md#onprem-on-premises]. Use `accept-new` (trust the key the first time, then refuse changes), or a path to a `known_hosts` file with the server's key.

Also, with `install: process` the host doesn't come back after a reboot; `install: systemd` (needs `sudo: true`) does.""",

    146: """`existing: true` means pskit does **not** create the `price-changes` topic. On premises a topic is a directory, and the host waits until that directory appears before it delivers anything to `on-price` [docs/providers.md#onprem-on-premises].

So someone else makes it: another service or process that publishes to `price-changes` and owns the directory. Without `existing`, the host would create it at start.

Validate for onprem: valid. If nothing ever creates the topic, `on-price` never runs, so check who owns it.""",

    147: """You want `on-mail` to run for each incoming mail, and `- smtp: inbound-mail` is the right trigger. But it points at an SMTP server resource that doesn't exist in this project. Validate fails:
`function 'on-mail' uses unknown resource 'inbound-mail'; known: <none>`

The `smtp` trigger always needs an `smtp` resource, which is the mail server that receives the mail [docs/smtp/README.md#create-it]:
1. **Resources** > **+ SMTP server**: key `inbound-mail`, your domain (for example `inbound.example.com`), where it runs, port 25, and tick `on-mail`.
2. Add the A and MX records from its **DNS guide** at your domain provider.

Studio then writes the `resources.inbound-mail` block (`type: smtp`) into pskit.yml, and validate passes.""",

    148: """`tick` gets its `event.data` from the schedule's `input` in pskit.yml: `schedule: {rate: 1 hour, input: {source: on-prem}}` [docs/events.md#schedule]. It's the same idea as the constant Input of an EventBridge rule.

The handler logs `tick` with that data and returns it. A local schedule test without a payload uses the configured input, and returned:
```json
{"ok": true, "data": {"source": "on-prem"}}
```
To test other input, pass your own data in the test; the deployed schedule always sends `{source: on-prem}`.""",

    149: """Validate for aws: valid, 3 functions in `eu-central-1`. On AWS all schedules are **EventBridge Scheduler** schedules that call the Lambda [docs/events.md#schedule]:

| Function | When | Input (`event.data`) |
|---|---|---|
| `heartbeat` | every 5 minutes | none |
| `daily-report` | 09:00 Mon-Fri, Berlin time | `report: sales`, `days: 1`, recipients |
| `daily-report` (`weekly`) | 07:00 Mondays, UTC | `report: sales-weekly`, `days: 7` |
| `cleanup` | once a day | `retention_days: 90` |

- `timezone: Europe/Berlin` works on AWS, so the 09:00 stays local across daylight saving.
- `cleanup`'s `enabled` comes from `CLEANUP_ENABLED` (default true), so you can switch it off without deleting it.
- Timeouts: 120 s by default, 300 s for `daily-report`, 900 s for `cleanup` (AWS's maximum).""",

    150: """Validate for aws: valid. Both functions subscribe to the SNS topic `order-events`, so each gets its own copy of a message (fan-out) [docs/events.md#topic]:

- `update-analytics`: no filter, every message.
- `notify-customer`: `filter: {event_type: ["order.shipped"]}`.

Yes, on AWS the filter is native: pskit turns it into an **SNS filter policy** on the subscription. SNS drops non-matching messages before Lambda runs, so `notify-customer` isn't even invoked for other event types. The filter matches **message attributes**, so publishers must set `event_type` as an attribute, not only in the JSON body.""",

    151: """`login` reads `user` from the JSON body (default `guest`) and returns `{"user": ...}` as JSON, plus a cookie set with `Response.json(...).set_cookie(...)` [docs/handlers.md#returning-a-response]:

- `sid` = the session value, kept for `max_age=3600` (1 hour), for the whole site (`path="/"`).
- `http_only=True`: JavaScript in the page can't read it, which helps against XSS.
- `secure=True`: only sent over HTTPS.
- `same_site="Lax"`: not sent with most cross-site requests, which helps against CSRF.

Those flags are good. My local run returned 200 with `{"user": "ana"}`; the local output doesn't list the cookie header, so I can't show it here.

The real weak spot is the value: `"demo-session-1"` is a fixed string, so every user would get the same session. Use a random token per login (for example `secrets.token_urlsafe(32)`) and store it server-side. Also, there's no password check yet.""",

    152: """`artifact_upload: direct` sends the code zip **inline** with the Lambda create/update call, instead of uploading it to S3 first [docs/providers.md#aws-aws-lambda]. Validate for aws: valid.

With the default `s3`, pskit creates a private `<service>-<stage>-code-*` bucket (or uses `artifact_bucket`) and the deploying identity needs `s3:CreateBucket` / `PutObject`. With `direct`, it doesn't need S3 at all, so for a role without S3 rights it's the right setting.

Risks:
- It's **only for small bundles**. Inline uploads hit the 50 MB limit, and larger ones can fail with `decomposing request: bufio.Scanner: token too long`.
- Adding a few dependencies can push you over that later.

For `tiny-api` with one small function, `direct` is fine. If the bundle grows, grant `PutObject` on one `artifact_bucket` instead.""",

    153: """Validate for gcp: valid, 9 functions.

On GCP there's no JWT authorizer (pskit's `auth: jwt` is AWS only) [docs/events.md#http]. So the `providers.gcp` block replaces `admin-stats`'s events with a plain `GET /admin/stats`. The route is **public** at the platform level.

The protection moves into the handler. `admin_stats` checks:
```python
if event.provider not in ("aws", "local") and not event.http.headers.get("authorization"):
    raise Unauthorized("missing bearer token")
```
So on GCP a request without an `Authorization` header gets 401. But it only checks that the header **exists**; it doesn't verify the token. The code comment says it: verify it with a JWT library in a real service. Until then, anyone who sends any `Authorization` value can read the stats on GCP.

Alternative on GCP: `auth: iam`, if the callers are Google identities.""",

    154: """`get-user` should answer `GET /users/<id>` and return the id from the path.

Validate fails:
`invalid path template '/users/{user-id}'; use /users/{id} or /files/{path+}`

Path parameter names must be identifiers: letters, digits and `_`, no dashes [docs/events.md#http]. Use `{user_id}`:
- route: `GET /users/{user_id}`
- handler: `event.http.path_params["user_id"]`

Want me to change both?""",

    155: """`flags` reads two environment variables and turns them into booleans:

- `FEATURE_DARK_MODE` from `provider.environment`: every function gets it. Value `"true"`.
- `FEATURE_BETA` from `functions.flags.environment`: only this function. Value `"false"`.

A function's `environment` is merged over the provider-level one, and pskit adds its own `PSKIT_*` variables on top [docs/handlers.md#environment-variables]. The values are quoted strings, so the code compares with `== "true"`.

My local run returned `{"dark_mode": true, "beta": false}`. To change a flag, edit the value and deploy again; on GCP they become the function's environment variables.""",

    156: """Validate for gcp: valid, `workflow decide: native engine` (Cloud Workflows).

**Rules** (choice) has one rule with `and`: go to **Auto** only when **both** are true [docs/workflows.md#choice-rules]:
- `$.amount` is at most 5000, and
- `$.score` is at least 700.

Otherwise `default` sends it to **Manual**. Auto runs `auto-approve`, Manual runs `manual`, and each ends the run.

**Amount 3000 with no `score`**: the first condition is true, but a rule whose variable is missing evaluates to **false** instead of failing. So the `and` is false and the loan goes to **Manual**. That's a safe default: no score, no auto-approval.""",

    157: """Validate for azure: valid, 9 functions. What's Azure-specific [docs/providers.md#azure-azure-functions]:

- **One Function App** hosts all 9 functions, with region `eastus` and the subscription from `ARM_SUBSCRIPTION_ID` (`providers.azure`).
- **No `/api` prefix**: routes are served exactly as written, `/books`, `/books/{id}`, `/admin/stats`...
- **`admin-stats`**: JWT auth isn't supported on Azure, so `providers.azure` restates it as a plain `GET /admin/stats`. The route is public, and the handler refuses requests without an `Authorization` header (it doesn't verify the token).
- **CORS**: `custom.cors` (the two origins, credentials allowed) is applied by pskit's runtime on Azure; there's no gateway CORS like on AWS.
- `environment` would be app-wide on Azure; this project sets none per function, so there's no conflict.""",

    158: """Validate for azure: valid, `workflow order-pipeline: embedded engine`, with a warning:
`runs on the embedded engine inside one function: total runtime is capped by the function timeout (600s max on Azure Functions)`

On Azure `engine: auto` keeps the embedded engine. pskit adds one extra function, `order-pipeline-orchestrator` (that's why there are 6 functions). It runs the states and calls `validate-order`, `reserve-item`, `charge-payment` and the others **in-process**, inside one invocation [docs/workflows.md#embedded-orchestrator].

Limits to know:
- The **whole run** must fit in 600 s. The workflow's own `timeout: 3600` can't be reached on Azure. The 30 s wait in ManualReview, map and retries all count.
- Start it with `POST /workflows/order-pipeline`; the answer is synchronous with `execution_id`, `status` and `output`.
- The route is public when HTTP is public; set `options.http: false` on the workflow for sensitive flows.

For long runs, set `engine: native` to deploy it as a Logic App.""",

    159: """`product` answers `GET /products/{sku}`.

- `{sku}` in the path is a **path parameter**: whatever is in that part of the URL. For `/products/tea-01`, `event.http.path_params["sku"]` is `"tea-01"` [docs/handlers.md#httprequest].
- If the SKU isn't in `PRODUCTS`, it raises `NotFound`, which pskit turns into a 404 JSON answer.
- Otherwise it returns the product as JSON.

My local run of `GET /products/tea-01` returned 200 with `{"name": "Green tea", "price": 4.5}`. `/products/coffee` would give 404 `no product coffee`.""",

    160: """Validate for azure/prod: valid, 2 functions.

**Created in prod** (both are managed, not `external`) [docs/resources.md#fields]:
- `files` (storage): a blob container named `docs-hub-files`.
- `index-jobs` (queue): a Storage Queue, in the Function App's storage account. It has no `name`, so the resource key is used.

**Who can use them**: neither resource has a `functions:` list, so every function you wrote, `upload` and `indexer`, gets both bindings. `indexer` is also triggered by `index-jobs` through `queue: {resource: index-jobs}`.

**How `upload` finds the container**: pskit passes each binding as environment variables, for example `PSKIT_RESOURCE_FILES_NAME=docs-hub-files` [docs/resources.md#what-handlers-receive]. In code: `resource("files").native_name`. So the name is never hard-coded and `pskit invoke` sets the same variables locally.""",
}

for _c in CONVERSATIONS:
    _c["final"] = FINALS[int(_c["id"].split("-")[1])]
