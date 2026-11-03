"""Category B (build / add), batch 15: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

SERVERS = json.dumps({"servers": {
    "app-1": {"host": "192.0.2.10", "user": "pskit", "port": 22},
    "app-2": {"host": "192.0.2.11", "user": "pskit", "port": 22},
    "lb-1": {"host": "192.0.2.30", "user": "pskit", "port": 22}}}, indent=2)


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
    # ------------------------------------------------------------------ 281
    B(281, stage="prod", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/handlers.md#get_secret-secrets-on-every-provider", "docs/resource-guides/onprem/secrets.md"],
      project=dict(files={
          "pskit.yml": yml("payments", 8281, """functions:
  charge:
    handler: app.pay.charge
    events:
    - http: POST /charge
""", "    host: 0.0.0.0\n    env_file: .env.onprem\n"),
          "app/__init__.py": "",
          "app/pay.py": FUTURE + """import os


def charge(event, ctx):
    key = os.environ.get("PSP_API_KEY", "")
    return {"configured": bool(key)}
""",
          ".env.onprem": "PSKIT_SECRETS_DRIVER=vault\n",
          "requirements.txt": ""}),
      user="On Lambda the PSP key came from Secrets Manager (secret `psp`, JSON field `api_key`). We now created an OpenBao one-click service named `secrets` and stored the same secret there. Change charge to read it from the store instead of the PSP_API_KEY env var.",
      steps=[
          S("read_file", path="app/pay.py"),
          S("search_docs", query="get_secret field store vault openbao",
            docs=[D("docs/handlers.md", "get_secret-secrets-on-every-provider", words=170),
                  D("docs/resource-guides/onprem/secrets.md", "one-click-openbao-pskits-secrets-manager-or-localstack", start="Name it **`secrets`**", end="`get_secret(\"db-password\", store=\"aws-secrets\")`")]),
          S("propose_plan", steps=["Rewrite `charge`: get_secret('psp', 'api_key', default='') instead of os.environ",
                                   "Validate (onprem, prod), invoke POST /charge"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/pay.py", content=FUTURE + """from py_serverless_kit import get_secret


def charge(event, ctx):
    key = get_secret("psp", "api_key", default="")
    if not key:
        ctx.logger.warning("psp api_key not found in the secret store")
    return {"configured": bool(key)}
