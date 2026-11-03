"""Category B (build / add), batch 16: on-premises only. Vague goals, studio-first users, small edits to larger
projects, approvals with notes, ask_user choices. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

SERVERS = json.dumps({"servers": {
    "app-1": {"host": "192.0.2.10", "user": "pskit", "port": 22},
    "app-2": {"host": "192.0.2.11", "user": "pskit", "port": 22},
    "db-1": {"host": "192.0.2.40", "user": "pskit", "port": 22},
    "gpu-box": {"host": "192.0.2.20", "user": "pskit", "port": 22}}}, indent=2)
CLUSTERS = json.dumps({"clusters": {"prod": {"orchestrator": "swarm", "master": "app-1", "servers": ["app-2"]}}},
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


def fn(body):
    return FUTURE + body


CONVERSATIONS = [
    # ------------------------------------------------------------------ 301
    B(301, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": yml("club", 8301, """functions:
  members:
    handler: app.members.members
    events:
    - http: GET /members
"""),
          "app/__init__.py": "",
          "app/members.py": fn("""
def members(event, ctx):
    return {"members": 2}
"""),
          "users.csv": "email,name\nana@example.com,Ana\nben@example.com,Ben\n",
          "requirements.txt": ""}),
      user="i want my app send email every monday to all users. the users are in users.csv",
      steps=[
          S("get_project"),
          S("ask_user", question="What time on Monday should the mail go out, and in which time zone?",
            options=["08:00 UTC", "09:00 in my local time zone (tell me which)"],
            answer="9 in morning, we are in madrid"),
          S("search_docs", query="schedule cron timezone weekly", docs=[D("docs/events.md", "schedule", words=170)]),
          S("propose_plan", steps=["Write `app/newsletter.py`: read users.csv, send one mail per user with smtplib; only log when SMTP_HOST is not set",
                                   "Write `.env.onprem` with SMTP_HOST / SMTP_PORT / MAIL_FROM placeholders and set provider.options.env_file",
                                   "Add `weekly-mail`: schedule {cron: '0 9 * * 1', timezone: Europe/Madrid}",
                                   "Validate for onprem and run it once"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/newsletter.py", content=fn("""import csv
import smtplib
from email.message import EmailMessage
from pathlib import Path

USERS = Path(__file__).resolve().parents[1] / "users.csv"


def load_users():
    with USERS.open(newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row.get("email")]


def weekly_mail(event, ctx):
    users = load_users()
    host = ctx.env.get("SMTP_HOST")
    if not host:
        ctx.logger.info("SMTP_HOST not set, nothing sent", extra={"users": len(users)})
        return {"sent": 0, "users": len(users)}
    sent = 0
    with smtplib.SMTP(host, int(ctx.env.get("SMTP_PORT", "25")), timeout=10) as smtp:
        for user in users:
            msg = EmailMessage()
            msg["From"] = ctx.env.get("MAIL_FROM", "news@example.com")
            msg["To"] = user["email"]
            msg["Subject"] = "This week at the club"
            msg.set_content(f"Hello {user.get('name') or 'there'},\\n\\nhere is this week's news.")
            smtp.send_message(msg)
            sent += 1
    return {"sent": sent, "users": len(users)}
