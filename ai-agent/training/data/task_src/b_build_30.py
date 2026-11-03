"""Category B (build / add), batch 30 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 581
    B(581, provider="aws", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: expenses
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="New expense tracker: POST /expenses with {amount, category} (amount > 0, else 400), GET /expenses/{month} with month as YYYY-MM, and a report job at 07:00 UTC on the 1st of each month. In-memory storage is fine for this first version.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/expenses.py: add, by_month and monthly_report sharing an in-memory list",
                                   "Functions add-expense (POST /expenses), list-expenses (GET /expenses/{month}), monthly-report (schedule \"0 7 1 * *\")",
                                   "Validate for aws, invoke add and list"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/expenses.py", content=FUTURE + """import datetime
import re

from py_serverless_kit import BadRequest

_EXPENSES = []  # first version only: lost on every cold start


def add(event, ctx):
    body = event.http.json(default={}) or {}
    amount = body.get("amount")
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise BadRequest("amount must be a number greater than 0")
    item = {"amount": amount, "category": body.get("category", "other"),
            "month": datetime.date.today().strftime("%Y-%m")}
    _EXPENSES.append(item)
    return item, 201


def by_month(event, ctx):
    month = event.http.path_params["month"]
    if not re.fullmatch(r"\\d{4}-\\d{2}", month):
        raise BadRequest("month must be YYYY-MM")
    items = [e for e in _EXPENSES if e["month"] == month]
    return {"month": month, "items": items, "total": sum(e["amount"] for e in items)}


def monthly_report(event, ctx):
    ctx.logger.info("monthly report", extra={"expenses": len(_EXPENSES)})
    return {"expenses": len(_EXPENSES)}
"""),
          S("set_config", path="functions.add-expense", value={"handler": "app.expenses.add", "events": [{"http": "POST /expenses"}]}),
          S("set_config", path="functions.list-expenses", value={"handler": "app.expenses.by_month", "events": [{"http": "GET /expenses/{month}"}]}),
          S("set_config", path="functions.monthly-report", value={"handler": "app.expenses.monthly_report", "events": [{"schedule": "0 7 1 * *"}]}),
          S("invoke_local", function="add-expense", method="POST", path="/expenses", data={"amount": 12.5, "category": "lunch"}),
          S("invoke_local", function="list-expenses", method="GET", path="/expenses/2026-13x"),
      ],
      final="""The tracker has three functions:

| Function | Trigger |
|---|---|
| `add-expense` | `POST /expenses` (amount must be > 0) |
| `list-expenses` | `GET /expenses/{month}` (`YYYY-MM`) |
| `monthly-report` | `0 7 1 * *`: 07:00 UTC on the 1st |

Checks: `pskit validate` (aws) valid after each function; add 12.5 lunch → **201**; `GET /expenses/2026-13x` → **400** `month must be YYYY-MM`.

Note: each Lambda function has its own memory, so the in-memory list isn't shared between them and is lost on cold starts. It's fine for trying the API; the next step is a real table (for example DynamoDB). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 582
    B(582, provider="gcp", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#using-a-resource-from-an-event", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: thumbs
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, thumbs-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="Two managed buckets: `originals` (native name thumbs-originals-5521) and `thumbnails` (thumbs-thumbnails-5521). Function `make-thumb` runs for new .jpg files in originals via the resource, and is the only function bound to thumbnails, where it will write. For now return where it would write.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.originals {type: storage, name: thumbs-originals-5521}",
                                   "resources.thumbnails {type: storage, name: thumbs-thumbnails-5521, functions: [make-thumb]}",
                                   "Write app/thumbs.py; make-thumb with storage {resource: originals, suffix: .jpg, events: [created]}",
                                   "Validate gcp, invoke a storage event"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.originals", value={"type": "storage", "name": "thumbs-originals-5521"}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/thumbs.py", content=FUTURE + """from py_serverless_kit import resource


def make_thumb(event, ctx):
    target = resource("thumbnails")
    out = []
    for r in event.records:
        # TODO: download r.key, resize, upload with google-cloud-storage
        out.append({"from": f"{r.bucket}/{r.key}", "to": f"{target.native_name}/thumb-{r.key}"})
    return out
"""),
          S("set_config", path="functions.make-thumb",
            value={"handler": "app.thumbs.make_thumb",
                   "events": [{"storage": {"resource": "originals", "suffix": ".jpg", "events": ["created"]}}]}),
          S("set_config", path="resources.thumbnails",
            value={"type": "storage", "name": "thumbs-thumbnails-5521", "functions": ["make-thumb"]}),
          S("invoke_local", function="make-thumb", type="storage", data={"bucket": "thumbs-originals-5521", "key": "cat.jpg"}),
      ],
      final="""Set up:

```yaml
resources:
  originals:  {type: storage, name: thumbs-originals-5521}
  thumbnails: {type: storage, name: thumbs-thumbnails-5521, functions: [make-thumb]}
functions:
  make-thumb:
    handler: app.thumbs.make_thumb
    events:
      - storage: {resource: originals, suffix: .jpg, events: [created]}
```

- The event uses the resource's native name [docs/resources.md#using-a-resource-from-an-event]; `resource("thumbnails").native_name` gives the target bucket [docs/resources.md#runtime-api].
- `pskit validate` (gcp): valid after each change.
- invoke with `cat.jpg`: `to: thumbs-thumbnails-5521/thumb-cat.jpg`.

The resize/upload is a TODO (add `google-cloud-storage` and `Pillow` to requirements.txt). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 583
    B(583, provider="azure", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/providers.md#azure-azure-functions", "docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": """service: weather
