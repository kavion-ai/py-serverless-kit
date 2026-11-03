"""Category C (fix a validation error), batch 9: schema errors in on-premises projects (keys, limits, variables,
handlers, workflows, routes). Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def C(n, **kw):
    return dict(id=f"c_fix-{n:04d}", category="c_fix", **kw)


def handlers(*names):
    body = FUTURE
    for name in names:
        body += f"\ndef {name}(event, ctx):\n    return {{\"ok\": True, \"fn\": \"{name}\"}}\n\n"
    return body.rstrip() + "\n"


def app(module, *names):
    return {"app/__init__.py": "", f"app/{module}.py": handlers(*names)}


def onprem(service, rest, port=8080, host="127.0.0.1"):
    """Header of a local on-prem pskit.yml (scaffolding); `rest` is the hand-written part."""
    return f"""service: {service}
provider:
  name: onprem
  region: local
  options:
    host: {host}
    port: {port}
{rest}"""


FN_KEYS = D("docs/configuration.md", "functions", start="```yaml", end="options: {}")
QUEUE = D("docs/events.md", "queue", start="```yaml", end="fifo: false")
HTTP = D("docs/events.md", "http", start="```yaml", end="Parameter names are identifiers")
WF_KEYS = D("docs/workflows.md", "workflow-keys", start="| `start_at` |", end="All `next` / `default` / `catch.next` targets")
VARS = D("docs/configuration.md", "variables", start="| Syntax |", end="| `${self:dotted.path}` |")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 161  hander typo (pasted)
    C(161, provider="onprem", stage="dev", mode="auto", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("gate-log", """functions:
  open-gate:
    hander: app.gate.open_gate
    events:
      - http: POST /gate/open
"""), **app("gate", "open_gate")}),
      user="""Error: pskit.yml is invalid:
  - functions.open-gate.handler: Field required
  - functions.open-gate.hander: Extra inputs are not permitted""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `functions.open-gate.hander` to `handler`", "Validate for onprem"]),
          S("set_config", path="functions.open-gate.hander", value=None),
          S("set_config", path="functions.open-gate.handler", value="app.gate.open_gate"),
      ],
      final="""Both lines are one typo: `hander` is unknown, so `handler` counted as missing [docs/configuration.md#functions]. Renamed it to `handler: app.gate.open_gate`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 162  evnets typo (Functions page)
    C(162, provider="onprem", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("library", """functions:
  books:
    handler: app.library.books
    events:
      - http: GET /books
  overdue:
    handler: app.library.overdue
    evnets:
      - schedule: "0 8 * * *"
""", host="0.0.0.0"), **app("library", "books", "overdue")}),
      user="Fix the problems on the Functions page. The overdue reminder shows red there.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `functions.overdue.evnets` to `events` (same schedule)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.overdue.evnets", value=None),
          S("set_config", path="functions.overdue.events", value=[{"schedule": "0 8 * * *"}]),
      ],
      final="""There was one problem: `overdue` had `evnets` instead of `events`, a key pskit doesn't know [docs/configuration.md#functions].

Renamed it, so `overdue` runs every day at 08:00 again. `pskit validate -p onprem -s staging`: valid, and the Problems button shows no errors."""),

    # ------------------------------------------------------------------ 163  batch_size 0
    C(163, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=dict(files={"pskit.yml": onprem("sms-out", """functions:
  send-sms:
    handler: app.sms.send
    events:
      - queue: {name: sms, batch_size: 0}
