"""Category B (build / add), batch 25 (aws / gcp / azure). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 481
    B(481, provider="aws", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: members-area
provider:
  name: aws
  region: eu-west-2
functions: {}
""",
          "requirements.txt": ""}),
      user="after someone logs in I want the browser to remember them with a cookie. can you start a login endpoint that sets one? password check can be fake for now",
      steps=[
          S("get_project"),
          S("search_docs", query="set cookie response",
            docs=[D("docs/handlers.md", "returning-a-response", start="```python", end="set_cookie")]),
          S("propose_plan", steps=["Write `app/login.py`: fake check, then Response.json(...).set_cookie(\"sid\", ...) with http_only and secure",
                                   "Add function `login` on POST /login",
                                   "Validate for aws (staging) and try a login locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/login.py", content=FUTURE + """import secrets

from py_serverless_kit import Response, Unauthorized


def login(event, ctx):
    body = event.http.json(default={}) or {}
    if not body.get("username") or not body.get("password"):
        raise Unauthorized("wrong username or password")
    session_id = secrets.token_urlsafe(24)
    return Response.json({"welcome": body["username"]}).set_cookie(
        "sid", session_id, max_age=3600, path="/", http_only=True, secure=True, same_site="Lax")
"""),
          S("set_config", path="functions.login", value={"handler": "app.login.login", "events": [{"http": "POST /login"}]}),
          S("invoke_local", function="login", method="POST", path="/login", data={"username": "mia", "password": "x"}),
      ],
      final="""Your login endpoint is ready: `login` on `POST /login`.

- It answers `{"welcome": "<name>"}` and sets a cookie `sid` that lasts one hour. `http_only` keeps page scripts from reading it, and `secure` sends it only over HTTPS [docs/handlers.md#returning-a-response].
- Missing username or password → 401.
- `pskit validate` (aws, staging): valid.
- Local test: 200, with a `set-cookie` header for `sid`.

The password check is fake for now, and the session id isn't stored anywhere yet; you'll need a database for both. Test it on **Test** > **▶ Run locally**. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 482
    B(482, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: legacy-bridge
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, legacy-bridge-prod}
functions: {}
""",
          "requirements.txt": ""}),
      user="We're putting a single function in front of an old app: every method on every path under /api/ must reach the same handler, which for now just echoes method and the sub-path so we can test routing.",
      steps=[
          S("get_project"),
          S("search_docs", query="http method ANY greedy path",
            docs=[D("docs/events.md", "http", end="Parameter names are identifiers")]),
          S("propose_plan", steps=["Write `app/bridge.py`: return method and path_params[\"rest\"]",
                                   "Add function `bridge` on ANY /api/{rest+}",
                                   "Validate for gcp (prod), invoke a PUT and a GET"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/bridge.py", content=FUTURE + """

def bridge(event, ctx):
    return {"method": event.http.method, "path": event.http.path_params.get("rest", "")}
"""),
          S("set_config", path="functions.bridge",
            value={"handler": "app.bridge.bridge", "events": [{"http": {"path": "/api/{rest+}", "method": "ANY"}}]}),
          S("invoke_local", function="bridge", method="PUT", path="/api/users/7/settings"),
          S("invoke_local", function="bridge", method="GET", path="/api/health"),
      ],
      final="""Added the catch-all:

```yaml
functions:
  bridge:
    handler: app.bridge.bridge
    events:
      - http: {path: "/api/{rest+}", method: ANY}
```

- `method: ANY` matches every method; `{rest+}` takes the rest of the path and must be the last segment [docs/events.md#http].
- validate (gcp, prod): valid.
- `PUT /api/users/7/settings` → `{"method": "PUT", "path": "users/7/settings"}`; `GET /api/health` → `{"method": "GET", "path": "health"}`.

GCP has no API gateway, so pskit's runtime does this matching itself. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 483
    B(483, provider="azure", stage="staging", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: sales-export
provider:
  name: azure
  region: westeurope
functions: {}
""",
          "requirements.txt": ""}),
      user="need GET /export.csv give csv file download in browser, columns date,amount. fake 2 rows ok",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/export.py`: build CSV with the csv module, Response.text with content-type text/csv and content-disposition attachment",
                                   "Add function `export-csv` on GET /export.csv",
                                   "Validate azure (staging), invoke"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/export.py", content=FUTURE + """import csv
import io

from py_serverless_kit import Response

ROWS = [("2026-10-30", "120.50"), ("2026-10-31", "98.00")]


def export_csv(event, ctx):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "amount"])
    writer.writerows(ROWS)
    return Response.text(buf.getvalue(), headers={
        "content-type": "text/csv",
        "content-disposition": 'attachment; filename="sales.csv"',
    })
"""),
          S("set_config", path="functions.export-csv",
            value={"handler": "app.export.export_csv", "events": [{"http": "GET /export.csv"}]}),
          S("invoke_local", function="export-csv", method="GET", path="/export.csv"),
      ],
      final="""Done. `GET /export.csv` returns a CSV that the browser downloads as `sales.csv` (because of the `content-disposition: attachment` header).

- validate (azure, staging): valid.
- invoke: 200, `content-type: text/csv`, body `date,amount` + 2 rows.

`Response.text(..., headers=...)` lets you set your own headers [docs/handlers.md#returning-a-response]. Replace `ROWS` with real data later. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 484
    B(484, provider="aws", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#data-flow"],
      project=dict(files={
          "pskit.yml": """service: checkout-flow
provider:
  name: aws
  region: us-east-1
functions:
  charge-card:
    handler: app.flow.charge
  send-receipt:
    handler: app.flow.receipt
""",
          "app/__init__.py": "",
          "app/flow.py": FUTURE + """

def charge(event, ctx):
    payment = dict(event.data or {})
    return {"charged": payment.get("amount"), "card": payment.get("card_last4")}


def receipt(event, ctx):
    return {"receipt_for": (event.data or {}).get("customer")}
""",
          "requirements.txt": ""}),
      user="wf `pay`: Charge gets only $.payment, result into $.charge. Receipt gets full data, discard its result",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["workflows.pay: Charge (charge-card, input_path $.payment, result_path $.charge) -> Receipt (send-receipt, result_path null, end)",
                                   "Validate aws, invoke charge-card with the payment part"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.pay",
            value={"start_at": "Charge",
                   "states": {"Charge": {"type": "task", "function": "charge-card", "input_path": "$.payment",
                                         "result_path": "$.charge", "next": "Receipt"},
                              "Receipt": {"type": "task", "function": "send-receipt", "result_path": None, "end": True}}}),
          S("invoke_local", function="charge-card", type="workflow", data={"amount": 30, "card_last4": "4242"}),
      ],
      final="""```yaml
workflows:
  pay:
    start_at: Charge
    states:
      Charge: {type: task, function: charge-card, input_path: $.payment, result_path: $.charge, next: Receipt}
      Receipt: {type: task, function: send-receipt, result_path: null, end: true}
```

- `input_path` selects what the task gets; `result_path: $.charge` stores the result next to the input; `null` discards Receipt's result [docs/workflows.md#data-flow].
- validate (aws): valid (Step Functions).
- charge-card with the payment part: `{"charged": 30, "card": "4242"}`.

Check the data flow: `pskit workflow run pay -i '{"customer": "c-1", "payment": {"amount": 30, "card_last4": "4242"}}' --history`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 485
    B(485, provider="gcp", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: marketing
provider:
  name: gcp
  region: us-east1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, marketing-staging}
functions:
  newsletter:
    handler: app.mk.newsletter
    events:
    - schedule: 0 9 * * 1
  signup:
    handler: app.mk.signup
    events:
    - http: POST /signup
""",
          "app/__init__.py": "",
          "app/mk.py": FUTURE + """

def newsletter(event, ctx):
    return {"sent": 0}


def signup(event, ctx):
    return {"ok": True}
""",
          "requirements.txt": ""}),
      user="On Lambda we'd set reserved concurrency to 0 to pause a function. I want to pause `newsletter` on staging for a while but keep its config. What's the pskit way?",
      steps=[
          S("get_project"),
          S("search_docs", query="disable function enabled false",
            docs=[D("docs/configuration.md", "functions", start="| `enabled` |", end="| `enabled` |")]),
          S("propose_plan", steps=["Set functions.newsletter.enabled = false (kept in the file, skipped on deploy)",
                                   "Validate for gcp (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.newsletter.enabled", value=False),
      ],
      final="""Use `enabled: false`. The function stays in pskit.yml but isn't deployed [docs/configuration.md#functions]:

```yaml
functions:
  newsletter:
    enabled: false
```

- `pskit validate` (gcp, staging): valid, and it lists `newsletter` as disabled in a warning.
- On the next deploy, the function and its Cloud Scheduler job are removed from staging. Turn it back on with `enabled: true` and deploy again.

To pause it only on staging and keep it in prod, put it under `stages: {staging: {functions: {newsletter: {enabled: false}}}}` instead. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 486
    B(486, provider="azure", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: store-ops
provider:
  name: azure
  region: westeurope
functions:
  open-store:
    handler: app.ops.open_store
""",
          "app/__init__.py": "",
          "app/ops.py": FUTURE + """

def open_store(event, ctx):
    shift = (event.data or {}).get("shift", "unknown")
    return {"opened": True, "shift": shift}
""",
          "requirements.txt": ""}),
      user="`open-store` needs two schedules: weekdays at 07:00 UTC with input {\"shift\": \"weekday\"}, and Saturday+Sunday at 09:00 UTC with {\"shift\": \"weekend\"}. Name them weekday-open and weekend-open.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["open-store.events = [schedule {cron: \"0 7 * * 1-5\", name: weekday-open, input: {shift: weekday}}, schedule {cron: \"0 9 * * 0,6\", name: weekend-open, input: {shift: weekend}}]",
                                   "Validate for azure (prod), run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.open-store.events",
            value=[{"schedule": {"cron": "0 7 * * 1-5", "name": "weekday-open", "input": {"shift": "weekday"}}},
                   {"schedule": {"cron": "0 9 * * 0,6", "name": "weekend-open", "input": {"shift": "weekend"}}}]),
          S("invoke_local", function="open-store", type="schedule"),
      ],
      final="""Two timers on one function:

```yaml
functions:
  open-store:
    events:
      - schedule: {cron: "0 7 * * 1-5", name: weekday-open, input: {shift: weekday}}
      - schedule: {cron: "0 9 * * 0,6", name: weekend-open, input: {shift: weekend}}
```

- Azure runs timers in UTC (6-field NCRONTAB, converted by pskit), which matches your times [docs/events.md#schedule].
- `pskit validate` (azure, prod): valid.
- Local schedule run: `{"opened": true, "shift": "weekday"}` (invoke uses the first schedule's `input`).

Test the other with `pskit invoke -f open-store -t schedule -d '{"shift": "weekend"}'`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 487
    B(487, provider="aws", stage="prod", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#provider-support"],
      project=dict(files={
          "pskit.yml": """service: settlements
provider:
  name: aws
  region: eu-west-1
functions:
  api:
    handler: app.settle.api
    events:
    - http: POST /settlements
""",
          "app/__init__.py": "",
          "app/settle.py": FUTURE + """

def api(event, ctx):
    return {"accepted": True}, 202
""",
          "requirements.txt": ""}),
      user="standalone fifo queue resource `settlement-batches`, visibility 300, dlq settlement-dlq after 5. no consumer in this service",
      steps=[
          S("get_project"),
          S("search_docs", query="standalone managed queue options fifo visibility_timeout",
            docs=[D("docs/resources.md", "provider-support", start="On AWS, standalone managed queues", end="On AWS, standalone managed queues")]),
          S("propose_plan", steps=["resources.settlement-batches: {type: queue, options: {fifo: true, visibility_timeout: 300, dead_letter: settlement-dlq, max_receive: 5}}",
                                   "Validate aws (prod)"]),
          S("set_config", path="resources.settlement-batches",
            value={"type": "queue", "options": {"fifo": True, "visibility_timeout": 300,
                                                "dead_letter": "settlement-dlq", "max_receive": 5}}),
      ],
      final="""```yaml
resources:
  settlement-batches:
    type: queue
    options: {fifo: true, visibility_timeout: 300, dead_letter: settlement-dlq, max_receive: 5}
```

validate (aws, prod): valid. With no event using it, the queue takes its settings from `options` [docs/resources.md#provider-support]. `api` is bound (default: all user functions), so it gets the queue's `ARN` and `URL` after deploy. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 488
    B(488, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: dice
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, dice-dev}
functions: {}
""",
          "requirements.txt": ""}),
      user="for our board game night I want a link that rolls a dice. maybe with ?sides=20 for bigger dice",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/dice.py`: read `sides` from the query string (default 6), return a random roll",
                                   "Add function `roll` on GET /roll",
                                   "Validate for gcp and roll once locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/dice.py", content=FUTURE + """import random

from py_serverless_kit import BadRequest


def roll(event, ctx):
    raw = event.http.query.get("sides", "6")
    if not raw.isdigit() or not 2 <= int(raw) <= 100:
        raise BadRequest("sides must be a number from 2 to 100")
    sides = int(raw)
    return {"sides": sides, "roll": random.randint(1, sides)}
"""),
          S("set_config", path="functions.roll", value={"handler": "app.dice.roll", "events": [{"http": "GET /roll"}]}),
          S("invoke_local", function="roll", method="GET", path="/roll"),
      ],
      final="""Your dice link is ready: function `roll` on `/roll`.

- `/roll` rolls a normal 6-sided die; `/roll?sides=20` rolls a d20. The code reads `sides` from `event.http.query` [docs/handlers.md#httprequest]. Anything that isn't 2-100 gets a friendly 400.
- `pskit validate` (gcp): valid.
- One local roll: 200 with `"sides": 6` and a random `roll`.

Roll again on **Test** > **▶ Run locally**. To share the link with your friends: **Deploy** page or `pskit deploy -s dev`, then `pskit info` shows the address. Have fun!"""),

    # ------------------------------------------------------------------ 489
    B(489, provider="azure", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: newsletter
provider:
  name: azure
  region: westeurope
functions:
  send-one:
    handler: app.news.send_one
""",
          "app/__init__.py": "",
          "app/news.py": FUTURE + """

def send_one(event, ctx):
    email = (event.data or {}).get("email")
    ctx.logger.info("send newsletter", extra={"email": email})
    return {"email": email, "sent": True}
""",
          "requirements.txt": ""}),
      user="I have a list of emails and send-one sends to one address. How can I send to all of them, but not all at once, like 3 at a time?",
      steps=[
          S("get_project"),
          S("search_docs", query="map state each item max_concurrency",
            docs=[D("docs/workflows.md", "state-types", start="| `map` |", end="| `map` |")]),
          S("propose_plan", steps=["Add workflow `send-all`: a map state over $.emails with max_concurrency 3; each item runs send-one",
                                   "Validate for azure and send one email locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.send-all",
            value={"start_at": "EachEmail",
                   "states": {"EachEmail": {"type": "map", "items_path": "$.emails", "max_concurrency": 3, "end": True,
                                            "iterator": {"start_at": "Send", "states": {
                                                "Send": {"type": "task", "function": "send-one", "end": True}}}}}}),
          S("invoke_local", function="send-one", type="workflow", data={"email": "ana@example.com"}),
      ],
      final="""I made a workflow `send-all` for that. It goes through your list and runs `send-one` for each address, at most 3 at a time:

```yaml
workflows:
  send-all:
    start_at: EachEmail
    states:
      EachEmail:
        type: map
        items_path: $.emails
        max_concurrency: 3
        end: true
        iterator:
          start_at: Send
          states:
            Send: {type: task, function: send-one, end: true}
```

- Start it with input like `{"emails": [{"email": "ana@example.com"}, {"email": "ben@example.com"}]}`.
- `pskit validate` (azure): valid. It warns that on Azure the whole run must fit in one function call (600 s max), because it runs on the embedded engine [docs/workflows.md#embedded-orchestrator]. Fine for a small list; for thousands of emails use a queue instead.
- One email locally: `{"email": "ana@example.com", "sent": true}`.

Try the whole list: `pskit workflow run send-all -i '{"emails": [{"email": "ana@example.com"}]}'`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 490
    B(490, provider="aws", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: profiles
provider:
  name: aws
  region: us-east-1
functions:
  profile:
    handler: app.profile.handle
    events:
    - http: GET /profile/{user_id}
""",
          "app/__init__.py": "",
          "app/profile.py": FUTURE + """

def handle(event, ctx):
    return {"user_id": event.http.path_params["user_id"], "name": "Sam"}
""",
          "requirements.txt": ""}),
      user="""PUT https://abc.execute-api.us-east-1.amazonaws.com/profile/42 -> 405 {"error": "Method Not Allowed", "status": 405}
we need to update profiles too, same function""",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add `- http: PUT /profile/{user_id}` to `profile`",
                                   "Handler: on PUT, read the JSON body and return the updated profile",
                                   "Validate for aws (staging), invoke a PUT"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.profile.events",
            value=[{"http": "GET /profile/{user_id}"}, {"http": "PUT /profile/{user_id}"}]),
          S("write_file", path="app/profile.py", content=FUTURE + """

def handle(event, ctx):
    user_id = event.http.path_params["user_id"]
    if event.http.method == "PUT":
        changes = event.http.json(default={}) or {}
        return {"user_id": user_id, **changes, "updated": True}
    return {"user_id": user_id, "name": "Sam"}
"""),
          S("validate"),
          S("invoke_local", function="profile", method="PUT", path="/profile/42", data={"name": "Samira"}),
      ],
      final="""The 405 came from pskit's router: only `GET /profile/{user_id}` was declared. Now both methods go to `profile`:

```yaml
functions:
  profile:
    events:
      - http: GET /profile/{user_id}
      - http: PUT /profile/{user_id}
```

- The handler branches on `event.http.method`.
- `pskit validate` (aws, staging): valid.
- Local `PUT /profile/42` with `{"name": "Samira"}`: 200 `{"user_id": "42", "name": "Samira", "updated": true}`.

After deploy, your PUT gets 200 instead of 405: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 491
    B(491, provider="gcp", stage="staging", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=dict(files={
          "pskit.yml": """service: geo-api
