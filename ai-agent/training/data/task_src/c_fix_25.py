"""Category C (fix a validation error), batch 25 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 481  aws effect lowercase
    C(481, provider="aws", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: s3-browser
provider:
  name: aws
  region: us-east-1
  iam:
    statements:
      - effect: allow
        actions: ["s3:ListBucket"]
        resources: ["arn:aws:s3:::team-files"]
functions:
  browse:
    handler: app.browse.list_files
    events:
      - http: GET /files
""", "browse", "list_files"),
      user="iam effect: Input should be 'Allow' or 'Deny'. case sensitive?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.iam.statements.0.effect` to `Allow`",
                                   "Validate for aws"]),
          S("set_config", path="provider.iam.statements.0.effect", value="Allow"),
      ],
      final="""Yes, `effect` is `Allow` or `Deny`, capitalised. It also defaults to `Allow`, so you can drop the key [docs/configuration.md#provider].

Set `effect: Allow`. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 482  aws actions string
    C(482, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#provider", "docs/configuration.md#functions"],
      project=proj("""service: contact-form
provider:
  name: aws
  region: eu-west-1
functions:
  contact:
    handler: app.contact.send
    iam:
      statements:
        - actions: ses:SendEmail
          resources: ["*"]
    events:
      - http: POST /contact
