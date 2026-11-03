"""Category C (fix a validation error), batch 18: on-premises fixes with plan notes, rejected plans, questions,
stage-only failures, Node.js host options and drivers. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble import D, S  # noqa: E402
from _onprem_c import C, app, cluster, mods, onprem, saved  # noqa: E402

P = "docs/providers.md"
A = "onprem-on-premises"
R = "docs/resources.md"
CF = "docs/configuration.md"
TUNING = D(P, A, start="    execution_retention: 500", end="capture_output: true")
TRIGGERS = D(P, A, start="| Trigger |", end="| http |")
NODE = D(P, A, start="**Node.js / TypeScript services**", end="**Node.js / TypeScript services**")
CLUSTER_OPT = D("docs/cluster.md", "set-up", start="4. **Point the functions", end="memory: 256")
ONE_GROUP = D("docs/placement.md", "how-the-groups-work-together", start="* A built-in queue or bucket", end="groups, give it a driver")
PRESETS = D(R, "storage-drivers", start="| Preset |", end="| `minio` |", words=330)
SQS_ROW = D(R, "queue-drivers", start="| Driver |", end="| `azure_queue` |", words=330)
FROM_EVENT = D(R, "using-a-resource-from-an-event", words=150)
DRIVERS_INTRO = D(R, "on-premises-drivers", start="Set `options.driver`", end="Set `options.driver`")
STAGES_OV = D(CF, "stages-per-stage-overrides")
SWITCH_OFF = D(CF, "switch-something-off-on-one-cloud", start="```yaml", end="Disabled functions and workflows")
QUEUE = D("docs/events.md", "queue", words=170)
H = dict(host="0.0.0.0")
NODE_FN = "exports.{0} = async (event, ctx) => ({{ ok: true, fn: \"{0}\" }});\n"

CONVERSATIONS = [
    # ------------------------------------------------------------------ 341  workflow_workers 0, plan approved with a note
    C(341, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("claims", """functions:
  assess:
    handler: app.claims.assess
workflows:
  claim:
    start_at: Assess
    states:
      Assess: {type: task, function: assess}
