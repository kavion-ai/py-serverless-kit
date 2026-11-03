"""Category B (build / add), batch 5. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def B(n, **kw):
    return dict(id=f"b_build-{n:04d}", category="b_build", **kw)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 81
    B(81, provider="ibm", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#ibm-code-engine-functions", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: units
provider:
  name: ibm
  region: jp-tok
  runtime: python3.11
functions: {}
""",
          "requirements.txt": ""}),
      user="Add `GET /convert?c=<celsius>` on IBM Code Engine that returns {\"celsius\": c, \"fahrenheit\": f} rounded to one decimal. A missing or non-numeric `c` must return 400. Timeout 60 s, 256 MB.",
      steps=[
          S("get_project"),
          S("search_docs", query="ibm code engine limits timeout memory runtime",
            docs=[D("docs/providers.md", "ibm-code-engine-functions", start="**Limits:**")]),
          S("propose_plan", steps=["Write `app/convert.py`: parse ?c as float, BadRequest when missing/invalid, return both values rounded",
                                   "Add function `convert` on GET /convert with timeout 60 and memory 256",
                                   "Validate for ibm and call /convert?c=21.5 locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/convert.py", content=FUTURE + """from py_serverless_kit import BadRequest


def convert(event, ctx):
    raw = event.http.query.get("c")
    try:
        celsius = float(raw)
    except (TypeError, ValueError):
        raise BadRequest("query parameter c must be a number")
    return {"celsius": round(celsius, 1), "fahrenheit": round(celsius * 9 / 5 + 32, 1)}
"""),
          S("set_config", path="functions.convert",
            value={"handler": "app.convert.convert", "timeout": 60, "memory": 256,
                   "events": [{"http": "GET /convert"}]}),
          S("invoke_local", function="convert", method="GET", path="/convert?c=21.5"),
      ],
      final="""Added `convert` on `GET /convert` (timeout 60 s, 256 MB). Both are within Code Engine's limits of 120 s and 4096 MB [docs/providers.md#ibm-code-engine-functions].

- `pskit validate` for ibm: valid.
- Local call `?c=21.5`: 200, `{"celsius": 21.5, "fahrenheit": 70.7}`.
- A missing or non-numeric `c` raises `BadRequest`, which becomes a 400 JSON error [docs/handlers.md#errors].

Check the 400: `pskit invoke -f convert --path "/convert?c=abc"`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 82
    B(82, provider="oracle", stage="staging", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#embedded-orchestrator", "docs/workflows.md#engines"],
      project=dict(files={
          "pskit.yml": """service: claims
provider:
  name: oracle
  region: eu-amsterdam-1
  options:
    compartment_id: ${env:OCI_COMPARTMENT_ID, ocid1.compartment.oc1..aaaa}
    subnet_ids:
    - ${env:OCI_SUBNET_ID, ocid1.subnet.oc1..aaaa}
    image_repository: ${env:OCI_IMAGE_REPO, ams.ocir.io/mytenancy/claims}
functions:
  check-claim:
    handler: app.claims.check
  pay-claim:
    handler: app.claims.pay
""",
          "app/__init__.py": "",
          "app/claims.py": FUTURE + """

def check(event, ctx):
    claim = dict(event.data or {})
    return {**claim, "valid": claim.get("amount", 0) > 0}


def pay(event, ctx):
    claim = dict(event.data or {})
    return {**claim, "paid": bool(claim.get("valid"))}
""",
          "requirements.txt": ""}),
      user="I have two functions, check-claim and pay-claim. Can they run one after the other automatically on Oracle?",
      steps=[
          S("get_project"),
          S("search_docs", query="workflow oracle embedded orchestrator",
            docs=[D("docs/workflows.md", "engines", start="| all others", end="| all others"),
                  D("docs/workflows.md", "embedded-orchestrator", end="Every run has an `execution_id`")]),
          S("propose_plan", steps=["Add workflow `handle-claim`: Check (check-claim) -> Pay (pay-claim, end)",
                                   "Validate for oracle (staging) and run check-claim locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.handle-claim",
            value={"start_at": "Check",
                   "states": {"Check": {"type": "task", "function": "check-claim", "next": "Pay"},
                              "Pay": {"type": "task", "function": "pay-claim", "end": True}}}),
          S("invoke_local", function="check-claim", type="workflow", data={"claim_id": "C-5", "amount": 250}),
      ],
      final="""Yes. I added a **workflow** called `handle-claim` that runs `check-claim` first and then `pay-claim`, with the first one's result as the input of the second:

```yaml
workflows:
  handle-claim:
    start_at: Check
    states:
      Check: {type: task, function: check-claim, next: Pay}
      Pay:   {type: task, function: pay-claim, end: true}
```

Oracle has no workflow service that pskit uses. pskit adds a helper function, `handle-claim-orchestrator`, that runs both steps [docs/workflows.md#engines].

- `pskit validate` (oracle, staging): valid, with two warnings. First, the whole run has to fit in one call of the helper function (300 s max on Oracle). Second, OCI's API Gateway needs an IAM policy, because the helper gets an HTTP route.
- `check-claim` run locally with amount 250: returned the claim with `"valid": true`.

After deploy, you start it with `POST /workflows/handle-claim` and the claim as the body [docs/workflows.md#embedded-orchestrator]. Try the whole thing locally first: `pskit workflow run handle-claim -i '{"claim_id": "C-5", "amount": 250}'`. Deploy: **Deploy** page or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 83
    B(83, provider="cloudflare", stage="prod", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#returning-a-response"],
      project=dict(files={
          "pskit.yml": """service: edge-config
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, 0123456789abcdef0123456789abcdef}
functions: {}
""",
          "requirements.txt": ""}),
      user="GET /config.json -> {features:{beta:false}, stage}, Cache-Control: public, max-age=300",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/config.py` returning Response.json(..., headers={cache-control})",
                                   "Add `config` on GET /config.json",
                                   "Validate for cloudflare (prod), invoke"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/config.py", content=FUTURE + """from py_serverless_kit import Response


def config(event, ctx):
    body = {"features": {"beta": False}, "stage": ctx.stage}
    return Response.json(body, headers={"Cache-Control": "public, max-age=300"})
"""),
          S("set_config", path="functions.config",
            value={"handler": "app.config.config", "events": [{"http": "GET /config.json"}]}),
          S("invoke_local", function="config", method="GET", path="/config.json"),
      ],
      final="""Added `config` on `GET /config.json`, using `Response.json(body, headers=...)` [docs/handlers.md#returning-a-response].

- validate (cloudflare, prod): valid. The Pyodide warning doesn't matter here, because there are no dependencies.
- invoke: 200, `{"features": {"beta": false}, "stage": "prod"}` with the `Cache-Control: public, max-age=300` header.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 84
    B(84, provider="digitalocean", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: sessions-cleanup
provider:
  name: digitalocean
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE, fn-00000000-0000-0000-0000-000000000000}
functions: {}
""",
          "requirements.txt": ""}),
      user="need purge old login sessions each night 3 o clock, older than 24 hour. on digitalocean",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/purge.py`: read max_age_hours from the schedule input and log the purge",
                                   "Add function `purge-sessions` with schedule cron `0 3 * * *` and input {max_age_hours: 24}",
                                   "Validate for digitalocean and run the schedule locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/purge.py", content=FUTURE + """from datetime import datetime, timedelta, timezone


def purge(event, ctx):
    hours = int((event.data or {}).get("max_age_hours", 24))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    # delete sessions older than `cutoff` in your session store here
    ctx.logger.info("purge sessions", extra={"older_than": cutoff.isoformat()})
    return {"max_age_hours": hours}
"""),
          S("set_config", path="functions.purge-sessions",
            value={"handler": "app.purge.purge",
                   "events": [{"schedule": {"cron": "0 3 * * *", "input": {"max_age_hours": 24}}}]}),
          S("invoke_local", function="purge-sessions", type="schedule"),
      ],
      final="""Done. `purge-sessions` runs every night at 03:00 UTC with the input `{"max_age_hours": 24}`. DigitalOcean schedules are a 5-field cron and run in UTC [docs/events.md#schedule].

- `pskit validate` for digitalocean: valid, with one warning: `doctl` is not installed here. Deploy needs it.
- Local schedule run: returned `{"max_age_hours": 24}` and logged the cutoff time.

The real delete is still a comment, because I don't know where your sessions are stored. Tell me (Redis, a database, ...) and I'll add it.

Test: `pskit invoke -f purge-sessions -t schedule`. Deploy: **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 85
    B(85, provider="alibaba", stage="prod", mode="auto", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#embedded-orchestrator", "docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: shipping
provider:
  name: alibaba
  region: cn-hangzhou
functions:
  quote-express:
    handler: app.ship.express
  quote-standard:
    handler: app.ship.standard
""",
          "app/__init__.py": "",
          "app/ship.py": FUTURE + """

def express(event, ctx):
    return {**(event.data or {}), "carrier": "express", "days": 1}


def standard(event, ctx):
    return {**(event.data or {}), "carrier": "standard", "days": 4}
""",
          "requirements.txt": ""}),
      user="Create workflow `pick-carrier` on Function Compute: if $.priority equals \"high\" OR $.weight_kg is below 1, use quote-express; otherwise quote-standard. Set a 120 s workflow timeout.",
      steps=[
          S("get_project"),
          S("search_docs", query="choice or combinator equals lt",
            docs=[D("docs/workflows.md", "choice-rules", end="next: AskEmail")]),
          S("propose_plan", steps=["Add workflow `pick-carrier` (timeout 120): Route choice with or[priority equals high, weight_kg lt 1] -> Express, default Standard",
                                   "Express / Standard: task states that end",
                                   "Validate for alibaba (prod) and run quote-express locally"]),
          S("set_config", path="workflows.pick-carrier",
            value={"timeout": 120, "start_at": "Route",
                   "states": {"Route": {"type": "choice",
                                        "choices": [{"or": [{"variable": "$.priority", "equals": "high"},
                                                            {"variable": "$.weight_kg", "lt": 1}],
                                                     "next": "Express"}],
                                        "default": "Standard"},
                              "Express": {"type": "task", "function": "quote-express", "end": True},
                              "Standard": {"type": "task", "function": "quote-standard", "end": True}}}),
          S("invoke_local", function="quote-express", type="workflow", data={"order": 12, "priority": "high", "weight_kg": 3}),
      ],
      final="""Added `pick-carrier`:

```yaml
workflows:
  pick-carrier:
    timeout: 120
    start_at: Route
    states:
      Route:
        type: choice
        choices:
          - or:
              - {variable: $.priority, equals: high}
              - {variable: $.weight_kg, lt: 1}
            next: Express
        default: Standard
      Express:  {type: task, function: quote-express, end: true}
      Standard: {type: task, function: quote-standard, end: true}
```

- validate (alibaba, prod): valid, with the embedded-engine warning (runtime capped by the function timeout, 3600 s max on Function Compute). Alibaba has no native engine in pskit, so it runs in a `pick-carrier-orchestrator` function. `timeout: 120` is that function's timeout and is also enforced by the engine, so a run that goes over ends `TIMED_OUT` [docs/workflows.md#workflow-keys].
- `quote-express` run locally: returned the order with `"carrier": "express", "days": 1`.

Check both branches: `pskit workflow run pick-carrier -i '{"priority": "low", "weight_kg": 5}' --history`. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 86
    B(86, provider="tencent", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http", "docs/handlers.md#httprequest"],
      project=dict(files={
          "pskit.yml": """service: notes
