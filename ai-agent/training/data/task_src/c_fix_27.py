"""Category C (fix a validation error), batch 27 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 521  aws `sns:` event
    C(521, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#topic", "docs/providers.md#aws-aws-lambda"],
      project=proj("""service: alarm-router
provider:
  name: aws
  region: us-east-1
functions:
  route-alarm:
    handler: app.alarms.route
    events:
      - sns: ops-alarms
""", "alarms", "route"),
      user="From serverless.yml: `- sns: ops-alarms`. The SNS topic is created by our monitoring stack, not by this service. pskit says unknown event type 'sns'.",
      steps=[
          S("get_validation"),
          S("search_docs", query="topic event existing sns",
            docs=[D("docs/events.md", "topic", end="# AWS SNS filter policy")]),
          S("propose_plan", steps=["Replace `sns: ops-alarms` with `topic: {name: ops-alarms, existing: true}` on `route-alarm`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.route-alarm.events.0", value={"topic": {"name": "ops-alarms", "existing": True}}),
      ],
      final="""The portable trigger is `topic`; on AWS it is an SNS topic + subscription [docs/providers.md#aws-aws-lambda].

Changed to `- topic: {name: ops-alarms, existing: true}`; `existing: true` means pskit only subscribes and never creates or deletes the topic [docs/events.md#topic]. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 522  aws rate(1 hour)
    C(522, provider="aws", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=proj("""service: fx-rates
provider:
  name: aws
  region: eu-west-1
functions:
  refresh:
    handler: app.fx.refresh
    events:
      - schedule: "rate(1 hour)"
""", "fx", "refresh"),
      user="schedule rate(1 hour) parsed as cron?? want hourly",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the schedule of `refresh` to the portable rate `1 hour`",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="functions.refresh.events.0", value={"schedule": "1 hour"}),
      ],
      final="""The shorthand takes a portable rate (`1 hour`) or a 5-field cron; `rate(...)` is the EventBridge form, so pskit read it as a bad cron. pskit writes `rate(1 hour)` for AWS itself [docs/events.md#schedule].

Set `- schedule: 1 hour`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 523  aws jwt missing issuer
    C(523, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=proj("""service: notes-sync
provider:
  name: aws
  region: us-west-2
functions:
  sync:
    handler: app.notes.sync
    events:
      - http:
          path: /sync
          method: POST
          auth: jwt
          authorizer:
            audience: [notes-mobile]
""", "notes", "sync"),
      user="The mobile app sends Cognito ID tokens with audience notes-mobile. Validation says jwt auth needs authorizer.issuer and authorizer.audience. I'm not sure what the issuer is.",
      steps=[
          S("get_validation"),
          S("ask_user", question="The issuer is the `iss` claim inside your tokens (decode one ID token to see it). What is it?",
            answer="https://cognito-idp.us-west-2.amazonaws.com/us-west-2_AbC123xyz"),
          S("propose_plan", steps=["Set `authorizer.issuer` of `/sync` to `https://cognito-idp.us-west-2.amazonaws.com/us-west-2_AbC123xyz`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sync.events.0.http.authorizer.issuer",
            value="https://cognito-idp.us-west-2.amazonaws.com/us-west-2_AbC123xyz"),
      ],
      final="""A JWT authorizer needs both the audience and the issuer of the tokens; only the audience was set [docs/events.md#http].

Added `issuer: https://cognito-idp.us-west-2.amazonaws.com/us-west-2_AbC123xyz`; the audience `notes-mobile` stays. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 524  aws cors "*"
    C(524, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/troubleshooting.md#http"],
      project=proj("""service: quiz-api
provider:
  name: aws
  region: ap-northeast-1
functions:
  questions:
    handler: app.quiz.questions
    events:
      - http:
          path: /questions
          method: GET
          cors: "*"
""", "quiz", "questions"),
      user="i want all website can call api so cors: \"*\" but error valid boolean / dictionary",
      steps=[
          S("get_validation"),
          S("search_docs", query="cors true origins default",
            docs=[D("docs/events.md", "http", start="**CORS**", end="max_age: 600")]),
          S("propose_plan", steps=["Set `cors: true` on `/questions` (default origins are `*`)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.questions.events.0.http.cors", value=True),
      ],
      final="""`cors` is `true` or a mapping, not a string. `cors: true` already allows every origin, because the default `origins` is `["*"]` [docs/events.md#http].

Set `cors: true` on `/questions`. Validate: valid. Later, to allow only your site, use `cors: {origins: ["https://quiz.example.com"]}` [docs/troubleshooting.md#http]."""),

    # ------------------------------------------------------------------ 525  aws start_at typo
    C(525, provider="aws", stage="prod", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: returns-flow
provider:
  name: aws
  region: eu-west-1
functions:
  validate-return:
    handler: app.returns.validate
  refund:
    handler: app.returns.refund
workflows:
  returns:
    start_at: Validate
    states:
      ValidateReturn: {type: task, function: validate-return, next: Refund}
      Refund: {type: task, function: refund, end: true}
""", "returns", "validate", "refund"),
      user="""Error: pskit.yml is invalid:
  - workflows.returns: Value error, start_at 'Validate' is not a defined state

prod, aws""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.returns.start_at` to `ValidateReturn`",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.returns.start_at", value="ValidateReturn"),
      ],
      final="""`start_at` must name an existing state; the first state is called `ValidateReturn`, not `Validate` [docs/workflows.md#workflow-keys].

Set `start_at: ValidateReturn`. `pskit validate -p aws -s prod`: valid (Step Functions)."""),

    # ------------------------------------------------------------------ 526  aws iam statements mapping
    C(526, provider="aws", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: table-reader
provider:
  name: aws
  region: us-east-1
  iam:
    statements:
      actions: ["dynamodb:GetItem", "dynamodb:Query"]
      resources: ["arn:aws:dynamodb:us-east-1:123456789012:table/products"]
functions:
  product:
    handler: app.products.get_product
    events:
      - http: GET /products/{id}
""", "products", "get_product"),
      user="provider.iam.statements: Input should be a valid list",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Wrap the statement in a list (one item, same actions/resources)",
                                   "Validate for aws"]),
          S("set_config", path="provider.iam.statements",
            value=[{"actions": ["dynamodb:GetItem", "dynamodb:Query"],
                    "resources": ["arn:aws:dynamodb:us-east-1:123456789012:table/products"]}]),
      ],
      final="""`iam.statements` is a list of statements; a single one still needs a `-` [docs/configuration.md#provider].

Wrapped it as one list item with the same actions and resources. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 527  aws handler with ()
    C(527, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: birthday-bot
provider:
  name: aws
  region: eu-west-1
functions:
  greet:
    handler: app.bot.greet()
    events:
      - schedule: "0 7 * * *"
""", "bot", "greet"),
      user="In the Handler field I wrote app.bot.greet() because that's how you call a function. It says it must be package.module.function.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.greet.handler` to `app.bot.greet` (no parentheses)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.greet.handler", value="app.bot.greet"),
      ],
      final="""The handler is the *name* of the function, not a call: pskit calls it for you with `(event, ctx)` [docs/configuration.md#functions].

Changed it to `handler: app.bot.greet`. Validate: valid."""),

    # ------------------------------------------------------------------ 528  gcp rate "every 5 minutes"
    C(528, provider="gcp", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=proj("""service: uptime-check
provider:
  name: gcp
  region: europe-west1
  options:
    project: uptime-check-dev
functions:
  ping:
    handler: app.uptime.ping
    events:
      - schedule:
          rate: every 5 minutes
""", "uptime", "ping"),
      user="I used the App Engine cron style `every 5 minutes` for the rate. pskit says rate must look like '<n> minutes|hours|days'.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set the rate of `ping` to `5 minutes` (drop \"every\")",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ping.events.0.schedule.rate", value="5 minutes"),
      ],
      final="""pskit's rate is just `<n> minutes|hours|days`, without "every" [docs/events.md#schedule].

Set `rate: 5 minutes`; Cloud Scheduler gets the cron `*/5 * * * *`. `pskit validate` for gcp: valid."""),

    # ------------------------------------------------------------------ 529  gcp service_account on a function
    C(529, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: bq-loader
provider:
  name: gcp
  region: us-central1
  options:
    project: bq-loader-staging
functions:
  load:
    handler: app.bq.load
    service_account: loader@bq-loader-staging.iam.gserviceaccount.com
    events:
      - storage: bq-loader-drops
""", "bq", "load"),
      user="load should run as loader@bq-loader-staging.iam.gserviceaccount.com (it has the BigQuery roles). I put service_account on the function and staging validation says Extra inputs are not permitted. It's the only function in this service.",
      steps=[
          S("get_validation"),
          S("search_docs", query="gcp service account option",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="```yaml", end="# optional runtime identity")]),
          S("propose_plan", steps=["Remove `functions.load.service_account`",
                                   "Set `provider.options.service_account: loader@bq-loader-staging.iam.gserviceaccount.com`",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.load.service_account", value=None),
          S("set_config", path="provider.options.service_account", value="loader@bq-loader-staging.iam.gserviceaccount.com"),
      ],
      final="""`service_account` is a GCP provider option, so it goes under `provider.options`, not directly on a function [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Moved it: `provider.options.service_account: loader@bq-loader-staging.iam.gserviceaccount.com`. Since `load` is the only function, it now runs as that account. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 530  gcp ${opt:project}
    C(530, provider="gcp", stage="dev", mode="ask", page="YAML", persona="informal_non_native",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: menu-sync
provider:
  name: gcp
  region: europe-west2
  options:
    project: ${opt:project}
functions:
  sync:
    handler: app.menu.sync
    events:
      - schedule: 1 hour
""", "menu", "sync"),
      user="i want give project with command line so ${opt:project}. error unresolved opt:project",
      steps=[
          S("get_validation"),
          S("search_docs", query="opt variables cli env",
            docs=[D("docs/configuration.md", "variables", end="| `${opt:stage}` / `${opt:provider}` / `${opt:region}` | effective CLI values (`${opt:x, default}` allowed) |")]),
          S("ask_user", question="There is no `--project` flag, so `${opt:project}` can't work. I can read it from an environment variable instead. Which project id should be the default?",
            answer="menu-sync-dev-12"),
          S("propose_plan", steps=["Set `provider.options.project` to `${env:GOOGLE_CLOUD_PROJECT, menu-sync-dev-12}`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.project", value="${env:GOOGLE_CLOUD_PROJECT, menu-sync-dev-12}"),
      ],
      final="""`${opt:...}` only has `stage`, `provider` and `region`, the values of the CLI flags. There is no project flag [docs/configuration.md#variables].

Now `project: ${env:GOOGLE_CLOUD_PROJECT, menu-sync-dev-12}`. To choose another project from the command line, set the variable before the command, e.g. `GOOGLE_CLOUD_PROJECT=menu-sync-prod pskit deploy -s prod`. Validate: valid."""),

    # ------------------------------------------------------------------ 531  gcp auth IAM uppercase
    C(531, provider="gcp", stage="prod", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: internal-reports
provider:
  name: gcp
  region: europe-west1
  options:
    project: internal-reports-prod
functions:
  report:
    handler: app.reports.report
    events:
      - http:
          path: /report
          method: GET
          auth: IAM
""", "reports", "report"),
      user="""Error: pskit.yml is invalid:
  - functions.report.events.0.auth: Input should be 'none', 'iam', 'jwt' or 'key'""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `auth` of `/report` to lowercase `iam`",
                                   "Validate for gcp, stage prod"]),
          S("set_config", path="functions.report.events.0.http.auth", value="iam"),
      ],
      final="""The values are lowercase; `IAM` isn't accepted [docs/events.md#http].

Set `auth: iam`, so on GCP no public invoker is added and callers need Google credentials. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 532  gcp concurrency unlimited
    C(532, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: chat-api
provider:
  name: gcp
  region: us-east1
  options:
    project: chat-api-dev
functions:
  messages:
    handler: app.chat.messages
    concurrency: unlimited
    events:
      - http: POST /messages
""", "chat", "messages"),
      user="On the Functions page I typed unlimited in Concurrency and now it's red. I don't want any limit.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `functions.messages.concurrency` (no value = no limit set by pskit)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.messages.concurrency", value=None),
      ],
      final="""Concurrency only takes a number. "No limit" means leaving the field empty, because it has no default [docs/configuration.md#functions].

I removed it from `messages`. Validate: valid."""),

    # ------------------------------------------------------------------ 533  gcp function name starts with a digit
    C(533, provider="gcp", stage="staging", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#top-level"],
      project=proj("""service: auth-svc
provider:
  name: gcp
  region: europe-west1
  options:
    project: auth-svc-staging
functions:
  2fa-verify:
    handler: app.otp.verify
    events:
      - http: POST /2fa/verify
""", "otp", "verify"),
      user="name '2fa-verify' must start with a letter. rename → verify-2fa, keep route",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Add `functions.verify-2fa` with the same handler and route",
                                   "Remove `functions.2fa-verify`",
                                   "Validate for gcp, stage staging"]),
          S("set_config", path="functions.verify-2fa",
            value={"handler": "app.otp.verify", "events": [{"http": "POST /2fa/verify"}]}),
          S("set_config", path="functions.2fa-verify", value=None),
      ],
      final="""Function names must start with a letter [docs/configuration.md#top-level].

Renamed to `verify-2fa`; handler and the route `POST /2fa/verify` are unchanged (paths may start with a digit). `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 534  azure `servicebus:` event
    C(534, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#azure-azure-functions", "docs/events.md#topic"],
      project=proj("""service: order-notify
provider:
  name: azure
  region: westeurope
functions:
  notify:
    handler: app.notify.on_order
    events:
      - servicebus: order-placed
""", "notify", "on_order"),
      user="I'm new to Azure (coming from SNS). I wrote `- servicebus: order-placed` and pskit says unknown event type. pskit should create the topic.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `servicebus: order-placed` with `topic: order-placed` on `notify`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.notify.events.0", value={"topic": "order-placed"}),
      ],
      final="""In pskit the trigger is `topic` on every cloud. On Azure pskit turns it into a Service Bus namespace/topic with one subscription per function, the same idea as SNS [docs/providers.md#azure-azure-functions].

Changed to `- topic: order-placed`. Validate: valid. pskit creates the topic because it isn't marked `existing` [docs/events.md#topic]."""),

    # ------------------------------------------------------------------ 535  azure queue `connection` binding key
    C(535, provider="azure", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions", "docs/events.md#queue"],
      project=proj("""service: telemetry-intake
provider:
  name: azure
  region: westeurope
functions:
  intake:
    handler: app.telemetry.intake
    events:
      - queue:
          name: device-readings
          connection: IOT_STORAGE
""", "telemetry", "intake"),
      user="In function.json the queue trigger had `connection: IOT_STORAGE`, because the queue lives in our IoT storage account, not the app's. pskit says connection: Extra inputs are not permitted. How do I point at the other account?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure storage_connection existing queue other account",
            docs=[D("docs/providers.md", "azure-azure-functions", start="```yaml", end="for `existing` queues/buckets in another account")]),
          S("propose_plan", steps=["Remove `connection` from the queue event of `intake` and set `existing: true`",
                                   "Set `provider.options.storage_connection: IOT_STORAGE`",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.intake.events.0.queue", value={"name": "device-readings", "existing": True}),
          S("set_config", path="provider.options.storage_connection", value="IOT_STORAGE"),
      ],
      final="""pskit has no per-event `connection`; for `existing` queues in another storage account you set the app setting name once in `provider.options.storage_connection` [docs/providers.md#azure-azure-functions].

- `intake`: `queue: {name: device-readings, existing: true}`
- `provider.options.storage_connection: IOT_STORAGE`

`pskit validate -p azure -s staging`: valid. The Function App needs the `IOT_STORAGE` app setting with that account's connection string; keep it out of pskit.yml with `${env:IOT_STORAGE}`."""),

    # ------------------------------------------------------------------ 536  azure http `methods`
    C(536, provider="azure", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: cart-api
provider:
  name: azure
  region: eastus
functions:
  cart:
    handler: app.cart.handle
    events:
      - http:
          path: /cart
          methods: [GET, POST]
""", "cart", "handle"),
      user="methods: [GET, POST] like azure function.json, pskit say extra inputs",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace the event with two: `http: GET /cart` and `http: POST /cart`",
                                   "Validate for azure"]),
          S("set_config", path="functions.cart.events", value=[{"http": "GET /cart"}, {"http": "POST /cart"}]),
      ],
      final="""pskit's key is `method` (one value per event), not `methods` [docs/events.md#http].

`cart` now has `- http: GET /cart` and `- http: POST /cart`. Validate: valid."""),

    # ------------------------------------------------------------------ 537  azure runOnStartup
    C(537, provider="azure", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#schedule"],
      project=proj("""service: cache-loader
provider:
  name: azure
  region: northeurope
functions:
  load-cache:
    handler: app.cache.load
    events:
      - schedule:
          cron: "0 3 * * *"
          runOnStartup: true
""", "cache", "load"),
      user="""Error: pskit.yml is invalid:
  - functions.load-cache.events.0.runOnStartup: Extra inputs are not permitted

prod""",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule options",
            docs=[D("docs/events.md", "schedule", end="name: morning-report               # optional, used in the resource name")]),
          S("propose_plan", steps=["Remove `runOnStartup` from the schedule of `load-cache`",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.load-cache.events.0.schedule.runOnStartup", value=None),
      ],
      final="""pskit's schedule has `rate`/`cron`, `input`, `timezone`, `enabled` and `name`; Azure's `runOnStartup` isn't one of them [docs/events.md#schedule].

Removed it; the job runs daily at 03:00 UTC. `pskit validate -p azure -s prod`: valid. To fill the cache right after a deploy, call the function once yourself, e.g. from the **Test** page with **☁ Send to azure / prod**."""),

    # ------------------------------------------------------------------ 538  azure storage `path` pattern
    C(538, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#storage"],
      project=proj("""service: csv-import
provider:
  name: azure
  region: westeurope
functions:
  import-csv:
    handler: app.importer.run
    events:
      - storage:
          bucket: imports
          path: "incoming/{name}.csv"
""", "importer", "run"),
      user="The blob trigger path `incoming/{name}.csv` is rejected (extra inputs). On S3 I'd use prefix/suffix filters; what does pskit want here?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `path` with `prefix: incoming/` and `suffix: .csv` on the storage event of `import-csv`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.import-csv.events.0.storage",
            value={"bucket": "imports", "prefix": "incoming/", "suffix": ".csv"}),
      ],
      final="""Same as on S3: pskit uses portable `prefix` and `suffix`, and on Azure turns them into the blob path pattern [docs/events.md#storage].

Now `storage: {bucket: imports, prefix: incoming/, suffix: .csv}`. Validate: valid. The file name is in `event.records[0].key`."""),

    # ------------------------------------------------------------------ 539  azure auth anonymous
    C(539, provider="azure", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#http"],
      project=proj("""service: public-menu
provider:
  name: azure
  region: westeurope
functions:
  menu:
    handler: app.menu.get_menu
    events:
      - http:
          path: /menu
          method: GET
          auth: anonymous
""", "menu", "get_menu"),
      user="My menu page should be open to everyone. Azure calls that anonymous, so I wrote auth: anonymous, but it's red.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `auth` of `/menu` to `none` (public)",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.menu.events.0.http.auth", value="none"),
      ],
      final="""In pskit "open to everyone" is `auth: none`; it works on all clouds [docs/events.md#http].

Set `auth: none` on `/menu`. Validate for staging: valid. (`none` is also the default, so you can remove the line.)"""),

    # ------------------------------------------------------------------ 540  azure engine logicapps
    C(540, provider="azure", stage="dev", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflow-keys", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: approval-flow
provider:
  name: azure
  region: westeurope
functions:
  request:
    handler: app.approval.request
  decide:
    handler: app.approval.decide
workflows:
  approve:
    engine: logicapps
    start_at: Request
    states:
      Request: {type: task, function: request, next: Decide}
      Decide: {type: task, function: decide, end: true}
""", "approval", "request", "decide"),
      user="engine: logicapps → should be auto/native/embedded. want logic apps",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.approve.engine` to `native` (Logic App on Azure)",
                                   "Validate for azure"]),
          S("set_config", path="workflows.approve.engine", value="native"),
      ],
      final="""On Azure, `engine: native` is the Logic App; `auto` would keep the embedded engine there [docs/workflows.md#workflow-keys].

Set `engine: native`. `pskit validate` for azure: valid (native engine). Start it with `POST` to the Logic App callback URL that `pskit info` shows [docs/providers.md#azure-azure-functions]."""),
]
