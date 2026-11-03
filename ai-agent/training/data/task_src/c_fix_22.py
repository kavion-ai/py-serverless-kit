"""Category C (fix a validation error), batch 22 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 421  aws wait seconds "1h"
    C(421, provider="aws", stage="dev", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: trial-reminder
provider:
  name: aws
  region: us-east-1
functions:
  remind:
    handler: app.trial.remind
workflows:
  trial:
    start_at: Wait
    states:
      Wait: {type: wait, seconds: 1h, next: Remind}
      Remind: {type: task, function: remind, end: true}
""", "trial", "remind"),
      user="Wait.seconds: unable to parse string as a number. want 1 hour",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.trial.states.Wait.seconds` to 3600",
                                   "Validate for aws"]),
          S("set_config", path="workflows.trial.states.Wait.seconds", value=3600),
      ],
      final="""`seconds` on a `wait` state is a number of seconds, no units [docs/workflows.md#state-types].

Set `Wait.seconds: 3600`. `pskit validate` for aws: valid (Step Functions, so a 1-hour wait is fine)."""),

    # ------------------------------------------------------------------ 422  aws parallel branch missing start_at
    C(422, provider="aws", stage="staging", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: order-enrich
provider:
  name: aws
  region: eu-west-1
functions:
  fraud-check:
    handler: app.enrich.fraud_check
  tax:
    handler: app.enrich.tax
workflows:
  enrich:
    start_at: Both
    states:
      Both:
        type: parallel
        branches:
          - states:
              Fraud: {type: task, function: fraud-check, end: true}
          - start_at: Tax
            states:
              Tax: {type: task, function: tax, end: true}
        end: true
""", "enrich", "fraud_check", "tax"),
      user="Staging validation for the enrich workflow says `branches.0.start_at: Field required`. The two branches (fraud check and tax) should run at the same time. Please fix the branch definition.",
      steps=[
          S("get_validation"),
          S("search_docs", query="parallel branches start_at",
            docs=[D("docs/workflows.md", "state-types", start="| `parallel` |", end="result is a list (one item per branch) |")]),
          S("propose_plan", steps=["Add `start_at: Fraud` to the first branch of `Both`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.enrich.states.Both.branches.0.start_at", value="Fraud"),
      ],
      final="""Each `parallel` branch is a small workflow of its own and needs its own `start_at`; the first branch had none [docs/workflows.md#state-types].

Added `start_at: Fraud` to branch 0; the Tax branch already had one. `pskit validate -p aws -s staging`: valid. Both branches run concurrently and the result is a list with one item per branch."""),

    # ------------------------------------------------------------------ 423  aws map with ASL itemProcessor
    C(423, provider="aws", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#state-types", "docs/workflows.md#compiler-notes-and-limits"],
      project=proj("""service: batch-emails
provider:
  name: aws
  region: us-west-2
functions:
  send-one:
    handler: app.emails.send_one
workflows:
  blast:
    start_at: EachUser
    states:
      EachUser:
        type: map
        items_path: $.users
        itemProcessor:
          start_at: Send
          states:
            Send: {type: task, function: send-one, end: true}
        end: true
""", "emails", "send_one"),
      user="Converted a Step Functions Map state; ASL calls it ItemProcessor so I wrote itemProcessor. pskit says extra inputs not permitted.",
      steps=[
          S("get_validation"),
          S("search_docs", query="map state iterator",
            docs=[D("docs/workflows.md", "state-types", start="| `map` |", end="result is a list |")]),
          S("propose_plan", steps=["Rename `itemProcessor` to `iterator` on `EachUser` (same content)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.blast.states.EachUser.iterator",
            value={"start_at": "Send", "states": {"Send": {"type": "task", "function": "send-one", "end": True}}}),
          S("set_config", path="workflows.blast.states.EachUser.itemProcessor", value=None),
      ],
      final="""pskit's key for the per-item sub-workflow is `iterator` (`{start_at, states}`) [docs/workflows.md#state-types]. On AWS pskit compiles it to an inline `ItemProcessor` for you [docs/workflows.md#compiler-notes-and-limits].

Moved the block from `itemProcessor` to `iterator`. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 424  aws topic filter as string
    C(424, provider="aws", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#topic"],
      project=proj("""service: notify-hub
provider:
  name: aws
  region: eu-central-1
functions:
  on-refund:
    handler: app.notify.on_refund
    events:
      - topic:
          name: payment-events
          filter: refunded
""", "notify", "on_refund"),
      user="""Error: pskit.yml is invalid:
  - functions.on-refund.events.0.filter: Input should be a valid dictionary

messages have attribute type=refunded""",
      steps=[
          S("get_validation"),
          S("search_docs", query="topic filter policy",
            docs=[D("docs/events.md", "topic", end="# AWS SNS filter policy")]),
          S("propose_plan", steps=["Set the filter of `on-refund` to `{type: [refunded]}`",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.on-refund.events.0.topic.filter", value={"type": ["refunded"]}),
      ],
      final="""`filter` is an SNS filter policy: a mapping of attribute name to allowed values, not a plain string [docs/events.md#topic].

Set `filter: {type: [refunded]}`, so only messages with attribute `type=refunded` reach `on-refund`. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 425  aws literal Slack webhook (security)
    C(425, provider="aws", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/troubleshooting.md#security-notes"],
      project=proj("""service: deploy-notifier
provider:
  name: aws
  region: us-east-1
functions:
  notify:
    handler: app.notify.post
    environment:
      SLACK_WEBHOOK_URL: https://hooks.slack.example.com/services/T0000/B0000/abcdefghijklmnop
    events:
      - topic: deploy-events
""", "notify", "post"),
      user="Please review pskit.yml before I open a PR. Validation is green, I just want to be sure nothing sensitive goes into the repo.",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Replace the literal webhook URL in `functions.notify.environment.SLACK_WEBHOOK_URL` with `${env:SLACK_WEBHOOK_URL}`",
                                   "Validate for aws (with the variable unset, validate will report it)"],
            result={"decision": "approved", "note": "use an empty default so validate works on machines without it"}),
          S("set_config", path="functions.notify.environment.SLACK_WEBHOOK_URL", value="${env:SLACK_WEBHOOK_URL, }"),
      ],
      final="""One problem: the Slack webhook URL was written in pskit.yml. Anyone who has that URL can post to your channel, so treat it like a password [docs/troubleshooting.md#security-notes].

Changed, with the empty default you asked for:

```yaml
environment:
  SLACK_WEBHOOK_URL: ${env:SLACK_WEBHOOK_URL, }
