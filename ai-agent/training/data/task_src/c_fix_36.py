"""Category C (fix a validation error), batch 36 (aws/gcp/azure): user-experience variety. Hand-written;
assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 701  aws beginner: rate and cron "to be safe"
    C(701, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      project=proj("""service: plant-watering
provider:
  name: aws
  region: eu-west-1
functions:
  remind:
    handler: app.plants.remind
    events:
      - schedule:
          rate: 1 day
          cron: "0 9 * * *"
""", "plants", "remind"),
      user="I wrote both rate and cron in my schedule to be safe, and now it says it needs exactly one. I just want a reminder every morning at 9.",
      steps=[
          S("get_validation"),
          S("propose_plan", say="A schedule is either a rate (every N minutes/hours/days, counted from the deploy) or a cron (fixed clock times). \"Every morning at 9\" is the cron.",
            steps=["Keep `cron: \"0 9 * * *\"` and remove `rate` from `remind`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.remind.events.0.schedule.rate", value=None),
      ],
      final="""A schedule takes exactly one of `rate` or `cron`; with both, pskit can't know which one you mean [docs/events.md#schedule].

`remind` now has only `cron: "0 9 * * *"` (09:00 every day, UTC; add `timezone: Europe/London` or similar for local time). Validate for aws: valid."""),

    # ------------------------------------------------------------------ 702  aws informal: memory 50 to save money
    C(702, provider="aws", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: url-shortener
provider:
  name: aws
  region: ap-southeast-1
functions:
  redirect:
    handler: app.links.redirect
    memory: 50
    events:
      - http: GET /{code}
""", "links", "redirect"),
      user="i put memory 50 for save money, it say must greater or equal 64. ok what is cheap value then",
      steps=[
          S("get_validation"),
          S("propose_plan", say="pskit accepts 64 MB and up. I'd use 128 MB, the usual smallest Lambda size; a redirect needs very little memory.",
            steps=["Set `functions.redirect.memory` to 128", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.redirect.memory", value=128),
      ],
      final="""`memory` must be at least 64 MB [docs/configuration.md#functions]; 50 was below that.

`redirect` now has `memory: 128`. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 703  aws why can't I deploy: two provider errors
    C(703, provider="aws", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/providers.md#aws-aws-lambda"],
      project=proj("""service: partner-api
provider:
  name: aws
  region: eu-central-1
functions:
  partners:
    handler: app.partners.list_partners
    timeout: 1000
    events:
      - http:
          path: /partners
          method: GET
          auth: key
""", "partners", "list_partners"),
      user="Why can't I deploy to AWS? This service ran on Azure before and we just switched the provider.",
      steps=[
          S("get_validation"),
          S("ask_user", say="Two Azure leftovers: `timeout: 1000` (Lambda max is 900 s) and `auth: key` (no API keys on AWS HTTP APIs).",
            question="For `/partners` AWS offers `jwt` (your identity provider's tokens), `iam` (AWS-signed requests) or `none`. Which one do partners use?",
            options=["jwt", "iam", "none"], answer="iam, they call from their AWS accounts"),
          S("propose_plan", steps=["Set `auth: iam` on `GET /partners`", "Set `functions.partners.timeout` to 30 (API Gateway waits 30 s at most)",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.partners.events.0.http.auth", value="iam"),
          S("set_config", path="functions.partners.timeout", value=30),
          S("validate"),
      ],
      final="""The config still had two Azure settings that AWS doesn't support [docs/events.md#http] [docs/providers.md#aws-aws-lambda]:
1. `auth: key` -> `auth: iam` (callers sign requests with their AWS credentials).
2. `timeout: 1000` -> `30`, because an HTTP call through API Gateway can't take longer.

`pskit validate -p aws -s prod`: valid. Deploy from the Deploy page; for `prod` studio asks you to type a confirmation."""),

    # ------------------------------------------------------------------ 704  aws terse: dead_letter: true
    C(704, provider="aws", stage="staging", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=proj("""service: webhook-relay
provider:
  name: aws
  region: us-east-1
functions:
  relay:
    handler: app.relay.forward
    events:
      - queue:
          name: webhooks
          dead_letter: true
          max_receive: 3
""", "relay", "forward"),
      user="dead_letter: true -> valid string?? just want a dlq",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`dead_letter: webhooks-dlq` (the DLQ's name, pskit creates it)", "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.relay.events.0.queue.dead_letter", value="webhooks-dlq"),
      ],
      final="""`dead_letter` is the DLQ name, not a flag [docs/events.md#queue]. Now `dead_letter: webhooks-dlq`, `max_receive: 3`. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 705  aws wrong fix: copy the renamed function
    C(705, provider="aws", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: signup-flow
provider:
  name: aws
  region: us-east-1
functions:
  create-account:
    handler: app.signup.create_account
  send-mail:
    handler: app.signup.send_mail
workflows:
  signup:
    start_at: Create
    states:
      Create: {type: task, function: create-account, next: Welcome}
      Welcome: {type: task, function: send-email, end: true}
""", "signup", "create_account", "send_mail"),
      user="I renamed send-email to send-mail and now the workflow references unknown function 'send-email'. I'll just add a send-email function again as a copy of send-mail, fine?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="A copy would work but deploys a second Lambda with the same code that you'd have to keep in sync. Pointing the state at the new name is smaller.",
            steps=["Set `Welcome.function` to `send-mail`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.signup.states.Welcome.function", value="send-mail"),
      ],
      final="""Task states name a function by its key under `functions`, and that key was renamed [docs/workflows.md#workflow-keys].

`Welcome` now calls `send-mail`; no duplicate function. Validate for aws: valid. When you rename a function on the Functions page, check **Workflows** for states that still use the old name."""),

    # ------------------------------------------------------------------ 706  aws auto: catch without next
    C(706, provider="aws", stage="dev", mode="auto", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#retry-and-catch", "docs/workflows.md#state-types"],
      project=proj("""service: payout-flow
provider:
  name: aws
  region: eu-west-1
functions:
  payout:
    handler: app.payouts.run
workflows:
  payouts:
    start_at: Pay
    states:
      Pay:
        type: task
        function: payout
        catch:
          - errors: [States.ALL]
        end: true
""", "payouts", "run"),
      user="""Error: pskit.yml is invalid:
  - workflows.payouts.states.Pay.catch.0.next: Field required""",
      steps=[
          S("get_validation"),
          S("search_docs", query="catch next state",
            docs=[D("docs/workflows.md", "retry-and-catch", start="Error names are the")]),
          S("propose_plan", steps=["Add `PayoutFailed: {type: fail, error: PayoutFailed, cause: payout raised an error}`",
                                   "Set the catcher's `next: PayoutFailed`", "Validate for aws"]),
          S("set_config", path="workflows.payouts.states.PayoutFailed",
            value={"type": "fail", "error": "PayoutFailed", "cause": "payout raised an error"}),
          S("set_config", path="workflows.payouts.states.Pay.catch.0.next", value="PayoutFailed"),
      ],
      final="""A catcher must say where to go: its `next` state [docs/workflows.md#retry-and-catch].

Added a `fail` state `PayoutFailed` and pointed the catcher at it, so errors end the run as failed with a clear name [docs/workflows.md#state-types]. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 707  aws ask_user: jwt issuer/audience (Auth0)
    C(707, provider="aws", stage="staging", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http"],
      project=proj("""service: courses-api
provider:
  name: aws
  region: us-west-2
functions:
  courses:
    handler: app.courses.list_courses
    events:
      - http:
          path: /courses
          method: GET
          auth: jwt
""", "courses", "list_courses"),
      user="Switched /courses from the Lambda authorizer to auth: jwt as the docs say. Now: jwt auth needs authorizer.issuer and authorizer.audience. We use Auth0.",
      steps=[
          S("get_validation"),
          S("ask_user", question="I need two values from your Auth0 tenant: the issuer (your Auth0 domain URL, ending with `/`) and the API audience (the API identifier).",
            answer="issuer https://courses.eu.auth0.example.com/ audience https://api.courses.example.com"),
          S("propose_plan", steps=["Add `authorizer: {issuer: https://courses.eu.auth0.example.com/, audience: [https://api.courses.example.com]}` to `/courses`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.courses.events.0.http.authorizer",
            value={"issuer": "https://courses.eu.auth0.example.com/", "audience": ["https://api.courses.example.com"]}),
      ],
      final="""On AWS `auth: jwt` is an API Gateway JWT authorizer, and it needs the token issuer and audience [docs/events.md#http].

`/courses` now has issuer `https://courses.eu.auth0.example.com/` and audience `https://api.courses.example.com`. `pskit validate -p aws -s staging`: valid. Clients send `Authorization: Bearer <Auth0 access token>`."""),

    # ------------------------------------------------------------------ 708  gcp beginner: resource key case
    C(708, provider="gcp", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=["docs/events.md#events-backed-by-a-resource"],
      project=proj("""service: photo-album
provider:
  name: gcp
  region: europe-west1
  options:
    project: photo-album-dev
resources:
  photos:
    type: storage
functions:
  make-thumb:
    handler: app.album.make_thumb
    events:
      - storage:
          resource: Photos
""", "album", "make_thumb"),
      user="It says uses unknown resource 'Photos'; known: photos. But that's the same thing??",
      steps=[
          S("get_validation"),
          S("propose_plan", say="Almost: names in pskit.yml are case-sensitive, so `Photos` and `photos` are two different names.",
            steps=["Set `resource: photos` on the trigger of `make-thumb`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.make-thumb.events.0.storage.resource", value="photos"),
      ],
      final="""`resource:` must match the key under `resources:` exactly, including capitals [docs/events.md#events-backed-by-a-resource].

The trigger now uses `resource: photos`. Validate for gcp: valid. Picking the resource from the list in the trigger form on the Functions page avoids this."""),

    # ------------------------------------------------------------------ 709  gcp informal: workflow unknown function
    C(709, provider="gcp", stage="staging", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#workflow-keys"],
      project=proj("""service: image-pipeline
provider:
  name: gcp
  region: asia-northeast1
  options:
    project: image-pipeline-stg
functions:
  resize-image:
    handler: app.images.resize
  tag-image:
    handler: app.images.tag
workflows:
  process:
    start_at: Resize
    states:
      Resize: {type: task, function: resize, next: Tag}
      Tag: {type: task, function: tag-image, end: true}
""", "images", "resize", "tag"),
      user="workflow say references unknown function 'resize'. but resize is there, i see it in code",
      steps=[
          S("get_validation"),
          S("propose_plan", say="`resize` is the Python function in `app/images.py`; the workflow needs the pskit function name, which is `resize-image`.",
            steps=["Set `Resize.function` to `resize-image`", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.process.states.Resize.function", value="resize-image"),
      ],
      final="""A task's `function` is the name under `functions:` in pskit.yml, not the Python function name [docs/workflows.md#workflow-keys].

`Resize` now calls `resize-image` (whose handler is `app.images.resize`). `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 710  gcp pasted partial: valid string (dead_letter true)
    C(710, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#queue"],
      project=proj("""service: event-sink
provider:
  name: gcp
  region: us-east1
  options:
    project: event-sink-dev
functions:
  sink:
    handler: app.events.sink
    events:
      - queue:
          name: raw-events
          dead_letter: true
""", "events", "sink"),
      user="Input should be a valid string — where?",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue dead_letter gcp",
            docs=[D("docs/events.md", "queue", start="| Option | aws (SQS)", end="| partial batch failure |")]),
          S("propose_plan", say="It's `dead_letter: true` on the `raw-events` trigger of `sink`: it expects a queue name. On GCP pskit doesn't apply `dead_letter` anyway (only a warning).",
            steps=["Remove `dead_letter` from the trigger", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sink.events.0.queue.dead_letter", value=None),
      ],
      final="""`dead_letter` takes the name of a dead-letter queue, not `true`, and on GCP it is ignored [docs/events.md#queue].

Removed it from `sink`. Validate for gcp: valid, no warnings. Failed Pub/Sub deliveries are retried as a whole; handle bad messages in the handler."""),

    # ------------------------------------------------------------------ 711  gcp "fix the problems on the Functions page"
    C(711, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions", "docs/events.md#schedule"],
      project=proj("""service: price-watch
provider:
  name: gcp
  region: europe-west3
  options:
    project: price-watch-dev
functions:
  scrape:
    handler: app.prices.scrape
    memory: 40000
    events:
      - schedule:
          rate: 1 hour
          cron: "0 * * * *"
""", "prices", "scrape"),
      user="Fix the problems on the Functions page please",
      steps=[
          S("get_validation"),
          S("ask_user", say="Two problems on `scrape`: memory 40000 MB is above the 32768 maximum, and the schedule has both `rate` and `cron`.",
            question="How much memory does the scraper really need?", options=["512", "1024", "2048"], answer="1024"),
          S("propose_plan", steps=["Set `scrape.memory` to 1024", "Remove `rate` (keep `cron: \"0 * * * *\"`, every hour on the hour)", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.scrape.memory", value=1024),
          S("set_config", path="functions.scrape.events.0.schedule.rate", value=None),
      ],
      final="""1. `memory` must be 64-32768 MB [docs/configuration.md#functions]; now 1024.
2. A schedule takes `rate` or `cron`, not both [docs/events.md#schedule]; kept the cron, every hour.

Validate for gcp: valid; the Functions page has no red marks now."""),

    # ------------------------------------------------------------------ 712  gcp wrong fix: unset ${env:...} for project
    C(712, provider="gcp", stage="staging", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#variables", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: quote-engine
provider:
  name: gcp
  region: europe-west1
functions:
  quote:
    handler: app.quotes.quote
    events:
      - http: POST /quote
""", "quotes", "quote"),
      user="GCP needs provider.options.project. I don't want the id in the file, so set project to ${env:GOOGLE_CLOUD_PROJECT}; it's set on our CI.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.options.project: ${env:GOOGLE_CLOUD_PROJECT}`", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options", value={"project": "${env:GOOGLE_CLOUD_PROJECT}"}),
          S("ask_user", say="That works on CI, but here the variable isn't set, so studio and every local `pskit validate` now fail. A default fixes that.",
            question="Which project id should be the default when GOOGLE_CLOUD_PROJECT is not set? (CI keeps using its own value.)",
            answer="quote-engine-staging"),
          S("propose_plan", steps=["Set `project: ${env:GOOGLE_CLOUD_PROJECT, quote-engine-staging}`", "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.project", value="${env:GOOGLE_CLOUD_PROJECT, quote-engine-staging}"),
      ],
      final="""`${env:NAME}` fails when the variable isn't set, and it isn't set in this studio session [docs/configuration.md#variables].

`project` is now `${env:GOOGLE_CLOUD_PROJECT, quote-engine-staging}`: CI uses its variable, everywhere else the default. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 713  gcp rejected plan: 6-field cron meaning
    C(713, provider="gcp", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=proj("""service: queue-monitor
provider:
  name: gcp
  region: us-central1
  options:
    project: queue-monitor-dev
functions:
  check-backlog:
    handler: app.monitor.check_backlog
    events:
      - schedule: "0 */2 * * * *"
""", "monitor", "check_backlog"),
      user="Copied the cron from our Azure timer: 0 */2 * * * *. pskit says cron must be a standard 5-field expression.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Drop the first field: `schedule: \"0 */2 * * *\"`", "Validate for gcp"],
            result={"decision": "rejected", "note": "That's every 2 hours! On Azure the first field is seconds, it ran every 2 minutes."}),
          S("propose_plan", say="You're right: in NCRONTAB the first field is seconds, so the second field `*/2` is minutes.",
            steps=["Set `schedule: \"*/2 * * * *\"` (every 2 minutes)", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.check-backlog.events.0", value={"schedule": "*/2 * * * *"}),
      ],
      final="""pskit uses the 5-field cron `minute hour day month weekday` everywhere [docs/events.md#schedule]. The Azure expression had a leading seconds field.

`check-backlog` now runs `*/2 * * * *`, every 2 minutes as before. Validate for gcp: valid. (`2 minutes` as a rate would work too.)"""),

    # ------------------------------------------------------------------ 714  gcp auto: "10 mins"
    C(714, provider="gcp", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=proj("""service: stock-sync
provider:
  name: gcp
  region: europe-west1
  options:
    project: stock-sync-prod
functions:
  sync:
    handler: app.stock.sync
    events:
      - schedule: 10 mins
""", "stock", "sync"),
      user="schedule '10 mins' -> 5-field cron error. fix",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`schedule: 10 minutes`", "Validate for gcp, stage prod"]),
          S("set_config", path="functions.sync.events.0", value={"schedule": "10 minutes"}),
      ],
      final="""`mins` isn't a rate unit, so the string was read as a cron. Rate units are minute(s), hour(s), day(s) [docs/events.md#schedule]. Now `10 minutes`. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 715  azure beginner: storage events [uploaded]
    C(715, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage"],
      project=proj("""service: cv-inbox
provider:
  name: azure
  region: westeurope
functions:
  parse-cv:
    handler: app.cvs.parse
    events:
      - storage:
          bucket: cv-uploads
          events: [uploaded]
""", "cvs", "parse"),
      user="I want parse-cv to run when someone uploads a CV. It says Input should be 'created' or 'deleted'. What word is right?",
      steps=[
          S("get_validation"),
          S("propose_plan", say="An upload is `created` in pskit. It's also the default, so the line can simply go.",
            steps=["Remove `events: [uploaded]` from the trigger (default `[created]`)", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.parse-cv.events.0.storage.events", value=None),
      ],
      final="""Storage triggers know two words, `created` and `deleted`, and the default is `[created]` [docs/events.md#storage]. On Azure only `created` (new or updated blobs) is possible.

`parse-cv` now has `storage: {bucket: cv-uploads}` and runs for every uploaded CV. Validate for azure: valid."""),

    # ------------------------------------------------------------------ 716  azure informal: 2 hours, two limits
    C(716, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#functions", "docs/providers.md#providers"],
      project=proj("""service: erp-import
provider:
  name: azure
  region: germanywestcentral
functions:
  import-orders:
    handler: app.erp.import_orders
    timeout: 7200
    events:
      - schedule: "0 2 * * *"
""", "erp", "import_orders"),
      user="import need 2 hour so timeout 7200, but say must less or equal 3600. ok i put 3600?",
      steps=[
          S("get_validation"),
          S("search_docs", say="3600 passes pskit's general check, but Azure has its own, lower limit. Let me confirm it.",
            query="max timeout per provider",
            docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| 600 s |")]),
          S("ask_user", question="Azure Functions stop at 600 s (10 minutes), so 3600 would fail with the next check. Can the import be cut into parts of under 10 minutes (e.g. per batch of orders)? For now I'd set 600.",
            options=["set 600, we split it later", "keep it, no Azure"], answer="set 600, we split it later"),
          S("propose_plan", steps=["Set `functions.import-orders.timeout` to 600", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.import-orders.timeout", value=600),
      ],
      final="""Two limits: pskit allows at most 3600 s [docs/configuration.md#functions], and Azure Functions only 600 s [docs/providers.md#providers]. So neither 7200 nor 3600 can deploy to Azure.

`import-orders` now has `timeout: 600`. Validate for azure: valid. Until the import is split, a run longer than 10 minutes is stopped by Azure."""),

    # ------------------------------------------------------------------ 717  azure pasted partial: disable the workflow too
    C(717, provider="azure", stage="staging", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/configuration.md#switch-something-off-on-one-cloud"],
      project=proj("""service: claims
provider:
  name: azure
  region: westeurope
providers:
  azure:
    functions:
      ocr: {enabled: false}
functions:
  ocr:
    handler: app.claims.ocr
  assess:
    handler: app.claims.assess
workflows:
  claim:
    start_at: Ocr
    states:
      Ocr: {type: task, function: ocr, next: Assess}
      Assess: {type: task, function: assess, end: true}
""", "claims", "ocr", "assess"),
      user="\"...which is disabled; disable the workflow too\" — what's disabled?",
      steps=[
          S("get_validation"),
          S("ask_user", say="`providers.azure` switches off `ocr` on Azure, and the `claim` workflow calls it in its first state.",
            question="Should `claim` also be switched off on Azure, or should `ocr` run on Azure again?",
            options=["disable claim on Azure", "enable ocr on Azure"], answer="disable claim on Azure"),
          S("propose_plan", steps=["Add `providers.azure.workflows.claim.enabled: false`", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.workflows", value={"claim": {"enabled": False}}),
      ],
      final="""A workflow can't call a function that's switched off on the same cloud, so pskit asks you to switch it off too [docs/configuration.md#switch-something-off-on-one-cloud].

`claim` is now disabled on Azure, next to `ocr`. `pskit validate -p azure -s staging`: valid, with warnings that both are not deployed there. Other providers still get both."""),

    # ------------------------------------------------------------------ 718  azure why can't I deploy (from aws): timeout + fifo queue
    C(718, provider="azure", stage="dev", mode="ask", page="Deploy", persona="aws_migrator",
      sources=["docs/events.md#queue", "docs/providers.md#providers"],
      project=proj("""service: ledger-writer
provider:
  name: azure
  region: westeurope
functions:
  write:
    handler: app.ledger.write
    timeout: 900
    events:
      - queue:
          name: ledger.fifo
          fifo: true
""", "ledger", "write"),
      user="Why can't I deploy to Azure? It worked on Lambda with a FIFO queue.",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure queue fifo name",
            docs=[D("docs/events.md", "queue", start="| Option | aws (SQS)", end="| partial batch failure |")]),
          S("propose_plan", say="Three Lambda leftovers: timeout 900 (Azure max 600), the `.fifo` name (dots aren't allowed), and `fifo` (Storage Queues aren't FIFO, so it's ignored).",
            steps=["Set `write.timeout` to 600", "Rename the queue to `ledger`", "Remove `fifo: true`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.write.timeout", value=600),
          S("set_config", path="functions.write.events.0", value={"queue": "ledger"}),
      ],
      final="""Azure has a 600 s limit [docs/providers.md#providers], queue names of lowercase letters, digits and dashes, and no FIFO queues [docs/events.md#queue].

`write`: `timeout: 600`, `- queue: ledger` (no `fifo`). Validate for azure: valid. Order isn't guaranteed on Azure anymore; if the ledger needs it, check a sequence number in the handler."""),

    # ------------------------------------------------------------------ 719  azure terse: batch_size 20000
    C(719, provider="azure", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      project=proj("""service: telemetry
provider:
  name: azure
  region: westeurope
functions:
  ingest:
    handler: app.telemetry.ingest
    events:
      - queue:
          name: telemetry-in
          batch_size: 20000
""", "telemetry", "ingest"),
      user="batch_size 20000 > 10000. set max",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["`batch_size: 10000`", "Validate for azure, stage staging"]),
          S("set_config", path="functions.ingest.events.0.queue.batch_size", value=10000),
      ],
      final="""Set `batch_size: 10000`; `pskit validate -p azure -s staging`: valid. Note: on Azure `batch_size` is ignored (the Storage Queue trigger has its own batching) [docs/events.md#queue], so this only matters for other providers."""),

    # ------------------------------------------------------------------ 720  azure ask_user: ${opt:customer}
    C(720, provider="azure", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: portal-${opt:customer}
provider:
  name: azure
  region: westeurope
functions:
  home:
    handler: app.portal.home
    events:
      - http: GET /
""", "portal", "home"),
      user="In serverless I passed --customer acme and used ${opt:customer}. pskit: unresolved variables: opt:customer.",
      steps=[
          S("get_validation"),
          S("search_docs", query="opt variables cli values",
            docs=[D("docs/configuration.md", "variables", end="(`${opt:x, default}` allowed) |")]),
          S("ask_user", question="pskit's `${opt:...}` only knows stage, provider and region; there is no `--customer` flag. I can read it from an environment variable instead: `${env:CUSTOMER, <default>}`. Which default customer name (lowercase)?",
            answer="demo"),
          S("propose_plan", steps=["Set `service: portal-${env:CUSTOMER, demo}`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="service", value="portal-${env:CUSTOMER, demo}"),
      ],
      final="""`${opt:...}` covers only `stage`, `provider` and `region`, so a custom option can't be passed [docs/configuration.md#variables].

`service` is now `portal-${env:CUSTOMER, demo}`. Validate for azure: valid (`portal-demo`). For a customer deploy, set the `CUSTOMER` environment variable (e.g. to `acme`) in your shell or in **Setup & credentials > Environment variables**, then deploy."""),
]
