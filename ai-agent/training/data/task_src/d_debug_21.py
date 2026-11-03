"""Category D (fix a handler bug), batch 21. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 401 onprem http, None compared with 0
    B(401, provider="onprem", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": OP("cart-svc", 8711) + """functions:
  add-item:
    handler: app.cart.add
    events:
      - http: POST /cart/items
""",
          "app/__init__.py": "",
          "app/cart.py": FUTURE + """from py_serverless_kit import BadRequest


def add(event, ctx):
    body = event.http.json()
    if not body.get("qty") > 0:
        raise BadRequest("qty must be positive")
    return {"sku": body["sku"], "qty": body["qty"]}, 201
""",
          "requirements.txt": ""}),
      user="""TypeError: '>' not supported between instances of 'NoneType' and 'int'
POST /cart/items without qty. should be 400 not 500""",
      steps=[
          S("read_file", path="app/cart.py"),
          S("invoke_local", function="add-item", method="POST", path="/cart/items", data={"sku": "mug"}),
          S("propose_plan", steps=["Check that `qty` is an int before comparing; missing or non-numeric gives 400",
                                   "POST without qty (400) and with qty 2 (201) locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/cart.py", content=FUTURE + """from py_serverless_kit import BadRequest


def add(event, ctx):
    body = event.http.json()
    qty = body.get("qty")
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        raise BadRequest("qty must be a positive whole number")
    return {"sku": body["sku"], "qty": qty}, 201
