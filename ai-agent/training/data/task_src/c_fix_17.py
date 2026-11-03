"""Category C (fix a validation error), batch 17: value types and shapes (cors, methods, events, workflows, tags,
resources) in on-premises projects. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import D, S  # noqa: E402
from _onprem_c import C, app, mods, onprem, saved  # noqa: E402

E = "docs/events.md"
W = "docs/workflows.md"
CF = "docs/configuration.md"
CORS = D(E, "http", start="**CORS**", end="max_age")
HTTP = D(E, "http", start="```yaml", end="```")
QUEUE = D(E, "queue", words=170)
STORAGE = D(E, "storage", words=150)
WF_KEYS = D(W, "workflow-keys", words=150)
STATES = D(W, "state-types", start="| `type` |", end="`task`, `wait`, `pass`, `parallel` and `map` without `next`")
CHOICES = D(W, "choice-rules", start="```yaml", end="```")
PROVIDER_T = D(CF, "provider", start="| Key |", end="| `log_retention_days` |")
FUNCS = D(CF, "functions", start="```yaml", end="```")
TOP = D(CF, "top-level", start="| Key |", end="| `custom` |")
RES_FIELDS = D("docs/resources.md", "fields", start="| Key |", end="| `external` |")
HOOKS = D(CF, "hooks", start="```yaml", end="Allowed hooks")
H = dict(host="0.0.0.0")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 321  cors max_age 1h
    C(321, provider="onprem", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=dict(files={"pskit.yml": onprem("booking-api", """functions:
  slots:
    handler: app.booking.slots
    events:
      - http:
          path: /slots
          method: GET
          cors: {origins: ["https://app.example.com"], max_age: 1h}
""", **H), **app("booking", "slots")}),
      user="The browser should cache the CORS preflight for an hour. Staging shows two errors, cors.bool and cors.CorsConfig.max_age. I only touched max_age.",
      steps=[
          S("get_validation"),
          S("search_docs", query="cors max_age seconds", docs=[CORS]),
          S("propose_plan", steps=["Set `functions.slots.events.0.http.cors.max_age` to 3600 (seconds)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.slots.events.0.http.cors.max_age", value=3600),
      ],
      final="""`max_age` is a number of seconds; `1h` isn't a number. The `cors.bool` line is only pydantic also trying the other allowed form (`cors: true`) [docs/events.md#http].