"""),
          S("validate"),
          S("invoke_local", function="charge", method="POST", path="/charge"),
      ],
      final="""Done. `charge` now calls `get_secret("psp", "api_key", default="")`, the same secret name and field as in Secrets Manager [docs/handlers.md#get_secret-secrets-on-every-provider]. Because the one-click service is named `secrets`, it is the default store and no `store=` is needed. Its connection (`PSKIT_SECRETS_DRIVER` set to `vault`, plus URL and token) is in `.env.onprem`, which the host loads [docs/resource-guides/onprem/secrets.md].

- `pskit validate` (onprem, prod): valid.
- Local `POST /charge`: `{"configured": false}`, with the warning. A local run doesn't load `.env.onprem`, so it uses the default `env` store, where there is no `psp` secret. That's expected here.

Values are cached for 60 s. The same code works on Lambda again with `PSKIT_SECRETS_DRIVER` set to `aws`. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. Then `pskit logs --function charge` should show no warning."""),

    # ------------------------------------------------------------------ 282
    B(282, stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#switch-something-off-on-one-cloud"],
      project=dict(files={
          "pskit.yml": """service: archive
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.archive.api
    events:
    - http: GET /files
  glacier-sync:
    handler: app.archive.glacier
    events:
    - schedule: 0 4 * * *
providers:
  onprem:
    region: local
    options: {port: 8282}
""",
          "app/__init__.py": "",
          "app/archive.py": FUTURE + """

def api(event, ctx):
    return {"files": []}


def glacier(event, ctx):
    return {"synced": True}
""",
          "requirements.txt": ""}),
      user="We now also deploy this with -p onprem. glacier-sync talks to S3 Glacier and makes no sense on our own server. Keep it on AWS, drop it only on-prem.",
      steps=[
          S("get_project"),
          S("search_docs", query="disable a function on one provider", docs=[D("docs/configuration.md", "switch-something-off-on-one-cloud")]),
          S("propose_plan", steps=["Add `providers.onprem.functions.glacier-sync.enabled: false`",
                                   "Validate with -p onprem and -p aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.onprem.functions", value={"glacier-sync": {"enabled": False}}),
          S("validate", provider="aws"),
          S("invoke_local", function="api", method="GET", path="/files"),
      ],
      final="""Done:

```yaml
providers:
  onprem:
    functions:
      glacier-sync: {enabled: false}
```

The block applies only when the target is onprem [docs/configuration.md#switch-something-off-on-one-cloud].

- `-p onprem`: valid. The only warning is that `glacier-sync` is disabled, which is what you asked for.
- `-p aws`: valid, both functions as before.
- `GET /files`: 200.

Deploy: `pskit deploy -p onprem -s staging` (no glacier-sync) and `pskit deploy -s staging` (AWS, with it)."""),

    # ------------------------------------------------------------------ 283
    B(283, stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/handlers.md#record", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": yml("meter", 8283, """functions:
  read-meter:
    handler: app.meter.read
    events:
    - queue: {name: readings, batch_size: 20}
"""),
          "app/__init__.py": "",
          "app/meter.py": FUTURE + """from py_serverless_kit import BatchResult


def read(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            reading = record.json()
            ctx.logger.info("reading", extra={"meter": reading["meter"], "kwh": reading["kwh"]})
        except Exception:
            result.fail(record)
    return result
""",
          "requirements.txt": ""}),
      user="""every message fails:

{"batchItemFailures": [{"itemIdentifier": "local-1"}]}

the old meters don't send json, they send plain lines like `M-17;4.25` (meter;kwh). the new ones send json. make read-meter accept both""",
      steps=[
          S("read_file", path="app/meter.py"),
          S("invoke_local", function="read-meter", type="queue", data=["M-17;4.25"]),
          S("propose_plan", steps=["Parse JSON bodies when they start with `{`, otherwise split record.text() on `;`",
                                   "Keep failing only records that match neither format",
                                   "Invoke with one plain line, one JSON and one broken message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/meter.py", content=FUTURE + """from py_serverless_kit import BatchResult


def parse(record):
    text = record.text().strip()
    if text.startswith("{"):
        data = record.json()
        return str(data["meter"]), float(data["kwh"])
    meter, kwh = text.split(";")
    return meter.strip(), float(kwh)


def read(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            meter, kwh = parse(record)
        except Exception:
            ctx.logger.warning("bad reading", extra={"record_id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("reading", extra={"meter": meter, "kwh": kwh})
    return result
"""),
          S("validate"),
          S("invoke_local", function="read-meter", type="queue", data=["M-17;4.25", {"meter": "M-18", "kwh": 1.5}, "garbage"]),
      ],
      final="""Cause: `record.json()` fails for a plain line like `M-17;4.25`, so the `except` marked every old-meter message as failed.

Now `parse()` reads `record.text()`. A body starting with `{` is parsed as JSON. Anything else is split as `meter;kwh` [docs/handlers.md#record]. Only messages that match neither format are failed [docs/handlers.md#batchresult], and they are logged as "bad reading".

Checks:
- `pskit validate` (onprem): valid.
- `["M-17;4.25", {"meter": "M-18", "kwh": 1.5}, "garbage"]`: only `local-2` (the third, garbage message) is in `batchItemFailures`.

Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 284
    B(284, stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/providers.md#logs-and-stats"],
      project=dict(files={
          "pskit.yml": yml("kiosk-api", 8284, """functions:
  api:
    handler: app.kiosk.api
    events:
    - http: GET /
""", "    host: 0.0.0.0\n    log_retention_days: 30\n"),
          "app/__init__.py": "",
          "app/kiosk.py": FUTURE + """

def api(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="""validate:

  WARNING: [provider.options.log_retention_days] unknown option 'log_retention_days' is ignored

i want to keep logs 30 days on the server, and the logs page should show more than now""",
      steps=[
          S("get_validation"),
          S("search_docs", query="on premises logs kept rotate buffer", docs=[D("docs/providers.md", "logs-and-stats", start="Entries written during an invocation", end="Messages longer than 16 KiB are truncated.")]),
          S("propose_plan", steps=["Remove provider.options.log_retention_days (not an on-prem option)",
                                   "Set provider.options.log_buffer: 20000 (entries kept in memory for the logs page)",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.log_retention_days", value=None),
          S("set_config", path="provider.options.log_buffer", value=20000),
      ],
      final="""On premises there is no retention in days, so I removed `log_retention_days` and set:

```yaml
provider:
  options:
    log_buffer: 20000      # entries kept in memory for the logs page / pskit logs (default 5000)
```

How the host keeps logs [docs/providers.md#logs-and-stats]:
- every entry is also appended to `<data_dir>/logs/host.jsonl`;
- that file rotates at 10 MiB and keeps three old files, so how many days you get depends on how much you log;
- the history is reloaded on restart.

`pskit validate` (onprem, prod): valid, no warnings.

If you need exactly 30 days, ship `host.jsonl` to your log system, or copy it daily with a cron job on the server. Deploy: **Deploy** page or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 285
    B(285, stage="prod", mode="auto", page="Load balancers", persona="pasted_error",
      sources=["docs/load-balancers.md#the-six-algorithms"],
      project=dict(files={
          "pskit.yml": yml("portal", 8285, """functions:
  web:
    handler: app.portal.web
    events:
    - http: GET /
""", "    host: 0.0.0.0\n    advertise: http://192.0.2.10:8285\n    balancer: {name: edge, path: portal, algorithm: ip_hash}\n"),
          "app/__init__.py": "",
          "app/portal.py": FUTURE + """

def web(event, ctx):
    return {"portal": "ok"}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="""pskit lb logs edge -n 5
  ... 198.51.100.4 "GET /portal/ HTTP/1.1" 200 upstream=192.0.2.10:8285
  ... 198.51.100.4 "GET /portal/ HTTP/1.1" 200 upstream=192.0.2.10:8285
  ... 198.51.100.4 "GET /portal/ HTTP/1.1" 200 upstream=192.0.2.10:8285

whole office is behind one NAT ip -> all on one server. portal has no sessions. fix""",
      steps=[
          S("get_project"),
          S("search_docs", query="ip_hash NAT least connections", docs=[D("docs/load-balancers.md", "the-six-algorithms", words=200)]),
          S("propose_plan", steps=["balancer.algorithm: least_connections (no stickiness needed)", "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.balancer", value={"name": "edge", "path": "portal", "algorithm": "least_connections"}),
      ],
      final="""Switched to `least_connections`:

```yaml
provider:
  options:
    balancer: {name: edge, path: portal, algorithm: least_connections}
```

`ip_hash` maps one client IP to one server, so many users behind one NAT land on one server. `least_connections` picks the server with the fewest requests in progress, and the portal has no sessions to keep [docs/load-balancers.md#the-six-algorithms].

validate (onprem, prod): valid.

`pskit deploy -s prod` updates the route. Then `pskit lb logs edge -n 50` should show several `upstream=` addresses."""),

    # ------------------------------------------------------------------ 286
    B(286, stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={"pskit.yml": yml("orders", 8286, "functions: {}\n"), "requirements.txt": ""}),
      user="POST /orders takes {customer_email, items: [{sku, qty}]}. Validate it: email must contain @, items non-empty, each qty an integer 1-99. On problems answer 422 with ALL field errors at once, like {\"error\": \"invalid order\", \"details\": {\"items.0.qty\": \"must be 1-99\"}}. Valid orders: 201 with an order id.",
      steps=[
          S("get_project"),
          S("search_docs", query="422 error details field", docs=[D("docs/handlers.md", "errors", words=170)]),
          S("propose_plan", steps=["Write `app/orders.py`: collect errors in a dict, raise UnprocessableEntity('invalid order', details=errors), else 201",
                                   "Add `create-order` on POST /orders", "Validate, invoke one bad and one good order"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/orders.py", content=FUTURE + """import uuid

from py_serverless_kit import UnprocessableEntity


def validate_order(body):
    errors = {}
    if "@" not in str(body.get("customer_email", "")):
        errors["customer_email"] = "must be an email address"
    items = body.get("items")
    if not isinstance(items, list) or not items:
        errors["items"] = "must be a non-empty list"
        return errors
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not item.get("sku"):
            errors[f"items.{i}.sku"] = "is required"
        qty = item.get("qty") if isinstance(item, dict) else None
        if not isinstance(qty, int) or isinstance(qty, bool) or not 1 <= qty <= 99:
            errors[f"items.{i}.qty"] = "must be 1-99"
    return errors


def create_order(event, ctx):
    body = event.http.json(default={}) or {}
    errors = validate_order(body)
    if errors:
        raise UnprocessableEntity("invalid order", details=errors)
    return {"order_id": uuid.uuid4().hex[:12], "items": len(body["items"])}, 201
"""),
          S("set_config", path="functions.create-order", value={"handler": "app.orders.create_order", "events": [{"http": "POST /orders"}]}),
          S("invoke_local", function="create-order", method="POST", path="/orders",
            data={"customer_email": "nobody", "items": [{"sku": "A1", "qty": 0}, {"qty": 3}]}),
          S("invoke_local", function="create-order", method="POST", path="/orders",
            data={"customer_email": "kim@example.com", "items": [{"sku": "A1", "qty": 2}]}),
      ],
      final="""Done. `create-order` on `POST /orders` collects every problem first, then raises `UnprocessableEntity("invalid order", details=errors)`, which pskit turns into a 422 with your `details` [docs/handlers.md#errors].

Checks:
- `pskit validate` (onprem): valid.
- Bad order: **422** with `customer_email`, `items.0.qty` and `items.1.sku` errors together.
- `{"customer_email": "kim@example.com", "items": [{"sku": "A1", "qty": 2}]}`: **201** with an `order_id`.

The order is not stored yet; that is the next step. Test again on **Test** or with `pskit invoke -f create-order --method POST --path /orders -d @order.json`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 287
    B(287, stage="staging", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#fields"],
      project=dict(files={
          "pskit.yml": yml("shop", 8287, """resources:
  psp-db:
    type: database
    external: true
    connection: {host: db-2.example.com, port: 5432, database: payments, password_env: PSP_DB_PASSWORD}
functions:
  catalog:
    handler: app.shop.catalog
    events:
    - http: GET /catalog
  pay:
    handler: app.shop.pay
    events:
    - http: POST /pay
"""),
          "app/__init__.py": "",
          "app/shop.py": FUTURE + """from py_serverless_kit import resources


def catalog(event, ctx):
    return {"bound": sorted(resources())}


def pay(event, ctx):
    return {"bound": sorted(resources())}
""",
          "requirements.txt": ""}),
      user="psp-db binding only for pay. catalog must not even see its host",
      steps=[
          S("get_project"),
          S("search_docs", query="resource functions list binding", docs=[D("docs/resources.md", "fields", start="| `functions` |", end="| `functions` |")]),
          S("propose_plan", steps=["resources.psp-db.functions: [pay]", "Validate (onprem, staging), invoke catalog and pay"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.psp-db.functions", value=["pay"]),
          S("invoke_local", function="catalog", method="GET", path="/catalog"),
          S("invoke_local", function="pay", method="POST", path="/pay"),
      ],
      final="""Set `resources.psp-db.functions: [pay]`. Without the list, every function you wrote gets the binding [docs/resources.md#fields].

- validate (onprem, staging): valid.
- `catalog`: `{"bound": []}`, so no `PSKIT_RESOURCE_PSP_DB_*` variables.
- `pay`: `{"bound": ["psp-db"]}`.

`resource("psp-db")` in catalog now raises "not bound to this function". Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 288
    B(288, stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/configuration.md#hooks"],
      project=dict(files={
          "pskit.yml": yml("status", 8288, """functions:
  health:
    handler: app.status.health
    events:
    - http: GET /health
""", "    host: 0.0.0.0\n    advertise: http://192.0.2.10:8288\n"),
          "app/__init__.py": "",
          "app/status.py": FUTURE + """

def health(event, ctx):
    return {"status": "ok"}
""",
          "requirements.txt": ""}),
      user="after each deploy i open the /health in browser by hand to see it works. can pskit do it automatic and tell me when it is broken?",
      steps=[
          S("get_project"),
          S("search_docs", query="hook after deploy smoke test", docs=[D("docs/configuration.md", "hooks")]),
          S("propose_plan", steps=["Write `scripts/smoke.py`: GET SMOKE_URL (default http://192.0.2.10:8288/health), exit 1 unless status 200 and status ok",
                                   "Add `hooks.after_deploy: [python scripts/smoke.py]`", "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="scripts/smoke.py", content=FUTURE + """import json
import os
import sys
import urllib.request

URL = os.environ.get("SMOKE_URL", "http://192.0.2.10:8288/health")

try:
    with urllib.request.urlopen(URL, timeout=10) as resp:
        body = json.loads(resp.read() or b"{}")
        ok = resp.status == 200 and body.get("status") == "ok"
except Exception as exc:
    print(f"smoke test FAILED: {URL}: {exc}")
    sys.exit(1)
if not ok:
    print(f"smoke test FAILED: {URL} answered {body}")
    sys.exit(1)
print(f"smoke test ok: {URL}")
"""),
          S("set_config", path="hooks", value={"after_deploy": ["python scripts/smoke.py"]}),
          S("invoke_local", function="health", method="GET", path="/health"),
      ],
      final="""Yes. After every `pskit deploy`, pskit now runs `python scripts/smoke.py` [docs/configuration.md#hooks]:

```yaml
hooks:
  after_deploy: ["python scripts/smoke.py"]
```

The script calls `http://192.0.2.10:8288/health` (or `SMOKE_URL` if set). It prints `smoke test ok` when it gets 200 with `"status": "ok"`. Otherwise it prints `smoke test FAILED ...` and exits with an error, so the deploy command ends with an error and you see it at once.

- `pskit validate` (onprem, prod): valid.
- `GET /health` locally: 200 `{"status": "ok"}`, the answer the script expects.

The hook runs on your machine, so it must reach 192.0.2.10:8288. The deploy itself is already done when the hook fails; it only tells you. Deploy: **Deploy** page or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 289
    B(289, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": yml("menu", 8289, """functions:
  dishes:
    handler: app.menu.dishes
    events:
    - http: GET /dishes
"""),
          "app/__init__.py": "",
          "app/menu.py": FUTURE + """
DISHES = [
    {"name": "soup", "price": 4.5},
    {"name": "pasta", "price": 9.0},
    {"name": "salad", "price": 6.0},
]


def dishes(event, ctx):
    return {"dishes": DISHES}
""",
          "requirements.txt": ""}),
      user="can the dishes list be sorted? like /dishes?sort=price or sort=name, and order=desc for the other way",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Update `dishes`: read ?sort (name|price, default name) and ?order (asc|desc), 400 for other values",
                                   "Validate for onprem and try sort=price&order=desc"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/menu.py", content=FUTURE + """from py_serverless_kit import BadRequest

DISHES = [
    {"name": "soup", "price": 4.5},
    {"name": "pasta", "price": 9.0},
    {"name": "salad", "price": 6.0},
]


def dishes(event, ctx):
    sort = event.http.query.get("sort", "name")
    order = event.http.query.get("order", "asc")
    if sort not in ("name", "price") or order not in ("asc", "desc"):
        raise BadRequest("sort must be name or price, order asc or desc")
    items = sorted(DISHES, key=lambda d: d[sort], reverse=(order == "desc"))
    return {"dishes": items}
"""),
          S("validate"),
          S("invoke_local", function="dishes", method="GET", path="/dishes?sort=price&order=desc"),
      ],
      final="""Yes. `GET /dishes` now takes two query parameters from `event.http.query` [docs/handlers.md#httprequest]:

- `sort=name` (default) or `sort=price`
- `order=asc` (default) or `order=desc`

Other values give a 400 with a short message.

Checks:
- `pskit validate` (onprem): valid.
- `/dishes?sort=price&order=desc`: pasta (9.0), salad (6.0), soup (4.5).

Try it on **Test** with the path `/dishes?sort=name`, or `pskit invoke -f dishes --method GET --path "/dishes?sort=name"`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 290
    B(290, stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={"pskit.yml": yml("importer", 8290, "functions: {}\n"), "requirements.txt": ""}),
      user="POST /import, body = raw csv (header sku,qty). return rows count + sum qty. bad qty -> 400 with line no",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/importer.py`: csv.DictReader over event.http.text(), BadRequest naming the line",
                                   "Add `import-csv` on POST /import", "Validate, invoke with 2 rows"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/importer.py", content=FUTURE + """import csv
import io

from py_serverless_kit import BadRequest


def import_csv(event, ctx):
    reader = csv.DictReader(io.StringIO(event.http.text()))
    rows = 0
    total = 0
    for line, row in enumerate(reader, start=2):
        try:
            total += int(row["qty"])
        except (KeyError, TypeError, ValueError):
            raise BadRequest(f"line {line}: qty must be an integer")
        rows += 1
    return {"rows": rows, "qty": total}
"""),
          S("set_config", path="functions.import-csv", value={"handler": "app.importer.import_csv", "events": [{"http": "POST /import"}]}),
          S("invoke_local", function="import-csv", method="POST", path="/import", data="sku,qty\nA1,3\nB2,4\n"),
      ],
      final="""Done: `import-csv` on `POST /import`. It reads the body with `event.http.text()` and `csv.DictReader` [docs/handlers.md#httprequest]. A bad `qty` gives `400 "line N: qty must be an integer"`; line 1 is the header.

- validate (onprem, staging): valid.
- `sku,qty / A1,3 / B2,4`: 200 `{"rows": 2, "qty": 7}`.

Call: `curl --data-binary @stock.csv -H "Content-Type: text/csv" http://<host>:8290/import`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 291
    B(291, stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={"pskit.yml": yml("transfers", 8291, "functions: {}\n", "    host: 0.0.0.0\n"), "requirements.txt": ""}),
      user="POST /transfers must be idempotent: clients send an Idempotency-Key header. Same key again within an hour -> return the first response again, without doing the transfer twice. No key -> 400. Keep it in memory for now, it's one server.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/transfers.py`: dict key -> (time, response), 1 h TTL; 400 without the header",
                                   "Add `create-transfer` on POST /transfers", "Validate (onprem, prod), invoke"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/transfers.py", content=FUTURE + """import time
import uuid

from py_serverless_kit import BadRequest

TTL = 3600
_SEEN = {}


def create_transfer(event, ctx):
    key = event.http.headers.get("idempotency-key", "").strip()
    if not key:
        raise BadRequest("Idempotency-Key header is required")
    now = time.time()
    for old in [k for k, (t, _) in _SEEN.items() if now - t > TTL]:
        del _SEEN[old]
    if key in _SEEN:
        return _SEEN[key][1]
    body = event.http.json(default={}) or {}
    response = {"transfer_id": uuid.uuid4().hex[:12], "amount": body.get("amount")}
    _SEEN[key] = (now, response)
    return response
"""),
          S("set_config", path="functions.create-transfer", value={"handler": "app.transfers.create_transfer", "events": [{"http": "POST /transfers"}]}),
          S("invoke_local", function="create-transfer", method="POST", path="/transfers", data={"amount": 250}),
      ],
      final="""Added `create-transfer` on `POST /transfers`:

- reads `Idempotency-Key` from `event.http.headers` (case-insensitive) [docs/handlers.md#httprequest];
- a key seen in the last hour gets the stored first response back, with no second transfer;
- no key: **400** "Idempotency-Key header is required" [docs/handlers.md#errors].

Checks:
- `pskit validate` (onprem, prod): valid.
- `POST /transfers {"amount": 250}` without the header: **400**, the no-key case.

Test the repeat yourself (invoke_local here can't send headers):
```bash
pskit invoke -f create-transfer --method POST --path /transfers -H "Idempotency-Key: t-1" -d '{"amount": 250}'
```
Within one `pskit invoke`, memory starts empty. Call the deployed host twice with curl to see the same `transfer_id`.

Limits: memory only, lost on restart, and per server. With a second server or replicas, move it to Redis or a database. Deploy: `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 292
    B(292, stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": yml("reports", 8292, """resources:
  reports:
    type: storage
functions:
  daily-report:
    handler: app.reports.daily
    events:
    - schedule: 0 6 * * *
"""),
          "app/__init__.py": "",
          "app/reports.py": FUTURE + """import boto3


def daily(event, ctx):
    body = "day,orders\\n2026-11-01,42\\n"
    boto3.client("s3").put_object(Bucket="acme-reports", Key="daily.csv", Body=body.encode())
    return {"written": "daily.csv"}
""",
          "requirements.txt": "boto3\n"}),
      user="This came from Lambda and still uses boto3 to put the CSV into S3. On-prem it should go into the built-in `reports` bucket that's already in pskit.yml. No more AWS.",
      steps=[
          S("read_file", path="app/reports.py"),
          S("search_docs", query="write object to bucket from handler on premises",
            docs=[D("docs/providers.md", "onprem-on-premises", start="From a handler in that process", end="From a handler in that process")]),
          S("propose_plan", steps=["Replace boto3 with put_object(resource('reports').native_name, ...) inside the host, log locally",
                                   "Drop boto3 from requirements.txt", "Validate, run the schedule"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/reports.py", content=FUTURE + """from py_serverless_kit import resource


def daily(event, ctx):
    body = "day,orders\\n2026-11-01,42\\n".encode("utf-8")
    bucket = resource("reports").native_name
    if ctx.env.get("PSKIT_ONPREM_ROOT"):
        from py_serverless_kit.runtime.onprem_host import put_object

        put_object(bucket, "daily.csv", body)
    else:
        ctx.logger.info("would write", extra={"bucket": bucket, "bytes": len(body)})
    return {"written": f"{bucket}/daily.csv"}
"""),
          S("write_file", path="requirements.txt", content=""),
          S("validate"),
          S("invoke_local", function="daily-report", type="schedule"),
      ],
      final="""Done. `boto3.client("s3").put_object(...)` is now `put_object(bucket, key, data)` from `py_serverless_kit.runtime.onprem_host`. It writes into the host's built-in bucket [docs/providers.md#onprem-on-premises]. The bucket name comes from `resource("reports").native_name`, so it is not hard-coded [docs/resources.md#runtime-api]. boto3 is gone from `requirements.txt`.

- `pskit validate` (onprem): valid.
- Schedule run: `{"written": "reports/daily.csv"}`. Locally there is no host, so it only logged "would write".

After deploy, the file is under the `reports` bucket in the host's `data_dir`; browse it on **Resources > Data**. Deploy: **Deploy** page or `pskit deploy -s dev`."""),


    # ------------------------------------------------------------------ 293
    B(293, stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": yml("scans", 8293, """functions:
  ocr-scan:
    handler: app.scans.ocr
    events:
    - storage: {bucket: scans, events: [created], prefix: inbox/, suffix: .pdf}
"""),
          "app/__init__.py": "",
          "app/scans.py": FUTURE + """

def ocr(event, ctx):
    return {"done": [r.key for r in event.records]}
""",
          "requirements.txt": ""}),
      user="ocr-scan only run for .pdf. the new scanner make .tif files too, also in inbox/. both must start it",
      steps=[
          S("get_project"),
          S("search_docs", query="storage event suffix prefix several", docs=[D("docs/events.md", "storage", words=170)]),
          S("propose_plan", steps=["Keep the .pdf trigger and add a second storage event with suffix .tif (same bucket and prefix)",
                                   "Validate (onprem, staging), invoke with a .tif"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ocr-scan.events",
            value=[{"storage": {"bucket": "scans", "events": ["created"], "prefix": "inbox/", "suffix": ".pdf"}},
                   {"storage": {"bucket": "scans", "events": ["created"], "prefix": "inbox/", "suffix": ".tif"}}]),
          S("invoke_local", function="ocr-scan", type="storage", data=[{"bucket": "scans", "key": "page-7.tif", "size": 40960}]),
      ],
      final="""`suffix` takes one ending, so `ocr-scan` now has two storage events, one per type:

```yaml
functions:
  ocr-scan:
    events:
      - storage: {bucket: scans, events: [created], prefix: inbox/, suffix: .pdf}
      - storage: {bucket: scans, events: [created], prefix: inbox/, suffix: .tif}
```

[docs/events.md#storage]

- validate (onprem, staging): valid.
- invoke with `page-7.tif`: `{"done": ["page-7.tif"]}`.

If the scanner also writes `.tiff`, add a third event. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 294
    B(294, stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": yml("helpdesk", 8294, """functions:
  api:
    handler: app.desk.api
    events:
    - http: GET /
"""),
          "app/__init__.py": "",
          "app/desk.py": FUTURE + """

def api(event, ctx):
    return {"desk": "ok"}
""",
          "VERSION": "2.4.1\n",
          "requirements.txt": ""}),
      user="we write the version in the file VERSION when we release. i want GET /version to show it, without me copying it to the yml every time",
      steps=[
          S("get_project"),
          S("search_docs", query="read value from a file variable", docs=[D("docs/configuration.md", "variables", end="| `${file(path.json)}` |")]),
          S("propose_plan", steps=["Write `app/version.py`: return ctx.env APP_VERSION",
                                   "Add function `version` on GET /version with APP_VERSION: ${file(VERSION)}",
                                   "Validate for onprem (prod) and call /version"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/version.py", content=FUTURE + """

def version(event, ctx):
    return {"version": ctx.env.get("APP_VERSION", "unknown")}
"""),
          S("set_config", path="functions.version",
            value={"handler": "app.version.version", "environment": {"APP_VERSION": "${file(VERSION)}"},
                   "events": [{"http": "GET /version"}]}),
          S("invoke_local", function="version", method="GET", path="/version"),
      ],
      final="""Done. `APP_VERSION: ${file(VERSION)}` reads the file when pskit loads `pskit.yml`. Files that are not JSON or YAML are used as stripped text [docs/configuration.md#variables].

```yaml
functions:
  version:
    handler: app.version.version
    environment:
      APP_VERSION: ${file(VERSION)}
    events:
      - http: GET /version
```

- `pskit validate` (onprem, prod): valid.
- `GET /version`: 200 `{"version": "2.4.1"}`.

When you release, change `VERSION` and deploy again: **Deploy** page or `pskit deploy -s prod`. The value is read at deploy time, not while the host runs."""),

    # ------------------------------------------------------------------ 295
    B(295, stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": yml("profile", 8295, """functions:
  me:
    handler: app.profile.me
    events:
    - http: GET /me
"""),
          "app/__init__.py": "",
          "app/profile.py": FUTURE + """

def me(event, ctx):
    return {"user": "demo"}
""",
          "requirements.txt": ""}),
      user="""The Lambda had a function URL with this CORS config:

```yaml
FunctionUrlConfig:
  Cors:
    AllowOrigins: [https://app.example.com]
    AllowMethods: [GET, POST]
    AllowHeaders: [authorization, content-type]
    AllowCredentials: true
    MaxAge: 3600
```

Same CORS for GET /me here.""",
      steps=[
          S("get_project"),
          S("search_docs", query="cors origins methods headers allow_credentials max_age",
            docs=[D("docs/events.md", "http", start="**CORS**", words=150)]),
          S("propose_plan", steps=["Set functions.me.events.0.http: {path: /me, method: GET, cors: {origins, methods, headers, allow_credentials, max_age}}",
                                   "Validate (onprem, staging), invoke"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.me.events",
            value=[{"http": {"path": "/me", "method": "GET",
                             "cors": {"origins": ["https://app.example.com"], "methods": ["GET", "POST"],
                                      "headers": ["authorization", "content-type"], "allow_credentials": True, "max_age": 3600}}}]),
          S("invoke_local", function="me", method="GET", path="/me"),
      ],
      final="""Same settings, pskit names:

```yaml
functions:
  me:
    events:
      - http:
          path: /me
          method: GET
          cors:
            origins: [https://app.example.com]
            methods: [GET, POST]
            headers: [authorization, content-type]
            allow_credentials: true
            max_age: 3600
```

[docs/events.md#http]

- validate (onprem, staging): valid.
- `GET /me`: 200 `{"user": "demo"}`.

With `allow_credentials: true`, keep the origin a real URL, not `*`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 296
    B(296, stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": yml("tickets", 8296, """functions:
  api:
    handler: app.tickets.api
    events:
    - http: GET /
""", "    host: 0.0.0.0\n    deploy:\n      server: app-2\n      path: /opt/pskit/tickets\n"),
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """

def api(event, ctx):
    return {"tickets": []}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="""validate warns

  WARNING: [provider.options.deploy.python] the remote host must already have python3.12 on PATH. Set options.deploy.python: bundle to ship a portable interpreter, or method: docker.

`pskit resources onprem servers test app-2` says python=3.10.12. I don't want to bundle, use the 3.10 that's there""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set provider.runtime: python3.10 and deploy.python: system", "Validate (onprem, prod), invoke"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value="python3.10"),
          S("set_config", path="provider.options.deploy.python", value="system"),
          S("invoke_local", function="api", method="GET", path="/"),
      ],
      final="""Done:

```yaml
provider:
  runtime: python3.10
  options:
    deploy:
      server: app-2
      path: /opt/pskit/tickets
      python: system      # use the python3.10 on the server
```

The warning came from the default runtime `python3.12`. With `runtime: python3.10`, pskit expects the `python3.10` that app-2 already has [docs/providers.md#onprem-on-premises].

`pskit validate` (onprem, prod): valid. The warning now says the server must have python3.10 on PATH, which app-2 has. Local `GET /`: 200.

Your handlers must run on 3.10. Deploy: **Deploy** page or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 297
    B(297, stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": yml("sync", 8297, """functions:
  pull-erp:
    handler: app.erp.pull
"""),
          "app/__init__.py": "",
          "app/erp.py": FUTURE + """

def pull(event, ctx):
    return {"pulled": True}
""",
          "requirements.txt": ""}),
      user="pull-erp every 10 min 08:00-17:50 mon-fri, Europe/Berlin",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["schedule {cron: '*/10 8-17 * * 1-5', timezone: Europe/Berlin}", "Validate, run once"]),
          S("set_config", path="functions.pull-erp.events",
            value=[{"schedule": {"cron": "*/10 8-17 * * 1-5", "timezone": "Europe/Berlin"}}]),
          S("invoke_local", function="pull-erp", type="schedule"),
      ],
      final="""Set:

```yaml
- schedule: {cron: "*/10 8-17 * * 1-5", timezone: Europe/Berlin}
```

Hours `8-17` with `*/10` give 08:00, 08:10 ... 17:50, Monday to Friday [docs/events.md#schedule].

- validate (onprem): valid, with a warning that this computer has no timezone database, so it uses UTC here. `pskit deploy` adds `tzdata`, so the host uses Berlin time.
- run once: `{"pulled": true}`.

Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 298
    B(298, stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#returning-a-response", "docs/local-development.md"],
      project=dict(files={"pskit.yml": yml("visits", 8298, "functions: {}\n"), "requirements.txt": ""}),
      user="new project, just to learn: a visitor counter. POST /visits adds one, GET /visits shows how many. on my laptop",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/visits.py` with a counter in memory: `add` and `count`",
                                   "Add `add-visit` (POST /visits) and `count-visits` (GET /visits)",
                                   "Validate for onprem and try both"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/visits.py", content=FUTURE + """
COUNTER = {"visits": 0}


def add(event, ctx):
    COUNTER["visits"] += 1
    return COUNTER, 201


def count(event, ctx):
    return COUNTER
"""),
          S("set_config", path="functions.add-visit", value={"handler": "app.visits.add", "events": [{"http": "POST /visits"}]}),
          S("set_config", path="functions.count-visits", value={"handler": "app.visits.count", "events": [{"http": "GET /visits"}]}),
          S("invoke_local", function="add-visit", method="POST", path="/visits"),
          S("invoke_local", function="count-visits", method="GET", path="/visits"),
      ],
      final="""Done. Your project has two functions:

- `add-visit` on `POST /visits` adds one and answers 201;
- `count-visits` on `GET /visits` shows the number.

Checks:
- `pskit validate` (onprem): valid.
- `POST /visits`: 201 `{"visits": 1}`.
- `GET /visits`: `{"visits": 0}`. Each `pskit invoke` is a fresh run, so the count starts at 0 again.

To see it count up, start the local server with `pskit dev` (port 3000) and call `POST /visits` a few times. Or deploy it on this laptop: **Deploy** page or `pskit deploy -s dev`. The count lives in memory, so it resets when the host restarts."""),

    # ------------------------------------------------------------------ 299
    B(299, stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/nodejs.md#handlers", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: orders-js
provider:
  name: onprem
  region: local
  runtime: nodejs20
  options:
    port: 8299
functions:
  validate-order:
    handler: src.orders.validateOrder
  charge-order:
    handler: src.orders.chargeOrder
""",
          "src/orders.js": """class ValidationError extends Error {}

exports.validateOrder = async (event) => {
  const order = event.data || {};
  if (!order.total || order.total <= 0) throw new ValidationError("total must be positive");
  return { ...order, valid: true };
};

exports.chargeOrder = async (event) => ({ ...event.data, charged: true });
""",
          "package.json": json.dumps({"name": "orders-js", "version": "1.0.0", "private": True}, indent=2) + "\n"}),
      user="Our functions are JavaScript. Workflow `checkout`: validate-order then charge-order. If validate-order throws ValidationError, end the run in a Fail state with error InvalidOrder instead of retrying. Can the embedded workflows do that with JS functions?",
      steps=[
          S("get_project"),
          S("search_docs", query="node.js workflows embedded retry catch error class name",
            docs=[D("docs/nodejs.md", "handlers", start="The API mirrors the", end="(`class ValidationError extends Error {}` → `ValidationError`).")]),
          S("propose_plan", steps=["Add workflow `checkout`: validate (task, catch ValidationError -> rejected) -> charge (task, end); rejected: fail InvalidOrder",
                                   "Validate (onprem, staging), invoke validate-order"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.checkout",
            value={"start_at": "validate", "states": {
                "validate": {"type": "task", "function": "validate-order", "next": "charge",
                             "catch": [{"errors": ["ValidationError"], "next": "rejected"}]},
                "charge": {"type": "task", "function": "charge-order", "end": True},
                "rejected": {"type": "fail", "error": "InvalidOrder", "cause": "order did not pass validation"}}}),
          S("invoke_local", function="validate-order", type="invoke", data={"order_id": "O-1", "total": 25}),
      ],
      final="""Yes. On premises the host's embedded engine runs the workflow, and only the task functions run in Node.js [docs/providers.md#onprem-on-premises]. `catch` matches the JS error's class name, so `class ValidationError extends Error {}` is caught as `ValidationError` [docs/nodejs.md#handlers].

```yaml
workflows:
  checkout:
    start_at: validate
    states:
      validate:
        type: task
        function: validate-order
        next: charge
        catch: [{errors: [ValidationError], next: rejected}]
      charge:   {type: task, function: charge-order, end: true}
      rejected: {type: fail, error: InvalidOrder, cause: order did not pass validation}
```

There is no `retry`, so a ValidationError goes straight to `rejected`.

- `pskit validate` (onprem, staging): valid (embedded engine).
- `validate-order` with `total: 25`: `{"order_id": "O-1", "total": 25, "valid": true}`.

See the failing path: `pskit workflow run checkout -i '{"order_id": "O-2", "total": 0}' --history` should end with `InvalidOrder`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 300
    B(300, stage="prod", mode="ask", page="Setup", persona="pasted_error",
      sources=["docs/resources.md#troubleshooting", "docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": yml("media", 8300, """resources:
  media:
    type: storage
    external: true
    options: {driver: minio, endpoint: "http://minio.example.com:9000", bucket: media,
              access_key_env: MEDIA_ACCESS_KEY, secret_key_env: MEDIA_SECRET_KEY}
functions:
  on-media:
    handler: app.media.on_media
    events:
    - storage: {resource: media}
""", "    host: 0.0.0.0\n"),
          "app/__init__.py": "",
          "app/media.py": FUTURE + """

def on_media(event, ctx):
    return {"seen": [r.key for r in event.records]}
""",
          "requirements.txt": ""}),
      user="""the deployed host does not start, logs say:

environment variable MEDIA_SECRET_KEY (option secret_key_env of resource media) is not set on the host

on my laptop both are exported. how do they get to the server? don't put the keys in pskit.yml""",
      steps=[
          S("get_project"),
          S("search_docs", query="secret_key_env not set on the host env_file",
            docs=[D("docs/resources.md", "on-premises-drivers", start="**Secrets.**", end="**Secrets.**")]),
          S("propose_plan", steps=["Set provider.options.env_file: .env.onprem",
                                   "Write `.env.onprem` with MEDIA_ACCESS_KEY and MEDIA_SECRET_KEY placeholders, and `.gitignore` for it",
                                   "Validate (onprem, prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.env_file", value=".env.onprem"),
          S("write_file", path=".env.onprem", content="# real values go here; never committed\nMEDIA_ACCESS_KEY=<fill in>\nMEDIA_SECRET_KEY=<fill in>\n"),
          S("write_file", path=".gitignore", content=".env.onprem\n"),
          S("validate"),
          S("invoke_local", function="on-media", type="storage", data=[{"key": "a.jpg", "size": 10}]),
      ],
      final="""Cause: `*_env` options are read from the **host's** environment when it starts. Variables exported on your laptop don't travel with the deploy [docs/resources.md#on-premises-drivers].

Fix:
- `provider.options.env_file: .env.onprem`: the file is copied next to the host as `host.env` and loaded at start, for local, SSH and Docker deploys. Only its digest is recorded.
- `.env.onprem` has `MEDIA_ACCESS_KEY` and `MEDIA_SECRET_KEY` with the placeholder `<fill in>`. Put the real values in with an editor.
- `.gitignore` keeps it out of git.

Checks:
- `pskit validate` (onprem, prod): valid.
- `on-media` with a sample object: `{"seen": ["a.jpg"]}`.

Then deploy again: **Deploy** page (type the confirmation) or `pskit deploy -s prod`. The host starts once both variables are set."""),
]
