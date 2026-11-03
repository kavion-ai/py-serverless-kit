"""Category B (build / add), batch 9: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    "gpu-box": {"host": "192.0.2.20", "user": "pskit", "port": 22},
    "lb-1": {"host": "192.0.2.30", "user": "pskit", "port": 22}}}, indent=2)
CLUSTERS = json.dumps({"clusters": {"prod": {"orchestrator": "swarm", "master": "app-1", "servers": ["app-2"]}}},
                      indent=2)


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", provider="onprem", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 161
    B(161, stage="prod", mode="auto", page="Setup", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: gateway
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8161
functions:
  api:
    handler: app.api.handle
    events:
    - http: ANY /api/{path+}
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def handle(event, ctx):
    return {"path": event.http.path}
""",
          "requirements.txt": ""}),
      user="lock down /__pskit/* on prod with a token from PSKIT_ADMIN_TOKEN",
      steps=[
          S("get_project"),
          S("search_docs", query="admin_token x-pskit-token __pskit",
            docs=[D("docs/providers.md", "onprem-on-premises", start="    admin_token:", end="# header x-pskit-token on /__pskit/* except health")]),
          S("propose_plan", steps=["provider.options.admin_token: ${env:PSKIT_ADMIN_TOKEN, }", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.admin_token", value="${env:PSKIT_ADMIN_TOKEN, }"),
      ],
      final="""Set `admin_token: "${env:PSKIT_ADMIN_TOKEN, }"`. Every `/__pskit/*` call except `/__pskit/health` now needs the header `x-pskit-token` [docs/providers.md#onprem-on-premises].

validate (onprem, prod): valid.

The value is resolved when you deploy. With the empty default, an unset variable means no token, so export `PSKIT_ADMIN_TOKEN` before `pskit deploy -s prod` (or **Deploy**, typed confirmation). pskit's own commands (`pskit logs`, `pskit trigger`, studio Test/Logs) keep working, because the stage remembers the token it deployed with."""),

    # ------------------------------------------------------------------ 162
    B(162, stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: reporting
provider:
  name: onprem
  region: local
  options:
    port: 8162
functions: {}
""",
          "requirements.txt": ""}),
      user="I need GET /reports/summary protected by an API key: callers send x-api-key, and the valid key is in REPORTS_API_KEY on the host. I wanted `auth: key` like on API Gateway, but if that isn't possible on-prem do it in the handler. Wrong or missing key -> 401.",
      steps=[
          S("get_project"),
          S("search_docs", query="http auth on premises none check tokens in the handler",
            docs=[D("docs/providers.md", "onprem-on-premises", start="| http |", end="(check tokens in the handler) |")]),
          S("propose_plan", steps=["Write `app/reports.py`: compare the x-api-key header with REPORTS_API_KEY (hmac.compare_digest), Unauthorized otherwise",
                                   "Add `report-summary` on GET /reports/summary (auth stays none: on-prem doesn't enforce key/iam/jwt)",
                                   "Give it REPORTS_API_KEY: ${env:REPORTS_API_KEY, }",
                                   "Validate (onprem, staging) and call it locally without a key (expect 401)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/reports.py", content=FUTURE + """import hmac

from py_serverless_kit import Unauthorized


def summary(event, ctx):
    expected = ctx.env.get("REPORTS_API_KEY", "")
    given = event.http.headers.get("x-api-key", "")
    if not expected or not hmac.compare_digest(given, expected):
        raise Unauthorized("missing or wrong API key")
    return {"orders": 120, "revenue": 8450.0}
"""),
          S("set_config", path="functions.report-summary",
            value={"handler": "app.reports.summary",
                   "environment": {"REPORTS_API_KEY": "${env:REPORTS_API_KEY, }"},
                   "events": [{"http": "GET /reports/summary"}]}),
          S("invoke_local", function="report-summary", method="GET", path="/reports/summary"),
      ],
      final="""`auth: key` is not possible here. On premises `auth` must be `none`, and tokens are checked in the handler [docs/providers.md#onprem-on-premises]. So `report-summary` checks the key itself:

- it compares the `x-api-key` header with `REPORTS_API_KEY` using `hmac.compare_digest`;
- a wrong or missing key raises `Unauthorized`, which gives 401 [docs/handlers.md#errors];
- if `REPORTS_API_KEY` is empty, every call is refused, so a missing variable never opens the endpoint.

Checks:
- `pskit validate` (onprem, staging): valid.
- Local call without a key: 401, as intended.

Test with a key: `REPORTS_API_KEY=abc pskit invoke -f report-summary --method GET --path /reports/summary -H "x-api-key: abc"` should give 200. The `${env:REPORTS_API_KEY, }` value is taken when you deploy. To keep it out of the deploy files, put it in `provider.options.env_file` instead. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 163
    B(163, stage="prod", mode="ask", page="Logs", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises", "docs/providers.md#logs-and-stats"],
      project=dict(files={
          "pskit.yml": """service: kiosk-fleet
provider:
  name: onprem
  region: local
  options:
    port: 8163
functions:
  heartbeat:
    handler: app.fleet.heartbeat
    events:
    - http: POST /heartbeat
""",
          "app/__init__.py": "",
          "app/fleet.py": FUTURE + """

def heartbeat(event, ctx):
    print("beat")
    return None
""",
          "requirements.txt": ""}),
      user="logs page is full of 'beat' prints and info lines from 300 kiosks. on prod i only want warnings and errors, no print lines",
      steps=[
          S("get_project"),
          S("search_docs", query="log_level capture_output print stdout host logs",
            docs=[D("docs/providers.md", "onprem-on-premises", start="    log_level: INFO", end="# also record print() / stdout / stderr lines")]),
          S("propose_plan", steps=["provider.options.log_level: WARNING", "provider.options.capture_output: false",
                                   "Validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.log_level", value="WARNING"),
          S("set_config", path="provider.options.capture_output", value=False),
      ],
      final="""Done:

```yaml
provider:
  options:
    log_level: WARNING      # only WARNING and above from logging
    capture_output: false   # print() / stdout / stderr lines are not recorded
```

[docs/providers.md#onprem-on-premises]

`pskit validate` (onprem, prod): valid.

The host still writes one `invocation` entry per call, and failures are `ERROR`, so you still see errors from the kiosks [docs/providers.md#logs-and-stats]. To hide those `invocation` lines on the **Logs** page, filter by level `warning`, or run `pskit logs --level warning`.

It takes effect after a deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 164
    B(164, stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: etl
provider:
  name: onprem
  region: local
  options:
    port: 8164
functions:
  extract:
    handler: app.etl.extract
  load:
    handler: app.etl.load
workflows:
  nightly-etl:
    start_at: Extract
    states:
      Extract: {type: task, function: extract, next: Load}
      Load: {type: task, function: load, end: true}
""",
          "app/__init__.py": "",
          "app/etl.py": FUTURE + """

def extract(event, ctx):
    return {"rows": 10}


def load(event, ctx):
    return {"loaded": (event.data or {}).get("rows", 0)}
""",
          "requirements.txt": ""}),
      user="max 4 workflow runs at once on this box, keep 2000 finished executions",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.workflow_workers: 4", "provider.options.execution_retention: 2000",
                                   "Validate (onprem, staging)"]),
          S("set_config", path="provider.options.workflow_workers", value=4),
          S("set_config", path="provider.options.execution_retention", value=2000),
      ],
      final="""Set `workflow_workers: 4` (further starts wait for a free worker) and `execution_retention: 2000` (finished runs kept under `<data_dir>/executions`) [docs/providers.md#onprem-on-premises].

validate (onprem, staging): valid (`nightly-etl` on the embedded engine).

Applies after `pskit deploy -s staging`. Browse the runs on the **Workflows** page, or with `GET /__pskit/executions`."""),

    # ------------------------------------------------------------------ 165
    B(165, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/resources.md#using-a-resource-from-an-event"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: onprem
  region: local
  options:
    port: 8165
resources:
  orders-redis:
    type: queue
    external: true
    options: {driver: redis, url_env: PSKIT_ORDERS_REDIS_URL, key: orders}
functions:
  checkout:
    handler: app.orders.checkout
    events:
    - http: POST /checkout
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def checkout(event, ctx):
    return {"ok": True}, 202
""",
          "requirements.txt": ""}),
      user="add a worker that handles the orders queue please",
      steps=[
          S("get_project"),
          S("ask_user", question="Your project already has a Redis queue resource `orders-redis` (list key `orders`). Should the worker read from that one, or from a new built-in queue called `orders` inside the host?",
            options=["Use the Redis queue orders-redis", "New built-in queue orders"],
            answer="Use the Redis queue orders-redis"),
          S("propose_plan", steps=["Write `app/worker.py`: log each order id",
                                   "Add `order-worker` with queue {resource: orders-redis}",
                                   "Validate for onprem and invoke with one order"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/worker.py", content=FUTURE + """

def handle_orders(event, ctx):
    done = []
    for record in event.records:
        order = record.json(default={}) or {}
        ctx.logger.info("order", extra={"order_id": order.get("order_id")})
        done.append(order.get("order_id"))
    return {"handled": done}
"""),
          S("set_config", path="functions.order-worker",
            value={"handler": "app.worker.handle_orders", "events": [{"queue": {"resource": "orders-redis"}}]}),
          S("invoke_local", function="order-worker", type="queue", data=[{"order_id": "o-501"}]),
      ],
      final="""Added `order-worker`, reading from your Redis queue:

```yaml
functions:
  order-worker:
    handler: app.worker.handle_orders
    events:
      - queue: {resource: orders-redis}
```

`resource:` means "use the queue described under `resources:`", so it reads the Redis list `orders` with the connection from `PSKIT_ORDERS_REDIS_URL` [docs/resources.md#using-a-resource-from-an-event]. It gets up to 10 messages at a time (the default `batch_size`).

- `pskit validate` (onprem): valid.
- Local test with one order: `{"handled": ["o-501"]}`.

Deploy: **Deploy** page or `pskit deploy -s dev`. Then send a test message from **Resources** > **Test**."""),

    # ------------------------------------------------------------------ 166
    B(166, stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: stock-sync
provider:
  name: onprem
  region: local
  options:
    port: 8166
functions:
  sync:
    handler: app.sync.run
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """

def run(event, ctx):
    mode = (event.data or {}).get("mode", "quick")
    ctx.logger.info("sync", extra={"mode": mode})
    return {"mode": mode}
""",
          "requirements.txt": ""}),
      user="sync need 2 timers: every hour mode=quick, and every night 1:00 mode=full. same function",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Give `sync` two schedules: rate 1 hour with input {mode: quick}, cron `0 1 * * *` with input {mode: full}",
                                   "Validate (onprem, prod) and run the schedule locally with {mode: full}"],
            result={"decision": "approved", "note": "name them hourly-quick and nightly-full"}),
          S("set_config", path="functions.sync.events",
            value=[{"schedule": {"rate": "1 hour", "input": {"mode": "quick"}, "name": "hourly-quick"}},
                   {"schedule": {"cron": "0 1 * * *", "input": {"mode": "full"}, "name": "nightly-full"}}],
            say="Adding both, with the names you asked for."),
          S("invoke_local", function="sync", type="schedule", data={"mode": "full"}),
      ],
      final="""Done, with your names:

```yaml
functions:
  sync:
    handler: app.sync.run
    events:
      - schedule: {rate: 1 hour, input: {mode: quick}, name: hourly-quick}
      - schedule: {cron: "0 1 * * *", input: {mode: full}, name: nightly-full}
```

One function can have several schedules. Each one sends its own `input` as `event.data` [docs/events.md#schedule].

- `pskit validate` (onprem, prod): valid.
- Local schedule run with `{"mode": "full"}`: `{"mode": "full"}`.

01:00 is UTC unless you add `timezone`. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 167
    B(167, stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#event", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: geocoder
provider:
  name: onprem
  region: local
  options:
    port: 8167
functions: {}
""",
          "requirements.txt": ""}),
      user="One function `geocode` with two entry points: POST /geocode for a single address (returns the result directly) and the queue `geocode-jobs` for bulk work. Same logic in both. Use a fake lookup that returns lat/lon 0,0 plus the normalised address.",
      steps=[
          S("get_project"),
          S("search_docs", query="event type is_http records one handler several triggers",
            docs=[D("docs/handlers.md", "event", words=170)]),
          S("propose_plan", steps=["Write `app/geocode.py`: `lookup(address)` shared; handler branches on event.is_http",
                                   "Add `geocode` with two events: POST /geocode and queue geocode-jobs",
                                   "Validate (onprem, staging); invoke over HTTP and as a queue"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/geocode.py", content=FUTURE + """from py_serverless_kit import BadRequest


def lookup(address):
    clean = " ".join(str(address).split()).title()
    return {"address": clean, "lat": 0.0, "lon": 0.0}


def geocode(event, ctx):
    if event.is_http:
        address = (event.http.json(default={}) or {}).get("address")
        if not address:
            raise BadRequest("address is required")
        return lookup(address)
    results = [lookup((r.json(default={}) or {}).get("address", "")) for r in event.records]
    ctx.logger.info("bulk geocode", extra={"count": len(results)})
    return {"geocoded": len(results)}
"""),
          S("set_config", path="functions.geocode",
            value={"handler": "app.geocode.geocode",
                   "events": [{"http": "POST /geocode"}, {"queue": "geocode-jobs"}]}),
          S("invoke_local", function="geocode", method="POST", path="/geocode", data={"address": "  10 main   street "}),
          S("invoke_local", function="geocode", type="queue", data=[{"address": "1 elm st"}, {"address": "2 oak ave"}]),
      ],
      final="""Added `geocode` with both triggers:

```yaml
functions:
  geocode:
    handler: app.geocode.geocode
    events:
      - http: POST /geocode
      - queue: geocode-jobs
```

The handler checks `event.is_http`. HTTP calls read the body, and queue deliveries loop over `event.records`. Both use the same `lookup()` [docs/handlers.md#event].

- `pskit validate` (onprem, staging): valid.
- `POST /geocode {"address": "  10 main   street "}`: 200, `{"address": "10 Main Street", "lat": 0.0, "lon": 0.0}`.
- Queue invoke with 2 jobs: `{"geocoded": 2}`.

Replace `lookup()` with your real geocoder. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 168
    B(168, stage="dev", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#choice-rules", "docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: shipping-rates
provider:
  name: onprem
  region: local
  options:
    port: 8168
functions:
  quote:
    handler: app.rates.quote
""",
          "app/__init__.py": "",
          "app/rates.py": FUTURE + """

def quote(event, ctx):
    data = dict(event.data or {})
    return {**data, "price": round(data.get("weight_kg", 0) * data.get("rate", 0), 2)}
""",
          "requirements.txt": ""}),
      user="wf `rate`: weight_kg < 2 -> rate 4.0, 2..<10 -> 2.5, else 1.2 (pass states into $.rate), then quote",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add workflow `rate`: Band choice (lt 2 -> Small, lt 10 -> Medium, default Large)",
                                   "Small/Medium/Large: pass states with result 4.0/2.5/1.2, result_path $.rate, next Quote",
                                   "Quote: task quote, end. Validate, invoke quote"]),
          S("set_config", path="workflows.rate",
            value={"start_at": "Band",
                   "states": {"Band": {"type": "choice",
                                       "choices": [{"variable": "$.weight_kg", "lt": 2, "next": "Small"},
                                                   {"variable": "$.weight_kg", "lt": 10, "next": "Medium"}],
                                       "default": "Large"},
                              "Small": {"type": "pass", "result": 4.0, "result_path": "$.rate", "next": "Quote"},
                              "Medium": {"type": "pass", "result": 2.5, "result_path": "$.rate", "next": "Quote"},
                              "Large": {"type": "pass", "result": 1.2, "result_path": "$.rate", "next": "Quote"},
                              "Quote": {"type": "task", "function": "quote", "end": True}}}),
          S("invoke_local", function="quote", type="workflow", data={"weight_kg": 5, "rate": 2.5}),
      ],
      final="""Added `rate`:

```yaml
workflows:
  rate:
    start_at: Band
    states:
      Band:
        type: choice
        choices:
          - {variable: $.weight_kg, lt: 2, next: Small}
          - {variable: $.weight_kg, lt: 10, next: Medium}
        default: Large
      Small:  {type: pass, result: 4.0, result_path: $.rate, next: Quote}
      Medium: {type: pass, result: 2.5, result_path: $.rate, next: Quote}
      Large:  {type: pass, result: 1.2, result_path: $.rate, next: Quote}
      Quote:  {type: task, function: quote, end: true}
```

Rules are checked in order, so `lt: 10` only sees weights of 2 and up [docs/workflows.md#choice-rules].

- validate (onprem): valid (embedded engine).
- `quote` with weight 5 and rate 2.5: `"price": 12.5`.

Run it: `pskit workflow run rate -i '{"weight_kg": 12}' --history` (expect rate 1.2). Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 169
    B(169, stage="staging", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#migrating-step-functions-asl"],
      project=dict(files={
          "pskit.yml": """service: kyc
provider:
  name: onprem
  region: local
  options:
    port: 8169
functions:
  verify-id:
    handler: app.kyc.verify_id
""",
          "app/__init__.py": "",
          "app/kyc.py": FUTURE + """

def verify_id(event, ctx):
    return {**(event.data or {}), "verified": True}
""",
          "requirements.txt": ""}),
      user="The state machine started with a Choice: if $.document_id is not present -> Fail state (Error MissingDocument, Cause 'no document id'); otherwise VerifyId Lambda then a Succeed state. Port it.",
      steps=[
          S("get_project"),
          S("search_docs", query="fail state error cause succeed is_present",
            docs=[D("docs/workflows.md", "state-types", start="| `succeed` |", end="| `fail` | `error`, `cause` | finish with an error |"),
                  D("docs/workflows.md", "choice-rules", start="| `is_present` |", end="the path exists (`true` / `false`) |")]),
          S("propose_plan", steps=["Add workflow `kyc-check`: HasDocument (choice: $.document_id is_present false -> Missing, default Verify)",
                                   "Missing: fail (error MissingDocument, cause 'no document id'); Verify: task verify-id -> Done (succeed)",
                                   "Validate (onprem, staging) and invoke verify-id as a task"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.kyc-check",
            value={"start_at": "HasDocument",
                   "states": {"HasDocument": {"type": "choice",
                                              "choices": [{"variable": "$.document_id", "is_present": False,
                                                           "next": "Missing"}],
                                              "default": "Verify"},
                              "Missing": {"type": "fail", "error": "MissingDocument", "cause": "no document id"},
                              "Verify": {"type": "task", "function": "verify-id", "next": "Done"},
                              "Done": {"type": "succeed"}}}),
          S("invoke_local", function="verify-id", type="workflow", data={"document_id": "P1234567"}),
      ],
      final="""Ported 1:1:

```yaml
workflows:
  kyc-check:
    start_at: HasDocument
    states:
      HasDocument:
        type: choice
        choices:
          - {variable: $.document_id, is_present: false, next: Missing}
        default: Verify
      Missing: {type: fail, error: MissingDocument, cause: no document id}
      Verify:  {type: task, function: verify-id, next: Done}
      Done:    {type: succeed}
```

`fail` ends the run with that error and cause, and `succeed` ends it with the current data [docs/workflows.md#state-types].

- `pskit validate` (onprem, staging): valid (embedded engine).
- `verify-id` as a task: returned the input with `"verified": true`.

Check the fail branch: `pskit workflow run kyc-check -i '{}' --history` should end with `MissingDocument`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 170
    B(170, stage="prod", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resource-guides/onprem/services.md#what-gets-written", "docs/cluster.md#resources-on-a-cluster"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    cluster: prod
    env_file: .env.onprem
functions:
  cart:
    handler: app.cart.get_cart
    events:
    - http: GET /cart
  catalog:
    handler: app.cart.catalog
    events:
    - http: GET /catalog
""",
          "app/__init__.py": "",
          "app/cart.py": FUTURE + """

def get_cart(event, ctx):
    return {"items": []}


def catalog(event, ctx):
    return []
""",
          ".env.onprem": "",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="my colleague ran this and it worked:\n\n  $ pskit resources onprem create cart-cache --service redis --role cache --cluster prod\n  cart-cache: redis on app-2 (cluster prod), wrote PSKIT_CART_CACHE_URL to .env.onprem\n\nbut it's not in pskit.yml (he used another checkout). only `cart` should use it, and show me in the response that it got the url",
      steps=[
          S("get_project"),
          S("search_docs", query="one-click service written pskit.yml url_env env file",
            docs=[D("docs/resource-guides/onprem/services.md", "what-gets-written", end="`ctx.env[resource(\"orders-db\")[\"password_env\"]]`.")]),
          S("propose_plan", steps=["Add resources.cart-cache: cache, external, connection {url_env: PSKIT_CART_CACHE_URL}, functions [cart]",
                                   "`get_cart` reports whether the URL variable is set",
                                   "Validate (onprem, prod), call GET /cart"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.cart-cache",
            value={"type": "cache", "external": True, "connection": {"url_env": "PSKIT_CART_CACHE_URL"},
                   "functions": ["cart"]}),
          S("write_file", path="app/cart.py", content=FUTURE + """from py_serverless_kit import resource


def get_cart(event, ctx):
    cache = resource("cart-cache")
    return {"items": [], "cache_url_set": bool(ctx.env.get(cache["url_env"]))}


def catalog(event, ctx):
    return []
"""),
          S("validate"),
          S("invoke_local", function="cart", method="GET", path="/cart"),
      ],
      final="""Added the cache your colleague created, bound only to `cart`:

```yaml
resources:
  cart-cache:
    type: cache
    external: true
    connection: {url_env: PSKIT_CART_CACHE_URL}
    functions: [cart]
```

The URL (with its generated password) stays in `.env.onprem`, which your project already ships with the host through `env_file` [docs/resource-guides/onprem/services.md#what-gets-written]. The handler reads it with `ctx.env[resource("cart-cache")["url_env"]]`.

- `pskit validate` (onprem, prod): valid.
- `GET /cart`: 200, `{"items": [], "cache_url_set": false}`. Your local `.env.onprem` is empty, so copy the `PSKIT_CART_CACHE_URL=...` line from his checkout (or `pskit settings export` there) before deploying.

The cache runs on app-2, and every replica of the cluster reaches it at app-2's cluster address [docs/cluster.md#resources-on-a-cluster]. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 171
    B(171, stage="staging", mode="auto", page="Network map", persona="informal_non_native",
      sources=["docs/resource-guides/onprem/database.md#3-declare-it-in-pskityml", "docs/onprem-network.md"],
      project=dict(files={
          "pskit.yml": """service: hr-portal
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8171
    deploy: {server: app-1, python: bundle}
functions:
  employees:
    handler: app.hr.employees
    events:
    - http: GET /employees
""",
          "app/__init__.py": "",
          "app/hr.py": FUTURE + """

def employees(event, ctx):
    return []
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="functions run on app-1, postgres is on db-1 (192.0.2.40, 5432, db hr, user hr_app, pass in HR_DB_PASSWORD). connect them and tell me what port to open",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add resources.hr-db: database, external, connection {host: 192.0.2.40, port: 5432, database: hr, user: hr_app, password_env: HR_DB_PASSWORD}, functions [employees]",
                                   "`employees` reports the bound db",
                                   "Validate (onprem, staging), call GET /employees"]),
          S("set_config", path="resources.hr-db",
            value={"type": "database", "external": True,
                   "connection": {"host": "192.0.2.40", "port": 5432, "database": "hr", "user": "hr_app",
                                  "password_env": "HR_DB_PASSWORD"},
                   "functions": ["employees"]}),
          S("write_file", path="app/hr.py", content=FUTURE + """from py_serverless_kit import resource


def employees(event, ctx):
    db = resource("hr-db")
    return {"db": f'{db["host"]}:{db["port"]}/{db["database"]}', "employees": []}
"""),
          S("validate"),
          S("invoke_local", function="employees", method="GET", path="/employees"),
      ],
      final="""Connected:

```yaml
resources:
  hr-db:
    type: database
    external: true
    connection: {host: 192.0.2.40, port: 5432, database: hr, user: hr_app, password_env: HR_DB_PASSWORD}
    functions: [employees]
```

- validate (onprem, staging): valid.
- `GET /employees`: 200, `{"db": "192.0.2.40:5432/hr", "employees": []}`.

**Port to open:** 5432/tcp on db-1, from app-1 (192.0.2.10). PostgreSQL itself must also accept app-1 (`listen_addresses` and a `pg_hba.conf` line for that host) [docs/resource-guides/onprem/database.md#1-set-up-postgresql]. The **Network map** page draws the servers and the ports pskit itself needs [docs/onprem-network.md]. A database you added by hand may not appear there, so open 5432 yourself.

Set `HR_DB_PASSWORD` on app-1 (or in `options.env_file`). Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 172
    B(172, stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/placement.md", "docs/placement.md#how-the-groups-work-together"],
      project=dict(files={
          "pskit.yml": """service: analytics
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8172
    deploy: {python: bundle}
functions:
  dashboard:
    handler: app.dash.page
    events:
    - http: GET /dashboard
  monthly-report:
    handler: functions.report.handler.main
    events:
    - schedule: 0 4 1 * *
""",
          "app/__init__.py": "",
          "app/dash.py": FUTURE + """

def page(event, ctx):
    return {"widgets": 3}
""",
          "functions/__init__.py": "",
          "functions/report/__init__.py": "",
          "functions/report/handler.py": FUTURE + """

def main(event, ctx):
    return {"report": "built"}
""",
          "functions/report/requirements.txt": "",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="The dashboard is light and can stay on the saved server app-1. monthly-report is heavy: put it on our scaling cluster `prod` with 3 replicas. Keep it as one project.",
      steps=[
          S("get_project"),
          S("search_docs", query="placement group cluster replicas functions",
            docs=[D("docs/placement.md", "functions-on-several-servers-on-premises", end="# this machine")]),
          S("propose_plan", steps=["provider.options.placement: default group `web` on server app-1; group `batch` on cluster {name: prod, replicas: 3} with functions [monthly-report]",
                                   "Validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.placement",
            value={"default": "web", "groups": {"web": {"server": "app-1"},
                                                 "batch": {"cluster": {"name": "prod", "replicas": 3},
                                                           "functions": ["monthly-report"]}}}),
          S("set_config", path="provider.options.placement.groups.batch.port", value=8173,
            say="Validate found a clash: the cluster's master is app-1, so both groups would use port 8172 there. Giving `batch` port 8173, as the error suggests."),
      ],
      final="""Set:

```yaml
provider:
  options:
    placement:
      default: web
      groups:
        web:   {server: app-1}
        batch: {cluster: {name: prod, replicas: 3}, functions: [monthly-report], port: 8173}
```

`dashboard` (and anything new) runs on app-1. `monthly-report` runs on cluster `prod` with only its own folder and `functions/report/requirements.txt` [docs/placement.md]. The default group still collects every group's logs and invocation counts [docs/placement.md#how-the-groups-work-together].

`pskit validate` (onprem, prod): the first try failed with `groups web and batch both run on app-1 port 8172`, because app-1 is also the master of `prod`. With `port: 8173` on `batch` it is valid.

Open 8172 and 8173 between app-1 and the cluster servers. Deploy both in one apply: **Deploy** page (typed confirmation; "Where functions run" shows the groups) or `pskit deploy -s prod`. Docker must run on this machine for the cluster image."""),

    # ------------------------------------------------------------------ 173
    B(173, stage="prod", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/placement.md#deploy-urls-and-load-balancers"],
      project=dict(files={
          "pskit.yml": """service: docscan
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    deploy: {python: bundle}
    placement:
      default: api
      groups:
        api: {server: app-1}
        vision: {server: gpu-box, functions: [ocr]}
functions:
  api:
    handler: app.api.submit
    events:
    - http: POST /scan
  ocr:
    handler: functions.ocr.handler.main
    events:
    - http: POST /ocr
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def submit(event, ctx):
    return {"queued": True}
""",
          "functions/__init__.py": "",
          "functions/ocr/__init__.py": "",
          "functions/ocr/handler.py": FUTURE + """

def main(event, ctx):
    return {"text": ""}
""",
          "functions/ocr/requirements.txt": "",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="POST /ocr on app-1 gives 404 pointing at gpu-box. want every route on both servers (one URL)",
      steps=[
          S("get_project"),
          S("search_docs", query="placement gateway every group answers every route",
            docs=[D("docs/placement.md", "deploy-urls-and-load-balancers", start="Each server answers only the HTTP routes", end="passing other groups' routes on")]),
          S("propose_plan", steps=["provider.options.placement.gateway: true", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.placement.gateway", value=True),
      ],
      final="""Set `placement.gateway: true`. Now every group answers every route and passes the other groups' routes on, so `POST /ocr` on app-1 is forwarded to gpu-box instead of returning the 404 [docs/placement.md#deploy-urls-and-load-balancers]. A forwarded request is never forwarded again, so there are no loops.

validate (onprem, prod): valid.

Port 8080 must be open between app-1 and gpu-box. Deploy: `pskit deploy -s prod` (or **Deploy**, typed confirmation)."""),

    # ------------------------------------------------------------------ 174
    B(174, stage="staging", mode="ask", page="Load balancers", persona="detailed_spec",
      sources=["docs/load-balancers.md#shared-between-projects-and-machines", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: shop
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
    advertise: http://192.0.2.10:8080
    deploy: {server: app-1, python: bundle}
    balancer: {name: edge, path: shop}
stages:
  staging:
    provider:
      options:
        port: 8090
        advertise: http://192.0.2.11:8090
        deploy: {server: app-2}
functions:
  catalog:
    handler: app.catalog.items
    events:
    - http: GET /items
""",
          "app/__init__.py": "",
          "app/catalog.py": FUTURE + """

def items(event, ctx):
    return []
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="prod is on lb `edge` at /shop. Staging uses the same pskit.yml and would take the same path, and a path belongs to one deployment. Put staging on edge at /shop-staging, prod unchanged.",
      steps=[
          S("get_project"),
          S("search_docs", query="load balancer path belongs to one deployment",
            docs=[D("docs/load-balancers.md", "shared-between-projects-and-machines", start="* a path belongs to one deployment", end="another one gets an error and picks another path;")]),
          S("propose_plan", steps=["Add stages.staging.provider.options.balancer: {name: edge, path: shop-staging}",
                                   "Validate for onprem as staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.staging.provider.options.balancer", value={"name": "edge", "path": "shop-staging"}),
      ],
      final="""Added to the staging override:

```yaml
stages:
  staging:
    provider:
      options:
        balancer: {name: edge, path: shop-staging}
```

Staging now routes `http://edge/shop-staging/` to app-2:8090, and prod keeps `/shop` on app-1. A path belongs to one deployment (`pskit-shop-staging` vs `pskit-shop-prod`), so they no longer collide [docs/load-balancers.md#shared-between-projects-and-machines].

`pskit validate` (onprem, staging): valid.

Deploy staging: **Deploy** page with stage `staging`, or `pskit deploy -s staging`. Then `pskit lb status edge` lists both routes."""),

    # ------------------------------------------------------------------ 175
    B(175, stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/events.md#http", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: rooms
provider:
  name: onprem
functions: {}
""",
          "requirements.txt": ""}),
      user="hi, new to this. i want a small app for our office: see the meeting rooms and book one. a room that is already booked cannot be booked again. it runs on the office server",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider: region local, options host 0.0.0.0 (office network), port 8175",
                                   "Write `app/rooms.py`: list rooms; book a room (404 unknown room, 409 already booked)",
                                   "Add `list-rooms` on GET /rooms and `book-room` on POST /rooms/{id}/book",
                                   "Validate for onprem and book a room locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.region", value="local"),
          S("set_config", path="provider.options", value={"host": "0.0.0.0", "port": 8175}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/rooms.py", content=FUTURE + """from py_serverless_kit import Conflict, NotFound

ROOMS = {
    "1": {"id": "1", "name": "Aurora", "booked_by": None},
    "2": {"id": "2", "name": "Borealis", "booked_by": None},
}


def list_rooms(event, ctx):
    return {"rooms": list(ROOMS.values())}


def book_room(event, ctx):
    room = ROOMS.get(event.http.path_params.get("id", ""))
    if room is None:
        raise NotFound("no such room")
    if room["booked_by"]:
        raise Conflict(f"{room['name']} is already booked")
    room["booked_by"] = (event.http.json(default={}) or {}).get("name", "someone")
    return room
"""),
          S("set_config", path="functions",
            value={"list-rooms": {"handler": "app.rooms.list_rooms", "events": [{"http": "GET /rooms"}]},
                   "book-room": {"handler": "app.rooms.book_room", "events": [{"http": "POST /rooms/{id}/book"}]}}),
          S("invoke_local", function="book-room", method="POST", path="/rooms/1/book", data={"name": "Sara"}),
      ],
      final="""Welcome! Your room app is ready:

- `GET /rooms` shows the rooms.
- `POST /rooms/{id}/book` with `{"name": "..."}` books one. An unknown room gives 404, and a room that is already booked gives 409 [docs/handlers.md#errors].

Checks:
- `pskit validate` (onprem): valid.
- Local booking of room 1 for Sara: 200, `{"id": "1", "name": "Aurora", "booked_by": "Sara"}`.

Two things to know:
1. `host: 0.0.0.0` lets other computers in the office reach port 8175.
2. Bookings are kept in memory, so they are lost on restart. Ask me to add a database when you're ready.

Test: **Test** page > **▶ Run locally**, or `pskit invoke -f list-rooms --method GET --path /rooms`. Start it: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 176
    B(176, stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#get_secret-secrets-on-every-provider", "docs/resources.md#secrets"],
      project=dict(files={
          "pskit.yml": """service: mailer
provider:
  name: onprem
  region: local
  options:
    port: 8176
    env_file: .env.onprem
functions:
  send:
    handler: app.mailer.send
    events:
    - queue: outgoing-mail
""",
          "app/__init__.py": "",
          "app/mailer.py": FUTURE + """

def send(event, ctx):
    return {"sent": 0}
""",
          ".env.onprem": "",
          "requirements.txt": ""}),
      user="The SMTP relay password should be read with get_secret so the same code works later with Vault. For now the store is just the env file on the host (secret name smtp-password). If it is missing, log a warning and skip sending instead of crashing.",
      steps=[
          S("get_project"),
          S("search_docs", query="get_secret env driver PSKIT_SECRET_ default",
            docs=[D("docs/handlers.md", "get_secret-secrets-on-every-provider")]),
          S("propose_plan", steps=["`send` uses get_secret(\"smtp-password\", default=\"\"): the env driver reads PSKIT_SECRET_SMTP_PASSWORD (or SMTP_PASSWORD) from the host environment / .env.onprem",
                                   "Log a warning and return sent 0 when it is empty",
                                   "Validate (onprem, prod) and invoke with one mail"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/mailer.py", content=FUTURE + """from py_serverless_kit import get_secret


def send(event, ctx):
    relay_pw = get_secret("smtp-password", default="")
    if not relay_pw:
        ctx.logger.warning("smtp-password secret not found, not sending", extra={"mails": len(event.records)})
        return {"sent": 0}
    # log in to the relay with `relay_pw` and send each record here
    return {"sent": len(event.records)}
"""),
          S("validate"),
          S("invoke_local", function="send", type="queue", data=[{"to": "ops@example.com", "subject": "Hi"}]),
      ],
      final="""`send` now reads the password with `get_secret("smtp-password", default="")`. With the default `env` driver that looks up `PSKIT_SECRET_SMTP_PASSWORD`, then `SMTP_PASSWORD`, in the host's environment [docs/handlers.md#get_secret-secrets-on-every-provider]. Your `.env.onprem` is loaded into that environment at start [docs/resources.md#secrets]. Switching to Vault later means setting `PSKIT_SECRETS_DRIVER` to `vault` (plus its URL and token variables), with no code change.

- `pskit validate` (onprem, prod): valid.
- Local invoke with one mail: the secret isn't set here, so it logged the warning and returned `{"sent": 0}` without crashing.

Add a line `PSKIT_SECRET_SMTP_PASSWORD=<password>` to `.env.onprem` on your machine (it's out of git). Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 177
    B(177, stage="dev", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: sandbox
provider:
  name: onprem
  region: local
  options:
    port: 8177
functions:
  echo:
    handler: app.echo.echo
    events:
    - http: POST /echo
""",
          "app/__init__.py": "",
          "app/echo.py": FUTURE + """

def echo(event, ctx):
    return event.http.json(default={})
""",
          "requirements.txt": ""}),
      user="dev in a local docker container on this laptop, image pskit/sandbox:dev, no ssh",
      steps=[
          S("get_project"),
          S("search_docs", query="docker on this laptop only deploy method",
            docs=[D("docs/providers.md", "onprem-on-premises", start="# Docker on this laptop only", end="image: pskit/orders:dev")]),
          S("propose_plan", steps=["provider.options.deploy: {method: docker, image: pskit/sandbox:dev}",
                                   "provider.options.host: 0.0.0.0 (a container must listen beyond its own 127.0.0.1)",
                                   "Validate (onprem, dev)"]),
          S("set_config", path="provider.options.deploy", value={"method": "docker", "image": "pskit/sandbox:dev"}),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""Set `deploy: {method: docker, image: pskit/sandbox:dev}`. With no `host`, the image is built and run on this laptop, with no SSH and no `.pem` [docs/providers.md#onprem-on-premises].

Also set `host: 0.0.0.0`. Validate warned that a host bound to 127.0.0.1 on the target only accepts traffic from inside the container. After the change it is valid.

Deploy: `pskit deploy -s dev` (Docker must be running). It waits until the container answers `/__pskit/health`."""),

    # ------------------------------------------------------------------ 178
    B(178, stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: intranet
provider:
  name: onprem
  region: local
  options:
    port: 8178
functions:
  news:
    handler: app.intranet.news
    events:
    - http: GET /news
  cleanup:
    handler: app.intranet.cleanup
    events:
    - schedule: 0 3 * * 0
""",
          "app/__init__.py": "",
          "app/intranet.py": FUTURE + """

def news(event, ctx):
    return []


def cleanup(event, ctx):
    return {"removed": 0}
""",
          "requirements.txt": ""}),
      user="new people in my team don't know what news and cleanup do. can you write a short description on each, and mark them with team=intranet so we can find them?",
      steps=[
          S("get_project"),
          S("search_docs", query="function description tags",
            docs=[D("docs/configuration.md", "functions", words=200)]),
          S("propose_plan", steps=["functions.news: description 'Latest intranet news for the home page', tags {team: intranet}",
                                   "functions.cleanup: description 'Sunday 03:00 cleanup of old news items', tags {team: intranet}",
                                   "Validate (onprem, staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.news.description", value="Latest intranet news for the home page"),
          S("set_config", path="functions.news.tags", value={"team": "intranet"}),
          S("set_config", path="functions.cleanup.description", value="Sunday 03:00 cleanup of old news items"),
          S("set_config", path="functions.cleanup.tags", value={"team": "intranet"}),
      ],
      final="""Done. Both functions now explain themselves:

```yaml
functions:
  news:
    description: Latest intranet news for the home page
    tags: {team: intranet}
  cleanup:
    description: Sunday 03:00 cleanup of old news items
    tags: {team: intranet}
```

`pskit validate` (onprem, staging): valid.

Your team sees the description on the **Functions** page (the Description field under Basics), and the tags under Concurrency & tags. Nothing about how they run has changed. Deploy when you like: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 179
    B(179, stage="prod", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises", "docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": """service: bids
provider:
  name: onprem
  region: local
  options:
    port: 8179
functions:
  place-bid:
    handler: app.bids.place
    events:
    - queue: {name: bids, batch_size: 1}
""",
          "app/__init__.py": "",
          "app/bids.py": FUTURE + """

def place(event, ctx):
    return None
""",
          "requirements.txt": ""}),
      user="bids worker reacts too slow, poll every 0.2s instead of 0.5",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider.options.poll_seconds: 0.2", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.poll_seconds", value=0.2),
      ],
      final="""Set `poll_seconds: 0.2` (default 0.5) [docs/providers.md#onprem-on-premises].

validate (onprem, prod): valid.

It applies to every poll of the host, including the driver queues and buckets, which are listed every `poll_seconds` [docs/resources.md#on-premises-drivers]. With only built-in queues the cost is small. Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 180
    B(180, stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#embedded-orchestrator", "docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": """service: claims-intake
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8180
resources:
  claims-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.50, port: 25, domains: claims.example.com, hostname: mail.claims.example.com}
functions:
  read-claim-mail:
    handler: app.claims.read_mail
    events:
    - smtp: {resource: claims-mail}
  score-claim:
    handler: app.claims.score
  open-case:
    handler: app.claims.open_case
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + """

def read_mail(event, ctx):
    mail = event.data or {}
    return {"from": mail.get("from"), "subject": mail.get("subject"),
            "attachments": len(mail.get("attachments") or [])}


def score(event, ctx):
    claim = dict(event.data or {})
    return {**claim, "score": 0.8 if claim.get("attachments") else 0.2}


def open_case(event, ctx):
    return {**(event.data or {}), "case": "C-1"}
""",
          "requirements.txt": ""}),
      user="Each mail to claims.example.com should go through: read-claim-mail -> score-claim -> open-case, as one tracked run I can see on the Workflows page. read-claim-mail already has the SMTP trigger. Don't add code that starts the workflow by hand.",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow first task starts when function runs smtp trigger on premises",
            docs=[D("docs/workflows.md", "embedded-orchestrator", start="- On premises, a workflow whose first state is a `task`",
                    end="Other clouds don't do this: start the workflow itself there.")]),
          S("propose_plan", steps=["Add workflow `claim-intake`: Read (read-claim-mail) -> Score (score-claim) -> Open (open-case, end)",
                                   "The SMTP trigger stays on read-claim-mail; on-prem starts the workflow when it runs on its own",
                                   "Validate (onprem, staging) and run read-claim-mail with a test mail"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.claim-intake",
            value={"start_at": "Read",
                   "states": {"Read": {"type": "task", "function": "read-claim-mail", "next": "Score"},
                              "Score": {"type": "task", "function": "score-claim", "next": "Open"},
                              "Open": {"type": "task", "function": "open-case", "end": True}}}),
          S("invoke_local", function="read-claim-mail", type="smtp",
            data={"from": "client@example.org", "to": ["new@claims.example.com"], "subject": "Water damage",
                  "text": "Photos attached."}),
      ],
      final="""Added `claim-intake`:

```yaml
workflows:
  claim-intake:
    start_at: Read
    states:
      Read:  {type: task, function: read-claim-mail, next: Score}
      Score: {type: task, function: score-claim, next: Open}
      Open:  {type: task, function: open-case, end: true}
```

No starter code is needed. On premises, when `read-claim-mail` runs on its own (here from its SMTP trigger), a workflow whose first state is that task starts with the mail as input. The function's result is reused as the first state's result, so it doesn't run twice [docs/workflows.md#embedded-orchestrator]. A failed run of `read-claim-mail` starts nothing.

- `pskit validate` (onprem, staging): valid (embedded engine).
- `read-claim-mail` with a test mail: `{"from": "client@example.org", "subject": "Water damage", "attachments": 0}`.

Deploy: **Deploy** page or `pskit deploy -s staging`. Each mail then shows up as a run on the **Workflows** page. Try the chain locally: `pskit workflow run claim-intake -i '{"from": "a@example.org"}' --history`."""),
]
