"""Category C (fix a validation error), batch 30 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 581  aws top-level region with provider shorthand
    C(581, provider="aws", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#top-level", "docs/configuration.md#provider"],
      project=proj("""service: recipe-box
provider: aws
region: eu-west-1
functions:
  recipes:
    handler: app.recipes.list_recipes
    events:
      - http: GET /recipes
""", "recipes", "list_recipes"),
      user="I wrote `provider: aws` like the docs say and then `region: eu-west-1` below it. Now it says region: Extra inputs are not permitted. Where does the region go?",
      steps=[
          S("get_validation"),
          S("search_docs", query="provider shorthand region",
            docs=[D("docs/configuration.md", "top-level", end="| `provider` |")]),
          S("propose_plan", steps=["Replace `provider: aws` + top-level `region` with `provider: {name: aws, region: eu-west-1}`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="region", value=None),
          S("set_config", path="provider", value={"name": "aws", "region": "eu-west-1"}),
      ],
      final="""`provider: aws` is only a shorthand for `provider: {name: aws}`; `region` belongs inside `provider`, not at the top level [docs/configuration.md#top-level].

Now:
```yaml
provider:
  name: aws
  region: eu-west-1
```
Validate for aws: valid (region eu-west-1)."""),

    # ------------------------------------------------------------------ 582  aws functions as a list
    C(582, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: survey-api
provider:
  name: aws
  region: us-east-1
functions:
  - name: submit
    handler: app.survey.submit
    events:
      - http: POST /answers
  - name: results
    handler: app.survey.results
    events:
      - http: GET /results
""", "survey", "submit", "results"),
      user="I converted our SAM template by hand and wrote functions as a list with name: fields. pskit: functions: Input should be a valid dictionary.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Turn `functions` into a map keyed by name: `submit` and `results` (handlers and routes unchanged)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions",
            value={"submit": {"handler": "app.survey.submit", "events": [{"http": "POST /answers"}]},
                   "results": {"handler": "app.survey.results", "events": [{"http": "GET /results"}]}}),
      ],
      final="""`functions` is a map from function name to its settings, not a list with `name:` fields [docs/configuration.md#functions].

Now `functions: {submit: {...}, results: {...}}` with the same handlers and routes. Validate for aws: valid, 2 functions."""),

    # ------------------------------------------------------------------ 583  aws memorySize / reservedConcurrency
    C(583, provider="aws", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: thumbs
provider:
  name: aws
  region: us-east-1
functions:
  make-thumb:
    handler: app.thumbs.make
    memorySize: 1024
    reservedConcurrency: 5
    events:
      - storage: thumbs-originals
""", "thumbs", "make"),
      user="memorySize + reservedConcurrency → extra inputs. map them",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`memorySize: 1024` → `memory: 1024`", "`reservedConcurrency: 5` → `concurrency: 5`",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="functions.make-thumb.memorySize", value=None),
          S("set_config", path="functions.make-thumb.reservedConcurrency", value=None),
          S("set_config", path="functions.make-thumb.memory", value=1024),
          S("set_config", path="functions.make-thumb.concurrency", value=5),
      ],
      final="""Those are Serverless Framework names; pskit uses `memory` and `concurrency` (reserved concurrency on AWS) [docs/configuration.md#functions].

`make-thumb`: `memory: 1024`, `concurrency: 5`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 584  aws layers -> options escape hatch
    C(584, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#escape-hatches"],
      project=proj("""service: pdf-render
provider:
  name: aws
  region: us-east-1
functions:
  render:
    handler: app.pdf.render
    layers:
      - arn:aws:lambda:us-east-1:123456789012:layer:wkhtmltopdf:4
    events:
      - http: POST /render
""", "pdf", "render"),
      user="render needs our wkhtmltopdf Lambda layer (arn:aws:lambda:us-east-1:123456789012:layer:wkhtmltopdf:4). `layers:` on the function gives Extra inputs are not permitted. Is there no way to attach a layer?",
      steps=[
          S("get_validation"),
          S("search_docs", query="lambda layers vpc option not modelled",
            docs=[D("docs/configuration.md", "escape-hatches", end="| Reference those resources |")]),
          S("propose_plan", steps=["Move the layer to `functions.render.options.layers` (merged into `aws_lambda_function`)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.render.layers", value=None),
          S("set_config", path="functions.render.options",
            value={"layers": ["arn:aws:lambda:us-east-1:123456789012:layer:wkhtmltopdf:4"]}),
      ],
      final="""pskit has no `layers` key, but `functions.<fn>.options` is merged into the provider's function resource, for AWS `aws_lambda_function`, which is meant for things like layers and VPC [docs/configuration.md#escape-hatches].

`render` now has `options: {layers: [arn:aws:lambda:us-east-1:123456789012:layer:wkhtmltopdf:4]}`. Validate for aws: valid. Validate doesn't check the ARN itself; `pskit plan -s dev` shows it on the Lambda before you deploy."""),

    # ------------------------------------------------------------------ 585  aws @daily
    C(585, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=proj("""service: backup-notes
provider:
  name: aws
  region: ap-south-1
functions:
  backup:
    handler: app.backup.run
    events:
      - schedule: "@daily"
""", "backup", "run"),
      user="in linux crontab @daily work. here say cron must be 5-field. how write daily",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the schedule of `backup` to `1 day` (same as @daily, runs once a day)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": "make it at midnight exactly please"}),
          S("set_config", path="functions.backup.events.0", value={"schedule": "0 0 * * *"}),
      ],
      final="""pskit takes a rate (`1 day`) or a normal 5-field cron; crontab shortcuts like `@daily` are not accepted [docs/events.md#schedule].

As you asked, midnight exactly: `- schedule: "0 0 * * *"` (00:00 UTC every day). Validate for aws: valid."""),

    # ------------------------------------------------------------------ 586  aws rate 0.5 hours
    C(586, provider="aws", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=proj("""service: price-cache
provider:
  name: aws
  region: eu-west-1
functions:
  refresh:
    handler: app.cache.refresh
    events:
      - schedule:
          rate: 0.5 hours
""", "cache", "refresh"),
      user="""Error: pskit.yml is invalid:
  - functions.refresh.events.0: Value error, rate must look like '<n> minutes|hours|days'

(prod) half an hour""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the rate of `refresh` to `30 minutes`", "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.refresh.events.0.schedule.rate", value="30 minutes"),
      ],
      final="""The number in a rate must be a whole number, so half an hour is `30 minutes` [docs/events.md#schedule].

Set `rate: 30 minutes` (EventBridge `rate(30 minutes)`). `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 587  aws jwt with terraform-style keys
    C(587, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=proj("""service: tenant-admin
provider:
  name: aws
  region: us-east-1
functions:
  tenants:
    handler: app.tenants.list_tenants
    events:
      - http:
          path: /tenants
          method: GET
          auth: jwt
          authorizer:
            issuer_url: https://login.example.com/
            audiences: [tenant-admin]
""", "tenants", "list_tenants"),
      user="I copied the authorizer from our Terraform (issuer_url, audiences). Validation still says jwt auth needs authorizer.issuer and authorizer.audience, but both are there?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `issuer_url` → `issuer` and `audiences` → `audience` in the authorizer of `/tenants`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.tenants.events.0.http.authorizer",
            value={"issuer": "https://login.example.com/", "audience": ["tenant-admin"]}),
      ],
      final="""pskit's authorizer keys are `issuer` and `audience`; `issuer_url`/`audiences` are the Terraform argument names, so pskit didn't find them [docs/events.md#http].

Now `authorizer: {issuer: https://login.example.com/, audience: [tenant-admin]}`. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 588  gcp serverless google plugin function
    C(588, provider="gcp", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#functions", "docs/events.md#topic"],
      project=proj("""service: order-events
provider:
  name: gcp
  region: europe-west1
  options:
    project: order-events-dev
functions:
  on-order:
    handler: app.orders.on_order
    memorySize: 512
    timeout: 60s
    events:
      - event:
          eventType: providers/cloud.pubsub/eventTypes/topic.publish
          resource: projects/order-events-dev/topics/orders
""", "orders", "on_order"),
      user="This came from serverless-google-cloudfunctions. pskit lists three errors for on-order (timeout, unknown event type 'event', memorySize). The topic `orders` already exists in the project.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`memorySize: 512` → `memory: 512`", "`timeout: 60s` → `timeout: 60`",
                                   "Replace the `event` trigger with `topic: {name: orders, existing: true}`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.on-order",
            value={"handler": "app.orders.on_order", "memory": 512, "timeout": 60,
                   "events": [{"topic": {"name": "orders", "existing": True}}]}),
      ],
      final="""All three are plugin syntax: pskit uses `memory`, a timeout in plain seconds, and a portable `topic` trigger instead of `eventType`/`resource` [docs/configuration.md#functions].

`on-order` now: `memory: 512`, `timeout: 60`, `topic: {name: orders, existing: true}` (pskit subscribes but doesn't create the topic) [docs/events.md#topic]. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 589  gcp prod-only memory override
    C(589, provider="gcp", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/configuration.md#stages-per-stage-overrides", "docs/configuration.md#provider"],
      project=proj("""service: search-index
provider:
  name: gcp
  region: us-central1
  memory: 2048
  options:
    project: search-index-prod
stages:
  prod:
    provider:
      memory: 65536
functions:
  query:
    handler: app.search.query
    events:
      - http: GET /search
""", "search", "query"),
      user="""Deploy page, stage prod, Validate:
Error: pskit.yml is invalid:
  - provider.memory: Input should be less than or equal to 32768

dev is fine with 2048""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `stages.prod.provider.memory` to 32768 (the maximum)", "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.provider.memory", value=32768),
      ],
      final="""The 65536 comes from `stages.prod`, so only prod breaks; pskit allows 64-32768 MB [docs/configuration.md#provider].

Prod now uses `memory: 32768`; dev keeps 2048. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 590  gcp cors credentials
    C(590, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=proj("""service: account-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: account-api-dev
functions:
  me:
    handler: app.account.me
    events:
      - http:
          path: /me
          method: GET
          cors:
            origins: ["https://app.example.com"]
            credentials: true
""", "account", "me"),
      user="My web app sends cookies, so I added credentials: true to CORS. Now there are two errors: cors.bool should be a valid boolean and CorsConfig.credentials extra inputs. I'm confused.",
      steps=[
          S("get_validation"),
          S("search_docs", query="cors allow credentials",
            docs=[D("docs/events.md", "http", start="**CORS**", end="max_age: 600")]),
          S("propose_plan", steps=["Rename `credentials` to `allow_credentials` in the CORS of `/me` (origins stay)", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.me.events.0.http.cors",
            value={"origins": ["https://app.example.com"], "allow_credentials": True}),
      ],
      final="""It's one mistake: the key is `allow_credentials`, not `credentials`. Because `cors` can be `true` or a mapping, pskit reports both forms failing [docs/events.md#http].

Now `cors: {origins: ["https://app.example.com"], allow_credentials: true}`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 591  gcp service name too long
    C(591, provider="gcp", stage="staging", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#top-level", "docs/configuration.md#functions"],
      project=proj("""service: acme-payments-reconciliation-service
provider:
  name: gcp
  region: europe-west1
  options:
    project: acme-recon-staging
functions:
  reconcile:
    handler: app.recon.reconcile
    events:
      - schedule: "0 2 * * *"
""", "recon", "reconcile"),
      user="Our naming policy says <company>-<team>-<purpose>-service, so I named it acme-payments-reconciliation-service. Validation: service must be 2-32 chars of lowercase letters, digits and dashes. It's all lowercase!",
      steps=[
          S("get_validation"),
          S("ask_user", question="The name is 36 characters; the limit is 32 (it ends up in every cloud resource name). Which shorter name should I use?",
            options=["acme-payments-recon", "acme-pay-reconciliation", "other"], answer="acme-payments-recon"),
          S("propose_plan", steps=["Set `service` to `acme-payments-recon`", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="service", value="acme-payments-recon"),
      ],
      final="""Lowercase was fine; the name was too long, 36 characters for a limit of 32 [docs/configuration.md#top-level].

`service: acme-payments-recon`. `pskit validate -p gcp -s staging`: valid. Functions will be named like `acme-payments-recon-staging-reconcile` [docs/configuration.md#functions]. Renaming the service changes these names, so a copy already deployed under the old name stays until you remove it."""),

    # ------------------------------------------------------------------ 592  gcp after moving from azure: auth key
    C(592, provider="gcp", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: device-ping
provider:
  name: gcp
  region: us-east1
  options:
    project: device-ping-dev
functions:
  ping:
    handler: app.devices.ping
    events:
      - http:
          path: /ping
          method: POST
          auth: key
""", "devices", "ping"),
      user="before on azure we use function key for devices. now switch gcp: http auth 'key' is not supported on GCP. devices can't do google login",
      steps=[
          S("get_validation"),
          S("search_docs", query="auth key gcp alternatives",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", question="GCP allows only `none` or `iam`, and `iam` needs Google credentials. For devices the usual way is `auth: none` plus a secret header that your handler checks (secret in `${env:DEVICE_TOKEN}`). OK?",
            options=["yes, none + header check", "no, use iam"], answer="yes, none + header check"),
          S("propose_plan", steps=["Set `auth: none` on `/ping`",
                                   "Add `environment: {DEVICE_TOKEN: ${env:DEVICE_TOKEN, \"\"}}` to `ping` so the handler can compare",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ping.events.0.http.auth", value="none"),
          S("set_config", path="functions.ping.environment", value={"DEVICE_TOKEN": "${env:DEVICE_TOKEN, \"\"}"}),
      ],
      final="""GCP has no function keys; pskit supports only `none` or `iam` there [docs/events.md#http].

- `/ping`: `auth: none`
- `ping` gets `DEVICE_TOKEN` from `${env:DEVICE_TOKEN}` (never written in pskit.yml)

Validate for gcp: valid. Next step in code: reject requests whose header (e.g. `X-Device-Token` in `event.http.headers`) doesn't match `os.environ["DEVICE_TOKEN"]`, and set `DEVICE_TOKEN` before you deploy."""),

    # ------------------------------------------------------------------ 593  gcp rate 1.5 hours
    C(593, provider="gcp", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=proj("""service: feed-poller
provider:
  name: gcp
  region: europe-west1
  options:
    project: feed-poller-dev
functions:
  poll:
    handler: app.feeds.poll
    events:
      - schedule: 1.5 hours
""", "feeds", "poll"),
      user="schedule 1.5 hours rejected, cron 5-field msg. want every 90 min",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the schedule of `poll` to `90 minutes`", "Validate for gcp"]),
          S("set_config", path="functions.poll.events.0", value={"schedule": "90 minutes"}),
      ],
      final="""A rate needs a whole number, so `1.5 hours` didn't parse as a rate and was then tried as a cron [docs/events.md#schedule].

Set `- schedule: 90 minutes`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 594  gcp Functions page: two errors at once
    C(594, provider="gcp", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions", "docs/events.md#queue"],
      project=proj("""service: parcel-tracking
provider:
  name: gcp
  region: europe-west1
  options:
    project: parcel-tracking-staging
functions:
  track:
    hander: app.parcels.track
    events:
      - http: GET /parcels/{id}
  scan-worker:
    handler: app.parcels.on_scan
    events:
      - queue:
          name: parcel-scans
          batch_size: 0
""", "parcels", "track", "on_scan"),
      user="Fix the problems on the Functions page please, there are a few red ones and I don't know what they mean.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`track`: rename the key `hander` to `handler`",
                                   "`scan-worker`: set `batch_size` to 1 (the minimum; 0 isn't allowed)",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.track",
            value={"handler": "app.parcels.track", "events": [{"http": "GET /parcels/{id}"}]}),
          S("set_config", path="functions.scan-worker.events.0.queue.batch_size", value=1),
      ],
      final="""Two separate problems:

1. `track` had `hander` (typo), so pskit saw no `handler` [docs/configuration.md#functions].
2. `scan-worker` had `batch_size: 0`; the range is 1-10000 [docs/events.md#queue].

Fixed both. `pskit validate -p gcp -s staging`: valid. On GCP `batch_size` is ignored anyway, so you could also remove it."""),

    # ------------------------------------------------------------------ 595  azure resource container name uppercase
    C(595, provider="azure", stage="dev", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/resources.md#fields"],
      project=proj("""service: invoice-store
provider:
  name: azure
  region: westeurope
resources:
  invoices:
    type: storage
    name: Invoices-2026
functions:
  index-invoice:
    handler: app.invoices.index
    events:
      - storage: {resource: invoices}
""", "invoices", "index"),
      user="I gave the invoices resource the name Invoices-2026 (one container per year). index-invoice now fails with container name 'Invoices-2026' must be 3-63 lowercase letters. The resource is the one with that name, not the function.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.invoices.name` to `invoices-2026`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.invoices.name", value="invoices-2026"),
      ],
      final="""The event takes its container from the resource's `name`, so the check runs on the function that uses it; Azure container names must be lowercase [docs/events.md#storage].

Set `name: invoices-2026` on the `invoices` resource; the event is unchanged. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 596  azure queue name too long
    C(596, provider="azure", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#queue"],
      project=proj("""service: onboarding-portal
provider:
  name: azure
  region: westeurope
functions:
  verify-docs:
    handler: app.onboarding.verify
    events:
      - queue: customer-onboarding-portal-prod-identity-document-verification-requests
""", "onboarding", "verify"),
      user="""  ERROR: [functions.verify-docs] queue name 'customer-onboarding-portal-prod-identity-document-verification-requests' must be 3-63 lowercase letters, digits, dashes

all lowercase??""",
      steps=[
          S("get_validation"),
          S("ask_user", question="It's lowercase, but 71 characters; Azure allows at most 63. Which shorter queue name should I use?",
            options=["identity-doc-verification", "onboarding-doc-verify"], answer="identity-doc-verification"),
          S("propose_plan", steps=["Set the queue of `verify-docs` to `identity-doc-verification`", "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.verify-docs.events.0", value={"queue": "identity-doc-verification"}),
      ],
      final="""The name was too long, not wrong in case: Azure queue names are 3-63 characters [docs/events.md#queue].

`verify-docs` now reads `identity-doc-verification`. `pskit validate -p azure -s prod`: valid. Producers that send to the old name must use the new one."""),

    # ------------------------------------------------------------------ 597  azure functionTimeout in provider
    C(597, provider="azure", stage="dev", mode="auto", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#provider", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: batch-reports
provider:
  name: azure
  region: westeurope
  functionTimeout: "00:10:00"
functions:
  report:
    handler: app.reports.build
    events:
      - schedule: "0 6 * * *"
""", "reports", "build"),
      user="Our host.json had functionTimeout 00:10:00. I put it under provider and pskit says provider.functionTimeout: Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `provider.functionTimeout`", "Set `provider.timeout: 600` (10 minutes in seconds)",
                                   "Validate for azure"]),
          S("set_config", path="provider.functionTimeout", value=None),
          S("set_config", path="provider.timeout", value=600),
      ],
      final="""pskit writes `host.json` itself; the portable setting is `timeout` in seconds [docs/configuration.md#provider].

Replaced it with `provider.timeout: 600`, which pskit turns into the Function App's `functionTimeout`. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 598  azure function.json bindings
    C(598, provider="azure", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: webhook-relay
provider:
  name: azure
  region: northeurope
functions:
  relay:
    handler: app.relay.forward
    bindings:
      - type: httpTrigger
        direction: in
        methods: [post]
        route: hooks/github
""", "relay", "forward"),
      user="i copy bindings from function.json, pskit say bindings extra inputs. how i make http trigger post /hooks/github",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `bindings` from `relay`", "Add `events: [{http: POST /hooks/github}]`",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.relay.bindings", value=None),
          S("set_config", path="functions.relay.events", value=[{"http": "POST /hooks/github"}]),
      ],
      final="""pskit generates the Azure bindings itself (`function_app.py`); in pskit.yml you write portable `events` [docs/providers.md#azure-azure-functions].

`relay` now has `- http: POST /hooks/github`, served at exactly `/hooks/github` (no `/api` prefix). `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 599  azure http route key
    C(599, provider="azure", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=proj("""service: orders-read
provider:
  name: azure
  region: westeurope
functions:
  get-order:
    handler: app.orders.get_order
    events:
      - http:
          route: "orders/{id}"
          method: GET
""", "orders", "get_order"),
      user="events.0.route: extra inputs. azure calls it route",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `route: orders/{id}` with `path: /orders/{id}`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.get-order.events.0", value={"http": {"path": "/orders/{id}", "method": "GET"}}),
      ],
      final="""pskit's key is `path`, starting with `/` [docs/events.md#http].

Now `http: {path: /orders/{id}, method: GET}`; `id` is in `event.http.path_params["id"]`. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 600  azure eventgrid -> storage -> deleted
    C(600, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: asset-sync
provider:
  name: azure
  region: westeurope
functions:
  sync-asset:
    handler: app.assets.sync
    events:
      - eventgrid:
          container: assets
          events: [BlobCreated, BlobDeleted]
""", "assets", "sync"),
      user="sync-asset should react when blobs in the assets container are created or deleted (we used Event Grid before). pskit: unknown event type 'eventgrid'.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace the trigger with `storage: {bucket: assets, events: [created, deleted]}`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sync-asset.events.0", value={"storage": {"bucket": "assets", "events": ["created", "deleted"]}}),
          S("ask_user", say="The trigger type is right now, but Azure rejects the `deleted` part.",
            question="pskit's blob trigger on Azure only fires on created/updated blobs. Keep only `created` on Azure (deletes not handled), or run this service on a provider with delete events?",
            options=["keep created only", "switch provider"], answer="keep created only"),
          S("set_config", path="functions.sync-asset.events.0.storage.events", value=["created"]),
      ],
      final="""The portable trigger for blobs is `storage` [docs/events.md#storage]; pskit's Azure blob trigger only reports created/updated blobs, so `deleted` can't be used there [docs/providers.md#azure-azure-functions].

`sync-asset` now has `storage: {bucket: assets, events: [created]}`. Validate for azure: valid. Deleted blobs won't reach this function; if you need them later, we can look at other options."""),
]