```

`pskit validate` for aws: valid [docs/configuration.md#variables]. Set `SLACK_WEBHOOK_URL` in your shell or CI before `pskit deploy`, otherwise the function gets an empty value. If the URL was ever committed, create a new webhook in Slack."""),

    # ------------------------------------------------------------------ 426  aws package.include string
    C(426, provider="aws", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#package"],
      project=proj("""service: geo-api
provider:
  name: aws
  region: eu-west-1
package:
  include: "app/**"
functions:
  lookup:
    handler: app.geo.lookup
    events:
      - http: GET /lookup
""", "geo", "lookup"),
      user="package.include: Input should be a valid list",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `package.include` to `[\"app/**\"]`",
                                   "Validate for aws"]),
          S("set_config", path="package.include", value=["app/**"]),
      ],
      final="""`include` is a list of gitignore-style globs, even for one pattern [docs/configuration.md#package].

Set `include: ["app/**"]`. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 427  aws service name underscore
    C(427, provider="aws", stage="staging", mode="ask", page="Overview", persona="pasted_error",
      sources=["docs/configuration.md#top-level"],
      project=proj("""service: orders_api
provider:
  name: aws
  region: us-east-1
functions:
  create:
    handler: app.orders.create
    events:
      - http: POST /orders
""", "orders", "create"),
      user="""Error: pskit.yml is invalid:
  - service: Value error, service must be 2-32 chars of lowercase letters, digits and dashes

