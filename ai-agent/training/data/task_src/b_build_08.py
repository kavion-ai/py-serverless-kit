"""Category B (build / add), batch 8: on-premises only. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"

SERVERS = json.dumps({"servers": {
    "app-1": {"host": "192.0.2.10", "user": "pskit", "port": 22},
    "app-2": {"host": "192.0.2.11", "user": "pskit", "port": 22},
    "db-1": {"host": "192.0.2.40", "user": "pskit", "port": 22},
    "gpu-box": {"host": "192.0.2.20", "user": "pskit", "port": 22},
    "lb-1": {"host": "192.0.2.30", "user": "pskit", "port": 22}}}, indent=2)
CLUSTERS = json.dumps({"clusters": {
    "prod": {"orchestrator": "swarm", "master": "app-1", "servers": ["app-2"]},
    "k3s-lab": {"orchestrator": "kubernetes", "master": "app-2", "servers": ["gpu-box"]}}}, indent=2)


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", provider="onprem", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 141
    B(141, stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/handlers.md#errors", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: config-store
provider:
  name: onprem
  region: local
  options:
    port: 8131
functions: {}
""",
          "requirements.txt": ""}),
      user="PUT /settings/{key} body {value}. keys in LOCKED set -> 409. else 200 {key,value}",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/settings.py`: Conflict for locked keys, BadRequest when value is missing",
                                   "Add `put-setting` on PUT /settings/{key}",
                                   "Validate, invoke PUT /settings/theme"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/settings.py", content=FUTURE + """from py_serverless_kit import BadRequest, Conflict

LOCKED = {"license", "tenant_id"}
SETTINGS = {}


def put_setting(event, ctx):
    key = event.http.path_params.get("key", "")
    if key in LOCKED:
        raise Conflict(f"setting {key} is locked")
    body = event.http.json(default={}) or {}
    if "value" not in body:
        raise BadRequest("value is required")
    SETTINGS[key] = body["value"]
    return {"key": key, "value": body["value"]}
"""),
          S("set_config", path="functions.put-setting",
            value={"handler": "app.settings.put_setting", "events": [{"http": "PUT /settings/{key}"}]}),
          S("invoke_local", function="put-setting", method="PUT", path="/settings/theme", data={"value": "dark"}),
      ],
      final="""Added `put-setting` on `PUT /settings/{key}`. A locked key raises `Conflict` (409), and a missing `value` raises `BadRequest` (400) [docs/handlers.md#errors].

- validate (onprem): valid.
- `PUT /settings/theme {"value": "dark"}`: 200, `{"key": "theme", "value": "dark"}`.

409 check: `pskit invoke -f put-setting --method PUT --path /settings/license -d '{"value": 1}'`. `SETTINGS` is in memory, so use a store before prod. Deploy: `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 142
    B(142, stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: recipes
provider:
  name: onprem
  region: local
  options:
    port: 8132
functions: {}
""",
          "requirements.txt": ""}),
      user="search recipes by many tags in url like /recipes?tags=vegan,quick, recipe must have all tags. make it",
      steps=[
          S("get_project"),
          S("search_docs", query="query string parameters http request",
            docs=[D("docs/handlers.md", "httprequest", words=170)]),
          S("propose_plan", steps=["Write `app/recipes.py`: split event.http.query[\"tags\"] on commas, keep recipes that have all of them",
                                   "Add `search-recipes` on GET /recipes",
                                   "Validate (onprem, staging) and call /recipes?tags=vegan,quick"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/recipes.py", content=FUTURE + """
RECIPES = [
    {"name": "Lentil soup", "tags": ["vegan", "quick"]},
    {"name": "Lasagne", "tags": ["vegetarian"]},
    {"name": "Hummus wrap", "tags": ["vegan", "quick", "cold"]},
    {"name": "Tofu curry", "tags": ["vegan"]},
]


def search(event, ctx):
    raw = event.http.query.get("tags", "")
    tags = [t.strip().lower() for t in raw.split(",") if t.strip()]
    found = [r for r in RECIPES if all(t in r["tags"] for t in tags)]
    return {"tags": tags, "recipes": [r["name"] for r in found]}
"""),
          S("set_config", path="functions.search-recipes",
            value={"handler": "app.recipes.search", "events": [{"http": "GET /recipes"}]}),
          S("invoke_local", function="search-recipes", method="GET", path="/recipes?tags=vegan,quick"),
      ],
      final="""Done. `search-recipes` on `GET /recipes` reads `event.http.query["tags"]`, splits it on commas, and keeps only recipes that have **all** the tags [docs/handlers.md#httprequest].

- `pskit validate` (onprem, staging): valid.
- `/recipes?tags=vegan,quick`: 200, `{"tags": ["vegan", "quick"], "recipes": ["Lentil soup", "Hummus wrap"]}`. "Tofu curry" is left out because it is not `quick`.
- No `tags` at all returns every recipe.

The recipes are sample data in `app/recipes.py`. Test more: `pskit invoke -f search-recipes --method GET --path "/recipes?tags=cold"`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 143
    B(143, stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: status-board
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8133
functions: {}
""",
          "requirements.txt": ""}),
      user="can a function show a real web page instead of json? i want a simple status page for the office tv that says all systems ok with the time",
      steps=[
          S("get_project"),
          S("search_docs", query="return html page response",
            docs=[D("docs/handlers.md", "returning-a-response", start="```python", end="Response.html(\"<h1>Hi</h1>\")")]),
          S("propose_plan", steps=["Write `app/board.py` returning Response.html(...) with a heading and the current UTC time",
                                   "Add function `board` on GET /board",
                                   "Validate for onprem and open /board locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/board.py", content=FUTURE + """from datetime import datetime, timezone

from py_serverless_kit import Response

PAGE = \"\"\"<!doctype html>
<html><head><meta http-equiv="refresh" content="60"><title>Status</title></head>
<body style="font-family: sans-serif; text-align: center">
<h1>All systems OK</h1><p>Updated {now} UTC</p>
</body></html>\"\"\"


def board(event, ctx):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return Response.html(PAGE.format(now=now))
"""),
          S("set_config", path="functions.board",
            value={"handler": "app.board.board", "events": [{"http": "GET /board"}]}),
          S("invoke_local", function="board", method="GET", path="/board"),
      ],
      final="""Yes. Return `Response.html(...)` and the browser shows a page [docs/handlers.md#returning-a-response]. I added a function `board` on `GET /board`. It says **All systems OK** with the time, and reloads itself every 60 seconds, which suits a TV.

- `pskit validate` (onprem): valid.
- Local call to `/board`: 200 with an HTML page (content type `text/html`).

After a deploy (**Deploy** page or `pskit deploy -s dev`), open `http://<this computer's address>:8133/board` on the TV. `host: 0.0.0.0` already lets other devices in the office reach it. To check it again without deploying: **Test** page > **▶ Run locally**."""),

    # ------------------------------------------------------------------ 144
    B(144, stage="prod", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/handlers.md#returning-a-response", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: golinks
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8134
functions: {}
""",
          "requirements.txt": ""}),
      user="short links for intranet: /go/wiki -> https://wiki.example.com, /go/hr -> https://hr.example.com. unknown code 404",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/go.py`: map code -> URL, Response.redirect(url, status=302), NotFound otherwise",
                                   "Add `go` on GET /go/{code}",
                                   "Validate (onprem, prod), invoke /go/wiki"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/go.py", content=FUTURE + """from py_serverless_kit import NotFound, Response

LINKS = {
    "wiki": "https://wiki.example.com",
    "hr": "https://hr.example.com",
}


def go(event, ctx):
    code = event.http.path_params.get("code", "").lower()
    url = LINKS.get(code)
    if url is None:
        raise NotFound(f"no short link {code}")
    return Response.redirect(url, status=302)
"""),
          S("set_config", path="functions.go",
            value={"handler": "app.go.go", "events": [{"http": "GET /go/{code}"}]}),
          S("invoke_local", function="go", method="GET", path="/go/wiki"),
      ],
      final="""Done. `go` on `GET /go/{code}` sends the browser on with `Response.redirect(url, status=302)` [docs/handlers.md#returning-a-response]. An unknown code raises `NotFound` (404).

- validate (onprem, prod): valid.
- `/go/wiki`: 302 with `location: https://wiki.example.com`.

To add links, edit `LINKS` in `app/go.py`. Test: `pskit invoke -f go --method GET --path /go/nope` (404). Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 145
    B(145, stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#queue", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: payouts
provider:
  name: onprem
  region: local
  options:
    port: 8135
functions:
  payout-worker:
    handler: app.payouts.work
    events:
    - queue: {name: payouts, batch_size: 10, dead_letter: payouts-dlq, max_receive: 4}
""",
          "app/__init__.py": "",
          "app/payouts.py": FUTURE + """

def work(event, ctx):
    return None
""",
          "requirements.txt": ""}),
      user="Messages that fail 4 times land in payouts-dlq and then nobody notices. Add a function `payout-dlq-alert` that consumes payouts-dlq one message at a time and logs an ERROR line with the payout id and how many times it was received.",
      steps=[
          S("get_project"),
          S("search_docs", query="dead letter queue consume record attributes receives",
            docs=[D("docs/events.md", "queue", words=150)]),
          S("propose_plan", steps=["Add `dlq_alert` to `app/payouts.py`: ERROR log with payout_id and record.attributes receive count",
                                   "Add function `payout-dlq-alert` with queue {name: payouts-dlq, batch_size: 1}",
                                   "Validate (onprem, staging), invoke with one dead message"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/payouts.py", content=FUTURE + """

def work(event, ctx):
    return None


def dlq_alert(event, ctx):
    for record in event.records:
        payout = record.json(default={}) or {}
        ctx.logger.error("payout gave up", extra={"payout_id": payout.get("payout_id"),
                                                  "message_id": record.id,
                                                  "attributes": record.attributes})
    return {"alerted": len(event.records)}
"""),
          S("set_config", path="functions.payout-dlq-alert",
            value={"handler": "app.payouts.dlq_alert", "events": [{"queue": {"name": "payouts-dlq", "batch_size": 1}}]}),
          S("invoke_local", function="payout-dlq-alert", type="queue", data=[{"payout_id": "p-3391", "amount": 120}]),
      ],
      final="""Added `payout-dlq-alert` on `payouts-dlq` with `batch_size: 1`. It logs one ERROR line per dead payout.

- `pskit validate` (onprem, staging): valid.
- Local invoke with one message: logged the ERROR with `payout_id: p-3391` and returned `{"alerted": 1}`.

On the receive count: I log `record.attributes` and the message id. I didn't hard-code an attribute name for the count, because the docs don't name one for the built-in queue. Once the alert fires after a deploy, check what really arrives on the **Logs** page (filter level `error`), or with `pskit logs --function payout-dlq-alert --level error`, and I'll pick the right field.

Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 146
    B(146, stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#embedded-orchestrator"],
      project=dict(files={
          "pskit.yml": """service: imports
provider:
  name: onprem
  region: local
  options:
    port: 8136
functions:
  import-batch:
    handler: app.imports.import_batch
    events:
    - queue: {name: import-jobs, batch_size: 1}
  notify-done:
    handler: app.imports.notify_done
""",
          "app/__init__.py": "",
          "app/imports.py": FUTURE + """

def import_batch(event, ctx):
    jobs = [r.json(default={}) for r in event.records] if event.records else [event.data]
    return {"imported": len(jobs)}


def notify_done(event, ctx):
    ctx.logger.info("import finished", extra={"result": event.data})
    return {"notified": True}
""",
          "requirements.txt": ""}),
      user="After import-batch processes a message from import-jobs, notify-done must run with its result. I don't want to change import-batch or call notify-done from it. Is a workflow the way on-prem?",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow starts when first task function runs on its own on premises",
            docs=[D("docs/workflows.md", "embedded-orchestrator", start="- On premises, a workflow whose first state is a `task`",
                    end="Other clouds don't do this: start the workflow itself there.")]),
          S("propose_plan", steps=["Add workflow `import-and-notify`: Import (task import-batch) -> Notify (task notify-done, end)",
                                   "No change to import-batch or its queue trigger",
                                   "Validate (onprem, prod) and run notify-done as a workflow task"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.import-and-notify",
            value={"start_at": "Import",
                   "states": {"Import": {"type": "task", "function": "import-batch", "next": "Notify"},
                              "Notify": {"type": "task", "function": "notify-done", "end": True}}}),
          S("invoke_local", function="notify-done", type="workflow", data={"imported": 1}),
      ],
      final="""Yes. On premises a workflow whose first state is a task **also starts when that function runs on its own**, including from its queue. The function's result becomes the first state's result, so `import-batch` does not run twice [docs/workflows.md#embedded-orchestrator]:

```yaml
workflows:
  import-and-notify:
    start_at: Import
    states:
      Import: {type: task, function: import-batch, next: Notify}
      Notify: {type: task, function: notify-done, end: true}
```

`import-batch` and its queue trigger are unchanged. A failed call starts nothing, so `notify-done` only runs after a successful import.

- `pskit validate` (onprem, prod): valid (embedded engine).
- `notify-done` as a workflow task with `{"imported": 1}`: `{"notified": true}`.

Only on-prem does this. If you ever deploy to a cloud, start the workflow explicitly there. To turn it off: `options.start_on_entry: false` on the workflow. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. Then follow runs on the **Workflows** page."""),

    # ------------------------------------------------------------------ 147
    B(147, stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types", "docs/workflows.md"],
      project=dict(files={
          "pskit.yml": """service: invoices
provider:
  name: onprem
  region: local
  options:
    port: 8137
functions:
  send-reminder:
    handler: app.dunning.send_reminder
  check-payment:
    handler: app.dunning.check_payment
""",
          "app/__init__.py": "",
          "app/dunning.py": FUTURE + """

def send_reminder(event, ctx):
    inv = dict(event.data or {})
    return {**inv, "reminded": True}


def check_payment(event, ctx):
    inv = dict(event.data or {})
    return {**inv, "paid": False}
""",
          "requirements.txt": ""}),
      user="when an invoice is late: send a reminder, then wait one hour, then check if it is paid. is waiting one hour a problem? functions have timeout 30 sec",
      steps=[
          S("get_project"),
          S("search_docs", query="wait state seconds workflow timeout on premises",
            docs=[D("docs/workflows.md", "state-types", start="| `wait` |", end="| sleep |"),
                  D("docs/workflows.md", "workflows-state-machines", start="- on the **embedded engine**", end="so the workflow is not cut off by a function timeout);")]),
          S("propose_plan", steps=["Add workflow `late-invoice`: Remind (send-reminder) -> WaitHour (wait 3600 s) -> Check (check-payment, end)",
                                   "Validate for onprem and run send-reminder as a workflow task"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.late-invoice",
            value={"start_at": "Remind",
                   "states": {"Remind": {"type": "task", "function": "send-reminder", "next": "WaitHour"},
                              "WaitHour": {"type": "wait", "seconds": 3600, "next": "Check"},
                              "Check": {"type": "task", "function": "check-payment", "end": True}}}),
          S("invoke_local", function="send-reminder", type="workflow", data={"invoice": "INV-88", "amount": 300}),
      ],
      final="""No problem on premises. The 30-second timeout is per function call, and the hour of waiting happens in the workflow engine inside your host, which is not cut off by a function timeout [docs/workflows.md]:

```yaml
workflows:
  late-invoice:
    start_at: Remind
    states:
      Remind:   {type: task, function: send-reminder, next: WaitHour}
      WaitHour: {type: wait, seconds: 3600, next: Check}
      Check:    {type: task, function: check-payment, end: true}
```

- `pskit validate` (onprem): valid.
- `send-reminder` run as a workflow step: returned the invoice with `"reminded": true`.

Deploy: **Deploy** page or `pskit deploy -s dev`. After that, start a run with `POST /workflows/late-invoice` and the invoice as the body, and watch it wait on the **Workflows** page."""),

    # ------------------------------------------------------------------ 148
    B(148, stage="staging", mode="auto", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#retry-and-catch"],
      project=dict(files={
          "pskit.yml": """service: signup-flow
provider:
  name: onprem
  region: local
  options:
    port: 8138
functions:
  parse-form:
    handler: app.flow.parse_form
  create-user:
    handler: app.flow.create_user
  reject-form:
    handler: app.flow.reject_form
""",
          "app/__init__.py": "",
          "app/flow.py": FUTURE + """

def parse_form(event, ctx):
    form = dict(event.data or {})
    if "@" not in str(form.get("email", "")):
        raise ValueError("email is not valid")
    return form


def create_user(event, ctx):
    return {**(event.data or {}), "user_id": "u-1"}


def reject_form(event, ctx):
    data = dict(event.data or {})
    return {"rejected": True, "why": (data.get("error") or {}).get("cause")}
""",
          "requirements.txt": ""}),
      user="Step Functions version had Catch: [{ErrorEquals: [ValueError], Next: RejectForm, ResultPath: $.error}] on ParseForm. Same here: parse-form -> create-user, ValueError -> reject-form.",
      steps=[
          S("get_project"),
          S("search_docs", query="catch errors next result_path",
            docs=[D("docs/workflows.md", "retry-and-catch", start="catch:", end="Without a match the run fails.")]),
          S("propose_plan", steps=["Add workflow `signup`: Parse (parse-form, catch ValueError -> Reject, result_path $.error) -> Create (create-user, end); Reject (reject-form, end)",
                                   "Validate (onprem, staging), invoke reject-form with a caught error"]),
          S("set_config", path="workflows.signup",
            value={"start_at": "Parse",
                   "states": {"Parse": {"type": "task", "function": "parse-form", "next": "Create",
                                        "catch": [{"errors": ["ValueError"], "next": "Reject",
                                                   "result_path": "$.error"}]},
                              "Create": {"type": "task", "function": "create-user", "end": True},
                              "Reject": {"type": "task", "function": "reject-form", "end": True}}}),
          S("invoke_local", function="reject-form", type="workflow",
            data={"email": "nope", "error": {"error": "ValueError", "cause": "email is not valid"}}),
      ],
      final="""Same Catch, pskit spelling:

```yaml
workflows:
  signup:
    start_at: Parse
    states:
      Parse:
        type: task
        function: parse-form
        next: Create
        catch:
          - {errors: [ValueError], next: Reject, result_path: $.error}
      Create: {type: task, function: create-user, end: true}
      Reject: {type: task, function: reject-form, end: true}
```

`errors` are the Python exception class names your handler raises. `result_path: $.error` stores `{"error", "cause"}` next to the input [docs/workflows.md#retry-and-catch].

- validate (onprem, staging): valid (embedded engine).
- `reject-form` with a caught error: `{"rejected": true, "why": "email is not valid"}`.

End to end: `pskit workflow run signup -i '{"email": "nope"}' --history`. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 149
    B(149, stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={
          "pskit.yml": """service: risk
provider:
  name: onprem
  region: local
  options:
    port: 8139
functions:
  credit-score:
    handler: app.risk.credit_score
  fraud-check:
    handler: app.risk.fraud_check
  decide:
    handler: app.risk.decide
""",
          "app/__init__.py": "",
          "app/risk.py": FUTURE + """

def credit_score(event, ctx):
    return {"score": 712}


def fraud_check(event, ctx):
    return {"fraud": False}


def decide(event, ctx):
    data = dict(event.data or {})
    checks = data.get("checks") or [{}, {}]
    ok = checks[0].get("score", 0) > 650 and not checks[1].get("fraud", True)
    return {"application": data.get("application"), "approved": ok}
""",
          "requirements.txt": ""}),
      user="wf `assess`: credit-score + fraud-check in parallel, results into $.checks, then decide",
      steps=[
          S("get_project"),
          S("search_docs", query="parallel branches result list",
            docs=[D("docs/workflows.md", "state-types", start="| `parallel` |", end="result is a list (one item per branch) |")]),
          S("propose_plan", steps=["Add workflow `assess`: Checks (parallel: [credit-score], [fraud-check], result_path $.checks) -> Decide (decide, end)",
                                   "Validate (onprem, prod), invoke decide with sample checks"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.assess",
            value={"start_at": "Checks",
                   "states": {"Checks": {"type": "parallel", "result_path": "$.checks", "next": "Decide",
                                         "branches": [
                                             {"start_at": "Credit",
                                              "states": {"Credit": {"type": "task", "function": "credit-score", "end": True}}},
                                             {"start_at": "Fraud",
                                              "states": {"Fraud": {"type": "task", "function": "fraud-check", "end": True}}}]},
                              "Decide": {"type": "task", "function": "decide", "end": True}}}),
          S("invoke_local", function="decide", type="workflow",
            data={"application": "A-12", "checks": [{"score": 712}, {"fraud": False}]}),
      ],
      final="""Added `assess`:

```yaml
workflows:
  assess:
    start_at: Checks
    states:
      Checks:
        type: parallel
        result_path: $.checks
        next: Decide
        branches:
          - start_at: Credit
            states: {Credit: {type: task, function: credit-score, end: true}}
          - start_at: Fraud
            states: {Fraud: {type: task, function: fraud-check, end: true}}
      Decide: {type: task, function: decide, end: true}
```

`$.checks` is a list with one item per branch, in branch order: `[credit, fraud]` [docs/workflows.md#state-types].

- validate (onprem, prod): valid (embedded engine).
- `decide` with sample checks: `{"application": "A-12", "approved": true}`.

Run: `pskit workflow run assess -i '{"application": "A-12"}' --history`. Deploy: `pskit deploy -s prod` (typed confirmation in **Deploy**)."""),

    # ------------------------------------------------------------------ 150
    B(150, stage="prod", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#compiler-notes-and-limits"],
      project=dict(files={
          "pskit.yml": """service: hr
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8140
functions:
  calc-salaries:
    handler: app.payroll.calc
  pay-salaries:
    handler: app.payroll.pay
  monthly-trigger:
    handler: app.payroll.trigger
    events:
    - schedule: 0 6 25 * *
""",
          "app/__init__.py": "",
          "app/payroll.py": FUTURE + """

def calc(event, ctx):
    return {"employees": 42, "total": 181000}


def pay(event, ctx):
    return {**(event.data or {}), "paid": True}


def trigger(event, ctx):
    return {"month": "current"}
""",
          "requirements.txt": ""}),
      user="make workflow payroll: calc-salaries then pay-salaries. but NOBODY may start it from http, it is money!",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow options http false orchestrator route",
            docs=[D("docs/workflows.md", "workflow-keys", start="| `options.http` |", end="removes the orchestrator's HTTP trigger |")]),
          S("propose_plan", steps=["Add workflow `payroll` with options.http: false: Calc (calc-salaries) -> Pay (pay-salaries, end)",
                                   "Validate (onprem, prod), invoke calc-salaries as a workflow task"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.payroll",
            value={"options": {"http": False}, "start_at": "Calc",
                   "states": {"Calc": {"type": "task", "function": "calc-salaries", "next": "Pay"},
                              "Pay": {"type": "task", "function": "pay-salaries", "end": True}}}),
          S("invoke_local", function="calc-salaries", type="workflow", data={}),
      ],
      final="""Done. `payroll` has no HTTP route:

```yaml
workflows:
  payroll:
    options: {http: false}
    start_at: Calc
    states:
      Calc: {type: task, function: calc-salaries, next: Pay}
      Pay:  {type: task, function: pay-salaries, end: true}
```

`options.http: false` removes the orchestrator's HTTP trigger, so `POST /workflows/payroll` does not exist [docs/workflows.md#workflow-keys].

- `pskit validate` (onprem, prod): valid.
- `calc-salaries` as a workflow step: `{"employees": 42, "total": 181000}`.

Note: `calc-salaries` and `pay-salaries` have no HTTP events either, good. On premises the admin API (`/__pskit/...`) can still start runs, so set `provider.options.admin_token` (from `${env:...}`) if you haven't. Local run: `pskit workflow run payroll`. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 151
    B(151, stage="staging", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: scans
provider:
  name: onprem
  region: local
  options:
    port: 8141
    services:
      storage: {use: directory, path: /data/buckets}
functions: {}
""",
          "requirements.txt": ""}),
      user="The scanner software already writes into /data/buckets/scanner-out (it creates that folder itself, pskit must not). When a .tif lands under scans/, run `ocr-page` with the file name. Don't fire for files that were there before.",
      steps=[
          S("get_project"),
          S("search_docs", query="storage existing true bucket on premises first start",
            docs=[D("docs/providers.md", "onprem-on-premises", start="Omitted services default to `builtin`", end="(`..`, slashes and NUL are rejected)."),
                  D("docs/providers.md", "onprem-on-premises", start="| storage |", end="does not emit them |")]),
          S("propose_plan", steps=["Write `app/ocr.py`: log and return each key",
                                   "Add `ocr-page` with storage {bucket: scanner-out, existing: true, prefix: scans/, suffix: .tif, events: [created]}",
                                   "Validate (onprem, staging), invoke"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/ocr.py", content=FUTURE + """

def ocr_page(event, ctx):
    pages = []
    for record in event.records:
        ctx.logger.info("ocr page", extra={"key": record.key, "size": record.size})
        pages.append(record.key)
    return {"pages": pages}
"""),
          S("set_config", path="functions.ocr-page",
            value={"handler": "app.ocr.ocr_page",
                   "events": [{"storage": {"bucket": "scanner-out", "existing": True, "prefix": "scans/",
                                           "suffix": ".tif", "events": ["created"]}}]}),
          S("invoke_local", function="ocr-page", type="storage",
            data={"bucket": "scanner-out", "key": "scans/batch-12/page-001.tif", "size": 734002, "action": "created"}),
      ],
      final="""Added `ocr-page`:

```yaml
- storage: {bucket: scanner-out, existing: true, prefix: scans/, suffix: .tif, events: [created]}
```

- `existing: true`: the host does not create `/data/buckets/scanner-out`. It waits until the folder appears.
- Files already in the folder at the first start are recorded and not sent, so only new scans fire [docs/providers.md#onprem-on-premises].

- validate (onprem, staging): valid.
- invoke: `{"pages": ["scans/batch-12/page-001.tif"]}`.

The host user needs read access to that folder. Deploy: `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 152
    B(152, stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#using-a-resource-from-an-event", "docs/resources.md#provider-support"],
      project=dict(files={
          "pskit.yml": """service: monitoring
provider:
  name: onprem
  region: local
  options:
    port: 8142
functions: {}
""",
          "requirements.txt": ""}),
      user="i want one 'alerts' channel where messages go, and two functions listening: one writes to log file, one counts them. how do i make the channel?",
      steps=[
          S("get_project"),
          S("search_docs", query="topic resource two functions use resource event",
            docs=[D("docs/resources.md", "using-a-resource-from-an-event", end="the event also sets a different `name`/`bucket`.")]),
          S("propose_plan", steps=["Add resources.alerts: type topic (managed: the host creates it)",
                                   "Write `app/alerts.py` with `log_alert` and `count_alerts`",
                                   "Add `alert-log` and `alert-count`, both with `- topic: {resource: alerts}`",
                                   "Validate for onprem and invoke alert-count"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.alerts", value={"type": "topic"}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/alerts.py", content=FUTURE + """
COUNT = {"total": 0}


def log_alert(event, ctx):
    for record in event.records:
        ctx.logger.warning("alert", extra={"alert": record.json(default=record.text())})
    return {"logged": len(event.records)}


def count_alerts(event, ctx):
    COUNT["total"] += len(event.records)
    return {"total": COUNT["total"]}
"""),
          S("set_config", path="functions.alert-log",
            value={"handler": "app.alerts.log_alert", "events": [{"topic": {"resource": "alerts"}}]}),
          S("set_config", path="functions.alert-count",
            value={"handler": "app.alerts.count_alerts", "events": [{"topic": {"resource": "alerts"}}]}),
          S("invoke_local", function="alert-count", type="topic", data=[{"level": "high", "msg": "disk 95%"}]),
      ],
      final="""The "channel" is a **topic**. I made it a resource called `alerts`, and both functions listen to it:

```yaml
resources:
  alerts:
    type: topic
functions:
  alert-log:
    handler: app.alerts.log_alert
    events:
      - topic: {resource: alerts}
  alert-count:
    handler: app.alerts.count_alerts
    events:
      - topic: {resource: alerts}
```

Every message sent to `alerts` goes to **both** functions. On premises the host creates the topic when it starts [docs/resources.md#provider-support].

- `pskit validate` (onprem): valid.
- `alert-count` with one test alert: `{"total": 1}`.

The count is in memory, so it starts at 0 after a restart. Deploy: **Deploy** page or `pskit deploy -s dev`. Then send a test from **Resources** > **Test**."""),

    # ------------------------------------------------------------------ 153
    B(153, stage="prod", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/smtp/README.md#what-the-handler-receives"],
      project=dict(files={
          "pskit.yml": """service: mailroom
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8143
resources:
  company-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.40, port: 25, domains: in.example.com, hostname: mail.in.example.com}
functions:
  archive:
    handler: app.mail.archive
    events:
    - smtp: {resource: company-mail}
""",
          "app/__init__.py": "",
          "app/mail.py": FUTURE + """

def archive(event, ctx):
    return {"archived": True}
""",
          "requirements.txt": ""}),
      user="from pskit resources onprem logs company-mail:\n\n  12:01:07 accepted <billing@in.example.com> from vendor@example.org -> host 200\n  12:03:40 accepted <support@in.example.com> from user@example.org -> host 200\n\nboth go to archive. I want a function `route-mail` that says 'billing' or 'support' or 'other' depending on which address it was sent to (real recipients, not the To header).",
      steps=[
          S("get_project"),
          S("search_docs", query="smtp envelope rcpt_to real recipients",
            docs=[D("docs/smtp/README.md", "what-the-handler-receives", start="| Field | |", end="the real recipients on this server) |")]),
          S("propose_plan", steps=["Write `app/route.py`: read event.data[\"envelope\"][\"rcpt_to\"], map billing@ / support@ to a label",
                                   "Add `route-mail` with `- smtp: {resource: company-mail}`",
                                   "Validate (onprem, prod) and run a test mail locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/route.py", content=FUTURE + """

ROUTES = {"billing": "billing", "support": "support"}


def route_mail(event, ctx):
    mail = event.data or {}
    rcpts = (mail.get("envelope") or {}).get("rcpt_to") or mail.get("to") or []
    labels = sorted({ROUTES.get(str(r).split("@")[0].lower(), "other") for r in rcpts}) or ["other"]
    ctx.logger.info("mail routed", extra={"rcpt": rcpts, "labels": labels})
    return {"labels": labels}
"""),
          S("set_config", path="functions.route-mail",
            value={"handler": "app.route.route_mail", "events": [{"smtp": {"resource": "company-mail"}}]}),
          S("invoke_local", function="route-mail", type="smtp",
            data={"from": "vendor@example.org", "to": ["billing@in.example.com"], "subject": "Invoice 9921",
                  "text": "attached"}),
      ],
      final="""Added `route-mail` on `company-mail`. It uses the **SMTP envelope** (`event.data["envelope"]["rcpt_to"]`), which holds the real recipients on your server, not what the To header claims [docs/smtp/README.md#what-the-handler-receives]. `billing@...` gives `billing`, `support@...` gives `support`, and anything else gives `other`. If the envelope is missing it falls back to `to`.

- `pskit validate` (onprem, prod): valid.
- Local test mail to `billing@in.example.com`: `{"labels": ["billing"]}`.

`archive` still gets every mail. Deploy: **Deploy** page (typed confirmation) or `pskit deploy -s prod`. Then `pskit resources onprem logs company-mail` shows each delivery, and **Logs** shows the label."""),

    # ------------------------------------------------------------------ 154
    B(154, stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine", "docs/configuration.md#stages-per-stage-overrides"],
      project=dict(files={
          "pskit.yml": """service: crm
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8144
    deploy: {python: bundle, path: /opt/pskit/crm}
functions:
  contacts:
    handler: app.crm.contacts
    events:
    - http: GET /contacts
""",
          "app/__init__.py": "",
          "app/crm.py": FUTURE + """

def contacts(event, ctx):
    return []
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS}),
      user="Make each stage go to its own saved server permanently: staging -> app-2, prod -> app-1. dev stays on this laptop. Keep python bundle and the path for both servers.",
      steps=[
          S("get_project"),
          S("search_docs", query="stages override deploy server per stage",
            docs=[D("docs/resource-guides/onprem/services.md", "deploy-the-functions-to-a-chosen-machine", start="or permanently, per stage:", end="stay. In the studio, **Deploy → Machine** picks one for that run.")]),
          S("propose_plan", steps=["Add stages.staging.provider.options.deploy.server: app-2",
                                   "Add stages.prod.provider.options.deploy.server: app-1 (dicts deep-merge, so python and path stay)",
                                   "Validate for onprem as staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages",
            value={"staging": {"provider": {"options": {"deploy": {"server": "app-2"}}}},
                   "prod": {"provider": {"options": {"deploy": {"server": "app-1"}}}}}),
      ],
      final="""Added per-stage overrides:

```yaml
stages:
  staging:
    provider: {options: {deploy: {server: app-2}}}
  prod:
    provider: {options: {deploy: {server: app-1}}}
```

Dicts are deep-merged, so each stage keeps `python: bundle` and `path: /opt/pskit/crm` from `provider.options.deploy` [docs/configuration.md#precedence-later-wins]. `dev` has no override, so it stays local. Each stage has its own Terraform state, so the two servers never overwrite each other [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine].

`pskit validate` (onprem, staging): valid.

Deploy: `pskit deploy -s staging` goes to app-2 and `pskit deploy -s prod` to app-1 (or **Deploy** page with that stage). `pskit deploy --server NAME` still overrides it for a single run."""),

    # ------------------------------------------------------------------ 155
    B(155, stage="dev", mode="auto", page="Cluster", persona="beginner",
      sources=["docs/cluster.md#set-up", "docs/cluster.md#one-server-or-the-cluster-per-deploy"],
      project=dict(files={
          "pskit.yml": """service: lab-api
provider:
  name: onprem
  region: local
  options:
    port: 8145
functions:
  ping:
    handler: app.lab.ping
    events:
    - http: GET /ping
""",
          "app/__init__.py": "",
          "app/lab.py": FUTURE + """

def ping(event, ctx):
    return {"pong": True}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="my colleague made a cluster called k3s-lab in studio. how do my functions go there? please do it, normal settings are fine",
      steps=[
          S("get_project"),
          S("search_docs", query="point functions at cluster options.cluster",
            docs=[D("docs/cluster.md", "set-up", start="4. **Point the functions at the cluster**", end="#   memory: 256                   # MB each replica reserves (default 256)")]),
          S("propose_plan", steps=["provider.options.cluster: k3s-lab (default replicas, cpu and memory)",
                                   "provider.options.host: 0.0.0.0 so the cluster's port answers for other machines",
                                   "Validate for onprem"]),
          S("set_config", path="provider.options.cluster", value="k3s-lab"),
          S("set_config", path="provider.options.host", value="0.0.0.0"),
      ],
      final="""Done. Your project now points at the cluster `k3s-lab` with the normal settings:

```yaml
provider:
  options:
    host: 0.0.0.0
    port: 8145
    cluster: k3s-lab
```

The normal settings are 2 web replicas plus 1 main replica, each reserving 0.25 CPU and 256 MB [docs/cluster.md#set-up]. `host: 0.0.0.0` lets the port answer for other machines. Without it, validate warned that the host would only bind 127.0.0.1.

- `pskit validate` (onprem): valid.

Nothing moves until you deploy: **Deploy** page (Run on > Scaling cluster) or `pskit deploy -s dev`. Docker must run on your computer to build the image. After that, `/ping` answers on port 8145 of every cluster server."""),

    # ------------------------------------------------------------------ 156
    B(156, stage="prod", mode="auto", page="Load balancers", persona="terse_expert",
      sources=["docs/load-balancers.md#create-one-and-put-projects-on-it", "docs/load-balancers.md#the-six-algorithms"],
      project=dict(files={
          "pskit.yml": """service: search
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8146
    cluster: prod
functions:
  query:
    handler: app.search.query
    events:
    - http: GET /q
""",
          "app/__init__.py": "",
          "app/search.py": FUTURE + """

def query(event, ctx):
    return {"hits": []}
""",
          "requirements.txt": "",
          ".pskit/onprem-servers.json": SERVERS,
          ".pskit/onprem-clusters.json": CLUSTERS}),
      user="route search on lb edge, weighted rr: app-1 x3, app-2 x1 (app-1 has 4x cpu)",
      steps=[
          S("get_project"),
          S("search_docs", query="balancer weights weighted_round_robin",
            docs=[D("docs/load-balancers.md", "the-six-algorithms", words=150)]),
          S("propose_plan", steps=["provider.options.balancer: {name: edge, algorithm: weighted_round_robin, weights: {app-1: 3, app-2: 1}}",
                                   "Validate (onprem, prod)"]),
          S("set_config", path="provider.options.balancer",
            value={"name": "edge", "algorithm": "weighted_round_robin", "weights": {"app-1": 3, "app-2": 1}}),
      ],
      final="""Set:

```yaml
provider:
  options:
    cluster: prod
    balancer: {name: edge, algorithm: weighted_round_robin, weights: {app-1: 3, app-2: 1}}
```

No `path`, so the route is `/search/` (the service name). app-1 gets about 3 of every 4 requests [docs/load-balancers.md#the-six-algorithms].

validate (onprem, prod): valid.

Applied on the next deploy: `pskit deploy -s prod`. Verify with `pskit lb status edge`, and see which server answered with `pskit lb logs edge -n 200` (`upstream=`)."""),

    # ------------------------------------------------------------------ 157
    B(157, stage="staging", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#variables", "docs/configuration.md#provider"],
      project=dict(files={
          "pskit.yml": """service: tickets
provider:
  name: onprem
  region: local
  options:
    port: 8147
custom:
  support_email: help@example.com
functions:
  open-ticket:
    handler: app.tickets.open_ticket
    events:
    - http: POST /tickets
  daily-summary:
    handler: app.tickets.summary
    events:
    - schedule: 0 18 * * *
""",
          "app/__init__.py": "",
          "app/tickets.py": FUTURE + """

def open_ticket(event, ctx):
    return {"opened": True}, 201


def summary(event, ctx):
    return {"sent": True}
""",
          "requirements.txt": ""}),
      user="all functions need SUPPORT_EMAIL from the custom block, and LOG_FORMAT=json. but daily-summary need LOG_FORMAT=text. dont write the email twice",
      steps=[
          S("get_project"),
          S("search_docs", query="self custom variable provider environment",
            docs=[D("docs/configuration.md", "variables", end="| `${self:dotted.path}` | any value of the merged config, e.g. `${self:service}`, `${self:custom.table}` |")]),
          S("propose_plan", steps=["provider.environment: {SUPPORT_EMAIL: ${self:custom.support_email}, LOG_FORMAT: json}",
                                   "functions.daily-summary.environment: {LOG_FORMAT: text}",
                                   "Validate (onprem, staging)"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.environment",
            value={"SUPPORT_EMAIL": "${self:custom.support_email}", "LOG_FORMAT": "json"}),
          S("set_config", path="functions.daily-summary.environment", value={"LOG_FORMAT": "text"}),
      ],
      final="""Done:

```yaml
provider:
  environment:
    SUPPORT_EMAIL: ${self:custom.support_email}
    LOG_FORMAT: json
functions:
  daily-summary:
    environment:
      LOG_FORMAT: text
```

`provider.environment` goes to every function, and a function's own `environment` wins for the same name. So `daily-summary` gets `text` and the others get `json`. `${self:custom.support_email}` reads the value from your `custom` block, so the email is written only once [docs/configuration.md#variables].

`pskit validate` (onprem, staging): valid.

You can see both values on the **Functions** page, in each function's Environment variables section. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 158
    B(158, stage="prod", mode="auto", page="Functions", persona="beginner",
      sources=["docs/configuration.md#variables", "docs/handlers.md#context"],
      project=dict(files={
          "pskit.yml": """service: about
provider:
  name: onprem
  region: local
  options:
    port: 8148
functions:
  version:
    handler: app.about.version
    events:
    - http: GET /version
""",
          "app/__init__.py": "",
          "app/about.py": FUTURE + """

def version(event, ctx):
    return {"version": "1.4.0"}
""",
          "requirements.txt": ""}),
      user="the /version page should also show the app name and if it is dev or prod. can that be automatic so i dont type it?",
      steps=[
          S("get_project"),
          S("search_docs", query="context stage service handler",
            docs=[D("docs/handlers.md", "context", words=120)]),
          S("propose_plan", steps=["Return ctx.service and ctx.stage from `version` (no config change needed)",
                                   "Validate (onprem, prod) and call /version"]),
          S("write_file", path="app/about.py", content=FUTURE + """

def version(event, ctx):
    return {"version": "1.4.0", "app": ctx.service, "stage": ctx.stage}
"""),
          S("validate"),
          S("invoke_local", function="version", method="GET", path="/version"),
      ],
      final="""Yes, it's automatic. Every function gets the service name and the stage in its context, `ctx.service` and `ctx.stage` [docs/handlers.md#context], so you don't need extra settings:

```python
def version(event, ctx):
    return {"version": "1.4.0", "app": ctx.service, "stage": ctx.stage}
```

- `pskit validate` (onprem, prod): valid.
- Local call `/version`: 200, `{"version": "1.4.0", "app": "about", "stage": "prod"}`.

When you deploy with another stage (for example `pskit deploy -s dev`), it shows `dev` by itself. Deploy prod: **Deploy** page (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 159
    B(159, stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#fields", "docs/resources.md#what-handlers-receive"],
      project=dict(files={
          "pskit.yml": """service: catalog-docs
provider:
  name: onprem
  region: local
  options:
    port: 8149
functions:
  products:
    handler: app.products.list_products
    events:
    - http: GET /products
  reindex:
    handler: app.products.reindex
    events:
    - schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/products.py": FUTURE + """

def list_products(event, ctx):
    return []


def reindex(event, ctx):
    return {"reindexed": 0}
""",
          "requirements.txt": ""}),
      user="On AWS this used DocumentDB with a connection string from Secrets Manager. Here it's our own MongoDB at mongo-1.example.com:27017, db `catalog`. The full URL with password is in CATALOG_MONGO_URL on the host. Both functions need it; let products show what it got.",
      steps=[
          S("get_project"),
          S("search_docs", query="database resource functions default all PSKIT_RESOURCE variables",
            docs=[D("docs/resources.md", "what-handlers-receive", end="`pskit invoke` and `pskit dev` inject the same variables locally.")]),
          S("propose_plan", steps=["Add resources.catalog-db: database, external, connection {host, port 27017, database catalog, url_env: CATALOG_MONGO_URL} (no `functions`: every function gets it)",
                                   "`list_products` returns the bound host/database and whether the URL is set",
                                   "Validate for onprem, call GET /products"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.catalog-db",
            value={"type": "database", "external": True,
                   "connection": {"host": "mongo-1.example.com", "port": 27017, "database": "catalog",
                                  "url_env": "CATALOG_MONGO_URL"}}),
          S("write_file", path="app/products.py", content=FUTURE + """from py_serverless_kit import resource


def list_products(event, ctx):
    db = resource("catalog-db")
    return {
        "db": f'{db["host"]}:{db["port"]}/{db["database"]}',
        "url_set": bool(ctx.env.get(db["url_env"])),
        "products": [],
    }


def reindex(event, ctx):
    return {"reindexed": 0}
"""),
          S("validate"),
          S("invoke_local", function="products", method="GET", path="/products"),
      ],
      final="""Instead of Secrets Manager, the database is a resource. pskit.yml has only the *name* of the variable that holds the URL:

```yaml
resources:
  catalog-db:
    type: database
    external: true
    connection:
      host: mongo-1.example.com
      port: 27017
      database: catalog
      url_env: CATALOG_MONGO_URL
```

Without `functions:`, every function you wrote gets the binding, so both `products` and `reindex` have it [docs/resources.md#fields]. They see `PSKIT_RESOURCE_CATALOG_DB_*` variables, read with `resource("catalog-db")` [docs/resources.md#what-handlers-receive].

- `pskit validate` (onprem): valid.
- `GET /products`: 200, `{"db": "mongo-1.example.com:27017/catalog", "url_set": false, "products": []}`. The URL isn't set on this machine.

Connect with `pymongo.MongoClient(ctx.env[db["url_env"]])` after adding `pymongo` to requirements.txt. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 160
    B(160, stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/events.md#schedule", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: greenhouse
provider:
  name: onprem
functions: {}
""",
          "requirements.txt": ""}),
      user="New project for our greenhouse sensors, on a small server in the building: sensors POST /readings with {sensor, temp_c}; temp_c above 35 is returned as alert=true. Separately, every 5 minutes a `heartbeat` function logs that the service is alive. Port 8150, reachable from the LAN.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["provider: region local, options host 0.0.0.0, port 8150",
                                   "Write `app/greenhouse.py` with `readings` (BadRequest when fields are missing) and `heartbeat`",
                                   "Add `readings` on POST /readings and `heartbeat` with schedule rate 5 minutes",
                                   "Validate for onprem, POST a hot reading locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.region", value="local"),
          S("set_config", path="provider.options", value={"host": "0.0.0.0", "port": 8150}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/greenhouse.py", content=FUTURE + """from py_serverless_kit import BadRequest

ALERT_C = 35.0


def readings(event, ctx):
    body = event.http.json(default={}) or {}
    if "sensor" not in body or "temp_c" not in body:
        raise BadRequest("sensor and temp_c are required")
    temp = float(body["temp_c"])
    return {"sensor": body["sensor"], "temp_c": temp, "alert": temp > ALERT_C}


def heartbeat(event, ctx):
    ctx.logger.info("greenhouse service alive")
    return {"alive": True}
"""),
          S("set_config", path="functions",
            value={"readings": {"handler": "app.greenhouse.readings", "events": [{"http": "POST /readings"}]},
                   "heartbeat": {"handler": "app.greenhouse.heartbeat", "events": [{"schedule": "5 minutes"}]}}),
          S("invoke_local", function="readings", method="POST", path="/readings", data={"sensor": "gh-3", "temp_c": 36.2}),
      ],
      final="""The greenhouse project is set up:

```yaml
provider:
  name: onprem
  region: local
  options: {host: 0.0.0.0, port: 8150}
functions:
  readings:
    handler: app.greenhouse.readings
    events:
      - http: POST /readings
  heartbeat:
    handler: app.greenhouse.heartbeat
    events:
      - schedule: 5 minutes
```

- `pskit validate` (onprem): valid.
- Local `POST /readings {"sensor": "gh-3", "temp_c": 36.2}`: 200, `{"sensor": "gh-3", "temp_c": 36.2, "alert": true}`.
- A missing `sensor` or `temp_c` gives 400.

`host: 0.0.0.0` lets the sensors on the LAN reach port 8150. On premises the host runs the 5-minute schedule itself [docs/providers.md#onprem-on-premises]. To run this on the building's server instead of this machine, save it under **Resources** > **+ On-prem service** > Servers and set `options.deploy.server`.

Test the heartbeat: `pskit invoke -f heartbeat -t schedule`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),
]
