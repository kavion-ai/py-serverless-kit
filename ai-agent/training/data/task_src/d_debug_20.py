"""Category D (fix a handler bug), batch 20. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 381 onprem http, int dict keys looked up with a str path param
    B(381, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": OP("tickets-api", 8701) + """functions:
  ticket:
    handler: app.tickets.get
    events:
      - http: GET /tickets/{id}
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """from py_serverless_kit import NotFound

TICKETS = {101: {"title": "Printer jam"}, 102: {"title": "VPN down"}}


def get(event, ctx):
    ticket = TICKETS.get(event.http.path_params["id"])
    if ticket is None:
        raise NotFound("no such ticket")
    return ticket
""",
          "requirements.txt": ""}),
      user="GET /tickets/101 says no such ticket, but ticket 101 is right there in the TICKETS dict. I don't understand.",
      steps=[
          S("read_file", path="app/tickets.py"),
          S("invoke_local", function="ticket", path="/tickets/101"),
          S("propose_plan", steps=["Convert the path parameter to `int` before the lookup (path values are text); return 404 for non-numbers",
                                   "GET /tickets/101 (200) and /tickets/abc (404) locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tickets.py", content=FUTURE + """from py_serverless_kit import NotFound

TICKETS = {101: {"title": "Printer jam"}, 102: {"title": "VPN down"}}


def get(event, ctx):
    raw = event.http.path_params["id"]
    ticket = TICKETS.get(int(raw)) if raw.isdigit() else None
    if ticket is None:
        raise NotFound("no such ticket")
    return ticket
"""),
          S("invoke_local", function="ticket", path="/tickets/101"),
          S("invoke_local", function="ticket", path="/tickets/abc"),
          S("validate"),
      ],
      final="""Path parameters are always **text**: `"101"`. Your dict keys are numbers (`101`), and `"101"` and `101` are different keys, so the lookup always missed. The id is now converted with `int()` first; something like `abc` is still a 404.

- `/tickets/101`: 200 `{"title": "Printer jam"}`.
- `/tickets/abc`: 404 `no such ticket`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 382 onprem queue, early return drops the rest of the batch
    B(382, provider="onprem", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": OP("sms-gateway", 8702) + """functions:
  send-sms:
    handler: app.sms.handle
    events:
      - queue:
          name: sms
          dead_letter: sms-dlq
""",
          "app/__init__.py": "",
          "app/sms.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    for record in event.records:
        msg = record.json()
        if not msg.get("to", "").startswith("+"):
            ctx.logger.warning("bad number", extra={"message_id": record.id})
            return BatchResult.of([record])
        ctx.logger.info("sent", extra={"to": msg["to"]})
    return BatchResult()
""",
          "requirements.txt": ""}),
      user="When a batch contains a message with a bad phone number, that one goes to sms-dlq as expected, but the messages after it in the same batch are never sent and never show up again. Messages before it are fine. Nothing is in the logs for them.",
      steps=[
          S("read_file", path="app/sms.py"),
          S("invoke_local", function="send-sms", type="queue",
            data=[{"to": "+15550100"}, {"to": "0800 bad"}, {"to": "+15550102"}]),
          S("propose_plan", steps=["Don't `return` at the first bad message: collect failures in one BatchResult and keep processing the rest",
                                   "Invoke with the bad message in the middle; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sms.py", content=FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        msg = record.json()
        if not msg.get("to", "").startswith("+"):
            ctx.logger.warning("bad number", extra={"message_id": record.id})
            result.fail(record)
            continue
        ctx.logger.info("sent", extra={"to": msg["to"]})
    return result
"""),
          S("invoke_local", function="send-sms", type="queue",
            data=[{"to": "+15550100"}, {"to": "0800 bad"}, {"to": "+15550102"}]),
          S("validate"),
      ],
      final="""`return BatchResult.of([record])` left the loop at the first bad message. The messages after it were never processed, but they weren't in the failure list either, so the host counted them as done and deleted them [docs/handlers.md#batchresult]. Now the handler collects failures and keeps going.

- Before: one `sent` line, then `local-1` failed; `local-2` silently lost.
- After: two `sent` lines and `{"batchItemFailures": [{"itemIdentifier": "local-1"}]}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 383 onprem schedule, random.sample larger than the list
    B(383, provider="onprem", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": OP("survey", 8703) + """functions:
  pick-respondents:
    handler: app.survey.pick
    events:
      - schedule:
          cron: "0 10 * * 1"
          input: {team: [ann, bo, raj], size: 5}
""",
          "app/__init__.py": "",
          "app/survey.py": FUTURE + """import random


def pick(event, ctx):
    team, size = event.data["team"], event.data["size"]
    return {"picked": sorted(random.sample(team, size))}
""",
          "requirements.txt": ""}),
      user="""ValueError: Sample larger than population or is negative
pick-respondents, on the small team (3 people). big teams fine""",
      steps=[
          S("read_file", path="app/survey.py"),
          S("invoke_local", function="pick-respondents", type="schedule"),
          S("propose_plan", steps=["Sample at most the team size: `min(size, len(team))`",
                                   "Run with the 3-person input; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/survey.py", content=FUTURE + """import random


def pick(event, ctx):
    team, size = event.data["team"], event.data["size"]
    return {"picked": sorted(random.sample(team, min(size, len(team))))}
"""),
          S("invoke_local", function="pick-respondents", type="schedule"),
          S("validate"),
      ],
      final="""`random.sample(team, 5)` can't pick 5 different people from 3. Now it picks `min(size, len(team))`, so a small team is simply asked in full.

- 3-person team, size 5: `{"picked": ["ann", "bo", "raj"]}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 384 onprem http, Node.js switch without break
    B(384, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": OP("plans-js", 8704, "  runtime: nodejs22\n") + """functions:
  plan-limits:
    handler: src.plans.limits
    events:
      - http: GET /plans/{plan}
""",
          "src/plans.js": """exports.limits = async (event) => {
  let seats;
  switch (event.http.pathParams.plan) {
    case "free":
      seats = 1;
    case "team":
      seats = 10;
    case "business":
      seats = 50;
      break;
    default:
      seats = 0;
  }
  return { seats };
};
"""}),
      user="GET /plans/free say seats 50. team also 50. only business should be 50",
      steps=[
          S("read_file", path="src/plans.js"),
          S("invoke_local", function="plan-limits", path="/plans/free"),
          S("propose_plan", steps=["Replace the `switch` (its cases fall through without `break`) with a lookup object",
                                   "GET free, team and an unknown plan locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/plans.js", content="""const SEATS = { free: 1, team: 10, business: 50 };

exports.limits = async (event) => {
  return { seats: SEATS[event.http.pathParams.plan] ?? 0 };
};
"""),
          S("invoke_local", function="plan-limits", path="/plans/free"),
          S("invoke_local", function="plan-limits", path="/plans/team"),
          S("invoke_local", function="plan-limits", path="/plans/gold"),
          S("validate"),
      ],
      final="""In a JavaScript `switch`, a `case` without `break` **falls through** into the next one. `free` set 1, then ran `team` (10), then `business` (50) until the `break`. A lookup object can't fall through, and `?? 0` covers unknown plans.

- free: `{"seats": 1}`. team: `{"seats": 10}`. gold: `{"seats": 0}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 385 onprem workflow, numeric choice rule gets a string
    B(385, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": OP("expense-flow", 8705) + """functions:
  read-claim:
    handler: app.claims.read
  auto-approve:
    handler: app.claims.auto_approve
  manager-review:
    handler: app.claims.manager_review
workflows:
  expense:
    start_at: Read
    states:
      Read: {type: task, function: read-claim, next: Route}
      Route:
        type: choice
        choices:
          - {variable: "$.amount", gte: 500, next: Review}
        default: Approve
      Review: {type: task, function: manager-review, end: true}
      Approve: {type: task, function: auto-approve, end: true}
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + """
def read(event, ctx):
    claim = event.data
    return {"id": claim["id"], "amount": claim["amount"].replace(",", "")}


def auto_approve(event, ctx):
    return {"id": event.data["id"], "status": "approved"}


def manager_review(event, ctx):
    return {"id": event.data["id"], "status": "waiting for manager"}
""",
          "requirements.txt": ""}),
      user="expense wf: claim of \"1,200\" auto-approved. Route has gte 500 -> Review. wtf",
      steps=[
          S("get_project"),
          S("read_file", path="app/claims.py"),
          S("invoke_local", function="read-claim", type="workflow", data={"id": "c-9", "amount": "1,200"}),
          S("propose_plan", steps=["Return `amount` as a number (`float(...)`) from read-claim; a numeric rule on a string is false",
                                   "Invoke read-claim with \"1,200\" and \"80\"; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/claims.py", content=FUTURE + """
def read(event, ctx):
    claim = event.data
    return {"id": claim["id"], "amount": float(str(claim["amount"]).replace(",", ""))}


def auto_approve(event, ctx):
    return {"id": event.data["id"], "status": "approved"}


def manager_review(event, ctx):
    return {"id": event.data["id"], "status": "waiting for manager"}
"""),
          S("invoke_local", function="read-claim", type="workflow", data={"id": "c-9", "amount": "1,200"}),
          S("invoke_local", function="read-claim", type="workflow", data={"id": "c-10", "amount": "80"}),
          S("validate"),
      ],
      final="""read-claim returned `"amount": "1200"`, a **string**. A rule whose variable has the wrong type evaluates to false [docs/workflows.md#choice-rules], so `gte: 500` didn't match and `default: Approve` won. It now returns a number.

- `"1,200"`: `{"id": "c-9", "amount": 1200.0}` -> Review.
- `"80"`: `{"id": "c-10", "amount": 80.0}` -> Approve.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 386 onprem http, (status, body) in the wrong order
    B(386, provider="onprem", stage="staging", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": OP("notes-api", 8706) + """functions:
  create-note:
    handler: app.notes.create
    events:
      - http: POST /notes
""",
          "app/__init__.py": "",
          "app/notes.py": FUTURE + """import uuid


def create(event, ctx):
    note = {"id": str(uuid.uuid4()), "text": event.http.json()["text"]}
    return 201, note
""",
          "requirements.txt": ""}),
      user="""status 200, body [201, {"id": "...", "text": "hi"}]
POST /notes. I want 201 with just the note""",
      steps=[
          S("read_file", path="app/notes.py"),
          S("invoke_local", function="create-note", method="POST", path="/notes", data={"text": "hi"}),
          S("propose_plan", steps=["Return `(body, status)`, body first: `return note, 201`",
                                   "POST /notes locally; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/notes.py", content=FUTURE + """import uuid


def create(event, ctx):
    note = {"id": str(uuid.uuid4()), "text": event.http.json()["text"]}
    return note, 201
"""),
          S("invoke_local", function="create-note", method="POST", path="/notes", data={"text": "hi"}),
          S("validate"),
      ],
      final="""The tuple form is `(body, status)`, body first [docs/handlers.md#returning-a-response]. `(201, note)` doesn't match it, so the whole tuple was sent as a JSON list with status 200. Swapped the order.

- After: 201 with `{"id": "<uuid>", "text": "hi"}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 387 onprem smtp, auto-reply answers bounces
    B(387, provider="onprem", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": OP("sales-mail", 8707) + """resources:
  sales-inbox:
    type: smtp
    external: true
    connection: {host: 192.0.2.45, port: 25, domains: sales.example.com}
functions:
  acknowledge:
    handler: app.ack.handle
    events:
      - smtp: sales-inbox
""",
          "app/__init__.py": "",
          "app/ack.py": FUTURE + """
def handle(event, ctx):
    mail = event.data
    return {"reply": {"to": mail["from"], "subject": "We got your message"}}
""",
          "requirements.txt": ""}),
      user="Our acknowledge function sends an automatic \"We got your message\" reply. Last night a mistyped address bounced, our reply went to MAILER-DAEMON, that bounced too, and the logs show hundreds of mails in a loop. Replies must never go to bounce or no-reply senders.",
      steps=[
          S("read_file", path="app/ack.py"),
          S("invoke_local", function="acknowledge", type="smtp",
            data={"from": "MAILER-DAEMON@mx.example.net", "to": ["offers@sales.example.com"], "subject": "Undelivered Mail Returned to Sender", "text": "bounce"}),
          S("propose_plan", steps=["Skip the reply when the sender's local part is mailer-daemon, postmaster, no-reply/noreply or bounce (any case)",
                                   "Invoke with a bounce and a normal mail; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/ack.py", content=FUTURE + """NO_REPLY = {"mailer-daemon", "postmaster", "no-reply", "noreply", "bounce", "bounces"}


def handle(event, ctx):
    mail = event.data
    sender = (mail["from"] or "").lower()
    if not sender or sender.split("@", 1)[0] in NO_REPLY:
        ctx.logger.info("no auto-reply", extra={"from": mail["from"]})
        return {"reply": None}
    return {"reply": {"to": mail["from"], "subject": "We got your message"}}
"""),
          S("invoke_local", function="acknowledge", type="smtp",
            data={"from": "MAILER-DAEMON@mx.example.net", "to": ["offers@sales.example.com"], "subject": "Undelivered Mail Returned to Sender", "text": "bounce"}),
          S("invoke_local", function="acknowledge", type="smtp",
            data={"from": "jo@example.org", "to": ["offers@sales.example.com"], "subject": "Quote", "text": "hello"}),
          S("validate"),
      ],
      final="""The function replied to every sender, including the bounce from MAILER-DAEMON, and each reply produced a new bounce. Now there's no reply when the sender is a bounce or no-reply address (mailer-daemon, postmaster, no-reply, noreply, bounce), and a `no auto-reply` log line instead.

- Bounce: `{"reply": null}`.
- Normal mail: reply to `jo@example.org`.
- validate (onprem, prod): valid.

A real mail program also checks the `auto-submitted` header (in `mail["headers"]`, lower-case keys) [docs/smtp/README.md#what-the-handler-receives]; I can add that check too."""),

    # ------------------------------------------------------------------ 388 onprem http, email without @ gives 500
    B(388, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": OP("invites", 8708) + """functions:
  invite:
    handler: app.invite.create
    events:
      - http: POST /invites
""",
          "app/__init__.py": "",
          "app/invite.py": FUTURE + """ALLOWED_DOMAINS = {"example.com"}


def create(event, ctx):
    email = event.http.json()["email"].strip().lower()
    domain = email.split("@")[1]
    if domain not in ALLOWED_DOMAINS:
        return {"error": "domain not allowed"}, 403
    return {"invited": email}, 201
""",
          "requirements.txt": ""}),
      user="when someone types a name instead of email in the invite form (like \"bob\") we get a 500 error. it should say the email is wrong.",
      steps=[
          S("read_file", path="app/invite.py"),
          S("invoke_local", function="invite", method="POST", path="/invites", data={"email": "bob"}),
          S("propose_plan", steps=["Split with `partition(\"@\")` and raise `BadRequest` when there is no `@` or an empty part",
                                   "POST \"bob\" (400) and a valid address (201) locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/invite.py", content=FUTURE + """from py_serverless_kit import BadRequest

ALLOWED_DOMAINS = {"example.com"}


def create(event, ctx):
    email = str(event.http.json().get("email", "")).strip().lower()
    user, at, domain = email.partition("@")
    if not (user and at and domain):
        raise BadRequest("email must look like name@example.com")
    if domain not in ALLOWED_DOMAINS:
        return {"error": "domain not allowed"}, 403
    return {"invited": email}, 201
"""),
          S("invoke_local", function="invite", method="POST", path="/invites", data={"email": "bob"}),
          S("invoke_local", function="invite", method="POST", path="/invites", data={"email": "Bob@Example.com"}),
          S("validate"),
      ],
      final="""`"bob".split("@")` has only one part, so `[1]` raised IndexError, which is a 500. Now the address is checked first and a wrong one gets a clear 400 [docs/handlers.md#errors].

- `bob`: 400 `email must look like name@example.com`.
- `Bob@Example.com`: 201 `{"invited": "bob@example.com"}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 389 aws http, expiry in milliseconds compared with seconds
    B(389, provider="aws", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AWS("share-links", "us-east-1") + """functions:
  open-link:
    handler: app.links.open_link
    events:
      - http: POST /links/open
""",
          "app/__init__.py": "",
          "app/links.py": FUTURE + """import time

from py_serverless_kit import Forbidden


def open_link(event, ctx):
    link = event.http.json()
    if link["expires_at"] < time.time():
        raise Forbidden("link expired")
    return {"file": link["file"]}
""",
          "requirements.txt": ""}),
      user="Share links never expire. Our frontend creates them with `expires_at: Date.now() + 3600000` (one hour). A link created a week ago with expires_at 1793000000000 still opens. Expired links must give 403.",
      steps=[
          S("read_file", path="app/links.py"),
          S("invoke_local", function="open-link", method="POST", path="/links/open",
            data={"file": "q3.pdf", "expires_at": 1793000000000}),
          S("propose_plan", steps=["Compare in the same unit: `expires_at` is milliseconds (`Date.now()`), `time.time()` is seconds",
                                   "POST an old and a future link locally; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/links.py", content=FUTURE + """import time

from py_serverless_kit import Forbidden


def open_link(event, ctx):
    link = event.http.json()
    expires_s = link["expires_at"] / 1000  # the frontend sends Date.now()-style milliseconds
    if expires_s < time.time():
        raise Forbidden("link expired")
    return {"file": link["file"]}
"""),
          S("invoke_local", function="open-link", method="POST", path="/links/open",
            data={"file": "q3.pdf", "expires_at": 1793000000000}),
          S("invoke_local", function="open-link", method="POST", path="/links/open",
            data={"file": "q3.pdf", "expires_at": 4102444800000}),
          S("validate"),
      ],
      final="""JavaScript's `Date.now()` is in **milliseconds**, Python's `time.time()` in seconds. 1793000000000 ms is a date in 2026, but read as seconds it's tens of thousands of years away, so no link ever expired. The handler now divides by 1000 before comparing.

- Week-old link: 403 `link expired`.
- Link expiring in 2100: 200 `{"file": "q3.pdf"}`.
- validate (aws, prod): valid.

Since the client sets `expires_at`, anyone can change it. For real share links, sign the link on the server."""),

    # ------------------------------------------------------------------ 390 aws http, Node.js indexOf() used as a boolean
    B(390, provider="aws", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AWS("flags-js", "eu-west-3", "  runtime: nodejs20\n") + """functions:
  features:
    handler: src.flags.features
    events:
      - http: GET /features
""",
          "src/flags.js": """const BETA = ["ana", "raj"];

exports.features = async (event) => {
  const user = event.http.query.user;
  return { user, beta: BETA.indexOf(user) ? true : false };
};
"""}),
      user="""GET /features?user=ana -> {"user": "ana", "beta": false}
ana is first in the BETA list. and bob (not in list) gets beta true""",
      steps=[
          S("read_file", path="src/flags.js"),
          S("invoke_local", function="features", path="/features?user=ana"),
          S("propose_plan", steps=["Use `BETA.includes(user)`: `indexOf` returns 0 for the first item (falsy) and -1 when missing (truthy)",
                                   "GET for ana and bob locally; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/flags.js", content="""const BETA = ["ana", "raj"];

exports.features = async (event) => {
  const user = event.http.query.user;
  return { user, beta: BETA.includes(user) };
};
"""),
          S("invoke_local", function="features", path="/features?user=ana"),
          S("invoke_local", function="features", path="/features?user=bob"),
          S("validate"),
      ],
      final="""`indexOf` returns a **position**, not true/false: `0` for ana (the first item, and 0 is falsy) and `-1` for a missing user (any non-zero number is truthy). So it was exactly backwards for those two. `includes()` returns a real boolean.

- ana: `{"user": "ana", "beta": true}`.
- bob: `{"user": "bob", "beta": false}`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 391 aws http, CRLF line endings leave \r in the last column
    B(391, provider="aws", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AWS("payments-import", "eu-west-1") + """functions:
  paid-count:
    handler: app.paid.count
    events:
      - http: POST /payments/paid-count
""",
          "app/__init__.py": "",
          "app/paid.py": FUTURE + """
def count(event, ctx):
    rows = [line.split(",") for line in event.http.text().strip().split("\\n")[1:]]
    paid = [r[0] for r in rows if r[1] == "paid"]
    return {"paid": paid}
""",
          "requirements.txt": ""}),
      user="file from windows excel: paid list only has the last row. same file from mac works. column 2 is status (paid/open)",
      steps=[
          S("read_file", path="app/paid.py"),
          S("invoke_local", function="paid-count", method="POST", path="/payments/paid-count",
            data="id,status\r\np-1,paid\r\np-2,open\r\np-3,paid\r\n"),
          S("propose_plan", steps=["Split lines with `splitlines()` (handles \\r\\n and \\n) and strip each field",
                                   "POST the Windows-style CSV locally; validate for aws (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/paid.py", content=FUTURE + """
def count(event, ctx):
    lines = event.http.text().strip().splitlines()[1:]
    rows = [[field.strip() for field in line.split(",")] for line in lines if line.strip()]
    paid = [r[0] for r in rows if len(r) > 1 and r[1] == "paid"]
    return {"paid": paid}
"""),
          S("invoke_local", function="paid-count", method="POST", path="/payments/paid-count",
            data="id,status\r\np-1,paid\r\np-2,open\r\np-3,paid\r\n"),
          S("validate"),
      ],
      final="""Windows ends lines with `\\r\\n`. Splitting on `\\n` left a `\\r` at the end of every line, so the status was `"paid\\r"`, not `"paid"`. Only the last row worked, because `.strip()` on the whole text removed its `\\r\\n`. `splitlines()` understands both endings, and each field is stripped too.

- Before: `{"paid": ["p-3"]}`. After: `{"paid": ["p-1", "p-3"]}`.
- validate (aws, staging): valid.

If the file can contain quoted commas, switch to the `csv` module."""),

    # ------------------------------------------------------------------ 392 aws schedule, calendar days instead of working days
    B(392, provider="aws", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AWS("sla-report", "eu-central-1") + """functions:
  sla:
    handler: app.sla.run
    events:
      - schedule:
          cron: "0 5 * * 1"
          input:
            tickets:
              - {id: t-1, opened: "2026-10-30", closed: "2026-11-02"}
              - {id: t-2, opened: "2026-11-02", closed: "2026-11-04"}
""",
          "app/__init__.py": "",
          "app/sla.py": FUTURE + """from datetime import date


def run(event, ctx):
    out = {}
    for t in event.data["tickets"]:
        days = (date.fromisoformat(t["closed"]) - date.fromisoformat(t["opened"])).days
        out[t["id"]] = {"days": days, "breached": days > 2}
    return out
""",
          "requirements.txt": ""}),
      user="Our SLA is 2 working days. Ticket t-1 was opened on Friday 2026-10-30 and closed on Monday 2026-11-02, which is 1 working day, but the report counts 3 days and marks it as breached. Weekends must not count.",
      steps=[
          S("read_file", path="app/sla.py"),
          S("invoke_local", function="sla", type="schedule"),
          S("propose_plan", steps=["Count only Monday-Friday days between opened (exclusive) and closed (inclusive)",
                                   "Run with the configured tickets; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sla.py", content=FUTURE + """from datetime import date, timedelta


def working_days(start, end):
    days, day = 0, start
    while day < end:
        day += timedelta(days=1)
        if day.weekday() < 5:
            days += 1
    return days


def run(event, ctx):
    out = {}
    for t in event.data["tickets"]:
        days = working_days(date.fromisoformat(t["opened"]), date.fromisoformat(t["closed"]))
        out[t["id"]] = {"days": days, "breached": days > 2}
    return out
"""),
          S("invoke_local", function="sla", type="schedule"),
          S("validate"),
      ],
      final="""Subtracting dates gives calendar days, weekends included. `working_days()` counts only the Monday-Friday days after the opening day, up to and including the closing day.

- t-1 (Fri to Mon): before 3 days, breached; now 1 day, not breached.
- t-2 (Mon to Wed): 2 days, not breached.
- validate (aws, prod): valid.

Public holidays still count as working days; tell me if you have a holiday list to exclude."""),

    # ------------------------------------------------------------------ 393 gcp http, None from dict.get gives 204
    B(393, provider="gcp", stage="staging", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": G("users-api", "europe-west1") + """functions:
  user:
    handler: app.users.get
    events:
      - http: GET /users/{id}
""",
          "app/__init__.py": "",
          "app/users.py": FUTURE + """USERS = {"u1": {"id": "u1", "name": "Ada"}}


def get(event, ctx):
    return USERS.get(event.http.path_params["id"])
""",
          "requirements.txt": ""}),
      user="GET /users/nope -> 204 empty. want 404",
      steps=[
          S("read_file", path="app/users.py"),
          S("invoke_local", function="user", path="/users/nope"),
          S("propose_plan", steps=["Raise `NotFound` when the user doesn't exist; returning `None` means 204",
                                   "GET /users/nope (404) and /users/u1 (200); validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/users.py", content=FUTURE + """from py_serverless_kit import NotFound

USERS = {"u1": {"id": "u1", "name": "Ada"}}


def get(event, ctx):
    user = USERS.get(event.http.path_params["id"])
    if user is None:
        raise NotFound("no such user")
    return user
"""),
          S("invoke_local", function="user", path="/users/nope"),
          S("invoke_local", function="user", path="/users/u1"),
          S("validate"),
      ],
      final="""`USERS.get()` returns `None` for an unknown id, and a handler returning `None` means `204 No Content` [docs/handlers.md#returning-a-response]. Now it raises `NotFound`.

- `/users/nope`: 404 `no such user`.
- `/users/u1`: 200 `{"id": "u1", "name": "Ada"}`.
- validate (gcp, staging): valid."""),

    # ------------------------------------------------------------------ 394 gcp queue, ISO times with offsets compared as text
    B(394, provider="gcp", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": G("first-login", "europe-west4") + """functions:
  earliest:
    handler: app.logins.handle
    events:
      - queue: logins
""",
          "app/__init__.py": "",
          "app/logins.py": FUTURE + """
def handle(event, ctx):
    logins = [record.json() for record in event.records]
    first = min(logins, key=lambda l: l["at"])
    return {"first": first["user"], "at": first["at"]}
""",
          "requirements.txt": ""}),
      user="Logins come from two regions. Berlin sends `2026-11-01T10:00:00+02:00` (08:00 UTC), London sends `2026-11-01T09:30:00+00:00`. The worker says London was first, but Berlin was half an hour earlier. Times must be compared as real instants.",
      steps=[
          S("read_file", path="app/logins.py"),
          S("invoke_local", function="earliest", type="queue",
            data=[{"user": "berlin-1", "at": "2026-11-01T10:00:00+02:00"}, {"user": "london-1", "at": "2026-11-01T09:30:00+00:00"}]),
          S("propose_plan", steps=["Parse `at` with `datetime.fromisoformat` and compare the datetimes (offsets are applied), not the text",
                                   "Invoke with the two logins; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/logins.py", content=FUTURE + """from datetime import datetime


def handle(event, ctx):
    logins = [record.json() for record in event.records]
    first = min(logins, key=lambda l: datetime.fromisoformat(l["at"]))
    return {"first": first["user"], "at": first["at"]}
"""),
          S("invoke_local", function="earliest", type="queue",
            data=[{"user": "berlin-1", "at": "2026-11-01T10:00:00+02:00"}, {"user": "london-1", "at": "2026-11-01T09:30:00+00:00"}]),
          S("validate"),
      ],
      final="""`min()` compared the strings character by character, and `"09:30"` sorts before `"10:00"`; the `+02:00` was never taken into account. `datetime.fromisoformat()` reads the offset, so the comparison uses the real moments in time.

- Before: london-1 first. After: `{"first": "berlin-1", "at": "2026-11-01T10:00:00+02:00"}`.
- validate (gcp, prod): valid.

On Python 3.9 and 3.10, `fromisoformat` doesn't accept a trailing `Z`; if a producer sends `...Z`, replace it with `+00:00` first."""),

    # ------------------------------------------------------------------ 395 gcp http, quantity string multiplied by a price
    B(395, provider="gcp", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": G("seats", "us-central1") + """functions:
  seat-price:
    handler: app.seats.price
    events:
      - http: POST /seats/price
""",
          "app/__init__.py": "",
          "app/seats.py": FUTURE + """SEAT_PRICE = 2


def price(event, ctx):
    qty = event.http.json()["qty"]
    return {"qty": qty, "total": qty * SEAT_PRICE}
""",
          "requirements.txt": ""}),
      user="I order 3 seats at 2 euro and the total is \"33\". It should be 6! The form sends the number of seats.",
      steps=[
          S("read_file", path="app/seats.py"),
          S("invoke_local", function="seat-price", method="POST", path="/seats/price", data={"qty": "3"}),
          S("propose_plan", steps=["Convert `qty` with `int()` and return 400 when it isn't a whole number from 1 up",
                                   "POST \"3\" and \"x\" locally; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/seats.py", content=FUTURE + """from py_serverless_kit import BadRequest

SEAT_PRICE = 2


def price(event, ctx):
    try:
        qty = int(event.http.json()["qty"])
    except (KeyError, TypeError, ValueError):
        raise BadRequest("qty must be a whole number") from None
    if qty < 1:
        raise BadRequest("qty must be at least 1")
    return {"qty": qty, "total": qty * SEAT_PRICE}
"""),
          S("invoke_local", function="seat-price", method="POST", path="/seats/price", data={"qty": "3"}),
          S("invoke_local", function="seat-price", method="POST", path="/seats/price", data={"qty": "x"}),
          S("validate"),
      ],
      final="""The form sends `"3"` as text, and in Python text times a number repeats the text: `"3" * 2` is `"33"`. The quantity is now converted to a whole number first; anything else gets a 400.

- `"3"`: `{"qty": 3, "total": 6}`.
- `"x"`: 400 `qty must be a whole number`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 396 gcp storage, env var limit used as a number
    B(396, provider="gcp", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#environment-variables"],
      project=dict(files={
          "pskit.yml": G("upload-guard", "europe-west2") + """functions:
  check-size:
    handler: app.guard.handle
    environment:
      MAX_MB: "10"
    events:
      - storage: user-uploads
""",
          "app/__init__.py": "",
          "app/guard.py": FUTURE + """import os

MAX_MB = os.environ.get("MAX_MB", 10)


def handle(event, ctx):
    too_big = [r.key for r in event.records if (r.size or 0) > MAX_MB * 1024 * 1024]
    return {"too_big": too_big}
""",
          "requirements.txt": ""}),
      user="""TypeError: '>' not supported between instances of 'int' and 'str'
check-size. worked in my tests before I set MAX_MB in the function's environment""",
      steps=[
          S("read_file", path="app/guard.py"),
          S("invoke_local", function="check-size", type="storage",
            data=[{"key": "video.mp4", "size": 52428800}, {"key": "cv.pdf", "size": 120000}]),
          S("propose_plan", steps=["Read MAX_MB as a number: `float(os.environ.get(\"MAX_MB\", \"10\"))` (env values are always text)",
                                   "Invoke with a big and a small file; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/guard.py", content=FUTURE + """import os

MAX_MB = float(os.environ.get("MAX_MB", "10"))


def handle(event, ctx):
    too_big = [r.key for r in event.records if (r.size or 0) > MAX_MB * 1024 * 1024]
    return {"too_big": too_big}
"""),
          S("invoke_local", function="check-size", type="storage",
            data=[{"key": "video.mp4", "size": 52428800}, {"key": "cv.pdf", "size": 120000}]),
          S("validate"),
      ],
      final="""Environment variables are always strings [docs/handlers.md#environment-variables]. Without `MAX_MB` you got the default `10` (an int), so your tests passed. Once it was set, `MAX_MB` was `"10"`, and `"10" * 1024 * 1024` *repeats the text* instead of multiplying, which can't be compared with a size. It's now converted with `float()`.

- After: `{"too_big": ["video.mp4"]}` (50 MB > 10 MB).
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 397 azure http, sorting dicts without a key
    B(397, provider="azure", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": AZ("menu-api", "westeurope") + """functions:
  menu:
    handler: app.menu.sorted_menu
    events:
      - http: POST /menu/sorted
""",
          "app/__init__.py": "",
          "app/menu.py": FUTURE + """
def sorted_menu(event, ctx):
    dishes = event.http.json()["dishes"]
    by = event.http.query.get("by", "price")
    return {"by": by, "dishes": sorted(dishes)}
""",
          "requirements.txt": ""}),
      user="""TypeError: '<' not supported between instances of 'dict' and 'dict'
POST /menu/sorted?by=name""",
      steps=[
          S("read_file", path="app/menu.py"),
          S("invoke_local", function="menu", method="POST", path="/menu/sorted?by=name",
            data={"dishes": [{"name": "Soup", "price": 6}, {"name": "Pasta", "price": 11}]}),
          S("propose_plan", steps=["Sort with `key=lambda d: d[by]` and allow only `name` or `price` (400 otherwise)",
                                   "POST with by=name, by=price and by=colour locally; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/menu.py", content=FUTURE + """from py_serverless_kit import BadRequest

SORTABLE = ("name", "price")


def sorted_menu(event, ctx):
    dishes = event.http.json()["dishes"]
    by = event.http.query.get("by", "price")
    if by not in SORTABLE:
        raise BadRequest(f"by must be one of: {', '.join(SORTABLE)}")
    return {"by": by, "dishes": sorted(dishes, key=lambda d: d[by])}
"""),
          S("invoke_local", function="menu", method="POST", path="/menu/sorted?by=name",
            data={"dishes": [{"name": "Soup", "price": 6}, {"name": "Pasta", "price": 11}]}),
          S("invoke_local", function="menu", method="POST", path="/menu/sorted?by=colour",
            data={"dishes": [{"name": "Soup", "price": 6}]}),
          S("validate"),
      ],
      final="""Python can't compare two dicts with `<`, so `sorted(dishes)` fails for any list with more than one dish. The `by` value was read but never used. Now the list is sorted by that field, and only `name` or `price` are accepted.

- `by=name`: Pasta, then Soup.
- `by=colour`: 400 `by must be one of: name, price`.
- validate (azure): valid."""),

    # ------------------------------------------------------------------ 398 azure queue, Decimal plus float
    B(398, provider="azure", stage="staging", mode="ask", page="Logs", persona="informal_non_native",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AZ("fees", "northeurope") + """functions:
  add-fee:
    handler: app.fees.handle
    events:
      - queue: transfers
""",
          "app/__init__.py": "",
          "app/fees.py": FUTURE + """from decimal import Decimal

FEE = 0.35


def handle(event, ctx):
    out = []
    for record in event.records:
        t = record.json()
        amount = Decimal(str(t["amount"]))
        out.append({"id": t["id"], "charged": str(amount + FEE)})
    return {"transfers": out}
""",
          "requirements.txt": ""}),
      user="add-fee crash: TypeError: unsupported operand type(s) for +: 'decimal.Decimal' and 'float'. i use Decimal for money like the docs of python say",
      steps=[
          S("read_file", path="app/fees.py"),
          S("invoke_local", function="add-fee", type="queue", data=[{"id": "tr-1", "amount": 100}]),
          S("propose_plan", steps=["Make the fee a Decimal too: `FEE = Decimal(\"0.35\")` (Decimal and float can't be added)",
                                   "Invoke with one transfer; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/fees.py", content=FUTURE + """from decimal import Decimal

FEE = Decimal("0.35")


def handle(event, ctx):
    out = []
    for record in event.records:
        t = record.json()
        amount = Decimal(str(t["amount"]))
        out.append({"id": t["id"], "charged": str(amount + FEE)})
    return {"transfers": out}
"""),
          S("invoke_local", function="add-fee", type="queue", data=[{"id": "tr-1", "amount": 100}]),
          S("validate"),
      ],
      final="""Decimal is right for money, but Python refuses to mix it with a float, because the float `0.35` isn't exactly 0.35. Write the fee as `Decimal("0.35")` (from a string) and keep all money values Decimal.

- After: `{"transfers": [{"id": "tr-1", "charged": "100.35"}]}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 399 azure schedule, quarter from month // 3
    B(399, provider="azure", stage="prod", mode="ask", page="Test", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("finance-close", "uksouth") + """functions:
  quarter-label:
    handler: app.quarter.run
    events:
      - schedule: "0 4 1 * *"
""",
          "app/__init__.py": "",
          "app/quarter.py": FUTURE + """from datetime import date


def run(event, ctx):
    day = date.fromisoformat((event.data or {}).get("day") or date.today().isoformat())
    return {"label": f"{day.year}-Q{day.month // 3}"}
""",
          "requirements.txt": ""}),
      user="quarter-label: 2026-01-15 -> Q0, 2026-03-01 -> Q1, 2026-12-01 -> Q4. jan must be Q1, dec Q4",
      steps=[
          S("read_file", path="app/quarter.py"),
          S("invoke_local", function="quarter-label", type="schedule", data={"day": "2026-01-15"}),
          S("propose_plan", steps=["Use `(month - 1) // 3 + 1`: months 1-3 -> Q1 ... 10-12 -> Q4",
                                   "Run for January, March, April and December; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/quarter.py", content=FUTURE + """from datetime import date


def run(event, ctx):
    day = date.fromisoformat((event.data or {}).get("day") or date.today().isoformat())
    return {"label": f"{day.year}-Q{(day.month - 1) // 3 + 1}"}
"""),
          S("invoke_local", function="quarter-label", type="schedule", data={"day": "2026-01-15"}),
          S("invoke_local", function="quarter-label", type="schedule", data={"day": "2026-03-01"}),
          S("invoke_local", function="quarter-label", type="schedule", data={"day": "2026-04-01"}),
          S("invoke_local", function="quarter-label", type="schedule", data={"day": "2026-12-01"}),
          S("validate"),
      ],
      final="""`month // 3` gives 0 for Jan-Feb, 1 for Mar-May, and so on: the quarters are shifted. `(month - 1) // 3 + 1` maps 1-3 to Q1, 4-6 to Q2, 7-9 to Q3, 10-12 to Q4. (December was only right by accident.)

- Jan: `2026-Q1`. Mar: `2026-Q1`. Apr: `2026-Q2`. Dec: `2026-Q4`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 400 azure http, list separated by spaces in the config
    B(400, provider="azure", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": AZ("embed-check", "westeurope") + """functions:
  embed-allowed:
    handler: app.embed.check
    environment:
      ALLOWED_SITES: https://shop.example.com https://blog.example.com
    events:
      - http: GET /embed/allowed
""",
          "app/__init__.py": "",
          "app/embed.py": FUTURE + """import os

# ALLOWED_SITES: comma-separated list of site URLs
ALLOWED = {s.strip() for s in os.environ.get("ALLOWED_SITES", "").split(",") if s.strip()}


def check(event, ctx):
    site = event.http.query.get("site", "")
    return {"site": site, "allowed": site in ALLOWED}
""",
          "requirements.txt": ""}),
      user="embed-allowed answers allowed: false for https://blog.example.com, and also for https://shop.example.com. Both are in ALLOWED_SITES on the Functions page. The code hasn't changed in months; a colleague edited the list last week.",
      steps=[
          S("read_file", path="app/embed.py"),
          S("invoke_local", function="embed-allowed", path="/embed/allowed?site=https://blog.example.com"),
          S("get_project"),
          S("propose_plan", steps=["Separate the sites in ALLOWED_SITES with commas, as the code expects (they are separated by a space now)",
                                   "GET /embed/allowed for both sites locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.embed-allowed.environment.ALLOWED_SITES",
            value="https://shop.example.com,https://blog.example.com"),
          S("invoke_local", function="embed-allowed", path="/embed/allowed?site=https://blog.example.com"),
          S("invoke_local", function="embed-allowed", path="/embed/allowed?site=https://shop.example.com"),
      ],
      final="""The code reads `ALLOWED_SITES` as a **comma**-separated list. The edited value used a space, so the whole line became one entry, `https://shop.example.com https://blog.example.com`, and no site matched it. I changed the value to `https://shop.example.com,https://blog.example.com` (`functions.embed-allowed.environment.ALLOWED_SITES`).

- validate (azure, staging): valid.
- blog and shop: both `"allowed": true` now.

A short note in the function's Description saying "comma-separated" helps the next person who edits it."""),
]
