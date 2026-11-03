"""Category B (build / add), batch 36 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 701
    B(701, provider="aws", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: daily-boost
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "requirements.txt": ""}),
      user="i want a web page that shows a random motivating quote each time you open it",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/quotes.py with a few quotes; GET /quote returns a small HTML page with a random one",
                                   "Validate for aws, open it locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/quotes.py", content=FUTURE + """import html
import random

from py_serverless_kit import Response

QUOTES = [
    "Small steps every day.",
    "Done is better than perfect.",
    "You don't have to see the whole staircase, just take the first step.",
    "Progress, not perfection.",
]


def quote(event, ctx):
    text = html.escape(random.choice(QUOTES))
    return Response.html(f"<html><body style='font-family:sans-serif;text-align:center;margin-top:20%'>"
                         f"<h1>{text}</h1></body></html>")
"""),
          S("set_config", path="functions.quote", value={"handler": "app.quotes.quote", "events": [{"http": "GET /quote"}]}),
          S("invoke_local", function="quote", method="GET", path="/quote"),
      ],
      final="""Your quote page is ready at **GET /quote**:

- Every visit picks a random quote from the list in `app/quotes.py` and shows it big in the middle of the page (`Response.html` [docs/handlers.md#returning-a-response]).
- Add your own quotes to `QUOTES`.

Checks: `pskit validate` (aws) valid; opening it locally returned 200 with an HTML page.

Run it again on **Test** > **▶ Run locally**; put it online with **Deploy** or `pskit deploy -s dev` and open the URL in your browser."""),

    # ------------------------------------------------------------------ 702
    B(702, provider="gcp", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: settings-svc
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, settings-svc-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="PUT /settings/{key} body {value}. upsert in memory: 201 when new, 200 when replaced",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/settings.py: put() stores value, returns (body, 201|200)",
                                   "functions.settings on PUT /settings/{key}", "Validate gcp, invoke twice"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/settings.py", content=FUTURE + """from py_serverless_kit import BadRequest

SETTINGS = {}


def put(event, ctx):
    key = event.http.path_params["key"]
    body = event.http.json(default={}) or {}
    if "value" not in body:
        raise BadRequest("body needs `value`")
    created = key not in SETTINGS
    SETTINGS[key] = body["value"]
    return {"key": key, "value": body["value"]}, 201 if created else 200
"""),
          S("set_config", path="functions.settings", value={"handler": "app.settings.put", "events": [{"http": "PUT /settings/{key}"}]}),
          S("invoke_local", function="settings", method="PUT", path="/settings/theme", data={"value": "dark"}),
      ],
      final="""```yaml
functions:
  settings:
    handler: app.settings.put
    events:
      - http: PUT /settings/{key}
```

- `(body, 201 if created else 200)` [docs/handlers.md#returning-a-response]; missing `value` → 400.
- `pskit validate` (gcp): valid; first PUT /settings/theme → 201. Each local invoke is a fresh process, so the 200 (replace) path only shows within one running instance (`pskit dev` or deployed).

In-memory, per instance. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 703
    B(703, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: club-calendar
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="""GET /events.ics: a calendar file people can subscribe to in Outlook/Google Calendar.
- Content-Type text/calendar; charset=utf-8
- two sample events (training Tue 2026-11-10 18:00-19:30 UTC, match Sat 2026-11-14 14:00-16:00 UTC)
- CRLF line endings as the iCalendar format requires""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/calendar.py: build the VCALENDAR text with CRLF, return (text, 200, {Content-Type: text/calendar; charset=utf-8})",
                                   "Add function calendar on GET /events.ics",
                                   "Validate for azure, invoke"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/calendar.py", content=FUTURE + """
EVENTS = [
    ("training-1110", "Training", "20261110T180000Z", "20261110T193000Z"),
    ("match-1114", "Match", "20261114T140000Z", "20261114T160000Z"),
]


def calendar(event, ctx):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//club-calendar//pskit//EN"]
    for uid, title, start, end in EVENTS:
        lines += ["BEGIN:VEVENT", f"UID:{uid}@club.example.com", "DTSTAMP:20261101T000000Z",
                  f"DTSTART:{start}", f"DTEND:{end}", f"SUMMARY:{title}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\\r\\n".join(lines) + "\\r\\n", 200, {"Content-Type": "text/calendar; charset=utf-8"}
"""),
          S("set_config", path="functions.calendar", value={"handler": "app.calendar.calendar", "events": [{"http": "GET /events.ics"}]}),
          S("invoke_local", function="calendar", method="GET", path="/events.ics"),
      ],
      final="""`GET /events.ics` serves a subscribable calendar:

- The body is built line by line and joined with CRLF; the `(body, 200, headers)` form sets `Content-Type: text/calendar; charset=utf-8` [docs/handlers.md#returning-a-response].
- Two events (Training 10 Nov, Match 14 Nov), each with a stable `UID` so calendar apps update instead of duplicating.

Checks: `pskit validate` (azure) valid; local GET → 200 with `text/calendar` and the VCALENDAR text (`\\r\\n` between lines).

After **Deploy** (`pskit deploy -s dev`), people add the URL as "subscribe from URL" in their calendar app."""),

    # ------------------------------------------------------------------ 704
    B(704, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: shipping
provider:
  name: aws
  region: us-east-1
functions: {}
""",
          "requirements.txt": ""}),
      user="subscribe new fn `label` to existing SNS topic shipment-created (other team's stack, same account+region). by name, dont create",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/label.py: log shipment_id per record",
                                   "functions.label: topic {name: shipment-created, existing: true}", "Validate aws, invoke"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/label.py", content=FUTURE + """

def label(event, ctx):
    ids = [r.json(default={}).get("shipment_id") for r in event.records]
    ctx.logger.info("labels", extra={"shipments": ids})
    return {"labels": ids}
"""),
          S("set_config", path="functions.label",
            value={"handler": "app.label.label", "events": [{"topic": {"name": "shipment-created", "existing": True}}]}),
          S("invoke_local", function="label", type="topic", data={"shipment_id": "sh-9"}),
      ],
      final="""```yaml
functions:
  label:
    handler: app.label.label
    events:
      - topic: {name: shipment-created, existing: true}
```

- `existing: true`: pskit only adds the subscription, the topic stays the other team's [docs/events.md#topic].
- `pskit validate` (aws): valid; one message → `{"labels": ["sh-9"]}`.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 705
    B(705, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#events-triggers", "docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: docs-gen
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, docs-gen-dev}
functions:
  api:
    handler: app.api.handler
    events:
    - http: POST /documents
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def handler(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="need new fn render-pdf, input {doc_id}, give back {doc_id, pages: 1} for now",
      steps=[
          S("get_project"),
          S("ask_user", question="Who will call render-pdf?",
            options=["Only my other functions / workflows (no public URL)", "Outside clients over HTTP"],
            answer="only api calls it"),
          S("propose_plan", steps=["app/render.py: render_pdf returns {doc_id, pages: 1}",
                                   "functions.render-pdf with no events (invoke-only)",
                                   "Validate gcp, invoke with -t invoke"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/render.py", content=FUTURE + """

def render_pdf(event, ctx):
    data = event.data or {}
    return {"doc_id": data.get("doc_id"), "pages": 1}
"""),
          S("set_config", path="functions.render-pdf", value={"handler": "app.render.render_pdf"}),
          S("invoke_local", function="render-pdf", type="invoke", data={"doc_id": "d-12"}),
      ],
      final="""`render-pdf` is an invoke-only function (no `events`), so it gets no public trigger [docs/events.md#events-triggers]:

```yaml
functions:
  render-pdf:
    handler: app.render.render_pdf
```

- `pskit validate` (gcp): valid; invoke with `{"doc_id": "d-12"}` → `{"doc_id": "d-12", "pages": 1}`.
- From `api`: `from py_serverless_kit import invoke` then `invoke("render-pdf", {"doc_id": ...})`. On GCP that is an authenticated HTTPS call with an ID token [docs/handlers.md#invoke-calling-another-function].

Test again: `pskit invoke -f render-pdf -t invoke -d '{"doc_id": "d-1"}'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 706
    B(706, provider="azure", stage="staging", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: profiles
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="""PATCH /profiles/{id} does a partial update of sample profiles (p1: {name: "Ana", city: "Porto", newsletter: false}).
- only name, city, newsletter may change; any other field -> 400 naming it
- unknown id -> 404
- returns the full updated profile""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/profiles.py: merge allowed fields into the stored dict",
                                   "Add function profiles on PATCH /profiles/{id}",
                                   "Validate azure staging, invoke p1 with {city: Lisbon}"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/profiles.py", content=FUTURE + """from py_serverless_kit import BadRequest, NotFound

ALLOWED = {"name", "city", "newsletter"}
PROFILES = {"p1": {"id": "p1", "name": "Ana", "city": "Porto", "newsletter": False}}


def patch(event, ctx):
    profile = PROFILES.get(event.http.path_params["id"])
    if profile is None:
        raise NotFound("profile not found")
    changes = event.http.json(default={}) or {}
    unknown = sorted(set(changes) - ALLOWED)
    if unknown:
        raise BadRequest("fields not allowed: " + ", ".join(unknown))
    profile.update(changes)
    return profile
"""),
          S("set_config", path="functions.profiles", value={"handler": "app.profiles.patch", "events": [{"http": "PATCH /profiles/{id}"}]}),
          S("invoke_local", function="profiles", method="PATCH", path="/profiles/p1", data={"city": "Lisbon"}),
          S("invoke_local", function="profiles", method="PATCH", path="/profiles/p1", data={"role": "admin"}),
      ],
      final="""`PATCH /profiles/{id}` is added:

| Check | Result |
|---|---|
| `pskit validate` (azure, staging) | valid |
| p1 `{"city": "Lisbon"}` | 200, full profile with city Lisbon |
| p1 `{"role": "admin"}` | 400 `fields not allowed: role` |

Unknown ids raise `NotFound` → 404 [docs/handlers.md#errors]. Field types aren't checked yet (e.g. `newsletter` should be a bool); say if you want that. Test on **Test** or `pskit invoke -f profiles --method PATCH --path /profiles/p1 -d '{"newsletter": true}' -s staging`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 707
    B(707, provider="aws", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#retry-and-catch", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: subscriptions
provider:
  name: aws
  region: eu-west-1
functions:
  charge-card:
    handler: app.billing.charge
  activate:
    handler: app.billing.activate
  notify-declined:
    handler: app.billing.declined
workflows:
  renew:
    start_at: Charge
    states:
      Charge: {type: task, function: charge-card, next: Activate}
      Activate: {type: task, function: activate, end: true}
""",
          "app/__init__.py": "",
          "app/billing.py": FUTURE + """

def charge(event, ctx):
    return {**(event.data or {}), "charged": True}


def activate(event, ctx):
    return {**(event.data or {}), "active": True}


def declined(event, ctx):
    return {**(event.data or {}), "notified": True}
""",
          "requirements.txt": ""}),
      user="When the bank declines a card, charge-card should raise a `PaymentDeclined` exception and the workflow must go to notify-declined instead of failing. Other errors (timeouts etc.) should still be retried twice and then fail the run. A card number ending in 0000 means declined, for testing.",
      steps=[
          S("get_project"),
          S("search_docs", query="catch custom exception class name", docs=[D("docs/workflows.md", "retry-and-catch", start="Error names are the", end="Without a match the run fails.")]),
          S("propose_plan", steps=["app/billing.py: class PaymentDeclined(Exception); raise it for cards ending 0000",
                                   "Charge: catch [PaymentDeclined] -> Declined; retry [\"*\"] max_attempts 2",
                                   "Declined: task notify-declined, end",
                                   "Validate for aws, invoke charge-card with a good card"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/billing.py", content=FUTURE + """

class PaymentDeclined(Exception):
    pass


def charge(event, ctx):
    data = event.data or {}
    if str(data.get("card", "")).endswith("0000"):
        raise PaymentDeclined("card declined by the bank")
    return {**data, "charged": True}


def activate(event, ctx):
    return {**(event.data or {}), "active": True}


def declined(event, ctx):
    return {**(event.data or {}), "notified": True}
"""),
          S("set_config", path="workflows.renew.states",
            value={"Charge": {"type": "task", "function": "charge-card", "next": "Activate",
                              "retry": [{"errors": ["*"], "max_attempts": 2}],
                              "catch": [{"errors": ["PaymentDeclined"], "next": "Declined"}]},
                   "Activate": {"type": "task", "function": "activate", "end": True},
                   "Declined": {"type": "task", "function": "notify-declined", "end": True}}),
          S("invoke_local", function="charge-card", type="workflow", data={"customer": "c-3", "card": "4242"}),
      ],
      final="""```yaml
workflows:
  renew:
    start_at: Charge
    states:
      Charge:
        type: task
        function: charge-card
        next: Activate
        retry:
          - {errors: ["*"], max_attempts: 2}
        catch:
          - {errors: [PaymentDeclined], next: Declined}
      Activate: {type: task, function: activate, end: true}
      Declined: {type: task, function: notify-declined, end: true}
```

- Error names are your Python exception class names, so `PaymentDeclined` is matched by its name [docs/workflows.md#retry-and-catch].
- Caveat: retriers are checked before catchers and `"*"` also matches `PaymentDeclined`, so a declined card is retried twice first, then caught. To skip those retries, list the retryable errors instead of `"*"` (e.g. `[TimeoutError, ConnectionError]`).
- `pskit validate` (aws): valid. charge-card with card 4242 → `charged: true`.

Try the declined path: `pskit workflow run renew -i '{"card": "40000000"}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 708
    B(708, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      project=dict(files={
          "pskit.yml": """service: shop-stats
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, shop-stats-dev}
functions:
  stats:
    handler: app.stats.stats
""",
          "app/__init__.py": "",
          "app/stats.py": FUTURE + """

def stats(event, ctx):
    return {"orders": 42, "revenue": 1234.5}
""",
          "requirements.txt": ""}),
      user="I already have a stats function. Every night at 23:00 I want another function to ask stats for the numbers and write a short summary in the log.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/summary.py: invoke(\"stats\", {}) and log a one-line summary",
                                   "Add function nightly-summary with schedule \"0 23 * * *\"",
                                   "Validate for gcp, run it locally (stats is called in-process)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/summary.py", content=FUTURE + """from py_serverless_kit import invoke


def summary(event, ctx):
    numbers = invoke("stats", {})
    text = f"{numbers['orders']} orders, {numbers['revenue']:.2f} revenue"
    ctx.logger.info("nightly summary", extra={"summary": text})
    return {"summary": text}
"""),
          S("set_config", path="functions.nightly-summary", value={"handler": "app.summary.summary", "events": [{"schedule": "0 23 * * *"}]}),
          S("invoke_local", function="nightly-summary", type="schedule"),
      ],
      final="""Added `nightly-summary`, every night at 23:00 UTC:

- It calls your `stats` function with `invoke("stats", {})` and logs one line [docs/handlers.md#invoke-calling-another-function]. On GCP that call is an authenticated HTTPS request; locally `stats` runs in the same process.
- Test run: `{"summary": "42 orders, 1234.50 revenue"}` and a `nightly summary` log line.
- `pskit validate` (gcp): valid.

For a different time zone add `timezone`, e.g. `schedule: {cron: "0 23 * * *", timezone: Europe/Paris}`. Run it again on **Test** (schedule) and read the line on **Logs** after **Deploy** (`pskit deploy -s dev`)."""),

    # ------------------------------------------------------------------ 709
    B(709, provider="azure", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: orders
provider:
  name: azure
  region: westeurope
functions:
  order:
    handler: app.orders.get
    events:
    - http: GET /orders/{id}
  items:
    handler: app.orders.items
    events:
    - http: GET /orders/{id}/items
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def get(event, ctx):
    return {"order": event.http.path_params["id"]}


def items(event, ctx):
    return {"order": event.http.path_params["id"], "items": []}
""",
          "requirements.txt": ""}),
      user="rename path param {id} to {order_id} in both routes and the code, our api doc use order_id",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["order: GET /orders/{order_id}; items: GET /orders/{order_id}/items",
                                   "app/orders.py: path_params[\"order_id\"]", "Validate azure, invoke both"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.order.events.0", value={"http": "GET /orders/{order_id}"}),
          S("set_config", path="functions.items.events.0", value={"http": "GET /orders/{order_id}/items"}),
          S("write_file", path="app/orders.py", content=FUTURE + """

def get(event, ctx):
    return {"order": event.http.path_params["order_id"]}


def items(event, ctx):
    return {"order": event.http.path_params["order_id"], "items": []}
"""),
          S("validate"),
          S("invoke_local", function="items", method="GET", path="/orders/o-5/items"),
      ],
      final="""Renamed in both routes and the code:

```yaml
functions:
  order:
    events:
      - http: GET /orders/{order_id}
  items:
    events:
      - http: GET /orders/{order_id}/items
```

- The handler reads `event.http.path_params["order_id"]` [docs/events.md#http]. The URLs callers use don't change, only the name.
- `pskit validate` (azure): valid; GET /orders/o-5/items → `{"order": "o-5", "items": []}`.

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 710
    B(710, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: support-desk
provider:
  name: aws
  region: eu-south-2
functions:
  sla-check:
    handler: app.sla.check
""",
          "app/__init__.py": "",
          "app/sla.py": FUTURE + """

def check(event, ctx):
    return {"breaches": 0}
""",
          "requirements.txt": ""}),
      user="sla-check must run every 15 minutes during office hours only: Monday to Friday, 08:00 until 18:45 Madrid time (so the last run is 18:45). Name the schedule office-hours.",
      steps=[
          S("get_project"),
          S("search_docs", query="schedule cron timezone aws", docs=[D("docs/events.md", "schedule", end="The handler gets `event.type == \"schedule\"`")]),
          S("propose_plan", steps=["functions.sla-check.events: schedule {cron: \"*/15 8-18 * * 1-5\", timezone: Europe/Madrid, name: office-hours}",
                                   "Validate for aws (prod), invoke the schedule"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sla-check.events",
            value=[{"schedule": {"cron": "*/15 8-18 * * 1-5", "timezone": "Europe/Madrid", "name": "office-hours"}}]),
          S("invoke_local", function="sla-check", type="schedule"),
      ],
      final="""```yaml
functions:
  sla-check:
    handler: app.sla.check
    events:
      - schedule:
          cron: "*/15 8-18 * * 1-5"
          timezone: Europe/Madrid
          name: office-hours
```

- `*/15 8-18` = minutes 0, 15, 30, 45 of hours 8–18, so 08:00 to 18:45; `1-5` = Monday–Friday.
- AWS EventBridge Scheduler honours `timezone`, so summer/winter time is handled [docs/events.md#schedule].
- `pskit validate` (aws, prod): valid; a scheduled run → `{"breaches": 0}`.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 711
    B(711, provider="gcp", stage="staging", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: payments-gw
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, payments-gw-stg}
functions:
  pay:
    handler: app.pay.pay
    events:
    - http: POST /payments
""",
          "app/__init__.py": "",
          "app/pay.py": FUTURE + """import uuid


def pay(event, ctx):
    return {"payment_id": uuid.uuid4().hex[:10]}, 201
""",
          "requirements.txt": ""}),
      user="""Make POST /payments idempotent for client retries:
- the `Idempotency-Key` header is required (400 if missing)
- the same key again returns the first response with status 200 instead of creating a new payment
- in memory per instance is fine for this sprint""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/pay.py: read event.http.headers[\"idempotency-key\"]; cache {key: body}",
                                   "Missing header -> BadRequest; repeat -> (cached body, 200)",
                                   "Validate gcp staging, invoke without the header (400 expected)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/pay.py", content=FUTURE + """import uuid

from py_serverless_kit import BadRequest

SEEN = {}  # Idempotency-Key -> first response body (per instance)


def pay(event, ctx):
    key = event.http.headers.get("idempotency-key")
    if not key:
        raise BadRequest("Idempotency-Key header is required")
    if key in SEEN:
        return SEEN[key], 200
    body = {"payment_id": uuid.uuid4().hex[:10]}
    SEEN[key] = body
    return body, 201
"""),
          S("validate"),
          S("invoke_local", function="pay", method="POST", path="/payments", data={"amount": 10}),
      ],
      final="""POST /payments is idempotent now:

- `Idempotency-Key` is read from the case-insensitive `event.http.headers` [docs/handlers.md#httprequest]; missing → 400 [docs/handlers.md#errors].
- First call with a key → 201 and a new payment id; same key again → 200 with the same body.

Checks: `pskit validate` (gcp, staging) valid; a POST without the header → 400 `Idempotency-Key header is required` (as specified). `invoke_local` can't send headers; test the happy path with `pskit invoke -f pay --method POST --path /payments -H "Idempotency-Key: k-1" -d '{"amount": 10}' -s staging`.

The cache is per instance and lost on restart; before going live it needs a shared store. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 712
    B(712, provider="azure", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: leap-year
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="for my kids homework: a link where you put a year and it says if it is a leap year",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write app/leap.py: GET /leap?year=2028 answers yes/no with the rule",
                                   "Validate for azure, try 2028 locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/leap.py", content=FUTURE + """from py_serverless_kit import BadRequest


def leap(event, ctx):
    try:
        year = int(event.http.query.get("year", ""))
    except ValueError:
        raise BadRequest("add ?year=2028 to the address")
    is_leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return {"year": year, "leap_year": is_leap,
            "answer": f"{year} is {'a' if is_leap else 'not a'} leap year"}
"""),
          S("set_config", path="functions.leap", value={"handler": "app.leap.leap", "events": [{"http": "GET /leap"}]}),
          S("invoke_local", function="leap", method="GET", path="/leap?year=2028"),
      ],
      final="""Here it is: **GET /leap?year=2028**

- Answer: `{"year": 2028, "leap_year": true, "answer": "2028 is a leap year"}` (that's what it said when I tried it).
- The rule: divisible by 4, except century years, unless divisible by 400 (so 2000 yes, 1900 no).
- No year or not a number → a friendly 400 message.

`pskit validate` (azure): valid. Try other years on **Test** > **▶ Run locally**; put it online with **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 713
    B(713, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#http", "docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: catalog
provider:
  name: aws
  region: eu-west-1
functions: {}
""",
          "app/__init__.py": "",
          "app/items.py": FUTURE + """

def update(event, ctx):
    item_id = event.http.path_params["id"]
    return {"id": item_id, **(event.http.json(default={}) or {})}
""",
          "requirements.txt": ""}),
      user="""SAM had this, handler code is already in app/items.py:

UpdateItem:
  Type: AWS::Serverless::Function
  Properties:
    Handler: app.items.update
    Timeout: 15
    MemorySize: 256
    Events:
      Put: {Type: HttpApi, Properties: {Path: /items/{id}, Method: put}}""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["functions.update-item: handler app.items.update, timeout 15, memory 256, http PUT /items/{id}",
                                   "Validate for aws, invoke PUT /items/7"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.update-item",
            value={"handler": "app.items.update", "timeout": 15, "memory": 256, "events": [{"http": "PUT /items/{id}"}]}),
          S("invoke_local", function="update-item", method="PUT", path="/items/7", data={"price": 12.5}),
      ],
      final="""```yaml
functions:
  update-item:
    handler: app.items.update
    timeout: 15
    memory: 256
    events:
      - http: PUT /items/{id}
```

- `Handler`, `Timeout`, `MemorySize` map to `handler`, `timeout`, `memory` [docs/configuration.md#functions]; the HttpApi event becomes `- http: PUT /items/{id}` on pskit's HTTP API [docs/events.md#http].
- `pskit validate` (aws): valid; PUT /items/7 `{"price": 12.5}` → `{"id": "7", "price": 12.5}`.

Deploy: **Deploy** or `pskit deploy -s dev`. The URL changes from the SAM stack's API to the one in `pskit info`."""),

    # ------------------------------------------------------------------ 714
    B(714, provider="gcp", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#package"],
      project=dict(files={
          "pskit.yml": """service: risk-score
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, risk-score-dev}
functions:
  score:
    handler: app.score.score
    events:
    - http: POST /score
""",
          "app/__init__.py": "",
          "app/score.py": FUTURE + """

def score(event, ctx):
    return {"score": 0.1}
""",
          "requirements.txt": "acme-risk-model>=3.2\n"}),
      user="Cloud Build can't reach our private package index, so the remote build fails installing acme-risk-model. Our deploy machine can reach it. Install the dependencies into the bundle on our side instead of shipping requirements.txt.",
      steps=[
          S("get_project"),
          S("search_docs", query="package vendor requirements remote build", docs=[D("docs/configuration.md", "package", start="| `vendor` |", end="get dependencies pip-installed into the zip as Linux (`manylinux2014`) wheels for the target runtime and architecture.")]),
          S("propose_plan", steps=["package.vendor: true (pip install into the bundle on the deploy machine)", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="package", value={"vendor": True}),
      ],
      final="""```yaml
package:
  vendor: true
```

- GCP normally builds remotely from `requirements.txt`; `vendor: true` forces `pip install` into the bundle on your machine instead [docs/configuration.md#package].
- `pskit validate` (gcp): valid.

Your deploy machine needs pip access to the private index (e.g. via `package.pip_args` with `--extra-index-url`, or your pip config). Check the bundle with **Deploy > Package** or `pskit package -s dev`, then **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 715
    B(715, provider="azure", stage="prod", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#provider", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: hr-portal
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
      user="log_retention_days 365 in prod (audit). others default",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["stages.prod.provider.log_retention_days: 365", "Validate azure prod"]),
          S("set_config", path="stages", value={"prod": {"provider": {"log_retention_days": 365}}}),
      ],
      final="""```yaml
stages:
  prod:
    provider:
      log_retention_days: 365
```

- `log_retention_days` defaults to 14 [docs/configuration.md#provider]; prod alone gets 365 [docs/configuration.md#stages-per-stage-overrides].
- `pskit validate` (azure, prod): valid.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 716
    B(716, provider="aws", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: helpdesk
provider:
  name: aws
  region: eu-west-1
functions:
  page-oncall:
    handler: app.desk.page
  queue-ticket:
    handler: app.desk.queue_ticket
""",
          "app/__init__.py": "",
          "app/desk.py": FUTURE + """

def page(event, ctx):
    return {**(event.data or {}), "paged": True}


def queue_ticket(event, ctx):
    return {**(event.data or {}), "queued": True}
""",
          "requirements.txt": ""}),
      user="new wf `triage`: if $.tags list have 'urgent' -> page-oncall, else queue-ticket",
      steps=[
          S("get_project"),
          S("search_docs", query="choice contains list", docs=[D("docs/workflows.md", "choice-rules", start="| Operator |", end="| `matches` |")]),
          S("propose_plan", steps=["workflows.triage: Route (choice: $.tags contains urgent -> Page, default Queue)",
                                   "Page (page-oncall) / Queue (queue-ticket), both end", "Validate aws, invoke page-oncall"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.triage",
            value={"start_at": "Route",
                   "states": {"Route": {"type": "choice",
                                        "choices": [{"variable": "$.tags", "contains": "urgent", "next": "Page"}],
                                        "default": "Queue"},
                              "Page": {"type": "task", "function": "page-oncall", "end": True},
                              "Queue": {"type": "task", "function": "queue-ticket", "end": True}}}),
          S("invoke_local", function="page-oncall", type="workflow", data={"ticket": "T-8", "tags": ["urgent", "db"]}),
      ],
      final="""```yaml
workflows:
  triage:
    start_at: Route
    states:
      Route:
        type: choice
        choices:
          - {variable: $.tags, contains: urgent, next: Page}
        default: Queue
      Page: {type: task, function: page-oncall, end: true}
      Queue: {type: task, function: queue-ticket, end: true}
```

- `contains` checks membership in a list (or a substring) [docs/workflows.md#choice-rules]; no `tags` → Queue.
- `pskit validate` (aws): valid (Step Functions). page-oncall with T-8 → `paged: true`.

Try both: `pskit workflow run triage -i '{"ticket": "T-9", "tags": ["ui"]}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 717
    B(717, provider="gcp", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: ingest
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, ingest-prod-3}
functions:
  load:
    handler: app.load.load
    events:
    - storage: {bucket: ingest-drop-5512, existing: true}
""",
          "app/__init__.py": "",
          "app/load.py": FUTURE + """

def load(event, ctx):
    return {"loaded": [r.key for r in event.records]}
""",
          "requirements.txt": ""}),
      user="load: skip files > 10 MB with warning log (key, size), still load others",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/load.py: record.size > 10 MB -> warning + skip", "Validate gcp prod, invoke a 25 MB file"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/load.py", content=FUTURE + """
MAX_BYTES = 10 * 1024 * 1024


def load(event, ctx):
    loaded, skipped = [], []
    for record in event.records:
        if (record.size or 0) > MAX_BYTES:
            ctx.logger.warning("file too big, skipped", extra={"key": record.key, "size": record.size})
            skipped.append(record.key)
            continue
        loaded.append(record.key)
    return {"loaded": loaded, "skipped": skipped}
"""),
          S("validate"),
          S("invoke_local", function="load", type="storage", data={"bucket": "ingest-drop-5512", "key": "big/dump.csv", "size": 26214400}),
      ],
      final="""Done: records over 10 MB (`record.size` [docs/events.md#storage]) are logged at WARNING with key and size and skipped; the rest load as before.

- `pskit validate` (gcp, prod): valid.
- 25 MB `big/dump.csv` → warning, `{"loaded": [], "skipped": ["big/dump.csv"]}`.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 718
    B(718, provider="azure", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: backup-export
provider:
  name: azure
  region: westeurope
functions:
  export:
    handler: app.export.export
    events:
    - http: GET /export
""",
          "app/__init__.py": "",
          "app/export.py": FUTURE + """

def export(event, ctx):
    return {"contacts": [{"name": "Ana"}, {"name": "Ben"}]}
""",
          "requirements.txt": ""}),
      user="browser just show the json. i want it download as file contacts-export.json",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/export.py: Response.json(..., headers={Content-Disposition: attachment; filename=\"contacts-export.json\"})",
                                   "Validate azure, invoke GET /export"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/export.py", content=FUTURE + """from py_serverless_kit import Response


def export(event, ctx):
    data = {"contacts": [{"name": "Ana"}, {"name": "Ben"}]}
    return Response.json(data, headers={"Content-Disposition": 'attachment; filename="contacts-export.json"'})
"""),
          S("validate"),
          S("invoke_local", function="export", method="GET", path="/export"),
      ],
      final="""Done. The response now has `Content-Disposition: attachment; filename="contacts-export.json"`, so the browser saves it as a file instead of showing it [docs/handlers.md#returning-a-response].

- `pskit validate` (azure): valid.
- GET /export → 200 JSON with the `content-disposition` header.

Deploy: **Deploy** or `pskit deploy -s dev`, then open /export in the browser."""),

    # ------------------------------------------------------------------ 719
    B(719, provider="aws", stage="staging", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: queue-api
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.api.handler
    events:
    - http: POST /jobs
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """

def handler(event, ctx):
    return {"queued": True}, 202
""",
          "requirements.txt": ""}),
      user="add GET /metrics fn, returns {jobs_today: 0} stub",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["app/metrics.py: metrics() -> {jobs_today: 0}", "functions.metrics on GET /metrics", "Validate aws staging, invoke"],
            result={"decision": "approved", "note": "internal only: auth iam, our prometheus scraper signs with SigV4"}),
          S("write_file", say="Adding it with `auth: iam`, as noted.", path="app/metrics.py", content=FUTURE + """

def metrics(event, ctx):
    return {"jobs_today": 0}
"""),
          S("set_config", path="functions.metrics",
            value={"handler": "app.metrics.metrics", "events": [{"http": {"path": "/metrics", "method": "GET", "auth": "iam"}}]}),
          S("invoke_local", function="metrics", method="GET", path="/metrics"),
      ],
      final="""```yaml
functions:
  metrics:
    handler: app.metrics.metrics
    events:
      - http: {path: /metrics, method: GET, auth: iam}
```

- Per your note, `auth: iam` → `AWS_IAM` on the route [docs/events.md#http]: only SigV4-signed callers with `execute-api:Invoke` permission get through.
- `pskit validate` (aws, staging): valid; local GET /metrics → `{"jobs_today": 0}` (local runs don't check IAM).

Give the scraper's role `execute-api:Invoke` on this API. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 720
    B(720, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: plant-care
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, plant-care-dev}
functions:
  water-reminder:
    handler: app.plants.remind
    events:
    - schedule: "0 8 * * *"
""",
          "app/__init__.py": "",
          "app/plants.py": FUTURE + """

def remind(event, ctx):
    plant = (event.data or {}).get("plant", "your plants")
    ctx.logger.info("time to water " + plant)
    return {"reminded": plant}
""",
          "requirements.txt": ""}),
      user="my water reminder says 'your plants'. I have a cactus that needs water only on Sundays at 10, and the fern every day at 8. can the same function do both?",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["water-reminder gets two schedules: daily 08:00 with input {plant: fern}, Sundays 10:00 with input {plant: cactus}",
                                   "Validate for gcp, run the schedule"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.water-reminder.events",
            value=[{"schedule": {"cron": "0 8 * * *", "input": {"plant": "fern"}, "name": "fern"}},
                   {"schedule": {"cron": "0 10 * * 0", "input": {"plant": "cactus"}, "name": "cactus"}}]),
          S("invoke_local", function="water-reminder", type="schedule"),
      ],
      final="""Yes! One function, two alarms:

```yaml
functions:
  water-reminder:
    handler: app.plants.remind
    events:
      - schedule: {cron: "0 8 * * *", input: {plant: fern}, name: fern}
      - schedule: {cron: "0 10 * * 0", input: {plant: cactus}, name: cactus}
```

- Each schedule sends its own `input`, which your code reads as `event.data` [docs/events.md#schedule]. `0` in the last field means Sunday.
- `pskit validate` (gcp): valid. A test run said "time to water fern" (the local test uses the first schedule's input).
- Times are UTC; add `timezone: Europe/London` (or yours) to each schedule if you want local time.

Deploy: **Deploy** or `pskit deploy -s dev`."""),
]