provider:
  name: azure
  region: westeurope
functions:
  forecast:
    handler: app.weather.forecast
    events:
    - http: GET /forecast
""",
          "app/__init__.py": "",
          "app/weather.py": FUTURE + """

def forecast(event, ctx):
    return {"days": []}
""",
          "requirements.txt": ""}),
      user="On Lambda, requests and python-dateutil came from a shared layer. Azure has no layers, right? How do I get them, and can forecast use dateutil to return the next 3 dates?",
      steps=[
          S("get_project"),
          S("search_docs", query="azure dependencies requirements remote build",
            docs=[D("docs/providers.md", "azure-azure-functions", end="- **Dependencies:**")]),
          S("propose_plan", steps=["Put requests and python-dateutil in requirements.txt (Azure installs them with a remote build)",
                                   "forecast: return the next 3 dates using dateutil.relativedelta",
                                   "Validate for azure, invoke GET /forecast"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="requirements.txt", content="requests>=2.31\npython-dateutil>=2.8\n"),
          S("write_file", path="app/weather.py", content=FUTURE + """import datetime

from dateutil.relativedelta import relativedelta


def forecast(event, ctx):
    today = datetime.date.today()
    days = [(today + relativedelta(days=n)).isoformat() for n in range(1, 4)]
    return {"days": days}
"""),
          S("validate"),
          S("invoke_local", function="forecast", method="GET", path="/forecast"),
      ],
      final="""Right, there are no layers here. On Azure, dependencies come from `requirements.txt`: the remote Oryx build installs them when you deploy [docs/providers.md#azure-azure-functions] [docs/configuration.md#package].

- requirements.txt: `requests>=2.31`, `python-dateutil>=2.8`.
- `forecast` returns the next 3 dates with `relativedelta`.
- `pskit validate` (azure): valid.
- Local `GET /forecast`: 200 with three ISO dates.

Locally the packages must be in your .venv (`pip install -r requirements.txt`). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 584
    B(584, provider="aws", stage="staging", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: legacy-feed
provider:
  name: aws
  region: eu-west-1
functions:
  stock:
    handler: app.feed.stock
    events:
    - http: GET /stock.xml
""",
          "app/__init__.py": "",
          "app/feed.py": FUTURE + """

def stock(event, ctx):
    return {"items": [{"sku": "A1", "qty": 3}]}
""",
          "requirements.txt": ""}),
      user="old partner system only read xml, not json. stock must answer xml like <stock><item sku=.. qty=../></stock>",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Build the XML with xml.etree.ElementTree (escapes values) in app/feed.py",
                                   "Return (xml, 200, {\"content-type\": \"application/xml\"})",
                                   "Validate for aws (staging), invoke GET /stock.xml"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/feed.py", content=FUTURE + """import xml.etree.ElementTree as ET

ITEMS = [{"sku": "A1", "qty": 3}, {"sku": "B7", "qty": 0}]


def stock(event, ctx):
    root = ET.Element("stock")
    for item in ITEMS:
        ET.SubElement(root, "item", sku=item["sku"], qty=str(item["qty"]))
    body = ET.tostring(root, encoding="unicode")
    return body, 200, {"content-type": "application/xml"}
"""),
          S("validate"),
          S("invoke_local", function="stock", method="GET", path="/stock.xml"),
      ],
      final="""Done. `stock` now answers XML:

```xml
<stock><item sku="A1" qty="3" /><item sku="B7" qty="0" /></stock>
```

- Built with `xml.etree.ElementTree`, so special characters are escaped.
- Returned as `(body, 200, {"content-type": "application/xml"})`, the Flask-style tuple [docs/handlers.md#returning-a-response].
- `pskit validate` (aws, staging): valid. Local `GET /stock.xml`: 200, `application/xml`.

Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 585
    B(585, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: pdf-render
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, pdf-render-prod}
functions:
  render:
    handler: app.render.render
    events:
    - queue: render-jobs
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + """

def render(event, ctx):
    return {"rendered": len(event.records)}
""",
          "requirements.txt": ""}),
      user="`render` (Pub/Sub queue render-jobs) sometimes needs 15 minutes for huge PDFs. Set its timeout to 900 and memory to 2048.",
      steps=[
          S("get_project"),
          S("search_docs", query="gcp event function timeout limit",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="**Limits:**")]),
          S("ask_user", question="On GCP, event-triggered functions are limited to 540 s, so 900 won't validate. What do you prefer?",
            options=["timeout 540 for now (split huge PDFs later)", "keep 900 and move render behind an HTTP trigger"],
            answer="timeout 540 for now (split huge PDFs later)"),
          S("propose_plan", steps=["functions.render.timeout = 540, memory = 2048", "Validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.render.timeout", value=540),
          S("set_config", path="functions.render.memory", value=2048),
      ],
      final="""Set as you chose:

```yaml
functions:
  render:
    timeout: 540
    memory: 2048
```

- 540 s is the GCP maximum for event-triggered functions (queue, topic, storage) [docs/providers.md#gcp-google-cloud-functions-2nd-gen]; 900 would fail validation.
- `pskit validate` (gcp, prod): valid after both changes.

For PDFs that need longer, split the work into smaller messages (for example one per page range). Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 586
    B(586, provider="azure", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue", "docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": """service: fulfil
