"""Category C (fix a validation error), batch 29 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 561  aws map state with function, no iterator
    C(561, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: label-printer
provider:
  name: aws
  region: us-east-1
functions:
  load-order:
    handler: app.labels.load_order
  print-label:
    handler: app.labels.print_label
workflows:
  labels:
    start_at: Load
    states:
      Load: {type: task, function: load-order, next: PrintAll}
      PrintAll:
        type: map
        items_path: $.parcels
        function: print-label
        end: true
""", "labels", "load_order", "print_label"),
      user="PrintAll should call print-label once for every parcel. I set the function on the map state but it says map state needs iterator. What's an iterator?",
      steps=[
          S("get_validation"),
          S("search_docs", query="map state iterator items_path",
            docs=[D("docs/workflows.md", "state-types", start="| `map` |", end="| `map` |")]),
          S("propose_plan", steps=["Move `function: print-label` into an `iterator` with one task state `Print`",
                                   "Keep `items_path: $.parcels` on `PrintAll`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.labels.states.PrintAll",
            value={"type": "map", "items_path": "$.parcels", "end": True,
                   "iterator": {"start_at": "Print",
                                "states": {"Print": {"type": "task", "function": "print-label", "end": True}}}}),
      ],
      final="""The iterator is the small workflow a `map` runs for each item; the function goes in a task state inside it, not on the map itself [docs/workflows.md#state-types].

`PrintAll` now has `iterator: {start_at: Print, states: {Print: {type: task, function: print-label}}}`, so each parcel in `$.parcels` is passed to `print-label`. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 562  gcp workflow timeout "1h"
    C(562, provider="gcp", stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: etl-nightly
provider:
  name: gcp
  region: us-central1
  options:
    project: etl-nightly-staging
functions:
  extract:
    handler: app.etl.extract
  load:
    handler: app.etl.load
workflows:
  nightly:
    timeout: 1h
    start_at: Extract
    states:
      Extract: {type: task, function: extract, next: Load}
      Load: {type: task, function: load, end: true}
""", "etl", "extract", "load"),
      user="workflows.nightly.timeout: unable to parse string as an integer. it's 1h",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.nightly.timeout` to 3600", "Validate for gcp, stage staging"]),
          S("set_config", path="workflows.nightly.timeout", value=3600),
      ],
      final="""Workflow `timeout` is a number of seconds, so `1h` doesn't parse [docs/workflows.md#workflow-keys].

Set `timeout: 3600`. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 563  azure backoff_rate 0.5
    C(563, provider="azure", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#retry-and-catch"],
      project=proj("""service: geo-enrich
provider:
  name: azure
  region: westeurope
functions:
  geocode:
    handler: app.geo.geocode
  save:
    handler: app.geo.save
workflows:
  enrich:
    start_at: Geocode
    states:
      Geocode:
        type: task
        function: geocode
        retry:
          - errors: [TimeoutError]
            max_attempts: 4
            interval_seconds: 8
            backoff_rate: 0.5
        next: Save
      Save: {type: task, function: save, end: true}
""", "geo", "geocode", "save"),
      user="The geocoding API is slow at first and then recovers, so I wanted the retries to get shorter: 8 s, 4 s, 2 s, 1 s. I put backoff_rate 0.5 and validation says it must be greater than or equal to 1.",
      steps=[
          S("get_validation"),
          S("search_docs", query="retry backoff_rate interval",
            docs=[D("docs/workflows.md", "retry-and-catch", end="Error names are")]),
          S("ask_user", question="Retries can only stay the same or get longer. Should I use a fixed 2 s between tries (`interval_seconds: 2`, `backoff_rate: 1`), or keep 8 s and stop shrinking it?",
            options=["fixed 2 s", "fixed 8 s"], answer="fixed 2 s"),
          S("propose_plan", steps=["Set the `Geocode` retry to `interval_seconds: 2`, `backoff_rate: 1` (max_attempts stays 4)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.enrich.states.Geocode.retry.0",
            value={"errors": ["TimeoutError"], "max_attempts": 4, "interval_seconds": 2, "backoff_rate": 1}),
      ],
      final="""`backoff_rate` multiplies the wait after each try, and pskit needs it to be at least 1, so waits can't shrink [docs/workflows.md#retry-and-catch].

The retry is now 4 tries, 2 s apart (`backoff_rate: 1`). Validate for azure: valid, with one warning: the workflow runs on the embedded engine, so its total time is capped by the function timeout (600 s max)."""),

    # ------------------------------------------------------------------ 564  gcp provider memory 40960
    C(564, provider="gcp", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: ml-scoring
provider:
  name: gcp
  region: us-central1
  memory: 40960
  options:
    project: ml-scoring-dev
functions:
  score:
    handler: app.model.score
    events:
      - http: POST /score
""", "model", "score"),
      user="model is big, i put memory 40960 (40 GB) but say less than or equal 32768. how i get more",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.memory` to 32768 (the pskit maximum)", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.memory", value=32768),
      ],
      final="""pskit accepts memory from 64 to 32768 MB, so 40960 is over the limit [docs/configuration.md#provider].

Set `memory: 32768` (32 GB), the most pskit allows. Validate for gcp: valid. If the model still doesn't fit, try a smaller model file or load it in parts."""),

    # ------------------------------------------------------------------ 565  aws terraform.required_version number
    C(565, provider="aws", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#terraform"],
      project=proj("""service: dns-sync
provider:
  name: aws
  region: us-east-1
  terraform:
    required_version: 1.6
functions:
  sync:
    handler: app.dns.sync
    events:
      - schedule: 15 minutes
""", "dns", "sync"),
      user="provider.terraform.required_version: Input should be a valid string. pin tf >= 1.6",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.terraform.required_version` to the string `>= 1.6.0`", "Validate for aws"]),
          S("set_config", path="provider.terraform.required_version", value=">= 1.6.0"),
      ],
      final="""`required_version` is a Terraform version constraint string (default `>= 1.5.0`); YAML read `1.6` as a number [docs/configuration.md#terraform].

Set `required_version: ">= 1.6.0"`. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 566  azure connection key 'name' reserved
    C(566, provider="azure", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#fields"],
      project=proj("""service: crm-sync
provider:
  name: azure
  region: westeurope
resources:
  crm-db:
    type: database
    external: true
    connection:
      host: crm-db.example.com
      port: 5432
      name: crm
      user: crm_sync
      password: ${env:CRM_DB_PASSWORD, ""}
functions:
  sync:
    handler: app.crm.sync
    events:
      - schedule: 1 hour
""", "crm", "sync"),
      user="The Postgres database is called crm, so I put `name: crm` in the connection of crm-db. Staging validation: connection key 'name' is reserved (set `name` on the resource itself). But it's the DB name, not the resource name.",
      steps=[
          S("get_validation"),
          S("search_docs", query="resource connection reserved keys",
            docs=[D("docs/resources.md", "fields", start="| `connection` |", end="| `connection` |")]),
          S("propose_plan", steps=["Rename the connection key `name` to `database` (value `crm`) on `crm-db`",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.crm-db.connection.name", value=None),
          S("set_config", path="resources.crm-db.connection.database", value="crm"),
      ],
      final="""`type`, `name` and `external` are reserved in `connection`, because `name` already means the resource's own native name [docs/resources.md#fields].

The key is now `database: crm`; the other values are unchanged and the password still comes from `${env:CRM_DB_PASSWORD}`. In the handler read `PSKIT_RESOURCE_CRM_DB_DATABASE`. `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 567  gcp connection Host/host
    C(567, provider="gcp", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=["docs/resources.md#fields"],
      project=proj("""service: quote-engine
provider:
  name: gcp
  region: europe-west1
  options:
    project: quote-engine-dev
resources:
  pricing-cache:
    type: cache
    external: true
    connection:
      Host: 192.0.2.12
      host: pricing-cache.internal.example.com
      port: 6379
functions:
  quote:
    handler: app.quotes.quote
    events:
      - http: POST /quote
""", "quotes", "quote"),
      user="""Error: pskit.yml is invalid:
  - resources.pricing-cache.connection: Value error, connection keys must be unique ignoring case

merged two .env files into this, no idea which one""",
      steps=[
          S("get_validation"),
          S("ask_user", question="`pricing-cache` has both `Host: 192.0.2.12` and `host: pricing-cache.internal.example.com`; handlers would see both as `PSKIT_RESOURCE_PRICING_CACHE_HOST`. Which one is the real cache?",
            options=["192.0.2.12", "pricing-cache.internal.example.com"], answer="pricing-cache.internal.example.com"),
          S("propose_plan", steps=["Remove `Host: 192.0.2.12` from `pricing-cache.connection`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.pricing-cache.connection.Host", value=None),
      ],
      final="""Connection keys become upper-case variable names, so `Host` and `host` would collide; they must be unique ignoring case [docs/resources.md#fields].

Kept `host: pricing-cache.internal.example.com` and removed `Host`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 568  gcp multi-cloud: jwt only on aws
    C(568, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/configuration.md#switch-something-off-on-one-cloud", "docs/events.md#http"],
      project=proj("""service: orders-api
provider:
  name: aws
  region: us-east-1
providers:
  gcp:
    region: europe-west1
    options:
      project: orders-api-dev
functions:
  orders:
    handler: app.orders.list_orders
    events:
      - http:
          path: /orders
          method: GET
          auth: jwt
          authorizer:
            issuer: https://id.example.com/
            audience: [orders-api]
""", "orders", "list_orders"),
      user="orders-api runs on AWS with a JWT authorizer. We also want a GCP copy. When I pick gcp in the top bar, validate fails with http auth 'jwt' is not supported on GCP. AWS must keep JWT.",
      steps=[
          S("get_validation"),
          S("search_docs", query="per provider override events auth",
            docs=[D("docs/configuration.md", "switch-something-off-on-one-cloud", end="Disabled functions and workflows")]),
          S("ask_user", question="On GCP the route can be `iam` (callers need Google credentials) or `none` (public; your handler checks the token). Which one for the GCP copy?",
            options=["iam", "none, check the JWT in the handler"], answer="iam"),
          S("propose_plan", steps=["Add `providers.gcp.functions.orders.events: [{http: {path: /orders, method: GET, auth: iam}}]`",
                                   "Leave the AWS jwt event as it is",
                                   "Validate for gcp, then for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.gcp.functions",
            value={"orders": {"events": [{"http": {"path": "/orders", "method": "GET", "auth": "iam"}}]}}),
          S("validate", provider="aws"),
      ],
      final="""GCP has no JWT authorizer, so `auth: jwt` can only stay on AWS. A `providers.gcp` block can give the function a different trigger list on GCP (lists replace) [docs/configuration.md#switch-something-off-on-one-cloud].

- `providers.gcp.functions.orders.events`: `GET /orders` with `auth: iam`
- the main config keeps `auth: jwt` for AWS

Validate: valid for gcp and for aws."""),

    # ------------------------------------------------------------------ 569  gcp added queue trigger to long http function
    C(569, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: report-export
provider:
  name: gcp
  region: europe-west1
  options:
    project: report-export-dev
functions:
  export:
    handler: app.export.run
    timeout: 900
    events:
      - http: POST /export
      - queue: export-requests
""", "export", "run"),
      user="export worked fine as an HTTP function with timeout 900 (big exports). I just added a queue trigger export-requests so other services can request exports, and now: event-triggered functions are limited to 540s on GCP. The HTTP route still needs 900.",
      steps=[
          S("get_validation"),
          S("ask_user", question="On GCP the 540 s limit applies once a function has an event trigger. I can (a) lower `export` to 540 s, or (b) keep `export` HTTP-only at 900 s and add a second function `export-queued` (same handler, queue trigger, 540 s). Which one?",
            options=["a: 540 s for everything", "b: separate function for the queue"], answer="b"),
          S("propose_plan", steps=["Remove the queue trigger from `export` (HTTP only, timeout 900)",
                                   "Add `export-queued` with handler `app.export.run`, timeout 540 and `queue: export-requests`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.export.events", value=[{"http": "POST /export"}]),
          S("set_config", path="functions.export-queued",
            value={"handler": "app.export.run", "timeout": 540, "events": [{"queue": "export-requests"}]}),
      ],
      final="""GCP limits event-triggered functions to 540 s, and the new queue trigger made `export` one of them [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

- `export`: `POST /export`, timeout 900
- `export-queued`: same handler, `queue: export-requests`, timeout 540

Validate for gcp: valid. The handler can tell them apart with `event.type` (`"http"` or `"queue"`)."""),

    # ------------------------------------------------------------------ 570  aws timeout_seconds "30s"
    C(570, provider="aws", stage="prod", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: kyc-check
provider:
  name: aws
  region: eu-west-1
functions:
  verify-id:
    handler: app.kyc.verify_id
  approve:
    handler: app.kyc.approve
workflows:
  kyc:
    start_at: VerifyId
    states:
      VerifyId:
        type: task
        function: verify-id
        timeout_seconds: 30s
        next: Approve
      Approve: {type: task, function: approve, end: true}
""", "kyc", "verify_id", "approve"),
      user="""prod:
Error: pskit.yml is invalid:
  - workflows.kyc.states.VerifyId.timeout_seconds: Input should be a valid integer, unable to parse string as an integer""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `timeout_seconds` of `VerifyId` to 30", "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.kyc.states.VerifyId.timeout_seconds", value=30),
      ],
      final="""`timeout_seconds` on a task state is a plain number of seconds [docs/workflows.md#state-types].

Set `timeout_seconds: 30` on `VerifyId`. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 571  aws function tag number
    C(571, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: fleet-tracker
provider:
  name: aws
  region: us-west-2
functions:
  positions:
    handler: app.fleet.positions
    tags:
      team: logistics
      cost-center: 4711
    events:
      - http: POST /positions
""", "fleet", "positions"),
      user="Same tags as in our CloudFormation (cost-center 4711). pskit: functions.positions.tags.cost-center: Input should be a valid string.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Quote the tag value: `cost-center: \"4711\"`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.positions.tags.cost-center", value="4711"),
      ],
      final="""Tags are a map of strings, and YAML reads an unquoted `4711` as a number [docs/configuration.md#functions].

Now `cost-center: "4711"`; `team: logistics` stays. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 572  azure blob deleted -> disable -> workflow
    C(572, provider="azure", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/configuration.md#switch-something-off-on-one-cloud", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: doc-archive
provider:
  name: aws
  region: us-east-1
providers:
  azure:
    region: westeurope
functions:
  on-delete:
    handler: app.archive.on_delete
    events:
      - storage: {bucket: archive-docs, events: [deleted]}
  purge-index:
    handler: app.archive.purge_index
workflows:
  cleanup:
    start_at: Purge
    states:
      Purge: {type: task, function: on-delete, next: Index}
      Index: {type: task, function: purge-index, end: true}
""", "archive", "on_delete", "purge_index"),
      user="doc-archive is on AWS and we're testing Azure as a second target. With azure selected: Azure blob triggers only fire on created/updated blobs. We don't need delete handling on Azure for now. Don't touch the AWS setup.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Add `providers.azure.functions.on-delete: {enabled: false}` (AWS keeps it)", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.functions", value={"on-delete": {"enabled": False}}),
          S("propose_plan", say="That revealed the next problem: the `cleanup` workflow calls `on-delete`, which is now off on Azure.",
            steps=["Add `providers.azure.workflows.cleanup: {enabled: false}`", "Validate for azure, then for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.workflows", value={"cleanup": {"enabled": False}}),
          S("validate", provider="aws"),
      ],
      final="""Azure blob triggers don't fire on deletes, so `on-delete` can't run there; and a workflow that calls a disabled function must be disabled too [docs/configuration.md#switch-something-off-on-one-cloud].

- `providers.azure.functions.on-delete: {enabled: false}`
- `providers.azure.workflows.cleanup: {enabled: false}`

Azure: valid (both reported as disabled warnings). AWS: valid and unchanged."""),

    # ------------------------------------------------------------------ 573  aws prod-only unset env var
    C(573, provider="aws", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: menu-board
provider:
  name: aws
  region: us-east-1
stages:
  prod:
    provider:
      region: ${env:PROD_REGION}
functions:
  menu:
    handler: app.menu.get_menu
    events:
      - http: GET /menu
""", "menu", "get_menu"),
      user="Validate works on dev but when I switch the stage to prod it says unresolved variables: env:PROD_REGION. I don't know where that variable should come from.",
      steps=[
          S("get_validation"),
          S("search_docs", query="env variable default",
            docs=[D("docs/configuration.md", "variables", end="| `${env:NAME, default}` |")]),
          S("ask_user", question="Only the prod stage reads `PROD_REGION`, and it isn't set here. Which AWS region should prod use when the variable is missing?",
            options=["us-east-1", "eu-west-1", "other"], answer="eu-west-1"),
          S("propose_plan", steps=["Set `stages.prod.provider.region` to `${env:PROD_REGION, eu-west-1}`", "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.provider.region", value="${env:PROD_REGION, eu-west-1}"),
      ],
      final="""`${env:PROD_REGION}` is only used by the prod override, and without a default it is an error when the variable isn't set [docs/configuration.md#variables].

Now `region: ${env:PROD_REGION, eu-west-1}`: prod uses eu-west-1 unless `PROD_REGION` is set. `pskit validate -p aws -s prod`: valid (region eu-west-1)."""),

    # ------------------------------------------------------------------ 574  aws prod override duplicates a route, plan rejected
    C(574, provider="aws", stage="prod", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http", "docs/configuration.md#stages-per-stage-overrides"],
      project=proj("""service: warehouse-api
provider:
  name: aws
  region: eu-central-1
stages:
  prod:
    functions:
      admin:
        events:
          - http: GET /admin
          - http: GET /health
functions:
  api:
    handler: app.wh.api
    events:
      - http: GET /health
      - http: GET /stock
  admin:
    handler: app.wh.admin
    events:
      - http: GET /admin
""", "wh", "api", "admin"),
      user="prod only: route GET /health is used by both 'api' and 'admin'",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `GET /health` from the prod override of `admin` (api keeps `/health`)",
                                   "Validate for aws, stage prod"],
            result={"decision": "rejected", "note": "No. In prod admin needs its own health check. Put it on /admin/health."}),
          S("propose_plan", say="Understood, I'll keep a health route for admin on its own path.",
            steps=["Change the prod override of `admin` to `GET /admin` and `GET /admin/health`",
                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.functions.admin.events",
            value=[{"http": "GET /admin"}, {"http": "GET /admin/health"}]),
      ],
      final="""The prod override gave `admin` the same `GET /health` that `api` already has, and a method + path can belong to only one function [docs/events.md#http].

As you asked, prod `admin` now has `GET /admin` and `GET /admin/health`; `api` keeps `/health`. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 575  azure external topic resource needs servicebus options
    C(575, provider="azure", stage="staging", mode="ask", page="Resources", persona="aws_migrator",
      sources=["docs/providers.md#azure-azure-functions"],
      project=proj("""service: shop-notify
provider:
  name: azure
  region: westeurope
resources:
  shop-events:
    type: topic
    external: true
    name: shop-events
functions:
  notify:
    handler: app.events.notify
    events:
      - topic: {resource: shop-events}
""", "events", "notify"),
      user="On AWS an external SNS topic just needed its name. On Azure staging: existing topics need options.servicebus_namespace_id and options.servicebus_connection. The topic lives in our shared Service Bus.",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure existing topic servicebus options",
            docs=[D("docs/providers.md", "azure-azure-functions", start="```yaml", end="servicebus_connection: SB_CONNECTION")]),
          S("ask_user", question="I need two values: the resource id of the shared Service Bus namespace (`/subscriptions/.../namespaces/<name>`) and the name of the app setting that will hold its connection string. What are they?",
            answer="/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/shared-rg/providers/Microsoft.ServiceBus/namespaces/shared-bus, setting SHARED_BUS_CONNECTION"),
          S("propose_plan", steps=["Set `provider.options.servicebus_namespace_id` to the shared-bus id",
                                   "Set `provider.options.servicebus_connection: SHARED_BUS_CONNECTION`",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.servicebus_namespace_id",
            value="/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/shared-rg/providers/Microsoft.ServiceBus/namespaces/shared-bus"),
          S("set_config", path="provider.options.servicebus_connection", value="SHARED_BUS_CONNECTION"),
      ],
      final="""An external topic on Azure is a topic in an existing Service Bus namespace, and pskit needs that namespace's id plus the app setting with its connection string [docs/providers.md#azure-azure-functions].

- `servicebus_namespace_id`: the `shared-bus` namespace id
- `servicebus_connection: SHARED_BUS_CONNECTION`

`pskit validate -p azure -s staging`: valid. The Function App needs a `SHARED_BUS_CONNECTION` setting holding the connection string; keep that string out of pskit.yml."""),

    # ------------------------------------------------------------------ 576  gcp renamed function, workflow still uses old name
    C(576, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: card-payments
provider:
  name: gcp
  region: europe-west1
  options:
    project: card-payments-dev
functions:
  charge-card:
    handler: app.pay.charge
  send-receipt:
    handler: app.pay.receipt
workflows:
  checkout:
    start_at: Charge
    states:
      Charge: {type: task, function: charge, next: Receipt}
      Receipt: {type: task, function: send-receipt, end: true}
""", "pay", "charge", "receipt"),
      user="i rename function charge to charge-card with Rename button, now workflow 'checkout' references unknown function 'charge'",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `function` of the `Charge` state to `charge-card`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.checkout.states.Charge.function", value="charge-card"),
      ],
      final="""The rename changed the function, but the `Charge` state still pointed at the old name, and every task `function` must exist under `functions` [docs/workflows.md#workflow-keys].

`Charge` now calls `charge-card`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 577  azure python3.13 after adding azure target
    C(577, provider="azure", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=proj("""service: price-watch
provider:
  name: aws
  region: us-east-1
  runtime: python3.13
providers:
  azure:
    region: westeurope
functions:
  watch:
    handler: app.prices.watch
    events:
      - schedule: 30 minutes
""", "prices", "watch"),
      user="price-watch runs on python3.13 on AWS. Adding Azure as a target fails: Azure Functions does not support python3.13. Can AWS stay on 3.13?",
      steps=[
          S("get_validation"),
          S("search_docs", query="per provider override runtime",
            docs=[D("docs/configuration.md", "providers-per-cloud-overrides", start="The block for the active provider")]),
          S("propose_plan", steps=["Add `runtime: python3.12` to the `providers.azure` block (AWS keeps python3.13)",
                                   "Validate for azure, then for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.runtime", value="python3.12"),
          S("validate", provider="aws"),
      ],
      final="""Yes. Azure Functions doesn't offer python3.13, and `runtime` can be set per cloud inside `providers.azure` [docs/configuration.md#providers-per-cloud-overrides].

Added `providers.azure.runtime: python3.12`. Azure: valid. AWS: valid, still on python3.13. Keep the handler free of 3.13-only features so it runs on both."""),

    # ------------------------------------------------------------------ 578  aws artifact_upload S3 uppercase
    C(578, provider="aws", stage="staging", mode="auto", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#aws-aws-lambda"],
      project=proj("""service: big-deps
provider:
  name: aws
  region: us-east-1
  options:
    artifact_upload: S3
functions:
  render:
    handler: app.render.page
    events:
      - http: GET /render
""", "render", "page"),
      user="""[provider.options.artifact_upload] artifact_upload must be 's3' or 'direct'

it IS S3??""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.artifact_upload` to lowercase `s3`", "Validate for aws, stage staging"]),
          S("set_config", path="provider.options.artifact_upload", value="s3"),
      ],
      final="""The value is case-sensitive: pskit accepts only lowercase `s3` or `direct`.

Set `artifact_upload: s3`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 579  gcp catch with `then`
    C(579, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#retry-and-catch"],
      project=proj("""service: lead-intake
provider:
  name: gcp
  region: us-east1
  options:
    project: lead-intake-dev
functions:
  enrich:
    handler: app.leads.enrich
  notify-sales:
    handler: app.leads.notify
  log-failure:
    handler: app.leads.log_failure
workflows:
  intake:
    start_at: Enrich
    states:
      Enrich:
        type: task
        function: enrich
        next: Notify
        catch:
          - errors: ["*"]
            then: LogFailure
      Notify: {type: task, function: notify-sales, end: true}
      LogFailure: {type: task, function: log-failure, end: true}
""", "leads", "enrich", "notify", "log_failure"),
      user="If Enrich fails it should go to LogFailure. The state editor calls it \"Then\" so I wrote then: LogFailure in the catch. Now: catch.0.next Field required.",
      steps=[
          S("get_validation"),
          S("search_docs", query="catch next errors",
            docs=[D("docs/workflows.md", "retry-and-catch", start="catch:", end="Error names are")]),
          S("propose_plan", steps=["In the catch of `Enrich`, replace `then: LogFailure` with `next: LogFailure`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.intake.states.Enrich.catch",
            value=[{"errors": ["*"], "next": "LogFailure"}]),
      ],
      final="""In pskit.yml the target of a catch is written `next` ("Then" is only the label in the editor) [docs/workflows.md#retry-and-catch].

The catch is now `{errors: ["*"], next: LogFailure}`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 580  azure map iterator as a list
    C(580, provider="azure", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: bulk-mailer
provider:
  name: azure
  region: northeurope
functions:
  load-list:
    handler: app.mail.load_list
  send-one:
    handler: app.mail.send_one
workflows:
  campaign:
    start_at: Load
    states:
      Load: {type: task, function: load-list, next: SendAll}
      SendAll:
        type: map
        items_path: $.recipients
        iterator:
          - {type: task, function: send-one}
""", "mail", "load_list", "send_one"),
      user="iterator: Input should be a valid dictionary or instance of WorkflowDefinition. i give list of step, why wrong",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Make the iterator a small workflow: `{start_at: Send, states: {Send: {type: task, function: send-one}}}`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.campaign.states.SendAll.iterator",
            value={"start_at": "Send", "states": {"Send": {"type": "task", "function": "send-one", "end": True}}}),
      ],
      final="""An `iterator` is not a list of steps; it is a workflow with `start_at` and named `states` [docs/workflows.md#state-types].

It is now `{start_at: Send, states: {Send: {type: task, function: send-one}}}`, so `send-one` runs for each item of `$.recipients`. Validate for azure: valid (one warning: on the embedded engine the whole run must fit in the function timeout, 600 s max)."""),
]