provider:
  name: tencent
  region: ap-hongkong
functions: {}
""",
          "requirements.txt": ""}),
      user="In SAM I had one Lambda `NotesFunction` with two Api events: GET /notes and POST /notes, and the code switched on event['httpMethod']. Keep it as one function on SCF.",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/notes.py`: one handler that branches on event.http.method (GET lists, POST adds and returns 201)",
                                   "Add function `notes` with two events: GET /notes and POST /notes",
                                   "Validate for tencent and POST a note locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/notes.py", content=FUTURE + """from py_serverless_kit import BadRequest

NOTES = []


def notes(event, ctx):
    if event.http.method == "POST":
        text = (event.http.json(default={}) or {}).get("text", "").strip()
        if not text:
            raise BadRequest("text is required")
        note = {"id": len(NOTES) + 1, "text": text}
        NOTES.append(note)
        return note, 201
    return NOTES
"""),
          S("set_config", path="functions.notes",
            value={"handler": "app.notes.notes", "events": [{"http": "GET /notes"}, {"http": "POST /notes"}]}),
          S("invoke_local", function="notes", method="POST", path="/notes", data={"text": "buy stamps"}),
      ],
      final="""One function, two routes, same as your SAM template:

```yaml
functions:
  notes:
    handler: app.notes.notes
    events:
      - http: GET /notes
      - http: POST /notes
```