""", extra="    workflow_workers: 0\n", **H), **app("claims", "assess")}),
      user="I set workflow_workers: 0 to stop workflows from overloading the prod box; validation fails. What's the safe minimum?",
      steps=[
          S("get_validation"),
          S("search_docs", query="workflow_workers runs at once", docs=[TUNING]),
          S("propose_plan", steps=["Set `provider.options.workflow_workers` to 1 (the minimum: one run at a time)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": "One is too slow for us, use 4."}),
          S("set_config", path="provider.options.workflow_workers", value=4),
      ],
      final="""`workflow_workers` is how many runs execute at once, and it must be at least 1; further starts wait for a free worker [docs/providers.md#onprem-on-premises].

As you noted, I set `workflow_workers: 4` instead of 1 (the default is 8). `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 342  replicas 600, approved with a note
    C(342, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="terse_expert",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={"pskit.yml": onprem("flash-sale", """functions:
  buy:
    handler: app.sale.buy
    events:
      - http: POST /buy
""", extra="    cluster: {name: prod, replicas: 600}\n", **H), **app("sale", "buy"), **cluster("prod", "swarm", "app-1", "app-2")}),
      user="cluster.replicas must be 1..500 on prod. max it",
      steps=[
          S("get_validation"),
          S("search_docs", query="cluster replicas cpu memory per replica", docs=[CLUSTER_OPT]),
          S("propose_plan", steps=["Set `provider.options.cluster.replicas` to 500 (the maximum)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": "Actually two servers can't hold 500. Use 50."}),
          S("set_config", path="provider.options.cluster.replicas", value=50),
      ],
      final="""`replicas` is 1..500 [docs/cluster.md#set-up]. Per your note I used 50, not the maximum: each replica reserves 0.25 CPU and 256 MB by default, so 50 on app-1 + app-2 is about 12.5 cores. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 343  bucket in two groups, rejected move -> minio
    C(343, provider="onprem", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/placement.md#how-the-groups-work-together", "docs/resources.md#storage-drivers"],
      project=dict(files={"pskit.yml": onprem("documents", """functions:
  preview:
    handler: app.docs.preview
    events:
      - storage: {bucket: uploads, suffix: .pdf}
  virus-scan:
    handler: app.scan.virus
    events:
      - storage: {bucket: uploads}
""", extra="    deploy: {python: bundle}\n    placement:\n      groups:\n        web: {server: app-1}\n        scan: {server: db-1, functions: [virus-scan]}\n", **H),
          **mods(docs="preview", scan="virus"), **saved("app-1", "db-1")}),
      user="Staging: bucket uploads triggers functions in groups scan and web. The scanner has to stay isolated on db-1 and preview on app-1. We run MinIO at http://192.0.2.30:9000 that both servers can reach.",
      steps=[
          S("get_validation"),
          S("search_docs", query="bucket several groups shared driver minio", docs=[ONE_GROUP]),
          S("propose_plan", steps=["Move `virus-scan` back to the web group", "Validate for onprem, stage staging"],
            result={"decision": "rejected", "note": "No, I said the scanner must stay on db-1."}),
          S("ask_user", question="Sorry, I'll keep both servers and put `uploads` on your MinIO instead. Which environment variables on the servers hold the MinIO access key and secret key?",
            answer="MINIO_ACCESS_KEY and MINIO_SECRET_KEY"),
          S("propose_plan", steps=["Add `resources.uploads` (storage) with `driver: minio`, `endpoint: http://192.0.2.30:9000`, `access_key_env: MINIO_ACCESS_KEY`, `secret_key_env: MINIO_SECRET_KEY`",
                                   "Point both events at `resource: uploads`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.uploads", value={"type": "storage", "external": True, "options": {
              "driver": "minio", "endpoint": "http://192.0.2.30:9000", "access_key_env": "MINIO_ACCESS_KEY", "secret_key_env": "MINIO_SECRET_KEY"}}),
          S("set_config", path="functions.preview.events.0", value={"storage": {"resource": "uploads", "suffix": ".pdf"}}),
          S("set_config", path="functions.virus-scan.events.0", value={"storage": {"resource": "uploads"}}),
      ],
      final="""A built-in bucket lives in one group; a bucket with a shared driver can trigger functions in several [docs/placement.md#how-the-groups-work-together].

Nothing moved. `uploads` is now an external MinIO bucket (`endpoint: http://192.0.2.30:9000`, keys from `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` on each host), and both events use `resource: uploads`. `pskit validate -p onprem -s staging`: valid. Both hosts poll MinIO, so preview and the scanner each see new files."""),

    # ------------------------------------------------------------------ 344  why can't I deploy to the Windows box: target_os win
    C(344, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("shop-floor", """functions:
  counter:
    handler: app.floor.counter
    events:
      - http: GET /count
""", extra="    deploy: {method: ssh, host: 192.0.2.50, python: bundle, target_os: win}\n", **H), **app("floor", "counter")}),
      user="Why can't I deploy to our Windows mini PC in the factory? I already enabled OpenSSH on it.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.deploy.target_os` to `windows`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.target_os", value="windows"),
      ],
      final="""Deploy stops because validation fails: `target_os` takes `auto`, `linux`, `windows` or `darwin`, and `win` isn't one of them [docs/providers.md#onprem-on-premises].

Set `target_os: windows`. Validate for onprem: valid. With `python: bundle` pskit ships a Windows CPython, so the PC needs no Python. Deploy from the **Deploy** page or `pskit deploy -s dev`."""),

    # ------------------------------------------------------------------ 345  stage-only failure: prod override batch_size 0
    C(345, provider="onprem", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/events.md#queue"],
      project=dict(files={"pskit.yml": onprem("mails", """functions:
  send:
    handler: app.mail.send
    events:
      - queue: {name: outbox, batch_size: 10}
stages:
  prod:
    functions:
      send:
        events:
          - queue: {name: outbox, batch_size: 0}
""", **H), **app("mail", "send")}),
      user="dev validate ok but prod say batch_size greater than or equal to 1?? i dont have 0",
      steps=[
          S("get_validation"),
          S("search_docs", query="stages override functions lists replaced", docs=[STAGES_OV, D(CF, "precedence-later-wins", start="Dicts are deep-merged", end="Dicts are deep-merged")]),
          S("ask_user", question="Your `stages.prod` block sets `batch_size: 0` for `send`. What batch size should prod use?", options=["1", "10 like dev"], answer="1, one mail at a time in prod"),
          S("propose_plan", steps=["Set `stages.prod.functions.send.events.0.queue.batch_size` to 1", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.functions.send.events.0.queue.batch_size", value=1),
      ],
      final="""The 0 is in `stages.prod`, which only applies to prod; there the events list replaces dev's whole list [docs/configuration.md#stages-per-stage-overrides].

Set the prod override to `batch_size: 1`. `pskit validate -p onprem -s prod`: valid. Dev still uses 10."""),

    # ------------------------------------------------------------------ 346  auth iam: keep it on AWS, none only on premises (approved with note)
    C(346, provider="onprem", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#onprem-on-premises", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=dict(files={"pskit.yml": """service: internal-api
provider:
  name: aws
  region: eu-west-1
providers:
  onprem:
    region: local
    options: {host: 0.0.0.0, port: 8080}
functions:
  report:
    handler: app.api.report
    events:
      - http: {path: /report, method: GET, auth: iam}
""", **app("api", "report")}),
      user="Same file deploys to AWS and on-prem. Validating for onprem gives auth `iam` is not enforced on-premises.",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem http auth none override one provider", docs=[TRIGGERS, SWITCH_OFF]),
          S("propose_plan", steps=["Set `functions.report.events.0.http.auth` to `none`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": "Keep IAM on AWS! Change it only for onprem."}),
          S("set_config", path="providers.onprem.functions", value={"report": {"events": [{"http": {"path": "/report", "method": "GET", "auth": "none"}}]}}),
      ],
      final="""On premises there's no IAM in front of the host, so `auth` must be `none` there [docs/providers.md#onprem-on-premises].

Following your note, AWS keeps `auth: iam`: I added `providers.onprem.functions.report.events` with the same route and `auth: none` (lists are replaced per provider) [docs/configuration.md#switch-something-off-on-one-cloud]. `pskit validate -p onprem -s staging`: valid. On premises, check the caller in the handler."""),

    # ------------------------------------------------------------------ 347  duplicate route, rejected delete -> new path
    C(347, provider="onprem", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/configuration.md#functions"],
      project=dict(files={"pskit.yml": onprem("orders", """functions:
  orders:
    handler: app.orders.list_orders
    events:
      - http: GET /orders
  orders-v2:
    handler: app.orders_v2.list_orders
    events:
      - http: GET /orders
"""), **mods(orders="list_orders", orders_v2="list_orders")}),
      user="""Error: pskit.yml is invalid:
  - <root>: Value error, route GET /orders is used by both 'orders' and 'orders-v2'""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete the duplicate function `orders-v2`", "Validate for onprem"],
            result={"decision": "rejected", "note": "No! v2 is the new version, both must run."}),
          S("ask_user", question="OK, both stay. Which path should v2 answer on?", options=["/v2/orders", "/orders/v2"], answer="/v2/orders"),
          S("propose_plan", steps=["Set `functions.orders-v2.events.0` to `- http: GET /v2/orders`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.orders-v2.events.0", value={"http": "GET /v2/orders"}),
      ],
      final="""Two functions can't share one `METHOD /path` [docs/configuration.md#functions].

Both functions stay; `orders-v2` now answers `GET /v2/orders`, `orders` keeps `GET /orders`. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 348  Node.js service: deploy.node portable
    C(348, provider="onprem", stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("js-api", """  runtime: nodejs20
functions:
  hello:
    handler: app.hello.hello
    events:
      - http: GET /hello
""", extra="    deploy: {method: ssh, host: 192.0.2.11, python: bundle, node: portable}\n", **H),
          "app/hello.js": NODE_FN.format("hello")}),
      user="Node.js service to a server without Node installed. I set node: portable and staging says options.deploy.node must be one of auto, system, bundle.",
      steps=[
          S("get_validation"),
          S("search_docs", query="node bundle system server", docs=[NODE]),
          S("propose_plan", steps=["Set `provider.options.deploy.node` to `bundle` (ships the official Node.js binary)", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.node", value="bundle"),
      ],
      final="""The portable option is called `bundle`: pskit downloads the official nodejs.org build for the target and ships only its `node` binary [docs/providers.md#onprem-on-premises].

Set `node: bundle`. `pskit validate -p onprem -s staging`: valid. `python: bundle` stays, because the host itself is a Python process."""),

    # ------------------------------------------------------------------ 349  Node.js service: host_python python3.8
    C(349, provider="onprem", stage="prod", mode="auto", page="Deploy", persona="terse_expert",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("ts-hooks", """  runtime: nodejs22
functions:
  hook:
    handler: app.hook.hook
    events:
      - http: POST /hook
""", extra="    deploy: {method: ssh, host: 192.0.2.10, node: bundle, python: bundle, host_python: python3.8}\n", **H),
          "app/hook.js": NODE_FN.format("hook")}),
      user="deploy.host_python must be one of ... prod. use the default",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `provider.options.deploy.host_python` (default python3.12)", "Validate for onprem, stage prod"]),
          S("set_config", path="provider.options.deploy.host_python", value=None),
      ],
      final="""`host_python` is the interpreter of the Python host that runs your Node.js workers; 3.8 isn't offered [docs/providers.md#onprem-on-premises]. Removed it, so the default python3.12 is bundled. `pskit validate -p onprem -s prod`: valid."""),

    # ------------------------------------------------------------------ 350  log_buffer 5k
    C(350, provider="onprem", stage="dev", mode="ask", page="Logs", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("chatty", """functions:
  talk:
    handler: app.chat.talk
    events:
      - http: POST /talk
""", extra="    log_buffer: 20k\n"), **app("chat", "talk")}),
      user="logs page lose old lines so i set log_buffer: 20k, now must be an integer >= 100",
      steps=[
          S("get_validation"),
          S("search_docs", query="log_buffer entries memory", docs=[TUNING]),
          S("propose_plan", steps=["Set `provider.options.log_buffer` to 20000", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.log_buffer", value=20000),
      ],
      final="""`log_buffer` is a plain number of entries kept in memory (default 5000, min 100); `20k` is text [docs/providers.md#onprem-on-premises]. Set `log_buffer: 20000`. Validate for onprem: valid. Older entries are still in `<data_dir>/logs/host.jsonl`."""),

    # ------------------------------------------------------------------ 351  execution_retention unlimited
    C(351, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("audit-flow", """functions:
  record:
    handler: app.audit.record
workflows:
  audit:
    start_at: Record
    states:
      Record: {type: task, function: record}
""", extra="    execution_retention: unlimited\n", **H), **app("audit", "record")}),
      user="Auditors want every workflow run kept, so I wrote execution_retention: unlimited. Prod validation: must be an integer >= 1.",
      steps=[
          S("get_validation"),
          S("ask_user", question="There's no 'unlimited'; it's a number of finished executions kept on disk. How many runs do you expect per year?",
            answer="about 30000"),
          S("propose_plan", steps=["Set `provider.options.execution_retention` to 50000 (headroom over 30000 a year)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.execution_retention", value=50000),
      ],
      final="""`execution_retention` is how many finished executions stay under `<data_dir>/executions` (default 500); it must be a number [docs/providers.md#onprem-on-premises].

Set `execution_retention: 50000`, more than a year of your runs. `pskit validate -p onprem -s prod`: valid. For a permanent audit trail, also have `record` write each run to your own storage."""),

    # ------------------------------------------------------------------ 352  sqs wait_seconds 20s
    C(352, provider="onprem", stage="staging", mode="auto", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#queue-drivers"],
      project=dict(files={"pskit.yml": onprem("sqs-reader", """resources:
  events:
    type: queue
    external: true
    options: {driver: sqs, queue_url: "https://sqs.eu-west-1.amazonaws.com/123456789012/events", wait_seconds: 20s}
functions:
  read:
    handler: app.events.read
    events:
      - queue: {resource: events}
""", **H), **app("events", "read")}),
      user="""  ERROR: [resources.events] resource 'events': wait_seconds must be an integer""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.events.options.wait_seconds` to 20", "Validate for onprem, stage staging"]),
          S("set_config", path="resources.events.options.wait_seconds", value=20),
      ],
      final="""`wait_seconds` is a number (0-20 for sqs) [docs/resources.md#queue-drivers]. Now `wait_seconds: 20`, the longest long poll. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 353  directory driver mapping without path
    C(353, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/resources.md#on-premises-drivers"],
      project=dict(files={"pskit.yml": onprem("plotter", """resources:
  jobs:
    type: queue
    external: true
    options:
      driver: {use: directory}
functions:
  plot:
    handler: app.plot.draw
    events:
      - queue: {resource: jobs}
"""), **app("plot", "draw")}),
      user="I want the plot jobs as files in a folder that another program also writes to. Studio shows: the directory driver needs path. Which path?",
      steps=[
          S("get_validation"),
          S("search_docs", query="driver mapping use parameters directory path", docs=[DRIVERS_INTRO]),
          S("ask_user", question="Which folder does the other program write the job files to?", answer="D:/plotter/jobs"),
          S("propose_plan", steps=["Set `resources.jobs.options.driver` to `{use: directory, path: D:/plotter/jobs}`", "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.jobs.options.driver", value={"use": "directory", "path": "D:/plotter/jobs"}),
      ],
      final="""The `directory` driver keeps the queue in a folder, so it needs that folder's `path` [docs/resources.md#on-premises-drivers].

Now `driver: {use: directory, path: D:/plotter/jobs}`. Validate for onprem: valid. The host reads one JSON file per message from there."""),

    # ------------------------------------------------------------------ 354  smtp event on a queue resource
    C(354, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#using-a-resource-from-an-event"],
      project=dict(files={"pskit.yml": onprem("helpdesk", """resources:
  support-mail:
    type: smtp
  tickets:
    type: queue
functions:
  inbound:
    handler: app.helpdesk.inbound
    events:
      - smtp: {resource: tickets}
""", **H), **app("helpdesk", "inbound")}),
      user="Incoming support e-mails should trigger inbound. Prod validation: function 'inbound' has a smtp event on resource 'tickets', which is a queue.",
      steps=[
          S("get_validation"),
          S("search_docs", query="event resource type must match", docs=[FROM_EVENT]),
          S("propose_plan", steps=["Set `functions.inbound.events.0.smtp.resource` to `support-mail` (your SMTP server resource)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.inbound.events.0.smtp.resource", value="support-mail"),
      ],
      final="""An event's resource must be of the same type, and `tickets` is a queue; the SMTP server is `support-mail` [docs/resources.md#using-a-resource-from-an-event].

The trigger is now `smtp: {resource: support-mail}`. `pskit validate -p onprem -s prod`: valid. `inbound` can still put tickets on the `tickets` queue from its code."""),

    # ------------------------------------------------------------------ 355  two problems in one: queue name and dead_letter with slashes
    C(355, provider="onprem", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("printing", """functions:
  print:
    handler: app.printing.run
    events:
      - queue: {name: print/high, dead_letter: print/failed}
""", **H), **app("printing", "run")}),
      user="2 errors invalid queue name 'print/high' and invalid dead_letter queue name. i want like folders",
      steps=[
          S("get_validation"),
          S("search_docs", query="onprem queue names single path segment", docs=[D(P, A, start="Omitted services default to `builtin`", end="Omitted services default to `builtin`")]),
          S("propose_plan", steps=["Rename the queue to `print-high` and the dead-letter queue to `print-failed`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.print.events.0.queue", value={"name": "print-high", "dead_letter": "print-failed"}),
      ],
      final="""On premises every queue is one folder, so its name is a single path segment without slashes; that applies to the dead-letter queue too [docs/providers.md#onprem-on-premises].

Now `name: print-high`, `dead_letter: print-failed`. `pskit validate -p onprem -s staging`: valid. Use dashes for the "folder" feeling: `print-low`, `print-high`, ..."""),

    # ------------------------------------------------------------------ 356  stage override: only prod has a bad deploy method
    C(356, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("menu", """functions:
  today:
    handler: app.menu.today
    events:
      - http: GET /today
stages:
  prod:
    provider:
      options:
        deploy: {method: container, host: 192.0.2.10}
""", **H), **app("menu", "today")}),
      user="Why does only prod fail? It says options.deploy.method must be one of local, ssh, docker. I wanted prod in a container on 192.0.2.10.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `stages.prod.provider.options.deploy.method` to `docker`", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.provider.options.deploy.method", value="docker"),
      ],
      final="""Only prod has the `stages.prod` override, and there `method: container` isn't a method; containers are `docker` [docs/providers.md#onprem-on-premises].

Set `method: docker` in the prod override. `pskit validate -p onprem -s prod`: valid. The image is built on your machine, copied over SSH and run on 192.0.2.10; Docker is installed there if missing."""),

    # ------------------------------------------------------------------ 357  queue exists instead of existing
    C(357, provider="onprem", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=dict(files={"pskit.yml": onprem("ingest", """functions:
  ingest:
    handler: app.ingest.run
    events:
      - queue: {name: raw, exists: true}
"""), **app("ingest", "run")}),
      user="queue exists: Extra inputs are not permitted",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue existing", docs=[QUEUE]),
          S("propose_plan", steps=["Rename `exists` to `existing`", "Validate for onprem"]),
          S("set_config", path="functions.ingest.events.0.queue", value={"name": "raw", "existing": True}),
      ],
      final="""The key is `existing` [docs/events.md#queue]. Now `queue: {name: raw, existing: true}`: the host waits for the `raw` queue instead of creating it. Validate for onprem: valid."""),

    # ------------------------------------------------------------------ 358  b2 preset without region
    C(358, provider="onprem", stage="prod", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/resources.md#storage-drivers"],
      project=dict(files={"pskit.yml": onprem("archive", """resources:
  archive:
    type: storage
    external: true
    options: {driver: b2, access_key_env: B2_KEY_ID, secret_key_env: B2_APP_KEY}
functions:
  catalog:
    handler: app.archive.catalog
    events:
      - storage: {resource: archive, events: [created]}
""", **H), **app("archive", "catalog")}),
      user="Prod: the b2 driver needs region. Our Backblaze bucket endpoint is s3.us-west-004.backblazeb2.com.",
      steps=[
          S("get_validation"),
          S("search_docs", query="b2 preset region endpoint", docs=[PRESETS]),
          S("propose_plan", steps=["Set `resources.archive.options.region` to `us-west-004` (from the endpoint)", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.archive.options.region", value="us-west-004"),
      ],
      final="""The b2 preset builds `https://s3.<region>.backblazeb2.com`, so it needs the region, which is in your endpoint: `us-west-004` [docs/resources.md#storage-drivers].

Set `region: us-west-004`. `pskit validate -p onprem -s prod`: valid. `B2_KEY_ID` is the application key ID, as the docs say for `access_key`."""),

    # ------------------------------------------------------------------ 359  unknown cluster key burst
    C(359, provider="onprem", stage="staging", mode="ask", page="Cluster", persona="detailed_spec",
      sources=["docs/cluster.md#set-up"],
      project=dict(files={"pskit.yml": onprem("search", """functions:
  query:
    handler: app.search.query
    events:
      - http: GET /search
""", extra="    cluster: {name: lab, replicas: 2, memory: 16384, cpu: 0.5, burst: true}\n", **H),
          **app("search", "query"), **cluster("lab", "kubernetes", "app-1", "app-2")}),
      user="I added burst: true to the cluster settings to allow bursting like on EKS; staging now fails with unknown options.cluster keys ['burst']. Remove whatever isn't supported, keep the rest.",
      steps=[
          S("get_validation"),
          S("search_docs", query="options.cluster keys replicas cpu memory", docs=[CLUSTER_OPT]),
          S("propose_plan", steps=["Delete `provider.options.cluster.burst`", "Validate for onprem, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.cluster.burst", value=None),
      ],
      final="""`options.cluster` takes only `name`, `replicas`, `cpu`, `memory` and `balancer_port`; there is no burst setting [docs/cluster.md#set-up].

Removed `burst`; replicas 2, 0.5 CPU and 16384 MB stay. `pskit validate -p onprem -s staging`: valid."""),

    # ------------------------------------------------------------------ 360  why can't I deploy: sudo sometimes on a saved server
    C(360, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#onprem-on-premises"],
      project=dict(files={"pskit.yml": onprem("kitchen", """functions:
  orders:
    handler: app.kitchen.orders
    events:
      - http: GET /orders
""", extra="    deploy: {server: app-2, python: bundle, sudo: sometimes}\n", **H), **app("kitchen", "orders"), **saved("app-2")}),
      user="why i cant deploy prod to app-2??",
      steps=[
          S("get_validation"),
          S("ask_user", question="`sudo: sometimes` isn't allowed; it's true or false. Does the SSH user on app-2 have passwordless sudo?",
            options=["yes", "no, it's not needed"], answer="yes"),
          S("propose_plan", steps=["Set `provider.options.deploy.sudo` to true", "Validate for onprem, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.deploy.sudo", value=True),
      ],
      final="""Deploy stopped because validation failed on `sudo: sometimes`: `deploy.sudo` must be true or false [docs/providers.md#onprem-on-premises].

Set `sudo: true` (passwordless `sudo -n` on app-2). `pskit validate -p onprem -s prod`: valid. Deploy again from **Deploy** (or `pskit deploy -s prod`)."""),
]
