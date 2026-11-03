"""Category D (fix a handler bug), batch 22 (10 conversations). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 421 onprem http, zip code stored as an int
    B(421, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": OP("address-book", 8721) + """functions:
  save-address:
    handler: app.address.save
    events:
      - http: POST /addresses
""",
          "app/__init__.py": "",
          "app/address.py": FUTURE + """from py_serverless_kit import BadRequest


def save(event, ctx):
    body = event.http.json()
    try:
        zip_code = int(body["zip"])
    except (KeyError, ValueError):
        raise BadRequest("zip must be digits") from None
    return {"city": body["city"], "zip": zip_code}, 201
""",
          "requirements.txt": ""}),
      user="zip 01067 (Dresden) saved as 1067. the 0 is lost",
      steps=[
          S("read_file", path="app/address.py"),
          S("invoke_local", function="save-address", method="POST", path="/addresses", data={"city": "Dresden", "zip": "01067"}),
          S("propose_plan", steps=["Keep the zip code as text and only check that it is 4-10 digits; a number drops leading zeros",
                                   "POST 01067 (201) and 1A2 (400) locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/address.py", content=FUTURE + """import re

from py_serverless_kit import BadRequest

ZIP = re.compile(r"\\d{4,10}")


def save(event, ctx):
    body = event.http.json()
    zip_code = str(body.get("zip", "")).strip()
    if not ZIP.fullmatch(zip_code):
        raise BadRequest("zip must be 4-10 digits")
    return {"city": body["city"], "zip": zip_code}, 201
"""),
          S("invoke_local", function="save-address", method="POST", path="/addresses", data={"city": "Dresden", "zip": "01067"}),
          S("invoke_local", function="save-address", method="POST", path="/addresses", data={"city": "X", "zip": "1A2"}),
          S("validate"),
      ],
      final="""A zip code looks like a number but is really a code: `int("01067")` is 1067, and the leading zero is gone. It's now kept as text and only checked to be digits.

- `01067`: 201 `{"city": "Dresden", "zip": "01067"}`.
- `1A2`: 400 `zip must be 4-10 digits`.
- validate (onprem): valid.

Addresses already saved as numbers need a one-time fix (pad German zips to 5 digits)."""),

    # ------------------------------------------------------------------ 422 onprem queue, lambdas in a loop bind late
    B(422, provider="onprem", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": OP("thumb-jobs", 8722) + """functions:
  plan-jobs:
    handler: app.jobs.handle
    events:
      - queue: image-jobs
""",
          "app/__init__.py": "",
          "app/jobs.py": FUTURE + """
def handle(event, ctx):
    tasks = []
    for record in event.records:
        image = record.json()["image"]
        tasks.append(lambda: f"resize {image}")
    return {"planned": [task() for task in tasks]}
""",
          "requirements.txt": ""}),
      user="plan-jobs builds a small task (a lambda) per message and runs them at the end. With three images a.png, b.png, c.png every task says `resize c.png`. Each task should keep its own image.",
      steps=[
          S("read_file", path="app/jobs.py"),
          S("invoke_local", function="plan-jobs", type="queue",
            data=[{"image": "a.png"}, {"image": "b.png"}, {"image": "c.png"}]),
          S("propose_plan", steps=["Bind the current value when the lambda is created: `lambda image=image: ...`",
                                   "Invoke with three images; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/jobs.py", content=FUTURE + """
def handle(event, ctx):
    tasks = []
    for record in event.records:
        image = record.json()["image"]
        tasks.append(lambda image=image: f"resize {image}")
    return {"planned": [task() for task in tasks]}
"""),
          S("invoke_local", function="plan-jobs", type="queue",
            data=[{"image": "a.png"}, {"image": "b.png"}, {"image": "c.png"}]),
          S("validate"),
      ],
      final="""A lambda looks up `image` when it **runs**, not when it's created. All three ran after the loop, when `image` was `c.png`. A default argument (`image=image`) stores the value at creation time.

