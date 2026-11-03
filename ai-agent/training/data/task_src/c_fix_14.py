"""Category C (fix a validation error), batch 14: schedules, event keys, workflow states and function names in
on-premises projects. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import D, S  # noqa: E402
from _onprem_c import C, app, mods, onprem  # noqa: E402

E = "docs/events.md"
W = "docs/workflows.md"
SCHED = D(E, "schedule", start="```yaml", end="```")
SCHED_TABLE = D(E, "schedule", start="| onprem |", end="A rate that can't be expressed")
HTTP = D(E, "http", start="```yaml", end="```")
QUEUE = D(E, "queue", words=150)
STORAGE = D(E, "storage", words=150)
TOPIC = D(E, "topic", words=150)
STATES = D(W, "state-types", start="| `type` |", end="`task`, `wait`, `pass`, `parallel` and `map` without `next`")
RETRY = D(W, "retry-and-catch", start="```yaml", end="```")
ENGINES = D(W, "engines", start="| Provider |", end="| all others")
TOP = D("docs/configuration.md", "top-level", start="| Key |", end="| `functions` |")
H = dict(host="0.0.0.0")

CONVERSATIONS = [
    # ------------------------------------------------------------------ 261  rate and cron together
    C(261, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=dict(files={"pskit.yml": onprem("backup", """functions:
  snapshot:
    handler: app.backup.snapshot
    events:
      - schedule: {rate: 1 day, cron: "0 2 * * *"}
"""), **app("backup", "snapshot")}),
      user="I want a backup once a day at 2 at night. I wrote rate 1 day and cron 0 2 * * * to be sure, now it says schedule needs exactly one of rate or cron.",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule rate or cron exactly one", docs=[SCHED]),
          S("propose_plan", steps=["Delete `functions.snapshot.events.0.schedule.rate` (the cron already says daily at 02:00)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.snapshot.events.0.schedule.rate", value=None),
      ],
      final="""A schedule is either a `rate` or a `cron`, never both [docs/events.md#schedule]. `rate: 1 day` would run every 24 hours from the deploy time, while the cron fixes the hour, so I kept `cron: "0 2 * * *"`. Validate for onprem: valid (UTC by default)."""),

    # ------------------------------------------------------------------ 262  schedule with only input
    C(262, provider="onprem", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={"pskit.yml": onprem("price-watch", """functions:
  check:
    handler: app.prices.check
    events:
      - schedule: {input: {shop: main}}
""", **H), **app("prices", "check")}),
      user="schedule needs exactly one of rate or cron... i only set input. want every 10 min",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.check.events.0.schedule.rate` to `10 minutes` (input stays)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.check.events.0.schedule.rate", value="10 minutes"),
      ],
      final="""`input` is only the data for `event.data`; the schedule also needs *when* [docs/events.md#schedule]. Added `rate: 10 minutes`, `input: {shop: main}` stays. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 263  Quartz 6-field cron
    C(263, provider="onprem", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=dict(files={"pskit.yml": onprem("ledger-close", """functions:
  close:
    handler: app.ledger.close
    events:
      - schedule: "0 0/15 * * * ?"
""", **H), **app("ledger", "close")}),
      user="This came from a Spring @Scheduled job: \"0 0/15 * * * ?\" (every 15 minutes). Prod validation says cron must be a standard 5-field expression. Convert it please.",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule 5-field cron onprem", docs=[SCHED_TABLE]),
          S("propose_plan", steps=["Set `functions.close.events.0` to `{schedule: \"*/15 * * * *\"}`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.close.events.0", value={"schedule": "*/15 * * * *"}),
      ],
      final="""Spring/Quartz crons have a seconds field and `?`; pskit uses standard 5-field unix cron [docs/events.md#schedule].

`0 0/15 * * * ?` is `*/15 * * * *` (minute 0, 15, 30, 45 of every hour). `pskit validate -p onprem -s prod`: valid. `rate: 15 minutes` would work too, but it counts from the host's start instead of the clock."""),

    # ------------------------------------------------------------------ 264  @daily
    C(264, provider="onprem", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=dict(files={"pskit.yml": onprem("logrotate", """functions:
  rotate:
    handler: app.logs.rotate
    events:
      - schedule: "@daily"
"""), **app("logs", "rotate")}),
      user="@daily rejected (cron must be 5-field). midnight daily",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.rotate.events.0` to `{schedule: \"0 0 * * *\"}`", "Validate for onprem"]),
          S("set_config", path="functions.rotate.events.0", value={"schedule": "0 0 * * *"}),
      ],
      final="""Cron macros like `@daily` aren't supported; it's `0 0 * * *` [docs/events.md#schedule]. Changed. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 265  rate 1 week
    C(265, provider="onprem", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=dict(files={"pskit.yml": onprem("newsletter", """functions:
  digest:
    handler: app.news.digest
    events:
      - schedule: 1 week
