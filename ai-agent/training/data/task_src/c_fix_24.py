"""Category C (fix a validation error), batch 24 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402

FUTURE = "from __future__ import annotations\n\n"


def C(n, **kw):
    return dict(id=f"c_fix-{n:04d}", category="c_fix", **kw)


def handlers(*names):
    """A tiny handler module with the given function names (scaffolding only)."""
    body = FUTURE
    for name in names:
        body += f"\ndef {name}(event, ctx):\n    return {{\"ok\": True, \"fn\": \"{name}\"}}\n\n"
    return body.rstrip() + "\n"


def proj(yml, module, *names, extra=None):
    files = {"pskit.yml": yml, "app/__init__.py": "", f"app/{module}.py": handlers(*names)}
    files.update(extra or {})
    return dict(files=files)


CONVERSATIONS = [
    # ------------------------------------------------------------------ 461  aws provider memory 2 (meant GB)
    C(461, provider="aws", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: ml-scorer
provider:
  name: aws
  region: us-east-1
  memory: 2
functions:
  score:
    handler: app.model.score
    events:
      - http: POST /score
""", "model", "score"),
      user="i set memory 2 for 2 gb, now error must be greater or equal 64. 64 gb?? too much",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.memory` to 2048 (MB = 2 GB)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.memory", value=2048),
      ],
      final="""Not 64 GB: `memory` is in **MB**, so the smallest value is 64 MB and 2 GB is `2048` [docs/configuration.md#provider].

Set `provider.memory: 2048`. Validate: valid."""),

    # ------------------------------------------------------------------ 462  aws batch_window -1
    C(462, provider="aws", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=proj("""service: order-stream
provider:
  name: aws
  region: eu-west-1
functions:
  consume:
    handler: app.stream.consume
    events:
      - queue:
          name: order-stream
          batch_size: 50
          batch_window: -1
""", "stream", "consume"),
      user="batch_window -1 to disable waiting -> rejected",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `batch_window` of the `consume` queue event to 0 (no wait)",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="functions.consume.events.0.queue.batch_window", value=0),
      ],
      final=""""No waiting" is `batch_window: 0` (range 0-300 s, default 0) [docs/events.md#queue].

Set it to 0. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 463  aws package.source not a directory
    C(463, provider="aws", stage="dev", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/configuration.md#package"],
      project=proj("""service: quotes-api
provider:
  name: aws
  region: eu-west-2
package:
  source: src
functions:
  quote:
    handler: app.quotes.random_quote
    events:
      - http: GET /quote
""", "quotes", "random_quote"),
      user="I added `package.source: src` because a template had it. Now validation says package.source is not a directory, plus a handler warning. My code is in app/ at the project root. Please fix the packaging config.",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Remove `package.source` (default `.`, the project root that contains app/)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="package.source", value=None),
      ],
      final="""`package.source` is the folder whose files are bundled, relative to pskit.yml. There is no `src/` folder in your project, and your code is in `app/` at the root [docs/configuration.md#package].

I removed `package.source`; the default `.` bundles the root, so `app.quotes.random_quote` is found again. `pskit validate` for aws: valid, no warning."""),

    # ------------------------------------------------------------------ 464  aws providers override typo
    C(464, provider="aws", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=proj("""service: storefront
provider:
  name: aws
  region: us-east-1
providers:
  aws:
    functions:
      apii: {memory: 512}
functions:
  api:
    handler: app.store.api
    events:
      - http: ANY /{path+}
""", "store", "api"),
      user="""Error: pskit.yml is invalid:
  - functions.apii.handler: Field required

there is no function apii??""",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Move the override to the real name: `providers.aws.functions.api.memory: 512`",
                                   "Remove `providers.aws.functions.apii`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.aws.functions.api", value={"memory": 512}),
          S("set_config", path="providers.aws.functions.apii", value=None),
      ],
      final="""Exactly: `apii` exists only in the `providers.aws` block (a typo of `api`). That block is merged into the config, so pskit saw a new function `apii` without a handler [docs/configuration.md#providers-per-cloud-overrides].

The override is now `providers.aws.functions.api: {memory: 512}`. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 465  aws enabled: nope
    C(465, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: newsletter
provider:
  name: aws
  region: eu-west-1
functions:
  subscribe:
    handler: app.news.subscribe
    events:
      - http: POST /subscribe
  weekly-send:
    handler: app.news.weekly_send
    enabled: nope
    events:
      - schedule: "0 8 * * 1"
""", "news", "subscribe", "weekly_send"),
      user="I want to switch off the weekly-send function for now, so I wrote enabled: nope. It says unable to interpret input.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.weekly-send.enabled` to `false`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.weekly-send.enabled", value=False),
      ],
      final="""`enabled` only understands true or false [docs/configuration.md#functions].

Set `enabled: false` on `weekly-send`. Validate: valid, with a warning that `weekly-send` is disabled. It stays in the file and is skipped on deploy; set it back to `true` when you want the weekly mail again."""),

    # ------------------------------------------------------------------ 466  aws stages override timeout 1200
    C(466, provider="aws", stage="staging", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/providers.md#providers"],
      project=proj("""service: data-export
provider:
  name: aws
  region: us-west-2
functions:
  export:
    handler: app.export.run
    timeout: 300
    events:
      - schedule: "0 1 * * *"
stages:
  staging:
    functions:
      export: {timeout: 1200}
""", "export", "run"),
      user="dev validates, staging fails with timeout 1200s exceeds AWS Lambda max 900s. The staging export processes more data, so I gave it a stages override. Set the longest allowed value for staging only.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `stages.staging.functions.export.timeout` to 900 (dev keeps 300)",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.staging.functions.export.timeout", value=900),
      ],
      final="""The `stages.staging` override replaced 300 with 1200 for staging only, and AWS Lambda allows at most 900 s [docs/providers.md#providers].

Changed the override to `timeout: 900`; dev still uses 300 [docs/configuration.md#stages-per-stage-overrides]. `pskit validate -p aws -s staging`: valid. If staging exports get longer than 15 minutes, split them into a Step Functions workflow."""),

    # ------------------------------------------------------------------ 467  aws catch errors string
    C(467, provider="aws", stage="prod", mode="auto", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#retry-and-catch"],
      project=proj("""service: kyc-flow
provider:
  name: aws
  region: eu-central-1
functions:
  verify:
    handler: app.kyc.verify
  reject:
    handler: app.kyc.reject
workflows:
  kyc:
    start_at: Verify
    states:
      Verify:
        type: task
        function: verify
        catch:
          - errors: ValueError
            next: Reject
        end: true
      Reject: {type: task, function: reject, end: true}
""", "kyc", "verify", "reject"),
      user="""Error: pskit.yml is invalid:
  - workflows.kyc.states.Verify.catch.0.errors: Input should be a valid list""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `Verify.catch.0.errors` to `[ValueError]`",
                                   "Validate for aws, stage prod"]),
          S("set_config", path="workflows.kyc.states.Verify.catch.0.errors", value=["ValueError"]),
      ],
      final="""`errors` in a catcher is a list of exception class names, even for one [docs/workflows.md#retry-and-catch].

Set `errors: [ValueError]` on the `Verify` catcher. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 468  aws events as mapping
    C(468, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#events-triggers"],
      project=proj("""service: dog-walkers
provider:
  name: aws
  region: ap-southeast-2
functions:
  walkers:
    handler: app.walkers.list_walkers
    events:
      http: GET /walkers
""", "walkers", "list_walkers"),
      user="My walkers function shows an error on the Functions page: events Input should be a valid list. How do I make it a list?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Write `events` of `walkers` as a list with one item: `- http: GET /walkers`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.walkers.events", value=[{"http": "GET /walkers"}]),
      ],
      final="""`events` is a list, and each trigger is one item starting with `-` [docs/events.md#events-triggers].

Now:

```yaml
events:
  - http: GET /walkers
```

The only change is the `- ` in front. Validate: valid."""),

    # ------------------------------------------------------------------ 469  gcp queue name + resource
    C(469, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#events-backed-by-a-resource"],
      project=proj("""service: mail-jobs
provider:
  name: gcp
  region: europe-west1
  options:
    project: mail-jobs-dev
resources:
  mails: {type: queue}
functions:
  send:
    handler: app.mailer.send
    events:
      - queue:
          resource: mails
          name: outgoing-mails
""", "mailer", "send"),
      user="error set either name or resource on queue event not both. i want the queue called outgoing-mails",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `name` from the queue event of `send` (keep `resource: mails`)",
                                   "Give the resource the native name: `resources.mails.name: outgoing-mails`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send.events.0.queue.name", value=None),
          S("set_config", path="resources.mails.name", value="outgoing-mails"),
      ],
      final="""With `resource:` the event takes its name from the resource, so a second `name` on the event conflicts [docs/events.md#events-backed-by-a-resource].

- Event: `queue: {resource: mails}`
- Resource: `mails: {type: queue, name: outgoing-mails}`

On GCP the Pub/Sub topic is now called `outgoing-mails`. Validate: valid."""),

    # ------------------------------------------------------------------ 470  gcp duplicate route /items vs /items/
    C(470, provider="gcp", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/troubleshooting.md#configuration"],
      project=proj("""service: shop-items
provider:
  name: gcp
  region: us-central1
  options:
    project: shop-items-staging
functions:
  list-items:
    handler: app.items.list_items
    events:
      - http: GET /items
  list-items-v2:
    handler: app.items.list_items_v2
    events:
      - http: GET /items/
""", "items", "list_items", "list_items_v2"),
      user="""Error: pskit.yml is invalid:
  - <root>: Value error, route GET /items is used by both 'list-items' and 'list-items-v2'

one has a slash at the end so they're different?""",
      steps=[
          S("get_validation"),
          S("search_docs", query="route used by both",
            docs=[D("docs/troubleshooting.md", "configuration", start="**`route GET /x is used by both 'a' and 'b'`**", end="(`/x` and `/x/` count as the same path).")]),
          S("ask_user", question="`/items` and `/items/` are the same route in pskit. Which path should `list-items-v2` get?",
            options=["GET /v2/items", "GET /items/v2"], answer="GET /v2/items"),
          S("propose_plan", steps=["Change the route of `list-items-v2` to `GET /v2/items`",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.list-items-v2.events.0.http", value="GET /v2/items"),
      ],
      final="""pskit treats `/items` and `/items/` as the same path, and each `METHOD /path` may belong to one function only [docs/troubleshooting.md#configuration].

`list-items-v2` is now on `GET /v2/items`; `list-items` keeps `GET /items`. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 471  gcp workflow start_at missing
    C(471, provider="gcp", stage="dev", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: invoice-run
provider:
  name: gcp
  region: europe-west1
  options:
    project: invoice-run-dev
functions:
  collect:
    handler: app.invoice.collect
  bill:
    handler: app.invoice.bill
workflows:
  monthly:
    states:
      Collect: {type: task, function: collect, next: Bill}
      Bill: {type: task, function: bill, end: true}
""", "invoice", "collect", "bill"),
      user="workflows.monthly.start_at: Field required. starts at Collect",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.monthly.start_at: Collect`",
                                   "Validate for gcp"]),
          S("set_config", path="workflows.monthly.start_at", value="Collect"),
      ],
      final="""Every workflow needs `start_at`, naming its first state [docs/workflows.md#workflow-keys].

Added `start_at: Collect`. `pskit validate` for gcp: valid (native Cloud Workflows)."""),

    # ------------------------------------------------------------------ 472  gcp ${env:...} in region unset
    C(472, provider="gcp", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: geo-cache
provider:
  name: gcp
  region: ${env:GEO_REGION}
  options:
    project: geo-cache-prod
functions:
  tile:
    handler: app.tiles.tile
    events:
      - http: GET /tiles/{z}/{x}/{y}
""", "tiles", "tile"),
      user="Our CI sets GEO_REGION, but validating prod here in studio fails with `unresolved variables: env:GEO_REGION`. CI should still be able to override the region; locally it should default to europe-west1.",
      steps=[
          S("get_validation"),
          S("search_docs", query="env variable default value",
            docs=[D("docs/configuration.md", "variables", end="| `${env:NAME, default}` | environment variable or `default` |")]),
          S("propose_plan", steps=["Set `provider.region` to `${env:GEO_REGION, europe-west1}`",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.region", value="${env:GEO_REGION, europe-west1}"),
      ],
      final="""`${env:GEO_REGION}` has no default, so it fails wherever the variable isn't set, like this studio session [docs/configuration.md#variables].

Now `region: ${env:GEO_REGION, europe-west1}`: CI's `GEO_REGION` still wins, and without it the region is `europe-west1`. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 473  gcp ${self:custom.topic} without custom
    C(473, provider="gcp", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#variables", "docs/configuration.md#top-level"],
      project=proj("""service: alerts
provider:
  name: gcp
  region: us-east1
  options:
    project: alerts-dev-904
functions:
  on-alert:
    handler: app.alerts.on_alert
    events:
      - topic: ${self:custom.topic}
""", "alerts", "on_alert"),
      user="I copied ${self:custom.topic} from an example. It says unresolved variables: self:custom.topic. My topic is called system-alerts.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Add `custom.topic: system-alerts` (the example had a `custom:` block you didn't copy)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="custom", value={"topic": "system-alerts"}),
      ],
      final="""`${self:custom.topic}` reads `custom.topic` from your own pskit.yml, and your file had no `custom:` block [docs/configuration.md#variables].

I added:

```yaml
custom:
  topic: system-alerts
```

Validate: valid. (You could also write `- topic: system-alerts` directly; `custom` is only useful when several places use the same value [docs/configuration.md#top-level].)"""),

    # ------------------------------------------------------------------ 474  gcp catch next -> missing state
    C(474, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: booking-flow
provider:
  name: gcp
  region: europe-west1
  options:
    project: booking-flow-staging
functions:
  reserve:
    handler: app.booking.reserve
  apologize:
    handler: app.booking.apologize
workflows:
  book:
    start_at: Reserve
    states:
      Reserve:
        type: task
        function: reserve
        catch:
          - errors: ["*"]
            next: SendSorry
        end: true
      Apologize: {type: task, function: apologize, end: true}
""", "booking", "reserve", "apologize"),
      user="book workflow say Reserve points to unknown state SendSorry. i renamed it Apologize before",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `Reserve.catch.0.next` to `Apologize`",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.book.states.Reserve.catch.0.next", value="Apologize"),
      ],
      final="""The catcher of `Reserve` still pointed to the old name `SendSorry`. pskit checks `catch.next` targets too [docs/workflows.md#workflow-keys].

Changed it to `next: Apologize`. `pskit validate -p gcp -s staging`: valid. Any error in `Reserve` now goes to `Apologize`."""),

    # ------------------------------------------------------------------ 475  azure providers.azure.funcions typo
    C(475, provider="azure", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=proj("""service: menu-board
provider:
  name: aws
  region: eu-west-1
providers:
  azure:
    region: westeurope
    funcions:
      render: {memory: 1024}
functions:
  render:
    handler: app.board.render
    events:
      - http: GET /board
""", "board", "render"),
      user="""Error: pskit.yml is invalid:
  - funcions: Extra inputs are not permitted

only when validating for azure""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `providers.azure.funcions` to `providers.azure.functions` (same content)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.functions", value={"render": {"memory": 1024}}),
          S("set_config", path="providers.azure.funcions", value=None),
      ],
      final="""The `providers.azure` block had `funcions` (missing "t"). That block is merged into the whole config only for Azure, which is why the other providers didn't complain [docs/configuration.md#providers-per-cloud-overrides].

Renamed it to `functions`, so on Azure `render` gets `memory: 1024`. `pskit validate -p azure`: valid."""),

    # ------------------------------------------------------------------ 476  azure Logic Apps matches middle star
    C(476, provider="azure", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#compiler-notes-and-limits", "docs/workflows.md#choice-rules"],
      project=proj("""service: invoice-routing
provider:
  name: azure
  region: westeurope
functions:
  archive-2024:
    handler: app.route.archive
  current:
    handler: app.route.current
workflows:
  route:
    engine: native
    start_at: ByYear
    states:
      ByYear:
        type: choice
        choices:
          - {variable: "$.number", matches: "INV*2024", next: Archive}
        default: Current
      Archive: {type: task, function: archive-2024, end: true}
      Current: {type: task, function: current, end: true}
""", "route", "archive", "current"),
      user="The native Logic App for `route` fails on prod: matches pattern 'INV*2024' can't be expressed. Invoice numbers always look like INV-<seq>-2024, so a suffix check is enough. Keep it on Logic Apps.",
      steps=[
          S("get_validation"),
          S("search_docs", query="logic apps matches pattern",
            docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="`matches` accepts", end="other globs are a validation error.")]),
          S("propose_plan", steps=["Change the rule in `ByYear` to `matches: \"*-2024\"` (suffix pattern, allowed on Logic Apps)",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.route.states.ByYear.choices.0",
            value={"variable": "$.number", "matches": "*-2024", "next": "Archive"}),
      ],
      final="""Logic Apps only take `abc`, `abc*`, `*abc`, `*abc*` or `*`; a star in the middle (`INV*2024`) isn't possible [docs/workflows.md#compiler-notes-and-limits].

Since every number ends with `-2024`, the rule is now `matches: "*-2024"` [docs/workflows.md#choice-rules]. `pskit validate -p azure -s prod`: valid, still the native engine."""),

    # ------------------------------------------------------------------ 477  azure queue batch_size 0
    C(477, provider="azure", stage="dev", mode="auto", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue"],
      project=proj("""service: orders-queue
provider:
  name: azure
  region: eastus
functions:
  handle-order:
    handler: app.orders.handle
    events:
      - queue:
          name: incoming-orders
          batch_size: 0
""", "orders", "handle"),
      user="batch_size 0 (I wanted the platform default, like SQS) → must be >= 1. Azure Storage Queue.",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue batch_size azure",
            docs=[D("docs/events.md", "queue", start="| Option | aws (SQS) |", end="| `dead_letter`, `max_receive` |")]),
          S("propose_plan", steps=["Remove `batch_size` from the queue event of `handle-order` (ignored on Azure)",
                                   "Validate for azure"]),
          S("set_config", path="functions.handle-order.events.0.queue.batch_size", value=None),
      ],
      final="""`batch_size` must be 1-10000, and on Azure Storage Queues it is ignored anyway [docs/events.md#queue]. "Platform default" simply means leaving it out.

Removed `batch_size`. `pskit validate` for azure: valid."""),

    # ------------------------------------------------------------------ 478  azure memory 1.5
    C(478, provider="azure", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: chart-maker
provider:
  name: azure
  region: westeurope
functions:
  chart:
    handler: app.charts.chart
    memory: 1.5
    events:
      - http: POST /chart
""", "charts", "chart"),
      user="I typed 1.5 in Memory for my chart function (1.5 GB) and it says got a number with a fractional part.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.chart.memory` to 1536 (MB = 1.5 GB)",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.chart.memory", value=1536),
      ],
      final="""The **Memory (MB)** field is in megabytes and takes whole numbers only [docs/configuration.md#functions].

1.5 GB = 1536 MB, so I set `memory: 1536`. Validate for staging: valid."""),

    # ------------------------------------------------------------------ 479  azure `timer:` event
    C(479, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: cleanup-bot
provider:
  name: azure
  region: northeurope
functions:
  cleanup:
    handler: app.cleanup.run
    events:
      - timer: "0 2 * * *"
""", "cleanup", "run"),
      user="in azure it call timer trigger so i write timer: but pskit say unknown event type timer",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `timer:` with `schedule: \"0 2 * * *\"` on `cleanup`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.cleanup.events.0", value={"schedule": "0 2 * * *"}),
      ],
      final="""In pskit it is called `schedule` on every cloud; on Azure pskit turns it into a timer trigger [docs/providers.md#azure-azure-functions].

Changed to `- schedule: "0 2 * * *"` (every day 02:00 UTC; Azure timers always use UTC) [docs/events.md#schedule]. Validate: valid."""),

    # ------------------------------------------------------------------ 480  azure `blob:` event
    C(480, provider="azure", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: media-ingest
provider:
  name: azure
  region: westeurope
functions:
  ingest:
    handler: app.media.ingest
    events:
      - blob: {container: media-in, path: "uploads/{name}"}
""", "media", "ingest"),
      user="unknown event type 'blob'. container media-in, files under uploads/",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace the `blob` event with `storage: {bucket: media-in, prefix: uploads/}`",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest.events.0", value={"storage": {"bucket": "media-in", "prefix": "uploads/"}}),
      ],
      final="""The portable trigger is `storage`; `bucket` is the container name, and `prefix` replaces the `uploads/{name}` path pattern [docs/events.md#storage]. On Azure it becomes a blob trigger [docs/providers.md#azure-azure-functions].

Set `- storage: {bucket: media-in, prefix: uploads/}`. `pskit validate -p azure -s prod`: valid."""),
]