Set `max_age: 3600`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 322  method as a list
    C(322, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=dict(files={"pskit.yml": onprem("notes", """functions:
  notes:
    handler: app.notes.handle
    events:
      - http: {path: /notes, method: [GET, POST]}
"""), **app("notes", "handle")}),
      user="method Input should be a valid string. i want GET and POST same function",
      steps=[
          S("get_validation"),
          S("search_docs", query="http method path shorthand", docs=[HTTP]),
          S("propose_plan", steps=["Replace the event with two: `- http: GET /notes` and `- http: POST /notes`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.notes.events", value=[{"http": "GET /notes"}, {"http": "POST /notes"}]),
      ],
      final="""`method` is one method per event; for two, give the function two events [docs/events.md#http].

Now `- http: GET /notes` and `- http: POST /notes`, both to `notes`. Validate for onprem: valid. In the handler, `event.http.method` tells them apart."""),

    # ------------------------------------------------------------------ 323  storage events updated
    C(323, provider="onprem", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage"],
      project=dict(files={"pskit.yml": onprem("price-files", """functions:
  load:
    handler: app.prices.load
    events:
      - storage: {bucket: prices, events: [created, updated]}
""", **H), **app("prices", "load")}),
      user="events.1: Input should be 'created' or 'deleted'. keep created",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.load.events.0.storage.events` to `[created]`", "Validate for onprem, stage prod"]),
          S("set_config", path="functions.load.events.0.storage.events", value=["created"]),
      ],
      final="""Storage events are only `created` and `deleted` [docs/events.md#storage]. Now `events: [created]`. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 324  dead_letter as a list
    C(324, provider="onprem", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue"],
      project=dict(files={"pskit.yml": onprem("webhooks", """functions:
  deliver:
    handler: app.hooks.deliver
    events:
      - queue: {name: outgoing, max_receive: 5, dead_letter: [outgoing-dlq]}
""", **H), **app("hooks", "deliver")}),
      user="SQS redrive policy took a list of targets in our template, so I wrote dead_letter: [outgoing-dlq]. Staging: dead_letter Input should be a valid string.",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue dead_letter max_receive", docs=[QUEUE]),
          S("propose_plan", steps=["Set `functions.deliver.events.0.queue.dead_letter` to `outgoing-dlq`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.deliver.events.0.queue.dead_letter", value="outgoing-dlq"),
      ],
      final="""A queue has one dead-letter queue, so `dead_letter` is a single name [docs/events.md#queue].

Now `dead_letter: outgoing-dlq`; after 5 failed receives a message moves there. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 325  workflow name with a space
    C(325, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/configuration.md#top-level"],
      project=dict(files={"pskit.yml": onprem("shop", """functions:
  pay:
    handler: app.shop.pay
workflows:
  Order Flow:
    start_at: Pay
    states:
      Pay: {type: task, function: pay}
"""), **app("shop", "pay")}),
      user="I typed 'Order Flow' as the workflow name in + Create workflow and now there's an error that the name must start with a letter... it does start with O!",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename workflow `Order Flow` to `order-flow` (no space)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows", value={"order-flow": {"start_at": "Pay", "states": {"Pay": {"type": "task", "function": "pay"}}}}),
      ],
      final="""It does, but the rest may only be letters, digits, `-` or `_`, and the space isn't allowed. Workflow names follow the function-name rules because they become URLs like `POST /workflows/<name>` [docs/configuration.md#top-level].

Renamed it `order-flow` (same states). Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 326  workflow without start_at
    C(326, provider="onprem", stage="staging", mode="auto", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={"pskit.yml": onprem("onboarding", """functions:
  account:
    handler: app.onboard.account
  laptop:
    handler: app.onboard.laptop
workflows:
  onboard:
    states:
      Account: {type: task, function: account, next: Laptop}
      Laptop: {type: task, function: laptop}
""", **H), **app("onboard", "account", "laptop")}),
      user="""Error: pskit.yml is invalid:
  - workflows.onboard.start_at: Field required""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.onboard.start_at` to `Account` (the first state)", "Validate for onprem, stage staging"]),
          S("set_config", path="workflows.onboard.start_at", value="Account"),
      ],
      final="""Every workflow must name its first state in `start_at` [docs/workflows.md#workflow-keys]. Set it to `Account`, which leads to `Laptop`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 327  tags as a list
    C(327, provider="onprem", stage="prod", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=dict(files={"pskit.yml": onprem("pos", """  tags: [team-retail, cost-center-42]
functions:
  sale:
    handler: app.pos.sale
    events:
      - http: POST /sale
""", **H), **app("pos", "sale")}),
      user="provider.tags Input should be a valid dictionary. tags is team retail and cost center 42",
      steps=[
          S("get_validation"),
          S("search_docs", query="provider tags map", docs=[PROVIDER_T]),
          S("propose_plan", steps=["Set `provider.tags` to `{team: retail, cost-center: \"42\"}`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.tags", value={"team": "retail", "cost-center": "42"}),
      ],
      final="""Tags are key/value pairs, not a list [docs/configuration.md#provider]. Now `tags: {team: retail, cost-center: "42"}`. `pskit validate -p onprem -s prod`: valid. On premises tags are only recorded, there's no cloud billing to use them."""),

    # ------------------------------------------------------------------ 328  events as a mapping
    C(328, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("greeter", """functions:
  greet:
    handler: app.greet.greet
    events:
      http: GET /greet
"""), **app("greet", "greet")}),
      user="it says functions.greet.events: Input should be a valid list. what is a valid list in yaml?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Make `events` a list: `- http: GET /greet`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.greet.events", value=[{"http": "GET /greet"}]),
      ],
      final="""In YAML a list item starts with `- `. `events` is a list of triggers, so it needs the dash even with one trigger [docs/configuration.md#functions]:

```yaml
functions:
  greet:
    handler: app.greet.greet
    events:
      - http: GET /greet
```
Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 329  handler as a file path
    C(329, provider="onprem", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("thumbs", """functions:
  thumb:
    handler: src/thumbs.py
    events:
      - http: POST /thumb
""", **H), "src/__init__.py": "", "src/thumbs.py": "from __future__ import annotations\n\n\ndef lambda_handler(event, ctx):\n    return {\"ok\": True}\n"}),
      user="handler 'src/thumbs.py' must be 'package.module.function'. In Lambda the file had lambda_handler in it.",
      steps=[
          S("get_validation"),
          S("read_file", path="src/thumbs.py"),
          S("propose_plan", steps=["Set `functions.thumb.handler` to `src.thumbs.lambda_handler`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.thumb.handler", value="src.thumbs.lambda_handler"),
      ],
      final="""The handler is a dotted import path plus the function name, like Lambda's `thumbs.lambda_handler` [docs/configuration.md#functions].