""", **H), **app("news", "digest")}),
      user="""Error: pskit.yml is invalid:
  - functions.digest.events.0: Value error, cron must be a standard 5-field expression: 'min hour dom month dow'

I didn't write a cron, I wrote 1 week. Monday 8:00 would be best actually.""",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule rate units minutes hours days", docs=[SCHED]),
          S("propose_plan", steps=["Set `functions.digest.events.0` to `{schedule: \"0 8 * * 1\"}` (Mondays 08:00)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.digest.events.0", value={"schedule": "0 8 * * 1"}),
      ],
      final="""Rates only know minutes, hours and days, so `1 week` wasn't read as a rate and pskit tried it as a cron [docs/events.md#schedule].

Since you want Monday 08:00, it's now the cron `0 8 * * 1`. `pskit validate -p onprem -s staging`: valid (UTC unless you add `timezone`)."""),

    # ------------------------------------------------------------------ 266  task state without function
    C(266, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={"pskit.yml": onprem("signup-flow", """functions:
  create-user:
    handler: app.users.create
  welcome:
    handler: app.mail.welcome
workflows:
  signup:
    start_at: Create
    states:
      Create: {type: task, function: create-user, next: Welcome}
      Welcome: {type: task}
"""), **mods(users="create", mail="welcome")}),
      user="In the workflow editor I added a step Welcome but validation says task state needs function. It should send the welcome mail.",
      steps=[
          S("get_validation"),
          S("search_docs", query="task state function", docs=[STATES]),
          S("propose_plan", steps=["Set `workflows.signup.states.Welcome.function` to `welcome`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.signup.states.Welcome.function", value="welcome"),
      ],
      final="""A `task` state runs a function, so it must name one [docs/workflows.md#state-types].

`Welcome` now calls your `welcome` function. Validate for onprem: valid. In studio that is the state inspector's **Function** field on **Workflows**."""),

    # ------------------------------------------------------------------ 267  wait state without seconds
    C(267, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("trial", """functions:
  start-trial:
    handler: app.trial.start
  remind:
    handler: app.trial.remind
workflows:
  trial:
    start_at: Start
    states:
      Start: {type: task, function: start-trial, next: Pause}
      Pause: {type: wait, next: Remind}
      Remind: {type: task, function: remind}
""", **H), **app("trial", "start", "remind")}),
      user="The trial workflow should wait one hour before the reminder. Staging validation: wait state needs seconds or seconds_path. I thought the default would be fine.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.trial.states.Pause.seconds` to 3600", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.trial.states.Pause.seconds", value=3600),
      ],
      final="""A `wait` state has no default length: it needs `seconds` or `seconds_path` [docs/workflows.md#state-types].

Set `seconds: 3600`. `pskit validate -p onprem -s staging`: valid. On premises the embedded engine runs inside the host, so an hour's wait isn't cut off by a function timeout [docs/providers.md#onprem-on-premises]."""),

    # ------------------------------------------------------------------ 268  parallel without branches
    C(268, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={"pskit.yml": onprem("order-flow", """functions:
  charge:
    handler: app.flow.charge
  notify-sms:
    handler: app.flow.sms
  notify-mail:
    handler: app.flow.mail
workflows:
  order:
    start_at: Charge
    states:
      Charge: {type: task, function: charge, next: Notify}
      Notify: {type: parallel}
""", **H), **app("flow", "charge", "sms", "mail")}),
      user="parallel state needs branches. i want sms and mail same time after charge",
      steps=[
          S("get_validation"),
          S("search_docs", query="parallel state branches", docs=[STATES]),
          S("propose_plan", steps=["Give `workflows.order.states.Notify` two branches: one runs `notify-sms`, one runs `notify-mail`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.order.states.Notify.branches", value=[
              {"start_at": "Sms", "states": {"Sms": {"type": "task", "function": "notify-sms"}}},
              {"start_at": "Mail", "states": {"Mail": {"type": "task", "function": "notify-mail"}}}]),
      ],
      final="""A `parallel` state runs its `branches` at the same time, so it needs at least one, each with `start_at` and `states` [docs/workflows.md#state-types].

`Notify` now has two branches: `Sms` (notify-sms) and `Mail` (notify-mail). The result is a list with one item per branch. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 269  map without iterator
    C(269, provider="onprem", stage="dev", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={"pskit.yml": onprem("batch-resize", """functions:
  resize:
    handler: app.images.resize
workflows:
  resize-all:
    start_at: Each
    states:
      Each: {type: map, items_path: $.images, max_concurrency: 4}
"""), **app("images", "resize")}),
      user="map state needs iterator. run resize per image",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.resize-all.states.Each.iterator` to `{start_at: Resize, states: {Resize: {type: task, function: resize}}}`", "Validate for onprem"]),
          S("set_config", path="workflows.resize-all.states.Each.iterator", value={"start_at": "Resize", "states": {"Resize": {"type": "task", "function": "resize"}}}),
      ],
      final="""`map` runs its `iterator` (a small `{start_at, states}` machine) for each item [docs/workflows.md#state-types]. Added an iterator with one task, `resize`. Validate for onprem: valid; 4 images at a time."""),

    # ------------------------------------------------------------------ 270  Task with a capital T
    C(270, provider="onprem", stage="staging", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#state-types"],
      project=dict(files={"pskit.yml": onprem("refunds", """functions:
  refund:
    handler: app.pay.refund
  notify:
    handler: app.pay.notify
workflows:
  refund:
    start_at: Refund
    states:
      Refund: {type: Task, function: refund, next: Notify}
      Notify: {type: Task, function: notify}
""", **H), **app("pay", "refund", "notify")}),
      user="Copied the state names from our Step Functions definition (Type: Task). Staging validation: Input should be 'task', 'choice', 'wait'... for both states.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `type` of `Refund` and `Notify` to `task` (lowercase)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.refund.states.Refund.type", value="task"),
          S("set_config", path="workflows.refund.states.Notify.type", value="task"),
      ],
      final="""pskit's workflow syntax is ASL-like but lowercase: `task`, `choice`, `wait`, ... [docs/workflows.md#state-types].

Both states are `type: task` now. `pskit validate -p onprem -s staging`: valid. On premises the workflow runs on the embedded engine."""),

    # ------------------------------------------------------------------ 271  catch to a state that doesn't exist
    C(271, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#retry-and-catch", "docs/workflows.md#state-types"],
      project=dict(files={"pskit.yml": onprem("payout", """functions:
  transfer:
    handler: app.bank.transfer
  confirm:
    handler: app.bank.confirm
workflows:
  payout:
    start_at: Transfer
    states:
      Transfer:
        type: task
        function: transfer
        catch: [{errors: ["*"], next: Failed}]
        next: Confirm
      Confirm: {type: task, function: confirm}
""", **H), **app("bank", "transfer", "confirm")}),
      user="Prod validate: state 'Transfer' points to unknown state 'Failed'. When the transfer fails, the run should simply end as failed with error TransferFailed.",
      steps=[
          S("get_validation"),
          S("search_docs", query="catch next fail state error", docs=[RETRY, STATES]),
          S("propose_plan", steps=["Add state `workflows.payout.states.Failed` = `{type: fail, error: TransferFailed}`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.payout.states.Failed", value={"type": "fail", "error": "TransferFailed"}),
      ],
      final="""The catcher sends errors to `Failed`, but no state had that name [docs/workflows.md#retry-and-catch].

Added `Failed: {type: fail, error: TransferFailed}`, so a failed transfer ends the run as failed with that error. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 272  engine native on premises
    C(272, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#engines"],
      project=dict(files={"pskit.yml": onprem("etl", """functions:
  extract:
    handler: app.etl.extract
workflows:
  nightly:
    engine: native
    start_at: Extract
    states:
      Extract: {type: task, function: extract}
"""), **app("etl", "extract")}),
      user="""  ERROR: [workflows.nightly] On-premises has no native workflow service supported by pskit; use `engine: embedded` or `auto`

this was for AWS, now same file for onprem""",
      steps=[
          S("get_validation"),
          S("search_docs", query="workflow engine native embedded", docs=[ENGINES]),
          S("ask_user", question="Do you still deploy this file to AWS too? Then I'd use `engine: auto` (Step Functions on AWS, embedded on premises).",
            options=["Yes, both: auto", "Only onprem now: embedded"], answer="Yes, both: auto"),
          S("propose_plan", steps=["Set `workflows.nightly.engine` to `auto`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.nightly.engine", value="auto"),
      ],
      final="""On premises there is no native workflow service; workflows run on the embedded engine in the host [docs/workflows.md#engines].

Set `engine: auto`: Step Functions on AWS, the embedded engine on premises. Validate for onprem: valid (`workflow nightly: embedded engine`)."""),

    # ------------------------------------------------------------------ 273  nodejs runtime on one function of a Python service
    C(273, provider="onprem", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("chat", """functions:
  rooms:
    handler: app.chat.rooms
    events:
      - http: GET /rooms
  typing:
    handler: app.chat.typing
    runtime: nodejs20
    events:
      - http: POST /typing
""", **H), **app("chat", "rooms", "typing")}),
      user="I set runtime nodejs20 on typing because a tutorial said Node is faster. Now: function 'typing' uses nodejs20 but the service runtime is python3.12. The code is Python anyway.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `functions.typing.runtime` (inherit python3.12)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.typing.runtime", value=None),
      ],
      final="""A pskit service is either Python or Node.js, never both, and `typing` is Python code anyway [docs/configuration.md#functions].

Removed `runtime: nodejs20`, so `typing` uses the service's python3.12. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 274  function name with a dot
    C(274, provider="onprem", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#top-level"],
      project=dict(files={"pskit.yml": onprem("mailer", """functions:
  send.email:
    handler: app.mail.send
    events:
      - queue: outbox
"""), **app("mail", "send")}),
      user="name 'send.email' must start with a letter and use letters, digits, - or _ . ok change it",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename function `send.email` to `send-email` (same handler and event)", "Validate for onprem"]),
          S("set_config", path="functions", value={"send-email": {"handler": "app.mail.send", "events": [{"queue": "outbox"}]}}),
      ],
      final="""Function names allow letters, digits, `-` and `_`, no dots [docs/configuration.md#top-level]. Renamed it `send-email`; handler and queue are unchanged. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 275  retry interval
    C(275, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#retry-and-catch"],
      project=dict(files={"pskit.yml": onprem("sync-flow", """functions:
  pull:
    handler: app.sync.pull
workflows:
  sync:
    start_at: Pull
    states:
      Pull:
        type: task
        function: pull
        retry: [{errors: [ConnectionError], max_attempts: 5, interval: 10}]
""", **H), **app("sync", "pull")}),
      user="retry.0.interval: Extra inputs are not permitted. want 10s between tries",
      steps=[
          S("get_validation"),
          S("search_docs", query="retry interval_seconds backoff", docs=[RETRY]),
          S("propose_plan", steps=["Rename `interval` to `interval_seconds` (10)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.sync.states.Pull.retry.0", value={"errors": ["ConnectionError"], "max_attempts": 5, "interval_seconds": 10}),
      ],
      final="""The key is `interval_seconds` [docs/workflows.md#retry-and-catch]. Now `interval_seconds: 10`, `max_attempts: 5`. `pskit validate -p onprem -s prod`: valid. `backoff_rate` defaults to 2.0, so waits grow 10, 20, 40 s; add `backoff_rate: 1` for a flat 10 s."""),

    # ------------------------------------------------------------------ 276  tz instead of timezone
    C(276, provider="onprem", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("standup", """functions:
  remind:
    handler: app.team.remind
    events:
      - schedule: {cron: "45 9 * * 1-5", tz: Europe/Berlin}
"""), **app("team", "remind")}),
      user="The stand-up reminder must fire at 09:45 Berlin time on weekdays. Validation: functions.remind.events.0.tz: Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule timezone", docs=[SCHED]),
          S("propose_plan", steps=["Rename `tz` to `timezone` (Europe/Berlin)", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.remind.events.0.schedule", value={"cron": "45 9 * * 1-5", "timezone": "Europe/Berlin"}),
      ],
      final="""The key is `timezone` [docs/events.md#schedule]. Now `timezone: Europe/Berlin`.

Validate for onprem: valid, with a WARNING that this machine has no IANA time-zone database yet; `pskit deploy` vendors `tzdata`, so the deployed host fires at 09:45 Berlin time [docs/providers.md#onprem-on-premises]."""),

    # ------------------------------------------------------------------ 277  http route instead of path
    C(277, provider="onprem", stage="staging", mode="auto", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http"],
      project=dict(files={"pskit.yml": onprem("orders-api", """functions:
  list-orders:
    handler: app.orders.listing
    events:
      - http: {route: /orders, method: GET}
""", **H), **app("orders", "listing")}),
      user="events.0.route: Extra inputs are not permitted (API GW called it route)",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the event to `{http: {path: /orders, method: GET}}`", "Validate for onprem, stage staging"]),
          S("set_config", path="functions.list-orders.events.0", value={"http": {"path": "/orders", "method": "GET"}}),
      ],
      final="""In pskit the HTTP key is `path` [docs/events.md#http]. Now `http: {path: /orders, method: GET}` (or the shorthand `- http: GET /orders`). `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 278  queue batch instead of batch_size
    C(278, provider="onprem", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#queue"],
      project=dict(files={"pskit.yml": onprem("geo-index", """functions:
  index:
    handler: app.geo.index
    events:
      - queue: {name: places, batch: 25}
""", **H), **app("geo", "index")}),
      user="""Error: pskit.yml is invalid:
  - functions.index.events.0.batch: Extra inputs are not permitted""",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue batch_size", docs=[QUEUE]),
          S("propose_plan", steps=["Rename `batch` to `batch_size` (25)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.index.events.0.queue", value={"name": "places", "batch_size": 25}),
      ],
      final="""The option is `batch_size` [docs/events.md#queue]. Now `queue: {name: places, batch_size: 25}`. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 279  suffix as a list
    C(279, provider="onprem", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage"],
      project=dict(files={"pskit.yml": onprem("gallery", """functions:
  thumb:
    handler: app.gallery.thumb
    events:
      - storage: {bucket: photos, suffix: [.jpg, .png]}
"""), **app("gallery", "thumb")}),
      user="I want thumbnails for .jpg and .png files. Validation says suffix: Input should be a valid string. How do I give two endings?",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage event suffix prefix", docs=[STORAGE]),
          S("propose_plan", steps=["Use two storage events on `photos`: one with `suffix: .jpg`, one with `suffix: .png`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.thumb.events", value=[{"storage": {"bucket": "photos", "suffix": ".jpg"}},
                                                                {"storage": {"bucket": "photos", "suffix": ".png"}}]),
      ],
      final="""`suffix` is one string per event [docs/events.md#storage]. For two endings, give the function two storage events on the same bucket: one `.jpg`, one `.png`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 280  topic filter as a list
    C(280, provider="onprem", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#topic"],
      project=dict(files={"pskit.yml": onprem("payments", """functions:
  paid:
    handler: app.pay.paid
    events:
      - topic: {name: billing, filter: [paid, refunded]}
""", **H), **app("pay", "paid")}),
      user="topic filter Input should be a valid dictionary. message have attribute kind, i want paid or refunded",
      steps=[
          S("get_validation"),
          S("search_docs", query="topic filter attributes", docs=[TOPIC]),
          S("propose_plan", steps=["Set `functions.paid.events.0.topic.filter` to `{kind: [paid, refunded]}`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.paid.events.0.topic.filter", value={"kind": ["paid", "refunded"]}),
      ],
      final="""A filter names the attribute and its allowed values: `{kind: [paid, refunded]}` [docs/events.md#topic]. Changed it. `pskit validate -p onprem -s staging`: valid. On premises it matches message attributes first, then JSON body fields."""),
]
