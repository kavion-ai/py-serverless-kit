"""Category B (build / add), batch 14: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

SERVERS = json.dumps({"servers": {
    "app-1": {"host": "192.0.2.10", "user": "pskit", "port": 22},
    "app-2": {"host": "192.0.2.11", "user": "pskit", "port": 22},
    "app-3": {"host": "192.0.2.12", "user": "pskit", "port": 22},
    "gpu-box": {"host": "192.0.2.20", "user": "pskit", "port": 22}}}, indent=2)
CLUSTERS = json.dumps({"clusters": {"prod": {"orchestrator": "swarm", "master": "app-1", "servers": ["app-2", "app-3"]}}},
                      indent=2)


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", provider="onprem", **kw)


def yml(service, port, body, opts=""):
    return f"""service: {service}
provider:
  name: onprem
  region: local
  options:
    port: {port}
{opts}{body}"""


CONVERSATIONS = [
    # ------------------------------------------------------------------ 261
    B(261, stage="staging", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": yml("render", 8261, """functions:
  start-render:
    handler: app.render.start
  check-render:
    handler: app.render.check
  publish-video:
    handler: app.render.publish
"""),
          "app/__init__.py": "",
          "app/render.py": FUTURE + """

def start(event, ctx):
    data = dict(event.data or {})
    data["job_id"] = "job-" + str(data.get("video", "x"))
    data["polls"] = 0
    return data


def check(event, ctx):
    data = dict(event.data or {})
    data["polls"] = data.get("polls", 0) + 1
    data["status"] = "DONE" if data["polls"] >= 3 else "RUNNING"
    return data


def publish(event, ctx):
    return {"published": event.data.get("job_id")}
""",
          "requirements.txt": ""}),
      user="""Our Step Functions machine polled a render job: StartRender -> Wait 30s -> CheckRender -> Choice ($.status == "DONE" -> Publish, otherwise back to Wait). The three Lambdas are already here as functions. Rebuild the state machine as workflow `render-video`, with a 2 hour limit.""",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow wait choice states loop", docs=[D("docs/workflows.md", "state-types", words=200), D("docs/workflows.md", "choice-rules", words=120)]),
          S("propose_plan", steps=["Add workflow `render-video` (timeout 7200): start (task) -> wait (30 s) -> check (task) -> is-done (choice: $.status == DONE -> publish, default -> wait) -> publish (task, end)",
                                   "Validate (onprem, staging), invoke check-render"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.render-video",
            value={"start_at": "start", "timeout": 7200, "states": {
                "start": {"type": "task", "function": "start-render", "next": "wait"},
                "wait": {"type": "wait", "seconds": 30, "next": "check"},
                "check": {"type": "task", "function": "check-render", "next": "is-done"},
                "is-done": {"type": "choice", "choices": [{"variable": "$.status", "equals": "DONE", "next": "publish"}],
                          "default": "wait"},
                "publish": {"type": "task", "function": "publish-video", "end": True}}}),
          S("invoke_local", function="check-render", type="invoke", data={"job_id": "job-7", "polls": 2}),
      ],
      final="""Added `render-video`:

```yaml
workflows:
  render-video:
    start_at: start
    timeout: 7200
    states:
      start:   {type: task, function: start-render, next: wait}
      wait:    {type: wait, seconds: 30, next: check}
      check:   {type: task, function: check-render, next: is-done}
      is-done:
        type: choice
        choices: [{variable: $.status, equals: DONE, next: publish}]
        default: wait
      publish: {type: task, function: publish-video, end: true}
```

`default: wait` is the loop back, like your Choice's `Default`. `timeout: 7200` ends the run as `TIMED_OUT` after 2 hours. On premises the embedded engine runs it inside the host, so the waits are not limited by a function timeout [docs/workflows.md#embedded-orchestrator].

- `pskit validate` (onprem, staging): valid (embedded engine).
- `check-render` with `polls: 2`: returns `status: DONE`. The sample code reports DONE on the 3rd poll; put your real status call there.