""", "contact", "send"),
      user="I gave my contact function permission to send email under Permissions (IAM) and now: actions Input should be a valid list.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Write the action of `contact` as a list: `actions: [\"ses:SendEmail\"]`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.contact.iam.statements.0.actions", value=["ses:SendEmail"]),
      ],
      final="""`actions` is a list, even when there is only one permission [docs/configuration.md#provider].

It now reads `actions: ["ses:SendEmail"]`. Validate: valid. The statement is added only to `contact`'s own role [docs/configuration.md#functions]."""),

    # ------------------------------------------------------------------ 483  aws statement `resource` singular
    C(483, provider="aws", stage="staging", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: job-dispatch
provider:
  name: aws
  region: us-west-2
functions:
  dispatch:
    handler: app.jobs.dispatch
    iam:
      statements:
        - actions: ["sqs:SendMessage"]
          resource: arn:aws:sqs:us-west-2:123456789012:jobs
    events:
      - http: POST /dispatch
""", "jobs", "dispatch"),
      user="iamRoleStatements in serverless.yml had Resource. Here `resource` gives extra inputs not permitted. What's the key?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `resource` with `resources: [arn:aws:sqs:us-west-2:123456789012:jobs]` in the statement of `dispatch`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.dispatch.iam.statements.0",
            value={"actions": ["sqs:SendMessage"], "resources": ["arn:aws:sqs:us-west-2:123456789012:jobs"]}),
      ],
      final="""It's plural and a list: `resources` (default `["*"]`) [docs/configuration.md#provider].

The statement is now `{actions: ["sqs:SendMessage"], resources: ["arn:aws:sqs:us-west-2:123456789012:jobs"]}`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 484  aws state config string
    C(484, provider="aws", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#state-remote-terraform-backend"],
      project=proj("""service: orders-core
provider:
  name: aws
  region: us-east-1
  state:
    backend: s3
    config: bucket=acme-tf-state
functions:
  orders:
    handler: app.orders.handler
    events:
      - http: ANY /orders/{path+}
""", "orders", "handler"),
      user="We want remote state in the S3 bucket acme-tf-state, key orders-core/<stage>.tfstate, region us-east-1, lock table tf-locks. I wrote `config: bucket=acme-tf-state` and validation says provider.state: Input should be a valid dictionary.",
      steps=[
          S("get_validation"),
          S("search_docs", query="remote terraform state backend s3",
            docs=[D("docs/configuration.md", "state-remote-terraform-backend")]),
          S("propose_plan", steps=["Rewrite `provider.state.config` as a mapping: bucket, key `orders-core/${opt:stage}.tfstate`, region, dynamodb_table",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.state.config",
            value={"bucket": "acme-tf-state", "key": "orders-core/${opt:stage}.tfstate",
                   "region": "us-east-1", "dynamodb_table": "tf-locks"}),
      ],
      final="""`state.config` is a mapping of backend settings, not a `key=value` string [docs/configuration.md#state-remote-terraform-backend].

Now:

```yaml
provider:
  state:
    backend: s3
    config:
      bucket: acme-tf-state
      key: orders-core/${opt:stage}.tfstate
      region: us-east-1
      dynamodb_table: tf-locks
```

`pskit validate -p aws -s prod`: valid. `${opt:stage}` gives each stage its own state file."""),

    # ------------------------------------------------------------------ 485  aws timeout "30s"
    C(485, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: shortlinks
provider:
  name: aws
  region: eu-central-1
functions:
  redirect:
    handler: app.links.redirect
    timeout: 30s
    events:
      - http: GET /{code}
""", "links", "redirect"),
      user="""Error: pskit.yml is invalid:
  - functions.redirect.timeout: Input should be a valid integer, unable to parse string as an integer""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.redirect.timeout` to 30",
                                   "Validate for aws"],
            result={"decision": "approved", "note": "make it 5, redirects must be fast"}),
          S("set_config", path="functions.redirect.timeout", value=5),
      ],
      final="""`timeout` is a plain number of seconds; the `s` made it a string [docs/configuration.md#functions].

Following your note, I set `timeout: 5` (not 30). `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 486  aws rate 1 week
    C(486, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=proj("""service: weekly-digest
provider:
  name: aws
  region: eu-west-1
functions:
  digest:
    handler: app.digest.send
    events:
      - schedule:
          rate: 1 week
""", "digest", "send"),
      user="rate 1 week not allowed? i want once a week, monday morning better",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule rate cron weekly",
            docs=[D("docs/events.md", "schedule", end="name: morning-report               # optional, used in the resource name")]),
          S("ask_user", question="Rates go up to days, so a weekly job is a cron. Which time on Monday (UTC)?",
            options=["08:00 UTC", "06:00 UTC"], answer="08:00"),
          S("propose_plan", steps=["Replace the rate of `digest` with `cron: \"0 8 * * 1\"` (Mondays 08:00 UTC)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.digest.events.0.schedule", value={"cron": "0 8 * * 1"}),
      ],
      final="""A `rate` only knows minutes, hours and days, so `1 week` is rejected. "Every Monday" is a cron [docs/events.md#schedule].

Now `schedule: {cron: "0 8 * * 1"}`: every Monday at 08:00 UTC. Validate: valid. Add `timezone: Europe/Berlin` (for example) if 08:00 should be local time; AWS honours it."""),

    # ------------------------------------------------------------------ 487  aws function-level architecture arm
    C(487, provider="aws", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: pdf-render
provider:
  name: aws
  region: us-east-1
functions:
  render:
    handler: app.render.pdf
    architecture: arm
    memory: 1536
    events:
      - http: POST /render
  health:
    handler: app.render.health
    events:
      - http: GET /health
""", "render", "pdf", "health"),
      user="render only on graviton. architecture arm → error. prod",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.render.architecture` to `arm64`",
                                   "Validate for aws, stage prod"]),
          S("set_config", path="functions.render.architecture", value="arm64"),
      ],
      final="""Value must be `x86_64` or `arm64` [docs/configuration.md#functions].

Set `render.architecture: arm64`; `health` stays x86_64. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 488  aws iam statement typo Allw
    C(488, provider="aws", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: photo-album
provider:
  name: aws
  region: eu-west-3
  iam:
    statements:
      - effect: Allw
        actions: ["s3:GetObject", "s3:PutObject"]
        resources: ["arn:aws:s3:::photo-album-images/*"]
functions:
  upload:
    handler: app.album.upload
    events:
      - http: POST /photos
""", "album", "upload"),
      user="why can't I deploy to aws? it says effect should be Allow or Deny but I didn't change anything there... I think",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Fix the typo `Allw` → `Allow` in `provider.iam.statements.0.effect`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.iam.statements.0.effect", value="Allow"),
      ],
      final="""There was a typo in the permission: `effect: Allw` instead of `Allow` [docs/configuration.md#provider].

Fixed it. Validate for staging: valid, so you can deploy from the **Deploy** page. Tip: the **YAML** page shows a diff, so you can see what changed since your last save."""),

    # ------------------------------------------------------------------ 489  gcp resources functions string
    C(489, provider="gcp", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resources.md#fields"],
      project=proj("""service: scoreboard
provider:
  name: gcp
  region: europe-west1
  options:
    project: scoreboard-dev
resources:
  scores:
    type: topic
    functions: publisher
functions:
  publisher:
    handler: app.scores.publish
    events:
      - http: POST /scores
  listener:
    handler: app.scores.listen
    events:
      - topic: {resource: scores}
""", "scores", "publish", "listen"),
      user="resources scores functions: Input should be a valid list. only publisher need it",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.scores.functions` to `[publisher, listener]`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": "no, only publisher like I said"}),
          S("set_config", path="resources.scores.functions", value=["publisher"]),
      ],
      final="""`functions` on a resource is a list of function names [docs/resources.md#fields].

As you said, it is `functions: [publisher]` now (I had proposed adding `listener` too; the topic trigger of `listener` works without the binding). Validate: valid."""),

    # ------------------------------------------------------------------ 490  gcp nested connection value
    C(490, provider="gcp", stage="staging", mode="ask", page="Resources", persona="detailed_spec",
      sources=["docs/resources.md#fields", "docs/resources.md#runtime-api"],
      project=proj("""service: ledger-api
provider:
  name: gcp
  region: us-central1
  options:
    project: ledger-api-staging
resources:
  ledger-db:
    type: database
    external: true
    connection:
      host: ledger-db.example.com
      port: 5432
      pool:
        min: 2
        max: 10
      password_env: LEDGER_DB_PASSWORD
functions:
  entries:
    handler: app.ledger.entries
    events:
      - http: GET /entries
""", "ledger", "entries"),
      user="Staging validation rejects ledger-db: `connection.pool must be a scalar`. The handler needs min and max pool sizes. Keep both values available to the code.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace `connection.pool` with two scalar keys: `pool_min: 2` and `pool_max: 10`",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.ledger-db.connection.pool", value=None),
          S("set_config", path="resources.ledger-db.connection.pool_min", value=2),
          S("set_config", path="resources.ledger-db.connection.pool_max", value=10),
      ],
      final="""Connection values become one environment variable each, so they must be scalars (string, number, bool), not a nested mapping [docs/resources.md#fields].

`pool` is now two keys, `pool_min: 2` and `pool_max: 10`. `pskit validate -p gcp -s staging`: valid. In the handler: `db = resource("ledger-db")`, then `int(db["pool_min"])` / `int(db["pool_max"])` [docs/resources.md#runtime-api]."""),

    # ------------------------------------------------------------------ 491  gcp timeout 0 on a queue worker
    C(491, provider="gcp", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#functions", "docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=proj("""service: thumbnailer
provider:
  name: gcp
  region: europe-west1
  options:
    project: thumbnailer-dev
functions:
  thumbs:
    handler: app.thumbs.make
    timeout: 0
    events:
      - queue: thumb-requests
""", "thumbs", "make"),
      user="I set timeout: 0 meaning no limit and got 'greater than or equal to 1'. What's the longest I can give this Pub/Sub worker?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.thumbs.timeout` to 540 (max for event-triggered functions on GCP)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.thumbs.timeout", value=540),
      ],
      final="""There is no "no limit" value: `timeout` is 1-3600 s [docs/configuration.md#functions], and event-triggered functions on GCP stop at 540 s [docs/events.md#gcp-multi-trigger-functions-are-split-automatically].

Set `thumbs.timeout: 540`. `pskit validate` for gcp: valid."""),

    # ------------------------------------------------------------------ 492  gcp ${file()} wrong extension
    C(492, provider="gcp", stage="prod", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: feature-flags
provider:
  name: gcp
  region: europe-west1
  options:
    project: feature-flags-prod
  environment: ${file(config/flags.json)}
functions:
  flags:
    handler: app.flags.get_flags
    events:
      - http: GET /flags
""", "flags", "get_flags", extra={"config/flags.yml": "NEW_CHECKOUT: \"true\"\nDARK_MODE: \"false\"\n"}),
      user="""Error: ${file(config/flags.json)}: .\\config\\flags.json does not exist

it's there, I can see it in the Code page""",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["Point the variable at the real file: `${file(config/flags.yml)}`",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.environment", value="${file(config/flags.yml)}"),
      ],
      final="""The file in your project is `config/flags.yml`, not `.json`. `${file(...)}` needs the exact name, and `.yml` files are parsed too [docs/configuration.md#variables].

Changed it to `environment: ${file(config/flags.yml)}`. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 493  gcp auth key
    C(493, provider="gcp", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: device-api
provider:
  name: gcp
  region: asia-south1
  options:
    project: device-api-staging
functions:
  report:
    handler: app.devices.report
    events:
      - http:
          path: /report
          method: POST
          auth: key
""", "devices", "report"),
      user="our devices send api key header. gcp say auth key not supported, only none or iam. devices cant do google login",
      steps=[
          S("get_validation"),
          S("search_docs", query="http auth key gcp",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("propose_plan", steps=["Set `auth` of `/report` to `none` (devices can't use Google credentials)",
                                   "Validate for gcp, stage staging",
                                   "Then: check the device key in the handler against an env var"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.report.events.0.http.auth", value="none"),
      ],
      final="""On GCP pskit has only `none` or `iam` (Google credentials). `key` is an Azure function key, not available on GCP [docs/events.md#http].

Your devices can't use `iam`, so `/report` is now `auth: none`. Validate for staging: valid.

The route is public now, so check the key yourself: put it in `environment: {DEVICE_KEY: ${env:DEVICE_KEY}}` and compare `event.http.headers.get("x-api-key")` with `ctx.env["DEVICE_KEY"]` in `report`, raising `Unauthorized` when it is wrong. Want me to add that?"""),

    # ------------------------------------------------------------------ 494  gcp memory 65536
    C(494, provider="gcp", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: genome-batch
provider:
  name: gcp
  region: us-central1
  options:
    project: genome-batch-prod
functions:
  align:
    handler: app.genome.align
    memory: 65536
    timeout: 3600
    events:
      - http: POST /align
""", "genome", "align"),
      user="memory 65536 rejected (≤ 32768). set max",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.align.memory` to 32768",
                                   "Validate for gcp, stage prod"]),
          S("set_config", path="functions.align.memory", value=32768),
      ],
      final="""pskit's `memory` range is 64-32768 MB [docs/configuration.md#functions].

Set `align.memory: 32768`. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 495  azure resource key Jobs -> queue name
    C(495, provider="azure", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/configuration.md#resources", "docs/events.md#queue"],
      project=proj("""service: print-jobs
provider:
  name: azure
  region: westeurope
resources:
  Jobs: {type: queue}
functions:
  printer:
    handler: app.printer.print_job
    events:
      - queue: {resource: Jobs}
""", "printer", "print_job"),
      user="I made a queue called Jobs on the Resources page. Now the printer function says queue name 'Jobs' must be lowercase. Where do I change it?",
      steps=[
          S("get_validation"),
          S("search_docs", query="resource name native name",
            docs=[D("docs/configuration.md", "resources", start="| Key | Default | |", end="| `connection` |")]),
          S("propose_plan", steps=["Give the resource a lowercase native name: `resources.Jobs.name: jobs`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="resources.Jobs.name", value="jobs"),
      ],
      final="""The queue gets its real name from the resource, and without `name` that is the key `Jobs`. Azure queue names must be lowercase [docs/configuration.md#resources] [docs/events.md#queue].

I added `name: jobs` to the `Jobs` resource; the key stays, so nothing else had to change. Validate: valid."""),

    # ------------------------------------------------------------------ 496  azure python3.8
    C(496, provider="azure", stage="staging", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#default-runtime", "docs/providers.md#providers"],
      project=proj("""service: legacy-billing
provider:
  name: azure
  region: eastus
  runtime: python3.8
functions:
  bill:
    handler: app.billing.bill
    events:
      - schedule: "0 1 * * *"
""", "billing", "bill"),
      user="This came from a python3.8 Lambda. Azure staging: runtime must be python3.9 .. python3.14. Which version do I pick for Azure?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure python runtimes default",
            docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| [`alibaba`]")]),
          S("ask_user", question="Azure runs python3.9-3.12. Use the closest to 3.8 (python3.9), or let pskit pick its default (python3.12)?",
            options=["python3.9", "default (python3.12)"], answer="python3.9 for now"),
          S("propose_plan", steps=["Set `provider.runtime` to python3.9",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.runtime", value="python3.9"),
      ],
      final="""pskit supports python3.9 and newer, and Azure runs 3.9-3.12 [docs/providers.md#providers].

Set `provider.runtime: python3.9`, the closest to your 3.8 code. `pskit validate -p azure -s staging`: valid. Later you can drop the pin to get python3.12 [docs/configuration.md#default-runtime]."""),

    # ------------------------------------------------------------------ 497  azure cors max_age "10m"
    C(497, provider="azure", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: survey-api
provider:
  name: azure
  region: canadacentral
functions:
  answers:
    handler: app.survey.answers
    events:
      - http:
          path: /answers
          method: POST
          cors:
            origins: ["https://survey.example.com"]
            max_age: 10m
""", "survey", "answers"),
      user="""Error: pskit.yml is invalid:
  - functions.answers.events.0.cors.bool: Input should be a valid boolean
  - functions.answers.events.0.cors.CorsConfig.max_age: Input should be a valid integer, unable to parse string as an integer""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `cors.max_age` of `answers` to 600 (seconds)",
                                   "Validate for azure"]),
          S("set_config", path="functions.answers.events.0.http.cors.max_age", value=600),
      ],
      final="""`cors.max_age` is a number of seconds; `10m` isn't parsed [docs/events.md#http].

Set `max_age: 600` (10 minutes). `pskit validate` for azure: valid."""),

    # ------------------------------------------------------------------ 498  azure embedded workflow long wait -> native
    C(498, provider="azure", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#embedded-orchestrator", "docs/workflows.md#engines", "docs/workflows.md#compiler-notes-and-limits"],
      project=proj("""service: trial-flow
provider:
  name: azure
  region: westeurope
functions:
  start-trial:
    handler: app.trial.start
  remind:
    handler: app.trial.remind
workflows:
  trial:
    start_at: Start
    states:
      Start: {type: task, function: start-trial, next: WaitDay}
      WaitDay: {type: wait, seconds: 86400, next: Remind}
      Remind: {type: task, function: remind, end: true}
""", "trial", "start", "remind"),
      user="The trial workflow waits one day before the reminder. Prod validation on Azure passes but warns about the embedded engine and the 600 s cap. That can't work with a 24 h wait, right? Make it work on Azure.",
      steps=[
          S("get_validation"),
          S("search_docs", query="embedded engine long wait azure native",
            docs=[D("docs/workflows.md", "embedded-orchestrator", start="- The **whole run must fit in one function invocation**", end="`pskit validate` warns about this.")]),
          S("search_docs", query="logic apps run timeout default",
            docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="A run stops after 5000 states", end="(default 1 hour).")]),
          S("propose_plan", steps=["Set `workflows.trial.engine: native` (Azure Logic App, no function time limit for the wait)",
                                   "Set `workflows.trial.timeout: 90000` (25 h; a Logic App run stops after 1 hour by default)",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.trial.engine", value="native"),
          S("set_config", path="workflows.trial.timeout", value=90000),
      ],
      final="""Right: on the embedded engine the whole run must fit in one function call (600 s on Azure), so a 24-hour `wait` can't work [docs/workflows.md#embedded-orchestrator].

- `engine: native`: `trial` is deployed as an Azure Logic App, which handles the wait itself [docs/workflows.md#engines].
- `timeout: 90000` (25 h): a Logic App run otherwise stops after 1 hour [docs/workflows.md#compiler-notes-and-limits].

`pskit validate -p azure -s prod`: valid, no warning.

The caller now starts it with `POST` to the Logic App's callback URL (`pskit info` shows it). With a one-day run, also set `options.sync: false` so the caller gets `202` at once instead of waiting for the output."""),

    # ------------------------------------------------------------------ 499  azure storage resource key Uploads
    C(499, provider="azure", stage="staging", mode="auto", page="Resources", persona="terse_expert",
      sources=["docs/configuration.md#resources", "docs/events.md#storage"],
      project=proj("""service: doc-converter
provider:
  name: azure
  region: northeurope
resources:
  Uploads: {type: storage}
functions:
  convert:
    handler: app.convert.to_pdf
    events:
      - storage: {resource: Uploads, suffix: .docx}
""", "convert", "to_pdf"),
      user="container name 'Uploads' must be lowercase — it's the resource key",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `resources.Uploads.name: uploads` (native container name)",
                                   "Validate for azure, stage staging"]),
          S("set_config", path="resources.Uploads.name", value="uploads"),
      ],
      final="""Without `name`, the native name is the resource key, and Azure container names must be lowercase [docs/configuration.md#resources] [docs/events.md#storage].

Added `name: uploads` to the `Uploads` resource. `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 500  azure storage events [modified]
    C(500, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=proj("""service: config-watch
provider:
  name: azure
  region: westeurope
functions:
  reload:
    handler: app.config.reload
    events:
      - storage:
          bucket: app-config
          events: [updated]
""", "config", "reload"),
      user="azure blob trigger fire on update, so i write events [updated]. pskit say should be created or deleted??",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage events created updated azure",
            docs=[D("docs/events.md", "storage", start="| azure |", end="in another account need `options.storage_connection` |")]),
          S("propose_plan", steps=["Set the storage events of `reload` to `[created]` (on Azure this covers created and updated blobs)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.reload.events.0.storage.events", value=["created"]),
      ],
      final="""pskit has only `created` and `deleted`. On Azure the blob trigger behind `created` fires for **created/updated** blobs, so `created` is what you want [docs/events.md#storage].

Set `events: [created]` on `reload`. Validate: valid. Every upload or overwrite of a file in `app-config` now runs `reload`."""),
]