In the handler, `event['httpMethod']` becomes `event.http.method`, and the body comes from `event.http.json()`. The same code works on every provider.

- `pskit validate` for tencent: valid.
- Local `POST /notes` with `{"text": "buy stamps"}`: 201, `{"id": 1, "text": "buy stamps"}`.

`NOTES` is in memory, so use a real store before production. Test the GET with `pskit invoke -f notes --method GET --path /notes`. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 87
    B(87, provider="huawei", stage="staging", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: shift-report
provider:
  name: huawei
  region: ap-southeast-3
functions:
  end-of-shift:
    handler: app.shift.report
""",
          "app/__init__.py": "",
          "app/shift.py": FUTURE + """

def report(event, ctx):
    ctx.logger.info("end of shift report")
    return {"report": "sent"}
""",
          "requirements.txt": ""}),
      user="end-of-shift report: only monday to friday 18:00. weekend no",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Add schedule cron `0 18 * * 1-5` to `end-of-shift`",
                                   "Validate for huawei (staging), run schedule locally"]),
          S("set_config", path="functions.end-of-shift.events", value=[{"schedule": "0 18 * * 1-5"}]),
          S("invoke_local", function="end-of-shift", type="schedule"),
      ],
      final="""Done: `- schedule: "0 18 * * 1-5"` on `end-of-shift`, so it runs Monday to Friday at 18:00 and not on weekends. pskit converts it to Huawei's 6-field cron [docs/events.md#schedule].

- validate (huawei, staging): valid.
- local schedule run: `{"report": "sent"}`.

The time is UTC. The docs list timezone support only for AWS, GCP and Alibaba, so shift the hour if you need local time. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 88
    B(88, provider="gcp", stage="staging", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#get_secret-secrets-on-every-provider"],
      project=dict(files={
          "pskit.yml": """service: partner-sync
provider:
  name: gcp
  region: europe-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions:
  sync:
    handler: app.sync.run
    events:
    - http: POST /sync
""",
          "app/__init__.py": "",
          "app/sync.py": FUTURE + """

def run(event, ctx):
    return {"synced": False}
""",
          "requirements.txt": ""}),
      user="On Lambda this read the partner key with boto3 secretsmanager.get_secret_value for the secret partner-api-key. We're on GCP now. What's the portable way? Wire it so sync reports whether the key is available.",
      steps=[
          S("get_project"),
          S("search_docs", query="get_secret portable secrets env driver",
            docs=[D("docs/handlers.md", "get_secret-secrets-on-every-provider")]),
          S("propose_plan", steps=["Use get_secret(\"partner-api-key\", default=\"\") in `sync` (no boto3)",
                                   "Give `sync` PSKIT_SECRET_PARTNER_API_KEY: ${env:PARTNER_API_KEY, } so the env driver finds it",
                                   "Validate for gcp (staging) and call POST /sync locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/sync.py", content=FUTURE + """from py_serverless_kit import get_secret


def run(event, ctx):
    partner_key = get_secret("partner-api-key", default="")
    if not partner_key:
        ctx.logger.warning("partner key missing")
    return {"synced": False, "key_available": bool(partner_key)}
"""),
          S("set_config", path="functions.sync.environment",
            value={"PSKIT_SECRET_PARTNER_API_KEY": "${env:PARTNER_API_KEY, }"}),
          S("invoke_local", function="sync", method="POST", path="/sync"),
      ],
      final="""The portable way is `get_secret()`. Same call on every provider, no boto3:

```python
from py_serverless_kit import get_secret

partner_key = get_secret("partner-api-key", default="")
```

The store comes from environment variables. With no store configured, the `env` driver reads `PSKIT_SECRET_PARTNER_API_KEY`, then `PARTNER_API_KEY` [docs/handlers.md#get_secret-secrets-on-every-provider]. So I gave `sync`:

```yaml
functions:
  sync:
    environment:
      PSKIT_SECRET_PARTNER_API_KEY: ${env:PARTNER_API_KEY, }
```

- `pskit validate` (gcp, staging): valid.
- Local `POST /sync`: 200 with `"key_available": false`, because `PARTNER_API_KEY` isn't set in this shell. Set it before deploying.

Note: `${env:...}` is resolved at deploy and ends up in Terraform state. If that's not acceptable, point `PSKIT_SECRETS_DRIVER` at Vault/OpenBao instead. The code stays the same. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 89
    B(89, provider="aws", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields", "docs/providers.md#aws-aws-lambda"],
      project=dict(files={
          "pskit.yml": """service: carts
provider:
  name: aws
  region: eu-west-1
functions:
  get-cart:
    handler: app.carts.get_cart
    events:
    - http: GET /carts/{cart_id}
""",
          "app/__init__.py": "",
          "app/carts.py": FUTURE + """

def get_cart(event, ctx):
    return {"cart_id": event.http.path_params["cart_id"], "items": []}
""",
          "requirements.txt": ""}),
      user="pls make pskit create dynamodb table carts for get-cart function",
      steps=[
          S("get_project"),
          S("search_docs", query="database resource dynamodb create",
            docs=[D("docs/resources.md", "fields", start="`database`, `cache` and `custom` must be", end="`database`, `cache` and `custom` must be"),
                  D("docs/providers.md", "aws-aws-lambda", start="  iam:", end="resources: [\"arn:aws:dynamodb")]),
          S("ask_user", question="pskit doesn't create databases. A `database` resource is always external: pskit only passes its details to your functions. Does the `carts` table already exist (or will you create it yourself)? Then I'll attach it and give get-cart read access.",
            options=["Yes, it exists (table carts, eu-west-1)", "No, stop"],
            answer="Yes, it exists (table carts, eu-west-1)"),
          S("propose_plan", steps=["Add resource `carts-table`: type database, external, connection {table: carts, region: eu-west-1}, functions [get-cart]",
                                   "Allow get-cart dynamodb:GetItem on the table via functions.get-cart.iam.statements",
                                   "Make get_cart return the bound table name; validate for aws and call it locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.carts-table",
            value={"type": "database", "external": True, "connection": {"table": "carts", "region": "eu-west-1"},
                   "functions": ["get-cart"]}),
          S("set_config", path="functions.get-cart.iam",
            value={"statements": [{"actions": ["dynamodb:GetItem"],
                                   "resources": ["arn:aws:dynamodb:eu-west-1:*:table/carts"]}]}),
          S("write_file", path="app/carts.py", content=FUTURE + """from py_serverless_kit import resource


def get_cart(event, ctx):
    table = resource("carts-table")
    return {"cart_id": event.http.path_params["cart_id"], "items": [], "table": table["table"]}
"""),
          S("validate"),
          S("invoke_local", function="get-cart", method="GET", path="/carts/c-1"),
      ],
      final="""pskit can't create the DynamoDB table, because `database` resources are always external [docs/resources.md#fields]. I attached your existing table instead:

```yaml
resources:
  carts-table:
    type: database
    external: true
    connection: {table: carts, region: eu-west-1}
    functions: [get-cart]
functions:
  get-cart:
    iam:
      statements:
        - actions: ["dynamodb:GetItem"]
          resources: ["arn:aws:dynamodb:eu-west-1:*:table/carts"]
```

- `pskit validate` for aws: valid.
- Local `GET /carts/c-1`: 200 with `"table": "carts"`, so the binding reaches the function.

To read items, use boto3 (`boto3.resource("dynamodb").Table(table["table"])`) and add `boto3` to requirements.txt. Deploy: **Deploy** or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 90
    B(90, provider="azure", stage="dev", mode="auto", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: uptime
provider:
  name: azure
  region: canadacentral
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions: {}
""",
          "requirements.txt": ""}),
      user="I just want something that writes 'still alive' to the logs every 5 minutes so I can see it's working",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/heartbeat.py` that logs 'still alive'",
                                   "Add function `heartbeat` with `schedule: 5 minutes`",
                                   "Validate for azure and run it locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/heartbeat.py", content=FUTURE + """

def beat(event, ctx):
    ctx.logger.info("still alive")
    return {"alive": True}
"""),
          S("set_config", path="functions.heartbeat",
            value={"handler": "app.heartbeat.beat", "events": [{"schedule": "5 minutes"}]}),
          S("invoke_local", function="heartbeat", type="schedule"),
      ],
      final="""Done. A new function `heartbeat` writes "still alive" to the logs every 5 minutes.

- `pskit validate` for azure: valid.
- A local run printed `still alive` and returned `{"alive": true}`.

After you deploy (**Deploy** page or `pskit deploy -s dev`), open the **Logs** page, or run `pskit logs --function heartbeat`, to see a line every 5 minutes. To run it once yourself: **Test** > **▶ Run locally**, or `pskit invoke -f heartbeat -t schedule`."""),

    # ------------------------------------------------------------------ 91
    B(91, provider="onprem", stage="staging", mode="ask", page="Setup", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/resources.md#on-premises-drivers"],
      project=dict(files={
          "pskit.yml": """service: geo-lookup
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8108
functions:
  lookup:
    handler: app.geo.lookup
    events:
    - http: GET /lookup
""",
          "app/__init__.py": "",
          "app/geo.py": FUTURE + """

def lookup(event, ctx):
    return {"configured": False}
""",
          "requirements.txt": ""}),
      user="`lookup` calls a paid geo API and needs GEO_API_KEY. I don't want the key in pskit.yml or in Terraform state at all; on our server it should come from a file next to the host. Set that up and make lookup report whether the key is present.",
      steps=[
          S("get_project"),
          S("search_docs", query="onprem env_file secrets host not terraform state",
            docs=[D("docs/resources.md", "on-premises-drivers", start="**Secrets.**", end="**Secrets.**")]),
          S("propose_plan", steps=["Set provider.options.env_file to .env.onprem (shipped as host.env, loaded at start, only its digest recorded)",
                                   "Change `lookup` to report whether GEO_API_KEY is in ctx.env",
                                   "Validate for onprem (staging) and call /lookup locally"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.env_file", value=".env.onprem"),
          S("write_file", path="app/geo.py", content=FUTURE + """

def lookup(event, ctx):
    return {"configured": bool(ctx.env.get("GEO_API_KEY"))}
"""),
          S("validate"),
          S("invoke_local", function="lookup", method="GET", path="/lookup"),
      ],
      final="""Set up:

```yaml
provider:
  options:
    env_file: .env.onprem
```

pskit ships `.env.onprem` with the host as `host.env` and loads it when the host starts. Only its digest is recorded, so the key never lands in pskit.yml or Terraform state [docs/resources.md#on-premises-drivers].

- `pskit validate` (onprem, staging): valid, with the warning that `.env.onprem` does not exist yet, so the host would start without it.
- Local `GET /lookup`: 200, `{"configured": false}`, as expected, because there is no key here.

Next: create `.env.onprem` with the line `GEO_API_KEY=<your key>`, and keep it out of git. Then deploy: **Deploy** or `pskit deploy -s staging`. For local tests, `pskit invoke -f lookup --env-file .env.onprem` loads the same file."""),

    # ------------------------------------------------------------------ 92
    B(92, provider="aws", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions", "docs/events.md#storage"],
      project=dict(files={
          "pskit.yml": """service: gallery
provider:
  name: aws
  region: us-east-1
functions: {}
""",
          "requirements.txt": ""}),
      user="thumbnails fn: arm64, 1024MB, 60s, s3 gallery-media prefix originals/ suffix .jpg",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/thumbs.py` (log key/size, return target key under thumbs/)",
                                   "Add `thumbnails`: architecture arm64, memory 1024, timeout 60, storage {bucket: gallery-media, prefix: originals/, suffix: .jpg}",
                                   "Validate for aws (prod), invoke one record"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/thumbs.py", content=FUTURE + """

def thumbnails(event, ctx):
    out = []
    for record in event.records:
        target = "thumbs/" + record.key.split("/", 1)[-1]
        ctx.logger.info("thumbnail", extra={"key": record.key, "size": record.size, "target": target})
        out.append(target)
    return {"targets": out}
"""),
          S("set_config", path="functions.thumbnails",
            value={"handler": "app.thumbs.thumbnails", "architecture": "arm64", "memory": 1024, "timeout": 60,
                   "events": [{"storage": {"bucket": "gallery-media", "prefix": "originals/", "suffix": ".jpg"}}]}),
          S("invoke_local", function="thumbnails", type="storage", data={"bucket": "gallery-media", "key": "originals/sunset.jpg"}),
      ],
      final="""Added `thumbnails`:

```yaml
functions:
  thumbnails:
    handler: app.thumbs.thumbnails
    architecture: arm64
    memory: 1024
    timeout: 60
    events:
      - storage: {bucket: gallery-media, prefix: originals/, suffix: .jpg}
```

- validate (aws, prod): valid.
- invoke: `{"targets": ["thumbs/sunset.jpg"]}`.

Write thumbnails outside `originals/`, as here, so the trigger doesn't loop. With arm64, pskit packages arm64 manylinux wheels when you add an image library to requirements.txt. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 93
    B(93, provider="gcp", stage="dev", mode="auto", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: app-feedback
provider:
  name: gcp
  region: australia-southeast1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, demo-project}
functions: {}
""",
          "requirements.txt": ""}),
      user="on my site app.example.com there is a thumbs up / thumbs down button. where does the click go? can you make the backend for it",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["Write `app/feedback.py`: accept {page, vote} where vote is up or down, 400 otherwise",
                                   "Add function `feedback` on POST /feedback, with CORS for https://app.example.com",
                                   "Validate for gcp and send one vote locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/feedback.py", content=FUTURE + """from py_serverless_kit import BadRequest


def vote(event, ctx):
    body = event.http.json(default={}) or {}
    if body.get("vote") not in ("up", "down"):
        raise BadRequest("vote must be 'up' or 'down'")
    ctx.logger.info("feedback", extra={"page": body.get("page"), "vote": body["vote"]})
    return {"thanks": True}
"""),
          S("set_config", path="functions.feedback",
            value={"handler": "app.feedback.vote",
                   "events": [{"http": {"path": "/feedback", "method": "POST",
                                        "cors": {"origins": ["https://app.example.com"]}}}]}),
          S("invoke_local", function="feedback", method="POST", path="/feedback", data={"page": "/pricing", "vote": "up"}),
      ],
      final="""The click goes to a small backend function. I made one: `feedback` on `POST /feedback`. Your page sends `{"page": "/pricing", "vote": "up"}` (or `"down"`) there.

- Only `https://app.example.com` may call it from the browser (CORS).
- `pskit validate` for gcp: valid.
- A test vote run locally: status 200, `{"thanks": true}`.

For now it only logs each vote. Tell me if you want to count them somewhere.

After you deploy (**Deploy** page or `pskit deploy -s dev`), `pskit info` shows the URL to use in your button's `fetch(...)`. Test locally: `pskit invoke -f feedback -d '{"page": "/", "vote": "down"}'`."""),

    # ------------------------------------------------------------------ 94
    B(94, provider="onprem", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#queue", "docs/providers.md#onprem-on-premises"],
      project=dict(files={
          "pskit.yml": """service: importer
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
functions:
  import-row:
    handler: app.rows.import_row
    events:
    - queue: {name: rows, dead_letter: rows-dlq, max_receive: 3}
""",
          "app/__init__.py": "",
          "app/rows.py": FUTURE + """

def import_row(event, ctx):
    for r in event.records:
        row = r.json()
        if "sku" not in row:
            raise ValueError("row without sku")
""",
          "requirements.txt": ""}),
      user="GET /__pskit/queues/rows-dlq -> {\"depth\": 12}\n12 messages stuck in the dead letter. I want a function that consumes rows-dlq and logs each one with its receive count so we can look at them later",
      steps=[
          S("get_project"),
          S("search_docs", query="record attributes onprem queue dead letter consumer",
            docs=[D("docs/handlers.md", "record")]),
          S("propose_plan", steps=["Add `inspect_dead` to `app/rows.py`: log id, body, receive count and source queue of each message (never fails)",
                                   "Add function `inspect-dlq` with `- queue: rows-dlq`",
                                   "Validate for onprem (prod) and run one dead message locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/rows.py", content=FUTURE + """

def import_row(event, ctx):
    for r in event.records:
        row = r.json()
        if "sku" not in row:
            raise ValueError("row without sku")


def inspect_dead(event, ctx):
    for r in event.records:
        ctx.logger.warning("dead row", extra={
            "message_id": r.id,
            "body": r.text()[:500],
            "receives": r.attributes.get("pskit_receives"),
            "from_queue": r.attributes.get("pskit_source_queue"),
        })
    return {"inspected": len(event.records)}
"""),
          S("set_config", path="functions.inspect-dlq",
            value={"handler": "app.rows.inspect_dead", "events": [{"queue": "rows-dlq"}]}),
          S("invoke_local", function="inspect-dlq", type="queue",
            data=[{"id": "m-1", "body": {"name": "chair", "qty": 2},
                   "attributes": {"pskit_source_queue": "rows", "pskit_receives": 3}}]),
      ],
      final="""Added `inspect-dlq` on `- queue: rows-dlq`. It logs each dead message's id, body (first 500 chars), receive count and source queue, and never fails, so the messages don't bounce again.

- `pskit validate` (onprem, prod): valid.
- Local run with one dead row (`{"name": "chair", "qty": 2}`, 3 receives from `rows`): `{"inspected": 1}`, with a "dead row" warning in the log.

When the host moves a message to `dead_letter`, it adds the attributes `pskit_source_queue` and `pskit_receives`. The handler reads those from `record.attributes` [docs/handlers.md#record]. The sample also shows why these rows failed: there is no `sku`.

Once deployed, the 12 waiting messages are consumed. Look at them on the **Logs** page, or with `pskit logs --function inspect-dlq`. Deploy prod: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 95
    B(95, provider="azure", stage="staging", mode="ask", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#using-a-resource-from-an-event", "docs/resources.md#provider-support"],
      project=dict(files={
          "pskit.yml": """service: orders-svc
provider:
  name: azure
  region: westus2
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID, 00000000-0000-0000-0000-000000000000}
functions:
  api:
    handler: app.orders.api
    events:
    - http: POST /orders
""",
          "app/__init__.py": "",
          "app/orders.py": FUTURE + """

def api(event, ctx):
    return {"accepted": True}, 202
""",
          "requirements.txt": ""}),
      user="managed queue resource order-jobs, worker consumes it via resource:, api gets the binding too",
      steps=[
          S("get_project"),
          S("search_docs", query="resource queue event binding azure app settings",
            docs=[D("docs/resources.md", "provider-support", start="On Azure, app settings", end="On Azure, app settings")]),
          S("propose_plan", steps=["resources.order-jobs: {type: queue}",
                                   "Add `worker` to app/orders.py; function `worker` with queue {resource: order-jobs}",
                                   "api returns resource('order-jobs').native_name; validate for azure (staging), invoke api + worker"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.order-jobs", value={"type": "queue"}),
          S("write_file", path="app/orders.py", content=FUTURE + """from py_serverless_kit import resource


def api(event, ctx):
    return {"accepted": True, "queue": resource("order-jobs").native_name}, 202


def worker(event, ctx):
    return {"processed": len(event.records)}
"""),
          S("set_config", path="functions.worker",
            value={"handler": "app.orders.worker", "events": [{"queue": {"resource": "order-jobs"}}]}),
          S("invoke_local", function="api", method="POST", path="/orders", data={"sku": "A1"}),
          S("invoke_local", function="worker", type="queue", data=[{"sku": "A1"}]),
      ],
      final="""Added:

```yaml
resources:
  order-jobs: {type: queue}
functions:
  worker:
    handler: app.orders.worker
    events:
      - queue: {resource: order-jobs}
```

- validate (azure, staging): valid.
- invoke api: 202 with the queue's native name. Invoke worker: `{"processed": 1}`.

No `functions:` list is needed on the resource. Without one, every function you wrote gets the binding, and on Azure app settings are app-wide anyway [docs/resources.md#provider-support]. To enqueue from `api`, use `azure-storage-queue` with those values. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 96
    B(96, provider="cloudflare", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/handlers.md#event", "docs/providers.md#cloudflare-workers"],
      project=dict(files={
          "pskit.yml": """service: edge-stats
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID, 0123456789abcdef0123456789abcdef}
functions: {}
""",
          "requirements.txt": ""}),
      user="One Worker function `stats` please: `GET /stats` returns {\"source\": \"http\"}, and the same function also runs hourly (cron 0 * * * *) and returns {\"source\": \"schedule\"}. Branch on the event type rather than writing two functions.",
      steps=[
          S("get_project"),
          S("search_docs", query="event.type is_http handler branch",
            docs=[D("docs/handlers.md", "event", end="- `is_http`, `is_batch`")]),
          S("propose_plan", steps=["Write `app/stats.py`: return {source: event.type}",
                                   "Add function `stats` with events GET /stats and schedule `0 * * * *`",
                                   "Validate for cloudflare (staging); invoke as http and as schedule"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/stats.py", content=FUTURE + """

def stats(event, ctx):
    if event.is_http:
        return {"source": "http"}
    return {"source": event.type}
"""),
          S("set_config", path="functions.stats",
            value={"handler": "app.stats.stats", "events": [{"http": "GET /stats"}, {"schedule": "0 * * * *"}]}),
          S("invoke_local", function="stats", method="GET", path="/stats"),
          S("invoke_local", function="stats", type="schedule"),
      ],
      final="""Added `stats` with both triggers:

```yaml
functions:
  stats:
    handler: app.stats.stats
    events:
      - http: GET /stats
      - schedule: "0 * * * *"
```

- `pskit validate` (cloudflare, staging): valid, plus the usual note that Python Workers get the stdlib and Pyodide packages only.
- invoke as HTTP: 200, `{"source": "http"}`. Invoke as schedule: `{"source": "schedule"}`.

The handler uses `event.is_http` / `event.type`, so one function serves both [docs/handlers.md#event]. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 97
    B(97, provider="ibm", stage="prod", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/handlers.md#httprequest", "docs/handlers.md#errors"],
      project=dict(files={
          "pskit.yml": """service: schema-check
provider:
  name: ibm
  region: eu-gb
  runtime: python3.11
functions: {}
""",
          "requirements.txt": ""}),
      user="partners send us stuff like this and we keep finding broken ones in the db:\n{\"id\": 17, \"email\": \"x@example.com\", \"tags\": [\"a\"]}\n{\"id\": \"17\", \"tags\": \"a\"}\nneed POST /validate: 400 if not json, 422 listing the problems, 200 {valid:true} otherwise",
      steps=[
          S("get_project"),
          S("search_docs", query="json invalid BadRequest UnprocessableEntity",
            docs=[D("docs/handlers.md", "httprequest", start="| `json(default=...)`", end="| `json(default=...)`")]),
          S("propose_plan", steps=["Write `app/validate.py`: event.http.json() (400 on bad JSON), check id int, email has @, tags list of str; 422 with problems",
                                   "Add function `validate-payload` on POST /validate",
                                   "Validate for ibm (prod) and post your second (broken) sample locally"]),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/validate.py", content=FUTURE + """from py_serverless_kit import UnprocessableEntity


def check(event, ctx):
    doc = event.http.json()
    problems = []
    if not isinstance(doc, dict):
        raise UnprocessableEntity("payload must be an object")
    if not isinstance(doc.get("id"), int):
        problems.append("id must be an integer")
    if "@" not in str(doc.get("email", "")):
        problems.append("email is missing or invalid")
    tags = doc.get("tags")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        problems.append("tags must be a list of strings")
    if problems:
        raise UnprocessableEntity("invalid payload", details={"problems": problems})
    return {"valid": True}
"""),
          S("set_config", path="functions.validate-payload",
            value={"handler": "app.validate.check", "events": [{"http": "POST /validate"}]}),
          S("invoke_local", function="validate-payload", method="POST", path="/validate", data={"id": "17", "tags": "a"}),
      ],
      final="""Added `validate-payload` on `POST /validate`:

- Body that isn't JSON: `event.http.json()` raises `BadRequest`, which gives 400 [docs/handlers.md#httprequest].
- Wrong fields: 422 with `details.problems`.
- Good payload: 200 `{"valid": true}`.

Checks:
- validate (ibm, prod): valid.
- Your broken sample `{"id": "17", "tags": "a"}` run locally: 422 listing all three problems (id, email, tags).

Retest the good one: `pskit invoke -f validate-payload -d '{"id": 17, "email": "x@example.com", "tags": ["a"]}'`. Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),

    # ------------------------------------------------------------------ 98
    B(98, provider="alibaba", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#events-triggers", "docs/events.md#topic"],
      project=dict(files={
          "pskit.yml": """service: print-jobs
provider:
  name: alibaba
  region: cn-shanghai
functions: {}
""",
          "requirements.txt": ""}),
      user="i need a queue worker for print jobs on alibaba cloud",
      steps=[
          S("get_project"),
          S("search_docs", query="alibaba queue support triggers",
            docs=[D("docs/events.md", "events-triggers", start="| Trigger |", end="| `topic` |")]),
          S("ask_user", question="pskit doesn't support `queue` triggers on Alibaba Function Compute. It does support MNS **topics**: messages published to a topic run your function. Should I build the print worker on an MNS topic instead?",
            options=["Yes, use an MNS topic", "No, I'll pick another provider"],
            answer="Yes, use an MNS topic"),
          S("propose_plan", steps=["Write `app/printer.py` that logs each print job (document, copies)",
                                   "Add function `print-worker` with `- topic: print-jobs`",
                                   "Validate for alibaba and run one job locally"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="app/__init__.py", content=""),
          S("write_file", path="app/printer.py", content=FUTURE + """

def print_worker(event, ctx):
    jobs = []
    for record in event.records:
        job = record.json(default={}) or {}
        ctx.logger.info("print job", extra={"document": job.get("document"), "copies": job.get("copies", 1)})
        jobs.append(job.get("document"))
    return {"printed": jobs}
"""),
          S("set_config", path="functions.print-worker",
            value={"handler": "app.printer.print_worker", "events": [{"topic": "print-jobs"}]}),
          S("invoke_local", function="print-worker", type="topic", data=[{"document": "invoice-88.pdf", "copies": 2}]),
      ],
      final="""Done, using an MNS topic, because pskit has no queue trigger on Alibaba [docs/events.md#events-triggers].

Your new function `print-worker` runs for every message published to the topic `print-jobs`:

- `pskit validate` for alibaba: valid.
- A test job `{"document": "invoice-88.pdf", "copies": 2}` run locally: returned `{"printed": ["invoice-88.pdf"]}`.

One difference from a queue: a topic delivers each message to every subscriber, and nothing waits in line if the function is down. For one worker like this, that's fine.

Try it on **Test** > **▶ Run locally**, or with `pskit invoke -f print-worker -t topic -d '[{"document": "a.pdf"}]'`. Deploy on the **Deploy** page or with `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 99
    B(99, provider="aws", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#data-flow", "docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": """service: enrich
provider:
  name: aws
  region: eu-west-3
functions:
  lookup-customer:
    handler: app.enrich.customer
  lookup-credit:
    handler: app.enrich.credit
""",
          "app/__init__.py": "",
          "app/enrich.py": FUTURE + """

def customer(event, ctx):
    return {"tier": "gold"}


def credit(event, ctx):
    return {"limit": 5000}
""",
          "requirements.txt": ""}),
      user="Workflow `enrich-order`: first a pass state that adds {\"source\": \"web\"} under $.meta, then a parallel state that runs lookup-customer and lookup-credit and stores the list of results under $.enrichment, keeping the original order data.",
      steps=[
          S("get_project"),
          S("search_docs", query="pass state result result_path parallel",
            docs=[D("docs/workflows.md", "data-flow")]),
          S("propose_plan", steps=["Add workflow `enrich-order`: Tag (pass, result {source: web}, result_path $.meta) -> Enrich (parallel, result_path $.enrichment, end)",
                                   "Branches: Customer (task lookup-customer), Credit (task lookup-credit)",
                                   "Validate for aws (staging) and run lookup-credit locally"],
            result={"decision": "approved", "note": "add a workflow timeout of 300 seconds"}),
          S("set_config", path="workflows.enrich-order",
            value={"timeout": 300, "start_at": "Tag",
                   "states": {"Tag": {"type": "pass", "result": {"source": "web"}, "result_path": "$.meta",
                                      "next": "Enrich"},
                              "Enrich": {"type": "parallel", "result_path": "$.enrichment", "end": True,
                                         "branches": [
                                             {"start_at": "Customer",
                                              "states": {"Customer": {"type": "task", "function": "lookup-customer", "end": True}}},
                                             {"start_at": "Credit",
                                              "states": {"Credit": {"type": "task", "function": "lookup-credit", "end": True}}}]}}},
            say="Including the 300 s timeout from your note."),
          S("invoke_local", function="lookup-credit", type="workflow", data={"order_id": 9, "meta": {"source": "web"}}),
      ],
      final="""Added `enrich-order` with the 300 s timeout from your note:

```yaml
workflows:
  enrich-order:
    timeout: 300
    start_at: Tag
    states:
      Tag:
        type: pass
        result: {source: web}
        result_path: $.meta
        next: Enrich
      Enrich:
        type: parallel
        result_path: $.enrichment
        end: true
        branches:
          - {start_at: Customer, states: {Customer: {type: task, function: lookup-customer, end: true}}}
          - {start_at: Credit,   states: {Credit:   {type: task, function: lookup-credit, end: true}}}
```

- Because of `result_path`, both states keep the order data and add their result under `$.meta` / `$.enrichment` [docs/workflows.md#data-flow]. On AWS, `timeout` becomes `TimeoutSeconds`.
- `pskit validate` (aws, staging): valid.
- `lookup-credit` run locally: `{"limit": 5000}`.

Following those `result_path` rules, `{"order_id": 9}` should end as the order plus `meta` and `enrichment: [{"tier": "gold"}, {"limit": 5000}]`. I didn't run the whole flow, so confirm it with `pskit workflow run enrich-order -i '{"order_id": 9}' --history`. Deploy: **Deploy** or `pskit deploy -s staging`."""),

    # ------------------------------------------------------------------ 100
    B(100, provider="onprem", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises", "docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: payroll
provider:
  name: onprem
  region: local
  options:
    host: 0.0.0.0
    port: 8080
functions:
  close-day:
    handler: app.payroll.close_day
""",
          "app/__init__.py": "",
          "app/payroll.py": FUTURE + """

def close_day(event, ctx):
    branch = (event.data or {}).get("branch", "all")
    ctx.logger.info("close day", extra={"branch": branch})
    return {"closed": branch}
""",
          "requirements.txt": ""}),
      user="close-day: 23:30 Asia/Kolkata daily, input branch=mumbai",
      steps=[
          S("get_project"),
          S("propose_plan", steps=["schedule {cron: \"30 23 * * *\", timezone: Asia/Kolkata, input: {branch: mumbai}} on close-day",
                                   "Validate for onprem (prod), invoke schedule"]),
          S("set_config", path="functions.close-day.events",
            value=[{"schedule": {"cron": "30 23 * * *", "timezone": "Asia/Kolkata", "input": {"branch": "mumbai"}}}]),
          S("invoke_local", function="close-day", type="schedule"),
      ],
      final="""Added to `close-day`:

```yaml
events:
  - schedule: {cron: "30 23 * * *", timezone: Asia/Kolkata, input: {branch: mumbai}}
```

- validate (onprem, prod): valid, with a warning: Asia/Kolkata needs the IANA database, which `pskit deploy` vendors (`tzdata`). Until then, the schedule would be evaluated in UTC. After deploy, the host runs it at 23:30 IST, Windows hosts included [docs/providers.md#onprem-on-premises].
- invoke: `{"closed": "mumbai"}`.

Deploy: **Deploy** (typed confirmation) or `pskit deploy -s prod`."""),
]
