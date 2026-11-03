"""Category C (fix a validation error), batch 23 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 441  aws visibility_timeout "2m"
    C(441, provider="aws", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=proj("""service: video-jobs
provider:
  name: aws
  region: us-east-1
functions:
  encode:
    handler: app.video.encode
    timeout: 20
    events:
      - queue:
          name: encode-jobs
          visibility_timeout: 2m
""", "video", "encode"),
      user="visibility_timeout 2m rejected, unable to parse as integer",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `visibility_timeout` of the `encode` queue event to 120 (seconds)",
                                   "Validate for aws"]),
          S("set_config", path="functions.encode.events.0.queue.visibility_timeout", value=120),
      ],
      final="""`visibility_timeout` is an integer number of seconds, no unit suffix [docs/events.md#queue].

Set `visibility_timeout: 120`. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 442  aws storage events string
    C(442, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage"],
      project=proj("""service: music-library
provider:
  name: aws
  region: eu-west-1
functions:
  index-song:
    handler: app.songs.index_song
    events:
      - storage:
          bucket: music-uploads
          events: created
          suffix: .mp3
""", "songs", "index_song"),
      user="it says events: Input should be a valid list. I only want created.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Write the storage events of `index-song` as a list: `[created]`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.index-song.events.0.storage.events", value=["created"]),
      ],
      final="""`events` inside a storage trigger is always a list, even with one item [docs/events.md#storage].

It is now `events: [created]`. Validate: valid. (`[created]` is also the default, so leaving the line out does the same.)"""),

    # ------------------------------------------------------------------ 443  aws cors methods string
    C(443, provider="aws", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: widget-api
provider:
  name: aws
  region: us-west-2
functions:
  widgets:
    handler: app.widgets.list_widgets
    events:
      - http:
          path: /widgets
          method: GET
          cors:
            origins: ["https://shop.example.com"]
            methods: GET
""", "widgets", "list_widgets"),
      user="""Error: pskit.yml is invalid:
  - functions.widgets.events.0.cors.bool: Input should be a valid boolean
  - functions.widgets.events.0.cors.CorsConfig.methods: Input should be a valid list

origins is a list already, what now""",
      steps=[
          S("get_validation"),
          S("search_docs", query="cors methods origins list",
            docs=[D("docs/events.md", "http", start="**CORS**", end="max_age: 600")]),
          S("propose_plan", steps=["Make `cors.methods` of `widgets` a list: `[GET]`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.widgets.events.0.http.cors.methods", value=["GET"]),
      ],
      final="""This time it's `methods`: like `origins`, it must be a list [docs/events.md#http].

Set `methods: [GET]`. `pskit validate -p aws -s staging`: valid. Browsers also send `OPTIONS` preflights; the runtime and API Gateway answer those for you."""),

    # ------------------------------------------------------------------ 444  aws function without handler
    C(444, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: club-site
provider:
  name: aws
  region: eu-west-2
functions:
  events-list:
    handler: app.site.events_list
    events:
      - http: GET /events
  health:
    events:
      - http: GET /health
""",
          "app/__init__.py": "",
          "app/site.py": handlers("events_list"),
          "app/health.py": handlers("health")}),
      user="the health function has a red mark on the Functions page and I can't validate. please fix it",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Set `functions.health.handler` to `app.health.health` (the function in app/health.py)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.health.handler", value="app.health.health"),
      ],
      final="""The `health` function had no `handler`, so pskit didn't know which code to run; `handler` is required [docs/configuration.md#functions].

Your project has `app/health.py` with a `health` function, so I set `handler: app.health.health`. The Functions page has no errors now, and validate says valid."""),

    # ------------------------------------------------------------------ 445  aws retry as mapping
    C(445, provider="aws", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#retry-and-catch"],
      project=proj("""service: shipment-flow
provider:
  name: aws
  region: eu-central-1
functions:
  book-courier:
    handler: app.ship.book_courier
workflows:
  ship:
    start_at: Book
    states:
      Book:
        type: task
        function: book-courier
        retry:
          errors: [TimeoutError, ConnectionError]
          max_attempts: 4
          interval_seconds: 5
        end: true
""", "ship", "book_courier"),
      user="The ship workflow should retry Book up to 4 times on TimeoutError or ConnectionError, 5 s apart. Validation for prod says `retry: Input should be a valid list`. Keep the same retry settings.",
      steps=[
          S("get_validation"),
          S("search_docs", query="retry rules list errors max_attempts",
            docs=[D("docs/workflows.md", "retry-and-catch", end="max_delay_seconds: 60                      # optional cap")]),
          S("propose_plan", steps=["Wrap the retry rule of `Book` in a list (one rule, same values)",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.ship.states.Book.retry",
            value=[{"errors": ["TimeoutError", "ConnectionError"], "max_attempts": 4, "interval_seconds": 5}]),
      ],
      final="""`retry` is a list of rules (the first matching rule is used), so a single rule still needs the `-` [docs/workflows.md#retry-and-catch].

Now:

```yaml
workflows:
  ship:
    states:
      Book:
        retry:
          - errors: [TimeoutError, ConnectionError]
            max_attempts: 4
            interval_seconds: 5
```

`pskit validate -p aws -s prod`: valid. `backoff_rate` defaults to 2.0, so waits grow (5 s, 10 s, ...); add `backoff_rate: 1` if you want exactly 5 s each time."""),

    # ------------------------------------------------------------------ 446  aws connection key with dash
    C(446, provider="aws", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields", "docs/resources.md#what-handlers-receive"],
      project=proj("""service: crm-sync
provider:
  name: aws
  region: ap-southeast-1
resources:
  crm-db:
    type: database
    external: true
    connection:
      db-host: crm-db.example.com
      port: 5432
      password_env: CRM_DB_PASSWORD
functions:
  sync:
    handler: app.crm.sync
    events:
      - schedule: 30 minutes
""", "crm", "sync"),
      user="resource crm-db connection error: key 'db-host' must start with letter... it start with d??",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the connection key `db-host` to `host` in `crm-db`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.crm-db.connection.db-host", value=None),
          S("set_config", path="resources.crm-db.connection.host", value="crm-db.example.com"),
      ],
      final="""It starts with a letter, yes; the problem is the dash. Connection keys may only have letters, digits and `_`.

I renamed `db-host` to `host` (same value). Validate: valid. In the handler read it as `resource("crm-db")["host"]` [docs/resources.md#what-handlers-receive]."""),

    # ------------------------------------------------------------------ 447  aws resource lists unknown function
    C(447, provider="aws", stage="staging", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/resources.md#fields"],
      project=proj("""service: jobs-svc
provider:
  name: aws
  region: us-east-2
resources:
  jobs:
    type: queue
    functions: [worker]
functions:
  process-jobs:
    handler: app.jobs.process
    events:
      - queue: {resource: jobs}
  api:
    handler: app.jobs.api
    events:
      - http: POST /jobs
""", "jobs", "process", "api"),
      user="resource 'jobs' lists unknown function 'worker'. renamed it to process-jobs; api enqueues too",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.jobs.functions` to `[process-jobs, api]`",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="resources.jobs.functions", value=["process-jobs", "api"]),
      ],
      final="""`resources.jobs.functions` still named the old `worker` [docs/resources.md#fields].

Set `functions: [process-jobs, api]`, so both get the queue binding (`api` needs it to send jobs). `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 448  aws auth key -> jwt (two answers)
    C(448, provider="aws", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http", "docs/providers.md#aws-aws-lambda"],
      project=proj("""service: partner-api
provider:
  name: aws
  region: us-east-1
functions:
  orders:
    handler: app.partner.orders
    events:
      - http:
          path: /partner/orders
          method: GET
          auth: key
""", "partner", "orders"),
      user="On the old REST API we used API keys (usage plans). pskit prod validate says API keys are not available on HTTP APIs. What do I replace it with?",
      steps=[
          S("get_validation"),
          S("search_docs", query="aws http api auth jwt iam",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", question="pskit deploys an HTTP API, which supports `iam` (SigV4-signed calls) or `jwt` (tokens from your identity provider). Which one fits your partners?",
            options=["jwt", "iam"], answer="jwt, we have an OIDC provider"),
          S("ask_user", question="For `jwt` I need the token issuer URL and the audience your tokens carry.",
            answer="issuer https://id.example.com/ and audience partner-api"),
          S("propose_plan", steps=["Set `auth: jwt` on `/partner/orders`",
                                   "Add `authorizer: {issuer: https://id.example.com/, audience: [partner-api]}`",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.orders.events.0.http",
            value={"path": "/partner/orders", "method": "GET", "auth": "jwt",
                   "authorizer": {"issuer": "https://id.example.com/", "audience": ["partner-api"]}}),
      ],
      final="""pskit uses API Gateway **HTTP APIs**, and they have no API keys or usage plans; the options are `jwt` or `iam` [docs/providers.md#aws-aws-lambda].

`/partner/orders` now has `auth: jwt` with `authorizer: {issuer: https://id.example.com/, audience: [partner-api]}` [docs/events.md#http]. `pskit validate -p aws -s prod`: valid.

Partners now send a bearer token from your OIDC provider instead of the API key. Rate limits per partner (usage plans) are not covered by this; handle them in the handler if you need them."""),

    # ------------------------------------------------------------------ 449  gcp projet typo under providers.gcp
    C(449, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="informal_non_native",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen", "docs/configuration.md#providers-per-cloud-overrides"],
      project=proj("""service: event-tickets
provider:
  name: aws
  region: eu-west-1
providers:
  gcp:
    region: europe-west1
    options:
      projet: event-tickets-4410
functions:
  tickets:
    handler: app.tickets.list_tickets
    events:
      - http: GET /tickets
""", "tickets", "list_tickets"),
      user="why can't I deploy to gcp? i did put the project in providers gcp options",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Rename `providers.gcp.options.projet` to `project`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.gcp.options.projet", value=None),
          S("set_config", path="providers.gcp.options.project", value="event-tickets-4410"),
      ],
      final="""Small typo: it was written `projet`, so pskit didn't find `project` [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. (Options are free-form, so a misspelled key is not reported, only the missing one.)

Now `providers.gcp.options.project: event-tickets-4410`. Validate for gcp: valid, and AWS is unchanged [docs/configuration.md#providers-per-cloud-overrides]. You can deploy from the Deploy page with gcp selected."""),

    # ------------------------------------------------------------------ 450  gcp timeout 4000
    C(450, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#functions", "docs/providers.md#providers"],
      project=proj("""service: model-export
provider:
  name: gcp
  region: us-central1
  options:
    project: model-export-prod
functions:
  export-model:
    handler: app.export.run
    timeout: 4000
    memory: 4096
    events:
      - http: POST /export
""", "export", "run"),
      user="export-model can run a bit over an hour. I set timeout 4000 for prod and validation rejects it. Please set the maximum GCP allows for this HTTP function and tell me if that's enough.",
      steps=[
          S("get_validation"),
          S("search_docs", query="gcp max timeout http",
            docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| [`azure`]")]),
          S("propose_plan", steps=["Set `functions.export-model.timeout` to 3600",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.export-model.timeout", value=3600),
      ],
      final="""pskit allows at most 3600 s for any function, and that is also GCP's limit for HTTP functions (event functions: 540 s) [docs/providers.md#providers].

Set `functions.export-model.timeout: 3600`. `pskit validate -p gcp -s prod`: valid.

It is **not** enough for runs "a bit over an hour": those will be stopped at 60 minutes. Split the export into steps, for example a workflow (native Cloud Workflows on GCP) that exports one part per task."""),

    # ------------------------------------------------------------------ 451  azure iam.statements warning
    C(451, provider="azure", stage="dev", mode="auto", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: blob-reader
provider:
  name: azure
  region: westeurope
  iam:
    statements:
      - actions: ["s3:GetObject"]
        resources: ["arn:aws:s3:::reports/*"]
functions:
  read:
    handler: app.reader.read
    events:
      - http: GET /read
""", "reader", "read"),
      user="validate ok but warns iam.statements ignored on Azure. leftover from the Lambda version. clean up",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `provider.iam` (AWS-style statements, ignored on Azure)",
                                   "Validate for azure"]),
          S("set_config", path="provider.iam", value=None),
      ],
      final="""`iam.statements` are AWS-style and aren't mapped on Azure, so they only produced the warning [docs/configuration.md#provider].

Removed `provider.iam`. `pskit validate` for azure: valid, no warnings. Azure permissions for other services have to be granted in Azure itself."""),

    # ------------------------------------------------------------------ 452  gcp handler module not found (warning)
    C(452, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: image-tools
provider:
  name: gcp
  region: europe-west1
  options:
    project: image-tools-dev
functions:
  resize:
    handler: app.handlers.resize
    events:
      - http: POST /resize
""", "images", "resize"),
      user="There's a yellow warning on my resize function: handler module 'app.handlers' not found. Validation still says valid, so is it ok?",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Set `functions.resize.handler` to `app.images.resize` (the file that has `resize`)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.resize.handler", value="app.images.resize"),
      ],
      final="""Not ok: validation passes, but the function would fail when called, because there is no `app/handlers.py`. Your `resize` code is in `app/images.py`.

I set `handler: app.images.resize` (folder.file.function) [docs/configuration.md#functions]. Validate: valid, no warning. Try it on the **Test** page with **▶ Run locally**."""),

    # ------------------------------------------------------------------ 453  gcp ${self:custom.bucket} vs buckets
    C(453, provider="gcp", stage="staging", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: doc-ingest
provider:
  name: gcp
  region: europe-west1
  options:
    project: doc-ingest-staging
custom:
  buckets:
    inbox: doc-ingest-inbox
functions:
  ingest:
    handler: app.docs.ingest
    events:
      - storage: ${self:custom.bucket}
""", "docs", "ingest"),
      user="""Error: unresolved variables: self:custom.bucket

custom has the bucket name, under buckets.inbox""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Change the storage event of `ingest` to `${self:custom.buckets.inbox}`",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest.events.0", value={"storage": "${self:custom.buckets.inbox}"}),
      ],
      final="""`${self:...}` takes the full dotted path, and the name lives at `custom.buckets.inbox`, not `custom.bucket` [docs/configuration.md#variables].

Changed the event to `- storage: ${self:custom.buckets.inbox}`, which resolves to `doc-ingest-inbox`. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 454  gcp hooks camelCase
    C(454, provider="gcp", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#hooks"],
      project=proj("""service: schema-api
provider:
  name: gcp
  region: us-east1
  options:
    project: schema-api-dev
hooks:
  beforePackage: ["python scripts/gen_schema.py"]
functions:
  api:
    handler: app.api.handler
    events:
      - http: ANY /{path+}
""", "api", "handler"),
      user="unknown hooks beforePackage. fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename hook `beforePackage` to `before_package` (same command)",
                                   "Validate for gcp"]),
          S("set_config", path="hooks.beforePackage", value=None),
          S("set_config", path="hooks.before_package", value=["python scripts/gen_schema.py"]),
      ],
      final="""Hook names are snake_case: `before_package`, `after_package`, `before_deploy`, `after_deploy`, `before_remove`, `after_remove` [docs/configuration.md#hooks].

Renamed `beforePackage` → `before_package` with the same command. `pskit validate` for gcp: valid."""),

    # ------------------------------------------------------------------ 455  gcp choice rule with `then`
    C(455, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#choice-rules"],
      project=proj("""service: parcel-flow
provider:
  name: gcp
  region: asia-east1
  options:
    project: parcel-flow-dev
functions:
  ship:
    handler: app.parcel.ship
  hold:
    handler: app.parcel.hold
workflows:
  parcel:
    start_at: Check
    states:
      Check:
        type: choice
        choices:
          - {variable: "$.paid", equals: true, then: Ship}
        default: Hold
      Ship: {type: task, function: ship, end: true}
      Hold: {type: task, function: hold, end: true}
""", "parcel", "ship", "hold"),
      user="workflow error choice rule in Check has no next. but i wrote then: Ship ??",
      steps=[
          S("get_validation"),
          S("search_docs", query="choice rule next",
            docs=[D("docs/workflows.md", "choice-rules", end="next: Standard")]),
          S("propose_plan", steps=["Replace `then: Ship` with `next: Ship` in the rule of `Check`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.parcel.states.Check.choices.0",
            value={"variable": "$.paid", "equals": True, "next": "Ship"}),
      ],
      final="""In pskit a choice rule says where to go with `next`, not `then` [docs/workflows.md#choice-rules].

The rule is now `{variable: "$.paid", equals: true, next: Ship}`; unpaid parcels still go to `Hold`. Validate: valid."""),

    # ------------------------------------------------------------------ 456  azure provider timeout 3600
    C(456, provider="azure", stage="staging", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#providers"],
      project=proj("""service: report-portal
provider:
  name: azure
  region: westeurope
  timeout: 3600
functions:
  home:
    handler: app.portal.home
    events:
      - http: GET /
  build-report:
    handler: app.portal.build_report
    events:
      - queue: report-requests
""", "portal", "home", "build_report"),
      user="why can't I deploy to azure? I set the timeout to one hour to be safe",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.timeout` to 600 (the Azure maximum) for both functions",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": "keep home short, 30 is fine there"}),
          S("set_config", path="provider.timeout", value=600),
          S("set_config", path="functions.home.timeout", value=30),
      ],
      final="""Azure Functions allow at most 600 s (10 minutes) in pskit, so one hour was rejected for both functions [docs/providers.md#providers].

Changed, following your note:
- `provider.timeout: 600` (used by `build-report`)
- `functions.home.timeout: 30`

Validate for staging: valid. You can deploy from the **Deploy** page now."""),

    # ------------------------------------------------------------------ 457  azure container name double dash
    C(457, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#storage"],
      project=proj("""service: scan-archive
provider:
  name: azure
  region: swedencentral
functions:
  archive:
    handler: app.archive.store
    events:
      - storage: raw--scans
""", "archive", "store"),
      user="""ERROR: [functions.archive] container name 'raw--scans' must be 3-63 lowercase letters, digits, dashes

it is lowercase with dashes...""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the container of `archive` to `raw-scans` (single dash)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.archive.events.0", value={"storage": "raw-scans"}),
      ],
      final="""Azure container names also can't have two dashes in a row (and can't start or end with one), so `raw--scans` fails even though every character is allowed [docs/events.md#storage].

Renamed it to `raw-scans`. Validate: valid."""),

    # ------------------------------------------------------------------ 458  azure existing topic, connection missing
    C(458, provider="azure", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions", "docs/events.md#topic"],
      project=proj("""service: price-updates
provider:
  name: azure
  region: westeurope
  options:
    servicebus_namespace_id: /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/core-rg/providers/Microsoft.ServiceBus/namespaces/core-bus
functions:
  on-price:
    handler: app.prices.on_price
    events:
      - topic: {name: price-changes, existing: true}
""", "prices", "on_price"),
      user="price-updates subscribes to an existing Service Bus topic in core-bus. I set servicebus_namespace_id, but prod validation still says existing topics need options.servicebus_namespace_id and options.servicebus_connection.",
      steps=[
          S("get_validation"),
          S("ask_user", question="The namespace is set; `servicebus_connection` is missing. It is the *name* of the app setting that holds the namespace connection string. What should it be called?",
            options=["SERVICEBUS_CONNECTION", "CORE_BUS_CONNECTION"], answer="CORE_BUS_CONNECTION"),
          S("propose_plan", steps=["Set `provider.options.servicebus_connection: CORE_BUS_CONNECTION`",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.servicebus_connection", value="CORE_BUS_CONNECTION"),
      ],
      final="""For an `existing` topic pskit needs both values: the namespace id and the app setting name for its connection string [docs/events.md#topic].

Added `servicebus_connection: CORE_BUS_CONNECTION`. `pskit validate -p azure -s prod`: valid.

The Function App must have an app setting `CORE_BUS_CONNECTION` with the connection string; pass it as `${env:CORE_BUS_CONNECTION}`, never as text in pskit.yml [docs/providers.md#azure-azure-functions]."""),

    # ------------------------------------------------------------------ 459  azure Logic Apps nesting too deep
    C(459, provider="azure", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#compiler-notes-and-limits"],
      project=proj("""service: catalog-sync
provider:
  name: azure
  region: westeurope
functions:
  sync-item:
    handler: app.catalog.sync_item
workflows:
  sync:
    engine: native
    start_at: Stores
    states:
      Stores:
        type: map
        items_path: $.stores
        iterator:
          start_at: Categories
          states:
            Categories:
              type: map
              items_path: $.categories
              iterator:
                start_at: Items
                states:
                  Items:
                    type: map
                    items_path: $.items
                    iterator:
                      start_at: Sync
                      states:
                        Sync: {type: task, function: sync-item, end: true}
                    end: true
              end: true
        end: true
""", "catalog", "sync_item"),
      user="3 nested maps in native azure workflow → error. keep structure if possible",
      steps=[
          S("get_validation"),
          S("search_docs", query="logic apps nesting map parallel",
            docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="Logic Apps allow 8 levels of nesting", end="`map` states two deep.")]),
          S("propose_plan", steps=["Set `workflows.sync.engine` to `embedded` (keeps the 3 nested maps)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.sync.engine", value="embedded"),
      ],
      final="""Logic Apps allow `map` states only two deep, and `sync` nests three [docs/workflows.md#compiler-notes-and-limits].

Set `engine: embedded`, so the structure stays as it is and pskit's orchestrator function runs it. `pskit validate -p azure`: valid. Validate warns that the whole run must fit in one function call (600 s on Azure); if a full sync takes longer, flatten one level instead and stay on Logic Apps."""),

    # ------------------------------------------------------------------ 460  azure blob deleted only -> disable on azure
    C(460, provider="azure", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#storage", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=proj("""service: cdn-purge
provider:
  name: aws
  region: us-east-1
providers:
  azure:
    region: westeurope
functions:
  site:
    handler: app.cdn.site
    events:
      - http: GET /status
  purge:
    handler: app.cdn.purge
    events:
      - storage:
          bucket: site-assets
          events: [deleted]
""", "cdn", "site", "purge"),
      user="On AWS purge runs on S3 delete notifications. For the Azure staging copy, validation fails on that trigger. Is there any way to get delete events there?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure blob delete trigger",
            docs=[D("docs/events.md", "storage", start="| azure |", end="in another account need `options.storage_connection` |")]),
          S("ask_user", question="No: Azure blob triggers fire only for created/updated blobs, so `purge` can't run on Azure. Disable `purge` on Azure only (it stays on AWS), or keep this service on AWS?",
            options=["Disable purge on Azure", "Keep the service on AWS only"],
            answer="Disable purge on Azure"),
          S("propose_plan", steps=["Add `providers.azure.functions.purge.enabled: false`",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.functions.purge.enabled", value=False),
      ],
      final="""There is no delete trigger on Azure in pskit: blob triggers fire only for created or updated blobs [docs/events.md#storage].

Added `providers.azure.functions.purge: {enabled: false}`. `pskit validate -p azure -s staging`: valid (with a warning that `purge` is disabled there). On AWS, `purge` still runs on S3 deletes [docs/configuration.md#switch-something-off-on-one-cloud]. On Azure, purge the CDN another way, e.g. from the code that deletes the blob."""),
]
