"""Category F (explain a config or handler), batch 7. Hand-written; assembled by tools/assemble.py.

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
    # ------------------------------------------------------------------ 121 remove hooks + data
    F(121, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/configuration.md#hooks", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": onprem_yml("ledger-sync", 8130, """hooks:
  before_remove: ["python scripts/export_state.py"]
  after_remove: ["python scripts/notify_ops.py"]
functions:
  sync:
    handler: app.sync.run
    events:
      - queue: ledger-changes
""", extra_opts="""    data_dir: /var/lib/pskit/ledger-sync
"""),
          "app/__init__.py": "",
          "app/sync.py": FUTURE + "def run(event, ctx):\n    return None\n",
          "scripts/export_state.py": "print('exported')\n",
          "scripts/notify_ops.py": "print('notified')\n"}),
      user="Explain what happens, in order, when someone runs pskit remove on this service, and whether queued ledger changes survive.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 122 host tuning options
    F(122, provider="onprem", stage="prod", mode="ask", page="Logs", persona="terse_expert",
      sources=["docs/providers.md#logs-and-stats"],
      project=dict(files={
          "pskit.yml": onprem_yml("gateway", 8131, """functions:
  route:
    handler: app.gw.route
    events:
      - http: ANY /api/{path+}
""", extra_opts="""    poll_seconds: 0.2
    log_buffer: 20000
    log_level: DEBUG
"""),
          "app/__init__.py": "",
          "app/gw.py": FUTURE + "def route(event, ctx):\n    return {\"path\": event.http.path_params[\"path\"]}\n"}),
      user="explain poll_seconds, log_buffer, log_level here. prod-safe?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 123 unknown hook
    F(123, provider="onprem", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#hooks"],
      project=dict(files={
          "pskit.yml": onprem_yml("site", 8132, """hooks:
  pre_deploy: ["npm run build"]
functions:
  page:
    handler: app.site.page
    events:
      - http: GET /
"""),
          "app/__init__.py": "",
          "app/site.py": FUTURE + "def page(event, ctx):\n    return \"<h1>hi</h1>\"\n"}),
      user="serverless-plugin-scripts had a pre_deploy hook. Explain this config and whether that hook name works in pskit.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 124 unknown resource
    F(124, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#using-a-resource-from-an-event"],
      project=dict(files={
          "pskit.yml": onprem_yml("print-shop", 8133, """functions:
  printer:
    handler: app.print.run
    events:
      - queue: {resource: print-jobs}
"""),
          "app/__init__.py": "",
          "app/print.py": FUTURE + "def run(event, ctx):\n    return None\n"}),
      user="what is resource print-jobs in my printer function? where is it?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 125 workflow next missing
    F(125, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": onprem_yml("kyc", 8134, """functions:
  check: {handler: app.kyc.check}
  approve: {handler: app.kyc.approve}
workflows:
  verify:
    start_at: Check
    states:
      Check: {type: task, function: check, next: Aprove}
      Approve: {type: task, function: approve, end: true}
"""),
          "app/__init__.py": "",
          "app/kyc.py": FUTURE + "def check(event, ctx):\n    return {}\n\n\ndef approve(event, ctx):\n    return {}\n"}),
      user="""workflows.verify: Value error, state 'Check' points to unknown state 'Aprove'
what is verify supposed to do and whats wrong""",
      steps=[S("get_validation"), S("get_project")]),

    # ------------------------------------------------------------------ 126 async sleep handler
    F(126, provider="onprem", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": onprem_yml("retry-api", 8135, """functions:
  fetch:
    handler: app.fetch.handle
    events:
      - http: GET /fetch
"""),
          "app/__init__.py": "",
          "app/fetch.py": FUTURE + """import asyncio


async def _call(attempt):
    await asyncio.sleep(0.05)
    if attempt < 2:
        raise ConnectionError("upstream busy")
    return {"data": "ok"}