""")),
          S("write_file", path=".env.onprem", content="# mail relay for weekly-mail; real values only on your machine\nSMTP_HOST=<fill in>\nSMTP_PORT=25\nMAIL_FROM=news@example.com\n"),
          S("set_config", path="provider.options.env_file", value=".env.onprem"),
          S("set_config", path="functions.weekly-mail",
            value={"handler": "app.newsletter.weekly_mail",
                   "events": [{"schedule": {"cron": "0 9 * * 1", "timezone": "Europe/Madrid"}}]}),
          S("invoke_local", function="weekly-mail", type="schedule"),
      ],
      final="""Done. New function `weekly-mail` runs every Monday at 09:00 Madrid time [docs/events.md#schedule]:

```yaml
functions:
  weekly-mail:
    handler: app.newsletter.weekly_mail
    events:
      - schedule: {cron: "0 9 * * 1", timezone: Europe/Madrid}
```

It reads every row of `users.csv` that has an email and sends each user one mail through your mail server.

Checks:
- `pskit validate` (onprem): valid. The warning only says this computer has no timezone database; `pskit deploy` adds `tzdata`, so the host uses Madrid time.
- One run now: `{"sent": 0, "users": 2}`. `SMTP_HOST` is not set on this computer, so it only logged and sent nothing.

Before deploying, open `.env.onprem` and put your mail server's name in `SMTP_HOST` (it says `<fill in>` now). The host loads that file at start (`provider.options.env_file`). Test again: **Test** page, pick `weekly-mail`, **▶ Run locally**, or `pskit invoke -f weekly-mail -t schedule`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 302
    B(302, stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/events.md#storage", "docs/events.md#events-backed-by-a-resource"],
      project=dict(files={
          "pskit.yml": yml("gallery", 8302, """resources:
  photos:
    type: storage
functions:
  gallery:
    handler: app.gallery.index
    events:
    - http: GET /photos
"""),
          "app/__init__.py": "",
          "app/gallery.py": fn("""
def index(event, ctx):
    return {"photos": []}
"""),
          "requirements.txt": ""}),
      user="On the Resources page I see my bucket photos. When someone puts a photo in it, I want the app to write down the name and the size somewhere I can look at later. Can you do that?",
      steps=[
          S("get_project"),
          S("search_docs", query="storage trigger resource bucket new file",
            docs=[D("docs/events.md", "events-backed-by-a-resource", words=120)]),
          S("propose_plan", steps=["Write `app/photo_log.py`: log each new photo's name and size",
                                   "Add `photo-added`: storage trigger on the `photos` resource, only new files",
                                   "Validate for onprem and try it with a sample photo"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/photo_log.py", content=fn("""
def photo_added(event, ctx):
    names = []
    for record in event.records:
        ctx.logger.info("new photo", extra={"name": record.key, "size": record.size})
        names.append(record.key)
    return {"logged": names}
""")),
          S("set_config", path="functions.photo-added",
            value={"handler": "app.photo_log.photo_added",
                   "events": [{"storage": {"resource": "photos", "events": ["created"]}}]}),
          S("invoke_local", function="photo-added", type="storage",
            data=[{"bucket": "photos", "key": "beach.jpg", "size": 248000}]),
      ],
      final="""Done. A new function `photo-added` runs every time a file is added to `photos`. It writes one log line per photo with its name and size in bytes [docs/events.md#events-backed-by-a-resource].

Checks:
- `pskit validate` (onprem): valid.
- Sample photo `beach.jpg` (248000 bytes): logged "new photo", answer `{"logged": ["beach.jpg"]}`.

Where to look later: after deploy, open **Logs** and search for "new photo", or run `pskit logs --function photo-added`.

To do the same yourself next time in studio: **Functions > + Create function**, step **Triggers**, click **Storage** and pick the `photos` resource. Test again: **Test** page or `pskit invoke -f photo-added -t storage`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 303
    B(303, stage="prod", mode="ask", page="Cluster", persona="informal_non_native",
      sources=["docs/cluster.md#set-up", "docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full"],
      project=dict(files={
          "pskit.yml": yml("shop", 8303, """functions:
  catalog:
    handler: app.shop.catalog
    events:
    - http: GET /catalog
  cart:
    handler: app.shop.cart
    events:
    - http: POST /cart
""", "    host: 0.0.0.0\n    cluster: {name: prod, replicas: 2}\n"),
          "app/__init__.py": "",
          "app/shop.py": fn("""
def catalog(event, ctx):
    return {"items": []}


def cart(event, ctx):
    return {"cart": "ok"}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="scaling cluster page say web replicas 2, both running, but cpu is 85% all the time. add one more copy pls",
      steps=[
          S("get_project"),
          S("search_docs", query="cluster replicas cpu memory", docs=[D("docs/cluster.md", "set-up", start="4. **Point the functions at the cluster**", end="admin_token: \"${env:PSKIT_ADMIN_TOKEN}\"")]),
          S("propose_plan", steps=["provider.options.cluster.replicas: 2 -> 3", "Validate for onprem (prod)"],
            result={"decision": "approved", "note": "ok. and give each copy 0.5 cpu, they are slow"}),
          S("set_config", path="provider.options.cluster.replicas", value=3),
          S("set_config", path="provider.options.cluster.cpu", value=0.5),
      ],
      final="""Done, with your note:

```yaml
provider:
  options:
    cluster: {name: prod, replicas: 3, cpu: 0.5}
```

That is 3 web replicas plus the main replica, and each one now reserves 0.5 CPU cores instead of the default 0.25 [docs/cluster.md#set-up].

`pskit validate` (onprem, prod): valid.

Bigger replicas need more room: after deploy, check `pskit cluster status prod` for any replica that "cannot be placed". If the servers are full, join another one [docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full].

In studio next time: **Scaling cluster**, fields **Web replicas** and **CPU per replica**, then **Save**. Deploy: **Deploy** page (prod asks you to type the confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 304
    B(304, stage="prod", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/placement.md"],
      project=dict(files={
          "pskit.yml": yml("scan", 8304, """functions:
  api:
    handler: app.web.api
    events:
    - http: POST /scan
  ocr:
    handler: app.ocr.ocr
""", """    host: 0.0.0.0
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        gpu: {server: gpu-box, functions: [ocr], port: 8091}
"""),
          "app/__init__.py": "",
          "app/web.py": fn("""from py_serverless_kit import invoke


def api(event, ctx):
    return invoke("ocr", {"doc": "x"})
"""),
          "app/ocr.py": fn("""
def ocr(event, ctx):
    return {"text": ""}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="gpu group port 8091 collides with node-exporter on gpu-box. move it to 9091",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.placement.groups.gpu.port: 8091 -> 9091", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.placement.groups.gpu.port", value=9091),
      ],
      final="""Done: `placement.groups.gpu: {server: gpu-box, functions: [ocr], port: 9091}`. The api group stays on app-1 with port 8304 [docs/placement.md].

validate (onprem, prod): valid.

`invoke("ocr", ...)` from api follows the new port after deploy, so no code change. Firewall: gpu-box must now accept 9091 from app-1; check **Network map** after saving. Same edit in studio: **Deploy > Where functions run**, the gpu group's **Port**. Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 305
    B(305, stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/placement.md", "docs/placement.md#how-the-groups-work-together"],
      project=dict(files={
          "pskit.yml": yml("docs-portal", 8305, """functions:
  api:
    handler: app.api.api
    events:
    - http: GET /documents
  export-pdf:
    handler: app.pdf.export_pdf
    events:
    - http: POST /export
  report:
    handler: app.report.report
    events:
    - schedule: 0 6 * * *
""", """    host: 0.0.0.0
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
"""),
          "app/__init__.py": "",
          "app/api.py": fn("""
def api(event, ctx):
    return {"documents": []}
"""),
          "app/pdf.py": fn("""
def export_pdf(event, ctx):
    return {"pdf": "queued"}
"""),
          "app/report.py": fn("""
def report(event, ctx):
    return {"report": "done"}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="export-pdf uses 3 GB of RAM while rendering and the other functions on app-1 get slow. Move only export-pdf to another saved server. api and report stay on app-1, and POST /export should keep working for the clients.",
      steps=[
          S("get_project"),
          S("ask_user", question="Which saved server should export-pdf run on?", options=["app-2", "gpu-box", "db-1"], answer="app-2"),
          S("search_docs", query="placement group move function other server",
            docs=[D("docs/placement.md", "functions-on-several-servers-on-premises", start="Per group: one of", end="each function shows where it runs.")]),
          S("propose_plan", steps=["Add placement group `pdf: {server: app-2, functions: [export-pdf]}`",
                                   "api and report stay in the default group on app-1", "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.pdf", value={"server": "app-2", "functions": ["export-pdf"]}),
      ],
      final="""Done:

```yaml
provider:
  options:
    placement:
      default: api
      groups:
        api: {server: app-1}
        pdf: {server: app-2, functions: [export-pdf]}
```

`export-pdf` now runs on app-2 with only its own code. `api` and `report` are not listed in a group, so they stay in the default group on app-1 [docs/placement.md].

`pskit validate` (onprem, prod): valid.

Clients keep calling `POST /export` on app-1. A request for a route of another group is passed on to that group [docs/placement.md#how-the-groups-work-together], so app-1 must reach app-2 on port 8305.

In studio: open `export-pdf` on **Functions** and change **Runs on**. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 306
    B(306, stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": yml("orders", 8306, """functions:
  list-orders:
    handler: app.orders.list_orders
    events:
    - http: GET /orders
  create-order:
    handler: app.orders.create_order
    events:
    - http: POST /orders
  ship-order:
    handler: app.orders.ship_order
    events:
    - queue: {name: shipping, batch_size: 5}
""", "    host: 0.0.0.0\n"),
          "app/__init__.py": "",
          "app/orders.py": fn("""import uuid

ORDERS = {
    "A-1": {"id": "A-1", "status": "shipped"},
    "A-2": {"id": "A-2", "status": "new"},
}


def list_orders(event, ctx):
    return {"orders": list(ORDERS.values())}


def create_order(event, ctx):
    order_id = "A-" + uuid.uuid4().hex[:6]
    ORDERS[order_id] = {"id": order_id, "status": "new"}
    return ORDERS[order_id], 201


def ship_order(event, ctx):
    return {"shipped": len(event.records)}
"""),
          "requirements.txt": ""}),
      user="need one more url: GET /orders/A-1/status give only the status of that order. not found -> 404",
      steps=[
          S("read_file", path="app/orders.py"),
          S("propose_plan", steps=["Add `order_status` to app/orders.py (path param `id`, NotFound when unknown)",
                                   "Add function `order-status` on GET /orders/{id}/status",
                                   "Validate (onprem, staging), try A-1 and an unknown id"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/orders.py", content=fn("""import uuid

from py_serverless_kit import NotFound

ORDERS = {
    "A-1": {"id": "A-1", "status": "shipped"},
    "A-2": {"id": "A-2", "status": "new"},
}


def list_orders(event, ctx):
    return {"orders": list(ORDERS.values())}


def create_order(event, ctx):
    order_id = "A-" + uuid.uuid4().hex[:6]
    ORDERS[order_id] = {"id": order_id, "status": "new"}
    return ORDERS[order_id], 201


def order_status(event, ctx):
    order_id = event.http.path_params["id"]
    order = ORDERS.get(order_id)
    if order is None:
        raise NotFound(f"order {order_id} not found")
    return {"id": order_id, "status": order["status"]}


def ship_order(event, ctx):
    return {"shipped": len(event.records)}
""")),
          S("set_config", path="functions.order-status",
            value={"handler": "app.orders.order_status", "events": [{"http": "GET /orders/{id}/status"}]}),
          S("invoke_local", function="order-status", method="GET", path="/orders/A-1/status"),
          S("invoke_local", function="order-status", method="GET", path="/orders/Z-9/status"),
      ],
      final="""Done. New function `order-status` on `GET /orders/{id}/status`. It reads `id` from `event.http.path_params` [docs/handlers.md#httprequest] and gives 404 for an unknown order. The other three functions did not change.

Checks:
- `pskit validate` (onprem, staging): valid.
- `/orders/A-1/status`: 200 `{"id": "A-1", "status": "shipped"}`.
- `/orders/Z-9/status`: 404 "order Z-9 not found".

Next time in studio: **Functions > + Create function**, step **Triggers**, **HTTP endpoint** with the route `/orders/{id}/status`. Test again: **Test** page or `pskit invoke -f order-status --method GET --path /orders/A-2/status`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 307
    B(307, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": yml("portal", 8307, """functions:
  login:
    handler: app.portal.login
    events:
    - http: POST /login
  purge-sessions:
    handler: app.portal.purge_sessions
"""),
          "app/__init__.py": "",
          "app/portal.py": fn("""
def login(event, ctx):
    return {"token": "demo"}


def purge_sessions(event, ctx):
    ctx.logger.info("old sessions removed")
    return {"purged": True}
"""),
          "requirements.txt": ""}),
      user="purge-sessions only runs when I click it. Can it run by itself every night?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add a schedule to purge-sessions: cron '0 3 * * *' (every night 03:00 UTC)",
                                   "Validate for onprem and run it once"],
            result={"decision": "approved", "note": "not 3, our backup runs then. make it 4:30, and vienna time please"}),
          S("set_config", path="functions.purge-sessions.events",
            value=[{"schedule": {"cron": "30 4 * * *", "timezone": "Europe/Vienna"}}]),
          S("invoke_local", function="purge-sessions", type="schedule"),
      ],
      final="""Done, at the time you asked for: `purge-sessions` now runs every night at 04:30 Vienna time [docs/events.md#schedule].

```yaml
functions:
  purge-sessions:
    handler: app.portal.purge_sessions
    events:
      - schedule: {cron: "30 4 * * *", timezone: Europe/Vienna}
```

Checks:
- `pskit validate` (onprem): valid. The warning only says this computer has no timezone database, so a local run would use UTC; `pskit deploy` adds `tzdata`, so the host uses Vienna time.
- One run now: logged "old sessions removed", answer `{"purged": true}`.

You can still run it by hand: **Test** page, pick `purge-sessions`, **▶ Run locally**, or `pskit invoke -f purge-sessions -t schedule`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 308
    B(308, stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": yml("catalog", 8308, """functions:
  list-items:
    handler: app.items.list_items
    events:
    - http: GET /api/v1/items
  get-item:
    handler: app.items.get_item
    events:
    - http: GET /api/v1/items/{id}
"""),
          "app/__init__.py": "",
          "app/items.py": fn("""
def list_items(event, ctx):
    return {"items": [{"id": "1"}]}


def get_item(event, ctx):
    return {"id": event.http.path_params["id"]}
"""),
          "requirements.txt": ""}),
      user="list-items also on GET /api/v2/items, same fn. keep v1",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.list-items.events: add `http: GET /api/v2/items` next to v1", "Validate, invoke v2"]),
          S("set_config", path="functions.list-items.events", value=[{"http": "GET /api/v1/items"}, {"http": "GET /api/v2/items"}]),
          S("invoke_local", function="list-items", method="GET", path="/api/v2/items"),
      ],
      final="""Done:

```yaml
functions:
  list-items:
    events:
      - http: GET /api/v1/items
      - http: GET /api/v2/items
```

One function can have several HTTP routes [docs/events.md#http]. `get-item` stays on v1 only.

- validate (onprem): valid.
- `GET /api/v2/items`: 200 `{"items": [{"id": "1"}]}`.

Use `event.http.route` if the handler must tell v1 from v2 later. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 309
    B(309, stage="prod", mode="ask", page="Load balancers", persona="informal_non_native",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it"],
      project=dict(files={
          "pskit.yml": yml("intranet", 8309, """functions:
  people:
    handler: app.people.search
    events:
    - http: GET /search
""", "    host: 0.0.0.0\n    advertise: http://192.0.2.10:8309\n    balancer: {name: edge, path: intranet}\n    deploy: {server: app-1, python: bundle}\n"),
          "app/__init__.py": "",
          "app/people.py": fn("""
def search(event, ctx):
    return {"people": []}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="on load balancers page the route of this project is /intranet/. boss want /people/ instead. change it",
      steps=[
          S("get_project"),
          S("search_docs", query="balancer path prefix route", docs=[D("docs/load-balancers.md", "create-one-and-put-projects-on-it", start="A project names it in `pskit.yml`", end="`/shop` redirects to `/shop/`.")]),
          S("propose_plan", steps=["provider.options.balancer.path: intranet -> people", "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.balancer.path", value="people"),
      ],
      final="""Done: `balancer: {name: edge, path: people}`.

`pskit validate` (onprem, prod): valid.

The route changes on the next deploy: `http://edge/people/search` reaches the same `search` function, and the prefix is still removed before the request arrives [docs/load-balancers.md#create-one-and-put-projects-on-it]. After the deploy `/intranet/` is gone, so tell people to update their bookmarks.

Deploy: **Deploy** page (type the confirmation for prod) or `pskit deploy -s prod`. Then the **Load balancers** page shows the `/people/` route."""),

    # ------------------------------------------------------------------ 310
    B(310, stage="prod", mode="ask", page="Network map", persona="pasted_error",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": yml("billing", 8080, """functions:
  invoices:
    handler: app.billing.invoices
    events:
    - http: GET /invoices
""", "    host: 0.0.0.0\n    advertise: http://192.0.2.10:8080\n    balancer: edge\n    deploy: {server: app-1, python: bundle}\n"),
          "app/__init__.py": "",
          "app/billing.py": fn("""
def invoices(event, ctx):
    return {"invoices": []}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="""network map shows:

  app-1   Inbound - accept   8080/tcp from lb-1 (load balancer edge)

our IT only opens 8443 on app-1, nothing else. make billing use 8443""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.port: 8080 -> 8443",
                                   "provider.options.advertise: http://192.0.2.10:8443 (the address edge calls)",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.port", value=8443),
          S("set_config", path="provider.options.advertise", value="http://192.0.2.10:8443"),
      ],
      final="""Done:

```yaml
provider:
  options:
    port: 8443
    advertise: http://192.0.2.10:8443
```

`advertise` is the address the load balancer calls [docs/load-balancers.md#create-one-and-put-projects-on-it], so it had to change together with the port.

`pskit validate` (onprem, prod): valid.

After you save, **Network map** should show app-1 accepting 8443 from lb-1. The host only moves to 8443 after the next deploy, so IT can close 8080 after that. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`.

Port 8443 is often used for HTTPS, but the host still speaks plain HTTP on it. TLS stays on the load balancer."""),

    # ------------------------------------------------------------------ 311
    B(311, stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#fields", "docs/resource-guides/onprem/cache.md"],
      project=dict(files={
          "pskit.yml": yml("members", 8311, """resources:
  sessions:
    type: cache
    external: true
    connection: {host: 127.0.0.1, port: 6379, password_env: PSKIT_SESSIONS_PASSWORD}
    functions: [profile]
functions:
  login:
    handler: app.members.login
    events:
    - http: POST /login
  profile:
    handler: app.members.profile
    events:
    - http: GET /profile
""", "    env_file: .env.onprem\n"),
          "app/__init__.py": "",
          "app/members.py": fn("""from py_serverless_kit import resources


def login(event, ctx):
    return {"bound": sorted(resources())}


def profile(event, ctx):
    return {"bound": sorted(resources())}
"""),
          ".env.onprem": "PSKIT_SESSIONS_PASSWORD=<generated>\n",
          "requirements.txt": ""}),
      user="I made a Valkey with + On-prem service and called it sessions. But the login function can't see it, only profile. I need it in login too.",
      steps=[
          S("get_project"),
          S("search_docs", query="resource functions bound list", docs=[D("docs/resources.md", "fields", start="| `functions` |", end="| `functions` |")]),
          S("propose_plan", steps=["resources.sessions.functions: [profile] -> [profile, login]", "Validate for onprem, invoke login"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.sessions.functions", value=["profile", "login"]),
          S("invoke_local", function="login", method="POST", path="/login"),
      ],
      final="""Done. The `sessions` resource had `functions: [profile]`, so only profile got it. Now it is `functions: [profile, login]` [docs/resources.md#fields].

Checks:
- `pskit validate` (onprem): valid.
- `POST /login`: `{"bound": ["sessions"]}`, so login now sees it. `resource("sessions")` gives the host, port and `password_env` [docs/resource-guides/onprem/cache.md].

In studio next time: **Resources**, open `sessions`, tick the function under **Bound functions**, then **Save**. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 312
    B(312, stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/resources.md#fields", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": yml("finance", 8312, """resources:
  orders-db:
    type: database
    external: true
    connection: {host: db-1.example.com, port: 5432, database: orders, user: orders_app, password_env: ORDERS_DB_PASSWORD}
    functions: [create-order]
  reports-db:
    type: database
    external: true
    connection: {host: db-2.example.com, port: 3306, database: reports, user: reports_app, password_env: REPORTS_DB_PASSWORD}
    functions: [weekly-report]
functions:
  create-order:
    handler: app.finance.create_order
    events:
    - http: POST /orders
  weekly-report:
    handler: app.finance.weekly_report
    events:
    - schedule: 0 6 * * 1
"""),
          "app/__init__.py": "",
          "app/finance.py": fn("""
def create_order(event, ctx):
    return {"created": True}, 201


def weekly_report(event, ctx):
    return {"report": "weekly"}
"""),
          "requirements.txt": ""}),
      user="Add a function monthly-totals that runs at 05:00 on the 1st of every month and needs the database connection. Just the connection details for now, the query comes later.",
      steps=[
          S("get_project"),
          S("ask_user", question="The project has two databases. Which one should monthly-totals use?",
            options=["orders-db (PostgreSQL on db-1)", "reports-db (MySQL on db-2)", "both"],
            answer="reports-db, the totals are for finance"),
          S("propose_plan", steps=["Write `app/totals.py`: read resource('reports-db') and log host/database (no query yet)",
                                   "Add `monthly-totals` with schedule `0 5 1 * *`",
                                   "Add monthly-totals to resources.reports-db.functions",
                                   "Validate (onprem, staging), run it once"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/totals.py", content=fn("""from py_serverless_kit import resource


def monthly_totals(event, ctx):
    db = resource("reports-db")
    has_pw = bool(ctx.env.get(db["password_env"]))
    ctx.logger.info("reports db", extra={"host": db["host"], "database": db["database"], "password_set": has_pw})
    return {"database": db["database"], "host": db["host"]}
""")),
          S("set_config", path="functions.monthly-totals",
            value={"handler": "app.totals.monthly_totals", "events": [{"schedule": "0 5 1 * *"}]}),
          S("set_config", path="resources.reports-db.functions", value=["weekly-report", "monthly-totals"]),
          S("invoke_local", function="monthly-totals", type="schedule"),
      ],
      final="""Done. `monthly-totals` runs at 05:00 (UTC) on the 1st of every month and is bound to `reports-db` only:

```yaml
resources:
  reports-db:
    functions: [weekly-report, monthly-totals]
functions:
  monthly-totals:
    handler: app.totals.monthly_totals
    events:
      - schedule: 0 5 1 * *
```

The handler reads the connection with `resource("reports-db")` [docs/resources.md#runtime-api] and the password from the variable named in `password_env`.

Checks:
- `pskit validate` (onprem, staging): valid.
- One run: `{"database": "reports", "host": "db-2.example.com"}`. `REPORTS_DB_PASSWORD` is not set on this computer, so the password is empty here; set it on the host (for example in the env file).

For the query, add a MySQL client such as `pymysql` to `requirements.txt`. Test again: **Test** page or `pskit invoke -f monthly-totals -t schedule`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 313
    B(313, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": yml("website", 8313, """functions:
  home:
    handler: app.site.home
    events:
    - http: GET /
"""),
          "app/__init__.py": "",
          "app/site.py": fn("""
def home(event, ctx):
    return {"site": "ok"}
"""),
          "requirements.txt": ""}),
      user="when someone fill the contact form on my website (name, email, message) i want save it so i can read later. no database please",
      steps=[
          S("get_project"),
          S("search_docs", query="write object to built-in bucket from handler",
            docs=[D("docs/providers.md", "onprem-on-premises", start="From a handler in that process", end="From a handler in that process")]),
          S("propose_plan", steps=["Add a built-in bucket resource `contact-forms`",
                                   "Write `app/contact.py`: POST /contact checks the fields, saves each form as one JSON file with put_object (only logs outside the host)",
                                   "Add function `contact` on POST /contact", "Validate for onprem and send a test form"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources", value={"contact-forms": {"type": "storage"}}),
          S("write_file", path="app/contact.py", content=fn("""import json
import time
import uuid

from py_serverless_kit import BadRequest, resource


def contact(event, ctx):
    form = event.http.json(default={}) or {}
    missing = [k for k in ("name", "email", "message") if not str(form.get(k, "")).strip()]
    if missing:
        raise BadRequest("missing: " + ", ".join(missing))
    key = time.strftime("%Y-%m-%d") + "/" + uuid.uuid4().hex[:8] + ".json"
    data = json.dumps({k: form[k] for k in ("name", "email", "message")}).encode("utf-8")
    bucket = resource("contact-forms").native_name
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import put_object

        put_object(bucket, key, data)
    else:
        ctx.logger.info("would save form", extra={"bucket": bucket, "key": key})
    return {"saved": True}, 201
""")),
          S("set_config", path="functions.contact", value={"handler": "app.contact.contact", "events": [{"http": "POST /contact"}]}),
          S("invoke_local", function="contact", method="POST", path="/contact",
            data={"name": "Lea", "email": "lea@example.com", "message": "Do you deliver on Sundays?"}),
          S("invoke_local", function="contact", method="POST", path="/contact", data={"name": "Lea"}),
      ],
      final="""Done, without a database. Each form is saved as one small JSON file in a built-in bucket `contact-forms`, in a folder per day (`2026-11-01/<id>.json`). The function uses `put_object` from `py_serverless_kit.runtime.onprem_host`, which works inside the host [docs/providers.md#onprem-on-premises].

Checks:
- `pskit validate` (onprem): valid.
- Full form: 201 `{"saved": true}`. On this computer there is no host, so it only logged "would save form".
- Only a name: 400 "missing: email, message".

To read the forms after deploy: **Resources**, open `contact-forms`, **Data**. Your website sends a JSON POST to `/contact`. Test again: **Test** page or `pskit invoke -f contact --method POST --path /contact -d @form.json`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 314
    B(314, stage="prod", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": yml("analytics", 8314, """functions:
  dashboard:
    handler: app.analytics.dashboard
    events:
    - http: GET /
  rep:
    handler: app.analytics.build_report
    events:
    - schedule: 0 2 * * *
""", "    host: 0.0.0.0\n"),
          "app/__init__.py": "",
          "app/analytics.py": fn("""
def dashboard(event, ctx):
    return {"ok": True}


def build_report(event, ctx):
    return {"rows": 0}
"""),
          "requirements.txt": ""}),
      user="nobody know what 'rep' function is. rename it to nightly-report, same code same timer",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add functions.nightly-report with the same handler and schedule as rep",
                                   "Delete functions.rep", "Validate (onprem, prod), run nightly-report once"]),
          S("set_config", path="functions.nightly-report",
            value={"handler": "app.analytics.build_report", "events": [{"schedule": "0 2 * * *"}]}),
          S("set_config", path="functions.rep", value=None),
          S("invoke_local", function="nightly-report", type="schedule"),
      ],
      final="""Done. `rep` is now `nightly-report`, with the same handler `app.analytics.build_report` and the same timer `0 2 * * *` [docs/configuration.md#functions]. The code did not change.

- validate (onprem, prod): valid.
- One run of `nightly-report`: `{"rows": 0}`.

After the next deploy, logs and stats show it as `nightly-report`; older log lines keep the name `rep`. In studio this is **Rename** on the function's row on **Functions**. Deploy: `pskit deploy -s prod` (or the **Deploy** page, with typed confirmation)."""),

    # ------------------------------------------------------------------ 315
    B(315, stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": yml("lunch", 8315, """functions:
  menu:
    handler: app.lunch.menu
    events:
    - http: GET /menu
"""),
          "app/__init__.py": "",
          "app/lunch.py": fn("""
def menu(event, ctx):
    return {"today": "soup"}
"""),
          "requirements.txt": ""}),
      user="I deployed the lunch app on my PC and it works for me at localhost:8315. My colleague types my PC's address with :8315 and gets nothing. What is wrong? Please fix it.",
      steps=[
          S("get_project"),
          S("search_docs", query="on premises host bind address 0.0.0.0 LAN",
            docs=[D("docs/providers.md", "onprem-on-premises", words=200)]),
          S("propose_plan", steps=["Set provider.options.host: 0.0.0.0 so the host accepts connections from other computers",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
          S("invoke_local", function="menu", method="GET", path="/menu"),
      ],
      final="""The host listened only on `127.0.0.1` (the default), which means "this PC only". I set:

```yaml
provider:
  options:
    host: 0.0.0.0     # accept connections from the network
```

Checks:
- `pskit validate` (onprem): valid.
- `GET /menu`: 200 `{"today": "soup"}`.

Deploy again so the host restarts with the new address: **Deploy** page or `pskit deploy -s dev`. If your colleague still gets nothing, the Windows/Linux firewall on your PC must allow port 8315.

In studio next time: **Overview & provider**, section **On-premises options**, field **Bind address**."""),

    # ------------------------------------------------------------------ 316
    B(316, stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/handlers.md#context", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": yml("quotes", 8316, """functions:
  quote:
    handler: app.quotes.quote
    events:
    - http: GET /quote
  health:
    handler: app.quotes.health
    events:
    - http: GET /health
"""),
          "app/__init__.py": "",
          "app/quotes.py": fn("""
def quote(event, ctx):
    return {"price": 12.5}


def health(event, ctx):
    return {"ok": True}
"""),
          "requirements.txt": ""}),
      user="On Lambda, quote put context.aws_request_id into every log line and sent it back as an X-Request-Id response header, so support could find a customer's call in the logs. I need the same for GET /quote here.",
      steps=[
          S("get_project"),
          S("search_docs", query="context request id response headers tuple",
            docs=[D("docs/handlers.md", "context", words=110), D("docs/handlers.md", "returning-a-response", words=120)]),
          S("propose_plan", steps=["Update `quote`: log with ctx.request_id, return (body, 200, {'x-request-id': ctx.request_id})",
                                   "Validate (onprem, staging), invoke GET /quote"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/quotes.py", content=fn("""
def quote(event, ctx):
    ctx.logger.info("quote", extra={"request_id": ctx.request_id})
    return {"price": 12.5}, 200, {"x-request-id": ctx.request_id}


def health(event, ctx):
    return {"ok": True}
""")),
          S("validate"),
          S("invoke_local", function="quote", method="GET", path="/quote"),
      ],
      final="""Done. `context.aws_request_id` is `ctx.request_id` in pskit [docs/handlers.md#context]. `quote` now logs it and returns it as a header with the `(body, status, headers)` form [docs/handlers.md#returning-a-response]:

```python
return {"price": 12.5}, 200, {"x-request-id": ctx.request_id}
```

Checks:
- `pskit validate` (onprem, staging): valid.
- `GET /quote`: 200, `{"price": 12.5}` with an `x-request-id` header.

On the host, log entries written during a call already carry its `request_id`, so support can search for the header value on **Logs** or with `pskit logs -q <id>`. Test again: **Test** page or `pskit invoke -f quote --method GET --path /quote`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 317
    B(317, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#events-backed-by-a-resource", "docs/resource-guides/onprem/services.md#what-gets-written"],
      project=dict(files={
          "pskit.yml": yml("billing", 8317, """resources:
  invoices-redis:
    type: queue
    external: true
    options: {driver: redis, url_env: PSKIT_INVOICES_REDIS_URL, key: invoices}
functions:
  create-invoice:
    handler: app.invoices.create_invoice
    events:
    - http: POST /invoices
""", "    env_file: .env.onprem\n"),
          "app/__init__.py": "",
          "app/invoices.py": fn("""
def create_invoice(event, ctx):
    body = event.http.json(default={}) or {}
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import submit_queue

        submit_queue("invoices", body)
    return {"queued": True}, 202
"""),
          ".env.onprem": "PSKIT_INVOICES_REDIS_URL=<generated>\n",
          "requirements.txt": ""}),
      user="add worker for the invoices queue, it should log invoice number. 10 per time",
      steps=[
          S("get_project"),
          S("ask_user", question="There are two \"invoices\" queues: create-invoice writes to the built-in queue `invoices`, and there is also the Redis resource `invoices-redis` (Redis key `invoices`). Which one should the worker read?",
            options=["the built-in queue invoices", "the Redis resource invoices-redis"],
            answer="the redis one, we are moving to it"),
          S("propose_plan", steps=["Write `app/invoice_worker.py`: log each record's `number`",
                                   "Add `process-invoice`: queue {resource: invoices-redis, batch_size: 10}",
                                   "Validate for onprem, invoke with 2 messages"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/invoice_worker.py", content=fn("""
def process_invoice(event, ctx):
    numbers = []
    for record in event.records:
        invoice = record.json()
        ctx.logger.info("invoice", extra={"number": invoice.get("number")})
        numbers.append(invoice.get("number"))
    return {"processed": numbers}
""")),
          S("set_config", path="functions.process-invoice",
            value={"handler": "app.invoice_worker.process_invoice",
                   "events": [{"queue": {"resource": "invoices-redis", "batch_size": 10}}]}),
          S("invoke_local", function="process-invoice", type="queue", data=[{"number": "INV-101"}, {"number": "INV-102"}]),
      ],
      final="""Done. `process-invoice` reads the Redis resource `invoices-redis`, up to 10 messages per call, and logs each invoice number [docs/events.md#events-backed-by-a-resource].

```yaml
functions:
  process-invoice:
    handler: app.invoice_worker.process_invoice
    events:
      - queue: {resource: invoices-redis, batch_size: 10}
```

Checks:
- `pskit validate` (onprem): valid.
- 2 messages: `{"processed": ["INV-101", "INV-102"]}`.

Important: `create-invoice` still puts messages into the **built-in** queue `invoices`, not into Redis, so the worker won't see them yet. When you are ready, change `create-invoice` to write to Redis; I can do that next. Test again: **Test** page or `pskit invoke -f process-invoice -t queue -d @invoices.json`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 318
    B(318, stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": yml("ingest", 8318, """functions:
  ingest:
    handler: app.ingest.ingest
    timeout: 45
    events:
    - queue: {name: rows, batch_size: 10, visibility_timeout: 30, dead_letter: rows-dlq, max_receive: 3}
  api:
    handler: app.ingest.api
    events:
    - http: GET /status
"""),
          "app/__init__.py": "",
          "app/ingest.py": fn("""
def ingest(event, ctx):
    return {"rows": len(event.records)}


def api(event, ctx):
    return {"ok": True}
"""),
          "requirements.txt": ""}),
      user="ingest: batch 10 -> 25, visibility 30 -> 90 (timeout is 45, msgs got redelivered). keep dlq",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.ingest.events.0.queue.batch_size: 25", "functions.ingest.events.0.queue.visibility_timeout: 90", "Validate (onprem, staging)"]),
          S("set_config", path="functions.ingest.events.0.queue.batch_size", value=25),
          S("set_config", path="functions.ingest.events.0.queue.visibility_timeout", value=90),
      ],
      final="""Done:

```yaml
- queue: {name: rows, batch_size: 25, visibility_timeout: 90, dead_letter: rows-dlq, max_receive: 3}
```

Visibility 90 s is now above the 45 s timeout, so a slow batch is not handed out again while it still runs [docs/events.md#queue]. DLQ unchanged.

validate (onprem, staging): valid.

25 rows per call take longer; if a batch gets near 45 s, raise `timeout` too. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 319
    B(319, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": yml("helpdesk", 8319, """functions:
  tickets:
    handler: app.desk.tickets
    events:
    - http: GET /tickets
  send-summary:
    handler: app.desk.send_summary
"""),
          "app/__init__.py": "",
          "app/desk.py": fn("""
def tickets(event, ctx):
    return {"open": 3}


def send_summary(event, ctx):
    ctx.logger.info("summary: 3 open tickets")
    return {"open": 3}
"""),
          "requirements.txt": ""}),
      user="can send-summary run by itself? like a timer",
      steps=[
          S("get_project"),
          S("ask_user", question="How often should send-summary run?",
            options=["every 15 minutes", "every hour", "once a day at a set time"],
            answer="once a day, 6 in the evening"),
          S("propose_plan", steps=["Add a schedule to send-summary: cron '0 18 * * *' (18:00 UTC)", "Validate for onprem, run it once"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send-summary.events", value=[{"schedule": "0 18 * * *"}]),
          S("invoke_local", function="send-summary", type="schedule"),
      ],
      final="""Yes. `send-summary` now runs once a day at 18:00 [docs/events.md#schedule]:

```yaml
functions:
  send-summary:
    handler: app.desk.send_summary
    events:
      - schedule: 0 18 * * *
```

Checks:
- `pskit validate` (onprem): valid.
- One run now: logged "summary: 3 open tickets".

The time is UTC. If you mean 18:00 where you are, tell me your city and I'll add the `timezone`. In studio next time: **Functions**, open the function, step **Triggers**, **Schedule**. Test again: **Test** page or `pskit invoke -f send-summary -t schedule`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 320
    B(320, stage="prod", mode="auto", page="Cluster", persona="detailed_spec",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={
          "pskit.yml": yml("billing", 8320, """functions:
  invoices:
    handler: app.billing.invoices
    events:
    - http: GET /invoices
  render-pdf:
    handler: app.billing.render_pdf
    events:
    - http: POST /invoices/{id}/pdf
""", "    host: 0.0.0.0\n    cluster: {name: prod, replicas: 3, cpu: 0.5}\n"),
          "app/__init__.py": "",
          "app/billing.py": fn("""
def invoices(event, ctx):
    return {"invoices": []}


def render_pdf(event, ctx):
    return {"pdf": event.http.path_params["id"]}
"""),
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="The billing replicas on cluster prod get OOM-killed when render-pdf runs. Give every replica 1024 MB. Keep 3 replicas and 0.5 CPU.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.cluster.memory: 1024 (replicas 3, cpu 0.5 unchanged)", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.cluster.memory", value=1024),
      ],
      final="""Done: `cluster: {name: prod, replicas: 3, cpu: 0.5, memory: 1024}`. Each replica reserves 1024 MB instead of the default 256 MB [docs/cluster.md#set-up].

validate (onprem, prod): valid.

The 4 replicas (3 web + the main one) now reserve 4 GB together on app-1 and app-2. After deploy, `pskit cluster status prod` lists any replica that cannot be placed. Same field in studio: **Scaling cluster**, **Memory per replica (MB)**. Deploy: `pskit deploy -s prod`."""),
]