"""), **app("sms", "send")}),
      user="i want one message one time so batch_size 0? error must be greater or equal 1",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.send-sms.events.0.queue.batch_size` to 1 (one message per call)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send-sms.events.0.queue.batch_size", value=1),
      ],
      final="""`batch_size` counts messages per call, so "one message at a time" is `1`; the range is 1-10000 [docs/events.md#queue].

Set `batch_size: 1`. Validate for onprem: valid. `event.records` now always has one record."""),

    # ------------------------------------------------------------------ 164  batch_size 20000
    C(164, provider="onprem", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#queue", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("meter-agg", """functions:
  aggregate:
    handler: app.meters.aggregate
    timeout: 300
    events:
      - queue: {name: readings, batch_size: 20000, batch_window: 60}
""", host="0.0.0.0"), **app("meters", "aggregate")}),
      user="Meters send ~20k readings per minute and `aggregate` should process them in one go, so I set batch_size 20000 with a 60 s window. Prod validation rejects it. What's the maximum and what happens to the rest?",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue batch_size maximum batch_window", docs=[QUEUE]),
          S("propose_plan", steps=["Set `functions.aggregate.events.0.queue.batch_size` to 10000 (the maximum)",
                                   "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.aggregate.events.0.queue.batch_size", value=10000),
      ],
      final="""`batch_size` is 1-10000 [docs/events.md#queue].

Set it to 10000, `batch_window: 60` kept. `pskit validate -p onprem -s prod`: valid. Nothing is lost: 20k readings simply arrive as two calls of up to 10000 records each. The on-premises host honours `batch_size` and `batch_window` [docs/providers.md#onprem-on-premises]."""),

    # ------------------------------------------------------------------ 165  batch_window 400
    C(165, provider="onprem", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={"pskit.yml": onprem("log-ship", """functions:
  ship:
    handler: app.logs.ship
    events:
      - queue: {name: log-lines, batch_size: 500, batch_window: 400}
"""), **app("logs", "ship")}),
      user="batch_window 400 rejected. use the max",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.ship.events.0.queue.batch_window` to 300", "Validate for onprem"]),
          S("set_config", path="functions.ship.events.0.queue.batch_window", value=300),
      ],
      final="""`batch_window` is 0-300 s [docs/events.md#queue]. Set to 300. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 166  memory 50
    C(166, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("tiny-bot", """functions:
  reply:
    handler: app.bot.reply
    memory: 50
    events:
      - http: POST /reply
"""), **app("bot", "reply")}),
      user="My bot is very small so I gave it 50 MB memory. Validate says it must be at least 64. Is 64 ok?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.reply.memory` to 64", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.reply.memory", value=64),
      ],
      final="""Yes. `memory` must be 64-32768 MB [docs/configuration.md#functions], so 64 is the smallest.

I set `memory: 64`. Validate for onprem: valid. On your own server all functions run inside one host process, so this number matters much more on the clouds than here."""),

    # ------------------------------------------------------------------ 167  timeout 5000
    C(167, provider="onprem", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#functions", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("video-encode", """functions:
  encode:
    handler: app.video.encode
    timeout: 5000
    events:
      - queue: {name: videos, batch_size: 1}
""", host="0.0.0.0"), **app("video", "encode")}),
      user="Lambda capped us at 15 minutes, which is why we moved encoding on-prem. Encodes take ~80 min. I set timeout 5000 and prod validation says <= 3600. Is that a hard limit on our own server too?",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem timeout handler not killed", docs=[
              D("docs/providers.md", "onprem-on-premises", start="**Limits:** no cloud authorizer", end="**Limits:** no cloud authorizer")]),
          S("propose_plan", steps=["Set `functions.encode.timeout` to 3600 (the schema maximum)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.encode.timeout", value=3600),
      ],
      final="""`timeout` is 1-3600 s in pskit.yml on every provider [docs/configuration.md#functions], so 5000 can't be written.

Set `timeout: 3600`. `pskit validate -p onprem -s prod`: valid. On-premises it isn't a hard stop: the host does not kill a handler at `timeout`; only `ctx.remaining_time_ms()` counts down [docs/providers.md#onprem-on-premises]. An 80-minute encode keeps running, so don't stop work because `remaining_time_ms()` reaches 0. One thing to check: the queue's `visibility_timeout` defaults to `max(30, 6 x timeout)`, which is plenty here."""),

    # ------------------------------------------------------------------ 168  ${self:custom.x} missing
    C(168, provider="onprem", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": onprem("stock-api", """custom:
  table_prefix: stock
functions:
  items:
    handler: app.stock.items
    environment:
      TABLE: ${self:custom.table}
    events:
      - http: GET /items
"""), **app("stock", "items")}),
      user="Error: unresolved variables: self:custom.table . but custom is there",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("ask_user", question="`custom` has `table_prefix`, not `table`. What should TABLE be?",
            options=["Use custom.table_prefix (value \"stock\")", "Add custom.table with another value"],
            answer="Use custom.table_prefix (value \"stock\")"),
          S("propose_plan", steps=["Set `functions.items.environment.TABLE` to `${self:custom.table_prefix}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.items.environment.TABLE", value="${self:custom.table_prefix}"),
      ],
      final="""`${self:custom.table}` points to a key that doesn't exist; `custom` only has `table_prefix` [docs/configuration.md#variables].

Now `TABLE: ${self:custom.table_prefix}`, which resolves to `stock`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 169  ${env:X} unset
    C(169, provider="onprem", stage="dev", mode="ask", page="Setup", persona="detailed_spec",
      sources=["docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": onprem("inventory", """functions:
  sync:
    handler: app.inventory.sync
    environment:
      ERP_URL: ${env:ERP_URL}
    events:
      - schedule: 15 minutes
"""), **app("inventory", "sync")}),
      user="Validation fails with 'unresolved variables: env:ERP_URL' on my laptop. In CI the variable is always set, but locally I just want it to fall back to our test ERP at http://192.0.2.80:8000. Make validate work locally without breaking CI.",
      steps=[
          S("get_validation"),
          S("search_docs", query="env variable default", docs=[VARS]),
          S("propose_plan", steps=["Set `functions.sync.environment.ERP_URL` to `${env:ERP_URL, http://192.0.2.80:8000}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sync.environment.ERP_URL", value="${env:ERP_URL, http://192.0.2.80:8000}"),
      ],
      final="""`${env:NAME}` is an error when the variable is unset; `${env:NAME, default}` falls back instead [docs/configuration.md#variables].

Now `ERP_URL: ${env:ERP_URL, http://192.0.2.80:8000}`. Validate for onprem: valid on your laptop. In CI, where `ERP_URL` is set, its value still wins."""),

    # ------------------------------------------------------------------ 170  handler module missing -> stub
    C(170, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("school-reports", """functions:
  timetable:
    handler: app.school.timetable
    events:
      - http: GET /timetable
  weekly-report:
    handler: app.reports.weekly
    events:
      - schedule: "0 16 * * 5"
"""), **app("school", "timetable")}),
      user="There's a warning that handler module app.reports is not found. I haven't written the report code yet. Can you make an empty one so the warning goes away?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Create `app/reports.py` with a `weekly(event, ctx)` stub",
                                   "Validate for onprem", "Run `weekly-report` locally as a schedule event"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/reports.py", content=FUTURE + """
def weekly(event, ctx):
    ctx.logger.info("weekly report: not written yet")
    return {"report": "todo"}
"""),
          S("validate"),
          S("invoke_local", function="weekly-report", type="schedule"),
      ],
      final="""`handler: app.reports.weekly` means the file `app/reports.py` with a function `weekly`, and that file didn't exist yet, so the function would fail when it runs [docs/configuration.md#functions].

I created `app/reports.py` with a small `weekly(event, ctx)` stub.
- Validate for onprem: valid, the warning is gone.
- A local run as a schedule event returned `{"report": "todo"}`.

Write the real report in that function later; open it on the **Code** page."""),

    # ------------------------------------------------------------------ 171  handler without dots
    C(171, provider="onprem", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("ping-svc", """functions:
  ping:
    handler: ping
    events:
      - http: GET /ping
"""), **app("health", "ping")}),
      user="""  - functions.ping.handler: Value error, handler 'ping' must be 'package.module.function' (or 'module:function')""",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Set `functions.ping.handler` to `app.health.ping` (the function in app/health.py)", "Validate for onprem"]),
          S("set_config", path="functions.ping.handler", value="app.health.ping"),
      ],
      final="""A handler needs the module path plus the function, not the function alone [docs/configuration.md#functions]. `ping` lives in `app/health.py`, so it's `handler: app.health.ping`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 172  workflow next to missing state
    C(172, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={"pskit.yml": onprem("onboarding", """functions:
  create-account:
    handler: app.onboard.create_account
  send-welcome:
    handler: app.onboard.send_welcome
workflows:
  onboard:
    start_at: CreateAccount
    states:
      CreateAccount: {type: task, function: create-account, next: SendWelcome}
      SendWellcome: {type: task, function: send-welcome, end: true}
"""), **app("onboard", "create_account", "send_welcome")}),
      user="workflow onboard: state CreateAccount points to unknown state SendWelcome. but i have it!",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Rename state `SendWellcome` to `SendWelcome` (matches `next`)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.onboard.states.SendWellcome", value=None),
          S("set_config", path="workflows.onboard.states.SendWelcome", value={"type": "task", "function": "send-welcome", "end": True}),
      ],
      final="""The state is named `SendWellcome` (double l), but `next` says `SendWelcome`. Every `next` must match a state name exactly [docs/workflows.md#workflow-keys].

Renamed the state to `SendWelcome`. `pskit validate -p onprem -s staging`: valid, and on-premises it runs on the embedded engine."""),

    # ------------------------------------------------------------------ 173  start_at not a state
    C(173, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={"pskit.yml": onprem("kyc", """functions:
  verify-id:
    handler: app.kyc.verify_id
  score-risk:
    handler: app.kyc.score_risk
workflows:
  kyc:
    start_at: Start
    states:
      VerifyId: {type: task, function: verify-id, next: ScoreRisk}
      ScoreRisk: {type: task, function: score-risk, end: true}
"""), **app("kyc", "verify_id", "score_risk")}),
      user="kyc workflow: start_at 'Start' is not a defined state. first step is VerifyId",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.kyc.start_at` to `VerifyId`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.kyc.start_at", value="VerifyId"),
      ],
      final="""`start_at` must name a state, and there is no `Start` [docs/workflows.md#workflow-keys]. Set `start_at: VerifyId`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 174  task references unknown function
    C(174, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={"pskit.yml": onprem("returns", """functions:
  inspect-item:
    handler: app.returns.inspect
  issue-refund:
    handler: app.returns.refund
workflows:
  return-flow:
    start_at: Inspect
    states:
      Inspect: {type: task, function: inspect-item, next: Refund}
      Refund: {type: task, function: refund, end: true}
""", host="0.0.0.0"), **app("returns", "inspect", "refund")}),
      user="Prod validation fails: workflow 'return-flow' references unknown function 'refund'. The Refund step must call the function that pays the money back. Please fix the reference, don't rename the function.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.return-flow.states.Refund.function` to `issue-refund`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.return-flow.states.Refund.function", value="issue-refund"),
      ],
      final="""A task's `function` must be a key under `functions:`. `refund` is only the Python function name inside `app/returns.py`; the pskit function is `issue-refund` [docs/workflows.md#workflow-keys].

Set `Refund.function: issue-refund`; the function wasn't renamed. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 175  choice rule without next
    C(175, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={"pskit.yml": onprem("loan-check", """functions:
  score:
    handler: app.loans.score
  approve:
    handler: app.loans.approve
  review:
    handler: app.loans.review