async def handle(event, ctx):
    for attempt in range(3):
        try:
            return await _call(attempt)
        except ConnectionError:
            ctx.logger.warning("retry", extra={"attempt": attempt})
    return {"data": None}, 503
"""}),
      user="fetch is async with retry loop. explain how many tries and what user get",
      steps=[S("read_file", path="app/fetch.py"),
             S("invoke_local", function="fetch", method="GET", path="/fetch")]),

    # ------------------------------------------------------------------ 127 duplicate route
    F(127, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": onprem_yml("portal", 8136, """functions:
  status-v1:
    handler: app.portal.status_v1
    events:
      - http: GET /status
  status-v2:
    handler: app.portal.status_v2
    events:
      - http: GET /status
"""),
          "app/__init__.py": "",
          "app/portal.py": FUTURE + "def status_v1(event, ctx):\n    return {\"v\": 1}\n\n\ndef status_v2(event, ctx):\n    return {\"v\": 2}\n"}),
      user="i have v1 and v2 of status. explain which one answer?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 128 set + decimal return
    F(128, provider="onprem", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": onprem_yml("tags-api", 8137, """functions:
  tags:
    handler: app.tags.handle
    events:
      - http: GET /tags
"""),
          "app/__init__.py": "",
          "app/tags.py": FUTURE + """from decimal import Decimal


def handle(event, ctx):
    tags = {"python", "serverless", "python"}
    return {"tags": tags, "price": Decimal("9.90")}
