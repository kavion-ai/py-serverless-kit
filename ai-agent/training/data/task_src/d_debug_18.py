"""Category D (fix a handler bug), batch 18. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

ONPREM = """provider:
  name: onprem
  region: local
{extra}  options:
    host: 127.0.0.1
    port: {port}
"""

GCP = """provider:
  name: gcp
  region: {region}
{extra}  options:
    project: ${{env:GOOGLE_CLOUD_PROJECT, demo-project}}
"""


def B(n, **kw):
    return dict(id=f"d_debug-{n:04d}", category="d_debug", **kw)


def AWS(service, region="us-east-1", extra=""):
    return f"service: {service}\nprovider:\n  name: aws\n  region: {region}\n{extra}"


def AZ(service, region="westeurope", extra=""):
    return f"service: {service}\nprovider:\n  name: azure\n  region: {region}\n{extra}"


def OP(service, port, extra=""):
    return f"service: {service}\n" + ONPREM.format(port=port, extra=extra)


def G(service, region="europe-west1", extra=""):
    return f"service: {service}\n" + GCP.format(region=region, extra=extra)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 341 onprem http, new package app/utils/ hides app/utils.py
    B(341, provider="onprem", stage="dev", mode="ask", page="Code", persona="pasted_error",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": OP("events-api", 8681) + """functions:
  upcoming:
    handler: app.events.upcoming
    events:
      - http: GET /events/upcoming
""",
          "app/__init__.py": "",
          "app/utils.py": FUTURE + """from datetime import date


def parse_date(text):
    return date.fromisoformat(text)
""",
          "app/utils/__init__.py": "",
          "app/utils/slack.py": FUTURE + """
def format_line(name, day):
    return f"*{name}* on {day.isoformat()}"
""",
          "app/events.py": FUTURE + """from app.utils import parse_date
from app.utils.slack import format_line

EVENTS = [("Meetup", "2026-11-12"), ("Workshop", "2026-12-03")]


def upcoming(event, ctx):
    return {"lines": [format_line(name, parse_date(day)) for name, day in EVENTS]}
""",
          "requirements.txt": ""}),
      user="""ImportError: cannot import name 'parse_date' from 'app.utils' (.\\app\\utils\\__init__.py)
