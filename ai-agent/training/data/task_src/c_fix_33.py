"""Category C (fix a validation error), batch 33 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 641  aws iamRoleStatements
    C(641, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: orders-table
provider:
  name: aws
  region: us-east-1
  iamRoleStatements:
    - Effect: Allow
      Action: ["dynamodb:PutItem", "dynamodb:GetItem"]
      Resource: ["arn:aws:dynamodb:us-east-1:123456789012:table/orders"]
functions:
  put-order:
    handler: app.orders.put_order
    events:
      - http: POST /orders
""", "orders", "put_order"),
      user="Our old serverless.yml (v2) used provider.iamRoleStatements. pskit: provider.iamRoleStatements: Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("search_docs", query="iam statements provider",
            docs=[D("docs/configuration.md", "provider", start="| `iam.statements` |", end="| `iam.role` |")]),
          S("propose_plan", steps=["Move the statement to `provider.iam.statements` with pskit keys `effect`, `actions`, `resources`",
                                   "Remove `iamRoleStatements`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.iamRoleStatements", value=None),
          S("set_config", path="provider.iam",
            value={"statements": [{"effect": "Allow", "actions": ["dynamodb:PutItem", "dynamodb:GetItem"],
                                   "resources": ["arn:aws:dynamodb:us-east-1:123456789012:table/orders"]}]}),
      ],
      final="""pskit's equivalent is `provider.iam.statements`, a list of `{effect, actions, resources}` in lowercase [docs/configuration.md#provider].

Moved the DynamoDB statement there (same actions and table ARN). Validate for aws: valid."""),

    # ------------------------------------------------------------------ 642  aws env instead of environment
    C(642, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: greeter
provider:
  name: aws
  region: eu-west-2
functions:
  greet:
    handler: app.greet.hello
    env:
      GREETING: Hello
    events:
      - http: GET /greet
""", "greet", "hello"),
      user="I added a GREETING variable under env: and now it says functions.greet.env: Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `env` to `environment` on `greet`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.greet.env", value=None),
          S("set_config", path="functions.greet.environment", value={"GREETING": "Hello"}),
      ],
      final="""The key is spelled out: `environment` [docs/configuration.md#functions].

`greet` now has `environment: {GREETING: Hello}`. Validate for aws: valid. In the handler read it with `os.environ["GREETING"]`."""),

    # ------------------------------------------------------------------ 643  aws package.patterns
    C(643, provider="aws", stage="staging", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#package"],
      project=proj("""service: report-gen
provider:
  name: aws
  region: us-east-1
package:
  patterns:
    - "!docs/**"
    - "!scripts/**"
functions:
  report:
    handler: app.reports.build
    events:
      - schedule: "0 6 * * 1"
""", "reports", "build"),
      user="package.patterns extra input. sls negation patterns → pskit?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `package.patterns` with `package.exclude: [\"docs/**\", \"scripts/**\"]`", "Validate for aws, stage staging"]),
          S("set_config", path="package", value={"exclude": ["docs/**", "scripts/**"]}),
      ],
      final="""pskit has `include` and `exclude` lists instead of `!` patterns [docs/configuration.md#package].

`package.exclude: ["docs/**", "scripts/**"]`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 644  aws serverless top-level keys
    C(644, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#top-level", "docs/configuration.md#package"],
      project=proj("""service: contact-form
frameworkVersion: "3"
useDotenv: true
plugins:
  - serverless-python-requirements
provider:
  name: aws
  region: us-east-1
functions:
  contact:
    handler: app.contact.send
    events:
      - http: POST /contact
""", "contact", "send"),
      user="Three errors on the top-level keys I kept from serverless.yml: frameworkVersion, useDotenv, plugins. Do I need replacements for them?",
      steps=[
          S("get_validation"),
          S("search_docs", query="requirements packaging dependencies",
            docs=[D("docs/configuration.md", "package", start="| `requirements` |", end="| `vendor` |")]),
          S("propose_plan", steps=["Remove `frameworkVersion`, `useDotenv` and `plugins`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="frameworkVersion", value=None),
          S("set_config", path="useDotenv", value=None),
          S("set_config", path="plugins", value=None),
      ],
      final="""None of them exist in pskit, and you don't need replacements [docs/configuration.md#top-level]:
- `plugins: [serverless-python-requirements]`: pskit installs `requirements.txt` into the bundle itself [docs/configuration.md#package].
- `useDotenv`: for local runs use `pskit invoke -f contact --env-file .env`; in pskit.yml use `${env:NAME}`.
- `frameworkVersion`: not needed.

Removed all three. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 645  aws deploymentBucket
    C(645, provider="aws", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#aws-aws-lambda"],
      project=proj("""service: payroll-api
provider:
  name: aws
  region: eu-west-1
  deploymentBucket:
    name: acme-deploy-artifacts-prod
functions:
  payslips:
    handler: app.payroll.payslips
    events:
      - http: GET /payslips
""", "payroll", "payslips"),
      user="Security only lets us upload code to acme-deploy-artifacts-prod (we can't create buckets). I put that in provider.deploymentBucket as in serverless and got Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("search_docs", query="aws artifact bucket upload code",
            docs=[D("docs/providers.md", "aws-aws-lambda", start="**Code upload:**", end="**Code upload:**")]),
          S("propose_plan", steps=["Remove `provider.deploymentBucket`", "Set `provider.options.artifact_bucket: acme-deploy-artifacts-prod`",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.deploymentBucket", value=None),
          S("set_config", path="provider.options", value={"artifact_bucket": "acme-deploy-artifacts-prod"}),
      ],
      final="""On AWS pskit's option is `provider.options.artifact_bucket`: the code is uploaded there instead of a bucket pskit creates [docs/providers.md#aws-aws-lambda].

Set `artifact_bucket: acme-deploy-artifacts-prod`. `pskit validate -p aws -s prod`: valid. The deploying identity then only needs `s3:PutObject` on that bucket."""),

    # ------------------------------------------------------------------ 646  aws kinesis, no trigger
    C(646, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=proj("""service: click-stream
provider:
  name: aws
  region: us-east-1
functions:
  count-clicks:
    handler: app.clicks.count
    events:
      - kinesis: clicks-stream
""", "clicks", "count"),
      user="we have kinesis stream clicks-stream, pskit say unknown event type kinesis. what i can use",
      steps=[
          S("get_validation"),
          S("ask_user", question="pskit has no Kinesis trigger. The closest is a `queue` (SQS) trigger with batches. Can the producer write to an SQS queue `clicks` instead?",
            options=["yes, use queue clicks", "no, must be kinesis"], answer="yes, use queue clicks"),
          S("propose_plan", steps=["Replace the trigger with `queue: {name: clicks, batch_size: 100}`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.count-clicks.events.0", value={"queue": {"name": "clicks", "batch_size": 100}}),
      ],
      final="""Kinesis isn't one of pskit's triggers; SQS via `queue` is the closest, and it delivers batches too [docs/events.md#queue].

`count-clicks` now has `queue: {name: clicks, batch_size: 100}` (pskit creates the queue). Validate for aws: valid. The producer must send to the `clicks` queue; each message is one `event.records` item."""),

    # ------------------------------------------------------------------ 647  aws prod-only memory "1024MB"
    C(647, provider="aws", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      project=proj("""service: image-api
provider:
  name: aws
  region: us-west-2
stages:
  prod:
    functions:
      resize:
        memory: 1024MB
functions:
  resize:
    handler: app.images.resize
    memory: 512
    events:
      - http: POST /resize
""", "images", "resize"),
      user="""prod only:
  - functions.resize.memory: Input should be a valid integer, unable to parse string as an integer""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `stages.prod.functions.resize.memory` to 1024 (a number of MB)", "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.functions.resize.memory", value=1024),
      ],
      final="""The prod override had `1024MB`; memory is a plain number of MB [docs/configuration.md#stages-per-stage-overrides].

`stages.prod.functions.resize.memory: 1024` (dev keeps 512). `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 648  gcp runtime python312
    C(648, provider="gcp", stage="dev", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: sheet-sync
provider:
  name: gcp
  region: europe-west1
  runtime: python312
  options:
    project: sheet-sync-dev
functions:
  sync:
    handler: app.sheets.sync
    events:
      - schedule: 30 minutes
""", "sheets", "sync"),
      user="""Error: pskit.yml is invalid:
  - provider.runtime: Value error, runtime must be python3.9 .. python3.14 or nodejs18, nodejs20, nodejs22, nodejs24 (provider support varies)

python312 is the gcloud runtime name""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.runtime` to `python3.12`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value="python3.12"),
      ],
      final="""pskit uses portable names like `python3.12` and maps them to GCP's `python312` itself [docs/configuration.md#provider].

Set `runtime: python3.12`. Validate for gcp: valid. (3.12 is also the default, so you could drop the line.)"""),

    # ------------------------------------------------------------------ 649  gcp labels -> tags
    C(649, provider="gcp", stage="staging", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: billing-export
provider:
  name: gcp
  region: us-central1
  labels:
    team: finance
    env: staging
  options:
    project: billing-export-staging
functions:
  export:
    handler: app.billing.export
    events:
      - schedule: "0 1 * * *"
""", "billing", "export"),
      user="Finance needs labels team=finance on every resource. I added provider.labels (that's what GCP calls them) but it's not allowed.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `provider.labels` to `provider.tags` (drop `env`, pskit adds `pskit-stage`)",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.labels", value=None),
          S("set_config", path="provider.tags", value={"team": "finance"}),
      ],
      final="""The portable key is `tags`; pskit merges it with its own `pskit-service`, `pskit-stage` and `managed-by` [docs/configuration.md#provider].

`provider.tags: {team: finance}`. I left out `env: staging` because `pskit-stage` already carries the stage. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 650  gcp maxInstances -> concurrency
    C(650, provider="gcp", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: pdf-export
provider:
  name: gcp
  region: europe-west1
  options:
    project: pdf-export-prod
functions:
  export:
    handler: app.pdf.export
    maxInstances: 10
    events:
      - http: POST /export
""", "pdf", "export"),
      user="maxInstances: 10 → extra inputs. cap at 10",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `maxInstances: 10` with `concurrency: 10` on `export`", "Validate for gcp, stage prod"]),
          S("set_config", path="functions.export.maxInstances", value=None),
          S("set_config", path="functions.export.concurrency", value=10),
      ],
      final="""pskit's key is `concurrency` (reserved concurrency / max instances where supported) [docs/configuration.md#functions].

`export`: `concurrency: 10`. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 651  gcp schedule retry key
    C(651, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=proj("""service: fx-import
provider:
  name: gcp
  region: europe-west3
  options:
    project: fx-import-dev
functions:
  import-rates:
    handler: app.fx.import_rates
    events:
      - schedule:
          cron: "15 16 * * 1-5"
          timezone: Europe/Berlin
          retry: 3
""", "fx", "import_rates"),
      user="Cloud Scheduler can retry failed jobs, so I put retry: 3 on the schedule. Validation says retry: Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule keys",
            docs=[D("docs/events.md", "schedule", end="The handler gets")]),
          S("propose_plan", steps=["Remove `retry` from the schedule of `import-rates`", "Validate for gcp"],
            result={"decision": "approved", "note": "ok, I'll retry inside the handler"}),
          S("set_config", path="functions.import-rates.events.0.schedule.retry", value=None),
      ],
      final="""A schedule has `rate`/`cron`, `input`, `timezone`, `enabled` and `name`; there's no retry setting [docs/events.md#schedule].

Removed `retry`; the job runs at 16:15 Berlin time on weekdays. Validate for gcp: valid. As you said, retry inside `import_rates`, e.g. a short loop around the API call."""),

    # ------------------------------------------------------------------ 652  gcp ack_deadline
    C(652, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=proj("""service: email-worker
provider:
  name: gcp
  region: us-east1
  options:
    project: email-worker-staging
functions:
  send:
    handler: app.mail.send
    events:
      - queue:
          name: outbox
          ack_deadline: 60
""", "mail", "send"),
      user="i put ack_deadline 60 like pubsub, pskit say extra inputs. where i set it",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue options gcp pubsub",
            docs=[D("docs/events.md", "queue", start="| Option |", end="| partial batch failure |")]),
          S("propose_plan", steps=["Remove `ack_deadline` from the queue event of `send`", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.send.events.0.queue", value={"name": "outbox"}),
      ],
      final="""pskit's queue event has no `ack_deadline`. On GCP the queue is a Pub/Sub topic with a push trigger that pskit sets up, and a failed delivery is retried as a whole [docs/events.md#queue].

Removed it; the event is `queue: {name: outbox}`. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 653  gcp hooks as string
    C(653, provider="gcp", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#hooks"],
      project=proj("""service: api-docs
provider:
  name: gcp
  region: europe-west1
  options:
    project: api-docs-dev
hooks:
  before_package: python scripts/build_openapi.py
functions:
  docs:
    handler: app.docs.serve
    events:
      - http: GET /docs
""", "docs", "serve"),
      user="I want to build the OpenAPI file before packaging. I added hooks before_package with the command and it says Input should be a valid list.",
      steps=[
          S("get_validation"),
          S("search_docs", query="hooks before_package commands",
            docs=[D("docs/configuration.md", "hooks")]),
          S("propose_plan", steps=["Make `hooks.before_package` a list: `[\"python scripts/build_openapi.py\"]`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="hooks.before_package", value=["python scripts/build_openapi.py"]),
      ],
      final="""Each hook is a list of shell commands, even for one command [docs/configuration.md#hooks].

`before_package: ["python scripts/build_openapi.py"]`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 654  gcp function name too long
    C(654, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/configuration.md#top-level"],
      project=proj("""service: kyc-docs
provider:
  name: gcp
  region: europe-west1
  options:
    project: kyc-docs-dev
functions:
  process-customer-identity-verification-documents-from-partner-uploads:
    handler: app.kyc.process
    events:
      - storage: kyc-partner-uploads
""", "kyc", "process"),
      user="I gave the function a very descriptive name so people know what it does, and now: name '...' must start with a letter and use letters, digits, - or _. It does start with a letter.",
      steps=[
          S("get_validation"),
          S("ask_user", question="It starts with a letter, but it is 69 characters and the limit is 63. Shorter name? You can keep the long text in `description`.",
            options=["process-partner-kyc-docs", "other"], answer="process-partner-kyc-docs"),
          S("propose_plan", steps=["Rename the function to `process-partner-kyc-docs`",
                                   "Put the long text into `description`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions",
            value={"process-partner-kyc-docs": {
                "handler": "app.kyc.process",
                "description": "Process customer identity verification documents from partner uploads",
                "events": [{"storage": "kyc-partner-uploads"}]}}),
      ],
      final="""Function names can be at most 63 characters [docs/configuration.md#top-level]; this one had 69.

Renamed to `process-partner-kyc-docs` and put the explanation in `description`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 655  azure app_settings -> environment
    C(655, provider="azure", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#provider", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: notify-hub
provider:
  name: azure
  region: westeurope
  app_settings:
    SENDER_EMAIL: noreply@example.com
    LOG_FORMAT: json
functions:
  notify:
    handler: app.notify.send
    events:
      - queue: notifications
""", "notify", "send"),
      user="On Azure these are app settings, so I wrote provider.app_settings. pskit: Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename `provider.app_settings` to `provider.environment` (same values)", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.app_settings", value=None),
          S("set_config", path="provider.environment", value={"SENDER_EMAIL": "noreply@example.com", "LOG_FORMAT": "json"}),
      ],
      final="""Use the portable `environment`; on Azure pskit writes it as app settings of the Function App, shared by all functions [docs/providers.md#azure-azure-functions].

`provider.environment` now has `SENDER_EMAIL` and `LOG_FORMAT`. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 656  azure resourceGroup at provider level
    C(656, provider="azure", stage="staging", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/providers.md#azure-azure-functions"],
      project=proj("""service: intranet-api
provider:
  name: azure
  region: westeurope
  resourceGroup: rg-intranet-staging
functions:
  pages:
    handler: app.intranet.pages
    events:
      - http: GET /pages
""", "intranet", "pages"),
      user="provider.resourceGroup extra input. must deploy into existing rg-intranet-staging",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Move it to `provider.options.resource_group: rg-intranet-staging`", "Validate for azure, stage staging"]),
          S("set_config", path="provider.resourceGroup", value=None),
          S("set_config", path="provider.options", value={"resource_group": "rg-intranet-staging"}),
      ],
      final="""It's an Azure option: `provider.options.resource_group` uses an existing resource group [docs/providers.md#azure-azure-functions].

Set `options.resource_group: rg-intranet-staging`. `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 657  azure subscription_id at provider level
    C(657, provider="azure", stage="prod", mode="ask", page="Setup", persona="beginner",
      sources=["docs/providers.md#azure-azure-functions"],
      project=proj("""service: timesheets
provider:
  name: azure
  region: northeurope
  subscription_id: ${env:ARM_SUBSCRIPTION_ID, ""}
functions:
  submit:
    handler: app.times.submit
    events:
      - http: POST /timesheets
""", "times", "submit"),
      user="The docs said Azure needs a subscription id, so I added provider.subscription_id. Now prod validation says Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure subscription id",
            docs=[D("docs/providers.md", "azure-azure-functions", start="```yaml", end="subscription_id:")]),
          S("propose_plan", steps=["Move it under `provider.options.subscription_id`", "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.subscription_id", value=None),
          S("set_config", path="provider.options", value={"subscription_id": "${env:ARM_SUBSCRIPTION_ID, \"\"}"}),
      ],
      final="""Right idea, wrong level: it's an Azure option, so it goes under `provider.options` [docs/providers.md#azure-azure-functions].

Now `options.subscription_id: ${env:ARM_SUBSCRIPTION_ID, ""}`. `pskit validate -p azure -s prod`: valid. Before deploying, set `ARM_SUBSCRIPTION_ID` (for example on **Setup & credentials > Environment variables > Set for this session**)."""),

    # ------------------------------------------------------------------ 658  azure poison_queue key
    C(658, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: label-queue
provider:
  name: azure
  region: westeurope
functions:
  print-label:
    handler: app.labels.print_label
    events:
      - queue:
          name: labels
          poison_queue: labels-failed
""", "labels", "print_label"),
      user="i want bad messages go to labels-failed, so poison_queue. pskit say extra inputs",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure poison queue dead letter",
            docs=[D("docs/events.md", "queue", start="| Option |", end="| `dead_letter`, `max_receive` |")]),
          S("propose_plan", steps=["Remove `poison_queue` from the queue event of `print-label`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.print-label.events.0.queue", value={"name": "labels"}),
      ],
      final="""On Azure you can't choose the poison queue: messages that keep failing go to `<queue>-poison` automatically, here `labels-poison` [docs/events.md#queue].

Removed `poison_queue`; the event is `queue: {name: labels}`. Validate for azure: valid. Watch `labels-poison` for bad messages."""),

    # ------------------------------------------------------------------ 659  azure topic subscription key
    C(659, provider="azure", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions", "docs/events.md#topic"],
      project=proj("""service: invoice-events
provider:
  name: azure
  region: westeurope
functions:
  bill:
    handler: app.invoices.bill
    events:
      - topic:
          name: order-events
          subscription: billing
  ship:
    handler: app.invoices.ship
    events:
      - topic:
          name: order-events
          subscription: shipping
""", "invoices", "bill", "ship"),
      user="Two functions should each get every order-events message, so I gave them Service Bus subscriptions billing and shipping. pskit: subscription: Extra inputs are not permitted.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `subscription` from both topic events (pskit makes one subscription per function)",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.bill.events.0", value={"topic": "order-events"}),
          S("set_config", path="functions.ship.events.0", value={"topic": "order-events"}),
      ],
      final="""You get that without naming them: on Azure pskit creates one Service Bus subscription per function, so `bill` and `ship` each receive every message [docs/providers.md#azure-azure-functions].

Both now have `- topic: order-events`. `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 660  azure visibility_timeout PT5M
    C(660, provider="azure", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#queue"],
      project=proj("""service: resize-queue
provider:
  name: azure
  region: westeurope
functions:
  resize:
    handler: app.images.resize
    events:
      - queue:
          name: resize-jobs
          visibility_timeout: PT5M
""", "images", "resize"),
      user="""Error: pskit.yml is invalid:
  - functions.resize.events.0.visibility_timeout: Input should be a valid integer, unable to parse string as an integer""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `visibility_timeout: 300` (seconds)", "Validate for azure"]),
          S("set_config", path="functions.resize.events.0.queue.visibility_timeout", value=300),
      ],
      final="""`visibility_timeout` is a number of seconds, not an ISO duration like `PT5M` [docs/events.md#queue].

Set `visibility_timeout: 300`. Validate for azure: valid."""),
]

