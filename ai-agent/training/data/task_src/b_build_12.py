"""Category B (build / add), batch 12: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

SERVERS = json.dumps({"servers": {
    "app-1": {"host": "192.0.2.10", "user": "pskit", "port": 22},
    "app-2": {"host": "192.0.2.11", "user": "pskit", "port": 22},
    "app-3": {"host": "192.0.2.12", "user": "pskit", "port": 22}}}, indent=2)
CLUSTERS = json.dumps({"clusters": {"prod": {"orchestrator": "swarm", "master": "app-1", "servers": ["app-2", "app-3"]}}},
                      indent=2)


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", provider="onprem", **kw)


def empty(service, port, extra=""):
    return f"""service: {service}
provider:
  name: onprem
  region: local
  options:
    port: {port}
{extra}functions: {{}}
"""


CONVERSATIONS = [
    # ------------------------------------------------------------------ 221
    B(221, stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing",
               "docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition"],
      project=dict(files={"pskit.yml": empty("users", 8221), "requirements.txt": ""}),
      user="""I have this from our Serverless Framework project and want it on our own server instead of Lambda:

```yaml
functions:
  getUser:
    handler: handler.get_user
    events:
      - httpApi: {path: /users/{id}, method: get}
```

```python
def get_user(event, context):
    uid = event["pathParameters"]["id"]
    user = USERS.get(uid)
    if not user:
        return {"statusCode": 404, "body": json.dumps({"error": "not found"})}
    return {"statusCode": 200, "body": json.dumps(user)}
```""",
      steps=[
          S("get_project"),
          S("search_docs", query="migrate lambda handler pathParameters statusCode",
            docs=[D("docs/migrating-from-aws.md", "step-1-separate-business-logic-from-aws-event-parsing",
                    start="| Lambda | pskit |", end="| `{\"statusCode\", \"headers\", \"body\"}` |")]),
          S("propose_plan", steps=["Write `app/users.py`: path_params instead of pathParameters, return the dict, raise NotFound",
                                   "Add function `get-user` on GET /users/{id}",
                                   "Validate for onprem, invoke /users/1 and /users/9"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/users.py", content=FUTURE + """from py_serverless_kit import NotFound

USERS = {"1": {"id": "1", "name": "Ada"}}


def get_user(event, ctx):
    uid = event.http.path_params["id"]
    user = USERS.get(uid)
    if not user:
        raise NotFound("not found")
    return user
"""),
          S("set_config", path="functions.get-user",
            value={"handler": "app.users.get_user", "events": [{"http": "GET /users/{id}"}]}),
          S("invoke_local", function="get-user", method="GET", path="/users/1"),
          S("invoke_local", function="get-user", method="GET", path="/users/9"),
      ],
      final="""Ported. The `httpApi` event becomes `- http: GET /users/{id}`, and the handler no longer builds `statusCode`/`body` [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing]:

```yaml
functions:
  get-user:
    handler: app.users.get_user
    events:
      - http: GET /users/{id}
```

- `event["pathParameters"]["id"]` -> `event.http.path_params["id"]`
- return the dict -> 200 JSON; `raise NotFound(...)` -> 404 JSON

Checks:
- `pskit validate` (onprem): valid.
- `GET /users/1`: 200 `{"id": "1", "name": "Ada"}`. `GET /users/9`: 404 `{"error": "not found", ...}`.