provider:
  name: gcp
  region: us-central1
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
      user="gcp-only settings into a providers.gcp block: region europe-west1, project geo-api-staging. keep base portable",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["providers.gcp = {region: europe-west1, options: {project: geo-api-staging}}",
                                   "Remove provider.region (us-central1) so the base has no GCP region",
                                   "Validate gcp (staging)"]),
          S("set_config", path="providers", value={"gcp": {"region": "europe-west1", "options": {"project": "geo-api-staging"}}}),
          S("set_config", path="provider.region", value=None,
            say="validate warns that the override wins over provider.region, so I'll drop the base region."),
      ],
      final="""```yaml
provider:
  name: gcp
providers:
  gcp:
    region: europe-west1
    options: {project: geo-api-staging}
```

- Inside a `providers.<cloud>` block, `region` and `options` are shorthand for `provider.region` / `provider.options`, merged only when that provider is active [docs/configuration.md#providers-per-cloud-overrides].
- The first validate warned that `providers.gcp.region` overrides `provider.region`, so I removed the base `region: us-central1`. Now validate (gcp, staging) is valid with no warning, region europe-west1.
- The handler didn't change.

Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 492
    B(492, provider="azure", stage="staging", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: claims-portal
provider:
  name: azure
  region: westeurope
functions:
  submit:
    handler: app.claims.submit
    events:
    - http: POST /claims
  status:
    handler: app.claims.status
    events:
    - http: GET /claims/{id}
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + """

def submit(event, ctx):
    return {"ok": True}, 201


def status(event, ctx):
    return {"id": event.http.path_params["id"], "status": "open"}
""",
          "requirements.txt": ""}),
      user="Our SAM template had `Globals: Function: Timeout: 20, MemorySize: 512` for every function. Where does that go in pskit?",
      steps=[
          S("get_project"),
          S("search_docs", query="provider memory timeout defaults all functions",
            docs=[D("docs/configuration.md", "provider", start="| `memory` |", end="| `timeout` |")]),
          S("propose_plan", steps=["Set provider.timeout = 20 and provider.memory = 512 (every function inherits them)",
                                   "Validate for azure (staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.timeout", value=20),
          S("set_config", path="provider.memory", value=512),
      ],
      final="""SAM `Globals` maps to the `provider` block. Every function inherits these unless it sets its own [docs/configuration.md#provider]:

```yaml
provider:
  timeout: 20
  memory: 512
```

- `pskit validate` (azure, staging) passed after both changes.
- To override one function, set `functions.<name>.memory` / `timeout` there.

Note: pskit's Azure provider doesn't use `memory` (the Consumption plan sizes instances itself), so on Azure only the timeout has an effect. Keeping `memory` is harmless and helps if you deploy elsewhere. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 493
    B(493, provider="aws", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#handler-signatures"],
      project=dict(files={
          "pskit.yml": """service: dashboard-api
provider:
  name: aws
  region: eu-west-1
functions:
  summary:
    handler: app.summary.summary
    events:
    - http: GET /summary
""",
          "app/__init__.py": "",
          "app/summary.py": FUTURE + """import time


def load_sales():
    time.sleep(0.2)
    return 1200


def load_visits():
    time.sleep(0.2)
    return 8800


def summary(event, ctx):
    return {"sales": load_sales(), "visits": load_visits()}
""",
          "requirements.txt": ""}),
      user="summary call 2 slow sources one by one. can it be async and do both same time?",
      steps=[
          S("get_project"),
          S("search_docs", query="async def handler",
            docs=[D("docs/handlers.md", "handler-signatures")]),
          S("propose_plan", steps=["Rewrite summary as `async def` and run both loaders with asyncio.gather (asyncio.sleep stands in for the slow calls)",
                                   "Validate for aws, invoke GET /summary"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/summary.py", content=FUTURE + """import asyncio


async def load_sales():
    await asyncio.sleep(0.2)
    return 1200


async def load_visits():
    await asyncio.sleep(0.2)
    return 8800


async def summary(event, ctx):
    sales, visits = await asyncio.gather(load_sales(), load_visits())
    return {"sales": sales, "visits": visits}
"""),
          S("validate"),
          S("invoke_local", function="summary", method="GET", path="/summary"),
      ],
      final="""Yes. `summary` is now `async def`, and both loaders run at the same time with `asyncio.gather`. pskit runs async handlers for you [docs/handlers.md#handler-signatures].

- `pskit validate` (aws): valid (no config change needed).
- invoke `GET /summary`: 200 `{"sales": 1200, "visits": 8800}`.

Note: this only helps if the real sources are async too (for example `aiohttp`). A normal blocking call inside an async function still waits. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 494
    B(494, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=dict(files={
          "pskit.yml": """service: asset-sync
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, asset-sync-prod}
functions: {}
""",
          "requirements.txt": ""}),
      user="Mirror changes from the existing bucket `brand-assets` (owned by design) into our CDN index: function `sync-asset` must run when objects are created AND when they're deleted, and log which action happened.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/assets.py`: log record.action and key",
                                   "Add function `sync-asset` with storage {bucket: brand-assets, existing: true, events: [created, deleted]}",
                                   "Validate gcp (prod), invoke a create and a delete"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/assets.py", content=FUTURE + """

def sync_asset(event, ctx):
    seen = []
    for record in event.records:
        ctx.logger.info("asset change", extra={"key": record.key, "action": record.action})
        seen.append({"key": record.key, "action": record.action})
    return {"changes": seen}
"""),
          S("set_config", path="functions.sync-asset",
            value={"handler": "app.assets.sync_asset",
                   "events": [{"storage": {"bucket": "brand-assets", "existing": True, "events": ["created", "deleted"]}}]}),
          S("invoke_local", function="sync-asset", type="storage", data={"bucket": "brand-assets", "key": "logo.svg"}),
          S("invoke_local", function="sync-asset", type="storage",
            data={"bucket": "brand-assets", "key": "old-logo.svg", "action": "deleted"}),
      ],
      final="""Added:

```yaml
functions:
  sync-asset:
    handler: app.assets.sync_asset
    events:
      - storage: {bucket: brand-assets, existing: true, events: [created, deleted]}
```

- On GCP `created` and `deleted` become two Eventarc deployments of the same code (Cloud Storage `finalized` / `deleted`) [docs/events.md#storage]. `pskit info` still shows one function.
- `existing: true`: design's bucket isn't created or deleted by this stack.
- validate (gcp, prod): valid.
- invoke: create → `"action": "created"` for `logo.svg`; delete → `"action": "deleted"` for `old-logo.svg`.

Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 495
    B(495, provider="azure", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: partner-api
provider:
  name: azure
  region: westeurope
functions:
  catalog:
    handler: app.partner.catalog
    events:
    - http: GET /catalog
""",
          "app/__init__.py": "",
          "app/partner.py": FUTURE + """

def catalog(event, ctx):
    return {"items": []}
""",
          "requirements.txt": ""}),
      user="catalog: function key auth + cors for https://partner.example.com only",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["catalog event -> {path: /catalog, method: GET, auth: key, cors: {origins: [https://partner.example.com], headers: [Content-Type, x-functions-key]}}",
                                   "Validate azure, invoke"]),
          S("set_config", path="functions.catalog.events.0",
            value={"http": {"path": "/catalog", "method": "GET", "auth": "key",
                            "cors": {"origins": ["https://partner.example.com"],
                                     "headers": ["Content-Type", "x-functions-key"]}}}),
          S("invoke_local", function="catalog", method="GET", path="/catalog"),
      ],
      final="""```yaml
functions:
  catalog:
    events:
      - http:
          path: /catalog
          method: GET
          auth: key
          cors:
            origins: ["https://partner.example.com"]
            headers: [Content-Type, x-functions-key]
```

- validate (azure): valid. invoke: 200 `{"items": []}` (the key is checked by Azure, not locally).
- `auth: key` → function key (`AuthLevel.FUNCTION`); the runtime answers CORS preflights [docs/events.md#http]. The partner's browser sends the key in `x-functions-key`, so I allowed that header in `cors.headers` (the default list doesn't include it).

Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 496
    B(496, provider="aws", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: shipping
provider:
  name: aws
  region: eu-central-1
functions:
  standard-ship:
    handler: app.ship.standard
  express-ship:
    handler: app.ship.express
""",
          "app/__init__.py": "",
          "app/ship.py": FUTURE + """

def standard(event, ctx):
    return {**(event.data or {}), "method": "standard"}


def express(event, ctx):
    return {**(event.data or {}), "method": "express"}
""",
          "requirements.txt": ""}),
      user="Workflow `ship-order` with one decision: orders to DE or FR from non-VIP customers ship standard; everything else (other countries, or any VIP) ships express. Input has $.country and $.vip (bool).",
      steps=[
          S("get_project"),
          S("search_docs", query="choice and not in combinators",
            docs=[D("docs/workflows.md", "choice-rules", end="next: AskEmail")]),
          S("propose_plan", steps=["Add workflow `ship-order`: Decide (choice: and [$.country in [DE, FR], not $.vip equals true] -> Standard; default Express)",
                                   "Standard: standard-ship (end); Express: express-ship (end)",
                                   "Validate for aws (staging), run standard-ship locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.ship-order",
            value={"start_at": "Decide",
                   "states": {"Decide": {"type": "choice",
                                         "choices": [{"and": [{"variable": "$.country", "in": ["DE", "FR"]},
                                                              {"not": {"variable": "$.vip", "equals": True}}],
                                                      "next": "Standard"}],
                                         "default": "Express"},
                              "Standard": {"type": "task", "function": "standard-ship", "end": True},
                              "Express": {"type": "task", "function": "express-ship", "end": True}}}),
          S("invoke_local", function="standard-ship", type="workflow", data={"country": "DE", "vip": False}),
      ],
      final="""Added:

```yaml
workflows:
  ship-order:
    start_at: Decide
    states:
      Decide:
        type: choice
        choices:
          - and:
              - {variable: $.country, in: [DE, FR]}
              - not: {variable: $.vip, equals: true}
            next: Standard
        default: Express
      Standard: {type: task, function: standard-ship, end: true}
      Express:  {type: task, function: express-ship, end: true}
```

- `and` / `not` can be nested; a missing `$.vip` makes the inner rule false, so `not` makes it true: non-VIP [docs/workflows.md#choice-rules].
- `pskit validate` (aws, staging): valid.
- `standard-ship` locally: `"method": "standard"`.

Check both paths: `pskit workflow run ship-order -i '{"country": "DE", "vip": true}' --history` (should go Express). Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 497
    B(497, provider="gcp", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/handlers.md#logging"],
      project=dict(files={
          "pskit.yml": """service: tip-calculator
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, tip-calc-dev}
functions:
  tip:
    handler: app.tip.tip
    events:
    - http: POST /tip
""",
          "app/__init__.py": "",
          "app/tip.py": FUTURE + """

def tip(event, ctx):
    body = event.http.json(default={}) or {}
    bill = float(body.get("bill", 0))
    print("got bill", bill)
    return {"tip": round(bill * 0.15, 2)}
""",
          "requirements.txt": ""}),
      user="I use print() to see what's happening but it's messy in the cloud logs. What's the better way? Please change my code to it.",
      steps=[
          S("get_project"),
          S("search_docs", query="logging structured logger",
            docs=[D("docs/handlers.md", "logging", words=110)]),
          S("propose_plan", steps=["Replace print() with ctx.logger.info(..., extra={...}) in app/tip.py",
                                   "Validate for gcp and run it locally to see the log line"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/tip.py", content=FUTURE + """

def tip(event, ctx):
    body = event.http.json(default={}) or {}
    bill = float(body.get("bill", 0))
    ctx.logger.info("tip requested", extra={"bill": bill})
    return {"tip": round(bill * 0.15, 2)}
"""),
          S("validate"),
          S("invoke_local", function="tip", method="POST", path="/tip", data={"bill": 40}),
      ],
      final="""Use `ctx.logger` instead of `print()`. I changed your code to:

```python
ctx.logger.info("tip requested", extra={"bill": bill})
```

- In the cloud each log call becomes one JSON line with your `extra` fields plus `function`, `request_id` and `provider`, so the cloud's log viewer can search and filter by `bill` [docs/handlers.md#logging].
- `pskit validate` (gcp): valid.
- Local run with a 40 bill: the log line `tip requested`, and the answer `{"tip": 6.0}`. Locally logs are plain text; in the cloud they're JSON.

After deploy, read them on the **Logs** page or with `pskit logs`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 498
    B(498, provider="azure", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md", "docs/resources.md#runtime-api"],
      project=dict(files={
          "pskit.yml": """service: leaderboard
provider:
  name: azure
  region: westeurope
functions:
  scores:
    handler: app.scores.top
    events:
    - http: GET /top
""",
          "app/__init__.py": "",
          "app/scores.py": FUTURE + """

def top(event, ctx):
    return []
""",
          "requirements.txt": ""}),
      user="we have azure redis cache already. host from env REDIS_HOST, port 6380, ssl, password in env REDIS_KEY. connect to scores function pls",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["resources.scores-cache: type cache, external, connection {host: ${env:REDIS_HOST, cache.example.com}, port 6380, ssl: true, password_env: REDIS_KEY}, functions [scores]",
                                   "scores returns host/port/ssl from resource(\"scores-cache\") (no password)",
                                   "Validate for azure (prod), invoke GET /top"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.scores-cache",
            value={"type": "cache", "external": True, "functions": ["scores"],
                   "connection": {"host": "${env:REDIS_HOST, cache.example.com}", "port": 6380, "ssl": True,
                                  "password_env": "REDIS_KEY"}}),
          S("write_file", path="app/scores.py", content=FUTURE + """from py_serverless_kit import resource


def top(event, ctx):
    cache = resource("scores-cache")
    return {"host": cache.get("host"), "port": cache.get("port"), "ssl": cache.get("ssl")}
"""),
          S("validate"),
          S("invoke_local", function="scores", method="GET", path="/top"),
      ],
      final="""Connected. The cache is registered as an external resource (pskit never creates or changes it):

```yaml
resources:
  scores-cache:
    type: cache
    external: true
    connection:
      host: ${env:REDIS_HOST, cache.example.com}
      port: 6380
      ssl: true
      password_env: REDIS_KEY
    functions: [scores]
```

- `password_env` is only the **name** of the variable; read the key with `ctx.env[cache["password_env"]]` [docs/resources.md].
- `pskit validate` (azure, prod): valid.
- invoke `GET /top`: host `cache.example.com`, port `6380`, ssl `true` (connection values arrive as strings).

Next: add `redis` to requirements.txt and connect with these values. Set `REDIS_HOST` and `REDIS_KEY` where you deploy. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 499
    B(499, provider="aws", stage="dev", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: accounts-api
provider:
  name: aws
  region: us-west-2
functions: {}
""",
          "requirements.txt": ""}),
      user="Add `create-user` on POST /users: it takes {email}, generates an id, and answers 201 with the user JSON plus a `Location: /users/<id>` header. Missing email is a 422 with details {field: email}.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/users.py`: UnprocessableEntity with details when email is missing; Response.json(user, status=201, headers={location})",
                                   "Add function `create-user` on POST /users",
                                   "Validate aws, invoke a good and a bad request"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/users.py", content=FUTURE + """import uuid

from py_serverless_kit import Response, UnprocessableEntity


def create_user(event, ctx):
    body = event.http.json(default={}) or {}
    if not body.get("email"):
        raise UnprocessableEntity("email is required", details={"field": "email"})
    user = {"id": uuid.uuid4().hex[:12], "email": body["email"]}
    return Response.json(user, status=201, headers={"location": f"/users/{user['id']}"})
"""),
          S("set_config", path="functions.create-user",
            value={"handler": "app.users.create_user", "events": [{"http": "POST /users"}]}),
          S("invoke_local", function="create-user", method="POST", path="/users", data={"name": "no email"}),
          S("invoke_local", function="create-user", method="POST", path="/users", data={"email": "lee@example.com"}),
      ],
      final="""Added `create-user` on `POST /users`.

- validate (aws): valid.
- Without email: **422** `{"error": "email is required", "status": 422, "details": {"field": "email"}}`.
- With email: **201**, the user JSON, and `location: /users/<id>` [docs/handlers.md#returning-a-response].

Retest: `pskit invoke -f create-user --method POST --path /users -d '{"email": "a@example.com"}'`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 500
    B(500, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#migrating-step-functions-asl"],
      project=dict(files={
          "pskit.yml": """service: etl
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, etl-staging}
functions:
  load-warehouse:
    handler: app.etl.load
""",
          "app/__init__.py": "",
          "app/etl.py": FUTURE + """

def load(event, ctx):
    return {**(event.data or {}), "loaded": True}
""",
          "requirements.txt": ""}),
      user="""Our state machine starts a Glue job with "Resource": "arn:aws:states:::glue:startJobRun.sync" and then a Lambda load-warehouse. On GCP, how do I do the first step? Build workflow `nightly-etl` for it.""",
      steps=[
          S("get_project"),
          S("search_docs", query="sync service integration not supported task function",
            docs=[D("docs/workflows.md", "migrating-step-functions-asl", start="Not supported:")]),
          S("propose_plan", steps=["`.sync` service integrations aren't supported: add a task function `run-transform` that starts the transform job (stub for now)",
                                   "Add workflow `nightly-etl`: Transform (run-transform) -> Load (load-warehouse, end)",
                                   "Validate for gcp (staging), invoke run-transform"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/etl.py", content=FUTURE + """

def run_transform(event, ctx):
    job = dict(event.data or {})
    ctx.logger.info("start transform", extra={"date": job.get("date")})
    # TODO: start the GCP job (e.g. Dataflow / Cloud Run job) with its client library and wait for it
    return {**job, "transform": "done"}


def load(event, ctx):
    return {**(event.data or {}), "loaded": True}
"""),
          S("set_config", path="functions.run-transform", value={"handler": "app.etl.run_transform", "timeout": 1800}),
          S("set_config", path="workflows.nightly-etl",
            value={"start_at": "Transform",
                   "states": {"Transform": {"type": "task", "function": "run-transform", "next": "Load"},
                              "Load": {"type": "task", "function": "load-warehouse", "end": True}}}),
          S("invoke_local", function="run-transform", type="workflow", data={"date": "2026-10-31"}),
      ],
      final="""pskit workflows don't support `.sync`/callback service integrations, so the first step becomes a small task function [docs/workflows.md#migrating-step-functions-asl]:

```yaml
functions:
  run-transform:
    handler: app.etl.run_transform
    timeout: 1800
workflows:
  nightly-etl:
    start_at: Transform
    states:
      Transform: {type: task, function: run-transform, next: Load}
      Load: {type: task, function: load-warehouse, end: true}
```

- `run-transform` is a stub with a TODO: start your GCP job there with its client library and wait for it. Cloud Workflows caps task HTTP calls at 1800 s, which is why I used `timeout: 1800`.
- `pskit validate` (gcp, staging): valid.
- `run-transform` locally: `"transform": "done"`.

Run the flow: `pskit workflow run nightly-etl -i '{"date": "2026-10-31"}' --history`. Deploy: **Deploy** or `pskit deploy -s staging`."""),
]