name is orders_api, it's only 10 chars""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the service to `orders-api` (dash instead of underscore)",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="service", value="orders-api"),
      ],
      final="""Length was fine; the underscore isn't allowed. A service name uses lowercase letters, digits and `-`, and starts with a letter [docs/configuration.md#top-level].

Renamed it to `service: orders-api`. `pskit validate -p aws -s staging`: valid.

The service name is part of every deployed name (`<service>-<stage>-<function>`), so if `orders_api` was ever deployed under another name, this creates new resources."""),

    # ------------------------------------------------------------------ 428  aws workflow references renamed function
    C(428, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: pet-adoption
provider:
  name: aws
  region: us-east-2
functions:
  check-application:
    handler: app.adopt.check_application
  approve-adoption:
    handler: app.adopt.approve
workflows:
  adopt:
    start_at: Check
    states:
      Check: {type: task, function: check-application, next: Approve}
      Approve: {type: task, function: approve, end: true}
""", "adopt", "check_application", "approve"),
      user="I renamed the function approve to approve-adoption on the Functions page and now my workflow has an error.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["In workflow `adopt`, set `Approve.function` to `approve-adoption`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.adopt.states.Approve.function", value="approve-adoption"),
      ],
      final="""The `Approve` step still called the old name `approve`, which no longer exists. Every `function` in a workflow must be a function under `functions` [docs/workflows.md#workflow-keys].

I pointed `Approve` at `approve-adoption`. Validate: valid. Next time you rename a function, check the **Workflows** page too."""),

    # ------------------------------------------------------------------ 429  gcp resource type pubsub
    C(429, provider="gcp", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/configuration.md#resources", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: telemetry
provider:
  name: gcp
  region: us-central1
  options:
    project: telemetry-dev-81
resources:
  device-events: {type: pubsub}
functions:
  ingest:
    handler: app.telemetry.ingest
    events:
      - topic: {resource: device-events}
""", "telemetry", "ingest"),
      user="resource type pubsub not accepted?? on gcp it IS pubsub",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.device-events.type` to `topic` (a Pub/Sub topic on GCP)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.device-events.type", value="topic"),
      ],
      final="""Resource types are portable names: `storage`, `queue`, `topic`, `database`, `cache`, `custom`, `smtp` [docs/configuration.md#resources]. On GCP a `topic` becomes a Pub/Sub topic [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Set `type: topic` on `device-events`. Validate: valid."""),

    # ------------------------------------------------------------------ 430  gcp topic event unknown resource
    C(430, provider="gcp", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#events-backed-by-a-resource"],
      project=proj("""service: audit-sink
provider:
  name: gcp
  region: europe-west1
  options:
    project: audit-sink-staging
functions:
  sink:
    handler: app.audit.sink
    events:
      - topic: {resource: audit-log}
""", "audit", "sink"),
      user="sink: unknown resource 'audit-log'. pskit should create the topic",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Add `resources.audit-log: {type: topic}` (managed by pskit)",
                                   "Validate for gcp, stage staging"]),
          S("set_config", path="resources.audit-log", value={"type": "topic"}),
      ],
      final="""The event pointed at `resource: audit-log`, but there was no such entry under `resources:` [docs/events.md#events-backed-by-a-resource].

Added `resources.audit-log: {type: topic}`; without `external`, pskit creates the Pub/Sub topic. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 431  gcp nodejs function in a python service
    C(431, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: recipe-api
provider:
  name: gcp
  region: europe-west2
  options:
    project: recipe-api-dev
functions:
  recipes:
    handler: app.recipes.list_recipes
    events:
      - http: GET /recipes
  search:
    handler: app.recipes.search
    runtime: nodejs20
    events:
      - http: GET /search
""", "recipes", "list_recipes", "search"),
      user="I copied the search function from another project and validate says a service is either Python or Node.js. My search code is Python though.",
      steps=[
          S("get_validation"),
          S("read_file", path="app/recipes.py"),
          S("propose_plan", steps=["Remove `runtime: nodejs20` from `search` (it is Python, like the rest)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.search.runtime", value=None),
      ],
      final="""The copied function kept a line `runtime: nodejs20`, so pskit thought `search` was Node.js while the service is Python. One service can't mix the two.

`search` is Python in `app/recipes.py`, so I removed that line; it now uses the service runtime like `recipes` [docs/configuration.md#functions]. Validate: valid."""),

    # ------------------------------------------------------------------ 432  gcp dead_letter warning
    C(432, provider="gcp", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: invoice-worker
provider:
  name: gcp
  region: us-east1
  options:
    project: invoice-worker-prod
functions:
  work:
    handler: app.invoices.work
    events:
      - queue:
          name: invoice-jobs
          dead_letter: invoice-jobs-dlq
          max_receive: 4
""", "invoices", "work"),
      user="Prod on GCP validates, but warns queue.dead_letter is not applied. On SQS that redrive was important to us. What actually happens on GCP and what should the config look like?",
      steps=[
          S("get_validation"),
          S("search_docs", query="dead_letter gcp pubsub",
            docs=[D("docs/events.md", "queue", start="| Option | aws (SQS) |", end="On GCP a \"queue\" is a Pub/Sub topic with a push trigger, because GCP has no SQS-style pull trigger.")]),
          S("propose_plan", steps=["Remove `dead_letter` and `max_receive` from the queue event of `work` (not applied on GCP)",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.work.events.0.queue.dead_letter", value=None),
          S("set_config", path="functions.work.events.0.queue.max_receive", value=None),
      ],
      final="""On GCP a pskit queue is a Pub/Sub topic with an Eventarc push trigger. Eventarc manages the subscription, so pskit can't set a dead-letter topic, and a failed delivery is retried as a whole [docs/events.md#queue].

I removed `dead_letter` and `max_receive` so the file says what really happens. `pskit validate -p gcp -s prod`: valid, no warning.

If you need SQS-style redrive, keep this function on aws, or catch errors in the handler and publish the failed message to a second topic yourself [docs/providers.md#gcp-google-cloud-functions-2nd-gen]."""),

    # ------------------------------------------------------------------ 433  gcp database resource not external
    C(433, provider="gcp", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/configuration.md#resources", "docs/resources.md#secrets"],
      project=proj("""service: members-api
provider:
  name: gcp
  region: europe-west1
  options:
    project: members-api-dev
resources:
  members-db:
    type: database
    connection:
      host: db.example.com
      port: 5432
      password_env: MEMBERS_DB_PASSWORD
functions:
  members:
    handler: app.members.list_members
    events:
      - http: GET /members
""", "members", "list_members"),
      user="i add database on resources page and error say pskit does not create database. so pskit cant make cloud sql for me?",
      steps=[
          S("get_validation"),
          S("search_docs", query="database resource external",
            docs=[D("docs/configuration.md", "resources", start="| `type` |", end="pskit never creates or destroys an external resource |")]),
          S("propose_plan", steps=["Set `resources.members-db.external: true` (pskit uses your existing database)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.members-db.external", value=True),
      ],
      final="""Right, pskit doesn't create databases. A `database` resource always describes one you already have (`external: true`), and pskit gives its connection details to your functions [docs/configuration.md#resources].

I added `external: true` to `members-db`. Validate: valid. Create the Cloud SQL instance yourself (console or your own Terraform). The password stays out of the file through `password_env: MEMBERS_DB_PASSWORD` [docs/resources.md#secrets]."""),

    # ------------------------------------------------------------------ 434  gcp http method list
    C(434, provider="gcp", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: forms-api
provider:
  name: gcp
  region: us-west1
  options:
    project: forms-api-dev
functions:
  form:
    handler: app.forms.form
    events:
      - http:
          path: /form
          method: [GET, POST]
""", "forms", "form"),
      user="""Error: pskit.yml is invalid:
  - functions.form.events.0.method: Input should be a valid string

need GET and POST on /form""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace the event with two: `http: GET /form` and `http: POST /form`",
                                   "Validate for gcp"]),
          S("set_config", path="functions.form.events", value=[{"http": "GET /form"}, {"http": "POST /form"}]),
      ],
      final="""`method` takes one method per event [docs/events.md#http].

`form` now has two events, `- http: GET /form` and `- http: POST /form`; `event.http.method` tells them apart. `pskit validate` for gcp: valid. (`method: ANY` would accept every method instead.)"""),

    # ------------------------------------------------------------------ 435  gcp 6-field cron
    C(435, provider="gcp", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule"],
      project=proj("""service: cache-warmer
provider:
  name: gcp
  region: europe-west1
  options:
    project: cache-warmer-staging
functions:
  warm:
    handler: app.cache.warm
    events:
      - schedule: "0 */10 * * * *"
""", "cache", "warm"),
      user="We moved cache-warmer from an Azure timer trigger (NCRONTAB `0 */10 * * * *`) to GCP. Validation on staging rejects the cron. It should keep running every 10 minutes.",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule cron 5 field gcp azure",
            docs=[D("docs/events.md", "schedule", start="pskit converts the portable syntax", end="always UTC on Linux Consumption |")]),
          S("propose_plan", steps=["Replace the schedule of `warm` with the portable rate `10 minutes`",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.warm.events.0", value={"schedule": "10 minutes"}),
      ],
      final="""`0 */10 * * * *` is Azure's 6-field NCRONTAB (with seconds). pskit takes portable 5-field cron or a rate, and converts it per cloud [docs/events.md#schedule].

Changed the trigger to `- schedule: 10 minutes`; GCP Cloud Scheduler gets `*/10 * * * *`. `pskit validate -p gcp -s staging`: valid. The same line would also work if you ever deploy back to Azure."""),

    # ------------------------------------------------------------------ 436  azure auth KEY uppercase
    C(436, provider="azure", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: metrics-api
provider:
  name: azure
  region: eastus2
functions:
  push-metrics:
    handler: app.metrics.push
    events:
      - http:
          path: /metrics
          method: POST
          auth: KEY
""", "metrics", "push"),
      user="auth KEY give error should be none iam jwt or key. i write key!!",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `auth` of `push-metrics` to lowercase `key`",
                                   "Validate for azure"]),
          S("set_config", path="functions.push-metrics.events.0.http.auth", value="key"),
      ],
      final="""Almost: the value is case-sensitive and must be lowercase `key`, not `KEY` [docs/events.md#http].

Changed it to `auth: key` (Azure function key). Validate: valid."""),

    # ------------------------------------------------------------------ 437  azure dead_letter warning
    C(437, provider="azure", stage="staging", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=proj("""service: pdf-queue
provider:
  name: azure
  region: westeurope
functions:
  render:
    handler: app.pdf.render
    events:
      - queue:
          name: pdf-jobs
          dead_letter: pdf-jobs-failed
""", "pdf", "render"),
      user="azure warns dead_letter ignored. where do failed msgs go then? clean it up",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `dead_letter` from the queue event of `render`",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.render.events.0.queue.dead_letter", value=None),
      ],
      final="""Azure Storage Queues move poison messages to `<queue>-poison` on their own, so failed messages end up in `pdf-jobs-poison`, not `pdf-jobs-failed` [docs/events.md#queue].

Removed `dead_letter`. `pskit validate -p azure -s staging`: valid, no warning. Watch `pdf-jobs-poison` for failures."""),

    # ------------------------------------------------------------------ 438  azure choice string_equals (Logic Apps)
    C(438, provider="azure", stage="prod", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#choice-rules"],
      project=proj("""service: tiered-support
provider:
  name: azure
  region: northeurope
functions:
  priority:
    handler: app.support.priority
  standard:
    handler: app.support.standard
workflows:
  route-ticket:
    engine: native
    start_at: Tier
    states:
      Tier:
        type: choice
        choices:
          - {variable: "$.tier", string_equals: gold, next: Priority}
        default: Standard
      Priority: {type: task, function: priority, end: true}
      Standard: {type: task, function: standard, end: true}
""", "support", "priority", "standard"),
      user="Logic App workflow fails on prod: unsupported choice rule with string_equals. That's StringEquals from ASL. What's the pskit operator?",
      steps=[
          S("get_validation"),
          S("search_docs", query="choice rules operators equals",
            docs=[D("docs/workflows.md", "choice-rules", start="| Operator | Meaning |", end="combinators; can be nested |")]),
          S("propose_plan", steps=["Change the rule in `Tier` to `{variable: \"$.tier\", equals: gold, next: Priority}`",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.route-ticket.states.Tier.choices.0",
            value={"variable": "$.tier", "equals": "gold", "next": "Priority"}),
      ],
      final="""pskit choice rules use one `equals` for every type (string, number, bool, null) instead of ASL's `StringEquals` / `NumericEquals` [docs/workflows.md#choice-rules].

Changed the rule to `{variable: "$.tier", equals: gold, next: Priority}`. `pskit validate -p azure -s prod`: valid, still on the native Logic Apps engine."""),

    # ------------------------------------------------------------------ 439  azure function name too long
    C(439, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#top-level"],
      project=proj("""service: hr-tools
provider:
  name: azure
  region: westeurope
functions:
  generate-monthly-employee-attendance-summary-report-for-all-departments:
    handler: app.hr.attendance_report
    events:
      - schedule: "0 6 1 * *"
""", "hr", "attendance_report"),
      user="it says the function name must start with a letter and use letters, digits, - or _. It does?? I only used letters and dashes",
      steps=[
          S("get_validation"),
          S("search_docs", query="function name rules max length",
            docs=[D("docs/configuration.md", "top-level", start="| `functions` |", end="max 63 |")]),
          S("ask_user", question="The name is 71 characters and the limit is 63. Which shorter name do you want?",
            options=["attendance-report", "monthly-attendance-summary"], answer="attendance-report"),
          S("propose_plan", steps=["Add function `attendance-report` with the same handler and schedule",
                                   "Remove the long-named function",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.attendance-report",
            value={"handler": "app.hr.attendance_report", "events": [{"schedule": "0 6 1 * *"}]}),
          S("set_config", path="functions.generate-monthly-employee-attendance-summary-report-for-all-departments", value=None),
      ],
      final="""The characters were fine; the name was too long. Function names may have at most 63 characters, and yours had 71. The message lists the character rules, but length is part of the same check [docs/configuration.md#top-level].

The function is now `attendance-report`, with the same handler and the same monthly schedule. Validate: valid."""),

    # ------------------------------------------------------------------ 440  azure 6-field NCRONTAB in pskit.yml
    C(440, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=proj("""service: sensor-poll
provider:
  name: azure
  region: germanywestcentral
functions:
  poll:
    handler: app.sensors.poll
    events:
      - schedule: "0 */5 * * * *"
""", "sensors", "poll"),
      user="on azure portal timer is 0 */5 * * * *. why pskit dont accept azure own format?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure timer ncrontab schedule",
            docs=[D("docs/events.md", "schedule", start="pskit converts the portable syntax", end="always UTC on Linux Consumption |")]),
          S("propose_plan", steps=["Set the schedule of `poll` to `5 minutes`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.poll.events.0", value={"schedule": "5 minutes"}),
      ],
      final="""pskit.yml uses one portable format for all clouds (5-field cron or a rate). pskit writes Azure's 6-field NCRONTAB `0 */5 * * * *` itself [docs/events.md#schedule].

Changed to `- schedule: 5 minutes`. Validate: valid. Azure timers run in UTC."""),
]