`USERS` is sample data. Put your real lookup in its place. Test again: `pskit invoke -f get-user --method GET --path /users/1`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 222
    B(222, stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/resources.md#runtime-api", "docs/resources.md#troubleshooting"],
      project=dict(files={
          "pskit.yml": """service: reporting
provider:
  name: onprem
  region: local
  options:
    port: 8222
functions:
  export-report:
    handler: app.reports.export
    events:
    - http: POST /reports
""",
          "app/__init__.py": "",
          "app/reports.py": FUTURE + """from py_serverless_kit import resource


def export(event, ctx):
    bucket = resource("reports").native_name
    return {"bucket": bucket, "key": "daily.csv"}, 201
""",
          "requirements.txt": ""}),
      user="""POST /reports on the Test page gives 500 and the log says

KeyError: "resource 'reports' is not bound to this function; bound: <none>. Check `resources:` and its `functions:` list in pskit.yml."

add the reports bucket so this works""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `resources.reports: {type: storage}` (a built-in bucket on the host)",
                                   "Validate for onprem, invoke POST /reports"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.reports", value={"type": "storage"}),
          S("invoke_local", function="export-report", method="POST", path="/reports"),
      ],
      final="""Fixed. `resource("reports")` needs a `reports` entry under `resources:` [docs/resources.md#troubleshooting]. I added a managed bucket:

```yaml
resources:
  reports:
    type: storage
```

On premises it is a built-in bucket folder, created when the host starts. With no `functions:` list, every function gets the binding.

- `pskit validate` (onprem): valid.
- `POST /reports`: 201, `{"bucket": "reports", "key": "daily.csv"}`.

Run it again on **Test** > **▶ Run locally**. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 223
    B(223, stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: stock
provider:
  name: onprem
  region: local
  runtime: nodejs20
  options:
    port: 8223
functions: {}
""",
          "package.json": json.dumps({"name": "stock", "version": "1.0.0", "private": True}, indent=2) + "\n"}),
      user="our team write javascript not python. need GET /stock/{sku} in js, gives count, unknown sku -> 404. runs on our server",
      steps=[
          S("get_project"),
          S("search_docs", query="node.js handler NotFound pathParams",
            docs=[D("docs/nodejs.md", "handlers", start="The handler string works like", end="(`class ValidationError extends Error {}` → `ValidationError`).")]),
          S("propose_plan", steps=["Write `src/stock.js`: export `getStock`, read event.http.pathParams.sku, throw NotFound if unknown",
                                   "Add function `get-stock` on GET /stock/{sku}",
                                   "Validate for onprem, invoke with a known and an unknown sku"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/stock.js", content="""const { NotFound } = require("pskit");

const STOCK = { "SKU-1": 12, "SKU-2": 0 };

exports.getStock = async (event, ctx) => {
  const sku = event.http.pathParams.sku;
  if (!(sku in STOCK)) {
    throw new NotFound(`unknown sku ${sku}`);
  }
  return { sku, count: STOCK[sku] };
};
"""),
          S("set_config", path="functions.get-stock",
            value={"handler": "src.stock.getStock", "events": [{"http": "GET /stock/{sku}"}]}),
          S("invoke_local", function="get-stock", method="GET", path="/stock/SKU-1"),
          S("invoke_local", function="get-stock", method="GET", path="/stock/NOPE"),
      ],
      final="""Done, in JavaScript. Your project already uses `runtime: nodejs20`, so the function is Node.js:

```yaml
functions:
  get-stock:
    handler: src.stock.getStock     # the getStock export of src/stock.js
    events:
      - http: GET /stock/{sku}
```

The API is the Python one in camelCase: `event.http.pathParams`, and `throw new NotFound(...)` gives a 404 [docs/nodejs.md#handlers].

- `pskit validate` (onprem): valid.
- `GET /stock/SKU-1`: 200 `{"sku": "SKU-1", "count": 12}`. `GET /stock/NOPE`: 404.

On the server, the host still runs in Python and starts `node` for each function, so the server needs `node` on PATH, or set `deploy.node: bundle` [docs/providers.md#onprem-on-premises]. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 224
    B(224, stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises", "docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": empty("search", 8224), "requirements.txt": ""}),
      user="rebuild-index: no route, no timer. external cron box calls /__pskit/invoke/rebuild-index with {full: bool}. token from PSKIT_ADMIN_TOKEN",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/index.py`: read event.data.full, log, return the mode",
                                   "Add `rebuild-index` with no events; admin_token: ${env:PSKIT_ADMIN_TOKEN, }",
                                   "Validate (onprem, prod), invoke with {full: true}"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/index.py", content=FUTURE + """

def rebuild(event, ctx):
    full = bool((event.data or {}).get("full", False))
    ctx.logger.info("rebuild index", extra={"full": full})
    return {"rebuilt": True, "mode": "full" if full else "incremental"}
"""),
          S("set_config", path="functions.rebuild-index", value={"handler": "app.index.rebuild"}),
          S("set_config", path="provider.options.admin_token", value="${env:PSKIT_ADMIN_TOKEN, }"),
          S("invoke_local", function="rebuild-index", type="invoke", data={"full": True}),
      ],
      final="""Done:

```yaml
provider:
  options:
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"
functions:
  rebuild-index:
    handler: app.index.rebuild      # no events = invoke-only
```

The cron box calls `POST /__pskit/invoke/rebuild-index` with header `x-pskit-token` and body `{"full": true}` [docs/providers.md#onprem-on-premises]. The body arrives as `event.data`.

- validate (onprem, prod): valid.
- invoke `{"full": true}`: `{"rebuilt": true, "mode": "full"}`.

Export `PSKIT_ADMIN_TOKEN` before `pskit deploy -s prod`. The host must listen on an address the cron box can reach (`options.host: 0.0.0.0`)."""),

    # ------------------------------------------------------------------ 225
    B(225, stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=["docs/cluster.md#alert-devops-optional"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8225
    cluster: prod
functions:
  web:
    handler: app.web.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/web.py": FUTURE + """

def home(event, ctx):
    return {"shop": "open"}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="When our cluster prod is full I want a message in our Teams channel. Write a function `notify-devops` that posts the alert's subject and the list of full servers to the webhook URL in TEAMS_WEBHOOK_URL. If the variable is not set it should only log. Tell me how to hook it to the cluster alerts.",
      steps=[
          S("get_project"),
          S("search_docs", query="cluster alerts function event data",
            docs=[D("docs/cluster.md", "alert-devops-optional", end="The function gets `event.data`:")]),
          S("propose_plan", steps=["Write `app/alerts.py`: build text from event.data (subject + servers with `over`), POST JSON {text} to TEAMS_WEBHOOK_URL with urllib, else log",
                                   "Add invoke-only function `notify-devops` with TEAMS_WEBHOOK_URL: ${env:TEAMS_WEBHOOK_URL, }",
                                   "Validate (onprem, prod), invoke with a sample alert"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/alerts.py", content=FUTURE + """import json
import urllib.request


def notify_devops(event, ctx):
    alert = event.data or {}
    full = [n["server"] for n in alert.get("nodes", []) if n.get("over")]
    text = f"{alert.get('subject', '[pskit] cluster alert')}\\nfull: {', '.join(full) or 'none'}"
    url = ctx.env.get("TEAMS_WEBHOOK_URL", "")
    if not url:
        ctx.logger.warning("no TEAMS_WEBHOOK_URL, alert not sent", extra={"text": text})
        return {"sent": False, "full": full}
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return {"sent": True, "status": resp.status, "full": full}
"""),
          S("set_config", path="functions.notify-devops",
            value={"handler": "app.alerts.notify_devops", "environment": {"TEAMS_WEBHOOK_URL": "${env:TEAMS_WEBHOOK_URL, }"}}),
          S("invoke_local", function="notify-devops", type="invoke",
            data={"type": "pskit.cluster.capacity", "cluster": "prod", "full": True,
                  "subject": "[pskit] cluster prod needs another server",
                  "nodes": [{"server": "app-1", "over": ["cpu"]}, {"server": "app-2", "over": []}]}),
      ],
      final="""Added `notify-devops` (no trigger; the cluster check calls it). It reads the alert from `event.data`, lists the servers whose `over` is not empty, and posts `{"text": ...}` to `TEAMS_WEBHOOK_URL`. Without the variable it only logs a warning.

- `pskit validate` (onprem, prod): valid.
- Local invoke with a sample alert (no URL set): `{"sent": false, "full": ["app-1"]}`.

Hook it up after deploying (the function must be deployed) [docs/cluster.md#alert-devops-optional]:

```bash
TEAMS_WEBHOOK_URL=https://example.com/teams-hook pskit deploy -s prod
pskit cluster alerts prod --function notify-devops --cooldown 30
pskit cluster alerts prod --test
```

Checks only run where pskit runs: the studio's **Scaling cluster** page with *Watch while the studio runs*, or `pskit cluster watch prod --interval 60` on an always-on machine."""),

    # ------------------------------------------------------------------ 226
    B(226, stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule", "docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": empty("exports", 8226), "requirements.txt": ""}),
      user="our server puts export files in /srv/exports and the disk gets full. can something delete the files older than 30 days every night?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/cleanup.py`: delete files in EXPORT_DIR older than KEEP_DAYS days, return how many",
                                   "Add `cleanup-exports` with schedule cron `0 3 * * *`, EXPORT_DIR=/srv/exports, KEEP_DAYS=30",
                                   "Validate for onprem (prod) and run it once locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/cleanup.py", content=FUTURE + """import os
import time


def cleanup(event, ctx):
    folder = ctx.env.get("EXPORT_DIR", "/srv/exports")
    keep_days = int(ctx.env.get("KEEP_DAYS", "30"))
    if not os.path.isdir(folder):
        ctx.logger.warning("export folder not found", extra={"folder": folder})
        return {"deleted": 0, "folder_found": False}
    cutoff = time.time() - keep_days * 86400
    deleted = 0
    for entry in os.scandir(folder):
        if entry.is_file() and entry.stat().st_mtime < cutoff:
            os.remove(entry.path)
            deleted += 1
    ctx.logger.info("cleanup done", extra={"deleted": deleted})
    return {"deleted": deleted, "folder_found": True}
"""),
          S("set_config", path="functions.cleanup-exports",
            value={"handler": "app.cleanup.cleanup", "environment": {"EXPORT_DIR": "/srv/exports", "KEEP_DAYS": "30"},
                   "events": [{"schedule": "0 3 * * *"}]}),
          S("invoke_local", function="cleanup-exports", type="schedule"),
      ],
      final="""Yes. `cleanup-exports` runs every night at 03:00 (UTC) and deletes files in `/srv/exports` older than 30 days:

```yaml
functions:
  cleanup-exports:
    handler: app.cleanup.cleanup
    environment: {EXPORT_DIR: /srv/exports, KEEP_DAYS: "30"}
    events:
      - schedule: 0 3 * * *
```

- `pskit validate` (onprem, prod): valid.
- Run once on this computer: `{"deleted": 0, "folder_found": false}`. There is no `/srv/exports` here, so it only logged a warning. On the server it deletes the old files.

To keep files longer, change `KEEP_DAYS`. Only files directly in the folder are checked, not sub-folders. The user that runs the host needs write access to `/srv/exports`. Deploy: **Deploy** page (prod asks you to type a confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 227
    B(227, stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/resource-guides/onprem/queue.md#redis-valkey"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: onprem
  region: local
  options:
    port: 8227
resources:
  orders:
    type: queue
functions:
  process-order:
    handler: app.orders.process
    events:
    - queue: {resource: orders, batch_size: 10}
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def process(event, ctx):
    return {"processed": len(event.records)}
""",
          "requirements.txt": ""}),
      user="In dev the built-in queue `orders` is fine. In prod the same queue must live in our Redis (cache.example.com), list key `orders`, URL with password in ORDERS_REDIS_URL on the host. One pskit.yml, the handler must not change.",
      steps=[
          S("get_project"),
          S("search_docs", query="stages override per stage resources",
            docs=[D("docs/configuration.md", "stages-per-stage-overrides"),
                  D("docs/resource-guides/onprem/queue.md", "redis-valkey", start="### 3. Declare it", words=120)]),
          S("propose_plan", steps=["Add `stages.prod.resources.orders`: external, options {driver: redis, url_env: ORDERS_REDIS_URL, key: orders}",
                                   "Validate for onprem with stage prod (and dev stays builtin)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.resources.orders",
            value={"external": True, "options": {"driver": "redis", "url_env": "ORDERS_REDIS_URL", "key": "orders"}}),
          S("invoke_local", function="process-order", type="queue", data=[{"order": 1}, {"order": 2}]),
      ],
      final="""Done. The base config keeps the built-in queue, and the `prod` stage swaps it for Redis:

```yaml
stages:
  prod:
    resources:
      orders:
        external: true
        options: {driver: redis, url_env: ORDERS_REDIS_URL, key: orders}
```

Stage blocks are deep-merged, so `type: queue` and the function's `queue: {resource: orders}` stay [docs/configuration.md#stages-per-stage-overrides]. `url_env` makes the host read the URL from its own environment at start, so the password is not written into pskit files.

- `pskit validate` (onprem, prod): valid.
- Local invoke with 2 orders: `{"processed": 2}`. The handler is unchanged.

Set `ORDERS_REDIS_URL` where the prod host runs (systemd unit, Docker `-e`, or `provider.options.env_file`), then deploy with `pskit deploy -s prod`. If the variable is missing, the host stops at start with an error naming it."""),

    # ------------------------------------------------------------------ 228
    B(228, stage="staging", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises", "docs/workflows.md"],
      project=dict(files={
          "pskit.yml": """service: expenses
provider:
  name: onprem
  region: local
  options:
    port: 8228
functions:
  check-expense:
    handler: app.expenses.check
  pay-expense:
    handler: app.expenses.pay
workflows:
  approve-expense:
    start_at: check
    states:
      check: {type: task, function: check-expense, next: pay}
      pay: {type: task, function: pay-expense, end: true}
""",
          "app/__init__.py": "",
          "app/expenses.py": FUTURE + """

def check(event, ctx):
    data = dict(event.data or {})
    data["approved"] = data.get("amount", 0) <= 500
    return data


def pay(event, ctx):
    data = dict(event.data or {})
    data["paid"] = data.get("approved", False)
    return data
""",
          "requirements.txt": ""}),
      user="after approve-expense is finish, put a message in queue payouts. and a worker send-payout read that queue. bank call is slow so it must be in queue not in workflow",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/payouts.py`: `enqueue_payout` (submit_queue to `payouts` inside the host, log locally) and `send_payout` (queue worker)",
                                   "Add functions `enqueue-payout` and `send-payout` (queue `payouts`, batch 5)",
                                   "Add state `enqueue` after `pay` in approve-expense",
                                   "Validate (onprem, staging), invoke both"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/payouts.py", content=FUTURE + """

def enqueue_payout(event, ctx):
    data = dict(event.data or {})
    if not data.get("paid"):
        return data
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import submit_queue

        data["payout_message"] = submit_queue("payouts", {"expense_id": data.get("id"), "amount": data.get("amount")})
    else:
        ctx.logger.info("would enqueue payout", extra={"expense_id": data.get("id")})
    return data


def send_payout(event, ctx):
    for record in event.records:
        payout = record.json(default={}) or {}
        ctx.logger.info("send payout", extra={"expense_id": payout.get("expense_id"), "amount": payout.get("amount")})
    return {"sent": len(event.records)}
"""),
          S("set_config", path="functions.enqueue-payout", value={"handler": "app.payouts.enqueue_payout"}),
          S("set_config", path="functions.send-payout",
            value={"handler": "app.payouts.send_payout", "events": [{"queue": {"name": "payouts", "batch_size": 5}}]}),
          S("set_config", path="workflows.approve-expense.states",
            value={"check": {"type": "task", "function": "check-expense", "next": "pay"},
                   "pay": {"type": "task", "function": "pay-expense", "next": "enqueue"},
                   "enqueue": {"type": "task", "function": "enqueue-payout", "end": True}}),
          S("invoke_local", function="enqueue-payout", type="invoke", data={"id": "E-7", "amount": 120, "approved": True, "paid": True}),
          S("invoke_local", function="send-payout", type="queue", data=[{"expense_id": "E-7", "amount": 120}]),
      ],
      final="""Done. The workflow is now `check -> pay -> enqueue`. The last step only puts a message in `payouts`, and the slow bank call happens in `send-payout`, outside the workflow:

```yaml
functions:
  enqueue-payout: {handler: app.payouts.enqueue_payout}
  send-payout:
    handler: app.payouts.send_payout
    events:
      - queue: {name: payouts, batch_size: 5}
```

`enqueue-payout` uses `submit_queue` from `py_serverless_kit.runtime.onprem_host`, which works inside the host [docs/providers.md#onprem-on-premises]. On your PC there is no host, so it only logs.

- `pskit validate` (onprem, staging): valid.
- `enqueue-payout` with a paid expense: the data comes back unchanged (logged "would enqueue payout").
- `send-payout` with one message: `{"sent": 1}`.

Whole run locally: `pskit workflow run approve-expense -i '{"id": "E-7", "amount": 120}' --history`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 229
    B(229, stage="staging", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#runtime-api", "docs/resource-guides/onprem/cache.md"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: onprem
  region: local
  options:
    port: 8229
functions:
  product:
    handler: app.catalog.product
    events:
    - http: GET /products/{id}
  health:
    handler: app.catalog.health
    events:
    - http: GET /health
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """

def product(event, ctx):
    pid = event.http.path_params["id"]
    return {"id": pid, "name": f"Product {pid}"}


def health(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="memcached at cache-2.example.com:11211 for product lookups, 5 min ttl, only bind to product. cache down -> still answer",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.product-cache: {type: cache, external: true, connection: {host: cache-2.example.com, port: 11211, ttl: 300}, functions: [product]}",
                                   "Rewrite `product` with pymemcache: get, else build and set; any cache error -> answer uncached",
                                   "Add pymemcache to requirements.txt", "Validate, invoke"]),
          S("set_config", path="resources.product-cache",
            value={"type": "cache", "external": True,
                   "connection": {"host": "cache-2.example.com", "port": 11211, "ttl": 300}, "functions": ["product"]}),
          S("write_file", path="app/catalog.py", content=FUTURE + """import json

from py_serverless_kit import resource


def _cache():
    try:
        from pymemcache.client.base import Client
    except ImportError:
        return None, 0
    cfg = resource("product-cache")
    return Client((cfg["host"], int(cfg["port"])), connect_timeout=0.5, timeout=0.5), int(cfg.get("ttl", 300))


def product(event, ctx):
    pid = event.http.path_params["id"]
    key = f"product:{pid}"
    client, ttl = _cache()
    if client is not None:
        try:
            hit = client.get(key)
            if hit:
                return dict(json.loads(hit), cached=True)
        except Exception as exc:
            ctx.logger.warning("cache unavailable", extra={"error": str(exc)})
            client = None
    item = {"id": pid, "name": f"Product {pid}"}
    if client is not None:
        try:
            client.set(key, json.dumps(item), expire=ttl)
        except Exception as exc:
            ctx.logger.warning("cache set failed", extra={"error": str(exc)})
    return dict(item, cached=False)


def health(event, ctx):
    return {"ok": True}
"""),
          S("write_file", path="requirements.txt", content="pymemcache\n"),
          S("validate"),
          S("invoke_local", function="product", method="GET", path="/products/42"),
      ],
      final="""Done:

```yaml
resources:
  product-cache:
    type: cache
    external: true
    connection: {host: cache-2.example.com, port: 11211, ttl: 300}
    functions: [product]
```

`product` reads host/port/ttl with `resource("product-cache")` [docs/resources.md#runtime-api], tries the cache first, and on a miss stores the item for 300 s. Any cache error is logged as a warning and the request is answered uncached. `health` does not get the binding. `pymemcache` is in requirements.txt.

- validate (onprem, staging): valid.
- `GET /products/42`: 200 `{"id": "42", "name": "Product 42", "cached": false}`. pymemcache is not installed here, so this run did not use the cache. After deploy the host installs it, and the second call should return `cached: true`.

Open TCP 11211 from the function server to cache-2. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 230
    B(230, stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/handlers.md#batchresult", "docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing"],
      project=dict(files={"pskit.yml": empty("mailer", 8230), "requirements.txt": ""}),
      user="""Our SQS Lambda (ReportBatchItemFailures on, BatchSize 10) looks like this:

```python
def handler(event, context):
    failures = []
    for r in event["Records"]:
        msg = json.loads(r["body"])
        if "to" not in msg:
            failures.append({"itemIdentifier": r["messageId"]})
            continue
        send(msg)
    return {"batchItemFailures": failures}
```

Move it on-prem as `send-email` on a built-in queue `emails`, failed ones to emails-dlq after 3 tries.""",
      steps=[
          S("get_project"),
          S("search_docs", query="BatchResult fail record partial batch",
            docs=[D("docs/handlers.md", "batchresult", words=140)]),
          S("propose_plan", steps=["Write `app/mailer.py`: loop event.records, record.json(), BatchResult().fail(record) when `to` is missing",
                                   "Add `send-email` with queue {name: emails, batch_size: 10, dead_letter: emails-dlq, max_receive: 3}",
                                   "Validate, invoke with one good and one bad message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/mailer.py", content=FUTURE + """from py_serverless_kit import BatchResult


def send(msg, ctx):
    ctx.logger.info("send email", extra={"to": msg["to"]})


def send_email(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json(default={}) or {}
        if "to" not in msg:
            result.fail(record)
            continue
        send(msg, ctx)
    return result
"""),
          S("set_config", path="functions.send-email",
            value={"handler": "app.mailer.send_email",
                   "events": [{"queue": {"name": "emails", "batch_size": 10, "dead_letter": "emails-dlq", "max_receive": 3}}]}),
          S("invoke_local", function="send-email", type="queue",
            data=[{"to": "kim@example.com", "subject": "hi"}, {"subject": "no recipient"}]),
      ],
      final="""Ported. `batchItemFailures` becomes `BatchResult` [docs/handlers.md#batchresult]:

| Lambda | pskit |
|---|---|
| `event["Records"]`, `json.loads(r["body"])` | `event.records`, `record.json()` |
| `failures.append({"itemIdentifier": ...})` | `result.fail(record)` |
| BatchSize 10, redrive after 3 | `batch_size: 10`, `dead_letter: emails-dlq`, `max_receive: 3` |

```yaml
functions:
  send-email:
    handler: app.mailer.send_email
    events:
      - queue: {name: emails, batch_size: 10, dead_letter: emails-dlq, max_receive: 3}
```

- `pskit validate` (onprem): valid.
- invoke with one good and one bad message: only the bad one is in `batchItemFailures`. The built-in queue retries just that id, and after 3 tries it moves to `emails-dlq`.

`send()` only logs for now; put your real mail code there. Deploy: **Deploy** page or `pskit deploy -s dev`. Enqueue after deploy: `POST /__pskit/queues/emails`."""),

    # ------------------------------------------------------------------ 231
    B(231, stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises", "docs/onprem-network.md#3-deploy-to-one-server-method-ssh-docker-or-server-name"],
      project=dict(files={
          "pskit.yml": """service: intranet
provider:
  name: onprem
  region: local
  options:
    port: 8231
    deploy:
      server: app-2
      path: /opt/pskit/intranet
functions:
  home:
    handler: app.site.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/site.py": FUTURE + """

def home(event, ctx):
    return {"intranet": "ok"}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="""validate shows:

  WARNING: [provider.options.host] the host binds to 127.0.0.1 on the target. Set options.host: 0.0.0.0 to accept LAN traffic, or keep 127.0.0.1 and reach it through an SSH tunnel.

colleagues must open it in the browser as http://intranet.example.com:8231. add what's needed""",
      steps=[
          S("get_validation"),
          S("search_docs", query="host 0.0.0.0 advertise remote",
            docs=[D("docs/providers.md", "onprem-on-premises", start="`options.host` is the bind address", end="SSH and remote Docker deploys default `advertise`")]),
          S("propose_plan", steps=["Set provider.options.host: 0.0.0.0", "Set provider.options.advertise: http://intranet.example.com:8231",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
          S("set_config", path="provider.options.advertise", value="http://intranet.example.com:8231"),
      ],
      final="""Done:

```yaml
provider:
  options:
    host: 0.0.0.0                                  # listen on the LAN, not only on the server itself
    advertise: http://intranet.example.com:8231    # the URL pskit info shows
    port: 8231
```

`host` is the bind address on the server. `advertise` is the URL written into outputs. Without it, a remote deploy shows `http://<server>:<port>` [docs/providers.md#onprem-on-premises].

`pskit validate` (onprem, prod): valid. The bind warning is gone. One warning stays: app-2 must already have python3.12 on PATH. If it doesn't, add `deploy.python: bundle`.

Two things outside pskit.yml: `intranet.example.com` must resolve to app-2, and app-2's firewall must allow TCP 8231 from your colleagues' network. Run `pskit firewall --server app-2` to list the rules. Deploy: **Deploy** page (type the confirmation for prod) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 232
    B(232, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: billing
provider:
  name: onprem
  region: local
  options:
    port: 8232
functions:
  api:
    handler: app.billing.api
    events:
    - http: GET /invoices
  charge-cards:
    handler: app.billing.charge
    events:
    - schedule: 0 6 * * *
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """

def api(event, ctx):
    return {"invoices": []}


def charge(event, ctx):
    ctx.logger.info("charging cards")
    return {"charged": 0}
""",
          "requirements.txt": ""}),
      user="charge-cards must not run in dev, only staging and prod. in dev it should not exist at all",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `stages.dev.functions.charge-cards.enabled: false`",
                                   "Validate for onprem in dev"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.dev.functions.charge-cards", value={"enabled": False}),
      ],
      final="""Done:

```yaml
stages:
  dev:
    functions:
      charge-cards: {enabled: false}
```

`enabled: false` keeps the function in the file but skips it on deploy [docs/configuration.md#functions]. The `stages.dev` block only applies to stage `dev` [docs/configuration.md#stages-per-stage-overrides], so staging and prod still deploy it with its 06:00 timer.

`pskit validate` (onprem, dev): valid, with a warning that `charge-cards` is disabled. That is the change you asked for.

Deploy dev: **Deploy** page or `pskit deploy -s dev`. Deploying with `-s prod` includes `charge-cards`."""),

    # ------------------------------------------------------------------ 233
    B(233, stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resource-guides/onprem/services.md", "docs/resources.md#custom-drivers"],
      project=dict(files={
          "pskit.yml": """service: fulfilment
provider:
  name: onprem
  region: local
  options:
    port: 8233
    env_file: .env.onprem
resources:
  orders-mq:
    type: queue
    external: true
    options:
      driver: custom
      class: pskit_drivers.rabbitmq_queue:RabbitQueue
      url_env: PSKIT_ORDERS_MQ_URL
      queue: orders-mq
    connection:
      management_url: http://192.0.2.11:15672
      user: pskit
functions: {}
""",
          "pskit_drivers/__init__.py": "",
          "pskit_drivers/rabbitmq_queue.py": "# RabbitMQ queue driver (copied by pskit resources onprem create)\n",
          ".env.onprem": "",
          "requirements.txt": "pika\n"}),
      user="I created a RabbitMQ with Resources > + On-prem service (key orders-mq), but didn't tick any function. Now add `fulfil-order` consuming it, 5 at a time; messages failing 4 times go to a built-in queue orders-dlq. Log the order id.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/fulfil.py` (logs order_id per record)",
                                   "Add `fulfil-order` with queue {resource: orders-mq, batch_size: 5, max_receive: 4, dead_letter: orders-dlq}",
                                   "Validate (onprem, staging), invoke with one order"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/fulfil.py", content=FUTURE + """

def fulfil(event, ctx):
    for record in event.records:
        order = record.json(default={}) or {}
        ctx.logger.info("fulfil order", extra={"order_id": order.get("order_id")})
    return {"fulfilled": len(event.records)}
"""),
          S("set_config", path="functions.fulfil-order",
            value={"handler": "app.fulfil.fulfil",
                   "events": [{"queue": {"resource": "orders-mq", "batch_size": 5, "max_receive": 4, "dead_letter": "orders-dlq"}}]}),
          S("invoke_local", function="fulfil-order", type="queue", data=[{"order_id": "O-881"}]),
      ],
      final="""Added `fulfil-order` on the RabbitMQ resource. This is the same trigger the create form would have added if you had ticked the function:

```yaml
functions:
  fulfil-order:
    handler: app.fulfil.fulfil
    events:
      - queue: {resource: orders-mq, batch_size: 5, max_receive: 4, dead_letter: orders-dlq}
```

The `custom` driver (`pskit_drivers.rabbitmq_queue:RabbitQueue`, pika in requirements.txt) leases messages with AMQP acks, so a failed message goes back to RabbitMQ. After 4 failed tries, `settle` moves it to `orders-dlq` [docs/resources.md#custom-drivers]. `orders-dlq` is not declared as a resource, so it is a built-in queue on the host.

- `pskit validate` (onprem, staging): valid.
- invoke with one order: `{"fulfilled": 1}`.

Deploy with `pskit deploy -s staging`, then send a test message with **Resources > Test** or `pskit resources send orders-mq`."""),

    # ------------------------------------------------------------------ 234
    B(234, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: office-board
provider:
  name: onprem
  region: local
  options:
    port: 8234
functions:
  screen-feed:
    handler: app.board.screen_feed
    events:
    - topic: announcements
""",
          "app/__init__.py": "",
          "app/board.py": FUTURE + """

def screen_feed(event, ctx):
    for record in event.records:
        ctx.logger.info("show on screen", extra={"text": (record.json(default={}) or {}).get("text")})
    return None
""",
          "requirements.txt": ""}),
      user="screen-feed shows what is sent to announcements. i want a small form page to post to it, so a POST /announce with a text sends it to the topic",
      steps=[
          S("get_project"),
          S("search_docs", query="publish to topic from a handler on premises",
            docs=[D("docs/providers.md", "onprem-on-premises", start="From a handler in that process", end="From a handler in that process")]),
          S("propose_plan", steps=["Write `app/announce.py`: POST /announce, 400 without text, submit_topic('announcements') inside the host",
                                   "Add function `announce` on POST /announce",
                                   "Validate for onprem and test with a text"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/announce.py", content=FUTURE + """from py_serverless_kit import BadRequest


def announce(event, ctx):
    text = ((event.http.json(default={}) or {}).get("text") or "").strip()
    if not text:
        raise BadRequest("text is required")
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import submit_topic

        message_id = submit_topic("announcements", {"text": text})
    else:
        ctx.logger.info("would publish", extra={"text": text})
        message_id = "local-test"
    return {"published": message_id}, 202
"""),
          S("set_config", path="functions.announce",
            value={"handler": "app.announce.announce", "events": [{"http": "POST /announce"}]}),
          S("invoke_local", function="announce", method="POST", path="/announce", data={"text": "Pizza at 12 in the kitchen"}),
      ],
      final="""Done. `POST /announce` with `{"text": "..."}` publishes the text to the topic `announcements`, and `screen-feed` receives it. An empty text gives 400.

Publishing uses `submit_topic`, which works inside the host after deploy [docs/providers.md#onprem-on-premises]. On this computer there is no host, so the test only logged it.

- `pskit validate` (onprem): valid.
- Test with "Pizza at 12 in the kitchen": 202, `{"published": "local-test"}`.

After deploy, your form can POST to `http://<server>:8234/announce`. If the form is on another website, you also need `cors` on the route. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 235
    B(235, stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/smtp/README.md", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: helpdesk
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8235
resources:
  support-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.35, port: 25, domains: support.example.com, hostname: mail.support.example.com}
functions: {}
""",
          "requirements.txt": ""}),
      user="smtp support-mail -> fn take-mail only enqueues {from, subject} to queue mail-jobs and returns fast. worker process-mail batch 10",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/mail.py`: take_mail (submit_queue inside host, log locally) and process_mail",
                                   "Add `take-mail` (smtp: {resource: support-mail}) and `process-mail` (queue mail-jobs, batch 10)",
                                   "Validate (onprem, prod), invoke both"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/mail.py", content=FUTURE + """

def take_mail(event, ctx):
    mail = event.data or {}
    job = {"from": mail.get("from"), "subject": mail.get("subject")}
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import submit_queue

        return {"queued": submit_queue("mail-jobs", job)}
    ctx.logger.info("would queue", extra=job)
    return {"queued": None}


def process_mail(event, ctx):
    for record in event.records:
        job = record.json(default={}) or {}
        ctx.logger.info("process mail", extra={"from": job.get("from"), "subject": job.get("subject")})
    return {"processed": len(event.records)}
"""),
          S("set_config", path="functions.take-mail",
            value={"handler": "app.mail.take_mail", "events": [{"smtp": {"resource": "support-mail"}}]}),
          S("set_config", path="functions.process-mail",
            value={"handler": "app.mail.process_mail", "events": [{"queue": {"name": "mail-jobs", "batch_size": 10}}]}),
          S("invoke_local", function="take-mail", type="smtp"),
          S("invoke_local", function="process-mail", type="queue", data=[{"from": "user@example.org", "subject": "printer broken"}]),
      ],
      final="""Done:

```yaml
functions:
  take-mail:
    handler: app.mail.take_mail
    events:
      - smtp: {resource: support-mail}
  process-mail:
    handler: app.mail.process_mail
    events:
      - queue: {name: mail-jobs, batch_size: 10}
```

`take-mail` only calls `submit_queue("mail-jobs", {from, subject})` inside the host and returns. All the slow work goes in `process-mail`.

- validate (onprem, prod): valid.
- `take-mail` with the sample mail: `{"queued": null}` (no host locally, logged only).
- `process-mail` with one job: `{"processed": 1}`.

Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 236
    B(236, stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/cluster.md#one-server-or-the-cluster-per-deploy"],
      project=dict(files={
          "pskit.yml": """service: portal
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8236
    deploy:
      server: app-2
      path: /opt/pskit/portal
functions:
  web:
    handler: app.portal.web
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/portal.py": FUTURE + """

def web(event, ctx):
    return {"portal": ctx.stage}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="Staging should keep going to the single saved server app-2 as now. Prod should run on our scaling cluster `prod` with 3 web replicas instead. Same pskit.yml.",
      steps=[
          S("get_project"),
          S("search_docs", query="cluster option replicas per stage",
            docs=[D("docs/cluster.md", "one-server-or-the-cluster-per-deploy", words=160)]),
          S("propose_plan", steps=["Add `stages.prod.provider.options.cluster: {name: prod, replicas: 3}` (cluster wins over deploy)",
                                   "Validate for onprem with stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.provider.options", value={"cluster": {"name": "prod", "replicas": 3}}),
      ],
      final="""Done:

```yaml
stages:
  prod:
    provider:
      options:
        cluster: {name: prod, replicas: 3}
```

Only stage `prod` gets the cluster. Staging keeps `deploy: {server: app-2, ...}` from the base config [docs/configuration.md#stages-per-stage-overrides]. In prod, `deploy` is still inherited, but `options.cluster` comes before `options.deploy` when pskit picks the target [docs/cluster.md#one-server-or-the-cluster-per-deploy].

`pskit validate` (onprem, prod): valid.

Deploy: `pskit deploy -s staging` still goes to app-2, and `pskit deploy -s prod` goes to cluster `prod` with 3 web replicas. Prod asks for a typed confirmation on the **Deploy** page. Check the replicas afterwards on **Scaling cluster** or with `pskit cluster status prod`."""),

    # ------------------------------------------------------------------ 237
    B(237, stage="staging", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: media-js
provider:
  name: onprem
  region: local
  runtime: nodejs22
  options:
    port: 8237
functions: {}
""",
          "package.json": json.dumps({"name": "media-js", "version": "1.0.0", "private": True}, indent=2) + "\n"}),
      user="js worker `thumbs` on builtin queue thumbnails, batch 5. record w/o image_id -> fail just that one",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `src/thumbs.js`: BatchResult, result.fail(record) when image_id missing",
                                   "Add `thumbs` with queue {name: thumbnails, batch_size: 5}",
                                   "Validate (onprem, staging), invoke one good + one bad record"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/thumbs.js", content="""const { BatchResult } = require("pskit");

exports.thumbs = async (event, ctx) => {
  const result = new BatchResult();
  for (const record of event.records) {
    const job = record.json();
    if (!job || !job.image_id) {
      result.fail(record);
      continue;
    }
    ctx.logger.info("thumbnail", { image_id: job.image_id });
  }
  return result;
};
"""),
          S("set_config", path="functions.thumbs",
            value={"handler": "src.thumbs.thumbs", "events": [{"queue": {"name": "thumbnails", "batch_size": 5}}]}),
          S("invoke_local", function="thumbs", type="queue", data=[{"image_id": "img-1"}, {"size": 128}]),
      ],
      final="""Done:

```yaml
functions:
  thumbs:
    handler: src.thumbs.thumbs
    events:
      - queue: {name: thumbnails, batch_size: 5}
```

`new BatchResult()` + `result.fail(record)` work as in Python [docs/nodejs.md#handlers]. The built-in queue retries only the failed ids.

- validate (onprem, staging): valid.
- invoke `[{image_id: img-1}, {size: 128}]`: only the second record is in `batchItemFailures`.

Retest: `pskit invoke -f thumbs -t queue -d '[{"image_id": "img-2"}]'`. Deploy: `pskit deploy -s staging`. The server needs `node`, or set `deploy.node: bundle`."""),

    # ------------------------------------------------------------------ 238
    B(238, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: uploads
provider:
  name: onprem
  region: local
  options:
    port: 8238
functions:
  make-thumb:
    handler: app.media.make_thumb
    events:
    - storage: {bucket: uploads, events: [created]}
""",
          "app/__init__.py": "",
          "app/media.py": FUTURE + """

def make_thumb(event, ctx):
    for record in event.records:
        ctx.logger.info("thumb", extra={"key": record.key, "size": record.size})
    return None
""",
          "requirements.txt": ""}),
      user="make-thumb runs when file come in uploads bucket. now i need POST /upload/{name} that save the body in that bucket, so make-thumb run after",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/upload.py`: put_object('uploads', name, body) inside the host, 400 for empty body",
                                   "Add function `upload` on POST /upload/{name}",
                                   "Validate for onprem, invoke with a small body"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/upload.py", content=FUTURE + """from py_serverless_kit import BadRequest


def upload(event, ctx):
    name = event.http.path_params["name"]
    body = event.http.body or b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    if not body:
        raise BadRequest("empty body")
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import put_object

        put_object("uploads", name, body)
    else:
        ctx.logger.info("would store", extra={"key": name, "bytes": len(body)})
    return {"stored": name, "bytes": len(body)}, 201
"""),
          S("set_config", path="functions.upload",
            value={"handler": "app.upload.upload", "events": [{"http": "POST /upload/{name}"}]}),
          S("invoke_local", function="upload", method="POST", path="/upload/cat.jpg", data={"demo": "bytes"}),
      ],
      final="""Done. `POST /upload/{name}` saves the request body as `<name>` in the `uploads` bucket with `put_object`. Writing through the host also delivers the storage event, so `make-thumb` runs after it [docs/providers.md#onprem-on-premises].

- `pskit validate` (onprem): valid.
- Test `POST /upload/cat.jpg`: 201, `{"stored": "cat.jpg", ...}`. Locally there is no host, so it only logged "would store".

After deploy, try `curl --data-binary @cat.jpg http://<server>:8238/upload/cat.jpg` and watch `make-thumb` in **Logs**. The name is one path segment, so `/upload/a/b.jpg` does not match. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 239
    B(239, stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#errors", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: website
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8239
functions:
  contact:
    handler: app.contact.contact
    events:
    - http: POST /contact
""",
          "app/__init__.py": "",
          "app/contact.py": FUTURE + """

def contact(event, ctx):
    return {"thanks": True}
""",
          "requirements.txt": ""}),
      user="bots send our contact form 100 times a minute. can the same person only send it 5 times per minute? after that say too many",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Rewrite `app/contact.py`: count requests per event.http.source_ip in the last 60 s, raise TooManyRequests after 5",
                                   "Validate for onprem (prod) and send a test"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/contact.py", content=FUTURE + """import time

from py_serverless_kit import TooManyRequests

LIMIT = 5
WINDOW = 60.0
_SEEN = {}


def contact(event, ctx):
    ip = event.http.source_ip or "unknown"
    now = time.time()
    recent = [t for t in _SEEN.get(ip, []) if now - t < WINDOW]
    if len(recent) >= LIMIT:
        raise TooManyRequests("too many messages, try again in a minute")
    recent.append(now)
    _SEEN[ip] = recent
    return {"thanks": True}
"""),
          S("validate"),
          S("invoke_local", function="contact", method="POST", path="/contact", data={"email": "a@example.com", "text": "hello"}),
      ],
      final="""Yes. `contact` now remembers the last minute of messages per sender address (`event.http.source_ip`). The 6th one within 60 seconds gets **429** `"too many messages, try again in a minute"` [docs/handlers.md#errors].

- `pskit validate` (onprem, prod): valid.
- One test message: 200 `{"thanks": true}`.

Good to know:
- The count is kept in memory: it resets when the host restarts, and each server or cluster replica counts on its own.
- If the site is behind a proxy or load balancer, every visitor may have the proxy's address. Then the limit hits everyone together.

Deploy: **Deploy** page (prod asks you to type a confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 240
    B(240, stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: sync-rates
provider:
  name: onprem
  region: local
  options:
    port: 8240
functions:
  sync:
    handler: app.rates.sync
""",
          "app/__init__.py": "",
          "app/rates.py": FUTURE + """

def sync(event, ctx):
    region = (event.data or {}).get("region", "all")
    ctx.logger.info("sync rates", extra={"region": region})
    return {"synced": region}
""",
          "requirements.txt": ""}),
      user="""The SAM template had this for `sync`:

```yaml
Events:
  EuSync:
    Type: Schedule
    Properties:
      Schedule: cron(0/30 * * * ? *)
      Input: '{"region": "eu"}'
```

Give it the same timer here.""",
      steps=[
          S("get_project"),
          S("search_docs", query="SAM Schedule cron translate pskit schedule input",
            docs=[D("docs/migrating-from-aws.md", "step-2-translate-the-sam-serverless-cdk-definition",
                    start="| SAM `Events` |", end="| `Schedule: cron(0 12 * * ? *)` |")]),
          S("propose_plan", steps=["Add schedule {cron: '*/30 * * * *', input: {region: eu}} to sync",
                                   "Validate (onprem, staging), run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sync.events",
            value=[{"schedule": {"cron": "*/30 * * * *", "input": {"region": "eu"}}}]),
          S("invoke_local", function="sync", type="schedule"),
      ],
      final="""Same timer:

```yaml
functions:
  sync:
    events:
      - schedule: {cron: "*/30 * * * *", input: {region: eu}}
```

- AWS's 6-field `cron(0/30 * * * ? *)` becomes the standard 5-field `*/30 * * * *`, with no year field and no `?` [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition].
- `Input` becomes `input`, as a mapping instead of a JSON string. The handler gets it as `event.data`.

Checks:
- `pskit validate` (onprem, staging): valid.
- Local schedule run: `{"synced": "eu"}`, the configured input.

On premises the cron runs in UTC unless you add `timezone:`, like EventBridge. Deploy: `pskit deploy -s staging`."""),
]
