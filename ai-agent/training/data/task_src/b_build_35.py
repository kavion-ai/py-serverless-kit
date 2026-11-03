"""Category B (build / add), batch 35 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 681
    B(681, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#errors", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: bakery-site
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="my contact form gets so much spam from robots. i want a function for the form that stops most of it",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/contact.py: POST /contact with name, email, message",
                                   "Honeypot: a hidden field `website` that people leave empty; robots fill it -> answer ok but drop it",
                                   "More than 2 links in the message -> 422; missing fields -> 400",
                                   "Validate for aws, try a normal message and a robot message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/contact.py", content=FUTURE + """from py_serverless_kit import BadRequest, UnprocessableEntity


def contact(event, ctx):
    body = event.http.json(default={}) or {}
    if body.get("website"):
        # honeypot filled: almost certainly a robot. Pretend success, keep nothing.
        ctx.logger.info("spam dropped", extra={"reason": "honeypot"})
        return {"ok": True}
    missing = [f for f in ("name", "email", "message") if not str(body.get(f, "")).strip()]
    if missing:
        raise BadRequest("please fill in: " + ", ".join(missing))
    message = str(body["message"])
    if message.count("http://") + message.count("https://") > 2:
        raise UnprocessableEntity("too many links in the message")
    ctx.logger.info("contact message", extra={"length": len(message)})
    # TODO: send it to your mailbox
    return {"ok": True}
"""),
          S("set_config", path="functions.contact", value={"handler": "app.contact.contact", "events": [{"http": "POST /contact"}]}),
          S("invoke_local", function="contact", method="POST", path="/contact",
            data={"name": "Jo", "email": "jo@example.com", "message": "Do you bake gluten-free bread?", "website": ""}),
          S("invoke_local", function="contact", method="POST", path="/contact",
            data={"name": "x", "email": "x@example.com", "message": "cheap pills", "website": "https://spam.example.com"}),
      ],
      final="""Your form now has a spam filter, `POST /contact`:

1. **Honeypot**: add a hidden field `website` to the form (hide it with CSS). People never fill it, robots usually do. Those messages get a normal "ok" but are thrown away, so the robot doesn't learn anything.
2. More than 2 links in the message → 422.
3. Empty name, email or message → 400 with what's missing [docs/handlers.md#errors].

Checks: `pskit validate` (aws) valid; a normal question → `{"ok": true}` and logged; the robot message → `{"ok": true}` with `spam dropped` in the log.

Sending the message on to your mailbox is the next step (a TODO in app/contact.py). Try it on **Test** > **▶ Run locally**; publish with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 682
    B(682, provider="gcp", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: clickstream
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, clickstream-dev}
functions:
  collect:
    handler: app.clicks.collect
    events:
    - queue: click-events
""",
          "app/__init__.py": "",
          "app/clicks.py": FUTURE + """

def collect(event, ctx):
    return {"n": len(event.records)}
""",
          "requirements.txt": ""}),
      user="collect: batch_size 50, batch_window 10",
      steps=[
          S("get_project"),
          S("search_docs", query="queue batch_size gcp pubsub", docs=[D("docs/events.md", "queue", start="| Option |", end="| `fifo` |")]),
          S("ask_user", say="On GCP a queue is a Pub/Sub push subscription: `batch_size` and `batch_window` are ignored there (one message per delivery).",
            question="Set them anyway (they take effect if this service also deploys to AWS), or leave the config as it is?",
            options=["Set them anyway", "Leave it"], answer="set them, we deploy to aws too later"),
          S("propose_plan", steps=["functions.collect.events.0: queue {name: click-events, batch_size: 50, batch_window: 10}",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.collect.events.0",
            value={"queue": {"name": "click-events", "batch_size": 50, "batch_window": 10}}),
      ],
      final="""```yaml
functions:
  collect:
    handler: app.clicks.collect
    events:
      - queue: {name: click-events, batch_size: 50, batch_window: 10}
```

- On GCP both options are ignored; each Pub/Sub delivery brings one message [docs/events.md#queue]. On AWS they become the SQS event source mapping's batch size and window.
- `pskit validate` (gcp): valid.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 683
    B(683, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: search-admin
provider:
  name: azure
  region: westeurope
functions:
  search:
    handler: app.search.search
    events:
    - http: GET /search
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """

def search(event, ctx):
    return {"hits": []}
""",
          "requirements.txt": ""}),
      user="Add `reindex`: runs every night at 01:30 UTC, and admins can also start it with POST /admin/reindex, which must need the function key (not public). Response/result: {\"reindexed\": true, \"trigger\": <event type>}.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/search.py: reindex() returns reindexed + event.type",
                                   "functions.reindex: schedule \"30 1 * * *\" and http {POST /admin/reindex, auth: key}",
                                   "Validate for azure, invoke both triggers"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/search.py", content=FUTURE + """

