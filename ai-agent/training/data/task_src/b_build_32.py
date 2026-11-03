"""Category B (build / add), batch 32 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 621
    B(621, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage", "docs/resources.md#fields"],
      project=dict(files={
          "pskit.yml": """service: picture-box
provider:
  name: aws
  region: eu-central-1
functions: {}
""",
          "requirements.txt": ""}),
      user="I want users to upload a picture and get a thumbnail. I have no idea where to start.",
      steps=[
          S("get_project"),
          S("ask_user", say="There are two common ways to do this, so let me check which one you want.",
            question="How should the pictures arrive?",
            options=["Users upload into a storage bucket, and a function makes the thumbnail when a file lands",
                     "Users send the picture straight to a web address (API) and get the thumbnail back"],
            answer="Users upload into a storage bucket, and a function makes the thumbnail when a file lands"),
          S("propose_plan", steps=["Add a managed bucket resource `pictures` (name picture-box-pictures-4410)",
                                   "Write app/thumbs.py: for each new .jpg under uploads/, decide the thumbnail key thumbs/<name>",
                                   "Add function make-thumbnail on storage {resource: pictures, prefix: uploads/, suffix: .jpg}",
                                   "Validate for aws, try it with a fake upload"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources", value={"pictures": {"type": "storage", "name": "picture-box-pictures-4410"}}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/thumbs.py", content=FUTURE + """

def make_thumbnail(event, ctx):
    done = []
    for record in event.records:
        name = record.key.rsplit("/", 1)[-1]
        target = "thumbs/" + name
        # TODO: download record.key, shrink it with Pillow, upload to `target`
        ctx.logger.info("thumbnail planned", extra={"source": record.key, "target": target, "size": record.size})
        done.append(target)
    return {"thumbnails": done}
"""),
          S("set_config", path="functions.make-thumbnail",
            value={"handler": "app.thumbs.make_thumbnail",
                   "events": [{"storage": {"resource": "pictures", "prefix": "uploads/", "suffix": ".jpg"}}]}),
          S("invoke_local", function="make-thumbnail", type="storage",
            data={"bucket": "picture-box-pictures-4410", "key": "uploads/cat.jpg", "size": 48213}),
      ],
      final="""Here is the starting point:

