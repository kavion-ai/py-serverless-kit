"""Category B (build / add), batch 17: on-premises only. Vague goals, small edits to larger projects, studio-first
users, approvals with notes, ask_user choices. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

SERVERS = json.dumps({"servers": {
    "app-1": {"host": "192.0.2.10", "user": "pskit", "port": 22},
    "app-2": {"host": "192.0.2.11", "user": "pskit", "port": 22},
    "gpu-box": {"host": "192.0.2.20", "user": "pskit", "port": 22}}}, indent=2)


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
    # ------------------------------------------------------------------ 321
    B(321, stage="dev", mode="ask", page="none", persona="beginner",
      sources=["docs/handlers.md#returning-a-response", "docs/local-development.md"],
      project=dict(files={"pskit.yml": yml("shop-tally", 8321, "functions: {}\n"), "requirements.txt": ""}),
      user="I have a small shop. I want my staff to type in how many of an item they sold, and then see the total for each item. Can you make that?",
      steps=[
          S("get_project"),
          S("ask_user", question="Should the numbers survive a restart of the app? That needs a database. Or is it fine to keep them in memory while you try it out?",
            options=["keep them in memory for now", "they must be kept (use a database)"],
            answer="memory is fine, we just test first"),
          S("propose_plan", steps=["Write `app/tally.py`: `add_sale` (POST /sales {item, qty}) and `totals` (GET /sales/totals), kept in memory",
                                   "Add functions `add-sale` and `sales-totals`",
                                   "Validate for onprem and try both"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/tally.py", content=fn("""from py_serverless_kit import BadRequest

TOTALS = {}


def add_sale(event, ctx):
    body = event.http.json(default={}) or {}
    item = str(body.get("item", "")).strip().lower()
    qty = body.get("qty")
    if not item or not isinstance(qty, int) or qty < 1:
        raise BadRequest("send an item name and a qty of 1 or more")
    TOTALS[item] = TOTALS.get(item, 0) + qty
    return {"item": item, "total": TOTALS[item]}, 201


def totals(event, ctx):
    return {"totals": TOTALS}
""")),
          S("set_config", path="functions.add-sale", value={"handler": "app.tally.add_sale", "events": [{"http": "POST /sales"}]}),
          S("set_config", path="functions.sales-totals", value={"handler": "app.tally.totals", "events": [{"http": "GET /sales/totals"}]}),
          S("invoke_local", function="add-sale", method="POST", path="/sales", data={"item": "Bread", "qty": 3}),
          S("invoke_local", function="add-sale", method="POST", path="/sales", data={"item": "milk"}),
      ],
      final="""Done. Your project now has two functions:

- `add-sale` on `POST /sales`: send `{"item": "bread", "qty": 3}`, and it adds to that item's total;
- `sales-totals` on `GET /sales/totals`: shows the total for every item.

Checks:
- `pskit validate` (onprem): valid.
- `{"item": "Bread", "qty": 3}`: 201 `{"item": "bread", "total": 3}` (names are stored in lowercase).
- `{"item": "milk"}` without qty: 400 "send an item name and a qty of 1 or more".

The totals live in memory, so they reset when the app restarts, as agreed. To try it for real, run `pskit dev` and send a few sales. Test again: **Test** page or `pskit invoke -f add-sale --method POST --path /sales -d '{"item": "milk", "qty": 2}'`. Deploy: **Deploy** page or `pskit deploy -s dev`. When you want to keep the numbers, ask me to connect a database."""),

    # ------------------------------------------------------------------ 322
    B(322, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": yml("bakery", 8322, """functions:
  home:
    handler: app.bakery.home
    events:
    - http: GET /
"""),
          "app/__init__.py": "",
          "app/bakery.py": fn("""
def home(event, ctx):
    return {"bakery": "open"}
"""),
          "static/pricelist.pdf": "%PDF-1.4\n% demo price list\n%%EOF\n",
          "requirements.txt": ""}),
      user="customers must can download our price list. the pdf is in static/pricelist.pdf in the project. make a link for it",
      steps=[
          S("get_project"),
          S("search_docs", query="return binary file pdf response", docs=[D("docs/handlers.md", "returning-a-response", words=170)]),
          S("propose_plan", steps=["Write `app/files.py`: read static/pricelist.pdf, return Response.binary(..., 'application/pdf') with a download file name",
                                   "Add function `pricelist` on GET /pricelist.pdf", "Validate for onprem and call it"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/files.py", content=fn("""from pathlib import Path

from py_serverless_kit import Response

PDF = Path(__file__).resolve().parents[1] / "static" / "pricelist.pdf"


def pricelist(event, ctx):
    return Response.binary(PDF.read_bytes(), "application/pdf",
                           headers={"content-disposition": 'attachment; filename="pricelist.pdf"'})