def search(event, ctx):
    return {"hits": []}


def reindex(event, ctx):
    ctx.logger.info("reindex started", extra={"trigger": event.type})
    return {"reindexed": True, "trigger": event.type}
"""),
          S("set_config", path="functions.reindex",
            value={"handler": "app.search.reindex",
                   "events": [{"schedule": "30 1 * * *"},
                              {"http": {"path": "/admin/reindex", "method": "POST", "auth": "key"}}]}),
          S("invoke_local", function="reindex", type="schedule"),
          S("invoke_local", function="reindex", type="http", method="POST", path="/admin/reindex"),
      ],
      final="""```yaml
functions:
  reindex:
    handler: app.search.reindex
    events:
      - schedule: "30 1 * * *"
      - http: {path: /admin/reindex, method: POST, auth: key}
```

- `auth: key` = Azure function key on that route [docs/events.md#http]; `search` stays public. Timers run in UTC on Azure [docs/events.md#schedule].
- `pskit validate` (azure): valid.
- Schedule run → `{"reindexed": true, "trigger": "schedule"}`; POST → `{"reindexed": true, "trigger": "http"}`. Local runs don't check the key.

After **Deploy** (`pskit deploy -s dev`) admins call it with the function key from the Azure portal."""),

    # ------------------------------------------------------------------ 684
    B(684, provider="aws", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: partner-api
provider:
  name: aws
  region: eu-west-1
functions:
  orders:
    handler: app.partner.orders
    events:
    - http:
        path: /partner/orders
        method: GET
        auth: jwt
        authorizer:
          issuer: https://login.example.com/
          audience: [partner-api]
""",
          "app/__init__.py": "",
          "app/partner.py": FUTURE + """

def orders(event, ctx):
    return {"orders": []}
""",
          "requirements.txt": ""}),
      user="Our old API Gateway JWT authorizer read the token from the X-Auth-Token header (IdentitySource $request.header.X-Auth-Token), and partner clients still send it there. Right now everything gets 401. Keep the issuer and audience.",
      steps=[
          S("get_project"),
          S("search_docs", query="jwt authorizer identity_source", docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("propose_plan", steps=["orders authorizer: add identity_source $request.header.X-Auth-Token (default is Authorization)",
                                   "Validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.orders.events.0.http.authorizer.identity_source", value="$request.header.X-Auth-Token"),
      ],
      final="""Cause: pskit's JWT authorizer reads `Authorization` unless told otherwise, and your partners send `X-Auth-Token`.

```yaml
functions:
  orders:
    events:
      - http:
          path: /partner/orders
          method: GET
          auth: jwt
          authorizer:
            issuer: https://login.example.com/
            audience: [partner-api]
            identity_source: $request.header.X-Auth-Token
```

- `identity_source` is an optional authorizer field for `auth: jwt` on AWS [docs/events.md#http]; issuer and audience are unchanged.
- `pskit validate` (aws, staging): valid.

The change counts on the next **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 685
    B(685, provider="gcp", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: analytics
provider:
  name: gcp
  region: europe-west1
  runtime: python3.12
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, analytics-dev-4}
functions:
  api:
    handler: app.api.handler
    events:
    - http: GET /stats
  crunch:
    handler: app.crunch.run
    events:
    - schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def handler(event, ctx):
    return {"stats": {}}
""",
          "app/crunch.py": FUTURE + """

def run(event, ctx):
    return {"crunched": 0}
""",
          "requirements.txt": ""}),
      user="crunch only -> python3.11 (numba wheel). api stays 3.12",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.crunch.runtime: python3.11", "Validate gcp, invoke crunch"]),
          S("set_config", path="functions.crunch.runtime", value="python3.11"),
          S("invoke_local", function="crunch", type="schedule"),
      ],
      final="""```yaml
functions:
  crunch:
    handler: app.crunch.run
    runtime: python3.11
```

- Function `runtime` overrides `provider.runtime` [docs/configuration.md#functions]; `api` keeps python3.12.
- `pskit validate` (gcp): valid; crunch run → `{"crunched": 0}` (locally it runs on your venv's Python, not 3.11).

Both functions share one requirements.txt, so numba must also install on 3.12 for `api`'s build, or move crunch to its own service. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 686
    B(686, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#providers"],
      project=dict(files={
          "pskit.yml": """service: archive-job