provider:
  name: azure
  region: westeurope
functions:
  pack:
    handler: app.pack.pack
    events:
    - queue: orders-eu
""",
          "app/__init__.py": "",
          "app/pack.py": FUTURE + """

def pack(event, ctx):
    return {"packed": len(event.records)}
""",
          "requirements.txt": ""}),
      user="pack: also consume orders-us, same code. log which queue each msg came from",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["pack.events = [queue orders-eu, queue orders-us]",
                                   "Log record.source per message", "Validate azure (staging), invoke"]),
          S("write_file", path="app/pack.py", content=FUTURE + """

def pack(event, ctx):
    for record in event.records:
        ctx.logger.info("packing", extra={"queue": record.source, "id": record.id})
    return {"packed": len(event.records)}
"""),
          S("set_config", path="functions.pack.events", value=[{"queue": "orders-eu"}, {"queue": "orders-us"}]),
          S("invoke_local", function="pack", type="queue", data=[{"order": 1}, {"order": 2}]),
      ],
      final="""```yaml
functions:
  pack:
    events:
      - queue: orders-eu
      - queue: orders-us
```

- Both Storage Queues are created in the app's storage account; each gets its own trigger on the same handler [docs/events.md#queue].
- `record.source` is the queue identifier [docs/handlers.md#record]; pack logs it with the message id.
- validate (azure, staging): valid. invoke with 2 messages: two `packing` logs, `{"packed": 2}`.

Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 587
    B(587, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: signup-events
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="A new user signup is published to the SNS topic `user-signed-up` (pskit creates it). Two independent functions should receive every message: `crm-sync` adds the user to the CRM, `welcome-gift` sends a gift code. One failing must not block the other.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/signup.py with crm_sync and welcome_gift",
                                   "Add both functions with topic user-signed-up (each gets its own SNS subscription)",
                                   "Validate for aws, invoke both with the same message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/signup.py", content=FUTURE + """

def crm_sync(event, ctx):
    users = [(r.json(default={}) or {}).get("email") for r in event.records]
    # TODO: call the CRM API
    return {"crm": users}


def welcome_gift(event, ctx):
    users = [(r.json(default={}) or {}).get("email") for r in event.records]
    # TODO: create and send a gift code
    return {"gifts": users}
"""),
          S("set_config", path="functions.crm-sync", value={"handler": "app.signup.crm_sync", "events": [{"topic": "user-signed-up"}]}),
          S("set_config", path="functions.welcome-gift", value={"handler": "app.signup.welcome_gift", "events": [{"topic": "user-signed-up"}]}),
          S("invoke_local", function="crm-sync", type="topic", data={"email": "noor@example.com"}),
          S("invoke_local", function="welcome-gift", type="topic", data={"email": "noor@example.com"}),
      ],
      final="""Both functions subscribe to the same topic:

```yaml
functions:
  crm-sync:
    handler: app.signup.crm_sync
    events:
      - topic: user-signed-up
  welcome-gift:
    handler: app.signup.welcome_gift
    events:
      - topic: user-signed-up
```

- On AWS, pskit creates the SNS topic once and one subscription per function [docs/events.md#topic], so SNS delivers every message to each one separately: if `crm-sync` fails, `welcome-gift` still gets it.
- `pskit validate` (aws): valid.
- invoke with the same message: crm-sync → `{"crm": ["noor@example.com"]}`, welcome-gift → `{"gifts": ["noor@example.com"]}`.

Deploy: **Deploy** or `pskit deploy -s dev`; test the real fan-out afterwards with `pskit trigger -f crm-sync -d '{"email": "a@example.com"}'`."""),

    # ------------------------------------------------------------------ 588
    B(588, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: tip-calc
provider:
  name: gcp
  region: us-east1
  runtime: nodejs20
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, tip-calc-dev}
functions: {}
""",
          "package.json": "{\n  \"name\": \"tip-calc\",\n  \"private\": true\n}\n"}),
      user="I know a bit of JavaScript. Can you make a tip calculator I can send the bill amount and percent to, and it tells me the tip? Tell me nicely if I forget the amount.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write src/tip.js: read {amount, percent} from the JSON body, BadRequest if amount is missing, default percent 15",
                                   "Add function `tip` on POST /tip",
                                   "Validate for gcp and try it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/tip.js", content="""const { BadRequest } = require("pskit");