- **Bucket** `pictures` (S3 name `picture-box-pictures-4410`), created by pskit [docs/resources.md#fields].
- **Function** `make-thumbnail` runs every time a `.jpg` lands under `uploads/` [docs/events.md#storage]. It works out the thumbnail name (`uploads/cat.jpg` → `thumbs/cat.jpg`). The actual shrinking is a TODO: add `Pillow` and `boto3` to requirements.txt when you're ready.

Checks: `pskit validate` (aws) is valid, and a fake upload of `uploads/cat.jpg` returned `{"thumbnails": ["thumbs/cat.jpg"]}`.

Thumbnails go to `thumbs/`, outside `uploads/`, so they don't trigger the function again. Try it again on the **Test** page (storage event), then **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 622
    B(622, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: uptime-probe
provider:
  name: gcp
  region: us-central1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, uptime-probe-staging}
functions: {}
""",
          "requirements.txt": ""}),
      user="""Add a health function for our load balancer probes. Acceptance criteria:
1. GET /health returns 200 {"status": "ok", "stage": <stage>}
2. HEAD /health returns 204 with no body (the probe only checks the status)
3. Any other method on /health gets 405""",
      steps=[
          S("get_project"),
          S("search_docs", query="http method HEAD 405 routing",
            docs=[D("docs/events.md", "http", start="pskit's runtime also matches", end="the same `METHOD /path`.")]),
          S("propose_plan", steps=["Write app/health.py: HEAD -> None (204), GET -> {status, stage}",
                                   "Add function health with two routes: GET /health and HEAD /health (other methods get 405 from the runtime)",
                                   "Validate for gcp (staging), invoke GET and HEAD"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/health.py", content=FUTURE + """

def health(event, ctx):
    if event.http.method == "HEAD":
        return None
    return {"status": "ok", "stage": ctx.stage}
"""),
          S("set_config", path="functions.health",
            value={"handler": "app.health.health", "events": [{"http": "GET /health"}, {"http": "HEAD /health"}]}),
          S("invoke_local", function="health", method="GET", path="/health"),
          S("invoke_local", function="health", method="HEAD", path="/health"),
      ],
      final="""`health` is in place:

```yaml
functions:
  health:
    handler: app.health.health
    events:
      - http: GET /health
      - http: HEAD /health
```

1. GET /health → 200 `{"status": "ok", "stage": "staging"}` (checked locally).
2. HEAD /health → 204, no body (checked locally; `None` becomes 204 [docs/handlers.md#returning-a-response]).
3. Other methods → 405: the runtime matches routes itself on GCP and answers `405 Method Not Allowed` for a known path with another method [docs/events.md#http]. `pskit invoke` calls the function directly, so this one can only be seen on the deployed URL.

`pskit validate` (gcp, staging): valid. Test again on **Test** or `pskit invoke -f health --method HEAD --path /health -s staging`; deploy with **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 623
    B(623, provider="azure", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#provider-support", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: monthly-reports
provider:
  name: azure
  region: northeurope
functions:
  report:
    handler: app.report.build
    events:
    - schedule: "0 5 1 * *"
  api:
    handler: app.report.api
    events:
    - http: GET /reports
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """

def build(event, ctx):
    return {"built": True}


def api(event, ctx):
    return {"reports": []}
""",
          "requirements.txt": ""}),
      user="I'm on the Resources page. I need a place to save the report files, only the report function should know about it. Can you add it?",
      steps=[
          S("get_project"),
          S("search_docs", query="azure managed storage container resource bound functions",
            docs=[D("docs/resources.md", "provider-support", start="| azure |", end="every function there sees every binding.")]),
          S("propose_plan", steps=["Add resource `exports`: type storage (a blob container pskit creates), functions: [report]",
                                   "report: read resource(\"exports\").native_name and log it",
                                   "Validate for azure, run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources", value={"exports": {"type": "storage", "functions": ["report"]}}),
          S("write_file", path="app/report.py", content=FUTURE + """from py_serverless_kit import resource


def build(event, ctx):
    exports = resource("exports")
    # TODO: upload the report with azure-storage-blob into this container
    ctx.logger.info("report target", extra={"container": exports.native_name})
    return {"built": True, "container": exports.native_name}


def api(event, ctx):
    return {"reports": []}
"""),
          S("validate"),
          S("invoke_local", function="report", type="schedule"),
      ],
      final="""Added a storage resource `exports`; on Azure it becomes a blob container that pskit creates:

```yaml
resources:
  exports:
    type: storage
    functions: [report]
```

- `report` reads it with `resource("exports")` [docs/resources.md#runtime-api]; locally it logged `container: exports`. Uploading the file is a TODO (azure-storage-blob).
- `pskit validate` (azure): valid. The scheduled run returned `{"built": true, "container": "exports"}`.
- One Azure detail: app settings are shared by the whole Function App, so `api` will see the binding too [docs/resources.md#provider-support]. The `functions:` list still documents the intent and narrows it on other clouds.

To do this yourself next time: **Resources > + Add resource**. Deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 624
    B(624, provider="aws", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: geo-batch
provider:
  name: aws
  region: us-west-2
functions:
  geocode:
    handler: app.geo.geocode
    timeout: 150
    events:
    - queue:
        name: geocode-jobs
        batch_size: 25
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + """

def geocode(event, ctx):
    return {"done": len(event.records)}
""",
          "requirements.txt": ""}),
      user="geocode-jobs: visibility_timeout 900 explicit, dlq geocode-dlq, max_receive 4",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.geocode.events.0.queue += visibility_timeout 900, dead_letter geocode-dlq, max_receive 4",
                                   "Validate aws prod"]),
          S("set_config", path="functions.geocode.events.0.queue",
            value={"name": "geocode-jobs", "batch_size": 25, "visibility_timeout": 900,
                   "dead_letter": "geocode-dlq", "max_receive": 4}),
      ],
      final="""```yaml
- queue:
    name: geocode-jobs
    batch_size: 25
    visibility_timeout: 900
    dead_letter: geocode-dlq
    max_receive: 4
```

- Explicit 900 s replaces the default `max(30, 6 x timeout)` (= 900 here anyway with timeout 150) [docs/events.md#queue]; it now stays fixed if the timeout changes.
- After 4 receives a message goes to `geocode-dlq` (redrive policy).
- `pskit validate` (aws, prod): valid.

Deploy: **Deploy** (typed confirmation for prod) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 625
    B(625, provider="gcp", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, catalog-dev-3}
functions:
  items:
    handler: app.items.list_items
    events:
    - http:
        path: /items
        method: GET
        cors:
          origins: [https://shop.example.com]
""",
          "app/__init__.py": "",
          "app/items.py": FUTURE + """
ITEMS = [{"id": i, "name": f"item {i}"} for i in range(1, 8)]


def list_items(event, ctx):
    return ITEMS
""",
          "requirements.txt": ""}),
      user="my js do fetch /items and read header X-Total-Count but its always null in browser. in postman header is there?? also api dont send it yet i think",
      steps=[
          S("get_project"),
          S("search_docs", query="cors expose headers",
            docs=[D("docs/events.md", "http", start="**CORS**", end="AWS additionally configures CORS on the HTTP API.")]),
          S("propose_plan", steps=["items: return the list with header X-Total-Count",
                                   "cors.expose_headers: [X-Total-Count] so browser JS may read it",
                                   "Validate for gcp, invoke GET /items"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/items.py", content=FUTURE + """
ITEMS = [{"id": i, "name": f"item {i}"} for i in range(1, 8)]


def list_items(event, ctx):
    return ITEMS, 200, {"X-Total-Count": str(len(ITEMS))}
"""),
          S("set_config", path="functions.items.events.0.http.cors",
            value={"origins": ["https://shop.example.com"], "expose_headers": ["X-Total-Count"]}),
          S("invoke_local", function="items", method="GET", path="/items"),
      ],
      final="""Two things were missing:

1. The handler didn't send the header. Now it returns `(ITEMS, 200, {"X-Total-Count": "7"})`.
2. Browsers hide response headers from JavaScript unless CORS exposes them; Postman doesn't apply CORS, that's why you saw it there. Added:

```yaml
functions:
  items:
    events:
      - http:
          path: /items
          method: GET
          cors:
            origins: [https://shop.example.com]
            expose_headers: [X-Total-Count]
```
[docs/events.md#http]

Checks: `pskit validate` (gcp) valid; local GET /items gives 200 with `X-Total-Count: 7`. The `Access-Control-Expose-Headers` header is only added when a request has an `Origin`, so check it in the browser after **Deploy** (or `pskit deploy -s dev`)."""),

    # ------------------------------------------------------------------ 626
    B(626, provider="azure", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: sessions
provider:
  name: azure
  region: westeurope
functions:
  login:
    handler: app.sessions.login
    events:
    - http: POST /login
""",
          "app/__init__.py": "",
          "app/sessions.py": FUTURE + """

def login(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="add timer fn purge-sessions, every 30 min, delete expired sessions (stub ok)",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add purge(event, ctx) to app/sessions.py (stub, returns purged count)",
                                   "Add function purge-sessions with schedule: 30 minutes",
                                   "Validate for azure, invoke the schedule"],
            result={"decision": "approved",
                    "note": "make it every 15 minutes, name the schedule purge-sessions, and pass input {max_age_hours: 12}"}),
          S("write_file", say="Following your note: every 15 minutes, named schedule, input max_age_hours 12.",
            path="app/sessions.py", content=FUTURE + """

def login(event, ctx):
    return {"ok": True}


def purge(event, ctx):
    max_age = int((event.data or {}).get("max_age_hours", 24))
    # TODO: delete sessions older than max_age hours from the session store
    ctx.logger.info("purging sessions", extra={"max_age_hours": max_age})
    return {"purged": 0, "max_age_hours": max_age}
"""),
          S("set_config", path="functions.purge-sessions",
            value={"handler": "app.sessions.purge",
                   "events": [{"schedule": {"rate": "15 minutes", "name": "purge-sessions",
                                            "input": {"max_age_hours": 12}}}]}),
          S("invoke_local", function="purge-sessions", type="schedule"),
      ],
      final="""Done, with your changes (15 minutes, named, input):

```yaml
functions:
  purge-sessions:
    handler: app.sessions.purge
    events:
      - schedule:
          rate: 15 minutes
          name: purge-sessions
          input: {max_age_hours: 12}
```

- `input` arrives as `event.data` [docs/events.md#schedule]; the handler reads `max_age_hours` (default 24). The delete itself is a stub.
- `pskit validate` (azure): valid. Scheduled run: `{"purged": 0, "max_age_hours": 12}`.

Test again: `pskit invoke -f purge-sessions -t schedule`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 627
    B(627, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: order-alerts
provider:
  name: aws
  region: us-east-1
functions: {}
""",
          "requirements.txt": ""}),
      user="Subscribe a new function `big-order-alert` to the SNS topic `orders` (pskit creates it). SNS should only deliver messages whose numeric attribute `amount` is >= 1000; we don't want to pay for invocations of small orders. The function logs order_id and amount.",
      steps=[
          S("get_project"),
          S("search_docs", query="topic filter policy sns",
            docs=[D("docs/events.md", "topic", end="| onprem | file topic, fan-out | exact match on attributes, then on JSON body fields |")]),
          S("propose_plan", steps=["Write app/alerts.py: log order_id and amount of each record",
                                   "Add big-order-alert on topic orders with filter {amount: [{numeric: [\">=\", 1000]}]} (SNS filter policy)",
                                   "Validate for aws, invoke with one big order"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/alerts.py", content=FUTURE + """

def big_order(event, ctx):
    for record in event.records:
        order = record.json()
        ctx.logger.warning("big order", extra={"order_id": order.get("order_id"), "amount": order.get("amount")})
    return {"alerts": len(event.records)}
"""),
          S("set_config", path="functions.big-order-alert",
            value={"handler": "app.alerts.big_order",
                   "events": [{"topic": {"name": "orders", "filter": {"amount": [{"numeric": [">=", 1000]}]}}}]}),
          S("invoke_local", function="big-order-alert", type="topic", data={"order_id": "o-881", "amount": 2400}),
      ],
      final="""```yaml
functions:
  big-order-alert:
    handler: app.alerts.big_order
    events:
      - topic:
          name: orders
          filter:
            amount: [{numeric: [">=", 1000]}]
```

- On AWS `filter` is the SNS filter policy, so small orders never invoke the function [docs/events.md#topic]. It matches **message attributes**: publishers must send `amount` as a `Number` attribute, not only inside the body.
- `pskit validate` (aws): valid.
- Local run with order o-881 / 2400: a `big order` warning log and `{"alerts": 1}`. The filter is applied by SNS, not by `pskit invoke`.

Test again on **Test** (topic event) or `pskit invoke -f big-order-alert -t topic -d '{"order_id": "o-881", "amount": 2400}'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 628
    B(628, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#data-flow"],
      project=dict(files={
          "pskit.yml": """service: shop-checkout
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, shop-checkout-dev}
functions:
  charge:
    handler: app.pay.charge
workflows:
  checkout:
    start_at: Charge
    states:
      Charge:
        type: task
        function: charge
        end: true
""",
          "app/__init__.py": "",
          "app/pay.py": FUTURE + """

def charge(event, ctx):
    data = event.data or {}
    settings = data.get("settings", {})
    return {"charged": data.get("amount"), "currency": settings.get("currency", "?")}
""",
          "requirements.txt": ""}),
      user="I'm on the Workflows page with my checkout workflow. charge needs to know the currency (always EUR) and the shop id (shop-12). I don't want to change the callers. Can the workflow just add that before charging?",
      steps=[
          S("get_project"),
          S("search_docs", query="pass state result inject value",
            docs=[D("docs/workflows.md", "state-types", start="| `pass` |", end="| `pass` |"),
                  D("docs/workflows.md", "data-flow", start="- `result_path` says", end="passes the input through.")]),
          S("propose_plan", steps=["Add a pass state AddSettings first: result {currency: EUR, shop_id: shop-12}, result_path $.settings",
                                   "start_at -> AddSettings, then Charge",
                                   "Validate for gcp, run charge with the input it will now receive"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.checkout",
            value={"start_at": "AddSettings",
                   "states": {"AddSettings": {"type": "pass", "result": {"currency": "EUR", "shop_id": "shop-12"},
                                              "result_path": "$.settings", "next": "Charge"},
                              "Charge": {"type": "task", "function": "charge", "end": True}}}),
          S("invoke_local", function="charge", type="workflow",
            data={"amount": 19.9, "settings": {"currency": "EUR", "shop_id": "shop-12"}}),
      ],
      final="""Yes. A `pass` state injects fixed values without calling any function [docs/workflows.md#state-types]:

```yaml
workflows:
  checkout:
    start_at: AddSettings
    states:
      AddSettings:
        type: pass
        result: {currency: EUR, shop_id: shop-12}
        result_path: $.settings
        next: Charge
      Charge: {type: task, function: charge, end: true}
```

`result_path: $.settings` keeps the caller's input and adds the values under `settings` [docs/workflows.md#data-flow], so callers don't change.

- `pskit validate` (gcp): valid (Cloud Workflows).
- `charge` with that input returned `{"charged": 19.9, "currency": "EUR"}`.

Run the whole workflow: **Deploy > Run a workflow locally**, or `pskit workflow run checkout -i '{"amount": 19.9}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 629
    B(629, provider="azure", stage="staging", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: storefront
provider:
  name: azure
  region: westeurope
  environment:
    LOG_LEVEL: INFO
functions:
  list-orders:
    handler: app.orders.list_orders
    events:
    - http: GET /api/v1/orders
  get-order:
    handler: app.orders.get_order
    events:
    - http: GET /api/v1/orders/{id}
  create-order:
    handler: app.orders.create_order
    events:
    - http: POST /api/v1/orders
  products:
    handler: app.catalog.products
    events:
    - http: GET /api/v1/products
  nightly-sync:
    handler: app.catalog.sync
    events:
    - schedule: "0 2 * * *"
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def list_orders(event, ctx):
    return []


def get_order(event, ctx):
    return {"id": event.http.path_params["id"]}


def create_order(event, ctx):
    return {"created": True}, 201
""",
          "app/catalog.py": FUTURE + """

def products(event, ctx):
    return []


def sync(event, ctx):
    return {"synced": 0}
""",
          "requirements.txt": ""}),
      user="get-order only: move to /api/v2/orders/{id}. rest stays v1",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.get-order.events.0: http GET /api/v2/orders/{id}",
                                   "Validate azure staging, invoke GET /api/v2/orders/42"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.get-order.events.0", value={"http": "GET /api/v2/orders/{id}"}),
          S("invoke_local", function="get-order", method="GET", path="/api/v2/orders/42"),
      ],
      final="""Changed one line:

```yaml
functions:
  get-order:
    handler: app.orders.get_order
    events:
      - http: GET /api/v2/orders/{id}
```

The other four functions are untouched. `pskit validate` (azure, staging): valid; GET /api/v2/orders/42 → 200 `{"id": "42"}`.

The old `/api/v1/orders/{id}` route disappears on the next **Deploy** (`pskit deploy -s staging`), so update clients first or keep both routes for a while (add a second `- http:` line)."""),

    # ------------------------------------------------------------------ 630
    B(630, provider="aws", stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: drafts
provider:
  name: aws
  region: eu-west-1
functions:
  preview:
    handler: app.preview.page
    events:
    - http: GET /preview/{slug}
""",
          "app/__init__.py": "",
          "app/preview.py": FUTURE + """from py_serverless_kit import Response


def page(event, ctx):
    slug = event.http.path_params["slug"]
    return Response.html(f"<h1>Draft: {slug}</h1>")
""",
          "requirements.txt": ""}),
      user="google index my preview pages, bad. add header X-Robots-Tag noindex to preview response pls",
      steps=[
          S("get_project"),
          S("read_file", path="app/preview.py"),
          S("propose_plan", steps=["app/preview.py: Response.html(..., headers={\"X-Robots-Tag\": \"noindex\"})",
                                   "Validate aws, invoke GET /preview/spring-sale"]),
          S("write_file", path="app/preview.py", content=FUTURE + """from py_serverless_kit import Response


def page(event, ctx):
    slug = event.http.path_params["slug"]
    return Response.html(f"<h1>Draft: {slug}</h1>", headers={"X-Robots-Tag": "noindex"})
"""),
          S("validate"),
          S("invoke_local", function="preview", method="GET", path="/preview/spring-sale"),
      ],
      final="""Done. `preview` now sends `X-Robots-Tag: noindex`, so search engines drop the pages from their index [docs/handlers.md#returning-a-response].

- `pskit validate` (aws): valid.
- GET /preview/spring-sale → 200 HTML with `x-robots-tag: noindex`.

Pages already indexed disappear after Google crawls them again. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 631
    B(631, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: inventory
provider:
  name: gcp
  region: europe-west4
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, inventory-dev-7}
functions: {}
""",
          "requirements.txt": ""}),
      user="""New function `store-item` on GET /stores/{store_id}/items/{item_id}. Use sample data: store s1 has items i1 (qty 4) and i2 (qty 0).
- unknown store -> 404 "store not found"
- known store, unknown item -> 404 "item not found"
- otherwise 200 {store_id, item_id, qty, in_stock}""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/stores.py with the sample data and the two 404s (NotFound)",
                                   "Add function store-item on GET /stores/{store_id}/items/{item_id}",
                                   "Validate for gcp, invoke s1/i2 and an unknown store"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/stores.py", content=FUTURE + """from py_serverless_kit import NotFound

STORES = {"s1": {"i1": 4, "i2": 0}}


def store_item(event, ctx):
    params = event.http.path_params
    items = STORES.get(params["store_id"])
    if items is None:
        raise NotFound("store not found")
    if params["item_id"] not in items:
        raise NotFound("item not found")
    qty = items[params["item_id"]]
    return {"store_id": params["store_id"], "item_id": params["item_id"], "qty": qty, "in_stock": qty > 0}
"""),
          S("set_config", path="functions.store-item",
            value={"handler": "app.stores.store_item", "events": [{"http": "GET /stores/{store_id}/items/{item_id}"}]}),
          S("invoke_local", function="store-item", method="GET", path="/stores/s1/items/i2"),
          S("invoke_local", function="store-item", method="GET", path="/stores/s9/items/i1"),
      ],
      final="""`store-item` is added on `GET /stores/{store_id}/items/{item_id}`. Both parameters arrive in `event.http.path_params` [docs/events.md#http].

| Check | Result |
|---|---|
| `pskit validate` (gcp) | valid |
| GET /stores/s1/items/i2 | 200 `{"store_id": "s1", "item_id": "i2", "qty": 0, "in_stock": false}` |
| GET /stores/s9/items/i1 | 404 `{"error": "store not found", "status": 404}` |

The "item not found" branch raises the same `NotFound` [docs/handlers.md#errors]. Try other ids on **Test** or with `pskit invoke -f store-item --method GET --path /stores/s1/items/i1`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 632
    B(632, provider="azure", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/providers.md#azure-azure-functions", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: claims
provider:
  name: azure
  region: westeurope
functions:
  submit:
    handler: app.claims.submit
    events:
    - http: POST /claims
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + """

def submit(event, ctx):
    return {"accepted": True}, 202
""",
          "requirements.txt": ""}),
      user="On AWS we only paid for CloudWatch Logs. Here every stage creates Application Insights and the dev bill is silly. Can dev go without it while staging and prod keep it?",
      steps=[
          S("get_project"),
          S("search_docs", query="azure app_insights option",
            docs=[D("docs/providers.md", "azure-azure-functions", words=190)]),
          S("propose_plan", steps=["stages.dev.provider.options.app_insights: false (default stays true elsewhere)",
                                   "Validate for azure (dev)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"dev": {"provider": {"options": {"app_insights": False}}}}),
      ],
      final="""```yaml
stages:
  dev:
    provider:
      options:
        app_insights: false
```

- `app_insights` defaults to `true` [docs/providers.md#azure-azure-functions]; the stage override turns it off for dev only [docs/configuration.md#stages-per-stage-overrides]. Staging and prod keep it.
- `pskit validate` (azure, dev): valid.

Without Application Insights, dev has no Azure log/trace view, so local runs (`pskit invoke`, **Test**) become the main way to debug there. Deploy dev: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 633
    B(633, provider="aws", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#fields", "docs/resources.md#secrets"],
      project=dict(files={
          "pskit.yml": """service: docs-search
provider:
  name: aws
  region: eu-west-1
functions:
  search:
    handler: app.search.search
    events:
    - http: GET /search
  reindex:
    handler: app.search.reindex
    events:
    - schedule: 1 day
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """

def search(event, ctx):
    return {"hits": []}


def reindex(event, ctx):
    return {"indexed": 0}
""",
          "requirements.txt": ""}),
      user="We use a hosted search SaaS. Register it as an external `custom` resource `search-engine`: url https://search.example.com, index `docs-dev`, and the API key comes from the env var SEARCH_API_KEY (name only, never the value). Only `search` gets it. For now `search` should just return which url and index it would query.",
      steps=[
          S("get_project"),
          S("search_docs", query="custom resource connection secret env name",
            docs=[D("docs/resources.md", "secrets", end="never values.")]),
          S("propose_plan", steps=["resources.search-engine: type custom, external true, connection {url, index, api_key_env: SEARCH_API_KEY}, functions [search]",
                                   "app/search.py: read resource(\"search-engine\") and return url + index + whether the key is set",
                                   "Validate for aws, invoke GET /search?q=pskit"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources",
            value={"search-engine": {"type": "custom", "external": True,
                                     "connection": {"url": "https://search.example.com", "index": "docs-dev",
                                                    "api_key_env": "SEARCH_API_KEY"},
                                     "functions": ["search"]}}),
          S("write_file", path="app/search.py", content=FUTURE + """from py_serverless_kit import resource


def search(event, ctx):
    engine = resource("search-engine")
    key_set = bool(ctx.env.get(engine["api_key_env"]))
    return {"url": engine["url"], "index": engine["index"], "q": event.http.query.get("q", ""), "key_set": key_set}


def reindex(event, ctx):
    return {"indexed": 0}
"""),
          S("validate"),
          S("invoke_local", function="search", method="GET", path="/search?q=pskit"),
      ],
      final="""```yaml
resources:
  search-engine:
    type: custom
    external: true
    connection:
      url: https://search.example.com
      index: docs-dev
      api_key_env: SEARCH_API_KEY
    functions: [search]
```

- pskit never creates a `custom` resource, it only hands the connection to `search` [docs/resources.md#fields]. `reindex` doesn't get it.
- Only the **name** of the key variable is in pskit.yml, as recommended [docs/resources.md#secrets]; the handler reads the value with `ctx.env[engine["api_key_env"]]`.
- `pskit validate` (aws): valid.
- GET /search?q=pskit → `{"url": "https://search.example.com", "index": "docs-dev", "q": "pskit", "key_set": false}`. `key_set` is false because SEARCH_API_KEY isn't set locally.

See the usage snippet under **Resources > How to use**. Deploy: **Deploy** or `pskit deploy -s dev`, with SEARCH_API_KEY set in the function environment."""),

    # ------------------------------------------------------------------ 634
    B(634, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": """service: payouts
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, payouts-prod-2}
functions:
  send-payout:
    handler: app.payout.send
  notify-failure:
    handler: app.payout.notify
workflows:
  payout:
    start_at: Send
    states:
      Send:
        type: task
        function: send-payout
        end: true
""",
          "app/__init__.py": "",
          "app/payout.py": FUTURE + """

def send(event, ctx):
    return {"sent": True, **(event.data or {})}


def notify(event, ctx):
    return {"notified": True}
""",
          "requirements.txt": ""}),
      user="payout: any error in Send -> Notify (notify-failure) with error info at $.error, then fail state PayoutFailed. notify should log payout_id + error",
      steps=[
          S("get_project"),
          S("search_docs", query="catch result_path error next",
            docs=[D("docs/workflows.md", "retry-and-catch")]),
          S("propose_plan", steps=["Send: catch [{errors: [\"*\"], next: Notify, result_path: $.error}]",
                                   "Notify: task notify-failure, next PayoutFailed; PayoutFailed: fail (error PayoutFailed)",
                                   "app/payout.py notify: log payout_id + error",
                                   "Validate gcp prod, invoke notify-failure with a sample error"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/payout.py", content=FUTURE + """

def send(event, ctx):
    return {"sent": True, **(event.data or {})}


def notify(event, ctx):
    data = event.data or {}
    err = data.get("error") or {}
    ctx.logger.error("payout failed", extra={"payout_id": data.get("payout_id"),
                                             "error": err.get("error"), "cause": err.get("cause")})
    return data
"""),
          S("set_config", path="workflows.payout.states",
            value={"Send": {"type": "task", "function": "send-payout", "end": True,
                            "catch": [{"errors": ["*"], "next": "Notify", "result_path": "$.error"}]},
                   "Notify": {"type": "task", "function": "notify-failure", "next": "PayoutFailed"},
                   "PayoutFailed": {"type": "fail", "error": "PayoutFailed", "cause": "payout could not be sent"}}),
          S("invoke_local", function="notify-failure", type="workflow",
            data={"payout_id": "po-311", "error": {"error": "ConnectionError", "cause": "bank API unreachable"}}),
      ],
      final="""```yaml
states:
  Send:
    type: task
    function: send-payout
    end: true
    catch:
      - {errors: ["*"], next: Notify, result_path: $.error}
  Notify: {type: task, function: notify-failure, next: PayoutFailed}
  PayoutFailed: {type: fail, error: PayoutFailed, cause: payout could not be sent}
```

- The catcher keeps the input and stores `{"error", "cause"}` at `$.error` [docs/workflows.md#retry-and-catch]; Notify logs it, then the run ends failed.
- `pskit validate` (gcp, prod): valid.
- notify-failure with po-311 / ConnectionError: ERROR log `payout failed` with both fields; it passes the data on.

Try the flow: `pskit workflow run payout -i '{"payout_id": "po-311"}' --history -s prod` (local). Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 635
    B(635, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: pass-check
provider:
  name: azure
  region: swedencentral
functions: {}
""",
          "requirements.txt": ""}),
      user="for my signup page i want something that tells people if their passphrase is weak, ok or strong while they type. can you make that?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/strength.py: score length, digits, upper/lower case and symbols -> weak / ok / strong",
                                   "Add function strength on POST /strength ({passphrase}); missing value -> 400",
                                   "Validate for azure, try one passphrase locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/strength.py", content=FUTURE + """from py_serverless_kit import BadRequest


def strength(event, ctx):
    body = event.http.json(default={}) or {}
    phrase = body.get("passphrase")
    if not isinstance(phrase, str) or not phrase:
        raise BadRequest("send {\\"passphrase\\": \\"...\\"}")
    score = 0
    score += len(phrase) >= 12
    score += len(phrase) >= 20
    score += any(c.isdigit() for c in phrase)
    score += any(c.isupper() for c in phrase) and any(c.islower() for c in phrase)
    score += any(not c.isalnum() for c in phrase)
    level = "weak" if score <= 1 else "ok" if score <= 3 else "strong"
    # never log the passphrase itself
    return {"level": level, "score": score}
"""),
          S("set_config", path="functions.strength",
            value={"handler": "app.strength.strength", "events": [{"http": "POST /strength"}]}),
          S("invoke_local", function="strength", method="POST", path="/strength",
            data={"passphrase": "Correct horse battery staple 9"}),
      ],
      final="""Your strength checker is ready:

- `POST /strength` with `{"passphrase": "..."}` answers `{"level": "weak" | "ok" | "strong", "score": n}`. Points for length (12+, 20+), digits, mixed case and symbols.
- Nothing sent → 400 with a short hint.
- The passphrase is never logged or stored.

Checks: `pskit validate` (azure) valid; "Correct horse battery staple 9" came back **strong**.

Your page can call it on each key press (or after a short pause). If the page is on another domain, ask me to add CORS. Try it on **Test** > **▶ Run locally**, then **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 636
    B(636, provider="aws", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: fulfil
provider:
  name: aws
  region: eu-west-1
functions:
  reserve:
    handler: app.steps.reserve
  charge:
    handler: app.steps.charge
workflows:
  order:
    start_at: Reserve
    states:
      Reserve:
        type: task
        function: reserve
        next: Charge
      Charge:
        type: task
        function: charge
        end: true
""",
          "app/__init__.py": "",
          "app/steps.py": FUTURE + """

def reserve(event, ctx):
    return {**(event.data or {}), "reserved": True}


def charge(event, ctx):
    return {**(event.data or {}), "charged": True}
""",
          "requirements.txt": ""}),
      user="In our ASL we had TimeoutSeconds: 600 on the state machine and TimeoutSeconds: 30 on the Charge task (the payment provider hangs sometimes). Where do those go in pskit?",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow timeout task timeout_seconds",
            docs=[D("docs/workflows.md", "workflow-keys", start="| `timeout` |", end="| `timeout` |"),
                  D("docs/workflows.md", "state-types", start="| `task` |", end="| `task` |")]),
          S("propose_plan", steps=["workflows.order.timeout: 600 (state machine TimeoutSeconds)",
                                   "states.Charge.timeout_seconds: 30 (task TimeoutSeconds)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.order.timeout", value=600),
          S("set_config", path="workflows.order.states.Charge.timeout_seconds", value=30),
      ],
      final="""Same two settings, pskit names:

```yaml
workflows:
  order:
    timeout: 600
    start_at: Reserve
    states:
      Reserve: {type: task, function: reserve, next: Charge}
      Charge:
        type: task
        function: charge
        timeout_seconds: 30
        end: true
```

- `timeout` on the workflow becomes the state machine's `TimeoutSeconds` on AWS [docs/workflows.md#workflow-keys].
- `timeout_seconds` is a task field [docs/workflows.md#state-types]; a hung Charge now fails with a timeout after 30 s instead of holding the run.
- `pskit validate` (aws): valid.

If a Charge timeout should go somewhere instead of failing the run, add a `catch` on Charge. Check the generated ASL with `pskit workflow show order --format asl`; deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 637
    B(637, provider="gcp", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage", "docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=dict(files={
          "pskit.yml": """service: gallery
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, gallery-dev-12}
functions:
  index-image:
    handler: app.images.index
    events:
    - storage:
        bucket: gallery-uploads-8812
        suffix: .png
""",
          "app/__init__.py": "",
          "app/images.py": FUTURE + """

def index(event, ctx):
    return {"indexed": [r.key for r in event.records]}
""",
          "requirements.txt": ""}),
      user="index-image only run for .png. need also .jpg files, suffix take only one value?",
      steps=[
          S("get_project"),
          S("search_docs", query="storage suffix filter several", docs=[D("docs/events.md", "storage", end="Each record has `bucket`, `key`, `size` and `action`")]),
          S("propose_plan", steps=["Add a second storage event on gallery-uploads-8812 with suffix .jpg",
                                   "Validate gcp, invoke with a .jpg"]),
          S("set_config", path="functions.index-image.events",
            value=[{"storage": {"bucket": "gallery-uploads-8812", "suffix": ".png"}},
                   {"storage": {"bucket": "gallery-uploads-8812", "suffix": ".jpg"}}]),
          S("invoke_local", function="index-image", type="storage",
            data={"bucket": "gallery-uploads-8812", "key": "2026/beach.jpg"}),
      ],
      final="""Yes, `suffix` is one string [docs/events.md#storage]. So now there are two storage events on the same bucket:

```yaml
events:
  - storage: {bucket: gallery-uploads-8812, suffix: .png}
  - storage: {bucket: gallery-uploads-8812, suffix: .jpg}
```

- On GCP each event trigger becomes its own deployment (`index-image-storage0`, `index-image-storage1`), same code [docs/events.md#gcp-multi-trigger-functions-are-split-automatically]. `pskit info` still shows one function.
- `pskit validate` (gcp): valid. Test with `2026/beach.jpg` → `{"indexed": ["2026/beach.jpg"]}`.

`.jpeg` or `.JPG` files are not matched; add more lines if you have them. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 638
    B(638, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#events-backed-by-a-resource"],
      project=dict(files={
          "pskit.yml": """service: mailer
provider:
  name: azure
  region: westeurope
resources:
  email-outbox:
    type: queue
  email-retry:
    type: queue
functions:
  api:
    handler: app.mail.api
    events:
    - http: POST /mail
  notify:
    handler: app.mail.notify
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """

def api(event, ctx):
    return {"queued": True}, 202


def notify(event, ctx):
    sent = []
    for record in event.records:
        sent.append(record.json().get("to"))
    return {"sent": sent}
""",
          "requirements.txt": ""}),
      user="connect notify to the email queue pls",
      steps=[
          S("get_project"),
          S("ask_user", say="The project has two queue resources, so I need to know which one.",
            question="Which queue should trigger notify?",
            options=["email-outbox", "email-retry", "both"],
            answer="email-outbox. retry is for later"),
          S("propose_plan", steps=["functions.notify.events: [queue {resource: email-outbox}]",
                                   "Validate for azure, invoke notify with one message"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.notify.events", value=[{"queue": {"resource": "email-outbox"}}]),
          S("invoke_local", function="notify", type="queue", data=[{"to": "ana@example.com"}]),
      ],
      final="""`notify` now runs for messages on `email-outbox`:

```yaml
functions:
  notify:
    handler: app.mail.notify
    events:
      - queue: {resource: email-outbox}
```

The event uses the resource's queue name, so nothing is duplicated [docs/events.md#events-backed-by-a-resource]. `email-retry` stays without a consumer for now.

- `pskit validate` (azure): valid.
- One test message to ana@example.com → `{"sent": ["ana@example.com"]}`.

In studio you can do the same on **Functions > notify > Add a trigger**. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 639
    B(639, provider="aws", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: telemetry
provider:
  name: aws
  region: eu-north-1
functions: {}
""",
          "requirements.txt": ""}),
      user="""Add `ingest` on POST /events. Requirements:
- Content-Type must be application/json, otherwise 415 {"error": "send JSON"}
- body is a list of events, at most 500, otherwise 413
- each event needs `name`; answer 202 {"accepted": n, "rejected": m}""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/ingest.py: check event.http.content_type, list size, count events with/without name",
                                   "415 and 413 as (body, status) returns",
                                   "Add function ingest on POST /events",
                                   "Validate for aws (staging), invoke with 3 events (one without name)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/ingest.py", content=FUTURE + """from py_serverless_kit import BadRequest

MAX_EVENTS = 500


def ingest(event, ctx):
    req = event.http
    if not (req.content_type or "").startswith("application/json"):
        return {"error": "send JSON"}, 415
    items = req.json(default=None)
    if not isinstance(items, list):
        raise BadRequest("body must be a JSON list")
    if len(items) > MAX_EVENTS:
        return {"error": f"at most {MAX_EVENTS} events per request"}, 413
    accepted = sum(1 for e in items if isinstance(e, dict) and e.get("name"))
    return {"accepted": accepted, "rejected": len(items) - accepted}, 202
"""),
          S("set_config", path="functions.ingest", value={"handler": "app.ingest.ingest", "events": [{"http": "POST /events"}]}),
          S("invoke_local", function="ingest", method="POST", path="/events",
            data=[{"name": "page_view"}, {"name": "click"}, {"value": 3}]),
      ],
      final="""`ingest` is added on `POST /events`:

- Not JSON → 415 `{"error": "send JSON"}` (checks `event.http.content_type` [docs/handlers.md#httprequest]).
- More than 500 events → 413; a body that isn't a list → 400 (`BadRequest` [docs/handlers.md#errors]).
- Otherwise 202 `{"accepted": n, "rejected": m}`; an event without `name` counts as rejected.

Checks: `pskit validate` (aws, staging) valid; 3 events (one without name) → 202 `{"accepted": 2, "rejected": 1}`. The local invoke sends JSON, so the 415 path is only reachable from a real client (`curl` with another Content-Type after deploy).

Test again on **Test** or `pskit invoke -f ingest --method POST --path /events -d '[{"name": "a"}]' -s staging`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 640
    B(640, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: data-loader
provider:
  name: aws
  region: us-east-2
functions:
  ingest:
    handler: app.load.ingest
    events:
    - queue: load-requests
""",
          "app/__init__.py": "",
          "app/load.py": FUTURE + """

def ingest(event, ctx):
    if event.type == "schedule":
        return {"source": (event.data or {}).get("source"), "loaded": 0}
    return {"source": "queue", "loaded": len(event.records)}
""",
          "requirements.txt": ""}),
      user="On the Functions page I see `ingest`, it runs from a queue. I also want it to run by itself every 6 hours with source = backfill. How do I add that second trigger? Please just do it.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add a second event to ingest: schedule {rate: 6 hours, input: {source: backfill}} (the queue stays)",
                                   "Validate for aws, run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest.events",
            value=[{"queue": "load-requests"}, {"schedule": {"rate": "6 hours", "input": {"source": "backfill"}}}]),
          S("invoke_local", function="ingest", type="schedule"),
      ],
      final="""`ingest` now has two triggers: the queue, and every 6 hours with `source: backfill`:

```yaml
events:
  - queue: load-requests
  - schedule:
      rate: 6 hours
      input: {source: backfill}
```

The `input` arrives as `event.data` [docs/events.md#schedule], and your code already handles it.

- `pskit validate` (aws): valid.
- Scheduled run: `{"source": "backfill", "loaded": 0}`.

Next time in studio: **Functions > ingest > Add a trigger**, choose schedule, then **Save**. Deploy: **Deploy** or `pskit deploy -s dev`."""),
]