""")),
          S("set_config", path="functions.pricelist", value={"handler": "app.files.pricelist", "events": [{"http": "GET /pricelist.pdf"}]}),
          S("invoke_local", function="pricelist", method="GET", path="/pricelist.pdf"),
      ],
      final="""Done. The link is `GET /pricelist.pdf`, for example `http://<your server>:8322/pricelist.pdf`. The new function `pricelist` sends the file with `Response.binary(..., "application/pdf")` [docs/handlers.md#returning-a-response]. The `content-disposition` header makes the browser download it as `pricelist.pdf`.

Checks:
- `pskit validate` (onprem): valid.
- `GET /pricelist.pdf`: 200, `content-type: application/pdf`, with the file's bytes.

The PDF is shipped with the code, so when you have a new price list, replace `static/pricelist.pdf` and deploy again: **Deploy** page or `pskit deploy -s dev`. Test again: **Test** page or `pskit invoke -f pricelist --method GET --path /pricelist.pdf`."""),

    # ------------------------------------------------------------------ 323
    B(323, stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#event", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": yml("printing", 8323, """functions:
  print-label:
    handler: app.labels.print_label
    events:
    - queue: {name: labels, batch_size: 5}
"""),
          "app/__init__.py": "",
          "app/labels.py": fn("""
def print_label(event, ctx):
    done = []
    for record in event.records:
        label = record.json()
        ctx.logger.info("print", extra={"order": label.get("order")})
        done.append(label.get("order"))
    return {"printed": done}
"""),
          "requirements.txt": ""}),
      user="On the Test page print-label works with a queue message. Now the office also wants to print one label right away from a web form, with POST /labels. Can the same function do both?",
      steps=[
          S("read_file", path="app/labels.py"),
          S("search_docs", query="event type is_http records one function two triggers", docs=[D("docs/handlers.md", "event", words=160)]),
          S("propose_plan", steps=["Add `http: POST /labels` to print-label next to the queue trigger",
                                   "Update the handler: if event.is_http, print the one label from the body; else loop over the records",
                                   "Validate, test both: HTTP and queue"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/labels.py", content=fn("""from py_serverless_kit import BadRequest


def print_one(label, ctx):
    ctx.logger.info("print", extra={"order": label.get("order")})
    return label.get("order")


def print_label(event, ctx):
    if event.is_http:
        label = event.http.json(default={}) or {}
        if not label.get("order"):
            raise BadRequest("order is required")
        return {"printed": [print_one(label, ctx)]}, 201
    return {"printed": [print_one(record.json(), ctx) for record in event.records]}
""")),
          S("set_config", path="functions.print-label.events",
            value=[{"queue": {"name": "labels", "batch_size": 5}}, {"http": "POST /labels"}]),
          S("invoke_local", function="print-label", type="http", method="POST", path="/labels", data={"order": "SO-77"}),
          S("invoke_local", function="print-label", type="queue", data=[{"order": "SO-78"}, {"order": "SO-79"}]),
      ],
      final="""Yes. `print-label` now has two triggers, the `labels` queue and `POST /labels`. The handler checks `event.is_http` [docs/handlers.md#event]: a web request prints the one label from the body, and a queue call prints every message in the batch.

Checks:
- `pskit validate` (onprem): valid.
- `POST /labels {"order": "SO-77"}`: 201 `{"printed": ["SO-77"]}`.
- Queue with 2 messages: `{"printed": ["SO-78", "SO-79"]}`.

On the **Test** page, **1. Choose the event** now lists both triggers, so you can run each with **▶ Run locally**. In the terminal: `pskit invoke -f print-label -t http --method POST --path /labels -d '{"order": "SO-80"}'`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 324
    B(324, stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": yml("shop", 8324, """functions:
  validate-cart:
    handler: app.steps.validate_cart
  reserve-stock:
    handler: app.steps.reserve_stock
  charge-card:
    handler: app.steps.charge_card
  send-receipt:
    handler: app.steps.send_receipt
workflows:
  place-order:
    start_at: validate
    states:
      validate: {type: task, function: validate-cart, next: charge}
      charge:
        type: task
        function: charge-card
        next: receipt
        retry: [{errors: ["*"], max_attempts: 3, interval_seconds: 5}]
      receipt: {type: task, function: send-receipt, end: true}
"""),
          "app/__init__.py": "",
          "app/steps.py": fn("""
def validate_cart(event, ctx):
    return dict(event.data or {}, valid=True)


def reserve_stock(event, ctx):
    return dict(event.data or {}, reserved=True)


def charge_card(event, ctx):
    return dict(event.data or {}, charged=True)


def send_receipt(event, ctx):
    return dict(event.data or {}, receipt=True)
"""),
          "requirements.txt": ""}),
      user="We wrote reserve-stock but place-order never calls it. Put it between validate and charge: validate -> reserve -> charge -> receipt. Don't touch the retry on charge.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add state `reserve`: task reserve-stock, next charge",
                                   "Change validate.next: charge -> reserve",
                                   "Validate (onprem, staging), invoke reserve-stock"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.place-order.states.reserve", value={"type": "task", "function": "reserve-stock", "next": "charge"}),
          S("set_config", path="workflows.place-order.states.validate.next", value="reserve"),
          S("invoke_local", function="reserve-stock", type="invoke", data={"cart": "C-1"}),
      ],
      final="""Done. `place-order` is now validate -> reserve -> charge -> receipt:

```yaml
workflows:
  place-order:
    states:
      validate: {type: task, function: validate-cart, next: reserve}
      reserve: {type: task, function: reserve-stock, next: charge}
```

`charge` and its retry are unchanged.

Checks:
- `pskit validate` (onprem, staging): valid (embedded engine).
- `reserve-stock` with `{"cart": "C-1"}`: `{"cart": "C-1", "reserved": true}`.

Run the whole flow locally: `pskit workflow run place-order -i '{"cart": "C-1"}' --history`, or on **Deploy > Run a workflow locally**. The **Workflows** page shows the new box between validate and charge. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 325
    B(325, stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/placement.md"],
      project=dict(files={
          "pskit.yml": yml("scan", 8325, """functions:
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
        gpu: {server: gpu-box, functions: [ocr], port: 9091}
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
      user="gpu-box go to repair for 2 weeks. ocr must run on app-1 with the api until then. slower is ok",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Remove placement group `gpu`, so ocr falls back to the default group (api on app-1)",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.gpu", value=None),
      ],
      final="""Done. I removed the `gpu` group:

```yaml
provider:
  options:
    placement:
      default: api
      groups:
        api: {server: app-1}
```

A function not listed in any group runs in the default group [docs/placement.md], so `ocr` now runs on app-1 next to `api`. `invoke("ocr", ...)` stays the same.

`pskit validate` (onprem, prod): valid.

The next deploy moves ocr: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. When gpu-box is back, add the group again: `gpu: {server: gpu-box, functions: [ocr], port: 9091}`, or use **Deploy > Where functions run**."""),

    # ------------------------------------------------------------------ 326
    B(326, stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": yml("admin", 8326, """functions:
  list-users:
    handler: app.admin.list_users
    events:
    - http: GET /admin/users
  ban-user:
    handler: app.admin.ban_user
    events:
    - http: POST /admin/users/{id}/ban
  health:
    handler: app.admin.health
    events:
    - http: GET /health
"""),
          "app/__init__.py": "",
          "app/admin.py": fn("""
def list_users(event, ctx):
    return {"users": []}


def ban_user(event, ctx):
    return {"banned": event.http.path_params["id"]}


def health(event, ctx):
    return {"ok": True}
"""),
          "requirements.txt": ""}),
      user="cors for https://admin.example.com on both /admin routes, with authorization header. not on /health",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["list-users and ban-user: http mapping with cors {origins: [https://admin.example.com], headers: [authorization, content-type]}",
                                   "Validate, invoke ban-user"]),
          S("set_config", path="functions.list-users.events",
            value=[{"http": {"path": "/admin/users", "method": "GET",
                             "cors": {"origins": ["https://admin.example.com"], "headers": ["authorization", "content-type"]}}}]),
          S("set_config", path="functions.ban-user.events",
            value=[{"http": {"path": "/admin/users/{id}/ban", "method": "POST",
                             "cors": {"origins": ["https://admin.example.com"], "headers": ["authorization", "content-type"]}}}]),
          S("invoke_local", function="ban-user", method="POST", path="/admin/users/42/ban"),
      ],
      final="""Done, on the two admin routes only:

```yaml
functions:
  list-users:
    events:
      - http:
          path: /admin/users
          method: GET
          cors: {origins: [https://admin.example.com], headers: [authorization, content-type]}
```

`ban-user` (`POST /admin/users/{id}/ban`) has the same `cors`. `/health` has none [docs/events.md#http].

- validate (onprem, staging): valid.
- `POST /admin/users/42/ban`: 200 `{"banned": "42"}`. No CORS headers in the output because a local invoke sends no `Origin`.

Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 327
    B(327, stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resource-guides/onprem/cache.md"],
      project=dict(files={
          "pskit.yml": yml("catalog", 8327, """resources:
  cache:
    type: cache
    external: true
    connection: {host: cache-1.example.com, port: 6379, db: 0, password_env: CACHE_PASSWORD}
    functions: [products]
functions:
  products:
    handler: app.catalog.products
    events:
    - http: GET /products
  orders:
    handler: app.catalog.orders
    events:
    - http: GET /orders
""", "    host: 0.0.0.0\n"),
          "app/__init__.py": "",
          "app/catalog.py": fn("""from py_serverless_kit import resource


def products(event, ctx):
    c = resource("cache")
    return {"cache": f"{c['host']}:{c['port']}"}


def orders(event, ctx):
    return {"orders": []}
"""),
          "requirements.txt": ""}),
      user="IT moved our redis to port 6380 this weekend, same host. change it in my project",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.cache.connection.port: 6379 -> 6380", "Validate (onprem, prod), invoke products"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.cache.connection.port", value=6380),
          S("invoke_local", function="products", method="GET", path="/products"),
      ],
      final="""Done: `resources.cache.connection.port: 6380`. The host and the rest stay the same.

Checks:
- `pskit validate` (onprem, prod): valid.
- `GET /products`: `{"cache": "cache-1.example.com:6380"}`, so `resource("cache")` already gives the new port [docs/resource-guides/onprem/cache.md].

The deployed host still uses 6379 until you deploy again: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. If the firewall between your server and cache-1 only allowed 6379, ask IT to open 6380 too.

In studio next time: **Resources**, open `cache`, edit the port under **Connection**, then **Save**."""),

    # ------------------------------------------------------------------ 328
    B(328, stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": yml("crm", 8328, """functions:
  contacts:
    handler: app.crm.contacts
    events:
    - http: GET /contacts
  cleanup:
    handler: app.crm.cleanup
    events:
    - schedule: 0 1 * * *
"""),
          "app/__init__.py": "",
          "app/crm.py": fn("""
def contacts(event, ctx):
    return {"contacts": []}


def cleanup(event, ctx):
    return {"deleted": 0}
"""),
          "requirements.txt": ""}),
      user="the nightly cleanup deletes the test contacts that our testers need. please turn it off",
      steps=[
          S("get_project"),
          S("ask_user", question="Turn cleanup off everywhere, or only on one stage?",
            options=["only on staging", "on staging and dev", "everywhere"],
            answer="only staging. prod must keep cleaning"),
          S("search_docs", query="per stage override disable function", docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["Add stages.staging.functions.cleanup.enabled: false", "Validate (onprem, staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"staging": {"functions": {"cleanup": {"enabled": False}}}}),
      ],
      final="""Done, only for staging:

```yaml
stages:
  staging:
    functions:
      cleanup: {enabled: false}
```

`stages.staging` is applied only when the stage is staging [docs/configuration.md#stages-per-stage-overrides]. Prod and dev still run cleanup every night at 01:00.

`pskit validate` (onprem, staging): valid. The warning says `cleanup` is disabled, which is what we want.

It stops after the next staging deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 329
    B(329, stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": yml("mailer", 8329, """functions:
  send-email:
    handler: app.mailer.send_email
    events:
    - queue: {name: emails, batch_size: 10, dead_letter: emails-dlq, max_receive: 5}
  api:
    handler: app.mailer.api
    events:
    - http: POST /emails
""", "    host: 0.0.0.0\n"),
          "app/__init__.py": "",
          "app/mailer.py": fn("""
def send_email(event, ctx):
    return {"sent": len(event.records)}


def api(event, ctx):
    return {"queued": True}, 202
"""),
          "requirements.txt": ""}),
      user="send-email: give up after 2 tries not 5, dlq renamed to failed-emails",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["events.0.queue.max_receive: 2", "events.0.queue.dead_letter: failed-emails", "Validate (onprem, prod)"]),
          S("set_config", path="functions.send-email.events.0.queue.max_receive", value=2),
          S("set_config", path="functions.send-email.events.0.queue.dead_letter", value="failed-emails"),
      ],
      final="""Done:

```yaml
- queue: {name: emails, batch_size: 10, dead_letter: failed-emails, max_receive: 2}
```

A message that fails twice now moves to `failed-emails` [docs/events.md#queue].

validate (onprem, prod): valid.

Messages already in `emails-dlq` stay there; that queue is no longer used. Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 330
    B(330, stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": yml("inventory", 8330, """functions:
  get-item:
    handler: app.items.get_item
    events:
    - http: GET /items/{id}
"""),
          "app/__init__.py": "",
          "app/items.py": fn("""from py_serverless_kit import NotFound

ITEMS = {"1": {"id": "1", "name": "chair", "stock": 4}}


def get_item(event, ctx):
    item = ITEMS.get(event.http.path_params["id"])
    if item is None:
        raise NotFound("no such item")
    return item
"""),
          "requirements.txt": ""}),
      user="""$ curl -X PUT http://127.0.0.1:8330/items/1 -d '{"stock": 9}'
{"error": "method not allowed"}   (405)

i need to change the stock of an item with PUT. only stock, nothing else""",
      steps=[
          S("read_file", path="app/items.py"),
          S("propose_plan", steps=["Add `update_item` to app/items.py: PUT body {stock}, integer >= 0, 404 for unknown item",
                                   "Add function `update-item` on PUT /items/{id}",
                                   "Validate, invoke PUT"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/items.py", content=fn("""from py_serverless_kit import BadRequest, NotFound

ITEMS = {"1": {"id": "1", "name": "chair", "stock": 4}}


def get_item(event, ctx):
    item = ITEMS.get(event.http.path_params["id"])
    if item is None:
        raise NotFound("no such item")
    return item


def update_item(event, ctx):
    item = ITEMS.get(event.http.path_params["id"])
    if item is None:
        raise NotFound("no such item")
    body = event.http.json(default={}) or {}
    stock = body.get("stock")
    if set(body) != {"stock"} or not isinstance(stock, int) or stock < 0:
        raise BadRequest("send only {\\"stock\\": <integer 0 or more>}")
    item["stock"] = stock
    return item
""")),
          S("set_config", path="functions.update-item", value={"handler": "app.items.update_item", "events": [{"http": "PUT /items/{id}"}]}),
          S("invoke_local", function="update-item", method="PUT", path="/items/1", data={"stock": 9}),
      ],
      final="""The 405 came from the route: only `GET /items/{id}` existed. Now there is a new function `update-item` on `PUT /items/{id}` [docs/events.md#http]. It accepts only `{"stock": <integer 0 or more>}`. Other fields or a negative number give 400, and an unknown item gives 404.

Checks:
- `pskit validate` (onprem): valid.
- `PUT /items/1 {"stock": 9}`: 200 `{"id": "1", "name": "chair", "stock": 9}`.

The stock is in memory (like `ITEMS` before), so it resets on restart. Your curl works after the next deploy: **Deploy** page or `pskit deploy -s dev`. Test again: `pskit invoke -f update-item --method PUT --path /items/1 -d '{"stock": 2}'`."""),

    # ------------------------------------------------------------------ 331
    B(331, stage="prod", mode="ask", page="Network map", persona="detailed_spec",
      sources=["docs/placement.md"],
      project=dict(files={
          "pskit.yml": yml("docs-portal", 8331, """functions:
  api:
    handler: app.api.api
    events:
    - http: GET /documents
  export-pdf:
    handler: app.pdf.export_pdf
    events:
    - http: POST /export
""", """    host: 0.0.0.0
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        pdf: {server: app-2, functions: [export-pdf]}
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
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="""The Network map shows app-1 opening a connection to 192.0.2.11:8331 for group pdf. Our network team doesn't allow app-1 to reach app-2 by IP. It has to go through http://pdf.internal.example.com:8331, which points at app-2. Make the other group use that address.""",
      steps=[
          S("get_project"),
          S("search_docs", query="placement group advertise url other groups call",
            docs=[D("docs/placement.md", "functions-on-several-servers-on-premises", start="Per group: one of", end="each function shows where it runs.")]),
          S("propose_plan", steps=["Set provider.options.placement.groups.pdf.advertise: http://pdf.internal.example.com:8331",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement.groups.pdf.advertise", value="http://pdf.internal.example.com:8331"),
      ],
      final="""Done:

```yaml
provider:
  options:
    placement:
      groups:
        pdf: {server: app-2, functions: [export-pdf], advertise: "http://pdf.internal.example.com:8331"}
```

`advertise` is the URL the other groups call when the server's own address is not reachable [docs/placement.md]. The api group on app-1 will send export-pdf requests there instead of 192.0.2.11.

`pskit validate` (onprem, prod): valid.

It takes effect on the next deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. Afterwards **Network map** should show the outbound connection from app-1 to the new address. app-1 must resolve `pdf.internal.example.com`."""),

    # ------------------------------------------------------------------ 332
    B(332, stage="dev", mode="ask", page="none", persona="informal_non_native",
      sources=["docs/handlers.md#errors", "docs/handlers.md#httprequest"],
      project=dict(files={"pskit.yml": yml("club-events", 8332, "functions: {}\n"), "requirements.txt": ""}),
      user="make api for my kids football club: see all events, and add event with title and date. event in the past cannot be added",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/events.py`: `list_events` (sorted by date) and `add_event` (title + date YYYY-MM-DD, 400 if missing, wrong or in the past)",
                                   "Add `list-events` (GET /events) and `add-event` (POST /events)",
                                   "Validate for onprem, try a good and a past event"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/events.py", content=fn("""from datetime import date

from py_serverless_kit import BadRequest

EVENTS = []


def list_events(event, ctx):
    return {"events": sorted(EVENTS, key=lambda e: e["date"])}


def add_event(event, ctx):
    body = event.http.json(default={}) or {}
    title = str(body.get("title", "")).strip()
    try:
        day = date.fromisoformat(str(body.get("date", "")))
    except ValueError:
        raise BadRequest("date must look like 2026-12-24")
    if not title:
        raise BadRequest("title is required")
    if day < date.today():
        raise BadRequest("this date is in the past")
    item = {"title": title, "date": day.isoformat()}
    EVENTS.append(item)
    return item, 201
""")),
          S("set_config", path="functions.list-events", value={"handler": "app.events.list_events", "events": [{"http": "GET /events"}]}),
          S("set_config", path="functions.add-event", value={"handler": "app.events.add_event", "events": [{"http": "POST /events"}]}),
          S("invoke_local", function="add-event", method="POST", path="/events", data={"title": "Summer cup", "date": "2027-06-12"}),
          S("invoke_local", function="add-event", method="POST", path="/events", data={"title": "Old game", "date": "2024-03-01"}),
      ],
      final="""Done. Two functions:

- `list-events` on `GET /events`: all events, sorted by date;
- `add-event` on `POST /events` with `{"title": "...", "date": "2027-06-12"}`. A missing title, a wrong date or a date in the past gives 400 with the reason [docs/handlers.md#errors].

Checks:
- `pskit validate` (onprem): valid.
- "Summer cup" on 2027-06-12: 201.
- "Old game" on 2024-03-01: 400 "this date is in the past".

The events are kept in memory, so they are lost when the app restarts. For a real club app, a database is the next step. Test again: **Test** page or `pskit invoke -f add-event --method POST --path /events -d @event.json`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 333
    B(333, stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": yml("checkout", 8333, """functions:
  checkout:
    handler: app.checkout.checkout
    events:
    - http: POST /checkout
"""),
          "app/__init__.py": "",
          "app/checkout.py": fn("""

def checkout(event, ctx):
    rate = float(ctx.env.get("TAX_RATE", "0"))
    amount = float((event.http.json(default={}) or {}).get("amount", 0))
    return {"amount": amount, "tax": round(amount * rate, 2)}
"""),
          "requirements.txt": ""}),
      user="On AWS, TAX_RATE came from SSM: /checkout/dev/tax_rate = 0.20 and /checkout/prod/tax_rate = 0.19. No SSM here. Put both values in pskit.yml so the right one is used per stage.",
      steps=[
          S("get_project"),
          S("search_docs", query="per stage values custom self variable", docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["custom.tax_rate: '0.20' (default for dev and others)",
                                   "stages.prod.custom.tax_rate: '0.19'",
                                   "functions.checkout.environment.TAX_RATE: ${self:custom.tax_rate}",
                                   "Validate (onprem, prod), invoke with amount 100"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="custom", value={"tax_rate": "0.20"}),
          S("set_config", path="stages", value={"prod": {"custom": {"tax_rate": "0.19"}}}),
          S("set_config", path="functions.checkout.environment", value={"TAX_RATE": "${self:custom.tax_rate}"}),
          S("invoke_local", function="checkout", method="POST", path="/checkout", data={"amount": 100}),
      ],
      final="""Done. The two SSM values are now in `pskit.yml`:

```yaml
custom:
  tax_rate: "0.20"
stages:
  prod:
    custom:
      tax_rate: "0.19"
functions:
  checkout:
    environment:
      TAX_RATE: ${self:custom.tax_rate}
```

`stages.prod` overrides `custom.tax_rate` only for prod [docs/configuration.md#stages-per-stage-overrides], and `${self:custom.tax_rate}` picks the value for the stage you deploy.

Checks:
- `pskit validate` (onprem, prod): valid.
- Prod, `{"amount": 100}`: `{"amount": 100.0, "tax": 19.0}`, so 0.19 is used.

Dev and every other stage get 0.20. Deploy: `pskit deploy -s prod` (typed confirmation on the **Deploy** page)."""),

    # ------------------------------------------------------------------ 334
    B(334, stage="staging", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#retry-and-catch", "docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": yml("etl", 8334, """functions:
  extract:
    handler: app.etl.extract
  transform:
    handler: app.etl.transform
  load:
    handler: app.etl.load
workflows:
  nightly-etl:
    start_at: extract
    states:
      extract: {type: task, function: extract, next: transform}
      transform: {type: task, function: transform, next: load}
      load: {type: task, function: load, end: true}
"""),
          "app/__init__.py": "",
          "app/etl.py": fn("""
def extract(event, ctx):
    return {"rows": 10}


def transform(event, ctx):
    return dict(event.data or {}, clean=True)


def load(event, ctx):
    return dict(event.data or {}, loaded=True)
"""),
          "requirements.txt": ""}),
      user="nightly-etl: whole run max 30 min. load: retry any error 2x, 30s apart",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow retry any error interval timeout", docs=[D("docs/workflows.md", "retry-and-catch", words=150)]),
          S("propose_plan", steps=["workflows.nightly-etl.timeout: 1800",
                                   "states.load.retry: [{errors: ['*'], max_attempts: 2, interval_seconds: 30}]",
                                   "Validate (onprem, staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.nightly-etl.timeout", value=1800),
          S("set_config", path="workflows.nightly-etl.states.load.retry", value=[{"errors": ["*"], "max_attempts": 2, "interval_seconds": 30}]),
      ],
      final="""Done:

```yaml
workflows:
  nightly-etl:
    timeout: 1800
    states:
      load:
        type: task
        function: load
        end: true
        retry: [{errors: ["*"], max_attempts: 2, interval_seconds: 30}]
```

`"*"` matches any error [docs/workflows.md#retry-and-catch]. The default backoff rate 2.0 still applies, so the second wait is 60 s. Add `backoff_rate: 1` if both waits must be 30 s.

validate (onprem, staging): valid (embedded engine).

Run it: `pskit workflow run nightly-etl --history`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 335
    B(335, stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": yml("notify", 8335, """functions:
  api:
    handler: app.notify.api
    events:
    - http: POST /notify
"""),
          "app/__init__.py": "",
          "app/notify.py": fn("""
def api(event, ctx):
    return {"queued": True}, 202
"""),
          "requirements.txt": ""}),
      user="add worker for queue sms-out. every message has phone and text, just log it for now",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/sms.py`: log phone + text per message, fail only messages without phone",
                                   "Add `send-sms` on queue sms-out (batch 10)", "Validate for onprem, invoke with 2 messages"],
            result={"decision": "approved", "note": "batch 5 please, the sms gateway is slow. and failed ones to sms-failed after 4 tries"}),
          S("write_file", path="app/sms.py", content=fn("""from py_serverless_kit import BatchResult


def send_sms(event, ctx):
    result = BatchResult()
    for record in event.records:
        sms = record.json(default={}) or {}
        if not sms.get("phone"):
            ctx.logger.warning("sms without phone", extra={"record_id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("sms", extra={"phone": sms["phone"], "text": sms.get("text", "")})
    return result
""")),
          S("set_config", path="functions.send-sms",
            value={"handler": "app.sms.send_sms",
                   "events": [{"queue": {"name": "sms-out", "batch_size": 5, "dead_letter": "sms-failed", "max_receive": 4}}]}),
          S("invoke_local", function="send-sms", type="queue",
            data=[{"phone": "+15550100", "text": "Your code is 1234"}, {"text": "no phone"}]),
      ],
      final="""Done, with your changes (batch 5, `sms-failed` after 4 tries):

```yaml
functions:
  send-sms:
    handler: app.sms.send_sms
    events:
      - queue: {name: sms-out, batch_size: 5, dead_letter: sms-failed, max_receive: 4}
```

Each message's phone and text are logged. A message without `phone` is marked failed on its own with `BatchResult` [docs/handlers.md#batchresult]. After 4 tries it moves to `sms-failed` [docs/events.md#queue].

Checks:
- `pskit validate` (onprem): valid.
- 2 messages: only the second (no phone) is failed: `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`.

Test again: **Test** page or `pskit invoke -f send-sms -t queue -d @sms.json`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 336
    B(336, stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": yml("timesheet", 8080, """functions:
  hours:
    handler: app.hours.hours
    events:
    - http: GET /hours
""", "    host: 0.0.0.0\n"),
          "app/__init__.py": "",
          "app/hours.py": fn("""
def hours(event, ctx):
    return {"hours": 38}
"""),
          "requirements.txt": ""}),
      user="deploy say port 8080 already used, jenkins is on it. put my app on 8090",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.port: 8080 -> 8090", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.port", value=8090),
      ],
      final="""Done: `provider.options.port: 8090`. Each service needs its own port [docs/providers.md#onprem-on-premises], and Jenkins keeps 8080.

`pskit validate` (onprem): valid.

Deploy again: **Deploy** page or `pskit deploy -s dev`. Then open `http://<this pc>:8090/hours`, and update any bookmarks that use 8080.

In studio next time: **Overview & provider**, section **On-premises options**, field **Port**."""),

    # ------------------------------------------------------------------ 337
    B(337, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": yml("subscriptions", 8337, """functions:
  plans:
    handler: app.subs.plans
    events:
    - http: GET /plans
"""),
          "app/__init__.py": "",
          "app/subs.py": fn("""
def plans(event, ctx):
    return {"plans": ["basic", "pro"]}
"""),
          "requirements.txt": ""}),
      user="I want to remind people 3 days before their subscription ends. For now the list of subscriptions can be in the code, I'll connect our real data later.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/reminders.py`: `find_ending` (daily 07:00, puts one message per subscription ending in 3 days on the built-in queue `reminders`; only logs outside the host) and `send_reminder` (queue worker, logs who to remind)",
                                   "Add `find-ending` (schedule 0 7 * * *) and `send-reminder` (queue reminders, batch 10)",
                                   "Validate for onprem, run both"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/reminders.py", content=fn("""from datetime import date, timedelta

SUBSCRIPTIONS = [
    {"email": "ana@example.com", "ends": (date.today() + timedelta(days=3)).isoformat()},
    {"email": "ben@example.com", "ends": (date.today() + timedelta(days=20)).isoformat()},
]


def find_ending(event, ctx):
    target = (date.today() + timedelta(days=3)).isoformat()
    ending = [s for s in SUBSCRIPTIONS if s["ends"] == target]
    for sub in ending:
        if ctx.env.get("PSKIT_ONPREM_ROOT"):
            from py_serverless_kit.runtime.onprem_host import submit_queue

            submit_queue("reminders", sub)
        else:
            ctx.logger.info("would queue reminder", extra={"email": sub["email"]})
    return {"queued": len(ending)}


def send_reminder(event, ctx):
    for record in event.records:
        sub = record.json()
        ctx.logger.info("remind", extra={"email": sub["email"], "ends": sub["ends"]})
    return {"reminded": len(event.records)}
""")),
          S("set_config", path="functions.find-ending", value={"handler": "app.reminders.find_ending", "events": [{"schedule": "0 7 * * *"}]}),
          S("set_config", path="functions.send-reminder",
            value={"handler": "app.reminders.send_reminder", "events": [{"queue": {"name": "reminders", "batch_size": 10}}]}),
          S("invoke_local", function="find-ending", type="schedule"),
          S("invoke_local", function="send-reminder", type="queue", data=[{"email": "ana@example.com", "ends": "2026-11-04"}]),
      ],
      final="""Done, in two steps:

1. `find-ending` runs every day at 07:00 (UTC) [docs/events.md#schedule]. It finds subscriptions that end in exactly 3 days and puts one message per person on the built-in queue `reminders` (with `submit_queue`, which works inside the host [docs/providers.md#onprem-on-premises]).
2. `send-reminder` reads that queue, 10 at a time, and logs who to remind. That is where the real email goes later.

Checks:
- `pskit validate` (onprem): valid.
- `find-ending`: `{"queued": 1}` (ana's subscription ends in 3 days). On this computer it only logged "would queue reminder".
- `send-reminder` with ana's message: `{"reminded": 1}`.

When you connect your real data, replace `SUBSCRIPTIONS`. Test again: **Test** page or `pskit invoke -f find-ending -t schedule`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 338
    B(338, stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#errors", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": yml("accounts", 8338, """functions:
  get-user:
    handler: app.users.get_user
    events:
    - http: GET /users/{id}
"""),
          "app/__init__.py": "",
          "app/users.py": fn("""from py_serverless_kit import NotFound

USERS = {"7": {"id": "7", "name": "Kim", "email": "kim@example.com", "role": "user"}}


def get_user(event, ctx):
    user = USERS.get(event.http.path_params["id"])
    if user is None:
        raise NotFound("user not found")
    return user
"""),
          "requirements.txt": ""}),
      user="Add PATCH /users/{id}. Only `name` and `email` may be changed. If the body has any other field (like role), answer 400 and list those fields. Unknown user: 404. Return the updated user.",
      steps=[
          S("read_file", path="app/users.py"),
          S("propose_plan", steps=["Add `patch_user` to app/users.py: allowed = {name, email}, 400 listing extra fields, 404 unknown",
                                   "Add function `patch-user` on PATCH /users/{id}",
                                   "Validate (onprem, staging), invoke a good and a bad patch"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/users.py", content=fn("""from py_serverless_kit import BadRequest, NotFound

USERS = {"7": {"id": "7", "name": "Kim", "email": "kim@example.com", "role": "user"}}
ALLOWED = {"name", "email"}


def get_user(event, ctx):
    user = USERS.get(event.http.path_params["id"])
    if user is None:
        raise NotFound("user not found")
    return user


def patch_user(event, ctx):
    user = USERS.get(event.http.path_params["id"])
    if user is None:
        raise NotFound("user not found")
    body = event.http.json(default={}) or {}
    extra = sorted(set(body) - ALLOWED)
    if extra:
        raise BadRequest("these fields cannot be changed: " + ", ".join(extra))
    user.update({k: body[k] for k in ALLOWED if k in body})
    return user
""")),
          S("set_config", path="functions.patch-user", value={"handler": "app.users.patch_user", "events": [{"http": "PATCH /users/{id}"}]}),
          S("invoke_local", function="patch-user", method="PATCH", path="/users/7", data={"email": "kim@new.example.com"}),
          S("invoke_local", function="patch-user", method="PATCH", path="/users/7", data={"name": "Kim", "role": "admin"}),
      ],
      final="""Done. New function `patch-user` on `PATCH /users/{id}` [docs/events.md#http]:

- only `name` and `email` are applied;
- any other field gives **400** "these fields cannot be changed: role" (all extra fields, sorted) [docs/handlers.md#errors];
- unknown id: **404**.

Checks:
- `pskit validate` (onprem, staging): valid.
- `PATCH /users/7 {"email": "kim@new.example.com"}`: 200 with the new email, `role` unchanged.
- `PATCH /users/7 {"name": "Kim", "role": "admin"}`: 400 naming `role`, and nothing was changed.

Test again: **Test** page or `pskit invoke -f patch-user --method PATCH --path /users/7 -d '{"name": "Kim Lee"}'`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 339
    B(339, stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": yml("school", 8339, """functions:
  pupils:
    handler: app.main.pupils
    events:
    - http: GET /pupils
  welcome-mail:
    handler: app.main.welcome_mail
    events:
    - queue: welcome
  report-mail:
    handler: app.main.report_mail
    events:
    - schedule: 0 16 * * 5
"""),
          "app/__init__.py": "",
          "app/main.py": fn("""
def pupils(event, ctx):
    return {"pupils": ["Ada", "Tim"]}


def welcome_mail(event, ctx):
    ctx.logger.info("welcome mails", extra={"count": len(event.records)})
    return {"mails": len(event.records)}


def report_mail(event, ctx):
    ctx.logger.info("weekly report mail")
    return {"sent": True}
"""),
          "requirements.txt": ""}),
      user="My main.py is getting big. Can you put the two mail functions in their own file? Everything should work the same after.",
      steps=[
          S("read_file", path="app/main.py"),
          S("propose_plan", steps=["Move welcome_mail and report_mail to `app/mail.py`; keep pupils in app/main.py",
                                   "Change the handlers to app.mail.welcome_mail and app.mail.report_mail",
                                   "Validate, run both mail functions"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/mail.py", content=fn("""
def welcome_mail(event, ctx):
    ctx.logger.info("welcome mails", extra={"count": len(event.records)})
    return {"mails": len(event.records)}


def report_mail(event, ctx):
    ctx.logger.info("weekly report mail")
    return {"sent": True}
""")),
          S("write_file", path="app/main.py", content=fn("""
def pupils(event, ctx):
    return {"pupils": ["Ada", "Tim"]}
""")),
          S("set_config", path="functions.welcome-mail.handler", value="app.mail.welcome_mail"),
          S("set_config", path="functions.report-mail.handler", value="app.mail.report_mail"),
          S("invoke_local", function="welcome-mail", type="queue", data=[{"pupil": "Ada"}]),
          S("invoke_local", function="report-mail", type="schedule"),
      ],
      final="""Done:

- `app/mail.py` now has `welcome_mail` and `report_mail`, unchanged;
- `app/main.py` keeps only `pupils`;
- in `pskit.yml` the handlers are `app.mail.welcome_mail` and `app.mail.report_mail` (the handler is `package.module.function` [docs/handlers.md#handler-signatures]). Triggers did not change.

Checks:
- `pskit validate` (onprem): valid, so both handler modules are found.
- `welcome-mail` with one message: `{"mails": 1}`.
- `report-mail`: `{"sent": true}`.

The new file shows in **Code**. Test again: **Test** page or `pskit invoke -f report-mail -t schedule`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 340
    B(340, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={"pskit.yml": yml("hello", 8340, "functions: {}\n"), "requirements.txt": ""}),
      user="Can my app say hello with the name I type in the address? Like /hello/ana shows Hello, Ana!",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/hello.py`: read the name from the path, answer 'Hello, <Name>!' as text",
                                   "Add function `hello` on GET /hello/{name}", "Validate for onprem and try /hello/ana"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/hello.py", content=fn("""
def hello(event, ctx):
    name = event.http.path_params["name"]
    return f"Hello, {name.capitalize()}!"
""")),
          S("set_config", path="functions.hello", value={"handler": "app.hello.hello", "events": [{"http": "GET /hello/{name}"}]}),
          S("invoke_local", function="hello", method="GET", path="/hello/ana"),
      ],
      final="""Yes. The new function `hello` answers `GET /hello/{name}`. `{name}` is a path parameter, so whatever is in that part of the address arrives in `event.http.path_params["name"]` [docs/handlers.md#httprequest]. Returning a string sends plain text.

Checks:
- `pskit validate` (onprem): valid.
- `/hello/ana`: 200 `Hello, Ana!`.

Open it in the browser: run `pskit dev` and go to `http://127.0.0.1:3000/hello/ana`. Next time in studio: **Functions > + Create function**, step **Triggers**, **HTTP endpoint** with the route `/hello/{name}`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),
]
