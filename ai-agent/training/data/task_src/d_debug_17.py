"""Category D (fix a handler bug), batch 17. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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
    # ------------------------------------------------------------------ 321 onprem http, Node.js optional query param
    B(321, provider="onprem", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": OP("recipes-js", 8671, "  runtime: nodejs22\n") + """functions:
  search:
    handler: src.search.find
    events:
      - http: GET /recipes
""",
          "src/search.js": """const RECIPES = [
  { name: "pancakes", tags: ["sweet", "quick"] },
  { name: "chili", tags: ["spicy"] },
];

exports.find = async (event) => {
  const wanted = event.http.query.tags.split(",");
  const hits = RECIPES.filter((r) => wanted.every((t) => r.tags.includes(t)));
  return { recipes: hits.map((r) => r.name) };
};
"""}),
      user="""TypeError: Cannot read properties of undefined (reading 'split')
    at exports.find (src/search.js:7)
GET /recipes without ?tags=. should list everything""",
      steps=[
          S("read_file", path="src/search.js"),
          S("invoke_local", function="search", path="/recipes"),
          S("propose_plan", steps=["Treat a missing or empty `tags` as \"no filter\" (`?? \"\"` and drop empty items)",
                                   "GET /recipes and /recipes?tags=sweet locally; validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/search.js", content="""const RECIPES = [
  { name: "pancakes", tags: ["sweet", "quick"] },
  { name: "chili", tags: ["spicy"] },
];

exports.find = async (event) => {
  const wanted = (event.http.query.tags ?? "").split(",").filter(Boolean);
  const hits = RECIPES.filter((r) => wanted.every((t) => r.tags.includes(t)));
  return { recipes: hits.map((r) => r.name) };
};
"""),
          S("invoke_local", function="search", path="/recipes"),
          S("invoke_local", function="search", path="/recipes?tags=sweet"),
          S("validate"),
      ],
      final="""Without `?tags=`, `event.http.query.tags` is `undefined`, and `undefined.split` throws. Now a missing value becomes `""`, and `.filter(Boolean)` drops the empty item, so no tags means no filter (`every` on an empty list is true).