`src/thumbs.py` defines `lambda_handler`, so it's `handler: src.thumbs.lambda_handler`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 330  timeout_seconds 5m
    C(330, provider="onprem", stage="prod", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={"pskit.yml": onprem("render", """functions:
  frame:
    handler: app.render.frame
workflows:
  movie:
    start_at: Frame
    states:
      Frame: {type: task, function: frame, timeout_seconds: 5m}
""", **H), **app("render", "frame")}),
      user="timeout_seconds 5m not an integer. 5 minutes",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.movie.states.Frame.timeout_seconds` to 300", "Validate for onprem, stage prod"]),
          S("set_config", path="workflows.movie.states.Frame.timeout_seconds", value=300),
      ],
      final="""`timeout_seconds` is a plain number of seconds [docs/workflows.md#state-types]. Now 300. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 331  external: sometimes
    C(331, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields"],
      project=dict(files={"pskit.yml": onprem("imports", """resources:
  incoming:
    type: queue
    external: sometimes
functions:
  load:
    handler: app.imports.load
    events:
      - queue: {resource: incoming}
"""), **app("imports", "load")}),
      user="external Input should be a valid boolean. i dont know if pskit should make it",
      steps=[
          S("get_validation"),
          S("search_docs", query="resource external true false", docs=[RES_FIELDS]),
          S("ask_user", question="Does the `incoming` queue already exist somewhere else (another project or service), or is it only for this project?",
            options=["Only this project", "It already exists"], answer="Only this project"),
          S("propose_plan", steps=["Delete `resources.incoming.external` (default false: pskit manages it)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.incoming.external", value=None),
      ],
      final="""`external` is true or false: `true` means it already exists and pskit never creates or deletes it [docs/resources.md#fields]. The queue is only for this project, so I removed the key; the default `false` lets the host create it. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 332  batch_window 5s
    C(332, provider="onprem", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#queue"],
      project=dict(files={"pskit.yml": onprem("metrics", """functions:
  rollup:
    handler: app.metrics.rollup
    events:
      - queue: {name: points, batch_size: 500, batch_window: 5s}
""", **H), **app("metrics", "rollup")}),
      user="""  - functions.rollup.events.0.batch_window: Input should be a valid integer, unable to parse string as an integer""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.rollup.events.0.queue.batch_window` to 5", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.rollup.events.0.queue.batch_window", value=5),
      ],
      final="""`batch_window` is seconds as a number (0-300) [docs/events.md#queue]. Now `batch_window: 5`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 333  options.cluster without a saved cluster
    C(333, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=["docs/cluster.md#set-up", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("intranet", """functions:
  home:
    handler: app.intranet.home
    events:
      - http: GET /