- Before: `resize c.png` three times. After: `resize a.png`, `resize b.png`, `resize c.png`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 423 onprem schedule, Node.js getMonth() is 0-based
    B(423, provider="onprem", stage="staging", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": OP("billing-js", 8723, "  runtime: nodejs22\n") + """functions:
  invoice-period:
    handler: src.period.label
    events:
      - schedule:
          cron: "0 3 1 * *"
          input: {day: "2026-11-01"}
""",
          "src/period.js": """exports.label = async (event) => {
  const d = new Date(event.data.day);
  const month = String(d.getUTCMonth()).padStart(2, "0");
  return { period: `${d.getUTCFullYear()}-${month}` };
};
"""}),
      user="invoice-period for 2026-11-01 -> 2026-10. january gives 2026-00",
      steps=[
          S("read_file", path="src/period.js"),
          S("invoke_local", function="invoice-period", type="schedule"),
          S("propose_plan", steps=["Add 1: `getUTCMonth()` counts months from 0 (January = 0)",
                                   "Run with the configured day and with 2026-01-15; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/period.js", content="""exports.label = async (event) => {
  const d = new Date(event.data.day);
  const month = String(d.getUTCMonth() + 1).padStart(2, "0");
  return { period: `${d.getUTCFullYear()}-${month}` };
};
"""),
          S("invoke_local", function="invoice-period", type="schedule"),
          S("invoke_local", function="invoice-period", type="schedule", data={"day": "2026-01-15"}),
          S("validate"),
      ],
      final="""JavaScript Date months are 0-based (`0` = January, `11` = December); days of the month are not. `getUTCMonth() + 1` gives the calendar month.

- 2026-11-01: `{"period": "2026-11"}`.
- 2026-01-15: `{"period": "2026-01"}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 424 onprem smtp, extension check is case-sensitive
    B(424, provider="onprem", stage="prod", mode="ask", page="Logs", persona="beginner",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": OP("cv-inbox", 8724) + """resources:
  jobs-mail:
    type: smtp
    external: true
    connection: {host: 192.0.2.47, port: 25, domains: jobs.example.com}
functions:
  collect-cv:
    handler: app.cv.handle
    events:
      - smtp: jobs-mail
""",
          "app/__init__.py": "",
          "app/cv.py": FUTURE + """ALLOWED = (".pdf", ".docx")


def handle(event, ctx):
    kept, rejected = [], []
    for att in event.data["attachments"]:
        (kept if att["filename"].endswith(ALLOWED) else rejected).append(att["filename"])
    return {"kept": kept, "rejected": rejected}
""",
          "requirements.txt": ""}),
      user="Some applicants' CVs are rejected although they are PDFs. The file names look like CV_Maria.PDF.",
      steps=[
          S("read_file", path="app/cv.py"),
          S("invoke_local", function="collect-cv", type="smtp",
            data={"from": "maria@example.org", "to": ["cv@jobs.example.com"], "subject": "Application",
                  "attachments": [{"filename": "CV_Maria.PDF", "content_type": "application/pdf", "content": "%PDF-1.7"}]}),
          S("propose_plan", steps=["Compare the extension in lower case: `att[\"filename\"].lower().endswith(ALLOWED)`",
                                   "Invoke with CV_Maria.PDF and notes.txt; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/cv.py", content=FUTURE + """ALLOWED = (".pdf", ".docx")


def handle(event, ctx):
    kept, rejected = [], []
    for att in event.data["attachments"]:
        (kept if att["filename"].lower().endswith(ALLOWED) else rejected).append(att["filename"])
    return {"kept": kept, "rejected": rejected}
"""),
          S("invoke_local", function="collect-cv", type="smtp",
            data={"from": "maria@example.org", "to": ["cv@jobs.example.com"], "subject": "Application",
                  "attachments": [{"filename": "CV_Maria.PDF", "content_type": "application/pdf", "content": "%PDF-1.7"},
                                  {"filename": "notes.txt", "content_type": "text/plain", "content": "hi"}]}),
          S("validate"),
      ],
      final="""`endswith(".pdf")` is case-sensitive, and `CV_Maria.PDF` ends in `.PDF`. The file name is now lower-cased before the check (the original name is kept in the result).

- Before: `CV_Maria.PDF` rejected.
- After: `{"kept": ["CV_Maria.PDF"], "rejected": ["notes.txt"]}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 425 aws http, path traversal in a template name
    B(425, provider="aws", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AWS("mail-preview", "eu-west-1") + """functions:
  preview:
    handler: app.preview.render
    events:
      - http: GET /preview
