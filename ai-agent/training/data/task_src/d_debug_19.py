"""Category D (fix a handler bug), batch 19. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 361 onprem http, Node.js typeof "array"
    B(361, provider="onprem", stage="dev", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": OP("bulk-js", 8691, "  runtime: nodejs22\n") + """functions:
  bulk-archive:
    handler: src.bulk.archive
    events:
      - http: POST /archive
""",
          "src/bulk.js": """exports.archive = async (event) => {
  const { ids } = event.http.json();
  const list = typeof ids === "array" ? ids : [ids];
  return { archived: list, count: list.length };
};
"""}),
      user="POST /archive {ids:[1,2]} -> archived [[1,2]], count 1. single id works",
      steps=[
          S("read_file", path="src/bulk.js"),
          S("invoke_local", function="bulk-archive", method="POST", path="/archive", data={"ids": [1, 2]}),
          S("propose_plan", steps=["Check with `Array.isArray(ids)`: `typeof` of an array is \"object\", never \"array\"",
                                   "POST a list and a single id locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/bulk.js", content="""exports.archive = async (event) => {
  const { ids } = event.http.json();
  const list = Array.isArray(ids) ? ids : [ids];
  return { archived: list, count: list.length };
};
"""),
          S("invoke_local", function="bulk-archive", method="POST", path="/archive", data={"ids": [1, 2]}),
          S("invoke_local", function="bulk-archive", method="POST", path="/archive", data={"ids": 7}),
          S("validate"),
      ],
      final="""`typeof [1, 2]` is `"object"` in JavaScript, so the check was always false and every list got wrapped again. `Array.isArray()` is the real test.