""", extra="    deploy: {server: app-1, python: bundle}\n    cluster: prod\n", **H), **app("intranet", "home"), **saved("app-1")}),
      user="I copied cluster: prod from another team's file. Prod validation: no cluster 'prod' (clusters: none yet). We don't have a cluster, this should simply run on app-1.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `provider.options.cluster` (deploy stays on the saved server app-1)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster", value=None),
      ],
      final="""`options.cluster` names a scaling cluster saved in this project, and there is none; without it the project deploys to `deploy.server` [docs/providers.md#onprem-on-premises].

Removed `cluster: prod`, so it runs on app-1. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 334  choice state without choices
    C(334, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={"pskit.yml": onprem("loans", """functions:
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
      Decide: {type: choice, default: Review}
      Approve: {type: task, function: approve}
      Review: {type: task, function: review}
"""), **app("loans", "score", "approve", "review")}),
      user="choice state needs choices. I want: if the score is 700 or more go to Approve, otherwise Review.",
      steps=[
          S("get_validation"),
          S("search_docs", query="choice rules gte variable next", docs=[CHOICES]),
          S("propose_plan", steps=["Set `workflows.loan.states.Decide.choices` to `[{variable: \"$.score\", gte: 700, next: Approve}]` (default stays Review)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.loan.states.Decide.choices", value=[{"variable": "$.score", "gte": 700, "next": "Approve"}]),
      ],
      final="""A `choice` state needs at least one rule in `choices`; `default` is only where it goes when none match [docs/workflows.md#choice-rules].

Added `{variable: "$.score", gte: 700, next: Approve}`; anything lower goes to `Review`. Validate for onprem: valid. `score` must return a mapping with a `score` key."""),

    # ------------------------------------------------------------------ 335  choice default to a missing state
    C(335, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={"pskit.yml": onprem("tickets", """functions:
  classify:
    handler: app.tickets.classify
  urgent:
    handler: app.tickets.urgent
  normal:
    handler: app.tickets.normal
workflows:
  triage:
    start_at: Classify
    states:
      Classify: {type: task, function: classify, next: Route}
      Route:
        type: choice
        choices: [{variable: "$.priority", equals: high, next: Urgent}]
        default: Standard
      Urgent: {type: task, function: urgent}
      Normal: {type: task, function: normal}
""", **H), **app("tickets", "classify", "urgent", "normal")}),
      user="""Error: pskit.yml is invalid:
  - workflows.triage: Value error, state 'Route' points to unknown state 'Standard'""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.triage.states.Route.default` to `Normal` (the existing state)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.triage.states.Route.default", value="Normal"),
      ],
      final="""`default` named `Standard`, but the state is called `Normal` [docs/workflows.md#choice-rules]. Set `default: Normal`. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 336  DB password in provider.environment (security)
    C(336, provider="onprem", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises", "docs/configuration.md#variables"],
      project=dict(files={"pskit.yml": onprem("hr", """  environment:
    DB_HOST: 192.0.2.20
    DB_PASSWORD: Winter2026!
functions:
  staff:
    handler: app.hr.staff
    events:
      - http: GET /staff
""", extra="    env_file: .env.onprem\n", **H), **app("hr", "staff"), ".env.onprem": "LOG_FORMAT=json\n"}),
      user="Prod validates. Before I push, check provider settings for anything sensitive. We already ship .env.onprem with the host; ops can add lines to it.",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Delete `provider.environment.DB_PASSWORD` (ops add it to .env.onprem)", "Keep `DB_HOST`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.environment.DB_PASSWORD", value=None),
      ],
      final="""`DB_PASSWORD` was written in `provider.environment` in plain text; secrets don't belong in YAML [docs/configuration.md#variables].

I removed it (`DB_HOST` stays). Ops add the `DB_PASSWORD` line to `.env.onprem`, which the host loads at start; it is never written to Terraform state [docs/providers.md#onprem-on-premises]. `pskit validate -p onprem -s prod`: valid. The handler still reads `ctx.env["DB_PASSWORD"]`. Change that password, it was in the file."""),

    # ------------------------------------------------------------------ 337  hooks before-deploy with a dash
    C(337, provider="onprem", stage="dev", mode="auto", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#hooks"],
      project=dict(files={"pskit.yml": onprem("site", """functions:
  page:
    handler: app.site.page
    events:
      - http: GET /
hooks:
  before-deploy: [python scripts/check.py]
"""), **app("site", "page")}),
      user="unknown hooks ['before-deploy'] whyy",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `hooks.before-deploy` to `hooks.before_deploy`", "Validate for onprem"]),
          S("set_config", path="hooks", value={"before_deploy": ["python scripts/check.py"]}),
      ],
      final="""Hook names use underscores: `before_deploy` [docs/configuration.md#hooks]. Renamed it. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 338  engine: stepfunctions on premises
    C(338, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#engines", "docs/workflows.md#workflow-keys"],
      project=dict(files={"pskit.yml": onprem("claims-flow", """functions:
  intake:
    handler: app.claims.intake
workflows:
  claim:
    engine: stepfunctions
    start_at: Intake
    states:
      Intake: {type: task, function: intake}
""", **H), **app("claims", "intake")}),
      user="Our Step Functions machine moved on-prem. I kept engine: stepfunctions and prod says Input should be 'auto', 'native' or 'embedded'. Which one runs it on our own server?",
      steps=[
          S("get_validation"),
          S("search_docs", query="workflow engine embedded on premises", docs=[D(W, "engines", start="| Provider |", end="| all others")]),
          S("propose_plan", steps=["Set `workflows.claim.engine` to `embedded`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.claim.engine", value="embedded"),
      ],
      final="""`engine` is `auto`, `native` or `embedded`; there is no Step Functions on premises, so the workflow runs on the embedded engine inside the host [docs/workflows.md#engines].

Set `engine: embedded`. `pskit validate -p onprem -s prod`: valid (`workflow claim: embedded engine`). `auto` would pick the same here."""),

    # ------------------------------------------------------------------ 339  top-level function: instead of functions:
    C(339, provider="onprem", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#top-level"],
      project=dict(files={"pskit.yml": onprem("ping", """function:
  ping:
    handler: app.ping.ping
    events:
      - http: GET /ping
"""), **app("ping", "ping")}),
      user="""Error: pskit.yml is invalid:
  - function: Extra inputs are not permitted""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the top-level key `function` to `functions`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="function", value=None),
          S("set_config", path="functions.ping", value={"handler": "app.ping.ping", "events": [{"http": "GET /ping"}]}),
      ],
      final="""The key is plural, `functions` [docs/configuration.md#top-level]. Renamed it; `ping` is unchanged. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 340  path template with a space
    C(340, provider="onprem", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={"pskit.yml": onprem("users", """functions:
  user:
    handler: app.users.get_user
    events:
      - http: "GET /users/{user id}"
""", **H), **app("users", "get_user")}),
      user="invalid path template '/users/{user id}' fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the event to `- http: GET /users/{user_id}`", "Validate for onprem, stage staging"]),
          S("set_config", path="functions.user.events.0", value={"http": "GET /users/{user_id}"}),
      ],
      final="""Path parameter names are identifiers: `{user_id}` works, `{user id}` doesn't [docs/events.md#http]. Now `GET /users/{user_id}`; read it as `event.http.path_params["user_id"]`. `pskit validate -p onprem -s staging`: valid."""),
]