I only added a folder app/utils/ with slack.py in it. parse_date is in app/utils.py and didn't change!""",
      steps=[
          S("get_project"),
          S("invoke_local", function="upcoming", path="/events/upcoming"),
          S("propose_plan", steps=["Move `parse_date` into the package as app/utils/dates.py (the folder `app/utils/` now wins over app/utils.py)",
                                   "Import it with `from app.utils.dates import parse_date` in app/events.py",
                                   "GET /events/upcoming locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/utils/dates.py", content=FUTURE + """from datetime import date


def parse_date(text):
    return date.fromisoformat(text)
"""),
          S("write_file", path="app/events.py", content=FUTURE + """from app.utils.dates import parse_date
from app.utils.slack import format_line

EVENTS = [("Meetup", "2026-11-12"), ("Workshop", "2026-12-03")]


def upcoming(event, ctx):
    return {"lines": [format_line(name, parse_date(day)) for name, day in EVENTS]}
"""),
          S("invoke_local", function="upcoming", path="/events/upcoming"),
          S("validate"),
      ],
      final="""A folder `app/utils/` with an `__init__.py` and a file `app/utils.py` have the same import name, `app.utils`, and the package (the folder) wins. So `from app.utils import parse_date` looked in the empty app/utils/__init__.py, as the error shows. I moved `parse_date` to app/utils/dates.py and changed the import in app/events.py.

- GET /events/upcoming: 200 with `*Meetup* on 2026-11-12` and `*Workshop* on 2026-12-03`.
- validate (onprem): valid.

app/utils.py can no longer be imported at all now. Delete it in Code (the tools here can't delete files), so nobody edits it by mistake."""),

    # ------------------------------------------------------------------ 342 onprem http, CSV split on commas inside quotes
    B(342, provider="onprem", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": OP("contacts-import", 8682) + """functions:
  import-csv:
    handler: app.importer.handle
    events:
      - http: POST /contacts/import
""",
          "app/__init__.py": "",
          "app/importer.py": FUTURE + """
def handle(event, ctx):
    lines = event.http.text().strip().splitlines()
    header = lines[0].split(",")
    rows = [dict(zip(header, line.split(","))) for line in lines[1:]]
    return {"imported": rows}
""",
          "requirements.txt": ""}),
      user="POST /contacts/import takes a CSV body (name,city). Spreadsheet exports quote names that contain a comma, like \"Smith, John\",Berlin. That row comes out as name `\"Smith` and city ` John\"`. Quoted fields must stay one value.",
      steps=[
          S("read_file", path="app/importer.py"),
          S("invoke_local", function="import-csv", method="POST", path="/contacts/import",
            data='name,city\n"Smith, John",Berlin\nAnna,Oslo'),
          S("propose_plan", steps=["Parse the body with `csv.DictReader` (it handles quotes and commas inside them) instead of `split(\",\")`",
                                   "POST the same CSV locally; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/importer.py", content=FUTURE + """import csv
import io


def handle(event, ctx):
    reader = csv.DictReader(io.StringIO(event.http.text().strip()))
    return {"imported": list(reader)}
"""),
          S("invoke_local", function="import-csv", method="POST", path="/contacts/import",
            data='name,city\n"Smith, John",Berlin\nAnna,Oslo'),
          S("validate"),
      ],
      final="""`line.split(",")` splits at every comma, also the one inside the quotes. `csv.DictReader` reads CSV the way spreadsheets write it: quoted fields stay together and the quotes are removed. It also uses the first line as the header.

- Before: `{"name": "\\"Smith", "city": " John\\""}`.
- After: `{"name": "Smith, John", "city": "Berlin"}` and `{"name": "Anna", "city": "Oslo"}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 343 onprem workflow, retry names an error the task never raises
    B(343, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": OP("fx-rates", 8683) + """functions:
  fetch-rates:
    handler: app.rates.fetch
  publish:
    handler: app.rates.publish
workflows:
  rates:
    start_at: Fetch
    states:
      Fetch:
        type: task
        function: fetch-rates
        retry:
          - {errors: [UpstreamDown], max_attempts: 3, interval_seconds: 10}
        next: Publish
      Publish: {type: task, function: publish, end: true}
""",
          "app/__init__.py": "",
          "app/rates.py": FUTURE + """SOURCES = {"ecb": "up", "legacy-bank": "down"}  # stands in for the real HTTP call


def fetch(event, ctx):
    source = event.data.get("source", "ecb")
    if SOURCES.get(source) != "up":
        raise RuntimeError(f"upstream {source} down")
    return {"source": source, "eur_usd": 1.08}


def publish(event, ctx):
    return {"published": event.data["eur_usd"]}
""",
          "requirements.txt": ""}),
      user="rates wf: Fetch has retry on UpstreamDown x3, but fails on the 1st attempt when the bank is down. no retries in history",
      steps=[
          S("get_project"),
          S("read_file", path="app/rates.py"),
          S("invoke_local", function="fetch-rates", type="workflow", data={"source": "legacy-bank"}),
          S("propose_plan", steps=["Define `class UpstreamDown(Exception)` and raise it instead of `RuntimeError`; retry matches the exception class name",
                                   "Invoke fetch-rates with the down and the up source; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/rates.py", content=FUTURE + """SOURCES = {"ecb": "up", "legacy-bank": "down"}  # stands in for the real HTTP call


class UpstreamDown(Exception):
    pass


def fetch(event, ctx):
    source = event.data.get("source", "ecb")
    if SOURCES.get(source) != "up":
        raise UpstreamDown(f"upstream {source} down")
    return {"source": source, "eur_usd": 1.08}


def publish(event, ctx):
    return {"published": event.data["eur_usd"]}
"""),
          S("invoke_local", function="fetch-rates", type="workflow", data={"source": "legacy-bank"}),
          S("invoke_local", function="fetch-rates", type="workflow", data={"source": "ecb"}),
          S("validate"),
      ],
      final="""`errors:` in a retry rule are Python exception **class names** [docs/workflows.md#retry-and-catch]. The task raised `RuntimeError`, which isn't in `[UpstreamDown]`, so no retrier matched and the run failed at once. It now raises `UpstreamDown`.

- Down source: the error is now `UpstreamDown: upstream legacy-bank down` (the invoke above), which the retry rule matches: 3 attempts, 10 s apart.
- Up source: `{"source": "ecb", "eur_usd": 1.08}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 344 onprem http, env var only set for prod, read at import
    B(344, provider="onprem", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": OP("stock-api", 8684) + """functions:
  stock:
    handler: app.stock.get
    events:
      - http: GET /stock/{sku}
stages:
  prod:
    provider:
      environment:
        DB_HOST: db.prod.internal.example.com
""",
          "app/__init__.py": "",
          "app/settings.py": FUTURE + """import os

DB_HOST = os.environ["DB_HOST"]
""",
          "app/stock.py": FUTURE + """from app import settings

STOCK = {"mug": 12}


def get(event, ctx):
    sku = event.http.path_params["sku"]
    ctx.logger.info("reading stock", extra={"db_host": settings.DB_HOST})
    return {"sku": sku, "in_stock": STOCK.get(sku, 0)}
""",
          "requirements.txt": ""}),
      user="stock works in prod but on staging every call is a 500 with KeyError: 'DB_HOST'. what is missing?",
      steps=[
          S("read_file", path="app/settings.py"),
          S("get_project"),
          S("invoke_local", function="stock", path="/stock/mug"),
          S("ask_user", question="DB_HOST is only set for the prod stage. Which database host should staging use?",
            options=["db.staging.internal.example.com", "the prod database"],
            answer="db.staging.internal.example.com"),
          S("propose_plan", steps=["Add `stages.staging.provider.environment.DB_HOST: db.staging.internal.example.com`",
                                   "GET /stock/mug on staging locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.staging.provider.environment.DB_HOST", value="db.staging.internal.example.com"),
          S("invoke_local", function="stock", path="/stock/mug"),
      ],
      final="""The code reads `DB_HOST` when app/settings.py is imported, and pskit.yml only sets it under `stages.prod`. On staging the variable doesn't exist, so the import fails and every request is a 500. I added it for staging: `stages.staging.provider.environment.DB_HOST: db.staging.internal.example.com` [docs/configuration.md#stages-per-stage-overrides].

- validate (onprem, staging): valid.
- GET /stock/mug: 200 `{"sku": "mug", "in_stock": 12}`, and the log line shows the staging host.

A new stage (for example `dev`) needs its own `DB_HOST` too."""),

    # ------------------------------------------------------------------ 345 onprem smtp, PDF sent as octet-stream
    B(345, provider="onprem", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": OP("ap-inbox", 8685) + """resources:
  invoices-mail:
    type: smtp
    external: true
    connection: {host: 192.0.2.43, port: 25, domains: ap.example.com}
functions:
  collect-invoices:
    handler: app.invoices.handle
    events:
      - smtp: invoices-mail
""",
          "app/__init__.py": "",
          "app/invoices.py": FUTURE + """
def handle(event, ctx):
    mail = event.data
    pdfs = [a["filename"] for a in mail["attachments"] if a["content_type"] == "application/pdf"]
    return {"from": mail["from"], "invoices": pdfs}
""",
          "requirements.txt": ""}),
      user="one supplier invoices never found. mail has invoice-118.pdf attached but invoices list is empty. other suppliers work",
      steps=[
          S("read_file", path="app/invoices.py"),
          S("invoke_local", function="collect-invoices", type="smtp",
            data={"from": "billing@supplier.example.org", "to": ["in@ap.example.com"], "subject": "Invoice 118",
                  "attachments": [{"filename": "invoice-118.pdf", "content_type": "application/octet-stream", "content": "%PDF-1.7"}]}),
          S("propose_plan", steps=["Accept an attachment as a PDF when its content type is application/pdf OR its file name ends in .pdf",
                                   "Invoke with the supplier's attachment; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/invoices.py", content=FUTURE + """
def is_pdf(att):
    return att["content_type"] == "application/pdf" or att["filename"].lower().endswith(".pdf")


def handle(event, ctx):
    mail = event.data
    pdfs = [a["filename"] for a in mail["attachments"] if is_pdf(a)]
    return {"from": mail["from"], "invoices": pdfs}
"""),
          S("invoke_local", function="collect-invoices", type="smtp",
            data={"from": "billing@supplier.example.org", "to": ["in@ap.example.com"], "subject": "Invoice 118",
                  "attachments": [{"filename": "invoice-118.pdf", "content_type": "application/octet-stream", "content": "%PDF-1.7"}]}),
          S("validate"),
      ],
      final="""That supplier's mail program sends the PDF as `application/octet-stream` (generic "binary file"), not `application/pdf`, so the exact type check skipped it. Now a `.pdf` file name counts too.

- Before: `"invoices": []`. After: `"invoices": ["invoice-118.pdf"]`.
- validate (onprem, prod): valid.

To be stricter, check that the decoded content starts with `%PDF` (`base64.b64decode(att["content"])`) [docs/smtp/README.md#what-the-handler-receives]."""),

    # ------------------------------------------------------------------ 346 onprem http, Node.js reduce without a start value
    B(346, provider="onprem", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": OP("basket-js", 8686, "  runtime: nodejs22\n") + """functions:
  basket-total:
    handler: src.basket.total
    events:
      - http: POST /basket/total
""",
          "src/basket.js": """exports.total = async (event) => {
  const { items } = event.http.json();
  const total = items.reduce((sum, item) => sum + item.price * item.qty);
  return { total };
};
"""}),
      user="""{"total": "[object Object]6"}
POST /basket/total with 2 items. what is object Object""",
      steps=[
          S("read_file", path="src/basket.js"),
          S("invoke_local", function="basket-total", method="POST", path="/basket/total",
            data={"items": [{"price": 4, "qty": 1}, {"price": 3, "qty": 2}]}),
          S("propose_plan", steps=["Give `reduce` a start value of `0`, so `sum` is a number and not the first item",
                                   "POST the 2 items and an empty basket locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/basket.js", content="""exports.total = async (event) => {
  const { items } = event.http.json();
  const total = items.reduce((sum, item) => sum + item.price * item.qty, 0);
  return { total };
};
"""),
          S("invoke_local", function="basket-total", method="POST", path="/basket/total",
            data={"items": [{"price": 4, "qty": 1}, {"price": 3, "qty": 2}]}),
          S("invoke_local", function="basket-total", method="POST", path="/basket/total", data={"items": []}),
          S("validate"),
      ],
      final="""Without a start value, `reduce` uses the **first item** (an object) as `sum`. Object + number turns into text: `"[object Object]" + 6`. With `0` as the start value the sum is a number, and an empty basket works too (it used to throw).

- 2 items: `{"total": 10}`.
- Empty basket: `{"total": 0}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 347 onprem queue, list.extend with a string
    B(347, provider="onprem", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": OP("labels", 8687) + """functions:
  collect-labels:
    handler: app.labels.handle
    events:
      - queue: label-events
""",
          "app/__init__.py": "",
          "app/labels.py": FUTURE + """
def handle(event, ctx):
    labels = []
    for record in event.records:
        msg = record.json()
        labels.extend(msg["label"])
    return {"labels": sorted(set(labels))}
""",
          "requirements.txt": ""}),
      user="I send labels like \"urgent\" and \"vip\" to the queue, and collect-labels returns single letters: e, g, i, n, p, r, t, u, v. I want the words.",
      steps=[
          S("read_file", path="app/labels.py"),
          S("invoke_local", function="collect-labels", type="queue", data=[{"label": "urgent"}, {"label": "vip"}]),
          S("propose_plan", steps=["Use `labels.append(...)` for one label (`extend` adds every character of a string)",
                                   "Invoke with the two labels; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/labels.py", content=FUTURE + """
def handle(event, ctx):
    labels = []
    for record in event.records:
        msg = record.json()
        labels.append(msg["label"])
    return {"labels": sorted(set(labels))}
"""),
          S("invoke_local", function="collect-labels", type="queue", data=[{"label": "urgent"}, {"label": "vip"}]),
          S("validate"),
      ],
      final="""`list.extend()` adds each item of what you give it, and the items of a string are its letters. `append()` adds the string as one item.

- Before: single letters. After: `{"labels": ["urgent", "vip"]}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 348 onprem schedule, last 7 days instead of last Monday-Sunday
    B(348, provider="onprem", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": OP("weekly-kpis", 8688) + """functions:
  weekly-report:
    handler: app.weekly.run
    events:
      - schedule: "0 7 * * 3"
""",
          "app/__init__.py": "",
          "app/weekly.py": FUTURE + """from datetime import date, timedelta


def run(event, ctx):
    today = date.fromisoformat((event.data or {}).get("today") or date.today().isoformat())
    start = today - timedelta(days=7)
    end = today - timedelta(days=1)
    return {"from": start.isoformat(), "to": end.isoformat()}
""",
          "requirements.txt": ""}),
      user="The weekly report runs on Wednesdays and must cover the last full calendar week, Monday to Sunday. For today = 2026-11-04 I expect 2026-10-26 to 2026-11-01, but it reports 2026-10-28 to 2026-11-03. The handler accepts {\"today\": \"YYYY-MM-DD\"}.",
      steps=[
          S("read_file", path="app/weekly.py"),
          S("invoke_local", function="weekly-report", type="schedule", data={"today": "2026-11-04"}),
          S("propose_plan", steps=["Find this week's Monday with `today - timedelta(days=today.weekday())`, then take the 7 days before it",
                                   "Run for 2026-11-04 and for a Monday (2026-11-02); validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/weekly.py", content=FUTURE + """from datetime import date, timedelta


def run(event, ctx):
    today = date.fromisoformat((event.data or {}).get("today") or date.today().isoformat())
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(days=7)
    end = this_monday - timedelta(days=1)
    return {"from": start.isoformat(), "to": end.isoformat()}
"""),
          S("invoke_local", function="weekly-report", type="schedule", data={"today": "2026-11-04"}),
          S("invoke_local", function="weekly-report", type="schedule", data={"today": "2026-11-02"}),
          S("validate"),
      ],
      final="""The old code took "the 7 days before today", which is a calendar week only when it runs on a Monday. Now it finds the Monday of the current week (`weekday()` is 0 for Monday) and reports the Monday-Sunday before it, whatever day it runs.

- 2026-11-04: `{"from": "2026-10-26", "to": "2026-11-01"}`.
- 2026-11-02 (a Monday): the same week.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 349 aws http, raw Lambda dict access on the Event
    B(349, provider="aws", stage="dev", mode="ask", page="Logs", persona="aws_migrator",
      sources=["docs/handlers.md#event", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AWS("signup", "us-east-1") + """functions:
  register:
    handler: app.signup.register
    events:
      - http: POST /signup
""",
          "app/__init__.py": "",
          "app/signup.py": FUTURE + """import json


def register(event, context):
    body = json.loads(event["body"])
    return {"statusCode": 201, "body": json.dumps({"email": body["email"]})}
""",
          "requirements.txt": ""}),
      user="I copied my Lambda handler over unchanged and POST /signup gives TypeError: 'Event' object is not subscriptable. It worked behind API Gateway for years.",
      steps=[
          S("read_file", path="app/signup.py"),
          S("invoke_local", function="register", method="POST", path="/signup", data={"email": "ana@example.com"}),
          S("search_docs", query="handler event http json returning response",
            docs=[D("docs/handlers.md", "event", words=120), D("docs/handlers.md", "returning-a-response", words=120)]),
          S("propose_plan", steps=["Read the body with `event.http.json()` (pskit passes an `Event` object, not the raw Lambda dict)",
                                   "Return `(body, 201)` instead of a hand-built `statusCode` dict",
                                   "POST /signup locally; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/signup.py", content=FUTURE + """
def register(event, ctx):
    body = event.http.json()
    return {"email": body["email"]}, 201
"""),
          S("invoke_local", function="register", method="POST", path="/signup", data={"email": "ana@example.com"}),
          S("validate"),
      ],
      final="""pskit doesn't pass the raw API Gateway dict. Your handler gets a portable `Event`, so `event["body"]` fails; the body is `event.http.json()` [docs/handlers.md#event]. You also don't build `statusCode`/`body` yourself: return a dict for 200, or `(body, status)` [docs/handlers.md#returning-a-response]. The same code then runs on every provider.

- POST /signup: 201 `{"email": "ana@example.com"}`.
- validate (aws): valid.

If you ever need the original Lambda event, it is in `event.raw` (that part isn't portable)."""),

    # ------------------------------------------------------------------ 350 aws queue, Node.js for...in over records
    B(350, provider="aws", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AWS("emails-js", "eu-west-1", "  runtime: nodejs20\n") + """functions:
  send-mails:
    handler: src.mails.handle
    events:
      - queue: outbound-mail
""",
          "src/mails.js": """const { BatchResult } = require("pskit");

exports.handle = async (event, ctx) => {
  const result = new BatchResult();
  for (const record in event.records) {
    const mail = record.json();
    if (!mail.to) result.fail(record);
    else ctx.logger.info("sending", { to: mail.to });
  }
  return result;
};
"""}),
      user="""TypeError: record.json is not a function
send-mails, every batch""",
      steps=[
          S("read_file", path="src/mails.js"),
          S("invoke_local", function="send-mails", type="queue", data=[{"to": "kim@example.com"}, {"subject": "no to"}]),
          S("propose_plan", steps=["Loop with `for (const record of event.records)`: `for...in` gives the indexes (\"0\", \"1\"), not the records",
                                   "Invoke with a good and a bad mail; validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/mails.js", content="""const { BatchResult } = require("pskit");

exports.handle = async (event, ctx) => {
  const result = new BatchResult();
  for (const record of event.records) {
    const mail = record.json();
    if (!mail.to) result.fail(record);
    else ctx.logger.info("sending", { to: mail.to });
  }
  return result;
};
"""),
          S("invoke_local", function="send-mails", type="queue", data=[{"to": "kim@example.com"}, {"subject": "no to"}]),
          S("validate"),
      ],
      final="""`for (const record in array)` walks the array's **keys**, so `record` was the string `"0"`, and strings have no `.json()`. `for...of` gives the items.

- After: one `sending` log line and `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}` for the mail without `to`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 351 aws http, a YAML mapping in environment becomes Python repr
    B(351, provider="aws", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": AWS("price-api", "us-east-2", "  environment:\n    PRICE_LIST: {mug: 8, cap: 5}\n") + """functions:
  price:
    handler: app.prices.get
    events:
      - http: GET /prices/{sku}
""",
          "app/__init__.py": "",
          "app/prices.py": FUTURE + """import json
import os

from py_serverless_kit import NotFound


def get(event, ctx):
    prices = json.loads(os.environ["PRICE_LIST"])
    sku = event.http.path_params["sku"]
    if sku not in prices:
        raise NotFound(f"no price for {sku}")
    return {"sku": sku, "price": prices[sku]}
""",
          "requirements.txt": ""}),
      user="I keep a small price list in provider.environment.PRICE_LIST and parse it with json.loads in the handler. Every request fails with JSONDecodeError: Expecting property name enclosed in double quotes. The YAML looks fine to me: PRICE_LIST: {mug: 8, cap: 5}.",
      steps=[
          S("read_file", path="app/prices.py"),
          S("invoke_local", function="price", path="/prices/mug"),
          S("search_docs", query="provider environment values strings",
            docs=[D("docs/configuration.md", "provider", start="| `environment`", words=20)]),
          S("propose_plan", steps=["Store PRICE_LIST as a JSON **string** in pskit.yml: `'{\"mug\": 8, \"cap\": 5}'`",
                                   "GET /prices/mug locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.environment.PRICE_LIST", value="{\"mug\": 8, \"cap\": 5}"),
          S("invoke_local", function="price", path="/prices/mug"),
      ],
      final="""Environment values are always converted to strings [docs/configuration.md#provider]. Your YAML mapping became the Python text `{'mug': 8, 'cap': 5}`, with single quotes, which isn't JSON. I wrote the value as a JSON string instead: `PRICE_LIST: '{"mug": 8, "cap": 5}'`. The handler didn't need changes.

- validate (aws, prod): valid.
- GET /prices/mug: `{"sku": "mug", "price": 8}`.

For a longer list, a file in the bundle (or a `custom` section read with `${self:custom...}` into a string) is easier to maintain."""),

    # ------------------------------------------------------------------ 352 aws http, str.title() capitalises after an apostrophe
    B(352, provider="aws", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": AWS("places", "ca-central-1") + """functions:
  add-place:
    handler: app.places.add
    events:
      - http: POST /places
""",
          "app/__init__.py": "",
          "app/places.py": FUTURE + """
def add(event, ctx):
    name = event.http.json()["name"].strip()
    return {"display_name": name.title()}, 201
""",
          "requirements.txt": ""}),
      user="restaurant name \"joe's diner\" show as \"Joe'S Diner\". the S is wrong, want \"Joe's Diner\"",
      steps=[
          S("read_file", path="app/places.py"),
          S("invoke_local", function="add-place", method="POST", path="/places", data={"name": "joe's diner"}),
          S("propose_plan", steps=["Use `string.capwords(name)`: it capitalises words split by spaces, `title()` also starts a new word after `'`",
                                   "POST \"joe's diner\" locally; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/places.py", content=FUTURE + """import string


def add(event, ctx):
    name = event.http.json()["name"].strip()
    return {"display_name": string.capwords(name)}, 201
"""),
          S("invoke_local", function="add-place", method="POST", path="/places", data={"name": "joe's diner"}),
          S("validate"),
      ],
      final="""`str.title()` starts a new word after every non-letter, also after `'`, so the `s` became `S`. `string.capwords()` only splits at spaces.

- Before: `Joe'S Diner`. After: 201 `{"display_name": "Joe's Diner"}`.
- validate (aws): valid.

Note that `capwords` also lowercases the rest of each word (`McDonald` becomes `Mcdonald`). If names are typed correctly, it's safer to store them as typed."""),

    # ------------------------------------------------------------------ 353 gcp http, unknown field in ?fields= gives 500
    B(353, provider="gcp", stage="staging", mode="ask", page="Logs", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": G("catalog", "europe-west2") + """functions:
  product:
    handler: app.products.get
    events:
      - http: GET /products/{id}
""",
          "app/__init__.py": "",
          "app/products.py": FUTURE + """from py_serverless_kit import NotFound

PRODUCTS = {"p1": {"id": "p1", "name": "Mug", "price": 8.0, "stock": 12}}


def get(event, ctx):
    product = PRODUCTS.get(event.http.path_params["id"])
    if product is None:
        raise NotFound("no such product")
    fields = event.http.query.get("fields")
    if fields:
        return {f: product[f] for f in fields.split(",")}
    return product
""",
          "requirements.txt": ""}),
      user="GET /products/p1?fields=name,colour -> 500 KeyError 'colour'. should be 400 listing valid fields",
      steps=[
          S("read_file", path="app/products.py"),
          S("invoke_local", function="product", path="/products/p1?fields=name,colour"),
          S("propose_plan", steps=["Check the requested fields against the product's keys and raise `BadRequest` naming the unknown ones and the valid ones",
                                   "GET with fields=name,colour (400) and fields=name,price (200); validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/products.py", content=FUTURE + """from py_serverless_kit import BadRequest, NotFound

PRODUCTS = {"p1": {"id": "p1", "name": "Mug", "price": 8.0, "stock": 12}}


def get(event, ctx):
    product = PRODUCTS.get(event.http.path_params["id"])
    if product is None:
        raise NotFound("no such product")
    fields = event.http.query.get("fields")
    if not fields:
        return product
    wanted = [f.strip() for f in fields.split(",") if f.strip()]
    unknown = [f for f in wanted if f not in product]
    if unknown:
        raise BadRequest(f"unknown fields: {', '.join(unknown)}; valid: {', '.join(product)}")
    return {f: product[f] for f in wanted}
"""),
          S("invoke_local", function="product", path="/products/p1?fields=name,colour"),
          S("invoke_local", function="product", path="/products/p1?fields=name,price"),
          S("validate"),
      ],
      final="""Each requested field was looked up with `product[f]`, so an unknown one raised KeyError (500). Unknown fields are now collected first and returned as a 400 [docs/handlers.md#errors].

- `fields=name,colour`: 400 `unknown fields: colour; valid: id, name, price, stock`.
- `fields=name,price`: 200 `{"name": "Mug", "price": 8.0}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 354 gcp queue, dedupe key depends on JSON key order
    B(354, provider="gcp", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": G("sensor-ingest", "us-central1") + """functions:
  ingest:
    handler: app.ingest.handle
    events:
      - queue: readings
""",
          "app/__init__.py": "",
          "app/ingest.py": FUTURE + """import json


def handle(event, ctx):
    seen, kept = set(), []
    for record in event.records:
        reading = record.json()
        key = json.dumps(reading)
        if key in seen:
            continue
        seen.add(key)
        kept.append(reading)
    return {"kept": len(kept)}
""",
          "requirements.txt": ""}),
      user="Two gateways forward the same sensor reading, so each reading arrives twice per batch. I dedupe on the JSON of the reading, but duplicates from different gateways are kept. A batch with one reading sent by both gateways should keep 1, I get 2. The only difference I can see is the field order.",
      steps=[
          S("read_file", path="app/ingest.py"),
          S("invoke_local", function="ingest", type="queue",
            data=[{"sensor": "s1", "ts": 1793484900, "value": 21.5}, {"value": 21.5, "sensor": "s1", "ts": 1793484900}]),
          S("propose_plan", steps=["Build the dedupe key with `json.dumps(reading, sort_keys=True)` so the field order doesn't matter",
                                   "Invoke with the same reading in two orders; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/ingest.py", content=FUTURE + """import json


def handle(event, ctx):
    seen, kept = set(), []
    for record in event.records:
        reading = record.json()
        key = json.dumps(reading, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        kept.append(reading)
    return {"kept": len(kept)}
"""),
          S("invoke_local", function="ingest", type="queue",
            data=[{"sensor": "s1", "ts": 1793484900, "value": 21.5}, {"value": 21.5, "sensor": "s1", "ts": 1793484900}]),
          S("validate"),
      ],
      final="""Right, it's the field order. `json.dumps` keeps the order the fields came in, so the two gateways produced two different strings for the same reading. `sort_keys=True` always writes the fields in the same order.

- Before: `{"kept": 2}`. After: `{"kept": 1}`.
- validate (gcp, prod): valid.

Deduping on `(sensor, ts)` would also catch duplicates whose values differ only in float formatting, if that can happen."""),

    # ------------------------------------------------------------------ 355 gcp storage, guess_type returns None for no extension
    B(355, provider="gcp", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": G("media-sort", "asia-northeast1") + """functions:
  sort-media:
    handler: app.sorter.handle
    events:
      - storage: media-inbox
""",
          "app/__init__.py": "",
          "app/sorter.py": FUTURE + """import mimetypes


def handle(event, ctx):
    images = []
    for record in event.records:
        if mimetypes.guess_type(record.key)[0].startswith("image/"):
            images.append(record.key)
    return {"images": images}
""",
          "requirements.txt": ""}),
      user="""AttributeError: 'NoneType' object has no attribute 'startswith'
sort-media, file "LICENSE" uploaded to media-inbox""",
      steps=[
          S("read_file", path="app/sorter.py"),
          S("invoke_local", function="sort-media", type="storage", data=[{"key": "cat.png"}, {"key": "LICENSE"}]),
          S("propose_plan", steps=["Treat an unknown type (`None`) as \"not an image\": `(guess_type(key)[0] or \"\")`",
                                   "Invoke with an image and a file without extension; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sorter.py", content=FUTURE + """import mimetypes


def handle(event, ctx):
    images = []
    for record in event.records:
        mime = mimetypes.guess_type(record.key)[0] or ""
        if mime.startswith("image/"):
            images.append(record.key)
    return {"images": images}
"""),
          S("invoke_local", function="sort-media", type="storage", data=[{"key": "cat.png"}, {"key": "LICENSE"}]),
          S("validate"),
      ],
      final="""`mimetypes.guess_type()` goes by the file extension and returns `(None, None)` when it can't tell, as with `LICENSE`. `None.startswith` then failed. An unknown type now counts as "not an image".

- After: `{"images": ["cat.png"]}`; LICENSE is skipped.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 356 gcp schedule, circular import through app/__init__.py
    B(356, provider="gcp", stage="staging", mode="ask", page="Code", persona="pasted_error",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": G("backup-jobs", "europe-west1") + """functions:
  nightly:
    handler: app.jobs.nightly
    events:
      - schedule: "0 1 * * *"
""",
          "app/__init__.py": FUTURE + """from app.jobs import nightly

VERSION = "1.4.0"
""",
          "app/jobs.py": FUTURE + """from app import VERSION


def nightly(event, ctx):
    return {"backup": "started", "version": VERSION}
""",
          "requirements.txt": ""}),
      user="""ImportError: cannot import name 'VERSION' from partially initialized module 'app' (most likely due to a circular import)
I only added `from app.jobs import nightly` to app/__init__.py so other scripts can import it shorter""",
      steps=[
          S("read_file", path="app/__init__.py"),
          S("invoke_local", function="nightly", type="schedule"),
          S("propose_plan", steps=["Put VERSION in its own module app/version.py, which imports nothing",
                                   "Import it from there in app/jobs.py, and in app/__init__.py define nothing before the re-export",
                                   "Run the schedule locally; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/version.py", content=FUTURE + """VERSION = "1.4.0"
"""),
          S("write_file", path="app/jobs.py", content=FUTURE + """from app.version import VERSION


def nightly(event, ctx):
    return {"backup": "started", "version": VERSION}
"""),
          S("write_file", path="app/__init__.py", content=FUTURE + """from app.jobs import nightly
from app.version import VERSION

__all__ = ["VERSION", "nightly"]
"""),
          S("invoke_local", function="nightly", type="schedule"),
          S("validate"),
      ],
      final="""Importing `app.jobs` first runs app/__init__.py. Its first line imports `app.jobs`, which asks for `VERSION` from `app`, but `VERSION` is only defined on the line after. I moved `VERSION` into app/version.py, a module that imports nothing from the app. Now `from app import nightly, VERSION` still works for your scripts.

- Before: ImportError.
- After: `{"backup": "started", "version": "1.4.0"}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 357 azure http, dd/mm/yyyy parser gets US dates
    B(357, provider="azure", stage="prod", mode="ask", page="Logs", persona="informal_non_native",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AZ("bookings-api", "westeurope") + """functions:
  availability:
    handler: app.availability.check
    events:
      - http: GET /availability
""",
          "app/__init__.py": "",
          "app/availability.py": FUTURE + """from datetime import datetime


def check(event, ctx):
    day = datetime.strptime(event.http.query["date"], "%d/%m/%Y").date()
    return {"date": day.isoformat(), "free_rooms": 3}
""",
          "requirements.txt": ""}),
      user="availability 500 for american customers. log: ValueError: time data '11/25/2026' does not match format '%d/%m/%Y'. how fix? we can tell the app team to send other format",
      steps=[
          S("read_file", path="app/availability.py"),
          S("invoke_local", function="availability", path="/availability?date=11/25/2026"),
          S("propose_plan", steps=["Accept one unambiguous format, ISO `YYYY-MM-DD`, and return 400 with an example for anything else",
                                   "GET with 2026-11-25 (200) and 11/25/2026 (400) locally; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/availability.py", content=FUTURE + """from datetime import date

from py_serverless_kit import BadRequest


def check(event, ctx):
    raw = event.http.query.get("date", "")
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        raise BadRequest("date must be YYYY-MM-DD, e.g. 2026-11-25") from None
    return {"date": day.isoformat(), "free_rooms": 3}
"""),
          S("invoke_local", function="availability", path="/availability?date=2026-11-25"),
          S("invoke_local", function="availability", path="/availability?date=11/25/2026"),
          S("validate"),
      ],
      final="""`11/25/2026` (month first) can't be read as day/month: there is no month 25. And `03/04/2026` would silently be read the wrong way. Since the app team can change the format, the API now takes only ISO dates (`YYYY-MM-DD`), which mean the same everywhere, and anything else is a clear 400 instead of a 500.

- `2026-11-25`: 200 `{"date": "2026-11-25", "free_rooms": 3}`.
- `11/25/2026`: 400 `date must be YYYY-MM-DD, e.g. 2026-11-25`.
- validate (azure, prod): valid.

Tell the app team about the format before you deploy this; old app versions will get 400."""),

    # ------------------------------------------------------------------ 358 azure schedule, shorthand dropped the input
    B(358, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("search-index", "northeurope") + """functions:
  reindex:
    handler: app.reindex.run
    events:
      - schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/reindex.py": FUTURE + """
def run(event, ctx):
    mode = event.data["mode"]
    return {"mode": mode, "full": mode == "full"}
""",
          "requirements.txt": ""}),
      user="reindex says TypeError: 'NoneType' object is not subscriptable since a colleague 'cleaned up' the trigger on the Functions page. it used to have mode incremental",
      steps=[
          S("read_file", path="app/reindex.py"),
          S("get_project"),
          S("invoke_local", function="reindex", type="schedule"),
          S("propose_plan", steps=["Turn the shorthand `- schedule: 1 hour` back into the long form with `input: {mode: incremental}`",
                                   "Run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.reindex.events.0", value={"schedule": {"rate": "1 hour", "input": {"mode": "incremental"}}}),
          S("invoke_local", function="reindex", type="schedule"),
      ],
      final="""The shorthand `- schedule: 1 hour` can't carry an `input`, so the cleanup removed it. Without input, `event.data` is `None`. I put the trigger back in the long form: `schedule: {rate: 1 hour, input: {mode: incremental}}` [docs/events.md#schedule].

- validate (azure): valid.
- Run: `{"mode": "incremental", "full": false}`.

If the handler should also survive a missing input, I can make it default to `incremental`."""),

    # ------------------------------------------------------------------ 359 azure http, "..." added to short names
    B(359, provider="azure", stage="staging", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": AZ("feed-cards", "eastus") + """functions:
  card:
    handler: app.cards.card
    events:
      - http: POST /cards
""",
          "app/__init__.py": "",
          "app/cards.py": FUTURE + """MAX = 20


def card(event, ctx):
    title = event.http.json()["title"]
    return {"title": title[:MAX] + "..."}
""",
          "requirements.txt": ""}),
      user="card titles: \"Short news\" -> \"Short news...\". only cut + ... when longer than 20",
      steps=[
          S("read_file", path="app/cards.py"),
          S("invoke_local", function="card", method="POST", path="/cards", data={"title": "Short news"}),
          S("propose_plan", steps=["Add `...` only when the title is longer than MAX; keep the result within MAX characters",
                                   "POST a short and a long title locally; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/cards.py", content=FUTURE + """MAX = 20


def shorten(text, limit=MAX):
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def card(event, ctx):
    return {"title": shorten(event.http.json()["title"])}
"""),
          S("invoke_local", function="card", method="POST", path="/cards", data={"title": "Short news"}),
          S("invoke_local", function="card", method="POST", path="/cards", data={"title": "Council approves the new tram line"}),
          S("validate"),
      ],
      final="""The `...` was appended unconditionally. `shorten()` returns titles up to 20 characters unchanged and otherwise cuts to 17 + `...`, so the card never exceeds 20.

- `Short news`: `Short news`.
- `Council approves the new tram line`: `Council approves...`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 360 aws queue, except ValueError around record.json()
    B(360, provider="aws", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/handlers.md#record", "docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": AWS("telemetry", "eu-north-1") + """functions:
  store-telemetry:
    handler: app.telemetry.handle
    events:
      - queue: telemetry
""",
          "app/__init__.py": "",
          "app/telemetry.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            point = record.json()
        except ValueError:
            ctx.logger.warning("bad message", extra={"message_id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("stored", extra={"device": point["device"]})
    return result
""",
          "requirements.txt": ""}),
      user="I wrap record.json() in try/except ValueError so a broken message is only marked as failed. Still, one truncated message (`{\"device\": \"d1\"`) makes the whole batch fail and every message gets retried. json.JSONDecodeError is a ValueError, so why doesn't my except catch it?",
      steps=[
          S("read_file", path="app/telemetry.py"),
          S("invoke_local", function="store-telemetry", type="queue", data=[{"device": "d1"}, "{\"device\": \"d2\""]),
          S("propose_plan", steps=["Catch `BadRequest` (what `record.json()` raises for invalid JSON) instead of `ValueError`",
                                   "Invoke with a good and a truncated message; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/telemetry.py", content=FUTURE + """from py_serverless_kit import BadRequest, BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            point = record.json()
        except BadRequest:
            ctx.logger.warning("bad message", extra={"message_id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("stored", extra={"device": point["device"]})
    return result
"""),
          S("invoke_local", function="store-telemetry", type="queue", data=[{"device": "d1"}, "{\"device\": \"d2\""]),
          S("validate"),
      ],
      final="""`record.json()` doesn't let the `JSONDecodeError` through: pskit raises its own `BadRequest` ("Record local-1 body is not valid JSON"), with the decode error as the cause. `BadRequest` is not a `ValueError`, so your `except` missed it and the exception failed the whole batch. Catching `BadRequest` marks only that message, and SQS retries just that one [docs/handlers.md#batchresult].

- After: `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`, with a `bad message` warning; d1 is stored.
- validate (aws, prod): valid.

If you'd rather catch `ValueError`, parse it yourself: `json.loads(record.text())`."""),
]
