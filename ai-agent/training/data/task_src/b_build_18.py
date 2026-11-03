"""Category B (build / add), batch 18: on-premises only. Small edits to larger projects (load balancers, clusters,
placement, workflows), studio-first users, approvals with notes, ask_user choices, auto mode. Hand-written; assembled
by tools/assemble.py (tool outputs are real)."""

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
    "db-1": {"host": "192.0.2.40", "user": "pskit", "port": 22}}}, indent=2)
CLUSTERS = json.dumps({"clusters": {
    "prod": {"orchestrator": "swarm", "master": "app-1", "servers": ["app-2"]},
    "prod2": {"orchestrator": "kubernetes", "master": "app-3", "servers": ["app-2"]}}}, indent=2)


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


def fn(body):
    return FUTURE + body


CONVERSATIONS = [
    # ------------------------------------------------------------------ 341
    B(341, stage="prod", mode="ask", page="Load balancers", persona="informal_non_native",
      sources=["docs/load-balancers.md#the-six-algorithms"],
      project=dict(files={
          "pskit.yml": yml("search", 8341, """functions:
  query:
    handler: app.search.query
    events:
    - http: GET /query
""", "    host: 0.0.0.0\n    cluster: {name: prod, replicas: 2}\n    balancer: {name: edge, path: search}\n"),
          "app/__init__.py": "",
          "app/search.py": fn("""
def query(event, ctx):
    return {"hits": []}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="search route on edge: app-2 is old and slow, many requests wait there. i want the lb send more to the faster server, automatic, not with fixed numbers",
      steps=[
          S("get_project"),
          S("search_docs", query="load balancer algorithm fastest server response time",
            docs=[D("docs/load-balancers.md", "the-six-algorithms", words=230)]),
          S("propose_plan", steps=["provider.options.balancer.algorithm: least_time (for this route only)", "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer.algorithm", value="least_time"),
      ],
      final="""Done: `balancer: {name: edge, path: search, algorithm: least_time}`.

`least_time` picks the server with the lowest average response time times the requests in progress, so the slow app-2 gets fewer requests on its own. It suits latency-sensitive APIs on uneven hardware. One note: it can favour one fast server until that one slows down [docs/load-balancers.md#the-six-algorithms]. Weights would be the fixed-numbers way, and you didn't want that.

`pskit validate` (onprem, prod): valid.

It applies to the `/search/` route only; other projects on edge keep their algorithm. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. Then the **Load balancers** page shows the route with `least_time`, and `pskit lb logs edge -n 50` shows which `upstream=` answers."""),

    # ------------------------------------------------------------------ 342
    B(342, stage="staging", mode="ask", page="Cluster", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": yml("billing", 8342, """functions:
  invoices:
    handler: app.billing.invoices
    events:
    - http: GET /invoices
""", "    host: 0.0.0.0\n    cluster: {name: prod, replicas: 3, cpu: 0.5}\n"),
          "app/__init__.py": "",
          "app/billing.py": fn("""
def invoices(event, ctx):
    return {"invoices": []}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="Staging and prod both deploy to cluster prod from this pskit.yml, so staging also takes 3 replicas at 0.5 CPU. Staging only needs 1 web replica with 0.25 CPU. Prod must stay as it is.",
      steps=[
          S("get_project"),
          S("search_docs", query="per stage override provider options", docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["Add stages.staging.provider.options.cluster: {name: prod, replicas: 1, cpu: 0.25}",
                                   "Validate (onprem, staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"staging": {"provider": {"options": {"cluster": {"name": "prod", "replicas": 1, "cpu": 0.25}}}}}),
      ],
      final="""Done:

```yaml
stages:
  staging:
    provider:
      options:
        cluster: {name: prod, replicas: 1, cpu: 0.25}
```

`stages.staging` only applies to staging deploys [docs/configuration.md#stages-per-stage-overrides]. So staging gets 1 web replica plus the main replica at 0.25 CPU, and prod keeps 3 at 0.5 [docs/cluster.md#set-up].

`pskit validate` (onprem, staging): valid.

Deploy: **Deploy** page or `pskit deploy -s staging`. The **Scaling cluster** page then lists the staging deployment with 1 web replica. The cluster page's **Web replicas** field edits the main `provider.options.cluster` (the prod value), not this staging override."""),

    # ------------------------------------------------------------------ 343
    B(343, stage="prod", mode="ask", page="Network map", persona="beginner",
      sources=["docs/placement.md"],
      project=dict(files={
          "pskit.yml": yml("photos", 8343, """functions:
  gallery:
    handler: app.gallery.gallery
    events:
    - http: GET /gallery
  resize-worker:
    handler: app.resize.resize
    events:
    - queue: {name: resize-jobs, batch_size: 5}
""", "    host: 0.0.0.0\n    deploy: {server: app-1, python: bundle}\n"),
          "app/__init__.py": "",
          "app/gallery.py": fn("""
def gallery(event, ctx):
    return {"photos": []}
"""),
          "app/resize.py": fn("""
def resize(event, ctx):
    return {"resized": len(event.records)}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="On the Network map only app-1 is used. app-2 is doing nothing. Can the resize worker run on app-2, so the gallery on app-1 is not slowed down?",
      steps=[
          S("get_project"),
          S("search_docs", query="placement groups function on another server",
            docs=[D("docs/placement.md", "functions-on-several-servers-on-premises", start="Per group: one of", end="each function shows where it runs.")]),
          S("propose_plan", steps=["Add provider.options.placement: default group `main` (keeps options.deploy, app-1) and group `workers: {server: app-2, functions: [resize-worker]}`",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement",
            value={"default": "main", "groups": {"main": {}, "workers": {"server": "app-2", "functions": ["resize-worker"]}}}),
      ],
      final="""Yes. I split the project into two placement groups:

```yaml
provider:
  options:
    deploy: {server: app-1, python: bundle}
    placement:
      default: main
      groups:
        main: {}                                            # uses options.deploy: app-1
        workers: {server: app-2, functions: [resize-worker]}
```

`resize-worker` now runs on app-2 with only its own code. `gallery` is not listed, so it stays in the default group on app-1 [docs/placement.md].

`pskit validate` (onprem, prod): valid.

After the next deploy (**Deploy** page with typed confirmation, or `pskit deploy -s prod`), the **Network map** shows app-2 as well. The two servers must reach each other on port 8343. To change it later in studio: the function's **Runs on** field on **Functions**, or **Deploy > Where functions run**."""),

    # ------------------------------------------------------------------ 344
    B(344, stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": yml("orders", 8344, """functions:
  create-order:
    handler: app.orders.create_order
    events:
    - http: POST /orders
  email-customer:
    handler: app.orders.email_customer
    events:
    - topic: order-events
"""),
          "app/__init__.py": "",
          "app/orders.py": fn("""
def create_order(event, ctx):
    return {"created": True}, 201


def email_customer(event, ctx):
    return {"emailed": len(event.records)}
"""),
          "requirements.txt": ""}),
      user="2nd subscriber on order-events: audit-log, logs type + order_id per msg",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/audit.py`", "Add `audit-log` with `topic: order-events`", "Validate, invoke with 2 msgs"]),
          S("write_file", path="app/audit.py", content=fn("""
def audit_log(event, ctx):
    for record in event.records:
        msg = record.json(default={}) or {}
        ctx.logger.info("audit", extra={"type": msg.get("type"), "order_id": msg.get("order_id")})
    return {"audited": len(event.records)}
""")),
          S("set_config", path="functions.audit-log", value={"handler": "app.audit.audit_log", "events": [{"topic": "order-events"}]}),
          S("invoke_local", function="audit-log", type="topic",
            data=[{"type": "created", "order_id": "O-1"}, {"type": "paid", "order_id": "O-1"}]),
      ],
      final="""Done: `audit-log` on `topic: order-events`, next to `email-customer`. Each subscriber gets every message [docs/events.md#topic].

- validate (onprem): valid.
- 2 messages: `{"audited": 2}`, one "audit" line each.

Bodies that are not JSON are logged with empty fields instead of failing. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 345
    B(345, stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#errors", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": yml("shop", 8345, """functions:
  orders:
    handler: app.shop.orders
    events:
    - http: GET /orders
""", "    host: 0.0.0.0\n"),
          "app/__init__.py": "",
          "app/shop.py": fn("""
ORDERS = [{"id": "A-1", "total": 20.0}, {"id": "A-2", "total": 35.5}]


def orders(event, ctx):
    return {"orders": ORDERS}
"""),
          "requirements.txt": ""}),
      user="need GET /stats with number of orders and sum of totals",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `stats` to app/shop.py: count and sum of ORDERS",
                                   "Add function `stats` on GET /stats", "Validate (onprem, prod), invoke"],
            result={"decision": "approved", "note": "only our office tools may read it. they send header x-api-key, the key is in STATS_KEY on the server"}),
          S("write_file", path="app/shop.py", content=fn("""import hmac

from py_serverless_kit import Unauthorized

ORDERS = [{"id": "A-1", "total": 20.0}, {"id": "A-2", "total": 35.5}]


def orders(event, ctx):
    return {"orders": ORDERS}


def stats(event, ctx):
    expected = ctx.env.get("STATS_KEY", "")
    sent = event.http.headers.get("x-api-key", "")
    if not expected or not hmac.compare_digest(sent, expected):
        raise Unauthorized("missing or wrong x-api-key")
    return {"orders": len(ORDERS), "total": round(sum(o["total"] for o in ORDERS), 2)}
""")),
          S("set_config", path="functions.stats", value={"handler": "app.shop.stats", "events": [{"http": "GET /stats"}]}),
          S("invoke_local", function="stats", method="GET", path="/stats"),
      ],
      final="""Done, with your note: `GET /stats` answers only when the `x-api-key` header matches `STATS_KEY` on the server. Otherwise it gives **401** [docs/handlers.md#errors]. If `STATS_KEY` is not set at all, every call is refused, so a missing key never opens it.

Checks:
- `pskit validate` (onprem, prod): valid.
- `GET /stats` without the header: 401 "missing or wrong x-api-key", as expected.

With the right key it returns `{"orders": 2, "total": 55.5}`. To try that locally, set `STATS_KEY` in your terminal and run `pskit invoke -f stats --method GET --path /stats -H "x-api-key: <your key>"`. On the server, put `STATS_KEY` in the host's env file (`provider.options.env_file`). Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 346
    B(346, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#topic", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": yml("orders", 8346, """functions:
  list-orders:
    handler: app.orders.list_orders
    events:
    - http: GET /orders
"""),
          "app/__init__.py": "",
          "app/orders.py": fn("""
def list_orders(event, ctx):
    return {"orders": []}
"""),
          "requirements.txt": ""}),
      user="when order is paid, warehouse system and accounting system both must know. each one is slow sometimes, one must not wait for other",
      steps=[
          S("get_project"),
          S("search_docs", query="topic fan-out several subscribers", docs=[D("docs/events.md", "topic", words=140)]),
          S("propose_plan", steps=["Write `app/paid.py`: `mark_paid` (POST /orders/{id}/paid, publishes to topic `order-paid` inside the host) and two subscribers",
                                   "Add `mark-paid`, `tell-warehouse` and `tell-accounting` (both on topic order-paid)",
                                   "Validate for onprem, invoke mark-paid and one subscriber"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/paid.py", content=fn("""
def mark_paid(event, ctx):
    message = {"order_id": event.http.path_params["id"], "status": "paid"}
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import submit_topic

        submit_topic("order-paid", message)
    else:
        ctx.logger.info("would publish", extra=message)
    return message, 202


def tell_warehouse(event, ctx):
    for record in event.records:
        ctx.logger.info("warehouse: ship", extra={"order_id": record.json().get("order_id")})
    return {"warehouse": len(event.records)}


def tell_accounting(event, ctx):
    for record in event.records:
        ctx.logger.info("accounting: book", extra={"order_id": record.json().get("order_id")})
    return {"accounting": len(event.records)}
""")),
          S("set_config", path="functions.mark-paid", value={"handler": "app.paid.mark_paid", "events": [{"http": "POST /orders/{id}/paid"}]}),
          S("set_config", path="functions.tell-warehouse", value={"handler": "app.paid.tell_warehouse", "events": [{"topic": "order-paid"}]}),
          S("set_config", path="functions.tell-accounting", value={"handler": "app.paid.tell_accounting", "events": [{"topic": "order-paid"}]}),
          S("invoke_local", function="mark-paid", method="POST", path="/orders/O-9/paid"),
          S("invoke_local", function="tell-warehouse", type="topic", data=[{"order_id": "O-9", "status": "paid"}]),
      ],
      final="""Done, with a topic, so each system gets its own copy and neither waits for the other [docs/events.md#topic]:

- `mark-paid` on `POST /orders/{id}/paid` publishes `{"order_id", "status": "paid"}` to the built-in topic `order-paid` (with `submit_topic`, inside the host [docs/providers.md#onprem-on-premises]) and answers 202 at once;
- `tell-warehouse` and `tell-accounting` both subscribe to `order-paid`.

Checks:
- `pskit validate` (onprem): valid.
- `POST /orders/O-9/paid`: 202. On this computer there is no host, so it only logged "would publish".
- `tell-warehouse` with that message: `{"warehouse": 1}`.

Replace the log lines with the real calls to the two systems later. Test again: **Test** page or `pskit invoke -f tell-accounting -t topic -d '[{"order_id": "O-9"}]'`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 347
    B(347, stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/placement.md", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": yml("erp", 8347, """functions:
  api:
    handler: app.api.api
    events:
    - http: GET /status
""", "    host: 0.0.0.0\n    deploy: {python: bundle}\n    placement:\n      default: api\n      groups:\n        api: {server: app-1}\n"),
          "app/__init__.py": "",
          "app/api.py": fn("""
def api(event, ctx):
    return {"ok": True}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="Add a function db-backup that runs pg_dump every night at 02:15 and writes the dump to /var/backups/erp/. It must run on the database machine itself, not on app-1.",
      steps=[
          S("get_project"),
          S("ask_user", question="Which saved server is the database machine?", options=["app-2", "app-3", "db-1"], answer="db-1"),
          S("propose_plan", steps=["Write `app/backup.py`: build the pg_dump command (file name with the date); run it only inside the host, log it locally",
                                   "Add `db-backup` with schedule `15 2 * * *`",
                                   "Add placement group `db: {server: db-1, functions: [db-backup]}`",
                                   "Validate (onprem, prod), run once"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/backup.py", content=fn("""import subprocess
from datetime import date

TARGET = "/var/backups/erp"


def db_backup(event, ctx):
    out = f"{TARGET}/erp-{date.today().isoformat()}.dump"
    cmd = ["pg_dump", "--format=custom", "--file", out, ctx.env.get("ERP_DB_NAME", "erp")]
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        subprocess.run(cmd, check=True, timeout=3000)
    else:
        ctx.logger.info("would run", extra={"cmd": " ".join(cmd)})
    return {"file": out}
""")),
          S("set_config", path="functions.db-backup", value={"handler": "app.backup.db_backup", "events": [{"schedule": "15 2 * * *"}]}),
          S("set_config", path="provider.options.placement.groups.db", value={"server": "db-1", "functions": ["db-backup"]}),
          S("invoke_local", function="db-backup", type="schedule"),
      ],
      final="""Done:

```yaml
functions:
  db-backup:
    handler: app.backup.db_backup
    events:
      - schedule: 15 2 * * *
provider:
  options:
    placement:
      groups:
        db: {server: db-1, functions: [db-backup]}
```

`db-backup` runs in its own placement group on db-1 [docs/placement.md] every night at 02:15 UTC [docs/events.md#schedule]. `api` stays on app-1.

Checks:
- `pskit validate` (onprem, prod): valid.
- One run here: `{"file": "/var/backups/erp/erp-<today>.dump"}`. Outside the host it only logged the command.

On db-1, the user that runs the host needs `pg_dump` on PATH, write access to `/var/backups/erp/` and access to the database (for example a `.pgpass` file). Set `ERP_DB_NAME` if the database is not called `erp`. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 348
    B(348, stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": yml("sales", 8348, """functions:
  daily-report:
    handler: app.sales.daily_report
    events:
    - schedule: {cron: 0 6 * * 1-5, timezone: Europe/Paris}
  api:
    handler: app.sales.api
    events:
    - http: GET /sales
"""),
          "app/__init__.py": "",
          "app/sales.py": fn("""
def daily_report(event, ctx):
    return {"report": "sent"}


def api(event, ctx):
    return {"sales": []}
"""),
          "requirements.txt": ""}),
      user="daily-report: 07:00 instead of 06:00, and saturdays too. tz stays",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["cron: '0 6 * * 1-5' -> '0 7 * * 1-6' (timezone Europe/Paris unchanged)", "Validate (onprem, prod), run once"]),
          S("set_config", path="functions.daily-report.events.0.schedule.cron", value="0 7 * * 1-6"),
          S("invoke_local", function="daily-report", type="schedule"),
      ],
      final="""Done: `schedule: {cron: "0 7 * * 1-6", timezone: Europe/Paris}`, so 07:00 Paris time, Monday to Saturday [docs/events.md#schedule].

- validate (onprem, prod): valid. The timezone warning is only about this computer; `pskit deploy` adds `tzdata`.
- one run: `{"report": "sent"}`.

Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 349
    B(349, stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": yml("paperless", 8349, """resources:
  scans:
    type: storage
functions:
  file-scan:
    handler: app.scans.file_scan
    events:
    - storage: {resource: scans, events: [created], prefix: inbox/}
"""),
          "app/__init__.py": "",
          "app/scans.py": fn("""
def file_scan(event, ctx):
    return {"filed": [r.key for r in event.records]}
"""),
          "requirements.txt": ""}),
      user="scans bucket now has inbox/invoices/ and inbox/letters/. file-scan must only run for invoices, letters are for other team",
      steps=[
          S("get_project"),
          S("search_docs", query="storage trigger prefix filter", docs=[D("docs/events.md", "storage", words=150)]),
          S("propose_plan", steps=["functions.file-scan.events.0.storage.prefix: inbox/ -> inbox/invoices/", "Validate for onprem, invoke with an invoice"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.file-scan.events.0.storage.prefix", value="inbox/invoices/"),
          S("invoke_local", function="file-scan", type="storage", data=[{"bucket": "scans", "key": "inbox/invoices/inv-204.pdf", "size": 51200}]),
      ],
      final="""Done: the trigger is now `storage: {resource: scans, events: [created], prefix: inbox/invoices/}`. Files under `inbox/letters/` no longer start `file-scan` [docs/events.md#storage].

Checks:
- `pskit validate` (onprem): valid.
- `inbox/invoices/inv-204.pdf`: `{"filed": ["inbox/invoices/inv-204.pdf"]}`.

If the other team needs a function for letters later, give it its own trigger with `prefix: inbox/letters/`. In studio next time: **Functions**, open `file-scan`, step **Triggers**, the storage trigger's prefix. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 350
    B(350, stage="staging", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": yml("checkout", 8350, """functions:
  validate-cart:
    handler: app.steps.validate_cart
  fraud-check:
    handler: app.steps.fraud_check
  charge-card:
    handler: app.steps.charge_card
workflows:
  pay:
    start_at: validate
    states:
      validate: {type: task, function: validate-cart, next: fraud}
      fraud: {type: task, function: fraud-check, next: charge}
      charge: {type: task, function: charge-card, end: true}
"""),
          "app/__init__.py": "",
          "app/steps.py": fn("""
def validate_cart(event, ctx):
    return dict(event.data or {}, valid=True)


def fraud_check(event, ctx):
    return dict(event.data or {}, fraud=False)


def charge_card(event, ctx):
    return dict(event.data or {}, charged=True)
"""),
          "requirements.txt": ""}),
      user="fraud vendor contract ended. skip fraud step in pay: validate -> charge",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["validate.next: fraud -> charge", "Delete state `fraud`", "Delete function `fraud-check`", "Validate (onprem, staging)"],
            result={"decision": "approved", "note": "keep the fraud-check function, new vendor starts in december. only remove the step"}),
          S("set_config", path="workflows.pay.states.validate.next", value="charge"),
          S("set_config", path="workflows.pay.states.fraud", value=None),
      ],
      final="""Done, and as you asked, `fraud-check` stays:

```yaml
workflows:
  pay:
    start_at: validate
    states:
      validate: {type: task, function: validate-cart, next: charge}
      charge: {type: task, function: charge-card, end: true}
```

validate (onprem, staging): valid (embedded engine). `fraud-check` is still a function you can call directly; no state uses it now.

In December, add the state back: `fraud: {type: task, function: fraud-check, next: charge}` and `validate.next: fraud`. Or use **Workflows**, **Add state**. Run it: `pskit workflow run pay -i '{"cart": "C-1"}' --history`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 351
    B(351, stage="prod", mode="auto", page="Cluster", persona="terse_expert",
      sources=["docs/cluster.md#one-server-or-the-cluster-per-deploy", "docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": yml("portal", 8351, """functions:
  web:
    handler: app.portal.web
    events:
    - http: GET /
""", "    host: 0.0.0.0\n    cluster: {name: prod, replicas: 2, cpu: 0.5, memory: 512}\n"),
          "app/__init__.py": "",
          "app/portal.py": fn("""
def web(event, ctx):
    return {"portal": "ok"}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="move portal from swarm cluster prod to new k3s cluster prod2, same sizes",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.cluster.name: prod -> prod2 (replicas 2, cpu 0.5, memory 512 kept)", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.cluster.name", value="prod2"),
      ],
      final="""Done: `cluster: {name: prod2, replicas: 2, cpu: 0.5, memory: 512}` [docs/cluster.md#set-up].

validate (onprem, prod): valid.

The next `pskit deploy -s prod` deploys to prod2. Afterwards check `pskit cluster status prod` for portal workloads still running on the old cluster, and clean them up on the **Scaling cluster** page. Data of the main replica stays on the old master (a Docker volume on Swarm); copy it first if portal keeps any."""),

    # ------------------------------------------------------------------ 352
    B(352, stage="prod", mode="ask", page="Cluster", persona="beginner",
      sources=["docs/placement.md", "docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": yml("media", 8352, """functions:
  api:
    handler: app.api.api
    events:
    - http: GET /videos
  render:
    handler: app.render.render
    events:
    - queue: {name: render-jobs, batch_size: 1}
""", """    host: 0.0.0.0
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-3}
        batch: {cluster: {name: prod, replicas: 2}, functions: [render]}
"""),
          "app/__init__.py": "",
          "app/api.py": fn("""
def api(event, ctx):
    return {"videos": []}
"""),
          "app/render.py": fn("""
def render(event, ctx):
    return {"rendered": len(event.records)}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="The render jobs pile up. Can render get one more copy on the cluster? The api is fine on its own server.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.placement.groups.batch.cluster.replicas: 2 -> 3 (api group unchanged)", "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.batch.cluster.replicas", value=3),
      ],
      final="""Done. Only the `batch` group changed:

```yaml
provider:
  options:
    placement:
      groups:
        api: {server: app-3}
        batch: {cluster: {name: prod, replicas: 3}, functions: [render]}
```

`render` runs on cluster prod with 3 web replicas now. `api` stays alone on app-3 [docs/placement.md].

`pskit validate` (onprem, prod): valid.

After the deploy (**Deploy** page with typed confirmation, or `pskit deploy -s prod`), the **Scaling cluster** page shows the new replica. If it says a replica "cannot be placed", the cluster is full; join another server [docs/cluster.md#set-up]."""),

    # ------------------------------------------------------------------ 353
    B(353, stage="dev", mode="ask", page="none", persona="beginner",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={"pskit.yml": yml("coupons", 8353, "functions: {}\n"), "requirements.txt": ""}),
      user="I want to give each customer a discount code and later check if a code is real and not used yet. How can my app do this?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/coupons.py`: `create_code` (POST /codes, random 8-character code), `check_code` (GET /codes/{code}), `use_code` (POST /codes/{code}/use, 409 if already used)",
                                   "Add the three functions", "Validate for onprem and try them"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/coupons.py", content=fn("""import secrets

from py_serverless_kit import Conflict, NotFound

CODES = {"WELCOME1": {"used": False}}


def create_code(event, ctx):
    code = secrets.token_hex(4).upper()
    CODES[code] = {"used": False}
    return {"code": code}, 201


def check_code(event, ctx):
    code = event.http.path_params["code"].upper()
    if code not in CODES:
        raise NotFound("unknown code")
    return {"code": code, "used": CODES[code]["used"]}


def use_code(event, ctx):
    code = event.http.path_params["code"].upper()
    if code not in CODES:
        raise NotFound("unknown code")
    if CODES[code]["used"]:
        raise Conflict("code already used")
    CODES[code]["used"] = True
    return {"code": code, "used": True}
""")),
          S("set_config", path="functions.create-code", value={"handler": "app.coupons.create_code", "events": [{"http": "POST /codes"}]}),
          S("set_config", path="functions.check-code", value={"handler": "app.coupons.check_code", "events": [{"http": "GET /codes/{code}"}]}),
          S("set_config", path="functions.use-code", value={"handler": "app.coupons.use_code", "events": [{"http": "POST /codes/{code}/use"}]}),
          S("invoke_local", function="check-code", method="GET", path="/codes/welcome1"),
          S("invoke_local", function="use-code", method="POST", path="/codes/WELCOME1/use"),
      ],
      final="""Done. Your app now has three functions:

- `create-code` on `POST /codes`: makes a new random code like `9F2A41C0`;
- `check-code` on `GET /codes/{code}`: says if the code exists and if it was used (404 for a fake code);
- `use-code` on `POST /codes/{code}/use`: marks it used. A second use gives **409** "code already used" [docs/handlers.md#errors].

Checks:
- `pskit validate` (onprem): valid.
- `GET /codes/welcome1`: 200 `{"code": "WELCOME1", "used": false}` (upper or lower case both work).
- `POST /codes/WELCOME1/use`: 200 `{"code": "WELCOME1", "used": true}`.

The codes are kept in memory for now, so they are lost on restart. For real customers, store them in a database. Test again: **Test** page or `pskit invoke -f create-code --method POST --path /codes`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 354
    B(354, stage="staging", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#provider", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": yml("crm", 8354, """functions:
  contacts:
    handler: app.crm.contacts
    events:
    - http: GET /contacts
  import-contacts:
    handler: app.crm.import_contacts
    events:
    - schedule: 0 3 * * *
"""),
          "app/__init__.py": "",
          "app/crm.py": fn("""
def contacts(event, ctx):
    return {"app": ctx.env.get("APP_NAME"), "log_level": ctx.env.get("LOG_LEVEL")}


def import_contacts(event, ctx):
    return {"app": ctx.env.get("APP_NAME"), "log_level": ctx.env.get("LOG_LEVEL")}
"""),
          "requirements.txt": ""}),
      user="""Our SAM template had

```yaml
Globals:
  Function:
    Environment:
      Variables: {LOG_LEVEL: INFO, APP_NAME: crm}
```

and ImportContactsFunction overrode LOG_LEVEL with DEBUG. Same here please.""",
      steps=[
          S("get_project"),
          S("search_docs", query="provider environment merged function environment",
            docs=[D("docs/configuration.md", "functions", start="| `environment`, `tags` | map |", end="| `environment`, `tags` | map |")]),
          S("propose_plan", steps=["provider.environment: {LOG_LEVEL: INFO, APP_NAME: crm} (like Globals)",
                                   "functions.import-contacts.environment: {LOG_LEVEL: DEBUG}",
                                   "Validate (onprem, staging), invoke both"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.environment", value={"LOG_LEVEL": "INFO", "APP_NAME": "crm"}),
          S("set_config", path="functions.import-contacts.environment", value={"LOG_LEVEL": "DEBUG"}),
          S("invoke_local", function="contacts", method="GET", path="/contacts"),
          S("invoke_local", function="import-contacts", type="schedule"),
      ],
      final="""Done. `provider.environment` is the pskit version of `Globals`, and a function's own `environment` is merged over it [docs/configuration.md#functions]:

```yaml
provider:
  environment:
    LOG_LEVEL: INFO
    APP_NAME: crm
functions:
  import-contacts:
    environment:
      LOG_LEVEL: DEBUG
```

Checks:
- `pskit validate` (onprem, staging): valid.
- `contacts`: `{"app": "crm", "log_level": "INFO"}`.
- `import-contacts`: `{"app": "crm", "log_level": "DEBUG"}`, with APP_NAME still inherited.

`LOG_LEVEL` is just a variable for your code here. In studio: **Overview & provider**, section **Environment variables**, and the function's own **Environment variables**. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 355
    B(355, stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": yml("crm", 8355, """functions:
  api:
    handler: app.crm.api
    events:
    - http: GET /
""", "    host: 0.0.0.0\n    deploy:\n      server: app-1\n      path: /opt/pskit/crm\n      python: bundle\n"),
          "app/__init__.py": "",
          "app/crm.py": fn("""
def api(event, ctx):
    return {"crm": "ok"}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="our admin say all apps must be in /srv/apps/ now, not /opt/pskit. change crm folder on app-1",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.deploy.path: /opt/pskit/crm -> /srv/apps/crm", "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.path", value="/srv/apps/crm"),
      ],
      final="""Done: `provider.options.deploy.path: /srv/apps/crm`. Server app-1, port 8355 and the bundled Python stay the same.

`pskit validate` (onprem, prod): valid.

Be careful with the switch:
1. The SSH user must be able to write to `/srv/apps/` (or have sudo).
2. On SSH deploys the data directory is `<path>/data` [docs/providers.md#onprem-on-premises]. Queues, buckets and logs under `/opt/pskit/crm/data` don't move by themselves; stop the old host and copy that folder if you need them.
3. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`.

Afterwards check that nothing from `/opt/pskit/crm` is still running on app-1, and delete that folder once the new one answers."""),

    # ------------------------------------------------------------------ 356
    B(356, stage="prod", mode="ask", page="Load balancers", persona="beginner",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={
          "pskit.yml": yml("wiki", 8356, """functions:
  pages:
    handler: app.wiki.pages
    events:
    - http: GET /pages
""", "    host: 0.0.0.0\n    deploy: {server: app-2, python: bundle}\n"),
          "app/__init__.py": "",
          "app/wiki.py": fn("""
def pages(event, ctx):
    return {"pages": []}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="Please put my wiki behind the load balancer so people don't need the port number.",
      steps=[
          S("get_project"),
          S("ask_user", question="The Load balancers page lists two: `edge` (public website traffic) and `intranet-lb` (internal only). Which one should the wiki use, and under which path?",
            options=["edge", "intranet-lb"], answer="intranet-lb, path wiki"),
          S("search_docs", query="put project on load balancer advertise", docs=[D("docs/load-balancers.md", "create-one-and-put-projects-on-it", start="A project names it in `pskit.yml`", end="`/shop` redirects to `/shop/`.")]),
          S("propose_plan", steps=["provider.options.balancer: {name: intranet-lb, path: wiki}",
                                   "provider.options.advertise: http://192.0.2.11:8356 (app-2, the address the load balancer calls)",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer", value={"name": "intranet-lb", "path": "wiki"}),
          S("set_config", path="provider.options.advertise", value="http://192.0.2.11:8356"),
      ],
      final="""Done:

```yaml
provider:
  options:
    advertise: http://192.0.2.11:8356            # app-2, called by the load balancer
    balancer: {name: intranet-lb, path: wiki}
```

After the next deploy people open `http://intranet-lb/wiki/pages` with no port. The `/wiki` prefix is removed before the request reaches your function [docs/load-balancers.md#create-one-and-put-projects-on-it].

`pskit validate` (onprem, prod): valid.

Deploy: **Deploy** page (type the confirmation) or `pskit deploy -s prod`. The route then shows on the **Load balancers** page. The load balancer's server must reach app-2 on port 8356."""),

    # ------------------------------------------------------------------ 357
    B(357, stage="dev", mode="auto", page="Code", persona="detailed_spec",
      sources=["docs/placement.md#each-function-is-its-own-sub-project"],
      project=dict(files={
          "pskit.yml": yml("reports", 8357, """functions:
  api:
    handler: app.api.api
    events:
    - http: GET /reports
  excel-report:
    handler: app.excel.excel_report
    events:
    - schedule: 0 6 * * 1
"""),
          "app/__init__.py": "",
          "app/api.py": fn("""
def api(event, ctx):
    return {"reports": []}
"""),
          "app/excel.py": fn("""
def excel_report(event, ctx):
    return {"sheet": "weekly"}
"""),
          "requirements.txt": ""}),
      user="excel-report will need openpyxl, but nothing else should get that dependency. Give it its own folder with its own requirements.txt, the way pskit recommends.",
      steps=[
          S("get_project"),
          S("search_docs", query="function own folder requirements sub-project",
            docs=[D("docs/placement.md", "each-function-is-its-own-sub-project", words=200)]),
          S("propose_plan", steps=["Create functions/__init__.py, functions/excel_report/__init__.py, handler.py (code from app/excel.py) and requirements.txt (openpyxl)",
                                   "Set functions.excel-report.handler: functions.excel_report.handler.excel_report",
                                   "Validate, run it once"]),
          S("write_file", path="functions/__init__.py", content=""),
          S("write_file", path="functions/excel_report/__init__.py", content=""),
          S("write_file", path="functions/excel_report/handler.py", content=fn("""
def excel_report(event, ctx):
    return {"sheet": "weekly"}
""")),
          S("write_file", path="functions/excel_report/requirements.txt", content="openpyxl\n"),
          S("set_config", path="functions.excel-report.handler", value="functions.excel_report.handler.excel_report"),
          S("invoke_local", function="excel-report", type="schedule"),
      ],
      final="""Done:

```
functions/
  __init__.py
  excel_report/
    __init__.py
    handler.py          # handler: functions.excel_report.handler.excel_report
    requirements.txt    # openpyxl
```

A function's sub-project is the nearest folder above its handler with a `requirements.txt` [docs/placement.md#each-function-is-its-own-sub-project]. On every provider its requirements are added to the bundle. With placement on premises, only the server running `excel-report` installs openpyxl. Right now there is no placement, so the one host installs it for the whole project; the other functions simply don't import it.

- validate (onprem): valid.
- run once: `{"sheet": "weekly"}`.

`app/excel.py` is now unused; delete it when you like. Import openpyxl inside `handler.py` when you add the real code. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 358
    B(358, stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": yml("payments", 8358, """functions:
  checkout:
    handler: app.pay.checkout
    events:
    - http: POST /checkout
""", "    host: 0.0.0.0\n"),
          "app/__init__.py": "",
          "app/pay.py": fn("""
def checkout(event, ctx):
    return {"redirect": "https://pay.example.com/session/1"}
"""),
          "requirements.txt": ""}),
      user="payment provider will call our webhook url with POST json when payment done. they sign body with HMAC-SHA256 hex in header X-Signature, the shared secret is in WEBHOOK_SECRET on server. wrong signature -> reject",
      steps=[
          S("get_project"),
          S("search_docs", query="raw body headers http request", docs=[D("docs/handlers.md", "httprequest", words=150)]),
          S("propose_plan", steps=["Write `app/webhook.py`: HMAC-SHA256 of the raw body with WEBHOOK_SECRET, compare_digest with X-Signature, 401 if wrong or missing",
                                   "Add function `payment-webhook` on POST /webhooks/payment",
                                   "Validate (onprem, staging), invoke without a signature"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/webhook.py", content=fn("""import hashlib
import hmac

from py_serverless_kit import Unauthorized


def payment_webhook(event, ctx):
    shared = ctx.env.get("WEBHOOK_SECRET", "").encode("utf-8")
    body = event.http.body or b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    expected = hmac.new(shared, body, hashlib.sha256).hexdigest()
    sent = event.http.headers.get("x-signature", "")
    if not shared or not hmac.compare_digest(sent, expected):
        raise Unauthorized("bad signature")
    payment = event.http.json(default={}) or {}
    ctx.logger.info("payment done", extra={"payment_id": payment.get("id")})
    return {"received": True}
""")),
          S("set_config", path="functions.payment-webhook", value={"handler": "app.webhook.payment_webhook", "events": [{"http": "POST /webhooks/payment"}]}),
          S("invoke_local", function="payment-webhook", method="POST", path="/webhooks/payment", data={"id": "pay_1", "status": "paid"}),
      ],
      final="""Done. New function `payment-webhook` on `POST /webhooks/payment`:

- it computes HMAC-SHA256 (hex) of the **raw** body with `WEBHOOK_SECRET` and compares it with `X-Signature` using `hmac.compare_digest` (headers are read case-insensitively) [docs/handlers.md#httprequest];
- a wrong or missing signature, or no secret on the server, gives **401** "bad signature" [docs/handlers.md#errors];
- a good one logs "payment done" with the payment id and answers 200.

Checks:
- `pskit validate` (onprem, staging): valid.
- POST without a signature: 401, as expected.

To test a signed call, set `WEBHOOK_SECRET` in your terminal, sign the body the same way and run `pskit invoke -f payment-webhook --method POST --path /webhooks/payment -d @body.json -H "X-Signature: <hex>"`. On the server, put `WEBHOOK_SECRET` in the host's env file. Give the provider `http://<your host>:8358/webhooks/payment`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 359
    B(359, stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response", "docs/handlers.md#errors"],
      project=dict(files={"pskit.yml": yml("bulk", 8359, "functions: {}\n"), "requirements.txt": ""}),
      user="POST /prices/bulk takes a JSON list of {sku, price}, at most 100 items. Each item is checked on its own: sku non-empty, price a number > 0. Answer 207 with one result per item ({sku, ok, error?}), or 400 if the body isn't a list or has more than 100 items.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/bulk.py`: check each item, collect results, return (results, 207); BadRequest for non-list / >100",
                                   "Add `bulk-prices` on POST /prices/bulk", "Validate, invoke with 2 good and 1 bad item"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/bulk.py", content=fn("""from py_serverless_kit import BadRequest

MAX_ITEMS = 100


def check(item):
    if not isinstance(item, dict) or not str(item.get("sku", "")).strip():
        return "sku is required"
    price = item.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
        return "price must be a number > 0"
    return None


def bulk_prices(event, ctx):
    items = event.http.json(default=None)
    if not isinstance(items, list):
        raise BadRequest("body must be a JSON list")
    if len(items) > MAX_ITEMS:
        raise BadRequest(f"at most {MAX_ITEMS} items")
    results = []
    for item in items:
        error = check(item)
        sku = item.get("sku") if isinstance(item, dict) else None
        results.append({"sku": sku, "ok": True} if error is None else {"sku": sku, "ok": False, "error": error})
    return {"results": results}, 207
""")),
          S("set_config", path="functions.bulk-prices", value={"handler": "app.bulk.bulk_prices", "events": [{"http": "POST /prices/bulk"}]}),
          S("invoke_local", function="bulk-prices", method="POST", path="/prices/bulk",
            data=[{"sku": "A1", "price": 9.5}, {"sku": "B2", "price": 3}, {"sku": "C3", "price": -1}]),
      ],
      final="""Done. `bulk-prices` on `POST /prices/bulk` checks each item on its own and answers **207** with one result per item, using the `(body, status)` return [docs/handlers.md#returning-a-response]. A body that isn't a list, or has more than 100 items, gives **400** [docs/handlers.md#errors].

Checks:
- `pskit validate` (onprem): valid.
- `[A1 9.5, B2 3, C3 -1]`: 207 with `A1` and `B2` ok, and `C3` `"price must be a number > 0"`.

The results are wrapped in `{"results": [...]}` so you can add totals later. Test again: **Test** page or `pskit invoke -f bulk-prices --method POST --path /prices/bulk -d @prices.json`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 360
    B(360, stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": yml("store", 8360, """functions:
  products:
    handler: app.store.products
    events:
    - http: GET /products
  list-products:
    handler: app.store.list_products
    events:
    - http: GET /products/all
  cart:
    handler: app.store.cart
    events:
    - http: POST /cart
"""),
          "app/__init__.py": "",
          "app/store.py": fn("""
PRODUCTS = [{"sku": "A1"}, {"sku": "B2"}]


def products(event, ctx):
    return {"products": PRODUCTS}


def list_products(event, ctx):
    return {"products": PRODUCTS}


def cart(event, ctx):
    return {"cart": []}
"""),
          "requirements.txt": ""}),
      user="products and list-products do the same thing. remove old list-products, but the old app still call /products/all so that must keep work",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Delete function list-products (and its handler code)",
                                   "functions.products.events: GET /products + GET /products/all",
                                   "Validate (onprem, staging), invoke /products/all"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.list-products", value=None),
          S("set_config", path="functions.products.events", value=[{"http": "GET /products"}, {"http": "GET /products/all"}]),
          S("write_file", path="app/store.py", content=fn("""
PRODUCTS = [{"sku": "A1"}, {"sku": "B2"}]


def products(event, ctx):
    return {"products": PRODUCTS}


def cart(event, ctx):
    return {"cart": []}
""")),
          S("validate"),
          S("invoke_local", function="products", method="GET", path="/products/all"),
      ],
      final="""Done:

```yaml
functions:
  products:
    events:
      - http: GET /products
      - http: GET /products/all     # old URL, same function
```

`list-products` and its `list_products` code are gone. One function can have several routes [docs/events.md#http].

Checks:
- `pskit validate` (onprem, staging): valid.
- `GET /products/all` on `products`: 200 `{"products": [{"sku": "A1"}, {"sku": "B2"}]}`.

The old app keeps working after the next deploy: **Deploy** page or `pskit deploy -s staging`."""),
]