"""),
          S("invoke_local", function="add-item", method="POST", path="/cart/items", data={"sku": "mug"}),
          S("invoke_local", function="add-item", method="POST", path="/cart/items", data={"sku": "mug", "qty": 2}),
          S("validate"),
      ],
      final="""`body.get("qty")` is `None` when the field is missing, and `None > 0` raises TypeError (a 500). Now `qty` must be a real whole number above 0 (`true` doesn't count), otherwise 400.

- Without qty: 400 `qty must be a positive whole number`.
- qty 2: 201 `{"sku": "mug", "qty": 2}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 402 onprem queue, ascii encode of a name
    B(402, provider="onprem", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": OP("badge-printer", 8712) + """functions:
  print-badge:
    handler: app.badges.handle
    events:
      - queue: badges
""",
          "app/__init__.py": "",
          "app/badges.py": FUTURE + """
def handle(event, ctx):
    jobs = []
    for record in event.records:
        name = record.json()["name"]
        payload = name.encode("ascii")
        jobs.append({"name_bytes": len(payload)})
    return {"jobs": jobs}
""",
          "requirements.txt": ""}),
      user="The badge printer worker fails for some attendees; the log shows UnicodeEncodeError. I first thought the queue corrupts special characters, but the message in the queue looks fine. It happens for names like Zoë or José. The printer accepts UTF-8.",
      steps=[
          S("read_file", path="app/badges.py"),
          S("invoke_local", function="print-badge", type="queue", data=[{"name": "Ada"}, {"name": "Zoë"}]),
          S("propose_plan", steps=["Encode the name as UTF-8 (the printer accepts it); ASCII has no ë or é",
                                   "Invoke with Ada and Zoë; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/badges.py", content=FUTURE + """
def handle(event, ctx):
    jobs = []
    for record in event.records:
        name = record.json()["name"]
        payload = name.encode("utf-8")
        jobs.append({"name_bytes": len(payload)})
    return {"jobs": jobs}
"""),
          S("invoke_local", function="print-badge", type="queue", data=[{"name": "Ada"}, {"name": "Zoë"}]),
          S("validate"),
      ],
      final="""The queue is fine: the message arrives as `Zoë`. `name.encode("ascii")` can only encode the 128 ASCII characters, and `ë` isn't one of them. Encoding as UTF-8 handles every name.

- Before: `UnicodeEncodeError: 'ascii' codec can't encode character '\\xeb'`.
- After: `{"jobs": [{"name_bytes": 3}, {"name_bytes": 4}]}` (ë takes 2 bytes in UTF-8).
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 403 onprem schedule, Feb 29 anniversary
    B(403, provider="onprem", stage="staging", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": OP("member-club", 8713) + """functions:
  anniversaries:
    handler: app.members.next_anniversary
    events:
      - schedule:
          cron: "0 7 * * *"
          input: {joined: "2024-02-29", year: 2026}
""",
          "app/__init__.py": "",
          "app/members.py": FUTURE + """from datetime import date


def next_anniversary(event, ctx):
    joined = date.fromisoformat(event.data["joined"])
    return {"anniversary": joined.replace(year=event.data["year"]).isoformat()}
""",
          "requirements.txt": ""}),
      user="""ValueError: day is out of range for month
anniversaries, member who joined 2024-02-29""",
      steps=[
          S("read_file", path="app/members.py"),
          S("invoke_local", function="anniversaries", type="schedule"),
          S("propose_plan", steps=["When Feb 29 doesn't exist in the target year, use Feb 28",
                                   "Run for 2026 and with year 2028; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/members.py", content=FUTURE + """import calendar
from datetime import date


def same_day_in(day, year):
    if day.month == 2 and day.day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)
    return day.replace(year=year)


def next_anniversary(event, ctx):
    joined = date.fromisoformat(event.data["joined"])
    return {"anniversary": same_day_in(joined, event.data["year"]).isoformat()}
"""),
          S("invoke_local", function="anniversaries", type="schedule"),
          S("invoke_local", function="anniversaries", type="schedule", data={"joined": "2024-02-29", "year": 2028}),
          S("validate"),
      ],
      final="""2026 is not a leap year, so `replace(year=2026)` on 29 February asks for a date that doesn't exist. `same_day_in()` uses 28 February in non-leap years and keeps the 29th in leap years.

- 2026: `{"anniversary": "2026-02-28"}`.
- 2028: `{"anniversary": "2028-02-29"}`.
- validate (onprem, staging): valid.

Some clubs use 1 March instead; tell me if that's your rule."""),

    # ------------------------------------------------------------------ 404 onprem http, Node.js replace() only replaces the first match
    B(404, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": OP("contacts-js", 8714, "  runtime: nodejs22\n") + """functions:
  normalise-phone:
    handler: src.phone.normalise
    events:
      - http: POST /phone
""",
          "src/phone.js": """exports.normalise = async (event) => {
  const { phone } = event.http.json();
  return { phone: phone.replace("-", "").replace(" ", "") };
};
"""}),
      user="phone 555-010-0199 become 555010-0199. all dash must go",
      steps=[
          S("read_file", path="src/phone.js"),
          S("invoke_local", function="normalise-phone", method="POST", path="/phone", data={"phone": "555-010-0199"}),
          S("propose_plan", steps=["Remove every dash and space with a global regex: `phone.replace(/[\\s-]/g, \"\")`",
                                   "POST two numbers locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/phone.js", content="""exports.normalise = async (event) => {
  const { phone } = event.http.json();
  return { phone: String(phone).replace(/[\\s-]/g, "") };
};
"""),
          S("invoke_local", function="normalise-phone", method="POST", path="/phone", data={"phone": "555-010-0199"}),
          S("invoke_local", function="normalise-phone", method="POST", path="/phone", data={"phone": "+1 555 010 0199"}),
          S("validate"),
      ],
      final="""In JavaScript, `replace` with a **string** pattern replaces only the first match. A regex with the `g` flag replaces all of them; `[\\s-]` covers spaces and dashes.

- `555-010-0199`: `5550100199`.
- `+1 555 010 0199`: `+15550100199`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 405 onprem storage, empty file divides by zero
    B(405, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": OP("archiver", 8715) + """functions:
  compress-stats:
    handler: app.stats.handle
    events:
      - storage: archive-in
""",
          "app/__init__.py": "",
          "app/stats.py": FUTURE + """ESTIMATED_COMPRESSED = 4096


def handle(event, ctx):
    return {"files": [{"key": r.key, "ratio": round(ESTIMATED_COMPRESSED / r.size, 3)} for r in event.records]}
""",
          "requirements.txt": ""}),
      user="""ZeroDivisionError: division by zero
compress-stats, after someone uploaded an empty .keep file into archive-in""",
      steps=[
          S("read_file", path="app/stats.py"),
          S("invoke_local", function="compress-stats", type="storage",
            data=[{"key": "logs.tar", "size": 81920}, {"key": "data/.keep", "size": 0}]),
          S("propose_plan", steps=["Skip empty (size 0) and size-unknown files instead of dividing by their size",
                                   "Invoke with a normal and an empty file; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/stats.py", content=FUTURE + """ESTIMATED_COMPRESSED = 4096


def handle(event, ctx):
    files = []
    for r in event.records:
        if not r.size:
            ctx.logger.info("skipping empty file", extra={"key": r.key})
            continue
        files.append({"key": r.key, "ratio": round(ESTIMATED_COMPRESSED / r.size, 3)})
    return {"files": files}
"""),
          S("invoke_local", function="compress-stats", type="storage",
            data=[{"key": "logs.tar", "size": 81920}, {"key": "data/.keep", "size": 0}]),
          S("validate"),
      ],
      final="""An empty file has `size` 0, and the ratio divides by the size. Files with size 0 (or an unknown size, `None`) are now skipped with a log line.

- After: `{"files": [{"key": "logs.tar", "ratio": 0.05}]}`; `data/.keep` skipped.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 406 onprem smtp, order number regex doesn't match every subject
    B(406, provider="onprem", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": OP("order-mail", 8716) + """resources:
  orders-mail:
    type: smtp
    external: true
    connection: {host: 192.0.2.46, port: 25, domains: orders.example.com}
functions:
  link-order:
    handler: app.link.handle
    events:
      - smtp: orders-mail
""",
          "app/__init__.py": "",
          "app/link.py": FUTURE + """import re


def handle(event, ctx):
    subject = event.data["subject"]
    order = re.search(r"#(\\d+)", subject).group(1)
    return {"order": order}
""",
          "requirements.txt": ""}),
      user="""AttributeError: 'NoneType' object has no attribute 'group'
link-order, subject "Order 1182 arrived damaged". with "#1182" it works""",
      steps=[
          S("read_file", path="app/link.py"),
          S("invoke_local", function="link-order", type="smtp",
            data={"from": "c@example.org", "to": ["help@orders.example.com"], "subject": "Order 1182 arrived damaged", "text": "photo attached"}),
          S("propose_plan", steps=["Accept `#1182`, `Order 1182` and `order no. 1182` (case-insensitive) in the pattern",
                                   "When nothing matches, return `order: null` instead of crashing",
                                   "Invoke with three subjects; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/link.py", content=FUTURE + """import re

ORDER = re.compile(r"(?:#|\\border(?:\\s+no\\.?)?\\s*)(\\d{3,})", re.IGNORECASE)


def handle(event, ctx):
    match = ORDER.search(event.data["subject"] or "")
    if match is None:
        ctx.logger.info("no order number in subject")
    return {"order": match.group(1) if match else None}
"""),
          S("invoke_local", function="link-order", type="smtp",
            data={"from": "c@example.org", "to": ["help@orders.example.com"], "subject": "Order 1182 arrived damaged", "text": "photo attached"}),
          S("invoke_local", function="link-order", type="smtp",
            data={"from": "c@example.org", "to": ["help@orders.example.com"], "subject": "Re: #1183", "text": "thanks"}),
          S("invoke_local", function="link-order", type="smtp",
            data={"from": "c@example.org", "to": ["help@orders.example.com"], "subject": "Question", "text": "hello"}),
          S("validate"),
      ],
      final="""`re.search()` returns `None` when the pattern isn't found, and `None.group(1)` crashes. The subject had no `#`. The pattern now also accepts `Order 1182` / `order no. 1182`, and a mail without an order number returns `order: null` with a log line.

- `Order 1182 arrived damaged`: `{"order": "1182"}`.
- `Re: #1183`: `{"order": "1183"}`.
- `Question`: `{"order": null}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 407 onprem http, json.dumps returned as text/plain
    B(407, provider="onprem", stage="dev", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": OP("inventory", 8717) + """functions:
  stock-levels:
    handler: app.stock.levels
    events:
      - http: GET /stock
""",
          "app/__init__.py": "",
          "app/stock.py": FUTURE + """import json

LEVELS = {"mug": 12, "cap": 0}


def levels(event, ctx):
    return json.dumps({"levels": LEVELS})
""",
          "requirements.txt": ""}),
      user="Our frontend's fetch().json() call rejects the stock endpoint because the content type is text/plain. In Lambda I always returned json.dumps(...) in the body and that was JSON. How do I make it application/json here?",
      steps=[
          S("read_file", path="app/stock.py"),
          S("invoke_local", function="stock-levels", path="/stock"),
          S("propose_plan", steps=["Return the dict itself; pskit serialises it and sets `application/json`",
                                   "GET /stock locally and check the content type; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/stock.py", content=FUTURE + """LEVELS = {"mug": 12, "cap": 0}


def levels(event, ctx):
    return {"levels": LEVELS}
"""),
          S("invoke_local", function="stock-levels", path="/stock"),
          S("validate"),
      ],
      final="""In pskit a returned **str** is sent as `text/plain`, and a returned dict becomes JSON with `application/json` [docs/handlers.md#returning-a-response]. `json.dumps(...)` is a string, so it went out as text. Return the dict and pskit serialises it.

- Before: `content-type: text/plain; charset=utf-8`.
- After: `content-type: application/json`, body `{"levels": {"mug": 12, "cap": 0}}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 408 onprem http, night shift across midnight
    B(408, provider="onprem", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": OP("timesheets", 8718) + """functions:
  shift-hours:
    handler: app.shifts.hours
    events:
      - http: POST /shifts/hours
""",
          "app/__init__.py": "",
          "app/shifts.py": FUTURE + """from datetime import datetime


def hours(event, ctx):
    body = event.http.json()
    start = datetime.strptime(body["start"], "%H:%M")
    end = datetime.strptime(body["end"], "%H:%M")
    return {"hours": (end - start).total_seconds() / 3600}
""",
          "requirements.txt": ""}),
      user="Timesheets send start and end as HH:MM. Day shifts are fine, but the night shift from 22:00 to 06:00 comes out as -16 hours. It should be 8. Shifts are never longer than 24 hours.",
      steps=[
          S("read_file", path="app/shifts.py"),
          S("invoke_local", function="shift-hours", method="POST", path="/shifts/hours", data={"start": "22:00", "end": "06:00"}),
          S("propose_plan", steps=["When the end time is earlier than (or equal to) the start, the shift ends the next day: add 24 hours",
                                   "POST a night and a day shift locally; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/shifts.py", content=FUTURE + """from datetime import datetime, timedelta


def hours(event, ctx):
    body = event.http.json()
    start = datetime.strptime(body["start"], "%H:%M")
    end = datetime.strptime(body["end"], "%H:%M")
    if end <= start:
        end += timedelta(days=1)  # the shift ends the next day
    return {"hours": (end - start).total_seconds() / 3600}
"""),
          S("invoke_local", function="shift-hours", method="POST", path="/shifts/hours", data={"start": "22:00", "end": "06:00"}),
          S("invoke_local", function="shift-hours", method="POST", path="/shifts/hours", data={"start": "08:30", "end": "17:00"}),
          S("validate"),
      ],
      final="""With only HH:MM, both times are on the same (dummy) day, so 06:00 is before 22:00 and the difference is negative. An end at or before the start now means the next day.

- 22:00 to 06:00: `{"hours": 8.0}`.
- 08:30 to 17:00: `{"hours": 8.5}`.
- validate (onprem, prod): valid.

Note that a start equal to the end now counts as a 24-hour shift."""),

    # ------------------------------------------------------------------ 409 aws schedule, ", " in a comma-separated env value
    B(409, provider="aws", stage="prod", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": AWS("snapshot-audit", "us-east-1", "  environment:\n    REGIONS: us-east-1, eu-west-1\n") + """functions:
  audit:
    handler: app.audit.run
    events:
      - schedule: 1 day
""",
          "app/__init__.py": "",
          "app/audit.py": FUTURE + """import os

KNOWN = {"us-east-1", "eu-west-1", "ap-southeast-2"}


def run(event, ctx):
    regions = os.environ["REGIONS"].split(",")
    return {"checked": [r for r in regions if r in KNOWN], "skipped": [r for r in regions if r not in KNOWN]}
""",
          "requirements.txt": ""}),
      user="audit skips eu-west-1. REGIONS: us-east-1, eu-west-1",
      steps=[
          S("read_file", path="app/audit.py"),
          S("invoke_local", function="audit", type="schedule"),
          S("propose_plan", steps=["Strip spaces around each item after `split(\",\")` and drop empty items",
                                   "Run the schedule locally; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/audit.py", content=FUTURE + """import os

KNOWN = {"us-east-1", "eu-west-1", "ap-southeast-2"}


def run(event, ctx):
    regions = [r.strip() for r in os.environ["REGIONS"].split(",") if r.strip()]
    return {"checked": [r for r in regions if r in KNOWN], "skipped": [r for r in regions if r not in KNOWN]}
"""),
          S("invoke_local", function="audit", type="schedule"),
          S("validate"),
      ],
      final="""`"us-east-1, eu-west-1".split(",")` gives `" eu-west-1"` with a leading space, which isn't in `KNOWN`. Each item is stripped now.

- Before: skipped `[" eu-west-1"]`. After: `{"checked": ["us-east-1", "eu-west-1"], "skipped": []}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 410 aws http, Node.js toFixed returns a string
    B(410, provider="aws", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AWS("invoice-js", "eu-west-1", "  runtime: nodejs20\n") + """functions:
  invoice-total:
    handler: src.invoice.total
    events:
      - http: POST /invoice/total
""",
          "src/invoice.js": """exports.total = async (event) => {
  const { lines } = event.http.json();
  const net = lines.reduce((s, l) => s + l.price * l.qty, 0);
  return { net: net.toFixed(2), vat: (net * 0.2).toFixed(2) };
};
"""}),
      user="Our accounting client validates the invoice-total response against a schema where net and vat are numbers. It rejects ours because they are strings like \"12.50\". I only wanted two decimals.",
      steps=[
          S("read_file", path="src/invoice.js"),
          S("invoke_local", function="invoice-total", method="POST", path="/invoice/total",
            data={"lines": [{"price": 2.5, "qty": 5}]}),
          S("propose_plan", steps=["Round to 2 decimals as a number: `Math.round(x * 100) / 100` (`toFixed` returns a string)",
                                   "POST the same lines locally; validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/invoice.js", content="""const round2 = (x) => Math.round(x * 100) / 100;

exports.total = async (event) => {
  const { lines } = event.http.json();
  const net = lines.reduce((s, l) => s + l.price * l.qty, 0);
  return { net: round2(net), vat: round2(net * 0.2) };
};
"""),
          S("invoke_local", function="invoice-total", method="POST", path="/invoice/total",
            data={"lines": [{"price": 2.5, "qty": 5}]}),
          S("validate"),
      ],
      final="""`Number.prototype.toFixed()` returns a **string** formatted for display. `round2()` rounds to 2 decimals and keeps a number.

- Before: `{"net": "12.50", "vat": "2.50"}`. After: `{"net": 12.5, "vat": 2.5}`.
- validate (aws, staging): valid.

A JSON number never keeps trailing zeros (`12.5`, not `12.50`); showing two decimals is up to the client."""),

    # ------------------------------------------------------------------ 411 aws queue, str.format with a missing field
    B(411, provider="aws", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": AWS("welcome-mails", "eu-north-1") + """functions:
  render:
    handler: app.render.handle
    events:
      - queue: signups
""",
          "app/__init__.py": "",
          "app/render.py": FUTURE + """TEMPLATE = "Hi {name}, welcome to {company}!"


def handle(event, ctx):
    return {"mails": [TEMPLATE.format(**record.json()) for record in event.records]}
""",
          "requirements.txt": ""}),
      user="""KeyError: 'company'
render, for people who signed up without a company. whole batch fails""",
      steps=[
          S("read_file", path="app/render.py"),
          S("invoke_local", function="render", type="queue",
            data=[{"name": "Ana", "company": "Acme"}, {"name": "Bo"}]),
          S("propose_plan", steps=["Fill missing fields with defaults before formatting (`company` -> \"our community\")",
                                   "Invoke with and without company; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/render.py", content=FUTURE + """TEMPLATE = "Hi {name}, welcome to {company}!"
DEFAULTS = {"name": "there", "company": "our community"}


def handle(event, ctx):
    mails = []
    for record in event.records:
        fields = {**DEFAULTS, **{k: v for k, v in record.json().items() if v}}
        mails.append(TEMPLATE.format(**fields))
    return {"mails": mails}
"""),
          S("invoke_local", function="render", type="queue",
            data=[{"name": "Ana", "company": "Acme"}, {"name": "Bo"}]),
          S("validate"),
      ],
      final="""`str.format(**msg)` needs every `{field}` in the template, and Bo's message has no `company`. The fields are now merged over defaults first (an empty value also gets the default).

- Ana: `Hi Ana, welcome to Acme!`.
- Bo: `Hi Bo, welcome to our community!`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 412 aws http, page count with floor division
    B(412, provider="aws", stage="prod", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AWS("articles", "us-west-2") + """functions:
  list-articles:
    handler: app.articles.list_page
    events:
      - http: GET /articles
""",
          "app/__init__.py": "",
          "app/articles.py": FUTURE + """ARTICLES = [f"article-{i}" for i in range(1, 102)]
SIZE = 10


def list_page(event, ctx):
    page = int(event.http.query.get("page", "1"))
    items = ARTICLES[(page - 1) * SIZE:page * SIZE]
    return {"page": page, "pages": len(ARTICLES) // SIZE, "items": items}
""",
          "requirements.txt": ""}),
      user="We have 101 articles. The site says there are 10 pages, so nobody finds article-101 on page 11.",
      steps=[
          S("read_file", path="app/articles.py"),
          S("invoke_local", function="list-articles", path="/articles?page=11"),
          S("propose_plan", steps=["Round the page count up: `math.ceil(len(ARTICLES) / SIZE)`",
                                   "GET page 11 locally; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/articles.py", content=FUTURE + """import math

ARTICLES = [f"article-{i}" for i in range(1, 102)]
SIZE = 10


def list_page(event, ctx):
    page = int(event.http.query.get("page", "1"))
    items = ARTICLES[(page - 1) * SIZE:page * SIZE]
    return {"page": page, "pages": math.ceil(len(ARTICLES) / SIZE), "items": items}
"""),
          S("invoke_local", function="list-articles", path="/articles?page=11"),
          S("validate"),
      ],
      final="""`101 // 10` is 10: floor division drops the last, partly filled page. `math.ceil(101 / 10)` is 11.

- Page 11: before `"pages": 10`, now `{"page": 11, "pages": 11, "items": ["article-101"]}`.
- validate (aws, prod): valid."""),

    # ------------------------------------------------------------------ 413 gcp http, user input used as a regex
    B(413, provider="gcp", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": G("course-search", "europe-west1") + """functions:
  search:
    handler: app.search.find
    events:
      - http: GET /courses
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """import re

COURSES = ["Intro to C", "C++ for beginners", "Python basics"]


def find(event, ctx):
    pattern = re.compile(event.http.query.get("q", ""), re.IGNORECASE)
    return {"hits": [c for c in COURSES if pattern.search(c)]}
""",
          "requirements.txt": ""}),
      user="GET /courses?q=c%2B%2B (a search for c++) returns every course, even Python basics. Only the C++ course should match.",
      steps=[
          S("read_file", path="app/search.py"),
          S("invoke_local", function="search", path="/courses?q=c%2B%2B"),
          S("propose_plan", steps=["Search for the text literally with `re.escape(q)` (`+` is a regex operator)",
                                   "GET q=c++ and q=python locally; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/search.py", content=FUTURE + """import re

COURSES = ["Intro to C", "C++ for beginners", "Python basics"]


def find(event, ctx):
    pattern = re.compile(re.escape(event.http.query.get("q", "")), re.IGNORECASE)
    return {"hits": [c for c in COURSES if pattern.search(c)]}
"""),
          S("invoke_local", function="search", path="/courses?q=c%2B%2B"),
          S("invoke_local", function="search", path="/courses?q=python"),
          S("validate"),
      ],
      final="""The search text went straight into `re.compile`, so `c++` was read as a regular expression: `c` followed by a repeat operator. On Python 3.11+ that matches any `c`, so every course with a "c" was a hit; on 3.9/3.10 it is even an error (`multiple repeat`). `re.escape()` makes every character literal.

- `c++`: before all three courses, now `{"hits": ["C++ for beginners"]}`.
- `python`: `{"hits": ["Python basics"]}`.
- validate (gcp): valid.

A plain `q.lower() in course.lower()` would do the same job without regex."""),

    # ------------------------------------------------------------------ 414 gcp queue, publisher base64-encodes the JSON itself
    B(414, provider="gcp", stage="staging", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": G("legacy-bridge", "us-central1") + """functions:
  bridge:
    handler: app.bridge.handle
    events:
      - queue: legacy-events
""",
          "app/__init__.py": "",
          "app/bridge.py": FUTURE + """
def handle(event, ctx):
    return {"ids": [record.json()["id"] for record in event.records]}
""",
          "requirements.txt": ""}),
      user="A legacy publisher on legacy-events base64-encodes its JSON before publishing (an old habit from an SDK that didn't do it for us). Our worker fails with BadRequest: body is not valid JSON for those messages. New publishers send plain JSON. The worker must take both.",
      steps=[
          S("read_file", path="app/bridge.py"),
          S("invoke_local", function="bridge", type="queue", data=[{"id": 1}, "eyJpZCI6IDJ9"]),
          S("propose_plan", steps=["Try JSON first; if that fails, base64-decode the text and parse that",
                                   "Invoke with a plain and a base64 message; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/bridge.py", content=FUTURE + """import base64
import binascii
import json


def parse(record):
    text = record.text().strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return json.loads(base64.b64decode(text, validate=True))  # legacy publisher encodes twice
    except (binascii.Error, ValueError):
        raise ValueError(f"message {record.id} is neither JSON nor base64 JSON") from None


def handle(event, ctx):
    return {"ids": [parse(record)["id"] for record in event.records]}
"""),
          S("invoke_local", function="bridge", type="queue", data=[{"id": 1}, "eyJpZCI6IDJ9"]),
          S("validate"),
      ],
      final="""pskit already decodes the Pub/Sub transport encoding, so `record.text()` is what the publisher sent. The legacy publisher encodes a second time, so its body is base64 text, not JSON. `parse()` tries JSON first and then base64 + JSON; anything else still fails with a clear message.

- Plain `{"id": 1}` and base64 `eyJpZCI6IDJ9`: `{"ids": [1, 2]}`.
- validate (gcp, staging): valid.

Fixing the legacy publisher to send plain JSON is the long-term cure."""),

    # ------------------------------------------------------------------ 415 gcp schedule, groupby without sorting
    B(415, provider="gcp", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": G("team-report", "europe-west3") + """functions:
  hours-by-team:
    handler: app.report.run
    events:
      - schedule:
          cron: "0 18 * * 5"
          input:
            entries:
              - {team: ops, hours: 3}
              - {team: dev, hours: 5}
              - {team: ops, hours: 2}
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """from itertools import groupby


def run(event, ctx):
    entries = event.data["entries"]
    groups = [{"team": team, "hours": sum(e["hours"] for e in rows)}
              for team, rows in groupby(entries, key=lambda e: e["team"])]
    return {"teams": groups}
""",
          "requirements.txt": ""}),
      user="report show team ops two times (3 and 2). want ops once with 5",
      steps=[
          S("read_file", path="app/report.py"),
          S("invoke_local", function="hours-by-team", type="schedule"),
          S("propose_plan", steps=["Sort the entries by team before `groupby` (it only groups neighbours)",
                                   "Run with the configured entries; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/report.py", content=FUTURE + """from itertools import groupby


def run(event, ctx):
    entries = sorted(event.data["entries"], key=lambda e: e["team"])
    groups = [{"team": team, "hours": sum(e["hours"] for e in rows)}
              for team, rows in groupby(entries, key=lambda e: e["team"])]
    return {"teams": groups}
"""),
          S("invoke_local", function="hours-by-team", type="schedule"),
          S("validate"),
      ],
      final="""`itertools.groupby` only groups items that are **next to each other**. ops, dev, ops gave three groups. Sorting by team first puts all ops entries together.

- After: `{"teams": [{"team": "dev", "hours": 5}, {"team": "ops", "hours": 5}]}`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 416 gcp http, isalpha() rejects real names
    B(416, provider="gcp", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": G("signup-api", "asia-south1") + """functions:
  register:
    handler: app.register.create
    events:
      - http: POST /register
""",
          "app/__init__.py": "",
          "app/register.py": FUTURE + """from py_serverless_kit import BadRequest


def create(event, ctx):
    name = event.http.json().get("name", "")
    if not name.isalpha():
        raise BadRequest("name may only contain letters")
    return {"registered": name}, 201
""",
          "requirements.txt": ""}),
      user="Anne-Marie and Mary Jane can't register, they get \"name may only contain letters\". Their names are fine!",
      steps=[
          S("read_file", path="app/register.py"),
          S("invoke_local", function="register", method="POST", path="/register", data={"name": "Anne-Marie"}),
          S("propose_plan", steps=["Allow letters with single spaces, hyphens or apostrophes between them; still reject digits and empty names",
                                   "POST \"Anne-Marie\", \"Mary Jane\" and \"R2D2\" locally; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/register.py", content=FUTURE + """import re

from py_serverless_kit import BadRequest

NAME = re.compile(r"[^\\W\\d_]+(?:[ '-][^\\W\\d_]+)*")


def create(event, ctx):
    name = str(event.http.json().get("name", "")).strip()
    if not NAME.fullmatch(name):
        raise BadRequest("name may only contain letters, spaces, hyphens and apostrophes")
    return {"registered": name}, 201
"""),
          S("invoke_local", function="register", method="POST", path="/register", data={"name": "Anne-Marie"}),
          S("invoke_local", function="register", method="POST", path="/register", data={"name": "Mary Jane"}),
          S("invoke_local", function="register", method="POST", path="/register", data={"name": "R2D2"}),
          S("validate"),
      ],
      final="""`str.isalpha()` is true only when **every** character is a letter, so the hyphen and the space failed. The new check allows letters (any language) separated by single spaces, hyphens or apostrophes, and still rejects digits.

- `Anne-Marie`, `Mary Jane`: 201.
- `R2D2`: 400 `name may only contain letters, spaces, hyphens and apostrophes`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 417 azure http, height in cm in the BMI formula
    B(417, provider="azure", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AZ("health-calc", "westeurope") + """functions:
  bmi:
    handler: app.bmi.calc
    events:
      - http: POST /bmi
""",
          "app/__init__.py": "",
          "app/bmi.py": FUTURE + """
def calc(event, ctx):
    body = event.http.json()
    weight_kg, height_cm = float(body["weight_kg"]), float(body["height_cm"])
    return {"bmi": round(weight_kg / height_cm ** 2, 1)}
""",
          "requirements.txt": ""}),
      user="bmi for 70 kg 175 cm show 0.0. must be about 22.9",
      steps=[
          S("read_file", path="app/bmi.py"),
          S("invoke_local", function="bmi", method="POST", path="/bmi", data={"weight_kg": 70, "height_cm": 175}),
          S("propose_plan", steps=["Convert the height to metres before squaring (BMI is kg / m²)",
                                   "POST 70 kg / 175 cm locally; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/bmi.py", content=FUTURE + """
def calc(event, ctx):
    body = event.http.json()
    weight_kg, height_m = float(body["weight_kg"]), float(body["height_cm"]) / 100
    return {"bmi": round(weight_kg / height_m ** 2, 1)}
"""),
          S("invoke_local", function="bmi", method="POST", path="/bmi", data={"weight_kg": 70, "height_cm": 175}),
          S("validate"),
      ],
      final="""BMI uses the height in **metres**. With centimetres, 175² is 30625, and 70 / 30625 rounds to 0.0. The height is divided by 100 first.

- After: `{"bmi": 22.9}`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 418 azure queue, set.add() used in a condition
    B(418, provider="azure", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AZ("push-notify", "northeurope") + """functions:
  push:
    handler: app.push.handle
    events:
      - queue: push-requests
""",
          "app/__init__.py": "",
          "app/push.py": FUTURE + """
def handle(event, ctx):
    seen, sent = set(), []
    for record in event.records:
        device = record.json()["device"]
        if not seen.add(device):
            sent.append(device)
    return {"sent": sent}
""",
          "requirements.txt": ""}),
      user="A device must get at most one push per batch. The code adds each device to a set and only sends when it wasn't there yet, but a device that appears twice in a batch still gets two pushes.",
      steps=[
          S("read_file", path="app/push.py"),
          S("invoke_local", function="push", type="queue",
            data=[{"device": "d-1"}, {"device": "d-2"}, {"device": "d-1"}]),
          S("propose_plan", steps=["Check membership first (`if device in seen: continue`), then add; `set.add()` always returns None",
                                   "Invoke with a repeated device; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/push.py", content=FUTURE + """
def handle(event, ctx):
    seen, sent = set(), []
    for record in event.records:
        device = record.json()["device"]
        if device in seen:
            continue
        seen.add(device)
        sent.append(device)
    return {"sent": sent}
"""),
          S("invoke_local", function="push", type="queue",
            data=[{"device": "d-1"}, {"device": "d-2"}, {"device": "d-1"}]),
          S("validate"),
      ],
      final="""`set.add()` returns `None` whether or not the item was already there, so `not seen.add(device)` was always true. Now the code checks `device in seen` first and only then adds it.

- Before: `["d-1", "d-2", "d-1"]`. After: `{"sent": ["d-1", "d-2"]}`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 419 azure schedule, first Monday of the month
    B(419, provider="azure", stage="staging", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("board-meeting", "westeurope") + """functions:
  first-monday:
    handler: app.meeting.run
    events:
      - schedule: "0 6 1 * *"
""",
          "app/__init__.py": "",
          "app/meeting.py": FUTURE + """from datetime import date, timedelta


def run(event, ctx):
    data = event.data or {}
    first = date(data["year"], data["month"], 1)
    monday = first + timedelta(days=7 - first.weekday())
    return {"meeting": monday.isoformat()}
""",
          "requirements.txt": ""}),
      user="first-monday for 2026-06 gives 2026-06-08. June 1 2026 IS a monday",
      steps=[
          S("read_file", path="app/meeting.py"),
          S("invoke_local", function="first-monday", type="schedule", data={"year": 2026, "month": 6}),
          S("propose_plan", steps=["Use `(7 - first.weekday()) % 7` days, which is 0 when the 1st is already a Monday",
                                   "Run for June and November 2026; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/meeting.py", content=FUTURE + """from datetime import date, timedelta


def run(event, ctx):
    data = event.data or {}
    first = date(data["year"], data["month"], 1)
    monday = first + timedelta(days=(7 - first.weekday()) % 7)
    return {"meeting": monday.isoformat()}
"""),
          S("invoke_local", function="first-monday", type="schedule", data={"year": 2026, "month": 6}),
          S("invoke_local", function="first-monday", type="schedule", data={"year": 2026, "month": 11}),
          S("validate"),
      ],
      final="""When the 1st is a Monday, `weekday()` is 0 and `7 - 0` jumps a whole week. `% 7` turns that 7 into 0.

- June 2026: `{"meeting": "2026-06-01"}`.
- November 2026: `{"meeting": "2026-11-02"}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 420 azure http, env var name differs between config and code
    B(420, provider="azure", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": AZ("report-api", "uksouth") + """functions:
  send-report:
    handler: app.report.send
    environment:
      REPORT_MAIL: finance@example.com
    events:
      - http: POST /reports/send
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """import os


def send(event, ctx):
    to = os.environ.get("REPORT_EMAIL", "noreply@example.com")
    return {"queued_for": to}, 202
""",
          "requirements.txt": ""}),
      user="I set the report address to finance@example.com on the Functions page, but reports are queued for noreply@example.com. Is the setting not saved?",
      steps=[
          S("read_file", path="app/report.py"),
          S("invoke_local", function="send-report", method="POST", path="/reports/send", data={}),
          S("get_project"),
          S("propose_plan", steps=["Rename the variable in pskit.yml from REPORT_MAIL to REPORT_EMAIL, the name the code reads",
                                   "POST /reports/send locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send-report.environment", value={"REPORT_EMAIL": "finance@example.com"}),
          S("invoke_local", function="send-report", method="POST", path="/reports/send", data={}),
      ],
      final="""It is saved, under a different name. pskit.yml sets `REPORT_MAIL`, but the code reads `REPORT_EMAIL`, so it never found a value and used its default, `noreply@example.com`. I renamed the variable in the function's environment to `REPORT_EMAIL`.

- validate (azure, prod): valid.
- POST /reports/send: 202 `{"queued_for": "finance@example.com"}`.

You can see it on the Functions page under Environment variables."""),
]