Run it locally: `pskit workflow run render-video -i '{"video": 7}' --history`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 262
    B(262, stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/configuration.md#package"],
      project=dict(files={"pskit.yml": yml("invoicing", 8262, "functions: {}\n"), "requirements.txt": ""}),
      user="On Lambda we had a layer with `common/money.py` (a format_eur(cents) helper) shared by all functions. How does that work here? Add a function GET /invoices/{id}/total that uses it, total 129900 cents.",
      steps=[
          S("get_project"),
          S("search_docs", query="package source shared code folder bundle", docs=[D("docs/configuration.md", "package", end="| `requirements` |")]),
          S("propose_plan", steps=["Write `common/__init__.py` and `common/money.py` (format_eur)",
                                   "Write `app/invoices.py` that imports common.money; add `invoice-total` on GET /invoices/{id}/total",
                                   "Validate for onprem, invoke"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="common/__init__.py", content=""),
          S("write_file", path="common/money.py", content=FUTURE + """

def format_eur(cents: int) -> str:
    euros, rest = divmod(int(cents), 100)
    return f"{euros:,}.{rest:02d} EUR".replace(",", " ")
"""),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/invoices.py", content=FUTURE + """from common.money import format_eur


def total(event, ctx):
    invoice_id = event.http.path_params["id"]
    cents = 129900
    return {"invoice": invoice_id, "cents": cents, "total": format_eur(cents)}
"""),
          S("set_config", path="functions.invoice-total",
            value={"handler": "app.invoices.total", "events": [{"http": "GET /invoices/{id}/total"}]}),
          S("invoke_local", function="invoice-total", method="GET", path="/invoices/INV-9/total"),
      ],
      final="""No layer needed. pskit bundles every file under `package.source` (the project folder by default), so `common/` ships with every function and a plain `from common.money import format_eur` works [docs/configuration.md#package]. Its third-party packages go in the project's `requirements.txt`.

Added:
- `common/money.py` with `format_eur(cents)`.
- `invoice-total` on `GET /invoices/{id}/total`.

Checks:
- `pskit validate` (onprem): valid.
- `GET /invoices/INV-9/total`: 200 `{"invoice": "INV-9", "cents": 129900, "total": "1 299.00 EUR"}`.

Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 263
    B(263, stage="prod", mode="auto", page="Functions", persona="aws_migrator",
      sources=["docs/handlers.md#context", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": yml("archiver", 8263, "functions: {}\n"), "requirements.txt": ""}),
      user="nightly `archive-orders` at 02:30, timeout 600. like on Lambda: work in chunks of 100 and stop cleanly when <60s left (get_remaining_time_in_millis), report what's left",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/archive.py`: loop over chunks, stop when ctx.remaining_time_ms() < 60000 (None = no limit), return done/left",
                                   "Add `archive-orders` (timeout 600, schedule cron `30 2 * * *`)", "Validate, run the schedule"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/archive.py", content=FUTURE + """
CHUNK = 100


def archive(event, ctx):
    pending = list(range(1, 451))  # sample order ids
    done = 0
    while pending:
        left_ms = ctx.remaining_time_ms()
        if left_ms is not None and left_ms < 60_000:
            ctx.logger.warning("stopping early", extra={"left": len(pending)})
            break
        chunk, pending = pending[:CHUNK], pending[CHUNK:]
        done += len(chunk)
    return {"archived": done, "left": len(pending)}
"""),
          S("set_config", path="functions.archive-orders",
            value={"handler": "app.archive.archive", "timeout": 600, "events": [{"schedule": "30 2 * * *"}]}),
          S("invoke_local", function="archive-orders", type="schedule"),
      ],
      final="""Done:

```yaml
functions:
  archive-orders:
    handler: app.archive.archive
    timeout: 600
    events:
      - schedule: 30 2 * * *
```

`context.get_remaining_time_in_millis()` is `ctx.remaining_time_ms()` here [docs/handlers.md#context]. The job stops when less than 60 s are left and returns `archived` / `left`. A local `pskit invoke` has no deadline, so `remaining_time_ms()` can be `None`; the code treats that as "no limit".

- validate (onprem, prod): valid.
- schedule run with 450 sample ids: `{"archived": 450, "left": 0}`.

Difference from Lambda: the on-prem host does not kill the handler at `timeout`, but `remaining_time_ms()` still counts down from it [docs/providers.md#onprem-on-premises], so this check is what keeps the job inside 600 s. Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 264
    B(264, stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/configuration.md#variables", "docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": yml("inventory", 8264, """functions:
  stock:
    handler: app.stock.stock
    events:
    - http: GET /stock
"""),
          "app/__init__.py": "",
          "app/stock.py": FUTURE + """

def stock(event, ctx):
    host = ctx.env["DB_HOST"]
    return {"db_host": host, "items": []}
""",
          "requirements.txt": ""}),
      user="""Test page:

{"status": 500, "body": {"error": "Internal Server Error", "status": 500, "request_id": "..."}}

and in the log: KeyError: 'DB_HOST'

on the server DB_HOST must be db-1.example.com, on my laptop localhost. add it""",
      steps=[
          S("get_project"),
          S("search_docs", query="environment variable default value env", docs=[D("docs/configuration.md", "variables", end="| `${env:NAME, default}` | environment variable or `default` |")]),
          S("propose_plan", steps=["Add `functions.stock.environment.DB_HOST: ${env:DB_HOST, localhost}`",
                                   "Add `stages.prod.functions.stock.environment.DB_HOST: db-1.example.com`",
                                   "Validate for onprem and call GET /stock"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.stock.environment", value={"DB_HOST": "${env:DB_HOST, localhost}"}),
          S("set_config", path="stages.prod.functions.stock.environment", value={"DB_HOST": "db-1.example.com"}),
          S("invoke_local", function="stock", method="GET", path="/stock"),
      ],
      final="""Cause: the handler reads `ctx.env["DB_HOST"]`, but nothing set `DB_HOST`. Added:

```yaml
functions:
  stock:
    environment:
      DB_HOST: ${env:DB_HOST, localhost}
stages:
  prod:
    functions:
      stock:
        environment: {DB_HOST: db-1.example.com}
```

- Your laptop (dev): `DB_HOST` from your shell if it is set, otherwise `localhost` [docs/configuration.md#variables].
- `-s prod` (the server): always `db-1.example.com`.

Checks:
- `pskit validate` (onprem, dev): valid.
- `GET /stock`: 200 `{"db_host": "localhost", "items": []}`.

Run it again on **Test > ▶ Run locally**. Deploy the server with `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 265
    B(265, stage="staging", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#troubleshooting", "docs/resource-guides/onprem/queue.md#redis-valkey"],
      project=dict(files={
          "pskit.yml": yml("jobs", 8265, """functions:
  worker:
    handler: app.jobs.work
    events:
    - queue: {resource: jobs, batch_size: 10}
"""),
          "app/__init__.py": "",
          "app/jobs.py": FUTURE + """

def work(event, ctx):
    return {"done": len(event.records)}
""",
          "requirements.txt": ""}),
      user="""validate says

Error: pskit.yml is invalid:
  - <root>: Value error, function 'worker' uses unknown resource 'jobs'; known: <none>

jobs is the redis list `jobs` on redis-1.example.com, the URL with the password is in JOBS_REDIS_URL on the host""",
      steps=[
          S("get_validation"),
          S("search_docs", query="redis queue resource url_env key", docs=[D("docs/resource-guides/onprem/queue.md", "redis-valkey", start="### 3. Declare it", words=110)]),
          S("propose_plan", steps=["Add resources.jobs: {type: queue, external: true, options: {driver: redis, url_env: JOBS_REDIS_URL, key: jobs}}",
                                   "Validate (onprem, staging), invoke worker"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.jobs",
            value={"type": "queue", "external": True, "options": {"driver": "redis", "url_env": "JOBS_REDIS_URL", "key": "jobs"}}),
          S("invoke_local", function="worker", type="queue", data=[{"id": 1}]),
      ],
      final="""The trigger names `resource: jobs`, but `resources:` had no `jobs` [docs/resources.md#troubleshooting]. Added:

```yaml
resources:
  jobs:
    type: queue
    external: true
    options: {driver: redis, url_env: JOBS_REDIS_URL, key: jobs}
```

`url_env` makes the host read the URL (with the password) from `JOBS_REDIS_URL` when it starts. It is not written into pskit files. If the variable is missing, the host stops with an error naming it.

- `pskit validate` (onprem, staging): valid.
- invoke with one message: `{"done": 1}`.

Deploy: **Deploy** page or `pskit deploy -s staging`. Then `LPUSH jobs '{"id": 2}'` from redis-cli, or `pskit resources send jobs`."""),

    # ------------------------------------------------------------------ 266
    B(266, stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": yml("items", 8266, """functions:
  list-items:
    handler: app.items.list_items
    events:
    - http: GET /items
""", "    host: 0.0.0.0\n"),
          "app/__init__.py": "",
          "app/items.py": FUTURE + """
ITEMS = {"41": {"id": "41", "name": "lamp"}, "42": {"id": "42", "name": "desk"}}


def list_items(event, ctx):
    return {"items": list(ITEMS.values())}
""",
          "requirements.txt": ""}),
      user="""$ curl -i http://192.0.2.10:8266/items/42
HTTP/1.1 404 Not Found
{"error": "Not Found", "status": 404}

the list works. I need the single item too""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `get_item` in app/items.py (NotFound for unknown ids)",
                                   "Add function `get-item` on GET /items/{id}", "Validate (onprem, prod), invoke /items/42"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/items.py", content=FUTURE + """from py_serverless_kit import NotFound

ITEMS = {"41": {"id": "41", "name": "lamp"}, "42": {"id": "42", "name": "desk"}}


def list_items(event, ctx):
    return {"items": list(ITEMS.values())}


def get_item(event, ctx):
    item = ITEMS.get(event.http.path_params["id"])
    if item is None:
        raise NotFound("no such item")
    return item
"""),
          S("set_config", path="functions.get-item",
            value={"handler": "app.items.get_item", "events": [{"http": "GET /items/{id}"}]}),
          S("invoke_local", function="get-item", method="GET", path="/items/42"),
      ],
      final="""That 404 is the router: only `GET /items` existed, so `/items/42` matched no route. Added `get-item` on `GET /items/{id}` [docs/events.md#http]. An unknown id gives its own 404, "no such item".

- `pskit validate` (onprem, prod): valid.
- `GET /items/42`: 200 `{"id": "42", "name": "desk"}`.

The server keeps the old version until you deploy: **Deploy** page (type the confirmation) or `pskit deploy -s prod`. Then run your curl again."""),

    # ------------------------------------------------------------------ 267
    B(267, stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md"],
      project=dict(files={
          "pskit.yml": yml("claims", 8267, """functions:
  receive-claim:
    handler: app.claims.receive
    events:
    - queue: {name: claims, batch_size: 1}
  score-claim:
    handler: app.claims.score
  open-case:
    handler: app.claims.open_case
"""),
          "app/__init__.py": "",
          "app/claims.py": FUTURE + """

def receive(event, ctx):
    claim = event.records[0].json(default={}) if event.records else dict(event.data or {})
    return {"claim_id": claim.get("claim_id"), "amount": claim.get("amount", 0)}


def score(event, ctx):
    data = dict(event.data or {})
    data["score"] = 90 if data.get("amount", 0) > 1000 else 20
    return data


def open_case(event, ctx):
    return {"case": f"CASE-{event.data.get('claim_id')}", "score": event.data.get("score")}
""",
          "requirements.txt": ""}),
      user="Every message on the built-in queue `claims` should become one tracked run: receive-claim -> score-claim -> open-case, visible on the Workflows page. receive-claim already consumes the queue with batch 1. I don't want an extra starter function.",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow starts when first task function runs queue on premises",
            docs=[D("docs/workflows.md", "embedded-orchestrator", start="- On premises, a workflow whose first state is a `task`", end="Set `options.start_on_entry: false` to turn this off.")]),
          S("propose_plan", steps=["Add workflow `handle-claim`: receive (task receive-claim) -> score (task score-claim) -> open (task open-case, end)",
                                   "Validate (onprem, staging), invoke receive-claim with one message"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.handle-claim",
            value={"start_at": "receive", "states": {
                "receive": {"type": "task", "function": "receive-claim", "next": "score"},
                "score": {"type": "task", "function": "score-claim", "next": "open"},
                "open": {"type": "task", "function": "open-case", "end": True}}}),
          S("invoke_local", function="receive-claim", type="queue", data=[{"claim_id": "C-55", "amount": 1500}]),
      ],
      final="""Added `handle-claim` with `receive-claim` as its first state:

```yaml
workflows:
  handle-claim:
    start_at: receive
    states:
      receive: {type: task, function: receive-claim, next: score}
      score:   {type: task, function: score-claim, next: open}
      open:    {type: task, function: open-case, end: true}
```

On premises, a workflow whose first state is a task also starts when that function runs on its own, here from the queue. The call's result is used as the first state's result, so `receive-claim` does not run twice. A failed call starts nothing [docs/workflows.md#embedded-orchestrator].

- `pskit validate` (onprem, staging): valid (embedded engine).
- `receive-claim` with one message: `{"claim_id": "C-55", "amount": 1500}`.

`pskit invoke` runs only the function. The automatic start happens in the deployed host. After `pskit deploy -s staging`, each message shows up as a run on **Workflows**. Locally: `pskit workflow run handle-claim -i '{"claim_id": "C-55", "amount": 1500}' --history`."""),

    # ------------------------------------------------------------------ 268
    B(268, stage="prod", mode="auto", page="Cluster", persona="terse_expert",
      sources=["docs/cluster.md#load-balancer-one-url-for-the-whole-cluster-optional"],
      project=dict(files={
          "pskit.yml": yml("billing", 8268, """functions:
  api:
    handler: app.billing.api
    events:
    - http: GET /
""", "    host: 0.0.0.0\n    cluster: prod\n"),
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """

def api(event, ctx):
    return {"billing": "ok"}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="shop already has port 80 on prod's cluster balancer. billing: own balancer port 8081, 2 replicas",
      steps=[
          S("get_project"),
          S("search_docs", query="several deployments one cluster balancer_port",
            docs=[D("docs/cluster.md", "load-balancer-one-url-for-the-whole-cluster-optional", start="**Several deployments on one cluster**", end="cluster: {name: prod, replicas: 3, balancer_port: 8081}")]),
          S("propose_plan", steps=["provider.options.cluster: {name: prod, replicas: 2, balancer_port: 8081}", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.cluster", value={"name": "prod", "replicas": 2, "balancer_port": 8081}),
      ],
      final="""Set:

```yaml
provider:
  options:
    cluster: {name: prod, replicas: 2, balancer_port: 8081}
```

Each deployment on the cluster balancer needs its own port. The first one takes 80, and the deploy stops with a hint when two would share one [docs/cluster.md#load-balancer-one-url-for-the-whole-cluster-optional].

validate (onprem, prod): valid.

`pskit deploy -s prod`, then billing is at `http://<lb>:8081`. Open 8081 on the load balancer server. Check with `pskit cluster status prod`."""),

    # ------------------------------------------------------------------ 269
    B(269, stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/placement.md", "docs/onprem-network.md#4-functions-on-several-servers-provideroptionsplacement"],
      project=dict(files={
          "pskit.yml": yml("vision", 8269, """functions:
  api:
    handler: app.vision.api
    events:
    - http: POST /detect
  detect:
    handler: app.vision.detect
""", """    host: 0.0.0.0
    placement:
      default: web
      groups:
        web: {server: app-1}
        gpu: {server: gpu-box, functions: [detect]}
"""),
          "app/__init__.py": "",
          "app/vision.py": FUTURE + """from py_serverless_kit import invoke


def api(event, ctx):
    return invoke("detect", event.http.json(default={}) or {})


def detect(event, ctx):
    return {"objects": ["cat"], "image": (event.data or {}).get("image")}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="gpu-box is in other building behind NAT. app-1 cannot reach 192.0.2.20, only http://gpu.example.com:9090 (port forward to gpu-box port 8290). invoke from api to detect must go there",
      steps=[
          S("get_project"),
          S("search_docs", query="placement group advertise port",
            docs=[D("docs/placement.md", "functions-on-several-servers-on-premises", start="Per group: one of `server`", end="when the server's own address is not reachable).")]),
          S("propose_plan", steps=["placement.groups.gpu: add port 8290 and advertise http://gpu.example.com:9090",
                                   "Validate (onprem, prod), invoke api"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.gpu",
            value={"server": "gpu-box", "functions": ["detect"], "port": 8290, "advertise": "http://gpu.example.com:9090"}),
          S("invoke_local", function="api", method="POST", path="/detect", data={"image": "cam1.jpg"}),
      ],
      final="""Done:

```yaml
provider:
  options:
    placement:
      default: web
      groups:
        web: {server: app-1}
        gpu: {server: gpu-box, functions: [detect], port: 8290, advertise: "http://gpu.example.com:9090"}
```

- `port: 8290`: the host on gpu-box listens there (your port forward target).
- `advertise`: the URL the other groups call when the server's own address can't be reached [docs/placement.md]. `invoke("detect", ...)` from `api` on app-1 now goes to `http://gpu.example.com:9090`.

Checks:
- `pskit validate` (onprem, prod): valid.
- Local `POST /detect`: 200 `{"objects": ["cat"], "image": "cam1.jpg"}`. Locally both run in one process, so this tests the code, not the network path.

Two warnings are still there, unrelated to this change:
- the servers must already have python3.12 on PATH, or add `deploy.python: bundle`;
- `api` and `detect` share `app/vision.py`, so each server gets a copy. `pskit function split api detect` gives each its own folder and requirements.txt.

The groups also send logs to the default group, so gpu-box must reach app-1 on port 8269 [docs/onprem-network.md#4-functions-on-several-servers-provideroptionsplacement]. Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 270
    B(270, stage="staging", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#storage-drivers", "docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": yml("media-sync", 8270, "functions: {}\n"), "requirements.txt": ""}),
      user="Our S3 bucket `acme-media-prod` (eu-central-1) stays in AWS. A function on our own server should run for every new object under `uploads/`. Use an IAM user's keys from MEDIA_AWS_KEY_ID / MEDIA_AWS_SECRET on the host.",
      steps=[
          S("get_project"),
          S("search_docs", query="s3 storage driver aws bucket region prefix",
            docs=[D("docs/resources.md", "storage-drivers", start="| `s3` |", end="| `s3` |"),
                  D("docs/resources.md", "storage-drivers", start="Every storage driver lists the bucket", end="On a large bucket, always set `prefix`.")]),
          S("propose_plan", steps=["resources.media: storage, external, options {driver: s3, bucket: acme-media-prod, region: eu-central-1, prefix: uploads/, access_key_env, secret_key_env}",
                                   "Write `app/media.py`; add `on-upload` with storage {resource: media, events: [created]}",
                                   "Validate (onprem, staging), invoke"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.media",
            value={"type": "storage", "external": True,
                   "options": {"driver": "s3", "bucket": "acme-media-prod", "region": "eu-central-1", "prefix": "uploads/",
                               "access_key_env": "MEDIA_AWS_KEY_ID", "secret_key_env": "MEDIA_AWS_SECRET"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/media.py", content=FUTURE + """

def on_upload(event, ctx):
    for record in event.records:
        ctx.logger.info("new object", extra={"key": record.key, "size": record.size})
    return {"seen": [r.key for r in event.records]}
"""),
          S("set_config", path="functions.on-upload",
            value={"handler": "app.media.on_upload", "events": [{"storage": {"resource": "media", "events": ["created"]}}]}),
          S("invoke_local", function="on-upload", type="storage", data=[{"key": "photo-1.jpg", "size": 51200}]),
      ],
      final="""Done:

```yaml
resources:
  media:
    type: storage
    external: true
    options: {driver: s3, bucket: acme-media-prod, region: eu-central-1, prefix: uploads/,
              access_key_env: MEDIA_AWS_KEY_ID, secret_key_env: MEDIA_AWS_SECRET}
functions:
  on-upload:
    handler: app.media.on_upload
    events:
      - storage: {resource: media, events: [created]}
```

How it differs from an S3 notification: the host lists the bucket every `poll_seconds` and diffs it. A new ETag is `created`, objects already there at first start are not emitted, and `prefix` is stripped from `record.key` [docs/resources.md#storage-drivers]. Keep the prefix, because every poll lists everything under it. The IAM user needs `s3:ListBucket` (and `s3:GetObject` to read objects).

- validate (onprem, staging): valid.
- invoke with `photo-1.jpg`: `{"seen": ["photo-1.jpg"]}`.

Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 271
    B(271, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/handlers.md#returning-a-response"],
      project=dict(files={"pskit.yml": yml("gateway", 8271, "functions: {}\n"), "requirements.txt": ""}),
      user="we move our old app slowly to pskit. until then, everything under /legacy/... should just go to the old app at http://legacy.example.com and give back its answer",
      steps=[
          S("get_project"),
          S("search_docs", query="greedy path parameter any method", docs=[D("docs/events.md", "http", start="**Path templates**", end="Parameter names are identifiers")]),
          S("propose_plan", steps=["Write `app/legacy.py`: forward method, sub-path, query and body to LEGACY_URL with urllib; return its status, content type and body; 502 when it can't be reached",
                                   "Add `legacy` on ANY /legacy/{path+} with LEGACY_URL=http://legacy.example.com",
                                   "Validate for onprem and try one request"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/legacy.py", content=FUTURE + """import urllib.error
import urllib.parse
import urllib.request

from py_serverless_kit import Response


def legacy(event, ctx):
    req = event.http
    url = ctx.env["LEGACY_URL"].rstrip("/") + "/" + req.path_params.get("path", "")
    if req.query:
        url += "?" + urllib.parse.urlencode(req.query)
    body = req.body if req.method not in ("GET", "HEAD") else None
    if isinstance(body, str):
        body = body.encode("utf-8")
    forward = urllib.request.Request(url, data=body or None, method=req.method,
                                     headers={"Content-Type": req.content_type or "application/octet-stream"})
    try:
        with urllib.request.urlopen(forward, timeout=10) as resp:
            return Response(body=resp.read(), status=resp.status,
                            headers={"Content-Type": resp.headers.get("Content-Type", "text/plain")})
    except urllib.error.HTTPError as exc:
        return Response(body=exc.read(), status=exc.code,
                        headers={"Content-Type": exc.headers.get("Content-Type", "text/plain")})
    except OSError as exc:
        ctx.logger.warning("legacy app unreachable", extra={"error": str(exc)})
        return {"error": "legacy app unreachable"}, 502
"""),
          S("set_config", path="functions.legacy",
            value={"handler": "app.legacy.legacy", "environment": {"LEGACY_URL": "http://legacy.example.com"},
                   "events": [{"http": "ANY /legacy/{path+}"}]}),
          S("invoke_local", function="legacy", method="GET", path="/legacy/reports/2026"),
      ],
      final="""Done. `ANY /legacy/{path+}` catches every method and every path below `/legacy/` [docs/events.md#http]. `legacy` sends the request to `LEGACY_URL` with the same method, sub-path, query and body, and returns the old app's status, content type and body. When the old app can't be reached, it answers **502**.

Checks:
- `pskit validate` (onprem): valid.
- `GET /legacy/reports/2026` from this computer: **502** `{"error": "legacy app unreachable"}`. `legacy.example.com` is not reachable from here, so this was the error path; on your network it returns the old app's answer.

Limits: request headers other than Content-Type are not passed on, and every call waits for the old app (10 s timeout). Each time you move a page to pskit, add its own route; the specific route wins over `{path+}`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 272
    B(272, stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resource-guides/onprem/queue.md", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": yml("exports", 8272, "functions: {}\n"), "requirements.txt": ""}),
      user="Our legacy ERP drops export jobs into a pskit-style queue folder on the NAS, mounted on the server at /mnt/nas/queues/exports. pskit must not create that folder. A function `run-export` should consume it 5 at a time.",
      steps=[
          S("get_project"),
          S("search_docs", query="queue directory driver shared folder path",
            docs=[D("docs/resource-guides/onprem/queue.md", "built-in-queue", start="Use a shared folder", end="`external: true`.")]),
          S("propose_plan", steps=["resources.exports: {type: queue, external: true, options: {driver: directory, path: /mnt/nas/queues/exports}}",
                                   "Write `app/exports.py`; add `run-export` on queue {resource: exports, batch_size: 5}",
                                   "Validate (onprem, prod), invoke"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.exports",
            value={"type": "queue", "external": True, "options": {"driver": "directory", "path": "/mnt/nas/queues/exports"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/exports.py", content=FUTURE + """

def run_export(event, ctx):
    for record in event.records:
        job = record.json(default={}) or {}
        ctx.logger.info("export", extra={"job": job.get("job")})
    return {"exported": len(event.records)}
"""),
          S("set_config", path="functions.run-export",
            value={"handler": "app.exports.run_export", "events": [{"queue": {"resource": "exports", "batch_size": 5}}]}),
          S("invoke_local", function="run-export", type="queue", data=[{"job": "customers-2026-11"}]),
      ],
      final="""Done:

```yaml
resources:
  exports:
    type: queue
    external: true
    options: {driver: directory, path: /mnt/nas/queues/exports}
functions:
  run-export:
    handler: app.exports.run_export
    events:
      - queue: {resource: exports, batch_size: 5}
```

`driver: directory` with `external: true` uses that existing folder instead of one under `data_dir` [docs/resource-guides/onprem/queue.md]. pskit never creates or deletes an external resource.

- `pskit validate` (onprem, prod): valid.
- invoke with one job: `{"exported": 1}`.

The ERP must write messages in the host's queue format (one JSON file per message). If it can POST HTTP instead, `POST /__pskit/queues/exports` is simpler [docs/providers.md#onprem-on-premises]. The host user needs read/write access on the NAS mount. Deploy: **Deploy** page or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 273
    B(273, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={"pskit.yml": yml("welcome", 8273, "functions: {}\n"), "requirements.txt": ""}),
      user="GET /welcome must say hello in the language of the browser (accept-language header). de, fr, es, else english",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/welcome.py`: read event.http.headers accept-language, first 2 letters, pick the greeting",
                                   "Add function `welcome` on GET /welcome", "Validate for onprem, invoke"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/welcome.py", content=FUTURE + """
GREETINGS = {"de": "Hallo!", "fr": "Bonjour !", "es": "¡Hola!", "en": "Hello!"}


def welcome(event, ctx):
    header = event.http.headers.get("accept-language", "")
    lang = header.split(",")[0].strip()[:2].lower()
    if lang not in GREETINGS:
        lang = "en"
    return {"lang": lang, "message": GREETINGS[lang]}
"""),
          S("set_config", path="functions.welcome", value={"handler": "app.welcome.welcome", "events": [{"http": "GET /welcome"}]}),
          S("invoke_local", function="welcome", method="GET", path="/welcome"),
      ],
      final="""Done. `GET /welcome` reads `Accept-Language` (headers are case-insensitive [docs/handlers.md#httprequest]) and uses its first language: `de`, `fr` and `es` get their greeting, anything else gets English.

- `pskit validate` (onprem): valid.
- Test without the header: 200 `{"lang": "en", "message": "Hello!"}`.

Test German: `pskit invoke -f welcome --method GET --path /welcome -H "Accept-Language: de-DE,de;q=0.9"` should give `"Hallo!"`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 274
    B(274, stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: cart-js
provider:
  name: onprem
  region: local
  runtime: nodejs20
  options:
    port: 8274
functions:
  price:
    handler: src.cart.price
""",
          "src/cart.js": """exports.price = async (event) => {
  const items = (event.data && event.data.items) || [];
  return { total: items.reduce((sum, i) => sum + i.qty * i.unit, 0) };
};
""",
          "package.json": json.dumps({"name": "cart-js", "version": "1.0.0", "private": True}, indent=2) + "\n"}),
      user="js: POST /checkout {items} -> invoke('price'), reply {total, currency: EUR}. 400 if items empty",
      steps=[
          S("read_file", path="src/cart.js"),
          S("propose_plan", steps=["Add `checkout` to src/cart.js: BadRequest on empty items, await invoke('price', {items})",
                                   "Add function `checkout` on POST /checkout", "Validate, invoke"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/cart.js", content="""const { BadRequest, invoke } = require("pskit");

exports.price = async (event) => {
  const items = (event.data && event.data.items) || [];
  return { total: items.reduce((sum, i) => sum + i.qty * i.unit, 0) };
};

exports.checkout = async (event) => {
  const body = event.http.json() || {};
  if (!Array.isArray(body.items) || body.items.length === 0) {
    throw new BadRequest("items must be a non-empty list");
  }
  const { total } = await invoke("price", { items: body.items });
  return { total, currency: "EUR" };
};
"""),
          S("set_config", path="functions.checkout", value={"handler": "src.cart.checkout", "events": [{"http": "POST /checkout"}]}),
          S("invoke_local", function="checkout", method="POST", path="/checkout", data={"items": [{"qty": 2, "unit": 4.5}, {"qty": 1, "unit": 10}]}),
      ],
      final="""Done:

```yaml
functions:
  checkout:
    handler: src.cart.checkout
    events:
      - http: POST /checkout
```

`checkout` awaits `invoke("price", {items})` and throws `BadRequest` (400) for an empty list [docs/nodejs.md#handlers].

- validate (onprem): valid.
- `POST /checkout` with 2 x 4.5 + 1 x 10: 200 `{"total": 19, "currency": "EUR"}`.

Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 275
    B(275, stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resource-guides/onprem/services.md", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": yml("digest", 8275, """resources:
  mailpit:
    type: custom
    external: true
    connection: {host: 127.0.0.1, port: 1025, web_url: "http://127.0.0.1:8025"}
functions: {}
"""),
          "requirements.txt": ""}),
      user="i made Mailpit with one click to test emails. now i want a weekly mail every monday 8:00 'your weekly digest' to team@example.com, sent through that mailpit",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/digest.py`: build the mail with email.message and send it with smtplib to the mailpit host/port from resource('mailpit')",
                                   "Add `weekly-digest` with schedule cron `0 8 * * 1`",
                                   "Validate for onprem, run it once"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/digest.py", content=FUTURE + """import smtplib
from email.message import EmailMessage

from py_serverless_kit import resource


def weekly_digest(event, ctx):
    smtp = resource("mailpit")
    msg = EmailMessage()
    msg["From"] = "digest@example.com"
    msg["To"] = "team@example.com"
    msg["Subject"] = "your weekly digest"
    msg.set_content("Here is what happened this week.")
    try:
        with smtplib.SMTP(smtp["host"], int(smtp["port"]), timeout=5) as client:
            client.send_message(msg)
    except OSError as exc:
        ctx.logger.warning("mail not sent", extra={"error": str(exc)})
        return {"sent": False}
    return {"sent": True}
"""),
          S("set_config", path="functions.weekly-digest",
            value={"handler": "app.digest.weekly_digest", "events": [{"schedule": "0 8 * * 1"}]}),
          S("invoke_local", function="weekly-digest", type="schedule"),
      ],
      final="""Done. `weekly-digest` runs every Monday at 08:00 (UTC) and sends "your weekly digest" to team@example.com through Mailpit. Host and port come from `resource("mailpit")` [docs/resources.md#runtime-api].

- `pskit validate` (onprem): valid.
- One run now: `{"sent": false}`, with the warning "mail not sent". Mailpit was not running on port 1025 for this test. Start it, run `pskit invoke -f weekly-digest -t schedule` again, and the mail should appear in the Mailpit inbox at http://127.0.0.1:8025.

Mailpit catches mail and never delivers it, so nobody really gets it. Before going live, point the function at a real mail relay. For 08:00 local time instead of UTC, add `timezone`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 276
    B(276, stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/nodejs.md", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: reminders-js
provider:
  name: onprem
  region: local
  runtime: nodejs22
  options:
    port: 8276
functions: {}
""",
          "package.json": json.dumps({"name": "reminders-js", "version": "1.0.0", "private": True}, indent=2) + "\n"}),
      user="js function standup-reminder every workday 9:45 vienna time, just log 'standup in 15 min'",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `src/reminder.js` (ctx.logger.info)",
                                   "Add `standup-reminder`: schedule {cron: '45 9 * * 1-5', timezone: Europe/Vienna}",
                                   "Validate, run once"]),
          S("write_file", path="src/reminder.js", content="""exports.standup = async (event, ctx) => {
  ctx.logger.info("standup in 15 min");
  return { reminded: true };
};
"""),
          S("set_config", path="functions.standup-reminder",
            value={"handler": "src.reminder.standup",
                   "events": [{"schedule": {"cron": "45 9 * * 1-5", "timezone": "Europe/Vienna"}}]}),
          S("invoke_local", function="standup-reminder", type="schedule"),
      ],
      final="""Done:

```yaml
functions:
  standup-reminder:
    handler: src.reminder.standup
    events:
      - schedule: {cron: "45 9 * * 1-5", timezone: Europe/Vienna}
```

`1-5` = Monday to Friday, 09:45 Vienna time [docs/events.md#schedule].

- validate (onprem): valid, with one warning: this computer has no timezone database, so here the schedule is evaluated in UTC. `pskit deploy` adds `tzdata`, so the deployed host uses Vienna time.
- run once: `{"reminded": true}`, and "standup in 15 min" is in the log.

Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 277
    B(277, stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": yml("crm", 8277, """functions:
  api:
    handler: app.crm.api
    events:
    - http: GET /
""", """    host: 0.0.0.0
    deploy:
      server: app-1
      path: /opt/pskit/crm
      python: bundle
"""),
          "app/__init__.py": "",
          "app/crm.py": FUTURE + """

def api(event, ctx):
    return {"crm": ctx.stage}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="Staging and prod both run on app-1. Prod already uses port 8277 and /opt/pskit/crm. Give staging its own port 8377 and folder /opt/pskit/crm-staging so the two never collide; prod stays exactly as it is.",
      steps=[
          S("get_project"),
          S("search_docs", query="per stage override provider options port", docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["Add stages.staging.provider.options: {port: 8377, deploy: {path: /opt/pskit/crm-staging}}",
                                   "Validate for staging and prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.staging.provider.options", value={"port": 8377, "deploy": {"path": "/opt/pskit/crm-staging"}}),
          S("invoke_local", function="api", method="GET", path="/"),
      ],
      final="""Done:

```yaml
stages:
  staging:
    provider:
      options:
        port: 8377
        deploy: {path: /opt/pskit/crm-staging}
```

The block is deep-merged, so staging keeps `server: app-1` and `python: bundle` and changes only the port and folder [docs/configuration.md#stages-per-stage-overrides]. Prod is unchanged: 8277 and `/opt/pskit/crm`. Each stage also has its own Terraform state, unit and data.

- `pskit validate` (onprem, staging): valid.
- Local `GET /`: 200 `{"crm": "staging"}`.

Open TCP 8377 on app-1 for whoever tests staging. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 278
    B(278, stage="prod", mode="ask", page="Network map", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises", "docs/onprem-network.md"],
      project=dict(files={
          "pskit.yml": yml("hr", 8278, """functions:
  api:
    handler: app.hr.api
    events:
    - http: GET /
""", """    host: 0.0.0.0
    deploy:
      server: app-1
      path: /opt/pskit/hr
      python: bundle
"""),
          "app/__init__.py": "",
          "app/hr.py": FUTURE + """

def api(event, ctx):
    return {"hr": "ok"}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="""pskit firewall --server app-1 says

  app-1 (192.0.2.10)
    [REQUIRED] inbound  TCP 8278  from users  - hr: HTTP routes

app-1 also has a public interface. hr must listen ONLY on the office LAN address 192.0.2.10, not on everything""",
      steps=[
          S("get_project"),
          S("search_docs", query="host bind address on the target", docs=[D("docs/providers.md", "onprem-on-premises", start="`options.host` is the bind address", end="`options.host` is the bind address")]),
          S("propose_plan", steps=["Set provider.options.host: 192.0.2.10 (instead of 0.0.0.0)", "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.host", value="192.0.2.10"),
      ],
      final="""Done: `provider.options.host: 192.0.2.10`. `host` is the bind address on the target. With a specific IP, the host listens only on that interface, so the public interface doesn't answer on 8278 [docs/providers.md#onprem-on-premises].

`pskit validate` (onprem, prod): valid.

Keep the firewall rule as well: allow TCP 8278 only from the office network. Deploy: **Deploy** page or `pskit deploy -s prod`. Then `curl http://192.0.2.10:8278/` from the LAN should answer, and the public address should not."""),

    # ------------------------------------------------------------------ 279
    B(279, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": yml("todos", 8279, """functions:
  list-todos:
    handler: app.todos.list_todos
    events:
    - http: GET /todos
"""),
          "app/__init__.py": "",
          "app/todos.py": FUTURE + """
TODOS = {"1": {"id": "1", "title": "buy milk"}, "2": {"id": "2", "title": "call bob"}}


def list_todos(event, ctx):
    return {"todos": list(TODOS.values())}
""",
          "requirements.txt": ""}),
      user="how can i delete a todo? i want DELETE /todos/1 and then it is gone. it should not send anything back",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `delete_todo` in app/todos.py: remove the id, NotFound if missing, return None (204 No Content)",
                                   "Add function `delete-todo` on DELETE /todos/{id}", "Validate for onprem and delete todo 1"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/todos.py", content=FUTURE + """from py_serverless_kit import NotFound

TODOS = {"1": {"id": "1", "title": "buy milk"}, "2": {"id": "2", "title": "call bob"}}


def list_todos(event, ctx):
    return {"todos": list(TODOS.values())}


def delete_todo(event, ctx):
    todo_id = event.http.path_params["id"]
    if TODOS.pop(todo_id, None) is None:
        raise NotFound(f"todo {todo_id} not found")
    return None
"""),
          S("set_config", path="functions.delete-todo",
            value={"handler": "app.todos.delete_todo", "events": [{"http": "DELETE /todos/{id}"}]}),
          S("invoke_local", function="delete-todo", method="DELETE", path="/todos/1"),
      ],
      final="""Done. `DELETE /todos/{id}` removes the todo and answers **204 No Content**: returning `None` from a handler means "nothing to send back" [docs/handlers.md#returning-a-response]. An id that doesn't exist gets 404.

- `pskit validate` (onprem): valid.
- `DELETE /todos/1`: 204, empty body.

The todos are kept in memory (sample data), so a deleted todo comes back after a restart, and each server has its own list. For real use, keep them in a database. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 280
    B(280, stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#topic", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": yml("audit", 8280, "functions: {}\n"), "requirements.txt": ""}),
      user="On AWS an EventBridge rule matched detail-type `UserDeleted` from source `app.users` and called a Lambda that wrote an audit line. Here our services publish to the built-in topic `domain-events` with attributes `source` and `type`. Give me `audit-user-deleted` for exactly those.",
      steps=[
          S("get_project"),
          S("search_docs", query="topic filter attributes exact match on premises",
            docs=[D("docs/providers.md", "onprem-on-premises", start="| topic |", end="| topic |")]),
          S("propose_plan", steps=["Write `app/audit.py`: log user id and the record attributes",
                                   "Add `audit-user-deleted` with topic {name: domain-events, filter: {source: [app.users], type: [UserDeleted]}}",
                                   "Validate (onprem, prod), invoke with one event"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/audit.py", content=FUTURE + """

def audit(event, ctx):
    for record in event.records:
        body = record.json(default={}) or {}
        ctx.logger.info("audit user deleted", extra={"user_id": body.get("user_id"), "attributes": record.attributes})
    return {"audited": len(event.records)}
"""),
          S("set_config", path="functions.audit-user-deleted",
            value={"handler": "app.audit.audit",
                   "events": [{"topic": {"name": "domain-events", "filter": {"source": ["app.users"], "type": ["UserDeleted"]}}}]}),
          S("invoke_local", function="audit-user-deleted", type="topic", data=[{"user_id": "u-42"}]),
      ],
      final="""Done:

```yaml
functions:
  audit-user-deleted:
    handler: app.audit.audit
    events:
      - topic:
          name: domain-events
          filter: {source: [app.users], type: [UserDeleted]}
```

The rule's `source` / `detail-type` become a topic `filter`. On premises the filter is an exact match on message attributes first, then on JSON body fields [docs/providers.md#onprem-on-premises], so other events on `domain-events` don't call this function.

- `pskit validate` (onprem, prod): valid.
- invoke with `{"user_id": "u-42"}`: `{"audited": 1}`.

Publishers send `POST /__pskit/topics/domain-events` with `{"message": {...}, "attributes": {"source": "app.users", "type": "UserDeleted"}}`. Deploy: `pskit deploy -s prod`."""),
]