"""}),
      user="Explain what tags returns. I expected a set and a Decimal to break JSON serialisation; do they?",
      steps=[S("read_file", path="app/tags.py"),
             S("invoke_local", function="tags", method="GET", path="/tags")]),

    # ------------------------------------------------------------------ 129 aws one handler, two triggers
    F(129, provider="aws", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: ingest
provider:
  name: aws
  region: us-east-1
functions:
  ingest:
    handler: app.ingest.handle
    events:
      - http: POST /ingest
      - queue: ingest-backlog
""",
          "app/__init__.py": "",
          "app/ingest.py": FUTURE + """

def handle(event, ctx):
    if event.is_http:
        items = [event.http.json()]
    else:
        items = [r.json() for r in event.records]
    ctx.logger.info("ingest", extra={"type": event.type, "count": len(items)})
    return {"ingested": len(items)}
"""}),
      user="explain the branching in handle",
      steps=[S("read_file", path="app/ingest.py"),
             S("invoke_local", function="ingest", type="queue", data=[{"a": 1}, {"a": 2}])]),

    # ------------------------------------------------------------------ 130 aws cors true
    F(130, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: widget
provider:
  name: aws
  region: us-east-1
functions:
  config:
    handler: app.widget.config
    events:
      - http: {method: GET, path: /widget/config, cors: true}
""",
          "app/__init__.py": "",
          "app/widget.py": FUTURE + "def config(event, ctx):\n    return {\"theme\": \"light\"}\n"}),
      user="what does cors: true allow? any website?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 131 aws jwt no authorizer
    F(131, provider="aws", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: profile
provider:
  name: aws
  region: eu-west-1
functions:
  me:
    handler: app.profile.me
    events:
      - http: {method: GET, path: /me, auth: jwt}
""",
          "app/__init__.py": "",
          "app/profile.py": FUTURE + "def me(event, ctx):\n    return {\"me\": None}\n"}),
      user="explain auth jwt on me. validate say something",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 132 aws disabled schedule
    F(132, provider="aws", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: billing-jobs
provider:
  name: aws
  region: us-east-1
functions:
  invoices:
    handler: app.jobs.invoices
    events:
      - schedule: {cron: "0 2 1 * *", input: {run: monthly}, name: monthly-invoices}
      - schedule: {rate: 1 day, input: {run: catch-up}, enabled: false, name: catch-up}
""",
          "app/__init__.py": "",
          "app/jobs.py": FUTURE + "def invoices(event, ctx):\n    return {\"run\": event.data[\"run\"]}\n"}),
      user="In EventBridge I had two rules, one DISABLED. Explain these two schedules and what exists in prod after deploy.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 133 invoke example on gcp
    F(133, provider="gcp", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(base="examples/09-function-invoke"),
      user="On AWS invoke() used lambda:InvokeFunction. Explain how quote reaches price-calculator when this runs on GCP.",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 134 gcp start_at missing
    F(134, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": """service: returns
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  inspect: {handler: app.ret.inspect}
  refund: {handler: app.ret.refund}
workflows:
  process-return:
    start_at: Start
    states:
      Inspect: {type: task, function: inspect, next: Refund}
      Refund: {type: task, function: refund, end: true}
""",
          "app/__init__.py": "",
          "app/ret.py": FUTURE + "def inspect(event, ctx):\n    return {}\n\n\ndef refund(event, ctx):\n    return {}\n"}),
      user="explain my return workflow, studio says error",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 135 gcp topic handler raises
    F(135, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#errors", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: sync
provider:
  name: gcp
  region: europe-west1
""" + GCP_OPTS + """functions:
  push-crm:
    handler: app.sync.push
    events:
      - topic: customer-updates
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """

def push(event, ctx):
    for record in event.records:
        customer = record.json()
        if "email" not in customer:
            raise ValueError(f"customer {customer.get('id')} has no email")
        ctx.logger.info("pushed", extra={"id": customer["id"]})
"""}),
      user="Explain what push-crm does when one message in the delivery has no email, and what Pub/Sub will do about it.",
      steps=[S("read_file", path="app/sync.py"),
             S("invoke_local", function="push-crm", type="topic", data=[{"id": 9}])]),

    # ------------------------------------------------------------------ 136 gcp bad method
    F(136, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: sync-api
provider:
  name: gcp
  region: us-central1
""" + GCP_OPTS + """functions:
  pull:
    handler: app.api.pull
    events:
      - http: FETCH /sync
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + "def pull(event, ctx):\n    return {\"items\": []}\n"}),
      user="explain this http line, i used FETCH because client use fetch()",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 137 async example on azure
    F(137, provider="azure", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#context"],
      project=dict(base="examples/12-async-and-context"),
      user="validate this for azure + explain batch-job's time check there",
      steps=[S("validate"), S("read_file", path="app/handlers.py")]),

    # ------------------------------------------------------------------ 138 azure container uppercase
    F(138, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: photos
provider:
  name: azure
  region: westeurope
functions:
  resize:
    handler: app.photos.resize
    events:
      - storage: {bucket: UserPhotos, suffix: .jpg}
""",
          "app/__init__.py": "",
          "app/photos.py": FUTURE + "def resize(event, ctx):\n    return None\n"}),
      user="explain resize trigger. is UserPhotos ok as name?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 139 azure literal key in env
    F(139, provider="azure", stage="prod", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": """service: mailer
provider:
  name: azure
  region: westeurope
  environment:
    MAIL_FROM: noreply@example.com
    MAIL_API_KEY: demo-key-7f3a9c21
functions:
  send:
    handler: app.mail.send
    events:
      - queue: outbox
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + "def send(event, ctx):\n    return None\n"}),
      user="explain environment in my file, validate is green so all good?",
      steps=[S("get_project"), S("validate")]),

    # ------------------------------------------------------------------ 140 azure two keys in event
    F(140, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md"],
      project=dict(files={
          "pskit.yml": """service: hooks
provider:
  name: azure
  region: westeurope
functions:
  receiver:
    handler: app.hooks.receive
    events:
      - http: POST /hooks
        schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/hooks.py": FUTURE + "def receive(event, ctx):\n    return None\n"}),
      user="In serverless.yml I grouped events like this. Explain what receiver's events block means to pskit.",
      steps=[S("get_project"), S("validate")]),
]

FINALS = {
    121: """Validate for onprem: valid. `pskit remove` on this service runs in this order:

1. **`before_remove`**: `python scripts/export_state.py`, in the project root with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set. If it exits non-zero, the remove stops there [docs/configuration.md#hooks].
2. **Remove**: the host process (or container / systemd unit) is stopped.
3. **`after_remove`**: `python scripts/notify_ops.py`.

**Queued ledger changes survive.** Remove does not delete `data_dir`, here `/var/lib/pskit/ledger-sync`, and that's where the `ledger-changes` queue files are [docs/providers.md#onprem-on-premises]. The next deploy with the same `data_dir` picks them up. Delete that folder yourself only if you really want them gone.

Remove asks for confirmation on the **Deploy** page (and typed confirmation for `prod*` stages).""",

    122: """Validate for onprem/prod: valid. The three options [docs/providers.md#logs-and-stats]:

- `poll_seconds: 0.2`: how often the host checks queues, buckets and drivers. The default is 0.5. Lower means faster pickup but more CPU and disk polling. `route` is HTTP only, so it doesn't gain anything here.
- `log_buffer: 20000`: the newest 20000 log entries are kept in memory for `/__pskit/logs` (default 5000). Everything is still written to `<data_dir>/logs/host.jsonl`, which rotates at 10 MiB.
- `log_level: DEBUG`: capture `logging` records from DEBUG up (default INFO).

For prod, DEBUG plus a big buffer means more memory and noisier logs, and debug lines sometimes contain request data. I'd keep `INFO` and the default buffer in prod, and use DEBUG on dev.""",

    123: """The config serves one function, `page`, on `GET /`, returning a small HTML string as text.

The hook name doesn't work. Validate fails with:
`unknown hooks ['pre_deploy']; allowed: ['after_deploy', 'after_package', 'after_remove', 'before_deploy', 'before_package', 'before_remove']`

pskit's hooks are `before_` / `after_` package, deploy and remove [docs/configuration.md#hooks]. Use `before_deploy: ["npm run build"]`, or `before_package` if the build output must be in the bundle: that also runs before every deploy, and before `pskit package` on its own. Shall I rename it to `before_package`?""",

    124: """`queue: {resource: print-jobs}` says: "listen to the queue described under `resources:` as `print-jobs`" [docs/resources.md#using-a-resource-from-an-event]. But your file has no `resources:` section, so it doesn't exist anywhere. Validate fails:
`function 'printer' uses unknown resource 'print-jobs'; known: <none>`

Two fixes:
1. Simplest: `- queue: print-jobs` (the queue name directly). On premises the host creates it at start.
2. Or declare it:
```yaml
resources:
  print-jobs:
    type: queue
```
That's useful when other functions use it too, or it lives in Redis or another driver later. Which do you prefer?""",

    125: """`verify` should run **Check** (`check`) and then **Approve** (`approve`), and end.

The problem is a typo: Check says `next: Aprove` (one `p`), but the state is called `Approve`. Validate shows the error you pasted:
`state 'Check' points to unknown state 'Aprove'`

Every `next` must name a state in `states` exactly, case included [docs/workflows.md#workflow-keys]. Fix: `next: Approve`. Want me to change it?""",

    126: """`handle` is `async`, and pskit awaits it for you. It tries up to **3 times**:

1. `_call` waits 50 ms, then raises `ConnectionError` for attempts 0 and 1, and succeeds on attempt 2.
2. Each `ConnectionError` is logged as `retry`, then the loop tries again.
3. If all 3 failed, the user would get `{"data": null}` with status **503**.

My local run shows the normal path: two `retry` warnings, then 200 with `{"data": "ok"}` on the third try.

Real-life notes: there's no wait between tries except the 50 ms in `_call`, so a busy upstream gets hit three times quickly. A growing pause, like `await asyncio.sleep(0.2 * (attempt + 1))`, is kinder.""",

    127: """Neither: this config doesn't load. Validate fails with:
`route GET /status is used by both 'status-v1' and 'status-v2'`

Two functions can't declare the same `METHOD /path` [docs/events.md#http], so pskit can't decide which one answers. Common fixes:
1. Version in the path: `GET /v1/status` and `GET /v2/status`.
2. Or keep only `status-v2` on `/status` and delete or disable v1.

Which one do you want?""",

    128: """`tags` returns a dict with a `set` of tags and a `Decimal` price. Neither breaks anything: pskit's JSON serialiser handles `set`, `Decimal`, `datetime`, `UUID` and objects with `model_dump()` or `to_dict()` [docs/handlers.md#returning-a-response].

The local run returned 200 with:
```json
{"tags": ["python", "serverless"], "price": 9.9}
```

Two details:
- The set becomes a **list**, and duplicates are already gone (`python` once). The order of a set is not guaranteed, so sort it if clients compare lists: `sorted(tags)`.
- `Decimal("9.90")` became the number `9.9`. If you need exactly two decimals in the answer, send it as a string (`"9.90"`) or as cents.""",

    129: """`ingest` has two triggers, so `handle` checks where the event came from [docs/handlers.md#event]:

- `event.is_http` true (from `POST /ingest`): one item, the JSON body.
- otherwise (from the `ingest-backlog` SQS queue): one item per message in `event.records`.

It logs `ingest` with `event.type` and the count, and returns `{"ingested": n}`. My local queue run with two messages returned `{"ingested": 2}`.

Note: on the queue path, a bad message raises and the whole batch is retried. Returning a `BatchResult` would retry only the bad one.""",

    130: """`cors: true` turns CORS on with the defaults [docs/events.md#http]:
- origins `["*"]`: **any website** may call it from a browser;
- methods GET POST PUT PATCH DELETE OPTIONS;
- headers `Content-Type`, `Authorization`, `X-Requested-With`.

pskit's runtime answers preflights with 204 and adds the `Access-Control-*` headers; on AWS, CORS is also set on the HTTP API. Validate for aws: valid.

For a public widget config that's fine. If only your own sites should read it, list them:
```yaml
- http:
    method: GET
    path: /widget/config
    cors:
      origins: ["https://app.example.com"]
```
CORS only limits browsers; anyone can still call the URL directly.""",

    131: """`auth: jwt` on `GET /me` means API Gateway should only let requests through that carry a valid JWT. But it doesn't know which tokens to trust, so validate fails:
`jwt auth needs authorizer.issuer and authorizer.audience`

You need [docs/events.md#http]:
```yaml
- http:
    method: GET
    path: /me
    auth: jwt
    authorizer:
      issuer: https://<your login server>/
      audience: [<your api or client id>]
```
- `issuer`: who issues the tokens, for example your Cognito user pool or Auth0 URL.
- `audience`: who the tokens are for.

Tell me the issuer and audience and I'll add them.""",

    132: """Validate for aws/prod: valid. `invoices` has two schedules [docs/events.md#schedule]:

1. **monthly-invoices**: `0 2 1 * *`, 02:00 UTC on the 1st of each month, with `event.data == {"run": "monthly"}`.
2. **catch-up**: every day, `{"run": "catch-up"}`, with `enabled: false`.

`name` is used in the resource names, so the two schedules are easy to tell apart in AWS. After deploy, both EventBridge Scheduler schedules exist and point at the same Lambda; the catch-up one is created **disabled**, like your DISABLED rule. Set `enabled: true` and deploy again to turn it on.

The handler returns `event.data["run"]`, so it can tell which schedule called it.""",

    133: """Validate for gcp: valid, 3 functions. On GCP, `invoke()` doesn't use an SDK call: it makes an **authenticated HTTPS call** to the other function's URL, `https://<region>-<project>.cloudfunctions.net/<service>-<stage>-<name>`, with an ID token from the metadata server [docs/handlers.md#invoke-calling-another-function].

So `invoke("price-calculator", {...})` in `quote` waits for that call and gets the totals back, like on AWS. The handler code doesn't change.

Two differences:
- `asynchronous=True` (the `audit-log` call) is fire-and-forget only on AWS.
- Validate warns `iam.statements are AWS-style and ignored on GCP`. The `lambda:InvokeFunction` statement does nothing here; the runtime service account must be allowed to invoke the other functions.""",

    134: """`process-return` should run **Inspect** (`inspect`) and then **Refund** (`refund`).

Validate fails with:
`start_at 'Start' is not a defined state`

`start_at` must name the first state, and there's no state called `Start` [docs/workflows.md#workflow-keys]. Set `start_at: Inspect` and it works. Shall I change it?""",

    135: """`push-crm` handles every message of a Pub/Sub delivery. For each one it parses the customer JSON and logs `pushed`. If a customer has no `email`, it **raises** `ValueError`.

My local run with `{"id": 9}` shows it: `ValueError: customer 9 has no email`, and the function failed.

What happens then: for non-HTTP events pskit re-raises the exception, so the platform's retry rules apply [docs/handlers.md#errors]. On GCP a failure retries **the whole delivery**, and there's no partial batch failure [docs/events.md#queue]. A message that will never have an email fails again on every retry.

Better: log and skip bad customers instead of raising, and only raise for errors where a retry can help, like the CRM being down.""",

    136: """`- http: FETCH /sync` means "method FETCH on path `/sync`". But FETCH isn't an HTTP method, so validate fails:
`method must be one of GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, ANY`

The browser's `fetch()` is a JavaScript function; it sends a normal method, `GET` by default [docs/events.md#http]. So for `pull`:
- `- http: GET /sync` if the client only reads,
- or `POST /sync` if it sends a body.

`GET` is what a plain `fetch("/sync")` uses. Shall I set that?""",

    137: """Validate for azure: valid, 3 functions.

`batch_job` does up to 100 chunks of work. Before each chunk it calls `ctx.remaining_time_ms()`. When that is **not None** and below 3000 ms, it logs a warning and stops early [docs/handlers.md#context].

On Azure, pskit doesn't get a deadline from the platform, so `remaining_time_ms()` returns `None`. The check is then skipped and the loop never stops early. Only the function timeout stops a long run there (600 s max on Azure). The `is not None` guard matters: without it the code would crash on Azure.

If you need a time budget on Azure, measure it yourself with `time.monotonic()` against your own limit.""",

    138: """`resize` should run when a `.jpg` is uploaded to the blob container `UserPhotos`.

The name isn't ok on Azure. Validate fails:
`container name 'UserPhotos' must be 3-63 lowercase letters, digits, dashes`

Azure blob containers can't have capital letters [docs/events.md#storage]. Use for example `user-photos`. Shall I rename it?""",

    139: """`environment` sets two variables for every function:
- `MAIL_FROM: noreply@example.com`: fine, not secret.
- `MAIL_API_KEY`: its real value is **written into the file**.

Validate is valid, because it only checks structure, not secrets. But it isn't all good: that key now sits in pskit.yml (and probably git), in Terraform state and in the Function App settings [docs/handlers.md#environment-variables].

Fix:
1. Use `MAIL_API_KEY: ${env:MAIL_API_KEY}` in pskit.yml.
2. Set the real value in your environment before deploying (**Setup & credentials** > Environment variables in studio).
3. Since this is prod and the key was in the file, rotate it with your mail provider.

Want me to make step 1?""",

    140: """pskit reads `events` as a list where **each item is one trigger with one key**. Your item has two keys, `http` and `schedule`, so validate fails:
`each event must be a single-key mapping such as `- http: {path: /hello}`; got {'http': 'POST /hooks', 'schedule': '1 hour'}`

Write two list items [docs/events.md]:
```yaml
events:
  - http: POST /hooks
  - schedule: 1 hour
```
Then `receiver` runs for `POST /hooks` and every hour. In the handler, `event.type` tells you which one (`http` or `schedule`). Want me to fix it?""",
}

for _c in CONVERSATIONS:
    _c["final"] = FINALS[int(_c["id"].split("-")[1])]