workflows:
  loan:
    start_at: Score
    states:
      Score: {type: task, function: score, next: Decide}
      Decide:
        type: choice
        choices:
          - {variable: "$.score", gte: 700}
        default: Review
      Approve: {type: task, function: approve, end: true}
      Review: {type: task, function: review, end: true}
"""), **app("loans", "score", "approve", "review")}),
      user="""Error: pskit.yml is invalid:
  - workflows.loan: Value error, choice rule in 'Decide' has no `next`: {'variable': '$.score', 'gte': 700}

700 and up should be approved""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.loan.states.Decide.choices.0.next` to `Approve`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.loan.states.Decide.choices.0.next", value="Approve"),
      ],
      final="""Each choice rule needs a `next`: the state to go to when it matches [docs/workflows.md#choice-rules].

Now `{variable: "$.score", gte: 700, next: Approve}`; anything else goes to `Review` (the `default`). Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 176  queue resource not in resources
    C(176, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#using-a-resource-from-an-event"],
      project=dict(files={"pskit.yml": onprem("mail-out", """resources:
  mails:
    type: queue
functions:
  send-mail:
    handler: app.mail.send
    events:
      - queue: {resource: mail}
"""), **app("mail", "send")}),
      user="function send-mail uses unknown resource 'mail'; known: mails . same thing no?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.send-mail.events.0.queue.resource` to `mails` (the resource key)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send-mail.events.0.queue.resource", value="mails"),
      ],
      final="""Not for pskit: `resource:` must be exactly a key under `resources:`, and the key is `mails` [docs/resources.md#using-a-resource-from-an-event].

Now `queue: {resource: mails}`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 177  method FETCH
    C(177, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={"pskit.yml": onprem("weather-api", """functions:
  forecast:
    handler: app.weather.forecast
    events:
      - http: {path: /forecast, method: FETCH}