""",
          "app/__init__.py": "",
          "app/preview.py": FUTURE + """from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render(event, ctx):
    name = event.http.query.get("template", "welcome.html")
    return (ROOT / "templates" / name).read_text(encoding="utf-8")
""",
          "templates/welcome.html": "<h1>Welcome!</h1>\n",
          "config/app.ini": "[db]\nhost = db.internal.example.com\n",
          "requirements.txt": ""}),
      user="A security scan flagged GET /preview?template=... as path traversal. I don't see how: the file is always read from templates/. Can you check, and fix it if it's real?",
      steps=[
          S("read_file", path="app/preview.py"),
          S("invoke_local", function="preview", path="/preview?template=../config/app.ini"),
          S("propose_plan", steps=["Accept only plain template names (`[a-z0-9-]+.html`) and return 404 for anything else",
                                   "Also check that the resolved path is still inside templates/",
                                   "GET welcome.html (200) and ../config/app.ini (404) locally; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/preview.py", content=FUTURE + """import re
from pathlib import Path

from py_serverless_kit import NotFound

TEMPLATES = (Path(__file__).resolve().parent.parent / "templates").resolve()
NAME = re.compile(r"[a-z0-9-]+\\.html")


def render(event, ctx):
    name = event.http.query.get("template", "welcome.html")
    path = (TEMPLATES / name).resolve()
    if not NAME.fullmatch(name) or path.parent != TEMPLATES or not path.is_file():
        raise NotFound("no such template")
    return path.read_text(encoding="utf-8")
"""),
          S("invoke_local", function="preview", path="/preview?template=welcome.html"),
          S("invoke_local", function="preview", path="/preview?template=../config/app.ini"),
          S("validate"),
      ],
      final="""It's real. `templates / "../config/app.ini"` walks out of templates/, and the first invoke above returned config/app.ini from the bundle. Anything in the deployment package (code, config) could be read that way. Now only plain names like `welcome.html` are accepted, and the resolved path must sit directly in templates/; everything else is a 404.

- `welcome.html`: 200 `<h1>Welcome!</h1>`.
- `../config/app.ini`: 404 `no such template`.
- validate (aws, prod): valid.

Since the deployed version could leak files, deploy this soon (Deploy page or `pskit deploy -s prod`), and check that nothing sensitive was in the bundle."""),

    # ------------------------------------------------------------------ 426 aws schedule, %U week number vs ISO week
    B(426, provider="aws", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AWS("sprint-report", "us-east-2") + """functions:
  week-label:
    handler: app.week.run
    events:
      - schedule: "0 6 * * 1"
""",
          "app/__init__.py": "",
          "app/week.py": FUTURE + """from datetime import date


def run(event, ctx):
    day = date.fromisoformat((event.data or {}).get("day") or date.today().isoformat())
    return {"label": day.strftime("%Y-W%U")}
""",
          "requirements.txt": ""}),
      user="""{"label": "2026-W00"}
for day 2026-01-01. our planning tool says that is week 1 (ISO weeks)""",
      steps=[
          S("read_file", path="app/week.py"),
          S("invoke_local", function="week-label", type="schedule", data={"day": "2026-01-01"}),
          S("propose_plan", steps=["Use the ISO calendar: `day.isocalendar()` gives the ISO year and week (weeks start on Monday)",
                                   "Run for 2026-01-01 and 2027-01-01; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/week.py", content=FUTURE + """from datetime import date


def run(event, ctx):
    day = date.fromisoformat((event.data or {}).get("day") or date.today().isoformat())
    iso_year, iso_week, _ = day.isocalendar()
    return {"label": f"{iso_year}-W{iso_week:02d}"}