- GET /recipes: `{"recipes": ["pancakes", "chili"]}`.
- GET /recipes?tags=sweet: `{"recipes": ["pancakes"]}`.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 322 onprem storage, handler re-triggers on its own output
    B(322, provider="onprem", stage="prod", mode="ask", page="Logs", persona="detailed_spec",
      sources=["docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": OP("photo-thumbs", 8672) + """functions:
  thumbnail:
    handler: app.thumbs.handle
    events:
      - storage: photos
""",
          "app/__init__.py": "",
          "app/thumbs.py": FUTURE + """
def handle(event, ctx):
    planned = []
    for record in event.records:
        planned.append({"source": record.key, "target": "thumbs/" + record.key})
    # the real code resizes and writes `target` back into the photos bucket
    return {"planned": planned}
""",
          "requirements.txt": ""}),
      user="The thumbnail function on our on-prem host writes thumbs/<key> back into the photos bucket. Since this morning the logs show keys like thumbs/thumbs/thumbs/cat.jpg and the host is busy all the time. One upload should give exactly one thumbnail.",
      steps=[
          S("read_file", path="app/thumbs.py"),
          S("invoke_local", function="thumbnail", type="storage", data=[{"key": "thumbs/cat.jpg"}]),
          S("propose_plan", steps=["Skip objects whose key starts with `thumbs/`: they are the function's own output, which fires the trigger again",
                                   "Invoke with an original and a thumbnail key; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/thumbs.py", content=FUTURE + """PREFIX = "thumbs/"


def handle(event, ctx):
    planned = []
    for record in event.records:
        if record.key.startswith(PREFIX):
            continue  # our own output; writing it fired this trigger again
        planned.append({"source": record.key, "target": PREFIX + record.key})
    # the real code resizes and writes `target` back into the photos bucket
    return {"planned": planned}
"""),
          S("invoke_local", function="thumbnail", type="storage",
            data=[{"key": "cat.jpg"}, {"key": "thumbs/cat.jpg"}]),
          S("validate"),
      ],
      final="""The trigger watches the whole `photos` bucket, so every thumbnail the function writes is a new object that fires it again: `cat.jpg` -> `thumbs/cat.jpg` -> `thumbs/thumbs/cat.jpg` ... Now keys under `thumbs/` are skipped.

- Before: `thumbs/cat.jpg` planned `thumbs/thumbs/cat.jpg`.
- After: only `cat.jpg` -> `thumbs/cat.jpg`; the thumbnail is ignored.
- validate (onprem, prod): valid.

A cleaner layout is a second bucket for thumbnails, or uploads under a prefix with `prefix:` on the storage event [docs/events.md#storage]. Delete the `thumbs/thumbs/...` objects that already exist."""),

    # ------------------------------------------------------------------ 323 onprem workflow, choice compares lower case, task returns upper case
    B(323, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": OP("loan-review", 8673) + """functions:
  score:
    handler: app.review.score
  approve:
    handler: app.review.approve
  manual:
    handler: app.review.manual
workflows:
  review:
    start_at: Score
    states:
      Score: {type: task, function: score, next: Route}
      Route:
        type: choice
        choices:
          - {variable: "$.decision", equals: approve, next: Approve}
        default: Manual
      Approve: {type: task, function: approve, end: true}
      Manual: {type: task, function: manual, end: true}
""",
          "app/__init__.py": "",
          "app/review.py": FUTURE + """
def score(event, ctx):
    points = event.data["points"]
    return {"points": points, "decision": "APPROVE" if points >= 700 else "MANUAL"}


def approve(event, ctx):
    return {"status": "approved", "points": event.data["points"]}


def manual(event, ctx):
    return {"status": "manual review", "points": event.data["points"]}
""",
          "requirements.txt": ""}),
      user="review workflow: every application go to Manual, also points 900. the Route choice look ok to me",
      steps=[
          S("get_project"),
          S("read_file", path="app/review.py"),
          S("invoke_local", function="score", type="workflow", data={"points": 900}),
          S("propose_plan", steps=["Return the decision in lower case (`approve` / `manual`), the value the Route rule compares with",
                                   "Invoke score with 900 and 500; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/review.py", content=FUTURE + """
def score(event, ctx):
    points = event.data["points"]
    return {"points": points, "decision": "approve" if points >= 700 else "manual"}


def approve(event, ctx):
    return {"status": "approved", "points": event.data["points"]}


def manual(event, ctx):
    return {"status": "manual review", "points": event.data["points"]}
"""),
          S("invoke_local", function="score", type="workflow", data={"points": 900}),
          S("invoke_local", function="score", type="workflow", data={"points": 500}),
          S("validate"),
      ],
      final="""The rule is fine, the value isn't: Score returns `"APPROVE"` and Route checks `equals: approve`. `equals` is an exact comparison, so `"APPROVE"` never matches and `default: Manual` wins [docs/workflows.md#choice-rules]. Score now returns lower case.

- 900: `{"points": 900, "decision": "approve"}` -> Approve.
- 500: `{"points": 500, "decision": "manual"}` -> Manual.
- validate (onprem, staging): valid. Run the whole workflow with Deploy > Run a workflow locally."""),

    # ------------------------------------------------------------------ 324 onprem http, resource connection values are strings
    B(324, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#what-handlers-receive", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": OP("orders-svc", 8674) + """resources:
  orders-db:
    type: database
    external: true
    connection: {host: db.internal.example.com, port: 5432, pool_size: 4}
    functions: [pool-info]
functions:
  pool-info:
    handler: app.db.info
    events:
      - http: GET /pool
""",
          "app/__init__.py": "",
          "app/db.py": FUTURE + """from py_serverless_kit import resource


def info(event, ctx):
    db = resource("orders-db")
    size = db.get("pool_size", 5)
    slots = [f"conn-{i}" for i in range(size)]
    return {"host": db.get("host"), "port": db.get("port"), "slots": slots}
""",
          "requirements.txt": ""}),
      user="""TypeError: 'str' object cannot be interpreted as an integer
started after I added pool_size: 4 to the orders-db connection on the Resources page""",
      steps=[
          S("read_file", path="app/db.py"),
          S("invoke_local", function="pool-info", path="/pool"),
          S("propose_plan", steps=["Convert the connection values to `int` in the handler (`pool_size`, `port`): bindings arrive as text",
                                   "GET /pool locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/db.py", content=FUTURE + """from py_serverless_kit import resource


def info(event, ctx):
    db = resource("orders-db")
    size = int(db.get("pool_size", 5))
    slots = [f"conn-{i}" for i in range(size)]
    return {"host": db.get("host"), "port": int(db.get("port", 5432)), "slots": slots}
"""),
          S("invoke_local", function="pool-info", path="/pool"),
          S("validate"),
      ],
      final="""Resource bindings reach the function as environment variables (`PSKIT_RESOURCE_ORDERS_DB_POOL_SIZE=...`), so every `connection` value is a **string**: `"4"`, not `4` [docs/resources.md#what-handlers-receive]. Without `pool_size` you got the default `5` (an int), which is why it only broke after you added it. The handler now converts with `int()`; `port` too.

- GET /pool: 200, 4 slots (`conn-0` .. `conn-3`), `port: 5432` as a number.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 325 onprem smtp, Bcc'd mail routed by the To header
    B(325, provider="onprem", stage="prod", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": OP("mail-router", 8675) + """resources:
  inbound-mail:
    type: smtp
    external: true
    connection: {host: 192.0.2.42, port: 25, domains: corp.example.com}
functions:
  route-mail:
    handler: app.router.handle
    events:
      - smtp: inbound-mail
""",
          "app/__init__.py": "",
          "app/router.py": FUTURE + """TEAMS = {"sales@corp.example.com": "sales", "jobs@corp.example.com": "hr"}


def handle(event, ctx):
    mail = event.data
    teams = sorted({TEAMS[a] for a in mail["to"] if a in TEAMS})
    return {"teams": teams or ["unrouted"]}
""",
          "requirements.txt": ""}),
      user="route-mail sends a mail to the team whose address it was sent to. When a partner writes to their own colleague and puts sales@corp.example.com in Bcc, the mail ends up as \"unrouted\". Bcc'd mail to our addresses should be routed like any other.",
      steps=[
          S("read_file", path="app/router.py"),
          S("invoke_local", function="route-mail", type="smtp",
            data={"from": "pat@partner.example.org", "to": ["lee@partner.example.org"], "bcc": ["sales@corp.example.com"], "subject": "Offer", "text": "see attached"}),
          S("propose_plan", steps=["Route by the SMTP envelope (`mail[\"envelope\"][\"rcpt_to\"]`, the real recipients on this server) instead of the To header",
                                   "Invoke with a Bcc'd mail and a normal one; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/router.py", content=FUTURE + """TEAMS = {"sales@corp.example.com": "sales", "jobs@corp.example.com": "hr"}


def handle(event, ctx):
    mail = event.data
    recipients = mail["envelope"]["rcpt_to"]
    teams = sorted({TEAMS[a.lower()] for a in recipients if a.lower() in TEAMS})
    return {"teams": teams or ["unrouted"]}
"""),
          S("invoke_local", function="route-mail", type="smtp",
            data={"from": "pat@partner.example.org", "to": ["lee@partner.example.org"], "bcc": ["sales@corp.example.com"], "subject": "Offer", "text": "see attached"}),
          S("invoke_local", function="route-mail", type="smtp",
            data={"from": "ann@example.org", "to": ["Jobs@corp.example.com"], "subject": "CV", "text": "hello"}),
          S("validate"),
      ],
      final="""Bcc addresses are never in the To header, so `mail["to"]` only had the partner's colleague. The SMTP **envelope** lists who the mail was really delivered to on your server: `mail["envelope"]["rcpt_to"]` [docs/smtp/README.md#what-the-handler-receives]. The router uses that now, and compares addresses in lower case.

- Bcc to sales: `{"teams": ["sales"]}`.
- To `Jobs@corp.example.com`: `{"teams": ["hr"]}`.
- validate (onprem, prod): valid."""),

    # ------------------------------------------------------------------ 326 onprem queue, remaining_time_ms() is None locally
    B(326, provider="onprem", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": OP("video-jobs", 8676) + """functions:
  transcode:
    handler: app.transcode.handle
    timeout: 120
    events:
      - queue: videos
""",
          "app/__init__.py": "",
          "app/transcode.py": FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        if ctx.remaining_time_ms() < 20000:
            result.fail(record)  # not enough time left: retry later
            continue
        ctx.logger.info("transcoding", extra={"video": record.json()["video"]})
    return result
""",
          "requirements.txt": ""}),
      user="When I click Run locally on the Test page I get TypeError: '<' not supported between instances of 'NoneType' and 'int'. What is None?",
      steps=[
          S("read_file", path="app/transcode.py"),
          S("invoke_local", function="transcode", type="queue", data=[{"video": "intro.mp4"}]),
          S("propose_plan", steps=["Read `ctx.remaining_time_ms()` once and only compare it when it isn't `None` (no time limit is known locally)",
                                   "Run the queue event locally and validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/transcode.py", content=FUTURE + """from py_serverless_kit import BatchResult


def handle(event, ctx):
    result = BatchResult()
    for record in event.records:
        left = ctx.remaining_time_ms()
        if left is not None and left < 20000:
            result.fail(record)  # not enough time left: retry later
            continue
        ctx.logger.info("transcoding", extra={"video": record.json()["video"]})
    return result
"""),
          S("invoke_local", function="transcode", type="queue", data=[{"video": "intro.mp4"}]),
          S("validate"),
      ],
      final="""`ctx.remaining_time_ms()` is None. It returns the milliseconds left before the timeout, or `None` when that isn't known [docs/handlers.md#context]. A local run has no timeout, so it is `None`, and `None < 20000` fails. The handler now skips the check when the value is `None`.

- Run locally: `{"batchItemFailures": []}` (nothing failed), with a `transcoding` log line.
- validate (onprem): valid."""),

    # ------------------------------------------------------------------ 327 onprem http, round() rounds half to even
    B(327, provider="onprem", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": OP("reviews", 8677) + """functions:
  stars:
    handler: app.stars.summary
    events:
      - http: POST /stars
""",
          "app/__init__.py": "",
          "app/stars.py": FUTURE + """
def summary(event, ctx):
    ratings = event.http.json()["ratings"]
    avg = sum(ratings) / len(ratings)
    return {"average": avg, "stars": round(avg)}
""",
          "requirements.txt": ""}),
      user="ratings [2, 3] average 2.5 and stars say 2. but [3, 4] average 3.5 give 4. why different? 2.5 must be 3 stars",
      steps=[
          S("read_file", path="app/stars.py"),
          S("invoke_local", function="stars", method="POST", path="/stars", data={"ratings": [2, 3]}),
          S("propose_plan", steps=["Round halves up with `math.floor(avg + 0.5)`: `round()` rounds .5 to the even number",
                                   "POST [2, 3] and [3, 4] locally; validate for onprem (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/stars.py", content=FUTURE + """import math


def summary(event, ctx):
    ratings = event.http.json()["ratings"]
    avg = sum(ratings) / len(ratings)
    return {"average": avg, "stars": math.floor(avg + 0.5)}
"""),
          S("invoke_local", function="stars", method="POST", path="/stars", data={"ratings": [2, 3]}),
          S("invoke_local", function="stars", method="POST", path="/stars", data={"ratings": [3, 4]}),
          S("validate"),
      ],
      final="""Python's `round()` rounds an exact .5 to the **even** number: `round(2.5)` is 2, `round(3.5)` is 4. `math.floor(avg + 0.5)` always rounds halves up (fine for positive ratings).

- [2, 3]: `{"average": 2.5, "stars": 3}`.
- [3, 4]: `{"average": 3.5, "stars": 4}`.
- validate (onprem, staging): valid."""),

    # ------------------------------------------------------------------ 328 onprem http, any() where all() was meant
    B(328, provider="onprem", stage="prod", mode="ask", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": OP("docs-admin", 8678) + """functions:
  delete-doc:
    handler: app.docs.delete
    events:
      - http: DELETE /docs/{id}
""",
          "app/__init__.py": "",
          "app/docs.py": FUTURE + """from py_serverless_kit import Forbidden

REQUIRED = ("editor", "admin")


def delete(event, ctx):
    roles = [r.strip() for r in event.http.query.get("roles", "").split(",")]
    if not any(r in roles for r in REQUIRED):
        raise Forbidden("editor and admin roles required")
    return {"deleted": event.http.path_params["id"]}
""",
          "requirements.txt": ""}),
      user="delete-doc must need editor AND admin. user with only editor can delete. roles come in ?roles= from our gateway",
      steps=[
          S("read_file", path="app/docs.py"),
          S("invoke_local", function="delete-doc", method="DELETE", path="/docs/d-9?roles=editor"),
          S("propose_plan", steps=["Use `all(...)` instead of `any(...)`: every required role must be present",
                                   "DELETE with editor (403) and editor,admin (200) locally; validate for onprem (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/docs.py", content=FUTURE + """from py_serverless_kit import Forbidden

REQUIRED = ("editor", "admin")


def delete(event, ctx):
    roles = {r.strip() for r in event.http.query.get("roles", "").split(",")}
    if not all(r in roles for r in REQUIRED):
        raise Forbidden("editor and admin roles required")
    return {"deleted": event.http.path_params["id"]}
"""),
          S("invoke_local", function="delete-doc", method="DELETE", path="/docs/d-9?roles=editor"),
          S("invoke_local", function="delete-doc", method="DELETE", path="/docs/d-9?roles=editor,admin"),
          S("validate"),
      ],
      final="""`any()` is true when **one** required role is there; `all()` needs every one. Switched to `all()`.

- `roles=editor`: was 200, now 403 `editor and admin roles required`.
- `roles=editor,admin`: 200 `{"deleted": "d-9"}`.
- validate (onprem, prod): valid.

This trusts the `roles` query value, so make sure only your gateway can reach the host (auth on premises is `none`; check identity in the handler)."""),

    # ------------------------------------------------------------------ 329 aws http, Node.js `in` on an array
    B(329, provider="aws", stage="dev", mode="ask", page="Test", persona="pasted_error",
      sources=["docs/nodejs.md#handlers"],
      project=dict(files={
          "pskit.yml": AWS("billing-js", "eu-west-2", "  runtime: nodejs20\n") + """functions:
  refunds:
    handler: src.refunds.create
    events:
      - http: POST /refunds
""",
          "src/refunds.js": """const { Forbidden } = require("pskit");

const ALLOWED = ["admin", "finance"];

exports.create = async (event) => {
  const { role, amount } = event.http.json();
  if (!(role in ALLOWED)) throw new Forbidden("not allowed to refund");
  return { refunded: amount };
};
"""}),
      user="""{"error": "not allowed to refund", "status": 403}
role "admin" gets 403 on POST /refunds. ALLOWED has admin""",
      steps=[
          S("read_file", path="src/refunds.js"),
          S("invoke_local", function="refunds", method="POST", path="/refunds", data={"role": "admin", "amount": 20}),
          S("propose_plan", steps=["Use `ALLOWED.includes(role)`: `in` checks array indexes (0, 1), not values",
                                   "POST as admin (200) and as intern (403) locally; validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="src/refunds.js", content="""const { Forbidden } = require("pskit");

const ALLOWED = ["admin", "finance"];

exports.create = async (event) => {
  const { role, amount } = event.http.json();
  if (!ALLOWED.includes(role)) throw new Forbidden("not allowed to refund");
  return { refunded: amount };
};
"""),
          S("invoke_local", function="refunds", method="POST", path="/refunds", data={"role": "admin", "amount": 20}),
          S("invoke_local", function="refunds", method="POST", path="/refunds", data={"role": "intern", "amount": 20}),
          S("validate"),
      ],
      final="""In JavaScript, `x in array` asks whether `x` is an **index** (or property) of the array: `"0" in ALLOWED` is true, `"admin" in ALLOWED` is false. `ALLOWED.includes(role)` checks the values.

- admin: 200 `{"refunded": 20}`.
- intern: 403 `not allowed to refund`.
- validate (aws): valid."""),

    # ------------------------------------------------------------------ 330 aws queue, dedupe by message id instead of order id
    B(330, provider="aws", stage="prod", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AWS("order-events", "us-east-2") + """functions:
  collect:
    handler: app.collect.handle
    events:
      - queue:
          name: order-events
          batch_size: 10
""",
          "app/__init__.py": "",
          "app/collect.py": FUTURE + """
def handle(event, ctx):
    seen, orders = set(), []
    for record in event.records:
        if record.id in seen:
            continue
        seen.add(record.id)
        orders.append(record.json()["order_id"])
    return {"orders": orders}
""",
          "requirements.txt": ""}),
      user="Our checkout service sometimes publishes the same order twice to SQS (a retry on its side). I dedupe in the worker by message id, the same way I did in my old Lambda, but duplicates still get through: two messages for order 1001 both end up in the result. I expected [1001, 1002].",
      steps=[
          S("read_file", path="app/collect.py"),
          S("invoke_local", function="collect", type="queue",
            data=[{"order_id": 1001}, {"order_id": 1001}, {"order_id": 1002}]),
          S("propose_plan", steps=["Dedupe by the business key `order_id` from the body: a re-published message gets a new message id",
                                   "Invoke with a duplicate order; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/collect.py", content=FUTURE + """
def handle(event, ctx):
    seen, orders = set(), []
    for record in event.records:
        order_id = record.json()["order_id"]
        if order_id in seen:
            continue
        seen.add(order_id)
        orders.append(order_id)
    return {"orders": orders}
"""),
          S("invoke_local", function="collect", type="queue",
            data=[{"order_id": 1001}, {"order_id": 1001}, {"order_id": 1002}]),
          S("validate"),
      ],
      final="""When the producer publishes the same order twice, those are two different messages, each with its own message id (`local-0`, `local-1` here, SQS ids in AWS). So `record.id` never repeats. Dedupe by `order_id`, the value that identifies the order.

- Before: `[1001, 1001, 1002]`. After: `{"orders": [1001, 1002]}`.
- validate (aws, prod): valid.

This only removes duplicates inside one batch. Across batches you need a store of seen ids (for example a DynamoDB conditional write)."""),

    # ------------------------------------------------------------------ 331 aws schedule, input value quoted in the config
    B(331, provider="aws", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AWS("cleanup", "ap-southeast-2") + """functions:
  purge-old:
    handler: app.purge.run
    events:
      - schedule:
          rate: 1 day
          input: {days: "30"}
""",
          "app/__init__.py": "",
          "app/purge.py": FUTURE + """from datetime import date, timedelta


def run(event, ctx):
    today = date.fromisoformat(event.data.get("today", date.today().isoformat()))
    cutoff = today - timedelta(days=event.data["days"])
    return {"delete_before": cutoff.isoformat()}
""",
          "requirements.txt": ""}),
      user="purge-old crashes with TypeError: unsupported type for timedelta days component: str. I didn't change the code, only the days on the Functions page",
      steps=[
          S("read_file", path="app/purge.py"),
          S("get_project"),
          S("invoke_local", function="purge-old", type="schedule"),
          S("propose_plan", steps=["Make the schedule input a number: `days: 30` instead of the text `\"30\"`",
                                   "Run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.purge-old.events.0.schedule.input", value={"days": 30}),
          S("invoke_local", function="purge-old", type="schedule"),
      ],
      final="""The code is fine; the schedule input in pskit.yml changed to `days: "30"`, with quotes, so the function got the **text** "30", and `timedelta(days="30")` needs a number. I set `input` to `{days: 30}` (`functions.purge-old.events.0.schedule.input`).

- validate (aws, staging): valid.
- Run: `delete_before` is 30 days before today.

When you type input values on the Functions page, numbers must not be quoted."""),

    # ------------------------------------------------------------------ 332 aws http, variable only set in one branch
    B(332, provider="aws", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": AWS("cart-api", "eu-north-1") + """functions:
  checkout:
    handler: app.cart.checkout
    events:
      - http: POST /checkout
""",
          "app/__init__.py": "",
          "app/cart.py": FUTURE + """COUPONS = {"WELCOME10": 0.10, "VIP20": 0.20}


def checkout(event, ctx):
    body = event.http.json()
    subtotal = body["subtotal"]
    code = body.get("coupon")
    if code in COUPONS:
        discount = round(subtotal * COUPONS[code], 2)
    return {"subtotal": subtotal, "discount": discount, "total": round(subtotal - discount, 2)}
""",
          "requirements.txt": ""}),
      user="""UnboundLocalError: local variable 'discount' referenced before assignment
POST /checkout {"subtotal": 50} -> 500. with coupon WELCOME10 it works""",
      steps=[
          S("read_file", path="app/cart.py"),
          S("invoke_local", function="checkout", method="POST", path="/checkout", data={"subtotal": 50}),
          S("propose_plan", steps=["Start with `discount = 0.0` so a missing or unknown coupon gives no discount",
                                   "POST without and with a coupon locally; validate for aws (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/cart.py", content=FUTURE + """COUPONS = {"WELCOME10": 0.10, "VIP20": 0.20}


def checkout(event, ctx):
    body = event.http.json()
    subtotal = body["subtotal"]
    discount = 0.0
    code = body.get("coupon")
    if code in COUPONS:
        discount = round(subtotal * COUPONS[code], 2)
    return {"subtotal": subtotal, "discount": discount, "total": round(subtotal - discount, 2)}
"""),
          S("invoke_local", function="checkout", method="POST", path="/checkout", data={"subtotal": 50}),
          S("invoke_local", function="checkout", method="POST", path="/checkout", data={"subtotal": 50, "coupon": "WELCOME10"}),
          S("validate"),
      ],
      final="""`discount` was only assigned inside `if code in COUPONS:`. With no coupon (or an unknown one) the variable never existed when the `return` line used it. It now starts at `0.0`.

- No coupon: `{"subtotal": 50, "discount": 0.0, "total": 50.0}`.
- WELCOME10: `{"subtotal": 50, "discount": 5.0, "total": 45.0}`.
- validate (aws, prod): valid.

Should an unknown coupon code give a 400 instead of silently no discount? I can add that."""),

    # ------------------------------------------------------------------ 333 gcp http, running total reset inside the loop
    B(333, provider="gcp", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": G("expenses") + """functions:
  report:
    handler: app.expenses.report
    events:
      - http: POST /expenses/report
""",
          "app/__init__.py": "",
          "app/expenses.py": FUTURE + """from app.money import total_of


def report(event, ctx):
    items = event.http.json()["items"]
    return {"count": len(items), "total": total_of(items)}
""",
          "app/money.py": FUTURE + """
def total_of(items):
    for item in items:
        total = 0
        total += item["amount"]
    return round(total, 2)
""",
          "requirements.txt": ""}),
      user="expense report total = only the last expense. 3 items 10 + 20 + 5 show 5",
      steps=[
          S("read_file", path="app/expenses.py"),
          S("read_file", path="app/money.py"),
          S("invoke_local", function="report", method="POST", path="/expenses/report",
            data={"items": [{"amount": 10}, {"amount": 20}, {"amount": 5}]}),
          S("propose_plan", steps=["In app/money.py, set `total = 0` once before the loop (it was reset for every item)",
                                   "POST the 3 items locally; validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/money.py", content=FUTURE + """
def total_of(items):
    total = 0
    for item in items:
        total += item["amount"]
    return round(total, 2)
"""),
          S("invoke_local", function="report", method="POST", path="/expenses/report",
            data={"items": [{"amount": 10}, {"amount": 20}, {"amount": 5}]}),
          S("validate"),
      ],
      final="""The bug is in app/money.py: `total = 0` was inside the loop, so it went back to 0 for every item and only the last amount was left. It's now set once, before the loop. This also fixes an empty list, which used to crash because `total` was never set.

- Before: `total: 5`. After: `{"count": 3, "total": 35}`.
- validate (gcp): valid."""),

    # ------------------------------------------------------------------ 334 gcp storage, unquote_plus copied from S3 code
    B(334, provider="gcp", stage="staging", mode="ask", page="Test", persona="aws_migrator",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": G("notes-index", "us-east1") + """functions:
  index-note:
    handler: app.index.handle
    events:
      - storage: notes
""",
          "app/__init__.py": "",
          "app/index.py": FUTURE + """from urllib.parse import unquote_plus


def handle(event, ctx):
    return {"indexed": [unquote_plus(r.key) for r in event.records]}
""",
          "requirements.txt": ""}),
      user="I ported our S3 indexer to GCS. An object named `c++ tips.txt` gets indexed as `c   tips.txt`, with the pluses turned into spaces. On AWS this exact code was correct.",
      steps=[
          S("read_file", path="app/index.py"),
          S("invoke_local", function="index-note", type="storage", data=[{"key": "c++ tips.txt"}]),
          S("propose_plan", steps=["Remove `unquote_plus`: `record.key` is already the plain object name",
                                   "Invoke with `c++ tips.txt`; validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/index.py", content=FUTURE + """
def handle(event, ctx):
    return {"indexed": [r.key for r in event.records]}
"""),
          S("invoke_local", function="index-note", type="storage", data=[{"key": "c++ tips.txt"}]),
          S("validate"),
      ],
      final="""Raw S3 event notifications URL-encode the key (a space arrives as `+`), so the old code had to decode it. `record.key` is already the plain object name [docs/handlers.md#record]. Decoding it again turned each real `+` into a space. The handler now uses `record.key` as it is.

- Before: `c   tips.txt`. After: `{"indexed": ["c++ tips.txt"]}`.
- validate (gcp, staging): valid.

pskit's AWS adapter decodes the S3 key too, so this version also works if you deploy it to AWS again."""),

    # ------------------------------------------------------------------ 335 gcp queue, null user in some events
    B(335, provider="gcp", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#batchresult"],
      project=dict(files={
          "pskit.yml": G("analytics", "europe-west4") + """functions:
  per-user:
    handler: app.per_user.handle
    events:
      - queue: clicks
""",
          "app/__init__.py": "",
          "app/per_user.py": FUTURE + """
def handle(event, ctx):
    counts = {}
    for record in event.records:
        click = record.json()
        uid = click["user"]["id"]
        counts[uid] = counts.get(uid, 0) + 1
    return {"users": counts}
""",
          "requirements.txt": ""}),
      user="""TypeError: 'NoneType' object is not subscriptable
per-user, line 7. happens for clicks from people who aren't logged in, the web tracker sends "user": null""",
      steps=[
          S("read_file", path="app/per_user.py"),
          S("invoke_local", function="per-user", type="queue",
            data=[{"user": {"id": "u1"}, "page": "/"}, {"user": None, "page": "/pricing"}]),
          S("propose_plan", steps=["Count clicks with `\"user\": null` (or no user) under `anonymous` instead of indexing None",
                                   "Invoke with a logged-in and an anonymous click; validate for gcp (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/per_user.py", content=FUTURE + """
def handle(event, ctx):
    counts = {}
    for record in event.records:
        click = record.json()
        uid = (click.get("user") or {}).get("id") or "anonymous"
        counts[uid] = counts.get(uid, 0) + 1
    return {"users": counts}
"""),
          S("invoke_local", function="per-user", type="queue",
            data=[{"user": {"id": "u1"}, "page": "/"}, {"user": None, "page": "/pricing"}]),
          S("validate"),
      ],
      final="""`click["user"]` is `None` for anonymous clicks, and `None["id"]` raises that TypeError. Because the exception failed the whole batch, every click in it was redelivered, the good ones too. Now a null or missing user counts as `anonymous`.

- After: `{"users": {"u1": 1, "anonymous": 1}}`.
- validate (gcp, prod): valid."""),

    # ------------------------------------------------------------------ 336 gcp schedule, input written as a JSON string in the config
    B(336, provider="gcp", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": G("feeds") + """functions:
  refresh-feeds:
    handler: app.feeds.refresh
    events:
      - schedule:
          rate: 15 minutes
          input: '{"feeds": ["news", "sport"]}'
""",
          "app/__init__.py": "",
          "app/feeds.py": FUTURE + """
def refresh(event, ctx):
    return {"refreshed": [f"feed:{name}" for name in event.data["feeds"]]}
""",
          "requirements.txt": ""}),
      user="refresh-feeds: TypeError: string indices must be integers. schedule input looks right in yaml",
      steps=[
          S("get_project"),
          S("invoke_local", function="refresh-feeds", type="schedule"),
          S("propose_plan", steps=["Write `input` as a YAML mapping, not a quoted JSON string, so `event.data` is a dict",
                                   "Run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.refresh-feeds.events.0.schedule.input", value={"feeds": ["news", "sport"]}),
          S("invoke_local", function="refresh-feeds", type="schedule"),
      ],
      final="""`input` was in single quotes, so YAML read it as one **string** that looks like JSON. `event.data` was that string, and `event.data["feeds"]` fails on a str. I made it a real mapping: `input: {feeds: [news, sport]}`.

- validate (gcp): valid.
- Run: `{"refreshed": ["feed:news", "feed:sport"]}`."""),

    # ------------------------------------------------------------------ 337 azure http, helper module uses an undefined logger
    B(337, provider="azure", stage="staging", mode="ask", page="Logs", persona="pasted_error",
      sources=["docs/handlers.md#logging"],
      project=dict(files={
          "pskit.yml": AZ("geo-lookup", "francecentral") + """functions:
  country:
    handler: app.api.country
    events:
      - http: GET /country/{code}
""",
          "app/__init__.py": "",
          "app/api.py": FUTURE + """from py_serverless_kit import NotFound

from app.lookup import find_country


def country(event, ctx):
    found = find_country(event.http.path_params["code"])
    if found is None:
        raise NotFound("unknown country code")
    return found
""",
          "app/lookup.py": FUTURE + """COUNTRIES = {"FR": "France", "DE": "Germany"}


def find_country(code):
    name = COUNTRIES.get(code.upper())
    if name is None:
        logger.warning("unknown code %s", code)
        return None
    return {"code": code.upper(), "name": name}
""",
          "requirements.txt": ""}),
      user="""NameError: name 'logger' is not defined
  File "app/lookup.py", line 7, in find_country
GET /country/xx. known codes work""",
      steps=[
          S("read_file", path="app/lookup.py"),
          S("invoke_local", function="country", path="/country/xx"),
          S("propose_plan", steps=["Define a module logger in app/lookup.py with `logging.getLogger(__name__)`",
                                   "GET /country/xx (404) and /country/fr (200) locally; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/lookup.py", content=FUTURE + """import logging

logger = logging.getLogger(__name__)

COUNTRIES = {"FR": "France", "DE": "Germany"}


def find_country(code):
    name = COUNTRIES.get(code.upper())
    if name is None:
        logger.warning("unknown code %s", code)
        return None
    return {"code": code.upper(), "name": name}
"""),
          S("invoke_local", function="country", path="/country/xx"),
          S("invoke_local", function="country", path="/country/fr"),
          S("validate"),
      ],
      final="""app/lookup.py used `logger` but never created one. Python only looks the name up when that line runs, which is why only unknown codes crashed. The module now has `logger = logging.getLogger(__name__)`. In the handler itself you can also use `ctx.logger` [docs/handlers.md#logging].

- `/country/xx`: 404 `unknown country code`, with the warning logged.
- `/country/fr`: 200 `{"code": "FR", "name": "France"}`.
- validate (azure, staging): valid."""),

    # ------------------------------------------------------------------ 338 azure queue, cents shown without two decimals
    B(338, provider="azure", stage="dev", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/handlers.md#record"],
      project=dict(files={
          "pskit.yml": AZ("receipts", "westeurope") + """functions:
  receipt-line:
    handler: app.receipts.handle
    events:
      - queue: payments
""",
          "app/__init__.py": "",
          "app/receipts.py": FUTURE + """
def handle(event, ctx):
    lines = []
    for record in event.records:
        p = record.json()
        lines.append(f"{p['item']}: EUR {p['amount_cents'] / 100}")
    return {"lines": lines}
""",
          "requirements.txt": ""}),
      user="Payment messages carry amount_cents. The receipt line for 1990 cents reads `EUR 19.9` and for 500 cents `EUR 5.0`. Receipts must always show two decimals: `EUR 19.90`, `EUR 5.00`.",
      steps=[
          S("read_file", path="app/receipts.py"),
          S("invoke_local", function="receipt-line", type="queue",
            data=[{"item": "Mug", "amount_cents": 1990}, {"item": "Pen", "amount_cents": 500}]),
          S("propose_plan", steps=["Format with integer math: `divmod(cents, 100)` and `{:02d}` for the cents part",
                                   "Invoke with 1990 and 500 cents; validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/receipts.py", content=FUTURE + """
def euros(cents):
    whole, rest = divmod(int(cents), 100)
    return f"{whole}.{rest:02d}"


def handle(event, ctx):
    lines = []
    for record in event.records:
        p = record.json()
        lines.append(f"{p['item']}: EUR {euros(p['amount_cents'])}")
    return {"lines": lines}
"""),
          S("invoke_local", function="receipt-line", type="queue",
            data=[{"item": "Mug", "amount_cents": 1990}, {"item": "Pen", "amount_cents": 500}]),
          S("validate"),
      ],
      final="""`1990 / 100` is the float `19.9`, and an f-string prints a float as short as possible. `euros()` now splits the cents with `divmod` and pads the rest to two digits. That stays exact (no float) and always shows two decimals.

- Before: `Mug: EUR 19.9`, `Pen: EUR 5.0`.
- After: `Mug: EUR 19.90`, `Pen: EUR 5.00`.
- validate (azure): valid.

Negative amounts (refunds) would need a sign handled separately; tell me if those come through this queue."""),

    # ------------------------------------------------------------------ 339 azure http, percent change when the old value is 0
    B(339, provider="azure", stage="prod", mode="ask", page="Logs", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": AZ("kpi-api", "uksouth") + """functions:
  growth:
    handler: app.kpi.growth
    events:
      - http: POST /kpi/growth
""",
          "app/__init__.py": "",
          "app/kpi.py": FUTURE + """
def growth(event, ctx):
    body = event.http.json()
    before, now = body["before"], body["now"]
    return {"change_pct": round((now - before) / before * 100, 1)}
""",
          "requirements.txt": ""}),
      user="the growth api crashes for a new product. it had 0 sales last month and 12 this month. error says ZeroDivisionError",
      steps=[
          S("read_file", path="app/kpi.py"),
          S("invoke_local", function="growth", method="POST", path="/kpi/growth", data={"before": 0, "now": 12}),
          S("propose_plan", steps=["When `before` is 0, return `change_pct: null` (a percentage of 0 has no meaning) instead of dividing",
                                   "POST 0 -> 12 and 10 -> 12 locally; validate for azure (prod)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/kpi.py", content=FUTURE + """
def growth(event, ctx):
    body = event.http.json()
    before, now = body["before"], body["now"]
    if before == 0:
        return {"change_pct": None, "note": "no earlier value to compare with"}
    return {"change_pct": round((now - before) / before * 100, 1)}
"""),
          S("invoke_local", function="growth", method="POST", path="/kpi/growth", data={"before": 0, "now": 12}),
          S("invoke_local", function="growth", method="POST", path="/kpi/growth", data={"before": 10, "now": 12}),
          S("validate"),
      ],
      final="""Growth in percent divides by last month's value, and you can't divide by 0. Now a 0 before gives `change_pct: null` with a short note, instead of a 500 error.

- 0 -> 12: `{"change_pct": null, "note": "no earlier value to compare with"}`.
- 10 -> 12: `{"change_pct": 20.0}`.
- validate (azure, prod): valid."""),

    # ------------------------------------------------------------------ 340 azure schedule, date checked against a list of strings
    B(340, provider="azure", stage="staging", mode="ask", page="Test", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": AZ("shift-reminders", "germanywestcentral") + """functions:
  remind:
    handler: app.remind.run
    events:
      - schedule: "0 6 * * 1-5"
""",
          "app/__init__.py": "",
          "app/remind.py": FUTURE + """from datetime import date

HOLIDAYS = ["2026-12-24", "2026-12-25", "2026-12-31"]


def run(event, ctx):
    day = date.fromisoformat((event.data or {}).get("day") or date.today().isoformat())
    if day in HOLIDAYS:
        return {"day": day.isoformat(), "sent": False, "reason": "holiday"}
    return {"day": day.isoformat(), "sent": True}
""",
          "requirements.txt": ""}),
      user="reminder sent on christmas day!! the holiday list has 2026-12-25. test with {\"day\": \"2026-12-25\"} say sent true",
      steps=[
          S("read_file", path="app/remind.py"),
          S("invoke_local", function="remind", type="schedule", data={"day": "2026-12-25"}),
          S("propose_plan", steps=["Store the holidays as `date` objects (a `date` is never equal to a string)",
                                   "Run for 2026-12-25 and 2026-12-28; validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/remind.py", content=FUTURE + """from datetime import date

HOLIDAYS = {date.fromisoformat(d) for d in ("2026-12-24", "2026-12-25", "2026-12-31")}


def run(event, ctx):
    day = date.fromisoformat((event.data or {}).get("day") or date.today().isoformat())
    if day in HOLIDAYS:
        return {"day": day.isoformat(), "sent": False, "reason": "holiday"}
    return {"day": day.isoformat(), "sent": True}
"""),
          S("invoke_local", function="remind", type="schedule", data={"day": "2026-12-25"}),
          S("invoke_local", function="remind", type="schedule", data={"day": "2026-12-28"}),
          S("validate"),
      ],
      final="""`day` is a `date` object and `HOLIDAYS` held strings. `date(2026, 12, 25) == "2026-12-25"` is False, so no day ever matched. The holidays are now `date` objects too.

- 2026-12-25: `{"day": "2026-12-25", "sent": false, "reason": "holiday"}`.
- 2026-12-28: `{"day": "2026-12-28", "sent": true}`.
- validate (azure, staging): valid."""),
]