"""), **app("weather", "forecast")}),
      user="My website uses fetch() to get the forecast, so I put method FETCH. validate says method must be one of GET, POST... which one?",
      steps=[
          S("get_validation"),
          S("search_docs", query="http methods", docs=[HTTP]),
          S("propose_plan", steps=["Set `functions.forecast.events.0.http.method` to `GET`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.forecast.events.0.http.method", value="GET"),
      ],
      final="""`fetch()` is the browser's way to send a request, not an HTTP method. Without options, `fetch()` sends **GET**. Methods are GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS or ANY [docs/events.md#http].

I set `method: GET`. Validate for onprem: valid. If your page loads from another address, you may also need `cors: true` on this route."""),

    # ------------------------------------------------------------------ 178  path {user-id}
    C(178, provider="onprem", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={"pskit.yml": onprem("profiles", """functions:
  profile:
    handler: app.profiles.get_profile
    events:
      - http: GET /users/{user-id}/profile
"""), **app("profiles", "get_profile")}),
      user="invalid path template /users/{user-id}/profile. fix, staging",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the route to `GET /users/{user_id}/profile`", "Validate for onprem, stage staging"]),
          S("set_config", path="functions.profile.events.0.http", value="GET /users/{user_id}/profile"),
      ],
      final="""Path parameter names are identifiers, so no dashes [docs/events.md#http]. Route is now `GET /users/{user_id}/profile`; read it as `event.http.path_params["user_id"]` in the handler. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 179  duplicate route
    C(179, provider="onprem", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=dict(files={"pskit.yml": onprem("notes-api", """functions:
  list-notes:
    handler: app.notes.list_notes
    events:
      - http: GET /notes
  create-note:
    handler: app.notes.create_note
    events:
      - http: GET /notes
"""), **app("notes", "list_notes", "create_note")}),
      user="I duplicated `list-notes` in studio to make `create-note`, and now validation says route GET /notes is used by both. `create-note` should take the JSON body of a new note on the same path.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the `create-note` route to `POST /notes`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.create-note.events.0.http", value="POST /notes"),
      ],
      final="""Duplicate keeps the trigger, so both functions claimed `GET /notes`; one method + path can belong to only one function [docs/events.md#http].

`create-note` is now `POST /notes`: same path, different method. Validate for onprem: valid. The handler reads the new note with `event.http.json()`."""),

    # ------------------------------------------------------------------ 180  two keys in one event
    C(180, provider="onprem", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#events-triggers"],
      project=dict(files={"pskit.yml": onprem("ingest", """functions:
  ingest:
    handler: app.ingest.handle
    events:
      - http: POST /ingest
        schedule: 1 hour
"""), **app("ingest", "handle")}),
      user="In serverless.yml I listed http and schedule together for the function and it worked. Here validation says each event must be a single-key mapping. What's the pskit way?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Split the event into two list items: `- http: POST /ingest` and `- schedule: 1 hour`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest.events", value=[{"http": "POST /ingest"}, {"schedule": "1 hour"}]),
      ],
      final="""Each item under `events:` is one trigger with one key; both keys were in a single item [docs/events.md#events-triggers]. A function can still have several triggers, one per list item:

```yaml
functions:
  ingest:
    events:
      - http: POST /ingest
      - schedule: 1 hour
```

Validate for onprem: valid. In the handler, `event.type` tells you which one fired (`http` or `schedule`)."""),
]
