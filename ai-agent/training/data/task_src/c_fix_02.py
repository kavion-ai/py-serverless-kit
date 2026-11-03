"""Category C (fix a validation error), batch 2. Hand-written; assembled by tools/assemble.py (tool outputs are real)."""

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


CONVERSATIONS = [
    # ------------------------------------------------------------------ 21  queue on huawei -> topic
    C(21, provider="huawei", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#events-triggers", "docs/providers.md#huawei-functiongraph"],
      project=dict(files={
          "pskit.yml": """service: audit-trail
provider:
  name: huawei
  region: cn-north-4
  iam:
    role: audit-agency
functions:
  store-audit:
    handler: app.audit.store
    events:
      - queue: audit-log
""",
          "app/__init__.py": "",
          "app/audit.py": handlers("store")}),
      user="huawei no like my queue trigger. what i can use instead? i need get messages from other service",
      steps=[
          S("get_validation"),
          S("search_docs", query="huawei supported triggers topic queue",
            docs=[D("docs/providers.md", "huawei-functiongraph", start="| Trigger |", end="| topic |")]),
          S("ask_user", question="Huawei FunctionGraph has no queue trigger in pskit, but it has `topic` (SMN). The other service would publish to an SMN topic instead of a queue. Which do you want?",
            options=["Use a topic trigger `audit-log` on Huawei", "Keep the queue and deploy to another provider"],
            answer="Use a topic trigger `audit-log` on Huawei"),
          S("propose_plan", steps=["Replace the `store-audit` trigger `queue: audit-log` with `topic: audit-log`",
                                   "Validate for huawei"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.store-audit.events", value=[{"topic": "audit-log"}]),
      ],
      final="""Huawei FunctionGraph has no `queue` trigger in pskit. It has `http`, `schedule`, `storage` and `topic` [docs/providers.md#huawei-functiongraph].

Now `store-audit` has `- topic: audit-log`, so it runs for every message published to the SMN topic `audit-log`. `pskit validate` for huawei: valid.

Your handler still gets the messages in `event.records`. The other service must now **publish to the topic `audit-log`** instead of sending to a queue."""),

    # ------------------------------------------------------------------ 22  storage on cloudflare -> per-provider events
    C(22, provider="cloudflare", stage="staging", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#cloudflare-workers", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=dict(files={
          "pskit.yml": """service: media-ingest
provider:
  name: aws
  region: eu-west-1
providers:
  cloudflare:
    options:
      account_id: ${env:CLOUDFLARE_ACCOUNT_ID, 0123456789abcdef0123456789abcdef}
functions:
  ingest:
    handler: app.ingest.on_upload
    events:
      - storage:
          bucket: media-raw
          suffix: .jpg
""",
          "app/__init__.py": "",
          "app/ingest.py": handlers("on_upload")}),
      user="Staging targets Cloudflare and validate rejects `ingest` because of its storage trigger. On Cloudflare I want the same handler exposed as `POST /ingest` instead (our uploader can call it). AWS must keep the S3 trigger. Please change only what's needed.",
      steps=[
          S("get_validation"),
          S("search_docs", query="override function events for one provider",
            docs=[D("docs/configuration.md", "switch-something-off-on-one-cloud")]),
          S("propose_plan", steps=["Add `providers.cloudflare.functions.ingest.events: [{http: POST /ingest}]` (replaces the storage trigger on Cloudflare only)",
                                   "Validate for cloudflare, stage staging; AWS keeps the S3 trigger"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.cloudflare.functions.ingest.events", value=[{"http": "POST /ingest"}]),
      ],
      final="""Cloudflare Workers support only `http` and `schedule`, so the storage trigger can't run there [docs/providers.md#cloudflare-workers].

Added a Cloudflare-only override:

```yaml
providers:
  cloudflare:
    functions:
      ingest: {events: [{http: POST /ingest}]}
```

Lists replace, so on Cloudflare `ingest` has only the HTTP route, and the top-level S3 trigger is untouched for AWS [docs/configuration.md#switch-something-off-on-one-cloud]. `pskit validate -p cloudflare -s staging`: valid, with only the usual Pyodide packages warning.

The handler now gets an HTTP event on Cloudflare and a storage event on AWS. If it reads `event.records`, check `event.is_http` and read the body for the HTTP case."""),

    # ------------------------------------------------------------------ 23  oracle three required options
    C(23, provider="oracle", stage="dev", mode="ask", page="Setup", persona="detailed_spec",
      sources=["docs/providers.md#oracle-oci-functions"],
      project=dict(files={
          "pskit.yml": """service: tax-calc
provider:
  name: oracle
  region: eu-amsterdam-1
functions:
  calculate:
    handler: app.tax.calculate
    events:
      - http: POST /tax
""",
          "app/__init__.py": "",
          "app/tax.py": handlers("calculate")}),
      user="First time on OCI. Validate shows three errors about compartment, subnets and an image. I have a compartment and a subnet ready and I'd like pskit to build and push the image itself to our OCIR repo. What do you need from me?",
      steps=[
          S("get_validation"),
          S("search_docs", query="oracle compartment_id subnet_ids image_repository",
            docs=[D("docs/providers.md", "oracle-oci-functions", start="OCI Functions only run", end="gateway_endpoint_type")]),
          S("ask_user", question="Please give me: 1) the compartment OCID, 2) the subnet OCID, 3) the OCIR repository path (e.g. `ams.ocir.io/<tenancy>/tax-calc`).",
            answer="compartment ocid1.compartment.oc1..aaaaexampletax, subnet ocid1.subnet.oc1.eu-amsterdam-1.aaaaexamplesub, repo ams.ocir.io/acmetenancy/tax-calc"),
          S("propose_plan", steps=["Set `provider.options` to compartment_id, subnet_ids (one subnet) and image_repository from your answer",
                                   "Validate for oracle"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options",
            value={"compartment_id": "ocid1.compartment.oc1..aaaaexampletax",
                   "subnet_ids": ["ocid1.subnet.oc1.eu-amsterdam-1.aaaaexamplesub"],
                   "image_repository": "ams.ocir.io/acmetenancy/tax-calc"}),
      ],
      final="""OCI Functions need a compartment, at least one subnet and a container image, and pskit can't guess them [docs/providers.md#oracle-oci-functions]. I set:

```yaml
provider:
  options:
    compartment_id: ocid1.compartment.oc1..aaaaexampletax
    subnet_ids: [ocid1.subnet.oc1.eu-amsterdam-1.aaaaexamplesub]
    image_repository: ams.ocir.io/acmetenancy/tax-calc
```

With `image_repository`, pskit runs `docker build` + push at deploy time, so Docker must be logged in to OCIR. `pskit validate` for oracle now has no errors. One WARNING stays: add an IAM policy that lets API Gateway call functions (the exact `ALLOW ...` statement is in the warning)."""),

    # ------------------------------------------------------------------ 24  cloudflare account_id
    C(24, provider="cloudflare", stage="prod", mode="auto", page="Setup", persona="terse_expert",
      sources=["docs/providers.md#cloudflare-workers"],
      project=dict(files={
          "pskit.yml": """service: edge-redirects
provider:
  name: cloudflare
  options:
    workers_subdomain: acme-edge
functions:
  redirect:
    handler: app.edge.redirect
    events:
      - http: GET /go/{slug}
""",
          "app/__init__.py": "",
          "app/edge.py": handlers("redirect")}),
      user="cf prod validate: account_id required. fix",
      steps=[
          S("get_validation"),
          S("ask_user", question="What is your Cloudflare account id?",
            answer="a1b2c3d4e5f60718293a4b5c6d7e8f90"),
          S("propose_plan", steps=["Set `provider.options.account_id: a1b2c3d4e5f60718293a4b5c6d7e8f90` (keep workers_subdomain)",
                                   "Validate for cloudflare, stage prod"]),
          S("set_config", path="provider.options.account_id", value="a1b2c3d4e5f60718293a4b5c6d7e8f90"),
      ],
      final="""Set `provider.options.account_id`; `workers_subdomain` kept. `pskit validate -p cloudflare -s prod`: valid (only the Pyodide warning).

Deploy also needs `CLOUDFLARE_API_TOKEN` in the environment [docs/providers.md#cloudflare-workers]; keep the token out of pskit.yml."""),

    # ------------------------------------------------------------------ 25  batch_size 20000 onprem
    C(25, provider="onprem", stage="dev", mode="auto", page="Functions", persona="pasted_error",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: metrics-rollup
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8110
functions:
  rollup:
    handler: app.rollup.handle
    timeout: 300
    events:
      - queue:
          name: raw-metrics
          batch_size: 20000
          batch_window: 30
""",
          "app/__init__.py": "",
          "app/rollup.py": handlers("handle")}),
      user="""Error: pskit.yml is invalid:
  - functions.rollup.events.0.batch_size: Input should be less than or equal to 10000

need the biggest batch possible""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.rollup.events.0.queue.batch_size` to 10000 (the maximum)",
                                   "Validate for onprem"]),
          S("set_config", path="functions.rollup.events.0.queue.batch_size", value=10000),
      ],
      final="""The largest `batch_size` pskit allows is 10000 [docs/events.md#queue]. I set `batch_size: 10000` on `rollup` (`batch_window: 30` unchanged). `pskit validate` for onprem: valid."""),

    # ------------------------------------------------------------------ 26  batch_window 400 aws
    C(26, provider="aws", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#queue"],
      project=dict(files={
          "pskit.yml": """service: clickstream
provider:
  name: aws
  region: us-east-2
functions:
  aggregate:
    handler: app.clicks.aggregate
    timeout: 120
    events:
      - queue:
          name: clicks
          batch_size: 500
          batch_window: 400
""",
          "app/__init__.py": "",
          "app/clicks.py": handlers("aggregate")}),
      user="I want SQS to buffer about 6-7 minutes of clicks before calling the Lambda, so I set batch_window 400 (like MaximumBatchingWindowInSeconds). pskit says it's too big?",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue batch_window maximum seconds",
            docs=[D("docs/events.md", "queue", end="fifo: false")]),
          S("propose_plan", steps=["Set `functions.aggregate.events.0.queue.batch_window` to 300, the maximum",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.aggregate.events.0.queue.batch_window", value=300),
      ],
      final="""`batch_window` is the number of seconds to wait to fill a batch, and pskit allows 0-300 [docs/events.md#queue]. So 5 minutes is the longest buffer.

Set `batch_window: 300` on `aggregate` (`batch_size: 500` unchanged). `pskit validate -p aws -s prod`: valid.

If you really need ~7 minutes of data per run, a `schedule` trigger every 7 minutes that reads the queue itself is another way, but that is a code change."""),

    # ------------------------------------------------------------------ 27  memory 50 gcp, plan note
    C(27, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: quote-of-day
provider:
  name: gcp
  region: asia-northeast1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, quote-of-day-dev}
functions:
  quote:
    handler: app.quotes.today
    memory: 50
    events:
      - http: GET /quote
""",
          "app/__init__.py": "",
          "app/quotes.py": handlers("today")}),
      user="i set memory to 50 so it is cheap but now there is a error. what is the smallest i can use?",
      steps=[
          S("get_validation"),
          S("search_docs", query="function memory minimum MB",
            docs=[D("docs/configuration.md", "functions", end="memory: 512")]),
          S("propose_plan", steps=["Set `functions.quote.memory` to 64, the smallest value pskit accepts",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": "make it 128 instead, 64 sounds too tight"}),
          S("set_config", path="functions.quote.memory", value=128),
      ],
      final="""The smallest memory pskit accepts is 64 MB (the range is 64-32768), and 50 is below it [docs/configuration.md#functions].

As you asked, I set `memory: 128` for `quote` instead of 64. Validate for gcp now says the configuration is valid."""),

    # ------------------------------------------------------------------ 28  timeout 5000 onprem
    C(28, provider="onprem", stage="prod", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions", "docs/providers.md#providers"],
      project=dict(files={
          "pskit.yml": """service: backup-runner
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8120
functions:
  nightly-backup:
    handler: app.backup.run
    timeout: 5000
    events:
      - schedule: "15 1 * * *"
""",
          "app/__init__.py": "",
          "app/backup.py": handlers("run")}),
      user="backup job timeout 5000 fails schema. max?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.nightly-backup.timeout` to 3600 (schema max, also the onprem max)",
                                   "Validate for onprem, stage prod"]),
          S("set_config", path="functions.nightly-backup.timeout", value=3600),
      ],
      final="""Max is 3600 s: the schema allows 1-3600 [docs/configuration.md#functions], and onprem's limit is also 3600 s [docs/providers.md#providers].

Set `nightly-backup.timeout: 3600`. `pskit validate -p onprem -s prod`: valid. If a backup can run longer than an hour, split it into parts."""),

    # ------------------------------------------------------------------ 29  bad rate alibaba
    C(29, provider="alibaba", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: price-watch
provider:
  name: alibaba
  region: cn-hangzhou
functions:
  check-prices:
    handler: app.prices.check
    events:
      - schedule:
          rate: every 10 minutes
""",
          "app/__init__.py": "",
          "app/prices.py": handlers("check")}),
      user="i want run check-prices every 10 min, i write rate every 10 minutes but validate say error rate must look like something",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule rate format minutes",
            docs=[D("docs/events.md", "schedule", end="The handler gets")]),
          S("propose_plan", steps=["Change the rate of `check-prices` from `every 10 minutes` to `10 minutes`",
                                   "Validate for alibaba"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.check-prices.events.0.schedule.rate", value="10 minutes"),
      ],
      final="""The rate must be only `<number> minutes|hours|days`, without the word "every" [docs/events.md#schedule].

I changed it to `rate: 10 minutes`. Validate for alibaba: valid. On Alibaba pskit turns this into a timer trigger `@every 10m`."""),

    # ------------------------------------------------------------------ 30  ${env:LOG_LEVEL} unset
    C(30, provider="aws", stage="staging", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/configuration.md#variables", "docs/troubleshooting.md#configuration"],
      project=dict(files={
          "pskit.yml": """service: search-api
provider:
  name: aws
  region: ap-southeast-2
  environment:
    LOG_LEVEL: ${env:SEARCH_LOG_LEVEL}
functions:
  search:
    handler: app.search.query
    events:
      - http: GET /search
""",
          "app/__init__.py": "",
          "app/search.py": handlers("query")}),
      user="Error: unresolved variables: env:SEARCH_LOG_LEVEL\n\nthis one only happens on my laptop, CI sets it",
      steps=[
          S("get_validation"),
          S("search_docs", query="unresolved variables env default",
            docs=[D("docs/troubleshooting.md", "configuration", end="Set the variable, or give a default")]),
          S("ask_user", question="`SEARCH_LOG_LEVEL` isn't set on your laptop. Should I add a fallback in pskit.yml (CI's value still wins), or will you set the variable locally?",
            options=["Add the fallback INFO", "I'll set it locally"],
            answer="Add the fallback INFO"),
          S("propose_plan", steps=["Change `provider.environment.LOG_LEVEL` to `${env:SEARCH_LOG_LEVEL, INFO}`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.environment.LOG_LEVEL", value="${env:SEARCH_LOG_LEVEL, INFO}"),
      ],
      final="""`${env:NAME}` without a default is an error when the variable is unset, which is the case on your laptop [docs/troubleshooting.md#configuration].

Changed to `LOG_LEVEL: ${env:SEARCH_LOG_LEVEL, INFO}`. When CI sets `SEARCH_LOG_LEVEL`, that value is used; otherwise `INFO` [docs/configuration.md#variables]. `pskit validate -p aws -s staging`: valid."""),

    # ------------------------------------------------------------------ 31  handler without dots, azure
    C(31, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=dict(files={
          "pskit.yml": """service: school-timetable
provider:
  name: azure
  region: uksouth
functions:
  timetable:
    handler: timetable
    events:
      - http: GET /timetable
""",
          "app/__init__.py": "",
          "app/timetable.py": FUTURE + """

def get_timetable(event, ctx):
    return {"monday": ["maths", "art"]}
"""}),
      user="I typed the handler name in the Functions page but it says it must be package.module.function. My file is app/timetable.py. What do I type?",
      steps=[
          S("get_validation"),
          S("read_file", path="app/timetable.py"),
          S("propose_plan", steps=["Set `functions.timetable.handler` to `app.timetable.get_timetable` (folder.file.function)",
                                   "Validate for azure",
                                   "Run `timetable` locally on GET /timetable"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.timetable.handler", value="app.timetable.get_timetable"),
          S("invoke_local", function="timetable", method="GET", path="/timetable"),
      ],
      final="""The handler needs three parts joined with dots: folder (`app`), file without `.py` (`timetable`), and the function name inside it (`get_timetable`) [docs/configuration.md#functions].

So the Handler field is now `app.timetable.get_timetable`.
- Validate for azure: valid.
- A local test of GET /timetable returned status 200 with `{"monday": ["maths", "art"]}`."""),

    # ------------------------------------------------------------------ 32  start_at wrong, gcp
    C(32, provider="gcp", stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": """service: kyc-flow
provider:
  name: gcp
  region: europe-west4
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT, kyc-flow-staging}
functions:
  fetch-docs:
    handler: app.kyc.fetch_docs
  score:
    handler: app.kyc.score
workflows:
  kyc:
    start_at: Fetch
    states:
      FetchDocs:
        type: task
        function: fetch-docs
        next: Score
      Score:
        type: task
        function: score
        end: true
""",
          "app/__init__.py": "",
          "app/kyc.py": handlers("fetch_docs", "score")}),
      user="kyc workflow start_at error, gcp staging",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `workflows.kyc.start_at` to `FetchDocs` (the first state; `Fetch` doesn't exist)",
                                   "Validate for gcp, stage staging"]),
          S("set_config", path="workflows.kyc.start_at", value="FetchDocs"),
      ],
      final="""`start_at: Fetch` named no state; the first state is `FetchDocs` [docs/workflows.md#workflow-keys]. Set `start_at: FetchDocs`. `pskit validate -p gcp -s staging`: valid (deploys as Cloud Workflows)."""),

    # ------------------------------------------------------------------ 33  workflow task -> unknown function, onprem
    C(33, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#workflow-keys"],
      project=dict(files={
          "pskit.yml": """service: signup-pipe
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8130
functions:
  create-user:
    handler: app.users.create
  send-mail:
    handler: app.users.send_mail
workflows:
  onboarding:
    start_at: Create
    states:
      Create:
        type: task
        function: create-user
        next: Welcome
      Welcome:
        type: task
        function: send-email
        end: true
""",
          "app/__init__.py": "",
          "app/users.py": handlers("create", "send_mail")}),
      user="workflow onboarding say references unknown function. but i have the mail function!",
      steps=[
          S("get_validation"),
          S("get_project"),
          S("propose_plan", steps=["In `onboarding`, set state `Welcome` function to `send-mail` (the real function name)",
                                   "Validate for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.onboarding.states.Welcome.function", value="send-mail"),
      ],
      final="""Yes, you have it, but it is called `send-mail`, and the `Welcome` state said `send-email`. A workflow task must use the exact function name from `functions:` [docs/workflows.md#workflow-keys].

I changed `Welcome` to `function: send-mail`. Validate for onprem: valid. On onprem the workflow runs on the embedded engine."""),

    # ------------------------------------------------------------------ 34  choice rule without next, azure
    C(34, provider="azure", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#choice-rules"],
      project=dict(files={
          "pskit.yml": """service: refund-flow
provider:
  name: azure
  region: westeurope
functions:
  auto-refund:
    handler: app.refunds.auto_refund
  manual-review:
    handler: app.refunds.manual_review
workflows:
  refund:
    start_at: Route
    states:
      Route:
        type: choice
        choices:
          - variable: $.amount
            lte: 50
        default: Review
      AutoRefund:
        type: task
        function: auto-refund
        end: true
      Review:
        type: task
        function: manual-review
        end: true
""",
          "app/__init__.py": "",
          "app/refunds.py": handlers("auto_refund", "manual_review")}),
      user="In the `refund` workflow, refunds of 50 or less should go straight to the AutoRefund state, everything else to Review. Validation for prod fails with a message about a choice rule. Please fix the rule so it does what I described.",
      steps=[
          S("get_validation"),
          S("search_docs", query="choice rule next variable",
            docs=[D("docs/workflows.md", "choice-rules", end="next: AskEmail")]),
          S("propose_plan", steps=["Add `next: AutoRefund` to the rule `$.amount lte 50` in state `Route` (default stays Review)",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.refund.states.Route.choices.0.next", value="AutoRefund"),
      ],
      final="""The choice rule had a condition (`$.amount` ≤ 50) but no `next`, so pskit didn't know where to go when it matched. Every rule needs a `next` [docs/workflows.md#choice-rules].

The rule is now `{variable: $.amount, lte: 50, next: AutoRefund}`, and `default: Review` handles everything else. `pskit validate -p azure -s prod`: valid. One WARNING: on Azure the workflow runs on the embedded engine inside one function, so the whole run must finish within the function timeout (600 s max on Azure)."""),

    # ------------------------------------------------------------------ 35  duplicate route aws
    C(35, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/troubleshooting.md#configuration"],
      project=dict(files={
          "pskit.yml": """service: shop-api
provider:
  name: aws
  region: eu-west-2
functions:
  list-products:
    handler: app.shop.list_products
    events:
      - http: GET /products
  search-products:
    handler: app.shop.search_products
    events:
      - http: GET /products
""",
          "app/__init__.py": "",
          "app/shop.py": handlers("list_products", "search_products")}),
      user="""Error: pskit.yml is invalid:
  - <root>: Value error, route GET /products is used by both 'list-products' and 'search-products'

I duplicated the function and forgot something I guess""",
      steps=[
          S("get_validation"),
          S("ask_user", question="Each `METHOD /path` can belong to one function only. Which route should `search-products` get?",
            options=["GET /products/search", "GET /search"],
            answer="GET /products/search"),
          S("propose_plan", steps=["Change the route of `search-products` to `GET /products/search`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.search-products.events.0.http", value="GET /products/search"),
      ],
      final="""Right: the copy kept the same route, and one `METHOD /path` can only belong to one function [docs/troubleshooting.md#configuration].

`search-products` is now on `GET /products/search`; `list-products` keeps `GET /products`. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 36  two keys in one event, digitalocean
    C(36, provider="digitalocean", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/troubleshooting.md#configuration", "docs/events.md#events-triggers"],
      project=dict(files={
          "pskit.yml": """service: weather-bot
provider:
  name: digitalocean
  region: ams3
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE, fn-00000000-0000-0000-0000-000000000000}
functions:
  forecast:
    handler: app.weather.forecast
    events:
      - http: GET /forecast
        schedule: 1 hour
""",
          "app/__init__.py": "",
          "app/weather.py": handlers("forecast")}),
      user="I want my forecast function to work from a link AND update itself every hour. I added both but now it says each event must be a single-key mapping?",
      steps=[
          S("get_validation"),
          S("search_docs", query="each event must be a single-key mapping",
            docs=[D("docs/troubleshooting.md", "configuration", start="**`each event must be a single-key mapping`**",
                    end="as separate list items")]),
          S("propose_plan", steps=["Split the one event item into two: `- http: GET /forecast` and `- schedule: 1 hour`",
                                   "Validate for digitalocean"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.forecast.events", value=[{"http": "GET /forecast"}, {"schedule": "1 hour"}]),
      ],
      final="""You can have both. They just need to be two separate items in the list (each with its own `-`), not two keys in one item [docs/troubleshooting.md#configuration]:

```yaml
events:
  - http: GET /forecast
  - schedule: 1 hour
```

Validate for digitalocean has no errors now. The only remaining warning says `doctl` isn't installed, which you need later for deploy."""),

    # ------------------------------------------------------------------ 37  cron: key on tencent
    C(37, provider="tencent", stage="dev", mode="auto", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#schedule"],
      project=dict(files={
          "pskit.yml": """service: weekday-report
provider:
  name: tencent
  region: ap-beijing
functions:
  report:
    handler: app.report.send
    events:
      - cron: "0 9 * * 1-5"
""",
          "app/__init__.py": "",
          "app/report.py": handlers("send")}),
      user="Coming from serverless.yml where I'd write `schedule: cron(0 9 ? * MON-FRI *)`. Here I tried `- cron:` and got unknown event type. What's the pskit way?",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule cron syntax provider conversion",
            docs=[D("docs/events.md", "schedule", end="The handler gets")]),
          S("propose_plan", steps=["Replace `- cron: \"0 9 * * 1-5\"` with `- schedule: \"0 9 * * 1-5\"` on `report`",
                                   "Validate for tencent"]),
          S("set_config", path="functions.report.events", value=[{"schedule": "0 9 * * 1-5"}]),
      ],
      final="""In pskit the event type is `schedule`; a cron is just its value, in portable 5-field unix form (no `cron(...)`, no `?`, no year) [docs/events.md#schedule].

Changed to:

```yaml
events:
  - schedule: "0 9 * * 1-5"   # 09:00 Mon-Fri, UTC
```

`pskit validate -p tencent`: valid. pskit converts it to Tencent's 7-field cron when it generates the timer trigger."""),

    # ------------------------------------------------------------------ 38  batch_size under http
    C(38, provider="aws", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: ingest-gw
provider:
  name: aws
  region: us-east-1
functions:
  receive:
    handler: app.gw.receive
    events:
      - http:
          path: /events
          method: POST
          batch_size: 25
""",
          "app/__init__.py": "",
          "app/gw.py": handlers("receive")}),
      user="schema error on receive: events.0.batch_size extra input. staging",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Delete `functions.receive.events.0.http.batch_size` (queue-only option, no meaning on http)",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="functions.receive.events.0.http.batch_size", value=None),
      ],
      final="""`batch_size` is a `queue` option; `http` takes only path, method, cors, auth, authorizer [docs/events.md#http]. Removed it from `receive`. `pskit validate -p aws -s staging`: valid.

If you meant to batch these events, put them on a queue and add a `queue` trigger with `batch_size: 25` to the consumer."""),

    # ------------------------------------------------------------------ 39  jwt without authorizer
    C(39, provider="aws", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: billing-api
provider:
  name: aws
  region: eu-west-1
functions:
  invoices:
    handler: app.billing.invoices
    events:
      - http:
          path: /invoices
          method: GET
          auth: jwt
""",
          "app/__init__.py": "",
          "app/billing.py": handlers("invoices")}),
      user="I set `auth: jwt` on GET /invoices so API Gateway checks our identity provider's tokens, but prod validation fails. Our issuer is https://login.example.com/ and the API audience is `billing-api`.",
      steps=[
          S("get_validation"),
          S("search_docs", query="jwt auth authorizer issuer audience",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="Example of AWS JWT auth")]),
          S("propose_plan", steps=["Add `authorizer: {issuer: https://login.example.com/, audience: [billing-api]}` to the GET /invoices route",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.invoices.events.0.http.authorizer",
            value={"issuer": "https://login.example.com/", "audience": ["billing-api"]}),
      ],
      final="""`auth: jwt` needs `authorizer.issuer` and `authorizer.audience`, so API Gateway knows which tokens to accept [docs/events.md#http].

Added:

```yaml
- http:
    path: /invoices
    method: GET
    auth: jwt
    authorizer:
      issuer: https://login.example.com/
      audience: [billing-api]
```

`pskit validate -p aws -s prod`: valid. Optional keys are `identity_source` and `scopes`, if you need them."""),

    # ------------------------------------------------------------------ 40  auth key on aws
    C(40, provider="aws", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#aws-aws-lambda", "docs/events.md#http"],
      project=dict(files={
          "pskit.yml": """service: partner-feed
provider:
  name: aws
  region: us-west-2
functions:
  feed:
    handler: app.feed.get_feed
    events:
      - http:
          path: /feed
          method: GET
          auth: key
""",
          "app/__init__.py": "",
          "app/feed.py": handlers("get_feed")}),
      user="With API Gateway REST APIs I used usage-plan API keys for partners. I put `auth: key` on the feed route and validate errors out. What does pskit want on AWS?",
      steps=[
          S("get_validation"),
          S("search_docs", query="aws auth key http api",
            docs=[D("docs/providers.md", "aws-aws-lambda", start="**Limits:**")]),
          S("ask_user", question="pskit deploys an API Gateway **HTTP API**, which has no API keys. Which should `/feed` use?",
            options=["iam (partners sign requests with AWS credentials)",
                     "jwt (partners send a token from an identity provider)"],
            answer="iam (partners sign requests with AWS credentials)"),
          S("propose_plan", steps=["Set `functions.feed.events.0.http.auth` to `iam`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.feed.events.0.http.auth", value="iam"),
      ],
      final="""pskit puts routes on an API Gateway HTTP API, not a REST API, and HTTP APIs have no API keys / usage plans [docs/providers.md#aws-aws-lambda].

As you chose, `/feed` now uses `auth: iam` (API Gateway `AWS_IAM`) [docs/events.md#http]. `pskit validate` for aws: valid.

Partners now need AWS credentials that are allowed to call the route. A plain `x-api-key` header won't work any more."""),
]