"""),
          S("invoke_local", function="week-label", type="schedule", data={"day": "2026-01-01"}),
          S("invoke_local", function="week-label", type="schedule", data={"day": "2027-01-01"}),
          S("validate"),
      ],
      final="""`%U` counts weeks starting on Sunday, and days before the first Sunday are week 00. ISO weeks start on Monday, and week 1 is the week with the year's first Thursday. `isocalendar()` gives the ISO week **and** the ISO year, which can differ from the calendar year around New Year.

- 2026-01-01: `{"label": "2026-W01"}`.
- 2027-01-01: `{"label": "2026-W53"}` (it still belongs to the last ISO week of 2026).
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 427 gcp http, float checked with range()
    B(427, provider="gcp", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": G("ratings", "europe-west1") + """functions:
  rate:
    handler: app.rate.submit
    events:
      - http: POST /ratings
""",
          "app/__init__.py": "",
          "app/rate.py": FUTURE + """from py_serverless_kit import BadRequest


def submit(event, ctx):
    stars = event.http.json()["stars"]
    if stars not in range(1, 6):
        raise BadRequest("stars must be between 1 and 5")
    return {"stars": stars}, 201
""",
          "requirements.txt": ""}),
      user="half stars 4.5 is rejected 'stars must be between 1 and 5'. 4.5 is between!",
      steps=[
          S("read_file", path="app/rate.py"),
          S("invoke_local", function="rate", method="POST", path="/ratings", data={"stars": 4.5}),
          S("propose_plan", steps=["Check `1 <= stars <= 5` for numbers and allow only whole or half stars",
                                   "POST 4.5 (201), 4.3 and 6 (400) locally; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/rate.py", content=FUTURE + """from py_serverless_kit import BadRequest


def submit(event, ctx):
    stars = event.http.json().get("stars")
    if isinstance(stars, bool) or not isinstance(stars, (int, float)):
        raise BadRequest("stars must be a number")
    if not 1 <= stars <= 5 or (stars * 2) % 1:
        raise BadRequest("stars must be between 1 and 5, in half steps")
    return {"stars": stars}, 201
"""),
          S("invoke_local", function="rate", method="POST", path="/ratings", data={"stars": 4.5}),
          S("invoke_local", function="rate", method="POST", path="/ratings", data={"stars": 4.3}),
          S("invoke_local", function="rate", method="POST", path="/ratings", data={"stars": 6}),
          S("validate"),
      ],
      final="""`range(1, 6)` contains only the whole numbers 1, 2, 3, 4, 5, so `4.5 in range(1, 6)` is False. Now it checks `1 <= stars <= 5` and allows whole or half stars only.

- 4.5: 201 `{"stars": 4.5}`.
- 4.3 and 6: 400 `stars must be between 1 and 5, in half steps`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 428 gcp queue, :.2f on a string price
    B(428, provider="gcp", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": G("price-alerts", "us-central1") + """functions:
  price-drop:
    handler: app.alerts.handle
    events:
      - queue: price-changes
""",
          "app/__init__.py": "",
          "app/alerts.py": FUTURE + """
def handle(event, ctx):
    lines = []
    for record in event.records:
        change = record.json()
        lines.append(f"{change['sku']} now {change['price']:.2f}")
    return {"alerts": lines}
""",
          "requirements.txt": ""}),
      user="""ValueError: Unknown format code 'f' for object of type 'str'
price-drop. the new shop system sends price as "9.5" in quotes""",
      steps=[
          S("read_file", path="app/alerts.py"),
          S("invoke_local", function="price-drop", type="queue",
            data=[{"sku": "mug", "price": 7.99}, {"sku": "cap", "price": "9.5"}]),
          S("propose_plan", steps=["Convert the price with `float()` before formatting, so numbers and numeric strings both work",
                                   "Invoke with a number and a string price; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/alerts.py", content=FUTURE + """
def handle(event, ctx):
    lines = []
    for record in event.records:
        change = record.json()
        lines.append(f"{change['sku']} now {float(change['price']):.2f}")
    return {"alerts": lines}
"""),
          S("invoke_local", function="price-drop", type="queue",
            data=[{"sku": "mug", "price": 7.99}, {"sku": "cap", "price": "9.5"}]),
          S("validate"),
      ],
      final="""The format spec `:.2f` works only on numbers, and `"9.5"` is a string. `float()` first turns either form into a number.

- After: `{"alerts": ["mug now 7.99", "cap now 9.50"]}`.
- validate (gcp): valid.

A price that isn't a number at all would still fail the whole batch; tell me if I should skip and log those instead."""),

    # ------------------------------------------------------------------ 429 azure http, seconds passed as minutes
    B(429, provider="azure", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AZ("download-links", "westeurope") + """functions:
  make-link:
    handler: app.links.make
    events:
      - http: POST /links
""",
          "app/__init__.py": "",
          "app/links.py": FUTURE + """from datetime import datetime, timedelta


def make(event, ctx):
    body = event.http.json()
    created = datetime.fromisoformat(body["created"])
    expires = created + timedelta(minutes=body["ttl_seconds"])
    return {"file": body["file"], "expires": expires.isoformat()}
""",
          "requirements.txt": ""}),
      user="Download links get `ttl_seconds` from the client (900 = 15 minutes). A link created at 10:00 expires at 01:00 on the next day instead of 10:15. The handler takes \"created\" in the body so we can test with fixed times.",
      steps=[
          S("read_file", path="app/links.py"),
          S("invoke_local", function="make-link", method="POST", path="/links",
            data={"file": "report.pdf", "created": "2026-11-01T10:00:00", "ttl_seconds": 900}),
          S("propose_plan", steps=["Pass the value as `timedelta(seconds=...)`; it was given as minutes",
                                   "POST the same link locally; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/links.py", content=FUTURE + """from datetime import datetime, timedelta


def make(event, ctx):
    body = event.http.json()
    created = datetime.fromisoformat(body["created"])
    expires = created + timedelta(seconds=body["ttl_seconds"])
    return {"file": body["file"], "expires": expires.isoformat()}
"""),
          S("invoke_local", function="make-link", method="POST", path="/links",
            data={"file": "report.pdf", "created": "2026-11-01T10:00:00", "ttl_seconds": 900}),
          S("validate"),
      ],
      final="""`timedelta(minutes=900)` is 15 **hours**. The field is in seconds, so it must be `timedelta(seconds=...)`.

- Before: expires `2026-11-02T01:00:00`. After: `{"file": "report.pdf", "expires": "2026-11-01T10:15:00"}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 430 azure schedule, fixed top-3 indexes on a short list
    B(430, provider="azure", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("sales-digest", "northeurope") + """functions:
  top-sellers:
    handler: app.digest.run
    events:
      - schedule:
          cron: "0 7 * * 1"
          input:
            sales: [{rep: kim, total: 900}, {rep: lee, total: 700}]
""",
          "app/__init__.py": "",
          "app/digest.py": FUTURE + """
def run(event, ctx):
    top = sorted(event.data["sales"], key=lambda s: s["total"], reverse=True)
    return {"gold": top[0]["rep"], "silver": top[1]["rep"], "bronze": top[2]["rep"]}
""",
          "requirements.txt": ""}),
      user="""IndexError: list index out of range
top-sellers, the week only 2 reps had sales""",
      steps=[
          S("read_file", path="app/digest.py"),
          S("invoke_local", function="top-sellers", type="schedule"),
          S("propose_plan", steps=["Fill the medals from the sorted list with `zip`, so missing places are simply `null`",
                                   "Run with the 2-rep input; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/digest.py", content=FUTURE + """MEDALS = ("gold", "silver", "bronze")


def run(event, ctx):
    top = sorted(event.data["sales"], key=lambda s: s["total"], reverse=True)
    result = dict.fromkeys(MEDALS)
    for medal, sale in zip(MEDALS, top):
        result[medal] = sale["rep"]
    return result
"""),
          S("invoke_local", function="top-sellers", type="schedule"),
          S("validate"),
      ],
      final="""`top[2]` assumes at least three reps with sales. With two, it doesn't exist. `zip(MEDALS, top)` stops at the shorter list, so missing places stay `null`.

- 2 reps: `{"gold": "kim", "silver": "lee", "bronze": null}`.
- validate (azure, prod): valid."""),
]