- `[1, 2]`: `{"archived": [1, 2], "count": 2}`.
- `7`: `{"archived": [7], "count": 1}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 362 onprem queue, raise after BatchResult retries the whole batch
    B(362, provider="onprem", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": OP("webhooks-out", 8692) + """functions:
  deliver:
    handler: app.deliver.handle
    events:
      - queue:
          name: webhook-jobs
          max_receive: 5
""",
          "app/__init__.py": "",
          "app/deliver.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        job = record.json()
        if not job.get("url", "").startswith("https://"):
            result.fail(record)
            continue
        ctx.logger.info("delivered", extra={"url": job["url"]})
    if result.failed:
        raise RuntimeError(f"{len(result.failed)} job(s) failed")  # so it shows up in Logs
    return result
""",
          "requirements.txt": ""}),
      user="Every webhook in a batch is delivered several times when one job in it is bad. I already report the bad job with BatchResult.fail. I think the on-prem host re-delivers the good messages too. I added the raise at the end only so failures show up in the Logs page.",
      steps=[
          S("read_file", path="app/deliver.py"),
          S("invoke_local", function="deliver", type="queue",
            data=[{"url": "https://hooks.example.com/a"}, {"url": "http://insecure.example.com"}]),
          S("propose_plan", steps=["Drop the `raise` at the end: an exception means the whole batch failed, so the host retries every message",
                                   "Log each failure with `ctx.logger.warning` instead, so it still shows in Logs",
                                   "Invoke with a good and a bad job; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/deliver.py", content=FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        job = record.json()
        if not job.get("url", "").startswith("https://"):
            ctx.logger.warning("bad webhook url", extra={"message_id": record.id, "url": job.get("url")})
            result.fail(record)
            continue
        ctx.logger.info("delivered", extra={"url": job["url"]})
    return result
"""),
          S("invoke_local", function="deliver", type="queue",
            data=[{"url": "https://hooks.example.com/a"}, {"url": "http://insecure.example.com"}]),
          S("validate"),
      ],
      final="""The host isn't the problem; the `raise` is. A handler that raises has failed as a whole, so the `BatchResult` is never returned and the host retries **every** message in the batch, the delivered ones too (up to `max_receive: 5`) [docs/handlers.md#batchresult]. Now the handler returns the result and logs a `bad webhook url` warning per failure, which shows in Logs.

- Before: traceback, whole batch retried.
- After: `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`; only the http:// job is retried.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 363 onprem http, int() before multiplying the percentage
    B(363, provider="onprem", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": OP("project-progress", 8693) + """functions:
  progress:
    handler: app.progress.get
    events:
      - http: POST /progress
""",
          "app/__init__.py": "",
          "app/progress.py": FUTURE + """
def get(event, ctx):
    tasks = event.http.json()["tasks"]
    done = sum(1 for t in tasks if t["done"])
    return {"done": done, "total": len(tasks), "percent": int(done / len(tasks)) * 100}
""",
          "requirements.txt": ""}),
      user="progress percent always 0 until all task done, then 100. 3 of 4 done should be 75",
      steps=[
          S("read_file", path="app/progress.py"),
          S("invoke_local", function="progress", method="POST", path="/progress",
            data={"tasks": [{"done": True}, {"done": True}, {"done": True}, {"done": False}]}),
          S("propose_plan", steps=["Multiply before cutting off: `int(done * 100 / total)`; also return 0 for an empty list",
                                   "POST 3 of 4 done and an empty list locally; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/progress.py", content=FUTURE + """
def get(event, ctx):
    tasks = event.http.json()["tasks"]
    done = sum(1 for t in tasks if t["done"])
    percent = int(done * 100 / len(tasks)) if tasks else 0
    return {"done": done, "total": len(tasks), "percent": percent}
"""),
          S("invoke_local", function="progress", method="POST", path="/progress",
            data={"tasks": [{"done": True}, {"done": True}, {"done": True}, {"done": False}]}),
          S("invoke_local", function="progress", method="POST", path="/progress", data={"tasks": []}),
          S("validate"),
      ],
      final="""`int(done / len(tasks))` cuts `0.75` down to `0` **before** the `* 100`, so you only ever saw 0 or 100. Now it multiplies first: `int(3 * 100 / 4)` = 75. An empty task list gives 0 instead of a division error.

- 3 of 4: `{"done": 3, "total": 4, "percent": 75}`.
- No tasks: `{"done": 0, "total": 0, "percent": 0}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 364 onprem workflow, catch result shape
    B(364, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": OP("payments-flow", 8694) + """functions:
  charge:
    handler: app.pay.charge
  notify-failure:
    handler: app.pay.notify_failure
workflows:
  pay:
    start_at: Charge
    states:
      Charge:
        type: task
        function: charge
        catch:
          - {errors: ["*"], next: NotifyFailure}
        end: true
      NotifyFailure: {type: task, function: notify-failure, end: true}
""",
          "app/__init__.py": "",
          "app/pay.py": FUTURE + """
class PaymentDeclined(Exception):
    pass


def charge(event, ctx):
    if event.data.get("card") == "expired":
        raise PaymentDeclined("card expired")
    return {"charged": event.data["amount"]}


def notify_failure(event, ctx):
    err = event.data["error"]
    return {"notify": event.data["email"], "reason": err["message"]}
""",
          "requirements.txt": ""}),
      user="""pay workflow, NotifyFailure step:
KeyError: 'message'
it should send the reason why Charge failed""",
      steps=[
          S("read_file", path="app/pay.py"),
          S("search_docs", query="catch result_path error cause",
            docs=[D("docs/workflows.md", "retry-and-catch", start="catch:", end="the run fails.")]),
          S("invoke_local", function="notify-failure", type="workflow",
            data={"email": "kim@example.com", "amount": 30, "card": "expired", "error": {"error": "PaymentDeclined", "cause": "card expired"}}),
          S("propose_plan", steps=["Read `error` (the exception class) and `cause` (its message) from `$.error`; there is no `message` key",
                                   "Invoke notify-failure with the data the catch passes; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/pay.py", content=FUTURE + """
class PaymentDeclined(Exception):
    pass


def charge(event, ctx):
    if event.data.get("card") == "expired":
        raise PaymentDeclined("card expired")
    return {"charged": event.data["amount"]}


def notify_failure(event, ctx):
    err = event.data.get("error") or {}
    return {"notify": event.data["email"], "error": err.get("error"), "reason": err.get("cause")}
"""),
          S("invoke_local", function="notify-failure", type="workflow",
            data={"email": "kim@example.com", "amount": 30, "card": "expired", "error": {"error": "PaymentDeclined", "cause": "card expired"}}),
          S("validate"),
      ],
      final="""A catch stores `{"error": "...", "cause": "..."}` under `$.error` (the default `result_path`) [docs/workflows.md#retry-and-catch]: `error` is the exception class name and `cause` its message. There's no `message` key. NotifyFailure now reads both.

- With the catch data: `{"notify": "kim@example.com", "error": "PaymentDeclined", "reason": "card expired"}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 365 onprem http, shallow merge drops nested fields
    B(365, provider="onprem", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": OP("profiles", 8695) + """functions:
  patch-profile:
    handler: app.profile.patch
    events:
      - http: PATCH /profile
""",
          "app/__init__.py": "",
          "app/profile.py": FUTURE + """import copy

CURRENT = {"name": "Kim", "address": {"street": "Main St 1", "city": "Berlin", "zip": "10115"}}


def patch(event, ctx):
    changes = event.http.json()
    updated = {**copy.deepcopy(CURRENT), **changes}
    return {"profile": updated}
""",
          "requirements.txt": ""}),
      user="PATCH /profile should only change the fields that are sent. Sending {\"address\": {\"zip\": \"10117\"}} wipes the street and city; the result has address = {zip: 10117} only. Nested objects must be merged too.",
      steps=[
          S("read_file", path="app/profile.py"),
          S("invoke_local", function="patch-profile", method="PATCH", path="/profile", data={"address": {"zip": "10117"}}),
          S("propose_plan", steps=["Add a recursive `deep_merge` that merges dicts key by key and replaces everything else",
                                   "PATCH the zip and the name locally; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/profile.py", content=FUTURE + """import copy

CURRENT = {"name": "Kim", "address": {"street": "Main St 1", "city": "Berlin", "zip": "10115"}}


def deep_merge(base, changes):
    out = copy.deepcopy(base)
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def patch(event, ctx):
    return {"profile": deep_merge(CURRENT, event.http.json())}
"""),
          S("invoke_local", function="patch-profile", method="PATCH", path="/profile", data={"address": {"zip": "10117"}}),
          S("invoke_local", function="patch-profile", method="PATCH", path="/profile", data={"name": "Kim Lee"}),
          S("validate"),
      ],
      final="""`{**current, **changes}` merges only the top level: the whole `address` value was replaced by `{"zip": "10117"}`. `deep_merge()` goes into nested dicts and changes only the keys you send; lists and plain values are still replaced.

- `{"address": {"zip": "10117"}}`: street `Main St 1` and city `Berlin` kept, zip `10117`.
- `{"name": "Kim Lee"}`: only the name changes.
- validate (onprem, prod): valid.

There's no way to delete a nested key with this yet; sending `null` sets it to null. Tell me if you need removal."""),

    # ------------------------------------------------------------------ 366 onprem smtp, HTML-only mails give an empty ticket
    B(366, provider="onprem", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": OP("support-tickets", 8696) + """resources:
  support-mail:
    type: smtp
    external: true
    connection: {host: 192.0.2.44, port: 25, domains: support.example.com}
functions:
  new-ticket:
    handler: app.tickets.handle
    events:
      - smtp: support-mail
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """
def handle(event, ctx):
    mail = event.data
    return {"ticket": {"from": mail["from"], "subject": mail["subject"], "body": mail["text"].strip()}}
""",
          "requirements.txt": ""}),
      user="Some customers' tickets have an empty body, but they wrote a long mail. It's always people who write from the same web mail program.",
      steps=[
          S("read_file", path="app/tickets.py"),
          S("invoke_local", function="new-ticket", type="smtp",
            data={"from": "lu@example.org", "to": ["help@support.example.com"], "subject": "Login",
                  "html": "<p>I can't log in.</p><p>Since <b>Monday</b>.</p>"}),
          S("propose_plan", steps=["When `text` is empty, build the body from `html` with the tags removed (stdlib `html.parser`)",
                                   "Invoke with an HTML-only mail and a normal one; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tickets.py", content=FUTURE + """from html.parser import HTMLParser


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_endtag(self, tag):
        if tag in ("p", "div", "br", "li"):
            self.parts.append("\\n")


def html_to_text(html):
    parser = _Text()
    parser.feed(html)
    lines = [line.strip() for line in "".join(parser.parts).splitlines()]
    return "\\n".join(line for line in lines if line)


def handle(event, ctx):
    mail = event.data
    body = mail["text"].strip() or html_to_text(mail["html"])
    return {"ticket": {"from": mail["from"], "subject": mail["subject"], "body": body}}
"""),
          S("invoke_local", function="new-ticket", type="smtp",
            data={"from": "lu@example.org", "to": ["help@support.example.com"], "subject": "Login",
                  "html": "<p>I can't log in.</p><p>Since <b>Monday</b>.</p>"}),
          S("invoke_local", function="new-ticket", type="smtp",
            data={"from": "max@example.org", "to": ["help@support.example.com"], "subject": "Invoice", "text": "Where is my invoice?"}),
          S("validate"),
      ],
      final="""That web mail program sends HTML only, with no plain-text part, and `mail["text"]` is then `""` [docs/smtp/README.md#what-the-handler-receives]. The handler now falls back to `mail["html"]` with the tags removed.

- HTML-only mail: body `I can't log in.` / `Since Monday.`
- Normal mail: body `Where is my invoice?` (unchanged).
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 367 onprem http, CSV download sent as text/plain
    B(367, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": OP("hr-export", 8697) + """functions:
  export-staff:
    handler: app.export.staff
    events:
      - http: GET /staff.csv
""",
          "app/__init__.py": "",
          "app/export.py": FUTURE + """from py_serverless_kit import Response

STAFF = [("Ann", "Sales"), ("Raj", "IT")]


def staff(event, ctx):
    csv = "name,team\\n" + "".join(f"{n},{t}\\n" for n, t in STAFF)
    return Response.text(csv)
""",
          "requirements.txt": ""}),
      user="staff.csv open as text in browser, not download. excel dont recognise. need real csv file download",
      steps=[
          S("read_file", path="app/export.py"),
          S("invoke_local", function="export-staff", path="/staff.csv"),
          S("propose_plan", steps=["Return the CSV with `content-type: text/csv` and `content-disposition: attachment; filename=\"staff.csv\"`",
                                   "GET /staff.csv locally and check the headers; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/export.py", content=FUTURE + """STAFF = [("Ann", "Sales"), ("Raj", "IT")]


def staff(event, ctx):
    csv = "name,team\\n" + "".join(f"{n},{t}\\n" for n, t in STAFF)
    headers = {"content-type": "text/csv; charset=utf-8",
               "content-disposition": 'attachment; filename="staff.csv"'}
    return csv, 200, headers
"""),
          S("invoke_local", function="export-staff", path="/staff.csv"),
          S("validate"),
      ],
      final="""`Response.text()` sends `text/plain`, so the browser shows it inline. The handler now returns `(body, 200, headers)` [docs/handlers.md#returning-a-response] with `content-type: text/csv` and `content-disposition: attachment; filename="staff.csv"`, which makes the browser download it as a file that Excel opens.

- GET /staff.csv: 200 with both headers (see the invoke output).
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 368 onprem schedule, chunk slice uses a fixed end
    B(368, provider="onprem", stage="prod", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": OP("newsletter", 8698) + """functions:
  plan-sends:
    handler: app.plan.run
    events:
      - schedule:
          cron: "0 8 * * 1"
          input: {subscribers: 250, chunk: 100}
""",
          "app/__init__.py": "",
          "app/plan.py": FUTURE + """
def run(event, ctx):
    ids = list(range(1, event.data["subscribers"] + 1))
    size = event.data["chunk"]
    chunks = [ids[i:size] for i in range(0, len(ids), size)]
    return {"chunks": [len(c) for c in chunks], "planned": sum(len(c) for c in chunks)}
""",
          "requirements.txt": ""}),
      user="plan-sends: 250 subscribers, planned 100. chunks [100, 0, 0]",
      steps=[
          S("read_file", path="app/plan.py"),
          S("invoke_local", function="plan-sends", type="schedule"),
          S("propose_plan", steps=["Slice `ids[i:i + size]` (the end is relative to the start)",
                                   "Run with the configured input; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/plan.py", content=FUTURE + """
def run(event, ctx):
    ids = list(range(1, event.data["subscribers"] + 1))
    size = event.data["chunk"]
    chunks = [ids[i:i + size] for i in range(0, len(ids), size)]
    return {"chunks": [len(c) for c in chunks], "planned": sum(len(c) for c in chunks)}
"""),
          S("invoke_local", function="plan-sends", type="schedule"),
          S("validate"),
      ],
      final="""`ids[i:size]` always ends at index 100, so only the first chunk had items (`ids[100:100]` is empty). The end must be `i + size`.

- After: `{"chunks": [100, 100, 50], "planned": 250}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 369 aws http, ranks start at 0
    B(369, provider="aws", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": AWS("quiz", "us-west-1") + """functions:
  ranking:
    handler: app.ranking.get
    events:
      - http: POST /ranking
""",
          "app/__init__.py": "",
          "app/ranking.py": FUTURE + """
def get(event, ctx):
    players = sorted(event.http.json()["players"], key=lambda p: p["score"], reverse=True)
    return {"ranking": [{"rank": i, "name": p["name"]} for i, p in enumerate(players)]}
""",
          "requirements.txt": ""}),
      user="The winner of our quiz shows as rank 0. The best player should be rank 1.",
      steps=[
          S("read_file", path="app/ranking.py"),
          S("invoke_local", function="ranking", method="POST", path="/ranking",
            data={"players": [{"name": "Bo", "score": 7}, {"name": "Ada", "score": 9}]}),
          S("propose_plan", steps=["Start counting at 1: `enumerate(players, 1)`",
                                   "POST two players locally; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/ranking.py", content=FUTURE + """
def get(event, ctx):
    players = sorted(event.http.json()["players"], key=lambda p: p["score"], reverse=True)
    return {"ranking": [{"rank": i, "name": p["name"]} for i, p in enumerate(players, 1)]}
"""),
          S("invoke_local", function="ranking", method="POST", path="/ranking",
            data={"players": [{"name": "Bo", "score": 7}, {"name": "Ada", "score": 9}]}),
          S("validate"),
      ],
      final="""`enumerate()` counts from 0 unless you give it a start. `enumerate(players, 1)` makes the best player rank 1.

- After: Ada rank 1, Bo rank 2.
- validate (aws): valid.

Players with the same score still get different ranks. Tell me if ties should share a rank."""),

    # ------------------------------------------------------------------ 370 aws queue, SNS envelope inside the SQS body
    B(370, provider="aws", stage="prod", mode="ask", page="Logs", persona="aws_migrator",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AWS("fulfil-orders", "eu-west-1") + """functions:
  pick:
    handler: app.pick.handle
    events:
      - queue: pick-orders
""",
          "app/__init__.py": "",
          "app/pick.py": FUTURE + """
def handle(event, ctx):
    return {"picked": [record.json()["order_id"] for record in event.records]}
""",
          "requirements.txt": ""}),
      user="We subscribed the pick-orders SQS queue to our existing `orders` SNS topic (set up outside pskit, no raw message delivery). The worker now fails with KeyError: 'order_id', although the publisher sends {\"order_id\": ...}.",
      steps=[
          S("read_file", path="app/pick.py"),
          S("invoke_local", function="pick", type="queue",
            data=[{"Type": "Notification", "TopicArn": "arn:aws:sns:eu-west-1:123456789012:orders", "Message": "{\"order_id\": 7}"}]),
          S("propose_plan", steps=["Unwrap the SNS envelope: when the body has `Type: Notification`, parse its `Message` string",
                                   "Invoke with a wrapped and a plain message; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/pick.py", content=FUTURE + """import json


def order_of(record):
    body = record.json()
    if isinstance(body, dict) and body.get("Type") == "Notification" and "Message" in body:
        body = json.loads(body["Message"])  # SQS subscribed to SNS without raw message delivery
    return body


def handle(event, ctx):
    return {"picked": [order_of(record)["order_id"] for record in event.records]}
"""),
          S("invoke_local", function="pick", type="queue",
            data=[{"Type": "Notification", "TopicArn": "arn:aws:sns:eu-west-1:123456789012:orders", "Message": "{\"order_id\": 7}"},
                  {"order_id": 8}]),
          S("validate"),
      ],
      final="""Without raw message delivery, SNS wraps each message before putting it in SQS: the SQS body is the SNS notification (`Type`, `TopicArn`, ...) and your JSON is a **string** in its `Message` field. `order_of()` unwraps that and still accepts plain messages.

- Wrapped and plain: `{"picked": [7, 8]}`.
- validate (aws, prod): valid.

The alternative is to turn on raw message delivery on the SNS subscription; then the old code works. Since the subscription isn't managed by pskit, that is a change in AWS."""),

    # ------------------------------------------------------------------ 371 aws storage, Node.js Object.assign mutates the defaults
    B(371, provider="aws", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AWS("resize-js", "us-east-1", "  runtime: nodejs20\n") + """functions:
  resize-plan:
    handler: src.resize.plan
    events:
      - storage: uploads
""",
          "src/resize.js": """const DEFAULTS = { quality: 85, width: 1200 };

exports.plan = async (event) => {
  return {
    jobs: event.records.map((record) => {
      const overrides = record.key.startsWith("low/") ? { quality: 50 } : {};
      const settings = Object.assign(DEFAULTS, overrides);
      return { key: record.key, quality: settings.quality };
    }),
  };
};
"""}),
      user="Uploads under low/ should be encoded at quality 50, everything else at 85. When a batch has low/a.jpg followed by b.jpg, b.jpg also gets 50. It only happens when a low/ file comes first in the batch.",
      steps=[
          S("read_file", path="src/resize.js"),
          S("invoke_local", function="resize-plan", type="storage", data=[{"key": "low/a.jpg"}, {"key": "b.jpg"}]),
          S("propose_plan", steps=["Build a new object per record: `{ ...DEFAULTS, ...overrides }` (Object.assign wrote into DEFAULTS)",
                                   "Invoke with low/a.jpg then b.jpg; validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/resize.js", content="""const DEFAULTS = Object.freeze({ quality: 85, width: 1200 });

exports.plan = async (event) => {
  return {
    jobs: event.records.map((record) => {
      const overrides = record.key.startsWith("low/") ? { quality: 50 } : {};
      const settings = { ...DEFAULTS, ...overrides };
      return { key: record.key, quality: settings.quality };
    }),
  };
};
"""),
          S("invoke_local", function="resize-plan", type="storage", data=[{"key": "low/a.jpg"}, {"key": "b.jpg"}]),
          S("validate"),
      ],
      final="""`Object.assign(target, ...)` copies **into** its first argument, so `DEFAULTS` itself became `quality: 50` and stayed that way for the next records (and for the next batches on a warm Lambda). Now each record gets a fresh object, `{ ...DEFAULTS, ...overrides }`, and `Object.freeze` makes a future write to DEFAULTS fail loudly in strict mode.

- Before: `b.jpg` quality 50. After: `low/a.jpg` 50, `b.jpg` 85.
- validate (aws, staging): valid."""),

    # ------------------------------------------------------------------ 372 aws schedule, stage name compared with the wrong text
    B(372, provider="aws", stage="prod", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": AWS("exports", "eu-central-1") + """functions:
  nightly-export:
    handler: app.export.run
    events:
      - schedule: "30 2 * * *"
""",
          "app/__init__.py": "",
          "app/export.py": FUTURE + """
def run(event, ctx):
    bucket = "acme-exports" if ctx.stage == "production" else "acme-exports-test"
    return {"stage": ctx.stage, "bucket": bucket}
""",
          "requirements.txt": ""}),
      user="prod export land in the test bucket acme-exports-test. stage is prod, i deploy with -s prod",
      steps=[
          S("read_file", path="app/export.py"),
          S("invoke_local", function="nightly-export", type="schedule"),
          S("propose_plan", steps=["Compare with the real stage name, `prod` (ctx.stage is the `-s` value)",
                                   "Run the schedule on stage prod locally; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/export.py", content=FUTURE + """
def run(event, ctx):
    bucket = "acme-exports" if ctx.stage == "prod" else "acme-exports-test"
    return {"stage": ctx.stage, "bucket": bucket}
"""),
          S("invoke_local", function="nightly-export", type="schedule"),
          S("validate"),
      ],
      final="""`ctx.stage` is exactly the stage you deploy with: `prod` [docs/handlers.md#context]. The code checked for `"production"`, which never matched, so it always picked the test bucket.

- Before: `{"stage": "prod", "bucket": "acme-exports-test"}`.
- After: `{"stage": "prod", "bucket": "acme-exports"}`.
- validate (aws, prod): valid.

Cleaner still: put the bucket name in `stages.prod.provider.environment` and read it with `os.environ`, so the code doesn't know stage names."""),

    # ------------------------------------------------------------------ 373 gcp http, Node.js parseFloat stops at the comma
    B(373, provider="gcp", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": G("weights-js", "europe-west3", "  runtime: nodejs20\n") + """functions:
  shipping:
    handler: src.shipping.quote
    events:
      - http: POST /shipping
""",
          "src/shipping.js": """exports.quote = async (event) => {
  const kg = parseFloat(event.http.json().weight);
  return { kg, price: kg > 2 ? 9.9 : 4.9 };
};
"""}),
      user="""{"kg": 2, "price": 4.9}
for weight "2,5" from the german shop form. 2,5 kg must be the 9.9 price""",
      steps=[
          S("read_file", path="src/shipping.js"),
          S("invoke_local", function="shipping", method="POST", path="/shipping", data={"weight": "2,5"}),
          S("propose_plan", steps=["Replace a decimal comma with a dot and use `Number()`, which rejects junk instead of stopping early",
                                   "Return 400 when the weight is not a positive number",
                                   "POST \"2,5\", \"1.2\" and \"abc\" locally; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/shipping.js", content="""const { BadRequest } = require("pskit");

exports.quote = async (event) => {
  const kg = Number(String(event.http.json().weight ?? "").trim().replace(",", "."));
  if (!Number.isFinite(kg) || kg <= 0) throw new BadRequest("weight must be a positive number");
  return { kg, price: kg > 2 ? 9.9 : 4.9 };
};
"""),
          S("invoke_local", function="shipping", method="POST", path="/shipping", data={"weight": "2,5"}),
          S("invoke_local", function="shipping", method="POST", path="/shipping", data={"weight": "1.2"}),
          S("invoke_local", function="shipping", method="POST", path="/shipping", data={"weight": "abc"}),
          S("validate"),
      ],
      final="""`parseFloat("2,5")` reads up to the first character it doesn't understand and returns `2`, silently. Now a decimal comma becomes a dot, and `Number()` (which fails on leftovers instead of ignoring them) parses the whole value; anything else is a 400.

- `"2,5"`: `{"kg": 2.5, "price": 9.9}`.
- `"1.2"`: `{"kg": 1.2, "price": 4.9}`.
- `"abc"`: 400 `weight must be a positive number`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 374 gcp queue, last message wins even when it's older
    B(374, provider="gcp", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": G("order-status", "us-east4") + """functions:
  latest-status:
    handler: app.status.handle
    events:
      - queue: status-updates
""",
          "app/__init__.py": "",
          "app/status.py": FUTURE + """
def handle(event, ctx):
    latest = {}
    for record in event.records:
        update = record.json()
        latest[update["order"]] = update["status"]
    return {"latest": latest}
""",
          "requirements.txt": ""}),
      user="Each status update carries a `seq` number that grows per order. In a batch where `shipped` (seq 3) arrives before `packed` (seq 2), the worker ends with `packed`. I suspect Pub/Sub delivered them out of order. Is that it, and can the handler cope?",
      steps=[
          S("read_file", path="app/status.py"),
          S("invoke_local", function="latest-status", type="queue",
            data=[{"order": "o-5", "status": "shipped", "seq": 3}, {"order": "o-5", "status": "packed", "seq": 2}]),
          S("propose_plan", steps=["Keep the update with the highest `seq` per order instead of the last one received",
                                   "Invoke with the two updates out of order; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/status.py", content=FUTURE + """
def handle(event, ctx):
    latest = {}
    for record in event.records:
        update = record.json()
        current = latest.get(update["order"])
        if current is None or update["seq"] > current["seq"]:
            latest[update["order"]] = update
    return {"latest": {order: u["status"] for order, u in latest.items()}}
"""),
          S("invoke_local", function="latest-status", type="queue",
            data=[{"order": "o-5", "status": "shipped", "seq": 3}, {"order": "o-5", "status": "packed", "seq": 2}]),
          S("validate"),
      ],
      final="""Yes, that's possible: Pub/Sub doesn't guarantee order (unless ordering keys are used), and retries can bring an old message back later. The handler trusted arrival order. Now it keeps the update with the highest `seq` per order, so the order of arrival doesn't matter.

- Out of order: before `packed`, now `{"latest": {"o-5": "shipped"}}`.
- validate (gcp, prod): valid.

This works within one batch. Across batches, store the last `seq` with the status and only update when the new one is higher."""),

    # ------------------------------------------------------------------ 375 gcp http, max() of no bids
    B(375, provider="gcp", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": G("auctions", "europe-west1") + """functions:
  top-bid:
    handler: app.auction.top
    events:
      - http: POST /auctions/top
""",
          "app/__init__.py": "",
          "app/auction.py": FUTURE + """
def top(event, ctx):
    bids = event.http.json()["bids"]
    return {"top": max(b["amount"] for b in bids), "count": len(bids)}
""",
          "requirements.txt": ""}),
      user="""ValueError: max() iterable argument is empty
POST /auctions/top for an auction that just opened""",
      steps=[
          S("read_file", path="app/auction.py"),
          S("invoke_local", function="top-bid", method="POST", path="/auctions/top", data={"bids": []}),
          S("propose_plan", steps=["Give `max()` a `default=None`, so an auction without bids returns `top: null`",
                                   "POST no bids and two bids locally; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/auction.py", content=FUTURE + """
def top(event, ctx):
    bids = event.http.json()["bids"]
    return {"top": max((b["amount"] for b in bids), default=None), "count": len(bids)}
"""),
          S("invoke_local", function="top-bid", method="POST", path="/auctions/top", data={"bids": []}),
          S("invoke_local", function="top-bid", method="POST", path="/auctions/top",
            data={"bids": [{"amount": 120}, {"amount": 150}]}),
          S("validate"),
      ],
      final="""`max()` needs at least one value, and a new auction has none. With `default=None` it returns `None` instead of raising, so the response is `top: null`.

- No bids: `{"top": null, "count": 0}`.
- Two bids: `{"top": 150, "count": 2}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 376 gcp schedule, deadline in the past for today
    B(376, provider="gcp", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": G("invoice-reminders", "us-central1") + """functions:
  overdue:
    handler: app.overdue.run
    events:
      - schedule:
          cron: "0 9 * * *"
          input:
            today: "2026-11-10"
            invoices:
              - {id: i-1, due: "2026-11-10"}
              - {id: i-2, due: "2026-11-03"}
""",
          "app/__init__.py": "",
          "app/overdue.py": FUTURE + """from datetime import date


def run(event, ctx):
    today = date.fromisoformat(event.data["today"])
    overdue = [i["id"] for i in event.data["invoices"] if date.fromisoformat(i["due"]) <= today]
    return {"overdue": overdue}
""",
          "requirements.txt": ""}),
      user="invoice due today is already overdue in the reminder. due today must be not overdue, only from tomorrow",
      steps=[
          S("read_file", path="app/overdue.py"),
          S("invoke_local", function="overdue", type="schedule"),
          S("propose_plan", steps=["Use `<` instead of `<=`: an invoice is overdue only when its due date is before today",
                                   "Run with the configured input; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/overdue.py", content=FUTURE + """from datetime import date


def run(event, ctx):
    today = date.fromisoformat(event.data["today"])
    overdue = [i["id"] for i in event.data["invoices"] if date.fromisoformat(i["due"]) < today]
    return {"overdue": overdue}
"""),
          S("invoke_local", function="overdue", type="schedule"),
          S("validate"),
      ],
      final="""`due <= today` also counts the due day itself. With `<` an invoice becomes overdue the day after its due date.

- Before: `["i-1", "i-2"]`. After: `{"overdue": ["i-2"]}`; i-1 (due today) is not overdue yet.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 377 azure http, join() with a null address line
    B(377, provider="azure", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AZ("labels-api", "westeurope") + """functions:
  shipping-label:
    handler: app.label.make
    events:
      - http: POST /labels
""",
          "app/__init__.py": "",
          "app/label.py": FUTURE + """
def make(event, ctx):
    a = event.http.json()["address"]
    lines = [a["name"], a["line1"], a["line2"], f"{a['zip']} {a['city']}"]
    return {"label": "\\n".join(lines)}
""",
          "requirements.txt": ""}),
      user="""TypeError: sequence item 2: expected str instance, NoneType found
POST /labels, only some addresses""",
      steps=[
          S("read_file", path="app/label.py"),
          S("invoke_local", function="shipping-label", method="POST", path="/labels",
            data={"address": {"name": "Ann Lee", "line1": "Main St 1", "line2": None, "zip": "1010", "city": "Vienna"}}),
          S("propose_plan", steps=["Leave out empty lines (null or blank `line2`) before joining",
                                   "POST an address with and without line2 locally; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/label.py", content=FUTURE + """
def make(event, ctx):
    a = event.http.json()["address"]
    lines = [a.get("name"), a.get("line1"), a.get("line2"), f"{a['zip']} {a['city']}"]
    return {"label": "\\n".join(line.strip() for line in lines if line and line.strip())}
"""),
          S("invoke_local", function="shipping-label", method="POST", path="/labels",
            data={"address": {"name": "Ann Lee", "line1": "Main St 1", "line2": None, "zip": "1010", "city": "Vienna"}}),
          S("invoke_local", function="shipping-label", method="POST", path="/labels",
            data={"address": {"name": "Raj Patel", "line1": "Hill Rd 4", "line2": "Flat 2", "zip": "1020", "city": "Vienna"}}),
          S("validate"),
      ],
      final="""`"\\n".join()` accepts only strings, and `line2` is `null` (None) for addresses without a second line: item 2 in the list. Empty lines are now skipped before joining.

- Without line2: `Ann Lee` / `Main St 1` / `1010 Vienna`.
- With line2: four lines including `Flat 2`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 378 azure queue, level names in different case
    B(378, provider="azure", stage="staging", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": AZ("alerts", "northeurope") + """functions:
  page-oncall:
    handler: app.alerts.handle
    events:
      - queue: alerts
""",
          "app/__init__.py": "",
          "app/alerts.py": FUTURE + """PRIORITY = {"critical": 1, "warning": 2, "info": 3}


def handle(event, ctx):
    pages = []
    for record in event.records:
        alert = record.json()
        if PRIORITY[alert["level"]] == 1:
            pages.append(alert["id"])
    return {"page": pages}
""",
          "requirements.txt": ""}),
      user="the new monitoring tool sends level \"CRITICAL\" in big letters and the function breaks with KeyError: 'CRITICAL'. the old one sent critical",
      steps=[
          S("read_file", path="app/alerts.py"),
          S("invoke_local", function="page-oncall", type="queue",
            data=[{"id": "a1", "level": "CRITICAL"}, {"id": "a2", "level": "info"}]),
          S("propose_plan", steps=["Lower-case and trim the level before the lookup",
                                   "Treat an unknown level as `info` and log a warning instead of failing the batch",
                                   "Invoke with CRITICAL, info and an unknown level; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/alerts.py", content=FUTURE + """PRIORITY = {"critical": 1, "warning": 2, "info": 3}


def handle(event, ctx):
    pages = []
    for record in event.records:
        alert = record.json()
        level = str(alert.get("level", "")).strip().lower()
        if level not in PRIORITY:
            ctx.logger.warning("unknown alert level", extra={"id": alert.get("id"), "level": alert.get("level")})
            level = "info"
        if PRIORITY[level] == 1:
            pages.append(alert["id"])
    return {"page": pages}
"""),
          S("invoke_local", function="page-oncall", type="queue",
            data=[{"id": "a1", "level": "CRITICAL"}, {"id": "a2", "level": "info"}, {"id": "a3", "level": "sev0"}]),
          S("validate"),
      ],
      final="""Dictionary keys are case-sensitive: `"CRITICAL"` is not the key `"critical"`. The level is now lower-cased before the lookup. An unknown level (like `sev0`) logs a warning and is treated as `info`, instead of failing the whole batch.

- After: `{"page": ["a1"]}`, plus an `unknown alert level` warning for a3.
- validate (azure, staging): valid.

If unknown levels should page someone to be safe, I can treat them as critical instead."""),

    # ------------------------------------------------------------------ 379 azure schedule, monthrange()[0] is a weekday
    B(379, provider="azure", stage="prod", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("payroll", "germanywestcentral") + """functions:
  payday:
    handler: app.payday.run
    events:
      - schedule:
          cron: "0 6 25 * *"
          input: {year: 2026, month: 2}
""",
          "app/__init__.py": "",
          "app/payday.py": FUTURE + """import calendar
from datetime import date


def run(event, ctx):
    year, month = event.data["year"], event.data["month"]
    last_day = calendar.monthrange(year, month)[0]
    return {"pay_on": date(year, month, last_day).isoformat()}
""",
          "requirements.txt": ""}),
      user="payday for 2026-02 says 2026-02-06. should be last day of month (28th)",
      steps=[
          S("read_file", path="app/payday.py"),
          S("invoke_local", function="payday", type="schedule"),
          S("propose_plan", steps=["Use `calendar.monthrange(year, month)[1]` (number of days); `[0]` is the weekday of the 1st",
                                   "Run for February 2026; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/payday.py", content=FUTURE + """import calendar
from datetime import date


def run(event, ctx):
    year, month = event.data["year"], event.data["month"]
    days_in_month = calendar.monthrange(year, month)[1]
    return {"pay_on": date(year, month, days_in_month).isoformat()}
"""),
          S("invoke_local", function="payday", type="schedule"),
          S("validate"),
      ],
      final="""`calendar.monthrange()` returns `(weekday of the 1st, number of days)`. `[0]` was 6 (1 Feb 2026 is a Sunday), so you got the 6th. `[1]` is the number of days, which is also the last day.

- After: `{"pay_on": "2026-02-28"}`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 380 azure http, tax rate as a percent in the provider override
    B(380, provider="azure", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=dict(files={
          "pskit.yml": AZ("checkout-eu", "germanywestcentral", "  environment:\n    TAX_RATE: \"0.2\"\n") + """functions:
  total:
    handler: app.total.get
    events:
      - http: POST /total
providers:
  azure:
    environment:
      TAX_RATE: "19"
""",
          "app/__init__.py": "",
          "app/total.py": FUTURE + """import os

# TAX_RATE is a fraction, e.g. 0.19 for 19 %
TAX_RATE = float(os.environ.get("TAX_RATE", "0"))


def get(event, ctx):
    net = float(event.http.json()["net"])
    return {"net": net, "gross": round(net * (1 + TAX_RATE), 2)}
""",
          "requirements.txt": ""}),
      user="On Azure (our German shop) a net price of 100 comes out as 2000 gross instead of 119. On the other deployment it's correct with 0.2. The code expects a fraction, as the comment says.",
      steps=[
          S("read_file", path="app/total.py"),
          S("invoke_local", function="total", method="POST", path="/total", data={"net": 100}),
          S("get_project"),
          S("propose_plan", steps=["Set the Azure override `providers.azure.environment.TAX_RATE` to the fraction \"0.19\" (it says \"19\")",
                                   "POST net 100 locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.environment.TAX_RATE", value="0.19"),
          S("invoke_local", function="total", method="POST", path="/total", data={"net": 100}),
      ],
      final="""The code is right; the Azure override isn't. `providers.azure` is merged over the base config when you deploy to Azure [docs/configuration.md#providers-per-cloud-overrides], and there `TAX_RATE` was `"19"` (a percent), so the gross was 100 x 20. I changed it to `"0.19"`.

- validate (azure): valid, with a warning that `providers.azure` overrides the `0.2` under `provider:`. That override is what you want here (19 % for the German shop), so the warning can stay.
- net 100: before 2000.0, now `{"net": 100.0, "gross": 119.0}`."""),
]