exports.tip = async function (event) {
  const body = event.http.json() || {};
  const amount = Number(body.amount);
  if (!amount) throw new BadRequest("please send the bill amount, for example {\\"amount\\": 40}");
  const percent = Number(body.percent || 15);
  const tip = Math.round(amount * percent) / 100;
  return { amount, percent, tip, total: amount + tip };
};
"""),
          S("set_config", path="functions.tip", value={"handler": "src.tip.tip", "events": [{"http": "POST /tip"}]}),
          S("invoke_local", function="tip", method="POST", path="/tip", data={"amount": 40, "percent": 20}),
          S("invoke_local", function="tip", method="POST", path="/tip", data={"percent": 20}),
      ],
      final="""Here's your tip calculator, in JavaScript:

- `POST /tip` with `{"amount": 40, "percent": 20}` → `{"tip": 8, "total": 48}`. Without `percent` it uses 15 %.
- Forgetting the amount gives a friendly **400**: `please send the bill amount, ...`. `BadRequest` comes from `pskit`, like in Python [docs/nodejs.md#handlers].

Checks: `pskit validate` (gcp) valid; both local tests gave the results above.

Try your own numbers on **Test** > **▶ Run locally**. Put it online with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 589
    B(589, provider="azure", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: storefront
provider:
  name: azure
  region: westeurope
  environment:
    SHOW_BANNER: "true"
    MAX_CART: "20"
functions:
  home:
    handler: app.store.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/store.py": FUTURE + """

def home(event, ctx):
    return {"banner": ctx.env.get("SHOW_BANNER"), "max_cart": ctx.env.get("MAX_CART")}
""",
          "config/flags.yml": "SHOW_BANNER: \"false\"\nMAX_CART: \"25\"\n",
          "requirements.txt": ""}),
      user="product team edit config/flags.yml for the feature flags. i want environment take from that file, not write in pskit.yml",
      steps=[
          S("get_project"),
          S("read_file", path="config/flags.yml"),
          S("search_docs", query="file variable yml",
            docs=[D("docs/configuration.md", "variables", end="When a value is exactly one variable")]),
          S("propose_plan", steps=["provider.environment = ${file(config/flags.yml)} (the whole mapping)",
                                   "Validate for azure, invoke GET / to see the file values"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.environment", value="${file(config/flags.yml)}"),
          S("invoke_local", function="home", method="GET", path="/"),
      ],
      final="""Done. The environment now comes from the product team's file:

```yaml
provider:
  environment: ${file(config/flags.yml)}
```

- `${file(...)}` reads the file relative to pskit.yml and parses `.yml` / `.json` [docs/configuration.md#variables]; because it is the whole value, the mapping is used as is.
- `pskit validate` (azure): valid.
- Local `GET /`: `{"banner": "false", "max_cart": "25"}`, the values from flags.yml.

Keep the values quoted strings in flags.yml. New values reach Azure on the next **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 590
    B(590, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: club-members
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="I export my club member list from Excel as CSV. Can I send that file to my function and have it tell me how many members and how many paid?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/members.py: read the CSV text from the request body with csv.DictReader, count rows and paid=yes",
                                   "Add function `count-members` on POST /members/import",
                                   "Validate for aws, send a small CSV locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/members.py", content=FUTURE + """import csv
import io

from py_serverless_kit import BadRequest


def count_members(event, ctx):
    text = event.http.text()
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise BadRequest("send a CSV file with a header row")
    paid = sum(1 for r in rows if (r.get("paid") or "").strip().lower() in ("yes", "y", "true", "1"))
    return {"members": len(rows), "paid": paid, "unpaid": len(rows) - paid}
"""),
          S("set_config", path="functions.count-members",
            value={"handler": "app.members.count_members", "events": [{"http": "POST /members/import"}]}),
          S("invoke_local", function="count-members", method="POST", path="/members/import",
            data="name,paid\nAna,yes\nBen,no\nCleo,yes\n"),
      ],
      final="""Yes. `count-members` on `POST /members/import` reads the CSV you send and counts:

- members = rows under the header; paid = rows whose `paid` column is yes/y/true/1.
- An empty file gets a 400 asking for a header row.

Checks: `pskit validate` (aws) valid; a 3-member test file → `{"members": 3, "paid": 2, "unpaid": 1}`.

Your CSV needs a header row with a `paid` column (change the name in app/members.py if yours is different). After **Deploy** (or `pskit deploy -s dev`) you can send it with `curl --data-binary @members.csv <your address>/members/import`; `pskit info` shows the address."""),

    # ------------------------------------------------------------------ 591
    B(591, provider="gcp", stage="staging", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: geocode
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, geocode-staging}
functions:
  lookup:
    handler: app.geo.lookup
    events:
    - http: GET /lookup
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + """

def lookup(event, ctx):
    return {"lat": 0, "lon": 0}
""",
          "requirements.txt": ""}),
      user="lookup: 429 + Retry-After: 30 when q missing? no - when caller sends header x-plan: free and already did 5 calls this instance. q required -> 400",
      steps=[
          S("get_project"),
          S("search_docs", query="HttpError status headers", docs=[D("docs/handlers.md", "errors")]),
          S("propose_plan", steps=["Per-instance counter per caller (x-caller header) for x-plan: free; over 5 -> HttpError 429 with Retry-After: 30",
                                   "Missing q -> BadRequest", "Validate gcp (staging), invoke"]),
          S("write_file", path="app/geo.py", content=FUTURE + """from py_serverless_kit import BadRequest, HttpError

FREE_LIMIT = 5
_CALLS = {}  # per instance only


def lookup(event, ctx):
    q = event.http.query.get("q")
    if not q:
        raise BadRequest("q is required")
    if event.http.headers.get("x-plan") == "free":
        caller = event.http.headers.get("x-caller", "anonymous")
        _CALLS[caller] = _CALLS.get(caller, 0) + 1
        if _CALLS[caller] > FREE_LIMIT:
            raise HttpError("free plan limit reached", status=429, headers={"retry-after": "30"})
    return {"q": q, "lat": 0, "lon": 0}
"""),
          S("validate"),
          S("invoke_local", function="lookup", method="GET", path="/lookup"),
          S("invoke_local", function="lookup", method="GET", path="/lookup?q=Berlin"),
      ],
      final="""app/geo.py:
- no `q` → **400** `q is required`;
- `x-plan: free` → counted per `x-caller`; call 6+ → `HttpError(..., status=429, headers={"retry-after": "30"})` [docs/handlers.md#errors].

validate (gcp, staging): valid. invoke: no q → 400; `?q=Berlin` → 200.

The counter is per instance, so it is a soft limit. A strict quota needs shared state (for example Memorystore or Firestore). Each `pskit invoke` starts fresh, so test the 429 against `pskit dev` with six requests sending `x-plan: free`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 592
    B(592, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/nodejs.md#choosing-the-runtime", "docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": """service: hello-js
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="I'm new and I prefer JavaScript. In this empty project, can you make a hello page in JS that says hello to the name in the address, like ?name=Kai?",
      steps=[
          S("get_project"),
          S("search_docs", query="nodejs runtime", docs=[D("docs/nodejs.md", "choosing-the-runtime", end="runs for you.")]),
          S("propose_plan", steps=["Set provider.runtime to nodejs20 (one language per service)",
                                   "Write src/hello.js and package.json; add function hello on GET /hello",
                                   "Validate for azure, open /hello?name=Kai locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value="nodejs20"),
          S("write_file", path="package.json", content="{\n  \"name\": \"hello-js\",\n  \"private\": true\n}\n"),
          S("write_file", path="src/hello.js", content="""exports.hello = async function (event) {
  const name = event.http.query.name || "world";
  return { message: `Hello, ${name}!` };
};
"""),
          S("set_config", path="functions.hello", value={"handler": "src.hello.hello", "events": [{"http": "GET /hello"}]}),
          S("invoke_local", function="hello", method="GET", path="/hello?name=Kai"),
      ],
      final="""Done, all in JavaScript:

- `provider.runtime: nodejs20`: a service is either Python or Node.js, so the whole project now uses Node.js [docs/nodejs.md#choosing-the-runtime].
- `src/hello.js` exports `hello`; it reads `?name=` and answers `Hello, <name>!`.
- `requirements.txt` is no longer needed; you can delete it.

Checks: `pskit validate` (azure) valid; `/hello?name=Kai` → 200 `{"message": "Hello, Kai!"}`.

Try it on **Test** > **▶ Run locally**, or run `pskit dev` and open `http://127.0.0.1:3000/hello?name=Kai`. Put it online with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 593
    B(593, provider="aws", stage="staging", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: region-info
provider:
  name: aws
  region: eu-west-1
functions:
  where:
    handler: app.where.where
    events:
    - http: GET /where
""",
          "app/__init__.py": "",
          "app/where.py": FUTURE + """import os


def where(event, ctx):
    return {"region": os.environ["AWS_REGION"], "fn": os.environ["AWS_LAMBDA_FUNCTION_NAME"]}
""",
          "requirements.txt": ""}),
      user="This handler came straight from Lambda and reads AWS_REGION and AWS_LAMBDA_FUNCTION_NAME from os.environ. It crashes locally. Make it portable so it also works when we move clouds.",
      steps=[
          S("get_project"),
          S("search_docs", query="context region function name", docs=[D("docs/handlers.md", "context")]),
          S("propose_plan", steps=["Use ctx.region, ctx.function and ctx.stage instead of the AWS-only variables",
                                   "Validate for aws (staging), invoke GET /where"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/where.py", content=FUTURE + """

def where(event, ctx):
    return {"region": ctx.region, "function": ctx.function, "stage": ctx.stage}
"""),
          S("validate"),
          S("invoke_local", function="where", method="GET", path="/where"),
      ],
      final="""Fixed. The handler now uses the pskit `Context` instead of Lambda's environment variables [docs/handlers.md#context]:

| Lambda | pskit |
|---|---|
| `os.environ["AWS_REGION"]` | `ctx.region` |
| `os.environ["AWS_LAMBDA_FUNCTION_NAME"]` | `ctx.function` (the logical name) |

- `pskit validate` (aws, staging): valid.
- Local `GET /where`: `{"region": "local", "function": "where", "stage": "staging"}`. Locally the region is `local`; in Lambda it's eu-west-1.

The same code works on GCP or Azure. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 594
    B(594, provider="gcp", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#what-handlers-receive", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, orders-dev}
functions:
  api:
    handler: app.api.create
    environment:
      TOPIC: order-events
    events:
    - http: POST /orders
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def create(event, ctx):
    return {"topic": ctx.env.get("TOPIC")}, 201
""",
          "requirements.txt": ""}),
      user="""google.api_core.exceptions.NotFound: 404 Resource not found (resource=order-events).
    at publisher.publish(topic_path, data) in app/api.py

the topic doesn't exist. let pskit create it and give api the real topic, not a hardcoded name""",
      steps=[
          S("get_project"),
          S("search_docs", query="managed topic resource handler binding",
            docs=[D("docs/resources.md", "what-handlers-receive", start="| Provider | Values added |", end="| gcp |")]),
          S("propose_plan", steps=["resources.order-events {type: topic, functions: [api]} (pskit creates the Pub/Sub topic)",
                                   "Remove the hardcoded TOPIC variable; the handler reads resource(\"order-events\") (id / native_name)",
                                   "Validate for gcp, invoke POST /orders"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.order-events", value={"type": "topic", "functions": ["api"]}),
          S("write_file", path="app/api.py", content=FUTURE + """from py_serverless_kit import resource


def create(event, ctx):
    topic = resource("order-events")
    # publish with google-cloud-pubsub: publisher.publish(topic.id or topic.native_name, data)
    return {"topic": topic.native_name, "topic_id": topic.id}, 201
"""),
          S("set_config", path="functions.api.environment", value=None),
          S("invoke_local", function="api", method="POST", path="/orders", data={"sku": "A1"}),
      ],
      final="""The topic was never created: `TOPIC: order-events` was only a name. Now pskit manages it:

```yaml
resources:
  order-events:
    type: topic
    functions: [api]
```

- pskit creates the Pub/Sub topic, and `api` gets its binding. On GCP managed topics also get `ID` (the Pub/Sub topic id) [docs/resources.md#what-handlers-receive], read with `resource("order-events").id` [docs/resources.md#runtime-api].
- The hardcoded `TOPIC` variable is removed.
- `pskit validate` (gcp): valid. Local POST: 201 with `topic: order-events` (locally names are unprefixed and there is no id; in the cloud you get the real ones).

Publish to `topic.id` in your Pub/Sub code. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 595
    B(595, provider="azure", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: admin-tools
provider:
  name: azure
  region: westeurope
functions:
  health:
    handler: app.admin.health
    events:
    - http: GET /health
  purge-cache:
    handler: app.admin.purge
    events:
    - http: POST /admin/purge
""",
          "app/__init__.py": "",
          "app/admin.py": FUTURE + """

def health(event, ctx):
    return {"ok": True}


def purge(event, ctx):
    return {"purged": True}
""",
          "requirements.txt": ""}),
      user="purge-cache: function key auth. health stays public",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["purge-cache event -> {path: /admin/purge, method: POST, auth: key}; health unchanged", "Validate azure prod"]),
          S("set_config", path="functions.purge-cache.events.0",
            value={"http": {"path": "/admin/purge", "method": "POST", "auth": "key"}}),
          S("invoke_local", function="purge-cache", method="POST", path="/admin/purge"),
      ],
      final="""```yaml
functions:
  purge-cache:
    events:
      - http: {path: /admin/purge, method: POST, auth: key}
```

- On Azure `auth: key` = a function key (`AuthLevel.FUNCTION`), so callers must send the key [docs/events.md#http]. `health` stays `auth: none`.
- validate (azure, prod): valid. invoke: 200 `{"purged": true}` (keys aren't checked locally).

Deploy: `pskit deploy -s prod` (typed confirmation in studio); find the key in the Azure portal (Function App > App keys)."""),

    # ------------------------------------------------------------------ 596
    B(596, provider="aws", stage="dev", mode="auto", page="Code", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: docs-js
provider:
  name: aws
  region: eu-west-1
  runtime: nodejs20
functions:
  ping:
    handler: src.http.ping
    events:
    - http: GET /ping
""",
          "src/http.js": """exports.ping = async function () {
  return { ok: true };
};
""",
          "package.json": "{\n  \"name\": \"docs-js\",\n  \"private\": true\n}\n"}),
      user="js. new fn when file upload in s3 bucket docs-js-inbox-3390 (pskit make it), only under incoming/ . log name and size",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write src/inbox.js: export onUpload, log record.key and record.size",
                                   "functions.on-upload: storage {bucket: docs-js-inbox-3390, prefix: incoming/, events: [created]}",
                                   "Validate aws, invoke a storage event"]),
          S("write_file", path="src/inbox.js", content="""exports.onUpload = async function (event, ctx) {
  const files = event.records.map((r) => ({ key: r.key, size: r.size }));
  for (const f of files) ctx.logger.info("uploaded", f);
  return { files };
};
"""),
          S("set_config", path="functions.on-upload",
            value={"handler": "src.inbox.onUpload",
                   "events": [{"storage": {"bucket": "docs-js-inbox-3390", "prefix": "incoming/", "events": ["created"]}}]}),
          S("invoke_local", function="on-upload", type="storage",
            data={"bucket": "docs-js-inbox-3390", "key": "incoming/report.pdf", "size": 48213}),
      ],
      final="""```yaml
functions:
  on-upload:
    handler: src.inbox.onUpload
    events:
      - storage: {bucket: docs-js-inbox-3390, prefix: incoming/, events: [created]}
```

- pskit creates the S3 bucket (public access blocked) and the notification for `incoming/` [docs/events.md#storage]. `src/inbox.js` logs `key` and `size` of each record.
- validate (aws): valid.
- invoke with `incoming/report.pdf`: one `uploaded` log, size 48213.

Deploy: `pskit deploy -s dev`; then `pskit trigger -f on-upload -d '{"key": "incoming/a.txt", "content": "x"}'` uploads a real test file."""),

    # ------------------------------------------------------------------ 597
    B(597, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response", "docs/configuration.md#variables"],
      project=dict(files={
          "pskit.yml": """service: fx-proxy
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, fx-proxy-dev}
functions:
  rate:
    handler: app.fx.rate
    environment:
      FX_API_URL: ${env:FX_API_URL, https://fx.example.com/latest}
    events:
    - http: GET /rate/{pair}
""",
          "app/__init__.py": "",
          "app/fx.py": FUTURE + """

def rate(event, ctx):
    return {"pair": event.http.path_params["pair"]}
""",
          "requirements.txt": ""}),
      user="`rate` should call FX_API_URL?pair=<pair> with `requests`, 3 second timeout. If the upstream times out or errors, answer 502 with {\"error\": \"upstream unavailable\"} instead of crashing.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add requests to requirements.txt",
                                   "FX_API_URL default -> not-set, so nothing is called until the real URL is set",
                                   "app/fx.py: requests.get(url, params={pair}, timeout=3); on requests.RequestException or no URL return ({error}, 502)",
                                   "Validate for gcp; invoke locally (no URL set, so expect the 502 path without a network call)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="requirements.txt", content="requests>=2.31\n"),
          S("set_config", path="functions.rate.environment.FX_API_URL", value="${env:FX_API_URL, not-set}"),
          S("write_file", path="app/fx.py", content=FUTURE + """import requests

UNAVAILABLE = ({"error": "upstream unavailable"}, 502)


def rate(event, ctx):
    pair = event.http.path_params["pair"]
    url = ctx.env.get("FX_API_URL", "not-set")
    if not url.startswith("https://"):
        ctx.logger.warning("FX_API_URL is not set", extra={"pair": pair})
        return UNAVAILABLE
    try:
        resp = requests.get(url, params={"pair": pair}, timeout=3)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        ctx.logger.warning("upstream failed", extra={"pair": pair, "error": type(exc).__name__})
        return UNAVAILABLE
"""),
          S("validate"),
          S("invoke_local", function="rate", method="GET", path="/rate/EURUSD"),
      ],
      final="""`rate` now proxies the FX API:

- `requests.get(FX_API_URL, params={"pair": ...}, timeout=3)`; any `requests.RequestException` (timeout, connection error, HTTP error) or a non-JSON answer → `({"error": "upstream unavailable"}, 502)` plus a warning log [docs/handlers.md#returning-a-response].
- `FX_API_URL` now defaults to `not-set` (`${env:FX_API_URL, not-set}` [docs/configuration.md#variables]); while no https URL is set, the handler answers the same 502 without calling anything.
- `requests>=2.31` is in requirements.txt (GCP installs it with the remote build).
- `pskit validate` (gcp): valid.
- Local `GET /rate/EURUSD`: **502** `upstream unavailable` with the "FX_API_URL is not set" warning, so the error path works and no request left your machine.

Set `FX_API_URL` to the real https address (Setup & credentials > Environment variables, or your shell) and test again on the **Test** page or with `pskit invoke -f rate --method GET --path /rate/EURUSD`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 598
    B(598, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/events.md#http", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: feedback-box
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="new project: my website https://www.example.com needs a little feedback box that sends a message to my function. Every friday I want a summary. Is that hard?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/feedback.py: send (POST /feedback, message required) and weekly_summary",
                                   "send: CORS for https://www.example.com so the browser may call it",
                                   "weekly-summary: schedule \"0 16 * * 5\" (Fridays 16:00 UTC)",
                                   "Validate for azure, try both locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/feedback.py", content=FUTURE + """from py_serverless_kit import BadRequest


def send(event, ctx):
    message = ((event.http.json(default={}) or {}).get("message") or "").strip()
    if not message:
        raise BadRequest("message is empty")
    ctx.logger.info("feedback", extra={"length": len(message)})
    # TODO: save the message
    return {"thanks": True}, 201


def weekly_summary(event, ctx):
    # TODO: read this week's messages and email yourself a summary
    return {"messages": 0}
"""),
          S("set_config", path="functions.send",
            value={"handler": "app.feedback.send",
                   "events": [{"http": {"path": "/feedback", "method": "POST", "cors": {"origins": ["https://www.example.com"]}}}]}),
          S("set_config", path="functions.weekly-summary",
            value={"handler": "app.feedback.weekly_summary", "events": [{"schedule": "0 16 * * 5"}]}),
          S("invoke_local", function="send", method="POST", path="/feedback", data={"message": "Love the new page!"}),
          S("invoke_local", function="weekly-summary", type="schedule"),
      ],
      final="""Not hard. Your project now has two functions:

- `send`: `POST /feedback` with `{"message": ...}` → **201**; an empty message gets a 400. CORS allows only `https://www.example.com`, so your site's browser code may call it [docs/events.md#http].
- `weekly-summary`: every Friday at 16:00 UTC (Azure timers use UTC [docs/events.md#schedule]).

Checks: `pskit validate` (azure) valid; send → 201 `{"thanks": true}`; weekly-summary → `{"messages": 0}`.

Saving the messages and the summary email are TODOs in app/feedback.py. Deploy with **Deploy** or `pskit deploy -s dev`; `pskit info` shows the address to use in your website's `fetch()` call."""),

    # ------------------------------------------------------------------ 599
    B(599, provider="aws", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: media-tools
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.tools.api
    events:
    - http: GET /tools
  encode:
    handler: app.tools.encode
    events:
    - queue: encode-jobs
""",
          "app/__init__.py": "",
          "app/tools.py": FUTURE + """

def api(event, ctx):
    return {"ok": True}


def encode(event, ctx):
    return {"encoded": len(event.records)}
""",
          "requirements.txt": ""}),
      user="only encode on arm64 + 3008 MB. api stays default",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.encode.architecture = arm64, memory = 3008", "Validate aws staging"]),
          S("set_config", path="functions.encode.architecture", value="arm64"),
          S("set_config", path="functions.encode.memory", value=3008),
      ],
      final="""```yaml
functions:
  encode:
    architecture: arm64
    memory: 3008
```

Function-level `architecture` and `memory` override the provider defaults for `encode` only [docs/configuration.md#functions]; `api` keeps the provider defaults. validate (aws, staging): valid after both.

Dependencies are packaged per architecture, so check that encode's native packages have arm64 wheels. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 600
    B(600, provider="gcp", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=dict(files={
          "pskit.yml": """service: year-end
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, year-end-prod}
functions:
  build-report:
    handler: app.report.build
    events:
    - http: POST /reports
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """

def build(event, ctx):
    return {"report": "queued"}
""",
          "requirements.txt": ""}),
      user="build-report is http and it take 20 min sometimes, it get cut at 30 sec. give it 25 minute",
      steps=[
          S("get_project"),
          S("search_docs", query="gcp timeout limits http",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="**Limits:**")]),
          S("propose_plan", steps=["functions.build-report.timeout = 1500 (the 540 s limit is only for event-triggered functions)",
                                   "Validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.build-report.timeout", value=1500),
      ],
      final="""Done: `build-report` now has `timeout: 1500` (25 minutes). The default was 30 s, which is why it was cut.

- The 540 s limit on GCP is for event-triggered functions only [docs/providers.md#gcp-google-cloud-functions-2nd-gen]; `build-report` is HTTP, so 1500 validates.
- `pskit validate` (gcp, prod): valid.

The caller (browser, curl) must also wait that long without giving up. If it can't, return 202 right away and do the work from a queue. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),
]