provider:
  name: azure
  region: westeurope
functions:
  archive:
    handler: app.archive.run
    timeout: 300
    events:
    - schedule: "0 4 * * *"
""",
          "app/__init__.py": "",
          "app/archive.py": FUTURE + """

def run(event, ctx):
    return {"archived": 0}
""",
          "requirements.txt": ""}),
      user="archive job need 15 minute sometimes, set timeout 900",
      steps=[
          S("get_project"),
          S("search_docs", query="azure functions max timeout", docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| 600 s |")]),
          S("ask_user", say="Azure Functions on the Consumption plan allow at most 600 s, so 900 would fail validation.",
            question="What should I do?",
            options=["Set 600 s (the maximum)", "Leave it at 300 and you split the job"],
            answer="600 then, I'll split later"),
          S("propose_plan", steps=["functions.archive.timeout: 600", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.archive.timeout", value=600),
      ],
      final="""Set to the Azure maximum:

```yaml
functions:
  archive:
    handler: app.archive.run
    timeout: 600
```

- Azure Functions allow up to 600 s [docs/providers.md#providers]; 900 can't work there.
- `pskit validate` (azure): valid.

For the 15-minute runs, splitting is the safe way: e.g. the timer puts one message per chunk on a queue and a queue function archives each chunk. Ask me when you want that. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 687
    B(687, provider="aws", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": """service: pdf-render
provider:
  name: aws
  region: eu-west-1
functions:
  render:
    handler: app.render.render
    events:
    - http: POST /render
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + """

def render(event, ctx):
    return {"pages": 1}
""",
          "requirements.txt": "pytest>=8\nruff>=0.6\nblack>=24\n",
          "requirements/prod.txt": "fpdf2>=2.7\n"}),
      user="Our requirements.txt is the developer file (pytest, ruff, black). The function only needs requirements/prod.txt. Make the bundle install only that file, so pytest doesn't end up in the Lambda zip.",
      steps=[
          S("get_project"),
          S("search_docs", query="package requirements file", docs=[D("docs/configuration.md", "package", end="| `vendor` |")]),
          S("propose_plan", steps=["package.requirements: requirements/prod.txt", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="package", value={"requirements": "requirements/prod.txt"}),
      ],
      final="""```yaml
package:
  requirements: requirements/prod.txt
```

- `package.requirements` names the file pskit installs into the bundle (default `requirements.txt`) [docs/configuration.md#package]. On AWS its packages are pip-installed into the zip as Linux wheels, so only `fpdf2` goes in now.
- `pskit validate` (aws): valid.

Check the result before deploying with **Deploy > Package** or `pskit package -s dev`, then deploy with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 688
    B(688, provider="gcp", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: pricing
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, pricing-dev-2}
functions: {}
""",
          "requirements.txt": ""}),
      user="""GET /quote?qty=<n> for our widget (unit price 19.99 EUR, 7% off from 10 pieces, VAT 19%). Money must be calculated with Decimal (no float rounding errors), rounded half-up to cents. Return {qty, net, vat, gross, valid_until} where valid_until is a date 14 days from today. qty missing or < 1 -> 400.""",
      steps=[
          S("get_project"),
          S("search_docs", query="json serialisation decimal date", docs=[D("docs/handlers.md", "returning-a-response", start="JSON serialisation", end="`to_dict()`.")]),
          S("propose_plan", steps=["Write app/quote.py with Decimal math (ROUND_HALF_UP) and a date for valid_until",
                                   "Return the Decimals and the date as they are (pskit serialises them)",
                                   "Add function quote on GET /quote; validate for gcp, invoke qty=12"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/quote.py", content=FUTURE + """from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from py_serverless_kit import BadRequest

UNIT = Decimal("19.99")
DISCOUNT = Decimal("0.07")
VAT = Decimal("0.19")
CENT = Decimal("0.01")


def quote(event, ctx):
    try:
        qty = int(event.http.query.get("qty", ""))
    except ValueError:
        raise BadRequest("qty must be a whole number")
    if qty < 1:
        raise BadRequest("qty must be at least 1")
    net = UNIT * qty
    if qty >= 10:
        net = net * (1 - DISCOUNT)
    net = net.quantize(CENT, rounding=ROUND_HALF_UP)
    vat = (net * VAT).quantize(CENT, rounding=ROUND_HALF_UP)
    return {"qty": qty, "net": net, "vat": vat, "gross": net + vat,
            "valid_until": date.today() + timedelta(days=14)}
"""),
          S("set_config", path="functions.quote", value={"handler": "app.quote.quote", "events": [{"http": "GET /quote"}]}),
          S("invoke_local", function="quote", method="GET", path="/quote?qty=12"),
      ],
      final="""`GET /quote` is added:

- All money is `Decimal`, rounded half-up to cents; 7% off from 10 pieces, then 19% VAT on the rounded net.
- pskit's JSON encoder handles `Decimal` and `date` (ISO 8601) [docs/handlers.md#returning-a-response], so the handler returns them directly.
- Missing, non-numeric or < 1 `qty` → 400.

Checks: `pskit validate` (gcp) valid; `?qty=12` → `{"qty": 12, "net": 223.09, "vat": 42.39, "gross": 265.48, "valid_until": "2026-11-15"}`. The Decimals are sent as JSON numbers with their exact digits; if a client parses them as floats, it should round for display only.

Test other quantities on **Test** or `pskit invoke -f quote --method GET --path "/quote?qty=3"`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 689
    B(689, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: photo-of-the-day
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="I have 5 nice photos online. I want one web address that always shows today's photo, a different one each day, going round in a circle",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/photo.py with your 5 photo addresses (placeholders for now)",
                                   "Pick one by the day number, so it changes daily and cycles through the 5",
                                   "GET /photo redirects the browser to today's photo",
                                   "Validate for azure, try it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/photo.py", content=FUTURE + """from datetime import datetime, timezone

from py_serverless_kit import Response

PHOTOS = [
    "https://photos.example.com/lake.jpg",
    "https://photos.example.com/forest.jpg",
    "https://photos.example.com/beach.jpg",
    "https://photos.example.com/city.jpg",
    "https://photos.example.com/mountain.jpg",
]


def photo(event, ctx):
    day = datetime.now(timezone.utc).date().toordinal()
    return Response.redirect(PHOTOS[day % len(PHOTOS)], status=302)
"""),
          S("set_config", path="functions.photo", value={"handler": "app.photo.photo", "events": [{"http": "GET /photo"}]}),
          S("invoke_local", function="photo", method="GET", path="/photo"),
      ],
      final="""Done! **GET /photo** sends the browser to today's photo:

- Your 5 photos are in a list in `app/photo.py`; replace the `photos.example.com` addresses with yours.
- Each day (UTC) it moves to the next photo, and after the 5th it starts again.
- It answers with a redirect [docs/handlers.md#returning-a-response], so you can use the address directly in a page: `<img src="https://<your-function-address>/photo">`.

Checks: `pskit validate` (azure) valid; today it answered 302 to `forest.jpg`.

Try it on **Test** > **▶ Run locally**; put it online with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 690
    B(690, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/handlers.md#batchresult", "docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: crm
provider:
  name: aws
  region: eu-west-1
functions:
  signup:
    handler: app.crm.signup
    events:
    - http: POST /signup
""",
          "app/__init__.py": "",
          "app/crm.py": FUTURE + """

def signup(event, ctx):
    return {"queued": True}, 202
""",
          "requirements.txt": ""}),
      user="consumer fn welcome on sqs `signups`, log email",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/crm.py: welcome() logs each email",
                                   "functions.welcome: queue signups",
                                   "Validate aws, invoke"],
            result={"decision": "approved", "note": "batch 5, and messages with an invalid email must be reported as failed with BatchResult"}),
          S("write_file", say="Adding batch 5 and BatchResult for invalid emails, as noted.", path="app/crm.py", content=FUTURE + """from py_serverless_kit import BatchResult


def signup(event, ctx):
    return {"queued": True}, 202


def welcome(event, ctx):
    result = BatchResult()
    for record in event.records:
        email = str((record.json(default={}) or {}).get("email", ""))
        if "@" not in email:
            ctx.logger.warning("invalid email", extra={"id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("welcome", extra={"email": email})
    return result
"""),
          S("set_config", path="functions.welcome",
            value={"handler": "app.crm.welcome", "events": [{"queue": {"name": "signups", "batch_size": 5}}]}),
          S("invoke_local", function="welcome", type="queue", data=[{"email": "kim@example.com"}, {"email": "nope"}]),
      ],
      final="""```yaml
functions:
  welcome:
    handler: app.crm.welcome
    events:
      - queue: {name: signups, batch_size: 5}
```

- Per your note: batch 5, and invalid emails go into a `BatchResult`, so on SQS only those messages are retried [docs/handlers.md#batchresult] [docs/events.md#queue].
- `pskit validate` (aws): valid.
- Test with one good, one bad: `welcome` log for kim@example.com, `batchItemFailures` with the bad message's id.

Invalid emails will never succeed, so add a `dead_letter` queue or they retry until the retention ends. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 691
    B(691, provider="gcp", stage="staging", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: marketplace
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, marketplace-stg}
functions:
  search:
    handler: app.search.search
    events:
    - http: GET /v1/search
  listing:
    handler: app.listings.get
    events:
    - http: GET /v1/listings/{id}
  sellers:
    handler: app.sellers.list_sellers
    events:
    - http: GET /v1/sellers
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """

def search(event, ctx):
    q = event.http.query.get("q", "")
    return {"q": q, "results": []}
""",
          "app/listings.py": FUTURE + """

def get(event, ctx):
    return {"id": event.http.path_params["id"]}
""",
          "app/sellers.py": FUTURE + """

def list_sellers(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="Search filters got too long for query strings. Change `search` from GET /v1/search?q=... to POST /v1/search with a JSON body {q, filters}. `filters` is optional and defaults to {}. Other routes stay as they are.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.search.events.0: http POST /v1/search",
                                   "app/search.py: read q and filters from event.http.json()",
                                   "Validate gcp staging, invoke POST with filters"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.search.events.0", value={"http": "POST /v1/search"}),
          S("write_file", path="app/search.py", content=FUTURE + """from py_serverless_kit import BadRequest


def search(event, ctx):
    body = event.http.json(default={}) or {}
    q = body.get("q", "")
    filters = body.get("filters") or {}
    if not isinstance(filters, dict):
        raise BadRequest("filters must be an object")
    return {"q": q, "filters": filters, "results": []}
"""),
          S("validate"),
          S("invoke_local", function="search", method="POST", path="/v1/search",
            data={"q": "bike", "filters": {"price_max": 300, "condition": ["used", "like-new"]}}),
      ],
      final="""`search` is now `POST /v1/search`:

```yaml
functions:
  search:
    handler: app.search.search
    events:
      - http: POST /v1/search
```

- The handler reads `{q, filters}` with `event.http.json()` [docs/handlers.md#httprequest]; `filters` defaults to `{}`, a non-object → 400.
- A GET on /v1/search now gets 405 from the runtime [docs/events.md#http]. `listing` and `sellers` are unchanged.
- `pskit validate` (gcp, staging): valid; POST with q "bike" and two filters → 200 echoing both.

Tell the frontend team before you **Deploy** (`pskit deploy -s staging`): GET callers break at that moment."""),

    # ------------------------------------------------------------------ 692
    B(692, provider="azure", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: claims-portal
provider:
  name: azure
  region: westeurope
functions:
  portal:
    handler: app.portal.home
    events:
    - http: GET /
""",
          "app/__init__.py": "",
          "app/portal.py": FUTURE + """

def home(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="Dev and staging may keep the resource groups pskit creates. Prod must go into the existing resource group `rg-claims-prod`, which the cloud team manages; pskit must not create a resource group in prod.",
      steps=[
          S("get_project"),
          S("search_docs", query="azure resource_group existing option", docs=[D("docs/providers.md", "azure-azure-functions", words=190)]),
          S("propose_plan", steps=["stages.prod.provider.options.resource_group: rg-claims-prod",
                                   "Validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"prod": {"provider": {"options": {"resource_group": "rg-claims-prod"}}}}),
      ],
      final="""```yaml
stages:
  prod:
    provider:
      options:
        resource_group: rg-claims-prod
```

- `options.resource_group` makes pskit use an existing resource group instead of creating one [docs/providers.md#azure-azure-functions]. Only prod gets it [docs/configuration.md#stages-per-stage-overrides]; dev and staging keep their generated groups.
- `pskit validate` (azure, prod): valid.

The deploying identity needs rights to create resources inside `rg-claims-prod`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 693
    B(693, provider="aws", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#what-handlers-receive", "docs/resources.md#aws-iam"],
      project=dict(files={
          "pskit.yml": """service: orders-core
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.api.create
    events:
    - http: POST /orders
  history:
    handler: app.api.history
    events:
    - http: GET /orders
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def create(event, ctx):
    return {"created": True}, 201


def history(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="Create a managed SNS topic resource `order-events` (other services will subscribe later). Only `api` publishes to it, so only `api` should get the binding and sns:Publish. For now `api` returns the topic's native name in its response.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.order-events: type topic, functions [api]",
                                   "app/api.py: create() returns resource(\"order-events\").native_name",
                                   "Validate for aws, invoke POST /orders"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources", value={"order-events": {"type": "topic", "functions": ["api"]}}),
          S("write_file", path="app/api.py", content=FUTURE + """from py_serverless_kit import resource


def create(event, ctx):
    topic = resource("order-events")
    # TODO: boto3.client("sns").publish(TopicArn=topic.arn, Message=...)
    return {"created": True, "topic": topic.native_name}, 201


def history(event, ctx):
    return []
"""),
          S("validate"),
          S("invoke_local", function="api", method="POST", path="/orders", data={"sku": "a-1"}),
      ],
      final="""```yaml
resources:
  order-events:
    type: topic
    functions: [api]
```

- pskit creates the SNS topic, even with no subscriber yet. `api` gets `PSKIT_RESOURCE_ORDER_EVENTS_*` variables, including the `ARN` in the cloud [docs/resources.md#what-handlers-receive], and an `sns:Publish` grant [docs/resources.md#aws-iam]. `history` gets neither.
- `pskit validate` (aws): valid.
- POST /orders → 201 with `topic: order-events` (locally names are unprefixed; deployed it's the provider-prefixed name).

Publishing is a TODO using `topic.arn` with boto3 (add it to requirements.txt). Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 694
    B(694, provider="gcp", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: file-check
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, file-check-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="i send raw file bytes in body (not json, not form) to POST /checksum. give back size and sha256 hex. empty body 400",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/checksum.py: hash event.http.body (bytes) with hashlib.sha256",
                                   "Add function checksum on POST /checksum",
                                   "Validate for gcp, invoke with a small body"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/checksum.py", content=FUTURE + """import hashlib

from py_serverless_kit import BadRequest


def checksum(event, ctx):
    data = event.http.body or b""
    if not data:
        raise BadRequest("send the file bytes in the request body")
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
"""),
          S("set_config", path="functions.checksum", value={"handler": "app.checksum.checksum", "events": [{"http": "POST /checksum"}]}),
          S("invoke_local", function="checksum", method="POST", path="/checksum", data="hello pskit"),
      ],
      final="""Done, `POST /checksum`:

- `event.http.body` is the raw bytes (already base64-decoded) [docs/handlers.md#httprequest], so any file type works.
- Answer: `{"size": n, "sha256": "<hex>"}`; empty body → 400.

Checks: `pskit validate` (gcp) valid; body `hello pskit` → size 11 and its sha256.

From a shell after deploy: `curl --data-binary @file.zip <url>/checksum`. For very big files, upload to a bucket and checksum from there instead. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 695
    B(695, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: accounts
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="""POST /signup validates the whole body and reports ALL problems at once, not just the first:
- username: 3-20 chars, letters/digits/underscore
- email: must contain @
- age: integer >= 16
Errors -> 422 with details {field: message}. OK -> 201 {"username": ...}.""",
      steps=[
          S("get_project"),
          S("search_docs", query="UnprocessableEntity details", docs=[D("docs/handlers.md", "errors", start="Raise an `HttpError`", end="# -> 422")]),
          S("propose_plan", steps=["Write app/signup.py: collect errors per field, raise UnprocessableEntity(details=errors)",
                                   "Add function signup on POST /signup",
                                   "Validate for azure, invoke a body with two errors"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/signup.py", content=FUTURE + """import re

from py_serverless_kit import UnprocessableEntity

USERNAME = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def signup(event, ctx):
    body = event.http.json(default={}) or {}
    errors = {}
    if not USERNAME.match(str(body.get("username", ""))):
        errors["username"] = "3-20 letters, digits or _"
    if "@" not in str(body.get("email", "")):
        errors["email"] = "must be an email address"
    age = body.get("age")
    if not isinstance(age, int) or isinstance(age, bool) or age < 16:
        errors["age"] = "must be a whole number, 16 or more"
    if errors:
        raise UnprocessableEntity("invalid signup", details=errors)
    return {"username": body["username"]}, 201
"""),
          S("set_config", path="functions.signup", value={"handler": "app.signup.signup", "events": [{"http": "POST /signup"}]}),
          S("invoke_local", function="signup", method="POST", path="/signup", data={"username": "al", "email": "al@example.com", "age": 15}),
      ],
      final="""`POST /signup` is added:

- All three fields are checked, and every problem is collected into one `UnprocessableEntity("invalid signup", details=errors)` [docs/handlers.md#errors].
- Valid → 201 `{"username": ...}`.

Checks: `pskit validate` (azure) valid; `{"username": "al", "email": "al@example.com", "age": 15}` → 422 with `details` for **username** and **age** together.

Try more bodies on **Test** or `pskit invoke -f signup --method POST --path /signup -d '{"username": "alex_9", "email": "a@example.com", "age": 30}'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 696
    B(696, provider="aws", stage="prod", mode="ask", page="Overview", persona="terse_expert",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: geo-lookup
provider:
  name: aws
  region: eu-west-1
functions:
  lookup:
    handler: app.geo.lookup
    events:
    - http: GET /lookup
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + """

def lookup(event, ctx):
    return {"region": ctx.region}
""",
          "requirements.txt": ""}),
      user="prod -> us-east-1 (customers in US). dev/staging stay eu-west-1",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["stages.prod.provider.region: us-east-1", "Validate aws prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages", value={"prod": {"provider": {"region": "us-east-1"}}}),
      ],
      final="""```yaml
stages:
  prod:
    provider:
      region: us-east-1
```

- `pskit validate` (aws, prod): valid; the header shows `region=us-east-1` [docs/configuration.md#stages-per-stage-overrides].
- dev and staging stay in eu-west-1.

If prod was already deployed in eu-west-1, the next prod deploy recreates everything in us-east-1 (new API URL; data in eu-west-1 is not moved). Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 697
    B(697, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#gcp-multi-trigger-functions-are-split-automatically", "docs/handlers.md#event"],
      project=dict(files={
          "pskit.yml": """service: thumbnailer
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, thumbnailer-dev}
functions:
  process:
    handler: app.process.handle
    events:
    - topic: image-uploaded
""",
          "app/__init__.py": "",
          "app/process.py": FUTURE + """

def handle(event, ctx):
    ids = [r.json().get("image_id") for r in event.records]
    return {"processed": ids}
""",
          "requirements.txt": ""}),
      user="Ops sometimes need to reprocess one image by hand. Add POST /reprocess with {image_id} to the same `process` function, sharing the code with the Pub/Sub path. Reply {\"processed\": [image_id]} in both cases.",
      steps=[
          S("get_project"),
          S("search_docs", query="gcp function http and topic split",
            docs=[D("docs/events.md", "gcp-multi-trigger-functions-are-split-automatically")]),
          S("propose_plan", steps=["app/process.py: if event.is_http take image_id from the body, else from the records",
                                   "process.events += http POST /reprocess",
                                   "Validate for gcp, invoke the http path"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/process.py", content=FUTURE + """from py_serverless_kit import BadRequest


def handle(event, ctx):
    if event.is_http:
        image_id = (event.http.json(default={}) or {}).get("image_id")
        if not image_id:
            raise BadRequest("image_id is required")
        ids = [image_id]
    else:
        ids = [r.json().get("image_id") for r in event.records]
    ctx.logger.info("processing", extra={"ids": ids, "trigger": event.type})
    return {"processed": ids}
"""),
          S("set_config", path="functions.process.events", value=[{"topic": "image-uploaded"}, {"http": "POST /reprocess"}]),
          S("invoke_local", function="process", type="http", method="POST", path="/reprocess", data={"image_id": "img-77"}),
      ],
      final="""```yaml
functions:
  process:
    handler: app.process.handle
    events:
      - topic: image-uploaded
      - http: POST /reprocess
```

- One handler, two paths: `event.is_http` picks the body, otherwise the Pub/Sub records [docs/handlers.md#event].
- GCP can't mix HTTP and events in one Cloud Function, so pskit deploys `process` (HTTP) and `process-topic0` (Pub/Sub) from the same code [docs/events.md#gcp-multi-trigger-functions-are-split-automatically]; `pskit info` shows one function.
- `pskit validate` (gcp): valid; POST /reprocess `{"image_id": "img-77"}` → `{"processed": ["img-77"]}`.

The route is public (`auth: none`); add `auth: iam` if only ops accounts may call it. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 698
    B(698, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: diary
provider:
  name: azure
  region: westeurope
functions:
  read:
    handler: app.diary.read
    events:
    - http: GET /entries
  write:
    handler: app.diary.write
    events:
    - http: POST /entries
  delete:
    handler: app.diary.delete
    events:
    - http: DELETE /entries/{id}
""",
          "app/__init__.py": "",
          "app/diary.py": FUTURE + """

def read(event, ctx):
    return []


def write(event, ctx):
    return {"saved": True}, 201


def delete(event, ctx):
    return None
""",
          "requirements.txt": ""}),
      user="can you put a password on my diary api? strangers shouldn't change it",
      steps=[
          S("get_project"),
          S("search_docs", query="azure auth key function key", docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", say="On Azure the built-in protection is a function key: a long secret the caller must send. Reading, writing and deleting are separate routes.",
            question="Which routes should need the key?",
            options=["Only writing and deleting (anyone can read)", "All three"],
            answer="only writing and deleting"),
          S("propose_plan", steps=["write: http {POST /entries, auth: key}", "delete: http {DELETE /entries/{id}, auth: key}",
                                   "read stays public; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.write.events.0", value={"http": {"path": "/entries", "method": "POST", "auth": "key"}}),
          S("set_config", path="functions.delete.events.0", value={"http": {"path": "/entries/{id}", "method": "DELETE", "auth": "key"}}),
      ],
      final="""Writing and deleting now need the key; reading stays open:

```yaml
functions:
  write:
    events:
      - http: {path: /entries, method: POST, auth: key}
  delete:
    events:
      - http: {path: "/entries/{id}", method: DELETE, auth: key}
```

- `auth: key` uses Azure's function key [docs/events.md#http]. Without it, Azure answers 401 before your code runs.
- `pskit validate` (azure): valid.

After **Deploy** (or `pskit deploy -s dev`), copy the function key from the Azure portal and send it with the requests from your diary app. Keep it out of public web pages, because anyone who sees it can write."""),

    # ------------------------------------------------------------------ 699
    B(699, provider="aws", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#logging"],
      project=dict(files={
          "pskit.yml": """service: profiles
provider:
  name: aws
  region: eu-west-1
functions:
  users:
    handler: app.users.handler
    events:
    - http: GET /users/{id}
    - http: GET /users/{id}/posts
""",
          "app/__init__.py": "",
          "app/users.py": FUTURE + """

def handler(event, ctx):
    ctx.logger.info("hit", extra={"path": event.http.path})
    if event.http.path.endswith("/posts"):
        return {"posts": []}
    return {"id": event.http.path_params["id"]}
""",
          "requirements.txt": ""}),
      user="metrics: log route template not raw path (cardinality). also dispatch on route not endswith",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/users.py: log event.http.route; branch on route == \"/users/{id}/posts\"",
                                   "Validate aws, invoke /users/5/posts"]),
          S("write_file", path="app/users.py", content=FUTURE + """
POSTS_ROUTE = "/users/{id}/posts"


def handler(event, ctx):
    route = event.http.route
    ctx.logger.info("hit", extra={"route": route})
    if route == POSTS_ROUTE:
        return {"posts": []}
    return {"id": event.http.path_params["id"]}
"""),
          S("validate"),
          S("invoke_local", function="users", method="GET", path="/users/5/posts"),
      ],
      final="""Done:

- Logs `route` (the matched template, e.g. `/users/{id}/posts`) [docs/handlers.md#httprequest] instead of the raw path, so metrics get one series per route [docs/handlers.md#logging].
- Dispatch compares `event.http.route` to the template.
- `pskit validate` (aws): valid; GET /users/5/posts → `{"posts": []}`, log `route: /users/{id}/posts`.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 700
    B(700, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: world-clock
provider:
  name: gcp
  region: asia-northeast1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, world-clock-dev}
functions:
  clock:
    handler: app.clock.now
    events:
    - http: GET /now
""",
          "app/__init__.py": "",
          "app/clock.py": FUTURE + """from datetime import datetime, timezone


def now(event, ctx):
    return {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
""",
          "requirements.txt": ""}),
      user="my clock shows only UTC. my friends are in Tokyo, can it also show their time?",
      steps=[
          S("get_project"),
          S("read_file", path="app/clock.py"),
          S("propose_plan", steps=["app/clock.py: add tokyo time (Japan is always UTC+9, no daylight saving)",
                                   "Validate for gcp, call GET /now"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/clock.py", content=FUTURE + """from datetime import datetime, timedelta, timezone

TOKYO = timezone(timedelta(hours=9), "JST")  # Japan has no daylight saving time


def now(event, ctx):
    utc_now = datetime.now(timezone.utc)
    return {
        "utc": utc_now.isoformat(timespec="seconds"),
        "tokyo": utc_now.astimezone(TOKYO).isoformat(timespec="seconds"),
    }
"""),
          S("validate"),
          S("invoke_local", function="clock", method="GET", path="/now"),
      ],
      final="""Your clock now shows Tokyo too:

- `GET /now` → `{"utc": "...", "tokyo": "...+09:00"}`. Japan is always 9 hours ahead of UTC (no summer time), so a fixed offset is exact.
- `pskit validate` (gcp): valid; the local call returned both times (see above).

Try it on **Test** > **▶ Run locally**, then **Deploy** or `pskit deploy -s dev`. For cities with summer time (like London) a fixed offset isn't enough; ask me and I'll use proper time zones."""),
]
