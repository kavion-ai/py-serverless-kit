"""Category D (fix a handler bug), batch 16. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
  options:
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


def G(service, region="europe-west1"):
    return f"service: {service}\n" + GCP.format(region=region)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 301 onprem http, circular import between two modules
    B(301, provider="onprem", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": OP("shop-orders", 8661) + """functions:
  create-order:
    handler: app.orders.create
    events:
      - http: POST /orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """from app.pricing import price_for

TAX_RATE = 0.2


def create(event, ctx):
    body = event.http.json()
    return {"sku": body["sku"], "total": price_for(body["sku"], body.get("qty", 1))}, 201
""",
          "app/pricing.py": FUTURE + """from app.orders import TAX_RATE

PRICES = {"mug": 8.0, "shirt": 20.0}


def price_for(sku, qty):
    return round(PRICES[sku] * qty * (1 + TAX_RATE), 2)
""",
          "requirements.txt": ""}),
      user="""ImportError: cannot import name 'TAX_RATE' from partially initialized module 'app.orders' (most likely due to a circular import)
after I moved the price code into app/pricing.py""",
      steps=[
          S("read_file", path="app/orders.py"),
          S("read_file", path="app/pricing.py"),
          S("invoke_local", function="create-order", method="POST", path="/orders", data={"sku": "mug", "qty": 2}),
          S("propose_plan", steps=["Move `TAX_RATE` into app/pricing.py (the only module that uses it) and drop the import of app.orders there",
                                   "Remove `TAX_RATE` from app/orders.py, so the import goes one way only (orders -> pricing)",
                                   "POST /orders locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/pricing.py", content=FUTURE + """TAX_RATE = 0.2
PRICES = {"mug": 8.0, "shirt": 20.0}


def price_for(sku, qty):
    return round(PRICES[sku] * qty * (1 + TAX_RATE), 2)
"""),
          S("write_file", path="app/orders.py", content=FUTURE + """from app.pricing import price_for


def create(event, ctx):
    body = event.http.json()
    return {"sku": body["sku"], "total": price_for(body["sku"], body.get("qty", 1))}, 201
"""),
          S("invoke_local", function="create-order", method="POST", path="/orders", data={"sku": "mug", "qty": 2}),
          S("validate"),
      ],
      final="""The two modules imported each other. Loading `app.orders` starts with `from app.pricing import ...`, and app/pricing.py then asks for `TAX_RATE` from `app.orders`, which hasn't got that far yet. I moved `TAX_RATE` into app/pricing.py, the module that uses it. Now the import only goes one way: orders imports pricing.

- Before: ImportError on every request.
- After: 201 `{"sku": "mug", "total": 19.2}`.
- validate (onprem): valid.

If other modules need shared constants later, put them in a small module (for example app/settings.py) that imports nothing from your app."""),

    # ------------------------------------------------------------------ 302 onprem http, slug helper in another module
    B(302, provider="onprem", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": OP("blog-api", 8662) + """functions:
  create-post:
    handler: app.posts.create
    events:
      - http: POST /posts
""",
          "app/__init__.py": "",
          "app/posts.py": FUTURE + """from app.text import slugify


def create(event, ctx):
    body = event.http.json()
    return {"title": body["title"], "slug": slugify(body["title"])}, 201
""",
          "app/text.py": FUTURE + """import re


def slugify(title):
    return re.sub(r"\\W", "-", title.lower())
""",
          "requirements.txt": ""}),
      user="POST /posts returns 201 but the slugs are ugly. For the title \"Hello, World!\" I expect `hello-world` and I get `hello--world-`. Slugs should be lowercase letters and digits separated by single dashes, with no dash at the start or end.",
      steps=[
          S("read_file", path="app/posts.py"),
          S("read_file", path="app/text.py"),
          S("invoke_local", function="create-post", method="POST", path="/posts", data={"title": "Hello, World!"}),
          S("propose_plan", steps=["In app/text.py, replace each run of non-alphanumeric characters with one dash and strip dashes at both ends",
                                   "POST two titles locally; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/text.py", content=FUTURE + """import re


def slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
"""),
          S("invoke_local", function="create-post", method="POST", path="/posts", data={"title": "Hello, World!"}),
          S("invoke_local", function="create-post", method="POST", path="/posts", data={"title": "  pskit 2.10 -- what's new?  "}),
          S("validate"),
      ],
      final="""The bug is in the helper, app/text.py. `re.sub(r"\\W", "-", ...)` replaces **each** non-word character with its own dash, so `, ` became `--` and `!` a trailing `-`. The new pattern `[^a-z0-9]+` turns each run of other characters into a single dash, and `.strip("-")` removes dashes at the ends. app/posts.py didn't change.

- `Hello, World!`: `hello-world`.
- `  pskit 2.10 -- what's new?  `: `pskit-2-10-what-s-new`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 303 onprem queue, user blames the DLQ config; loop variable after the loop
    B(303, provider="onprem", stage="prod", mode="ask", page="Logs", persona="informal_non_native",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": OP("billing", 8663) + """functions:
  book-invoice:
    handler: app.invoices.handle
    events:
      - queue:
          name: invoices
          dead_letter: invoices-dlq
          max_receive: 3
""",
          "app/__init__.py": "",
          "app/invoices.py": FUTURE + """from py_serverless_kit import BatchResult


def book(invoice):
    if invoice["amount"] <= 0:
        raise ValueError("amount must be positive")
    return invoice["id"]


def handle(event, ctx):
    result = BatchResult()
    failed = False
    for record in event.records:
        try:
            book(record.json())
        except ValueError as exc:
            ctx.logger.warning("rejected", extra={"error": str(exc)})
            failed = True
    if failed:
        result.fail(record)
    return result
""",
          "requirements.txt": ""}),
      user="good invoice end in invoices-dlq and the bad one (amount -5) is gone. i think dead_letter or max_receive is configured wrong?",
      steps=[
          S("get_project"),
          S("read_file", path="app/invoices.py"),
          S("invoke_local", function="book-invoice", type="queue",
            data=[{"id": "inv-1", "amount": -5}, {"id": "inv-2", "amount": 40}]),
          S("propose_plan", steps=["Keep the queue config as it is (dead_letter and max_receive are fine)",
                                   "Call `result.fail(record)` inside the `except`, for the record that failed, instead of after the loop",
                                   "Invoke with a bad and a good invoice; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/invoices.py", content=FUTURE + """from py_serverless_kit import BatchResult


def book(invoice):
    if invoice["amount"] <= 0:
        raise ValueError("amount must be positive")
    return invoice["id"]


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            book(record.json())
        except ValueError as exc:
            ctx.logger.warning("rejected", extra={"message_id": record.id, "error": str(exc)})
            result.fail(record)
    return result
"""),
          S("invoke_local", function="book-invoice", type="queue",
            data=[{"id": "inv-1", "amount": -5}, {"id": "inv-2", "amount": 40}]),
          S("validate"),
      ],
      final="""The config is fine; the handler reported the wrong message. `result.fail(record)` ran **after** the loop, and by then `record` is always the last message in the batch. So the good inv-2 was retried and dead-lettered, and the bad inv-1 counted as done and was deleted. Now each failed record is reported inside the `except` [docs/handlers.md#batchresult].

- Before: `local-1` (inv-2, the good one) failed.
- After: `{"batchItemFailures": [{"itemIdentifier": "local-0"}]}` (inv-1). It goes to `invoices-dlq` after 3 tries.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 304 onprem smtp, auto-reply adds Re: to a reply
    B(304, provider="onprem", stage="prod", mode="ask", page="Code", persona="beginner",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": OP("helpdesk-mail", 8664) + """resources:
  inbound-mail:
    type: smtp
    external: true
    connection: {host: 192.0.2.41, port: 25, domains: help.example.com}
functions:
  auto-reply:
    handler: app.autoreply.handle
    events:
      - smtp: inbound-mail
""",
          "app/__init__.py": "",
          "app/autoreply.py": FUTURE + """
def handle(event, ctx):
    mail = event.data
    reply = {
        "to": mail["from"],
        "subject": "Re: " + mail["subject"],
        "text": "Thanks, we got your mail. A ticket number follows.",
    }
    return {"reply": reply}
""",
          "requirements.txt": ""}),
      user="when customer answer to a mail, our auto reply subject become \"Re: Re: Order late\". i want only one Re:",
      steps=[
          S("read_file", path="app/autoreply.py"),
          S("invoke_local", function="auto-reply", type="smtp",
            data={"from": "kim@example.org", "to": ["help@help.example.com"], "subject": "Re: Order late", "text": "still waiting"}),
          S("propose_plan", steps=["Add `Re: ` only when the subject doesn't already start with `re:` (any case)",
                                   "Invoke with `Re: Order late` and `Order late`; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/autoreply.py", content=FUTURE + """
def reply_subject(subject):
    subject = (subject or "").strip()
    if subject.lower().startswith("re:"):
        return subject
    return "Re: " + subject


def handle(event, ctx):
    mail = event.data
    reply = {
        "to": mail["from"],
        "subject": reply_subject(mail["subject"]),
        "text": "Thanks, we got your mail. A ticket number follows.",
    }
    return {"reply": reply}
"""),
          S("invoke_local", function="auto-reply", type="smtp",
            data={"from": "kim@example.org", "to": ["help@help.example.com"], "subject": "Re: Order late", "text": "still waiting"}),
          S("invoke_local", function="auto-reply", type="smtp",
            data={"from": "kim@example.org", "to": ["help@help.example.com"], "subject": "Order late", "text": "where is it"}),
          S("validate"),
      ],
      final="""The code always put `Re: ` in front, even when the customer's subject already had it. Now `reply_subject()` adds it only when the subject doesn't start with `re:` (`RE:` too).

- `Re: Order late`: reply subject `Re: Order late`.
- `Order late`: reply subject `Re: Order late`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 305 onprem workflow task returns an HTTP-style tuple
    B(305, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#data-flow", "docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": OP("checkout-flow", 8665) + """functions:
  check-order:
    handler: app.flow.check
  charge:
    handler: app.flow.charge
workflows:
  checkout:
    start_at: Check
    states:
      Check: {type: task, function: check-order, next: Charge}
      Charge: {type: task, function: charge, end: true}
""",
          "app/__init__.py": "",
          "app/flow.py": FUTURE + """
def check(event, ctx):
    order = event.data
    if not order.get("items"):
        return {"ok": False, "reason": "empty order"}, 400
    return {"ok": True, "order": order}, 200


def charge(event, ctx):
    order = event.data["order"]
    return {"charged": sum(i["price"] * i["qty"] for i in order["items"])}
""",
          "requirements.txt": ""}),
      user="""checkout workflow, Charge step:
TypeError: list indices must be integers or slices, not str
Check works fine when I call it alone (I reused the code from our HTTP version)""",
      steps=[
          S("read_file", path="app/flow.py"),
          S("invoke_local", function="check-order", type="workflow",
            data={"id": "o-1", "items": [{"price": 4.5, "qty": 2}]}),
          S("propose_plan", steps=["Make `check` return only the data (no `(body, status)` tuple, which is an HTTP thing)",
                                   "For an empty order, raise an error so the workflow fails at Check",
                                   "Invoke check-order and charge with workflow data; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/flow.py", content=FUTURE + """
class EmptyOrder(Exception):
    pass


def check(event, ctx):
    order = event.data
    if not order.get("items"):
        raise EmptyOrder("empty order")
    return {"ok": True, "order": order}


def charge(event, ctx):
    order = event.data["order"]
    return {"charged": sum(i["price"] * i["qty"] for i in order["items"])}
"""),
          S("invoke_local", function="check-order", type="workflow",
            data={"id": "o-1", "items": [{"price": 4.5, "qty": 2}]}),
          S("invoke_local", function="charge", type="workflow",
            data={"ok": True, "order": {"id": "o-1", "items": [{"price": 4.5, "qty": 2}]}}),
          S("validate"),
      ],
      final="""`(body, status)` is a response shape for **HTTP** functions [docs/handlers.md#returning-a-response]. A workflow task's return value is passed on as data, so Check handed Charge a list, `[{...}, 200]`, and `event.data["order"]` failed on it. Check now returns just the dict. An empty order raises `EmptyOrder` instead of returning a 400, so the workflow fails at Check (you can add a `catch` on `EmptyOrder` later).

- check-order: `{"ok": true, "order": {...}}`.
- charge with that: `{"charged": 9.0}`.
- validate (onprem): valid. To run the whole thing: Deploy > Run a workflow locally, or `pskit workflow run checkout -i '{"id": "o-1", "items": [{"price": 4.5, "qty": 2}]}'`."""),

    # ------------------------------------------------------------------ 306 onprem http, config points at the old handler
    B(306, provider="onprem", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": OP("health-api", 8666) + """functions:
  status:
    handler: app.api.status_v1
    events:
      - http: GET /status
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """import os


def status_v1(event, ctx):
    return {"status": "ok"}


def status(event, ctx):
    return {"status": "ok", "service": ctx.service, "stage": ctx.stage,
            "version": os.environ.get("APP_VERSION", "dev")}
""",
          "requirements.txt": ""}),
      user="i added service, stage and version to my status function but GET /status still shows only status ok. i saved the file!",
      steps=[
          S("read_file", path="app/api.py"),
          S("invoke_local", function="status", path="/status"),
          S("get_project"),
          S("propose_plan", steps=["Point `functions.status.handler` at the new function `app.api.status` (it still says `status_v1`)",
                                   "GET /status locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.status.handler", value="app.api.status"),
          S("invoke_local", function="status", path="/status"),
      ],
      final="""Your file is fine. The problem is in pskit.yml: the function's handler was still `app.api.status_v1`, the old function, so your new `status` code never ran. I changed `functions.status.handler` to `app.api.status`.

- validate (onprem, staging): valid.
- GET /status: `{"status": "ok", "service": "health-api", "stage": "staging", "version": "dev"}`. `version` is `dev` because `APP_VERSION` isn't set.

You can check the handler on Functions > status > Basics > Handler. Delete `status_v1` when nothing uses it."""),

    # ------------------------------------------------------------------ 307 onprem http, Node.js sort() on numbers
    B(307, provider="onprem", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": OP("leaderboard", 8667, "  runtime: nodejs20\n") + """functions:
  top-scores:
    handler: src.scores.top
    events:
      - http: POST /scores/top
""",
          "src/scores.js": """exports.top = async (event) => {
  const { scores } = event.http.json();
  const sorted = scores.sort().reverse();
  return { top3: sorted.slice(0, 3) };
};
"""}),
      user="top3 for [9,100,25,7,80] gives [9,80,7]. expected [100,80,25]",
      steps=[
          S("read_file", path="src/scores.js"),
          S("invoke_local", function="top-scores", method="POST", path="/scores/top", data={"scores": [9, 100, 25, 7, 80]}),
          S("propose_plan", steps=["Sort numerically, descending, with a compare function on a copy: `[...scores].sort((a, b) => b - a)`",
                                   "POST the same scores locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/scores.js", content="""exports.top = async (event) => {
  const { scores } = event.http.json();
  const sorted = [...scores].sort((a, b) => b - a);
  return { top3: sorted.slice(0, 3) };
};
"""),
          S("invoke_local", function="top-scores", method="POST", path="/scores/top", data={"scores": [9, 100, 25, 7, 80]}),
          S("validate"),
      ],
      final="""`Array.prototype.sort()` without a compare function sorts as **strings**: `"100" < "25" < "7" < "80" < "9"`. Now `(a, b) => b - a` sorts numbers, highest first. The copy (`[...scores]`) also keeps the input array unchanged.

- Before: `[9, 80, 7]`. After: `{"top3": [100, 80, 25]}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 308 onprem queue, plain-text messages from an old producer
    B(308, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": OP("search-sync", 8668) + """functions:
  reindex:
    handler: app.reindex.handle
    events:
      - queue: reindex
""",
          "app/__init__.py": "",
          "app/reindex.py": FUTURE + """
def handle(event, ctx):
    done = []
    for record in event.records:
        job = record.json()
        done.append(f"{job['index']}:{job['doc_id']}")
    return {"reindexed": done}
""",
          "requirements.txt": ""}),
      user="""From the Logs page, function reindex:
  File "/srv/pskit/search-sync/app/reindex.py", line 7, in handle
    job = record.json()
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
The old cron script still pushes plain text like products:42, the new service sends JSON.""",
      steps=[
          S("read_file", path="app/reindex.py"),
          S("invoke_local", function="reindex", type="queue",
            data=[{"index": "products", "doc_id": 7}, "products:42"]),
          S("propose_plan", steps=["Parse `record.text()` with `json.loads`; when that raises `ValueError`, read the text as `<index>:<doc_id>`",
                                   "Invoke with one JSON and one plain-text message; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/reindex.py", content=FUTURE + """import json


def parse_job(record):
    text = record.text().strip()
    try:
        return json.loads(text)
    except ValueError:
        index, _, doc_id = text.partition(":")
        return {"index": index, "doc_id": doc_id}


def handle(event, ctx):
    done = []
    for record in event.records:
        job = parse_job(record)
        done.append(f"{job['index']}:{job['doc_id']}")
    return {"reindexed": done}
"""),
          S("invoke_local", function="reindex", type="queue",
            data=[{"index": "products", "doc_id": 7}, "products:42"]),
          S("validate"),
      ],
      final="""`record.json()` parses the body as JSON, and `products:42` isn't JSON. pskit turns that into `BadRequest: Record local-1 body is not valid JSON`, and the whole batch failed. `parse_job()` now reads `record.text()` [docs/handlers.md#record], tries `json.loads` (its `JSONDecodeError` is a `ValueError`), and otherwise splits the text at the first `:`.

- Before: JSONDecodeError traceback.
- After: `{"reindexed": ["products:7", "products:42"]}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 309 aws http, relative import beyond the package
    B(309, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": AWS("rate-limits", "eu-central-1") + """functions:
  limits:
    handler: app.api.limits
    events:
      - http: GET /limits/{plan}
""",
          "app/__init__.py": "",
          "app/settings.py": FUTURE + """LIMITS = {"free": 100, "pro": 10000}
""",
          "app/api.py": FUTURE + """from py_serverless_kit import NotFound

from ..settings import LIMITS


def limits(event, ctx):
    plan = event.http.path_params["plan"]
    if plan not in LIMITS:
        raise NotFound(f"no plan {plan}")
    return {"plan": plan, "requests_per_day": LIMITS[plan]}
""",
          "requirements.txt": ""}),
      user="In my old Lambda everything was flat in one folder. Now settings.py and api.py are both in app/, and `from ..settings import LIMITS` gives \"ImportError: attempted relative import beyond top-level package\". Isn't .. the current folder?",
      steps=[
          S("read_file", path="app/api.py"),
          S("invoke_local", function="limits", path="/limits/pro"),
          S("propose_plan", steps=["Use `from .settings import LIMITS` (one dot = the same package, app)",
                                   "GET /limits/pro locally; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/api.py", content=FUTURE + """from py_serverless_kit import NotFound

from .settings import LIMITS


def limits(event, ctx):
    plan = event.http.path_params["plan"]
    if plan not in LIMITS:
        raise NotFound(f"no plan {plan}")
    return {"plan": plan, "requests_per_day": LIMITS[plan]}
"""),
          S("invoke_local", function="limits", path="/limits/pro"),
          S("validate"),
      ],
      final="""No: in a relative import **one** dot is the current package (`app`), and two dots are its parent. `app` is the top-level package of your bundle, so `..` points outside it. `from .settings import LIMITS` (or `from app.settings import LIMITS`) imports app/settings.py.

- GET /limits/pro: `{"plan": "pro", "requests_per_day": 10000}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 310 aws schedule, user blames the cron; replace(day=0) on the 1st
    B(310, provider="aws", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AWS("daily-report", "us-west-2") + """functions:
  yesterday-report:
    handler: app.report.run
    events:
      - schedule: "0 6 * * *"
""",
          "app/__init__.py": "",
          "app/report.py": FUTURE + """from datetime import date


def run(event, ctx):
    data = event.data or {}
    today = date.fromisoformat(data["date"]) if data.get("date") else date.today()
    yesterday = today.replace(day=today.day - 1)
    return {"report_for": yesterday.isoformat()}
""",
          "requirements.txt": ""}),
      user="yesterday-report failed this morning (Nov 1) and also on Oct 1, but runs every other day. I suspect the cron `0 6 * * *` is evaluated in UTC and hits some edge at the month change. The handler accepts {\"date\": \"YYYY-MM-DD\"} for re-runs; 2026-11-01 reproduces it.",
      steps=[
          S("read_file", path="app/report.py"),
          S("invoke_local", function="yesterday-report", type="schedule", data={"date": "2026-11-01"}),
          S("propose_plan", steps=["Keep the cron (it isn't the cause)",
                                   "Compute yesterday with `today - timedelta(days=1)` instead of `replace(day=today.day - 1)`",
                                   "Run for 2026-11-01 and 2026-03-01; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/report.py", content=FUTURE + """from datetime import date, timedelta


def run(event, ctx):
    data = event.data or {}
    today = date.fromisoformat(data["date"]) if data.get("date") else date.today()
    yesterday = today - timedelta(days=1)
    return {"report_for": yesterday.isoformat()}
"""),
          S("invoke_local", function="yesterday-report", type="schedule", data={"date": "2026-11-01"}),
          S("invoke_local", function="yesterday-report", type="schedule", data={"date": "2026-03-01"}),
          S("validate"),
      ],
      final="""The cron is fine; the date math breaks on the 1st. `today.replace(day=today.day - 1)` asks for day **0** of the month, and `date` raises `ValueError: day is out of range for month`. Subtracting a `timedelta(days=1)` crosses month and year ends correctly.

- 2026-11-01: `{"report_for": "2026-10-31"}`.
- 2026-03-01: `{"report_for": "2026-02-28"}`.
- validate (aws, prod): valid.

(The cron does run in UTC on AWS, but that only changes *when* it runs, not this error.)"""),

    # ------------------------------------------------------------------ 311 aws http, Node.js forEach with an async callback
    B(311, provider="aws", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AWS("quote-js", "eu-west-1", "  runtime: nodejs20\n") + """functions:
  quote:
    handler: src.quote.quote
    events:
      - http: POST /quote
""",
          "src/quote.js": """async function priceOf(sku) {
  return { mug: 8, shirt: 20 }[sku] ?? 0;
}

exports.quote = async (event) => {
  const { items } = event.http.json();
  let total = 0;
  items.forEach(async (item) => {
    total += (await priceOf(item.sku)) * item.qty;
  });
  return { total };
};
"""}),
      user="quote total is always 0 in javascript. 2 mug + 1 shirt should be 36",
      steps=[
          S("read_file", path="src/quote.js"),
          S("invoke_local", function="quote", method="POST", path="/quote",
            data={"items": [{"sku": "mug", "qty": 2}, {"sku": "shirt", "qty": 1}]}),
          S("propose_plan", steps=["Replace `forEach(async ...)` with a `for...of` loop that awaits each price",
                                   "POST 2 mugs + 1 shirt locally; validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/quote.js", content="""async function priceOf(sku) {
  return { mug: 8, shirt: 20 }[sku] ?? 0;
}

exports.quote = async (event) => {
  const { items } = event.http.json();
  let total = 0;
  for (const item of items) {
    total += (await priceOf(item.sku)) * item.qty;
  }
  return { total };
};
"""),
          S("invoke_local", function="quote", method="POST", path="/quote",
            data={"items": [{"sku": "mug", "qty": 2}, {"sku": "shirt", "qty": 1}]}),
          S("validate"),
      ],
      final="""`forEach` doesn't wait for `async` callbacks. It starts them all and returns at once, so `return { total }` ran while total was still 0. A `for...of` loop with `await` waits for each price.

- Before: `{"total": 0}`. After: `{"total": 36}`.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 312 aws storage, helper unpacks a nested key
    B(312, provider="aws", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AWS("tenant-files", "us-east-1") + """functions:
  ingest:
    handler: app.ingest.handle
    events:
      - storage: tenant-uploads
""",
          "app/__init__.py": "",
          "app/keys.py": FUTURE + """
def parse_key(key):
    tenant, filename = key.split("/")
    return tenant, filename
""",
          "app/ingest.py": FUTURE + """from app.keys import parse_key


def handle(event, ctx):
    out = []
    for record in event.records:
        tenant, filename = parse_key(record.key)
        out.append({"tenant": tenant, "file": filename})
    return {"files": out}
""",
          "requirements.txt": ""}),
      user="""ValueError: too many values to unpack (expected 2)
  File "app/keys.py", line 4, in parse_key
ingest, key acme/2026/11/report.csv. acme/report.csv works.""",
      steps=[
          S("read_file", path="app/keys.py"),
          S("invoke_local", function="ingest", type="storage", data=[{"key": "acme/2026/11/report.csv"}]),
          S("propose_plan", steps=["Split only at the first `/`: `key.split(\"/\", 1)` (tenant, then the rest of the path)",
                                   "Invoke with a nested and a flat key; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/keys.py", content=FUTURE + """
def parse_key(key):
    tenant, path = key.split("/", 1)
    return tenant, path
"""),
          S("invoke_local", function="ingest", type="storage",
            data=[{"key": "acme/2026/11/report.csv"}, {"key": "acme/report.csv"}]),
          S("validate"),
      ],
      final="""`key.split("/")` gives one item per path part: `acme/2026/11/report.csv` is 4 parts, but `tenant, filename = ...` expects exactly 2. `split("/", 1)` splits only at the first slash, so you always get the tenant and the rest of the path.

- `acme/2026/11/report.csv`: tenant `acme`, file `2026/11/report.csv`.
- `acme/report.csv`: tenant `acme`, file `report.csv`.
- validate (aws, prod): valid.

A key without any `/` would still fail. Tell me if uploads can land at the bucket root, and I'll handle that too."""),

    # ------------------------------------------------------------------ 313 gcp http, list used as a dict key for some inputs
    B(313, provider="gcp", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": G("tagger") + """functions:
  group-by-tag:
    handler: app.tags.group
    events:
      - http: POST /group
""",
          "app/__init__.py": "",
          "app/tags.py": FUTURE + """
def group(event, ctx):
    groups = {}
    for item in event.http.json()["items"]:
        groups.setdefault(item["tag"], []).append(item["id"])
    return {"groups": groups}
""",
          "requirements.txt": ""}),
      user="""TypeError: unhashable type: 'list'
only some requests to POST /group. the new mobile client sends "tag": ["red", "sale"] for items with several tags, the web client sends "tag": "red\"""",
      steps=[
          S("read_file", path="app/tags.py"),
          S("invoke_local", function="group-by-tag", method="POST", path="/group",
            data={"items": [{"id": 1, "tag": "red"}, {"id": 2, "tag": ["red", "sale"]}]}),
          S("propose_plan", steps=["Accept `tag` as a string or a list, and add the item to every tag in it",
                                   "POST a mixed body locally; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tags.py", content=FUTURE + """
def group(event, ctx):
    groups = {}
    for item in event.http.json()["items"]:
        tags = item["tag"] if isinstance(item["tag"], list) else [item["tag"]]
        for tag in tags:
            groups.setdefault(tag, []).append(item["id"])
    return {"groups": groups}
"""),
          S("invoke_local", function="group-by-tag", method="POST", path="/group",
            data={"items": [{"id": 1, "tag": "red"}, {"id": 2, "tag": ["red", "sale"]}]}),
          S("validate"),
      ],
      final="""Dict keys must be hashable, and a list isn't. So the mobile client's `["red", "sale"]` failed as a key, while plain strings worked. Now a single tag is treated as a one-item list, and the item is added under each of its tags.

- Mixed body: `{"groups": {"red": [1, 2], "sale": [2]}}`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 314 gcp queue, user blames Pub/Sub; dict.update overwrites
    B(314, provider="gcp", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": G("stock-moves", "us-central1") + """functions:
  tally:
    handler: app.tally.handle
    events:
      - queue: stock-moves
""",
          "app/__init__.py": "",
          "app/tally.py": FUTURE + """
def handle(event, ctx):
    counts = {}
    for record in event.records:
        move = record.json()
        counts.update({move["sku"]: move["qty"]})
    return {"counts": counts}
""",
          "requirements.txt": ""}),
      user="The tally worker sums stock moves per SKU for each batch. With two moves for `mug` (2 and 3) and one for `cap` (1) in a batch, I get mug 3 instead of 5. My guess is that Pub/Sub drops or merges messages with the same SKU. Can you confirm?",
      steps=[
          S("read_file", path="app/tally.py"),
          S("invoke_local", function="tally", type="queue",
            data=[{"sku": "mug", "qty": 2}, {"sku": "mug", "qty": 3}, {"sku": "cap", "qty": 1}]),
          S("propose_plan", steps=["Add to the running count (`counts.get(sku, 0) + qty`) instead of `dict.update`, which replaces the value",
                                   "Invoke the same three moves; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tally.py", content=FUTURE + """
def handle(event, ctx):
    counts = {}
    for record in event.records:
        move = record.json()
        counts[move["sku"]] = counts.get(move["sku"], 0) + move["qty"]
    return {"counts": counts}
"""),
          S("invoke_local", function="tally", type="queue",
            data=[{"sku": "mug", "qty": 2}, {"sku": "mug", "qty": 3}, {"sku": "cap", "qty": 1}]),
          S("validate"),
      ],
      final="""It isn't Pub/Sub: the same thing happens locally with no Pub/Sub involved. `counts.update({sku: qty})` **replaces** the value for that key, so the second mug move (3) overwrote the first (2). Now each move is added to the running count.

- Before: `{"mug": 3, "cap": 1}`. After: `{"counts": {"mug": 5, "cap": 1}}`.
- validate (gcp, prod): valid.

`collections.Counter` would also work (`counts[sku] += qty`)."""),

    # ------------------------------------------------------------------ 315 gcp workflow, input_path in the config cuts the data
    B(315, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#data-flow"],
      project=dict(files={
          "pskit.yml": G("fulfilment") + """functions:
  reserve:
    handler: app.steps.reserve
  ship:
    handler: app.steps.ship
workflows:
  fulfil:
    start_at: Reserve
    states:
      Reserve: {type: task, function: reserve, input_path: $.order, next: Ship}
      Ship: {type: task, function: ship, end: true}
""",
          "app/__init__.py": "",
          "app/steps.py": FUTURE + """
def reserve(event, ctx):
    data = event.data
    return {"email": data["customer"]["email"], "skus": [i["sku"] for i in data["order"]["items"]]}


def ship(event, ctx):
    return {"shipped": event.data["skus"], "notify": event.data["email"]}
""",
          "requirements.txt": ""}),
      user="fulfil workflow fail in Reserve with KeyError 'customer'. but my input have customer! {customer:{email}, order:{items}}. code is same like last week",
      steps=[
          S("read_file", path="app/steps.py"),
          S("get_project"),
          S("invoke_local", function="reserve", type="workflow", data={"items": [{"sku": "mug"}]}),
          S("propose_plan", steps=["Remove `input_path: $.order` from the Reserve state, so it gets the whole input (customer and order)",
                                   "Invoke reserve with the full input"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.fulfil.states.Reserve.input_path", value=None),
          S("invoke_local", function="reserve", type="workflow",
            data={"customer": {"email": "kim@example.com"}, "order": {"items": [{"sku": "mug"}]}}),
      ],
      final="""The code is fine; the workflow config changed. The Reserve state has `input_path: $.order`, so it passed only the order (`{"items": [...]}`) to the function, and there's no `customer` in that [docs/workflows.md#data-flow]. I removed `input_path`, so Reserve gets the whole input again.

- validate (gcp, staging): valid.
- reserve with the full input: `{"email": "kim@example.com", "skus": ["mug"]}`.

The first invoke above shows what Reserve received before: only the order."""),

    # ------------------------------------------------------------------ 316 gcp http, bool("false") is True
    B(316, provider="gcp", stage="prod", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": G("accounts", "europe-west3") + """functions:
  set-active:
    handler: app.users.set_active
    events:
      - http: PUT /users/{id}/status
""",
          "app/__init__.py": "",
          "app/users.py": FUTURE + """
def set_active(event, ctx):
    body = event.http.json()
    return {"id": event.http.path_params["id"], "active": bool(body.get("active", True))}
""",
          "requirements.txt": ""}),
      user="I send active false to deactivate a user, but the answer says active true. The admin form sends it as text, \"false\".",
      steps=[
          S("read_file", path="app/users.py"),
          S("invoke_local", function="set-active", method="PUT", path="/users/u-7/status", data={"active": "false"}),
          S("propose_plan", steps=["Read `active` as a real boolean or the text true/false (also 1/0), and return 400 for anything else",
                                   "PUT \"false\", false and \"maybe\" locally; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/users.py", content=FUTURE + """from py_serverless_kit import BadRequest

TRUE = {"true", "1", "yes"}
FALSE = {"false", "0", "no"}


def to_bool(value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in TRUE:
        return True
    if text in FALSE:
        return False
    raise BadRequest("active must be true or false")


def set_active(event, ctx):
    body = event.http.json()
    return {"id": event.http.path_params["id"], "active": to_bool(body.get("active", True))}
"""),
          S("invoke_local", function="set-active", method="PUT", path="/users/u-7/status", data={"active": "false"}),
          S("invoke_local", function="set-active", method="PUT", path="/users/u-7/status", data={"active": False}),
          S("invoke_local", function="set-active", method="PUT", path="/users/u-7/status", data={"active": "maybe"}),
          S("validate"),
      ],
      final="""`bool("false")` is `True`: any non-empty text counts as true in Python. Now `to_bool()` understands a real `true`/`false` and the text forms (`"false"`, `"0"`, `"no"`...), and anything else is a 400.

- `"false"`: `{"id": "u-7", "active": false}`. `false`: the same.
- `"maybe"`: 400 `active must be true or false`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 317 azure http, recursion on a cyclic category tree
    B(317, provider="azure", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AZ("catalog-api", "northeurope") + """functions:
  category-path:
    handler: app.catalog.path
    events:
      - http: GET /categories/{id}/path
""",
          "app/__init__.py": "",
          "app/data.py": FUTURE + """CATEGORIES = {
    "c1": {"name": "Home", "parent": None},
    "c2": {"name": "Kitchen", "parent": "c1"},
    "c4": {"name": "Mugs", "parent": "c5"},
    "c5": {"name": "Cups", "parent": "c4"},
}
""",
          "app/catalog.py": FUTURE + """from py_serverless_kit import NotFound

from app.data import CATEGORIES


def path_of(cat_id):
    cat = CATEGORIES[cat_id]
    if cat["parent"] is None:
        return [cat["name"]]
    return path_of(cat["parent"]) + [cat["name"]]


def path(event, ctx):
    cat_id = event.http.path_params["id"]
    if cat_id not in CATEGORIES:
        raise NotFound(f"no category {cat_id}")
    return {"path": path_of(cat_id)}
""",
          "requirements.txt": ""}),
      user="""RecursionError: maximum recursion depth exceeded
GET /categories/c4/path. c2 works. The categories come from an import of the old shop.""",
      steps=[
          S("read_file", path="app/catalog.py"),
          S("read_file", path="app/data.py"),
          S("invoke_local", function="category-path", path="/categories/c4/path"),
          S("propose_plan", steps=["Walk up the parents in a loop and remember the visited ids",
                                   "When an id comes back (a cycle), return 409 naming the category instead of crashing",
                                   "GET c2 (200) and c4 (409) locally; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/catalog.py", content=FUTURE + """from py_serverless_kit import Conflict, NotFound

from app.data import CATEGORIES


def path_of(cat_id):
    names, seen = [], set()
    while cat_id is not None:
        if cat_id in seen:
            raise Conflict(f"category {cat_id} is its own ancestor; fix its parent")
        seen.add(cat_id)
        cat = CATEGORIES[cat_id]
        names.append(cat["name"])
        cat_id = cat["parent"]
    return list(reversed(names))


def path(event, ctx):
    cat_id = event.http.path_params["id"]
    if cat_id not in CATEGORIES:
        raise NotFound(f"no category {cat_id}")
    return {"path": path_of(cat_id)}
"""),
          S("invoke_local", function="category-path", path="/categories/c2/path"),
          S("invoke_local", function="category-path", path="/categories/c4/path"),
          S("validate"),
      ],
      final="""The data has a loop: c4's parent is c5 and c5's parent is c4. `path_of` called itself forever until Python stopped it. The code itself was fine for c2. Now it walks the parents in a loop, remembers the ids it has seen, and answers 409 when one comes back [docs/handlers.md#errors].

- c2: `{"path": ["Home", "Kitchen"]}`.
- c4: 409 `category c4 is its own ancestor; fix its parent`.
- validate (azure, prod): valid.

The real fix is in app/data.py: give c4 or c5 a correct parent (probably `c2`). Tell me which, and I'll change it."""),

    # ------------------------------------------------------------------ 318 azure queue, Node.js Date from seconds
    B(318, provider="azure", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AZ("door-events", "westeurope", "  runtime: nodejs20\n") + """functions:
  door-log:
    handler: src.doors.handle
    events:
      - queue: door-events
""",
          "src/doors.js": """exports.handle = async (event) => {
  const out = [];
  for (const record of event.records) {
    const msg = record.json();
    out.push({ door: msg.door, at: new Date(msg.ts).toISOString() });
  }
  return { events: out };
};
"""}),
      user="door log shows date 1970-01-21 for all events. sensor send ts like 1793484900",
      steps=[
          S("read_file", path="src/doors.js"),
          S("invoke_local", function="door-log", type="queue", data=[{"door": "north", "ts": 1793484900}]),
          S("propose_plan", steps=["Multiply `ts` by 1000: the sensor sends Unix **seconds**, `new Date(n)` expects milliseconds",
                                   "Invoke with the same message; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/doors.js", content="""exports.handle = async (event) => {
  const out = [];
  for (const record of event.records) {
    const msg = record.json();
    out.push({ door: msg.door, at: new Date(msg.ts * 1000).toISOString() });
  }
  return { events: out };
};
"""),
          S("invoke_local", function="door-log", type="queue", data=[{"door": "north", "ts": 1793484900}]),
          S("validate"),
      ],
      final="""`new Date(number)` in JavaScript takes **milliseconds** since 1970. The sensor sends seconds, so 1793484900 was read as about 20 days after 1 Jan 1970. `msg.ts * 1000` fixes it.

- Before: `1970-01-21T18:11:24.900Z`. After: `2026-10-31T22:15:00.000Z`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 319 azure schedule, user blames UTC; datetime text vs date
    B(319, provider="azure", stage="staging", mode="ask", page="Logs", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("bookings", "swedencentral") + """functions:
  daily-count:
    handler: app.report.run
    events:
      - schedule: "0 20 * * *"
""",
          "app/__init__.py": "",
          "app/store.py": FUTURE + """
def load_bookings():
    return [
        {"id": "b1", "at": "2026-11-01T08:30:00"},
        {"id": "b2", "at": "2026-11-01T17:45:00"},
        {"id": "b3", "at": "2026-11-02T09:00:00"},
    ]
""",
          "app/report.py": FUTURE + """from datetime import date

from app.store import load_bookings


def run(event, ctx):
    day = (event.data or {}).get("day") or date.today().isoformat()
    todays = [b for b in load_bookings() if b["at"] == day]
    return {"day": day, "count": len(todays)}
""",
          "requirements.txt": ""}),
      user="daily-count always 0. azure timers are UTC, wrong day? same with input {\"day\": \"2026-11-01\"} though",
      steps=[
          S("read_file", path="app/report.py"),
          S("invoke_local", function="daily-count", type="schedule", data={"day": "2026-11-01"}),
          S("propose_plan", steps=["Compare only the date part of `at` (`b[\"at\"][:10]`) with the day; the full timestamp never equals a plain date",
                                   "Run with day 2026-11-01; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/report.py", content=FUTURE + """from datetime import date

from app.store import load_bookings


def run(event, ctx):
    day = (event.data or {}).get("day") or date.today().isoformat()
    todays = [b for b in load_bookings() if b["at"][:10] == day]
    return {"day": day, "count": len(todays)}
"""),
          S("invoke_local", function="daily-count", type="schedule", data={"day": "2026-11-01"}),
          S("validate"),
      ],
      final="""Not UTC: your explicit day gives 0 too. `b["at"]` is a full timestamp (`2026-11-01T08:30:00`), and it is never equal to `2026-11-01`. Now only its first 10 characters (the date) are compared.

- day 2026-11-01: before 0, now `{"day": "2026-11-01", "count": 2}`.
- validate (azure, staging): valid.

UTC still matters for the default day: at `0 20 * * *` UTC, `date.today()` is the UTC date [docs/events.md#schedule]."""),

    # ------------------------------------------------------------------ 320 azure http, function-level env overrides the provider value
    B(320, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": AZ("media-upload", "westeurope", "  environment:\n    MAX_UPLOAD_MB: \"25\"\n") + """functions:
  upload-check:
    handler: app.upload.check
    environment:
      MAX_UPLOAD_MB: "2"
    events:
      - http: POST /uploads/check
""",
          "app/__init__.py": "",
          "app/upload.py": FUTURE + """import os


def check(event, ctx):
    limit = float(os.environ.get("MAX_UPLOAD_MB", "10"))
    size_mb = float(event.http.json()["size_mb"])
    if size_mb > limit:
        return {"error": f"file is larger than {limit:g} MB"}, 413
    return {"ok": True, "limit_mb": limit}
""",
          "requirements.txt": ""}),
      user="I raised the upload limit to 25 MB by setting MAX_UPLOAD_MB under provider.environment, but a 10 MB file still gets 413 \"file is larger than 2 MB\". Where does the 2 come from? The code reads the variable correctly, I think.",
      steps=[
          S("read_file", path="app/upload.py"),
          S("invoke_local", function="upload-check", method="POST", path="/uploads/check", data={"size_mb": 10}),
          S("get_project"),
          S("propose_plan", steps=["Remove `functions.upload-check.environment` (its `MAX_UPLOAD_MB: \"2\"` overrides the provider value)",
                                   "POST a 10 MB check locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.upload-check.environment", value=None),
          S("invoke_local", function="upload-check", method="POST", path="/uploads/check", data={"size_mb": 10}),
      ],
      final="""The code is right; the 2 comes from pskit.yml. `upload-check` has its own `environment: {MAX_UPLOAD_MB: "2"}`, and a function's environment wins over `provider.environment` for the same name [docs/configuration.md#functions]. I removed the function-level block, so the provider's 25 applies.

- validate (azure): valid.
- 10 MB: `{"ok": true, "limit_mb": 25.0}`.

On the Functions page, check the function's Environment variables section too when a provider value seems ignored."""),
]
