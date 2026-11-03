"""Category C (fix a validation error), batch 31 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 601  aws storage prefix as a list
    C(601, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage"],
      project=proj("""service: ingest-files
provider:
  name: aws
  region: eu-west-1
functions:
  ingest:
    handler: app.ingest.on_file
    events:
      - storage:
          bucket: acme-ingest-dev
          prefix: [raw/, incoming/]
""", "ingest", "on_file"),
      user="Files arrive in two folders of the same bucket, raw/ and incoming/. I gave prefix a list and got prefix: Input should be a valid string. Both folders should trigger ingest.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Replace the event with two storage events on `acme-ingest-dev`: `prefix: raw/` and `prefix: incoming/`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest.events",
            value=[{"storage": {"bucket": "acme-ingest-dev", "prefix": "raw/"}},
                   {"storage": {"bucket": "acme-ingest-dev", "prefix": "incoming/"}}]),
      ],
      final="""`prefix` is a single string; for two folders you add one storage event per prefix [docs/events.md#storage].

`ingest` now has two events on `acme-ingest-dev`, `prefix: raw/` and `prefix: incoming/`. Validate for aws: valid. The folder is visible in `record.key`."""),

    # ------------------------------------------------------------------ 602  onprem project, aws target, timeout 1800
    C(602, provider="aws", stage="staging", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=proj("""service: video-cutter
provider:
  name: onprem
  timeout: 1800
providers:
  aws:
    region: us-east-1
functions:
  cut:
    handler: app.video.cut
    events:
      - http: POST /cut
""", "video", "cut"),
      user="Why can't I deploy to aws? On our own server it works. I chose aws in the top bar and Validate shows a red error about the timeout.",
      steps=[
          S("get_validation"),
          S("ask_user", question="On your server `cut` may run 30 minutes; AWS Lambda stops at 900 s (15 minutes). Should I set 900 s for AWS only (the server keeps 1800 s)?",
            options=["yes, 900 on aws only", "no"], answer="yes, 900 on aws only"),
          S("propose_plan", steps=["Add `timeout: 900` to the `providers.aws` block", "Validate for aws, stage staging, then for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.aws.timeout", value=900),
          S("validate", provider="onprem"),
      ],
      final="""Your service has `timeout: 1800`; that's fine on your own server, but AWS Lambda allows at most 900 s. Inside `providers.aws` you can set a different `timeout` just for AWS [docs/configuration.md#providers-per-cloud-overrides].

Added `providers.aws.timeout: 900`. aws (staging): valid. onprem: valid, still 1800 s. Videos that need more than 15 minutes will be stopped on AWS."""),

    # ------------------------------------------------------------------ 603  aws parallel branch without states
    C(603, provider="aws", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: welcome-flow
provider:
  name: aws
  region: us-east-1
functions:
  send-email:
    handler: app.welcome.email
  send-sms:
    handler: app.welcome.sms
  done:
    handler: app.welcome.done
workflows:
  welcome:
    start_at: Notify
    states:
      Notify:
        type: parallel
        branches:
          - start_at: Email
          - start_at: Sms
        next: Done
      Email: {type: task, function: send-email, end: true}
      Sms: {type: task, function: send-sms, end: true}
      Done: {type: task, function: done, end: true}
""", "welcome", "email", "sms", "done"),
      user="Like ASL Branches, each branch has a StartAt. I defined Email and Sms at the top level, but pskit says branches.0.states: Field required.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Move `Email` into branch 0 and `Sms` into branch 1 as their `states`",
                                   "Remove them from the top-level states",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.welcome.states",
            value={"Notify": {"type": "parallel", "next": "Done", "branches": [
                       {"start_at": "Email", "states": {"Email": {"type": "task", "function": "send-email", "end": True}}},
                       {"start_at": "Sms", "states": {"Sms": {"type": "task", "function": "send-sms", "end": True}}}]},
                   "Done": {"type": "task", "function": "done", "end": True}}),
      ],
      final="""Same as ASL: a branch is a complete machine with its own `start_at` and `states`; it can't use states from the outer workflow [docs/workflows.md#state-types].

`Email` and `Sms` now live inside their branches, and `Notify` goes to `Done`. Validate for aws: valid (Step Functions)."""),

    # ------------------------------------------------------------------ 604  aws http list
    C(604, provider="aws", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      project=proj("""service: feedback-api
provider:
  name: aws
  region: eu-central-1
functions:
  feedback:
    handler: app.feedback.handle
    events:
      - http: [GET /feedback, POST /feedback]
""", "feedback", "handle"),
      user="i write http: [GET /feedback, POST /feedback] in one line, error valid dictionary or instance of HttpEvent",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Split into two events: `http: GET /feedback` and `http: POST /feedback`", "Validate for aws"]),
          S("set_config", path="functions.feedback.events", value=[{"http": "GET /feedback"}, {"http": "POST /feedback"}]),
      ],
      final="""One `http` event is one route; a list there isn't allowed [docs/events.md#http].

Now two events: `- http: GET /feedback` and `- http: POST /feedback`. Validate for aws: valid. In the handler, `event.http.method` tells them apart."""),

    # ------------------------------------------------------------------ 605  aws package.exclude string
    C(605, provider="aws", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#package"],
      project=proj("""service: geo-tiles
provider:
  name: aws
  region: us-west-2
package:
  exclude: "notebooks/**"
functions:
  tile:
    handler: app.tiles.tile
    events:
      - http: GET /tiles/{z}/{x}/{y}
""", "tiles", "tile"),
      user="package.exclude: Input should be a valid list",
      steps=[
          S("get_validation"),
          S("search_docs", query="package exclude globs",
            docs=[D("docs/configuration.md", "package", start="| `include` |", end="| `exclude` |")]),
          S("propose_plan", steps=["Set `package.exclude` to `[\"notebooks/**\"]`", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="package.exclude", value=["notebooks/**"]),
      ],
      final="""`exclude` is a list of globs, added to the default excludes [docs/configuration.md#package].

Set `exclude: ["notebooks/**"]`. Validate for aws: valid."""),

    # ------------------------------------------------------------------ 606  aws service name with ${sls:stage}
    C(606, provider="aws", stage="staging", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/configuration.md#functions", "docs/configuration.md#variables"],
      project=proj("""service: orders-${sls:stage}
provider:
  name: aws
  region: us-east-1
functions:
  create:
    handler: app.orders.create
    events:
      - http: POST /orders
""", "orders", "create"),
      user="In serverless.yml we had service: orders-${sls:stage} so every stage gets its own stack. pskit says service must be 2-32 chars of lowercase letters, digits and dashes.",
      steps=[
          S("get_validation"),
          S("search_docs", query="deployed function names stage",
            docs=[D("docs/configuration.md", "functions", start="Event syntax is in", end="Event syntax is in")]),
          S("propose_plan", steps=["Set `service` to `orders` (pskit adds the stage itself)", "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="service", value="orders"),
      ],
      final="""pskit doesn't know `${sls:...}`, so the text stayed literal and `$`, `{`, `}` aren't allowed in a service name. You don't need it: deployed names are `<service>-<stage>-<function>`, and each provider+stage has its own state [docs/configuration.md#functions].

Set `service: orders`. `pskit validate -p aws -s staging`: valid; `create` deploys as `orders-staging-create`."""),

    # ------------------------------------------------------------------ 607  aws events: none
    C(607, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: pricing
provider:
  name: aws
  region: us-east-1
functions:
  quote:
    handler: app.pricing.quote
    events:
      - http: POST /quote
  calc-tax:
    handler: app.pricing.calc_tax
    events: none
""", "pricing", "quote", "calc_tax"),
      user="calc-tax is only called from quote with invoke(), it shouldn't have triggers. I wrote events: none and it says Input should be a valid list.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `events` from `calc-tax` (no events = invoke-only)", "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.calc-tax.events", value=None),
      ],
      final="""`events` is a list; to have no triggers you leave it out (or `[]`), which makes an invoke-only function [docs/configuration.md#functions].

Removed `events` from `calc-tax`. Validate for aws: valid, 2 functions."""),

    # ------------------------------------------------------------------ 608  gcp storage suffix list
    C(608, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=proj("""service: photo-resize
provider:
  name: gcp
  region: europe-west1
  options:
    project: photo-resize-dev
functions:
  resize:
    handler: app.photos.resize
    events:
      - storage:
          bucket: photo-resize-uploads
          suffix: [.jpg, .png]
""", "photos", "resize"),
      user="want resize only jpg and png. suffix: [.jpg, .png] give error valid string",
      steps=[
          S("get_validation"),
          S("ask_user", question="`suffix` takes one value. I can (a) add two storage events, one for `.jpg` and one for `.png`, or (b) drop the suffix and skip other files in the handler. Which?",
            options=["a: two events", "b: check in handler"], answer="b"),
          S("propose_plan", steps=["Remove `suffix` from the storage event of `resize`", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.resize.events.0.storage", value={"bucket": "photo-resize-uploads"}),
      ],
      final="""`suffix` is one string, not a list [docs/events.md#storage].

As you chose, the event is now just `storage: {bucket: photo-resize-uploads}`. Validate for gcp: valid. In `resize`, skip records whose `record.key` doesn't end with `.jpg` or `.png`."""),

    # ------------------------------------------------------------------ 609  gcp why can't I deploy: missing project + iam warning
    C(609, provider="gcp", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: files-api
provider:
  name: gcp
  region: europe-west1
  iam:
    statements:
      - actions: ["s3:GetObject"]
        resources: ["arn:aws:s3:::files-bucket/*"]
functions:
  files:
    handler: app.files.get_file
    events:
      - http: GET /files/{name}
""", "files", "get_file"),
      user="why can't I deploy to gcp? I changed the provider from aws and there's one error and one warning.",
      steps=[
          S("get_validation"),
          S("ask_user", question="GCP needs the id of the Google Cloud project to deploy into. What is it?",
            answer="files-api-dev-4821"),
          S("propose_plan", steps=["Set `provider.options.project: files-api-dev-4821`",
                                   "Remove the AWS-style `provider.iam.statements` (ignored on GCP)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options", value={"project": "files-api-dev-4821"}),
          S("set_config", path="provider.iam", value=None),
      ],
      final="""The error: GCP needs `provider.options.project`. The warning: the S3 permission is AWS-style IAM, which GCP ignores; there you grant roles to `options.service_account` [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

- `provider.options.project: files-api-dev-4821`
- removed the S3 `iam.statements`

Validate for gcp: valid, no warnings. If `files` must read from Cloud Storage, give its service account a storage role in Google Cloud."""),

    # ------------------------------------------------------------------ 610  gcp from azure: provider timeout 600 with a queue fn
    C(610, provider="gcp", stage="staging", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen", "docs/configuration.md#functions"],
      project=proj("""service: invoice-batch
provider:
  name: gcp
  region: europe-west1
  timeout: 600
  options:
    project: invoice-batch-staging
functions:
  api:
    handler: app.invoices.api
    events:
      - http: GET /invoices
  render:
    handler: app.invoices.render
    events:
      - queue: invoice-render
""", "invoices", "api", "render"),
      user="We came from Azure where everything had a 10 minute timeout (provider.timeout 600). On GCP staging: [functions.render] event-triggered functions are limited to 540s on GCP. The HTTP api doesn't need more than 30 s.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.timeout` to 30 (enough for `api`)",
                                   "Set `functions.render.timeout: 540` (the GCP maximum for queue triggers)",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.timeout", value=30),
          S("set_config", path="functions.render.timeout", value=540),
      ],
      final="""`provider.timeout: 600` applies to every function, and `render` has a queue trigger, which GCP caps at 540 s [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

- `provider.timeout: 30` (the `api` default)
- `render.timeout: 540`

`pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 611  gcp function name with a dot
    C(611, provider="gcp", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#top-level"],
      project=proj("""service: catalog
provider:
  name: gcp
  region: us-central1
  options:
    project: catalog-dev
functions:
  products.list:
    handler: app.products.list_products
    events:
      - http: GET /products
""", "products", "list_products"),
      user="name 'products.list' must start with a letter... → products-list",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the function key `products.list` to `products-list` (same handler and route)",
                                   "Validate for gcp"]),
          S("set_config", path="functions", value={"products-list": {"handler": "app.products.list_products",
                                                                      "events": [{"http": "GET /products"}]}}),
      ],
      final="""Function names allow letters, digits, `-` and `_`; a dot isn't allowed [docs/configuration.md#top-level].

Renamed to `products-list`, same handler and `GET /products`. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 612  gcp prod-only project typo
    C(612, provider="gcp", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen", "docs/configuration.md#stages-per-stage-overrides"],
      project=proj("""service: shop-search
provider:
  name: gcp
  region: europe-west1
stages:
  dev:
    provider:
      options:
        project: shop-search-dev
  prod:
    provider:
      options:
        projectId: shop-search-prod
functions:
  search:
    handler: app.search.search
    events:
      - http: GET /search
""", "search", "search"),
      user="""ERROR: [provider.options] GCP needs provider.options.project (the GCP project id)

only on prod! dev has the project""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["In `stages.prod.provider.options`, rename `projectId` to `project`", "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.provider.options", value={"project": "shop-search-prod"}),
      ],
      final="""Each stage sets its own project, and prod used the key `projectId`; pskit reads `options.project` [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

`stages.prod.provider.options.project: shop-search-prod`. `pskit validate -p gcp -s prod`: valid."""),

    # ------------------------------------------------------------------ 613  gcp parallel branches as function names
    C(613, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: price-compare
provider:
  name: gcp
  region: europe-west1
  options:
    project: price-compare-dev
functions:
  shop-a:
    handler: app.prices.shop_a
  shop-b:
    handler: app.prices.shop_b
  best:
    handler: app.prices.best
workflows:
  compare:
    start_at: AskShops
    states:
      AskShops:
        type: parallel
        branches: [shop-a, shop-b]
        next: Best
      Best: {type: task, function: best, end: true}
""", "prices", "shop_a", "shop_b", "best"),
      user="i put branches: [shop-a, shop-b] for call both shop same time. error valid dictionary or WorkflowDefinition",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Make each branch a small workflow with one task: `ShopA` (shop-a) and `ShopB` (shop-b)", "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.compare.states.AskShops.branches",
            value=[{"start_at": "ShopA", "states": {"ShopA": {"type": "task", "function": "shop-a", "end": True}}},
                   {"start_at": "ShopB", "states": {"ShopB": {"type": "task", "function": "shop-b", "end": True}}}]),
      ],
      final="""A branch is not a function name; it is a small workflow with `start_at` and `states` [docs/workflows.md#state-types].

`AskShops` now has two branches, `ShopA` → `shop-a` and `ShopB` → `shop-b`; `Best` gets a list with both results. Validate for gcp: valid."""),

    # ------------------------------------------------------------------ 614  gcp prod-only jwt
    C(614, provider="gcp", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http", "docs/configuration.md#stages-per-stage-overrides"],
      project=proj("""service: metrics-api
provider:
  name: gcp
  region: us-central1
  options:
    project: metrics-api-prod
stages:
  prod:
    functions:
      metrics:
        events:
          - http:
              path: /metrics
              method: GET
              auth: jwt
              authorizer:
                issuer: https://accounts.google.com
                audience: [metrics-api]
functions:
  metrics:
    handler: app.metrics.get_metrics
    events:
      - http: GET /metrics
""", "metrics", "get_metrics"),
      user="Dev is public on purpose. For prod I added a stages override with JWT so only our dashboards (Google service accounts) can call it, and prod validation says http auth 'jwt' is not supported on GCP.",
      steps=[
          S("get_validation"),
          S("search_docs", query="gcp iam auth invoker",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="| Trigger | Implementation |", end="| http |")]),
          S("propose_plan", steps=["In `stages.prod`, make `/metrics` `auth: iam` and drop the authorizer", "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="stages.prod.functions.metrics.events",
            value=[{"http": {"path": "/metrics", "method": "GET", "auth": "iam"}}]),
      ],
      final="""GCP has no JWT authorizer in pskit; for callers with Google service accounts the GCP way is `auth: iam`, which adds no public invoker [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

The prod override is now `GET /metrics` with `auth: iam`; dev stays public. `pskit validate -p gcp -s prod`: valid. The dashboards' service accounts need permission to invoke the function."""),

    # ------------------------------------------------------------------ 615  azure ${sls:stage} in queue name
    C(615, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#variables", "docs/events.md#queue"],
      project=proj("""service: job-runner
provider:
  name: azure
  region: westeurope
functions:
  run-job:
    handler: app.jobs.run
    events:
      - queue: jobs-${sls:stage}
""", "jobs", "run"),
      user="queue name 'jobs-${sls:stage}' must be 3-63 lowercase letters... why is the variable still there? It's from our serverless.yml.",
      steps=[
          S("get_validation"),
          S("search_docs", query="variables opt stage",
            docs=[D("docs/configuration.md", "variables", end="| `${opt:stage}` / `${opt:provider}` / `${opt:region}` |")]),
          S("propose_plan", steps=["Change the queue of `run-job` to `jobs-${opt:stage}`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.run-job.events.0", value={"queue": "jobs-${opt:stage}"}),
      ],
      final="""`${sls:...}` is Serverless Framework syntax; pskit leaves unknown `${...}` forms as plain text, so the queue name kept the `$` and braces. pskit's stage variable is `${opt:stage}` [docs/configuration.md#variables].

The queue is now `jobs-${opt:stage}` (`jobs-dev` here). Validate for azure: valid."""),

    # ------------------------------------------------------------------ 616  onprem -> azure timeout 900
    C(616, provider="azure", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/configuration.md#providers-per-cloud-overrides"],
      project=proj("""service: log-crunch
provider:
  name: onprem
providers:
  azure:
    region: westeurope
functions:
  crunch:
    handler: app.logs.crunch
    timeout: 900
    events:
      - schedule: "0 1 * * *"
""", "logs", "crunch"),
      user="we run log-crunch on own server, now also azure. azure say timeout 900s exceeds Azure Functions max 600s. on server must stay 900",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Add `providers.azure.functions.crunch.timeout: 600` (server keeps 900)",
                                   "Validate for azure, then for onprem"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.functions", value={"crunch": {"timeout": 600}}),
          S("validate", provider="onprem"),
      ],
      final="""Azure Functions allows at most 600 s here, and a `providers.azure` block can change one function only on Azure [docs/configuration.md#providers-per-cloud-overrides].

Added `providers.azure.functions.crunch.timeout: 600`. azure: valid. onprem: valid, still 900 s. On Azure the job must finish in 10 minutes."""),

    # ------------------------------------------------------------------ 617  azure container URL as bucket
    C(617, provider="azure", stage="staging", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#storage", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: scan-ocr
provider:
  name: azure
  region: westeurope
functions:
  ocr:
    handler: app.ocr.scan
    events:
      - storage: https://acmescans.blob.core.windows.net/scans
""", "ocr", "scan"),
      user="I pasted the container URL from the Azure portal into the storage trigger. It says container name must be 3-63 lowercase letters, digits, dashes.",
      steps=[
          S("get_validation"),
          S("ask_user", question="The trigger wants only the container name (`scans`). Is `acmescans` the storage account pskit creates for this app, or an existing account of yours?",
            options=["pskit's account, create the container", "an existing account"], answer="pskit's account, create the container"),
          S("propose_plan", steps=["Set the storage trigger of `ocr` to `scans`", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ocr.events.0", value={"storage": "scans"}),
      ],
      final="""`bucket` (or the shorthand) is the container name, not a URL; on Azure it must be 3-63 lowercase letters, digits or dashes [docs/events.md#storage].

Now `- storage: scans`; pskit creates the container in the app's storage account [docs/providers.md#azure-azure-functions]. `pskit validate -p azure -s staging`: valid."""),

    # ------------------------------------------------------------------ 618  azure nested variable -> stages
    C(618, provider="azure", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/configuration.md#stages-per-stage-overrides"],
      project=proj("""service: mail-queue
provider:
  name: azure
  region: westeurope
custom:
  queues:
    dev: outbox-dev
    prod: outbox-prod
functions:
  sender:
    handler: app.mail.send
    events:
      - queue: ${self:custom.queues.${opt:stage}}
""", "mail", "send"),
      user="""Error: unresolved variables: self:custom.queues.${opt:stage

the closing } is missing in the message?""",
      steps=[
          S("get_validation"),
          S("search_docs", query="per stage values",
            docs=[D("docs/configuration.md", "stages-per-stage-overrides")]),
          S("propose_plan", steps=["Set the queue of `sender` to `outbox-dev`", "Add `stages.prod.functions.sender.events: [{queue: outbox-prod}]`",
                                   "Remove `custom.queues`", "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.sender.events", value=[{"queue": "outbox-dev"}]),
          S("set_config", path="stages", value={"prod": {"functions": {"sender": {"events": [{"queue": "outbox-prod"}]}}}}),
          S("set_config", path="custom", value=None),
      ],
      final="""A variable inside another variable isn't resolved, so pskit read `self:custom.queues.${opt:stage` as one name; that's why the brace looks cut off. Per-stage values go in `stages:` instead [docs/configuration.md#stages-per-stage-overrides].

- default: `queue: outbox-dev`
- `stages.prod`: `queue: outbox-prod`

Validate for azure (dev): valid. To check prod too, run `pskit validate -p azure -s prod` or pick stage prod in the top bar and press **Validate**."""),

    # ------------------------------------------------------------------ 619  azure storage_connection set to ${env:...}
    C(619, provider="azure", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions"],
      project=proj("""service: legacy-queue
provider:
  name: azure
  region: westeurope
  options:
    storage_connection: ${env:LEGACY_STORAGE_CONNECTION_STRING}
functions:
  drain:
    handler: app.legacy.drain
    events:
      - queue: {name: legacy-orders, existing: true}
""", "legacy", "drain"),
      user="The legacy-orders queue is in an old storage account. I set storage_connection to ${env:LEGACY_STORAGE_CONNECTION_STRING} so the connection string isn't in the file, but validate says unresolved variables. I don't want to export the secret on my laptop.",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure storage_connection app setting",
            docs=[D("docs/providers.md", "azure-azure-functions", start="```yaml", end="storage_connection: OTHER_STORAGE")]),
          S("propose_plan", steps=["Set `provider.options.storage_connection` to the app setting name `LEGACY_STORAGE` (not the string itself)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.storage_connection", value="LEGACY_STORAGE"),
      ],
      final="""`storage_connection` takes the *name* of an app setting, not the connection string, so no secret is needed in pskit.yml or on your laptop [docs/providers.md#azure-azure-functions].

Set `storage_connection: LEGACY_STORAGE`. Validate for azure: valid. Before the first run, add an app setting `LEGACY_STORAGE` to the Function App holding the old account's connection string."""),

    # ------------------------------------------------------------------ 620  azure schedule 30 seconds
    C(620, provider="azure", stage="staging", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#schedule"],
      project=proj("""service: heartbeat
provider:
  name: azure
  region: westeurope
functions:
  beat:
    handler: app.beat.send
    events:
      - schedule: 30 seconds
""", "beat", "send"),
      user="schedule 30 seconds → cron 5-field error. NCRONTAB has seconds, why not",
      steps=[
          S("get_validation"),
          S("ask_user", question="pskit rates are minutes, hours or days (portable 5-field cron), so 1 minute is the shortest. Use `1 minute`?",
            options=["1 minute", "other"], answer="1 minute"),
          S("propose_plan", steps=["Set the schedule of `beat` to `1 minute`", "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.beat.events.0", value={"schedule": "1 minute"}),
      ],
      final="""pskit writes the 6-field NCRONTAB itself from a portable rate or 5-field cron, and rates go down to minutes, not seconds [docs/events.md#schedule].

Set `- schedule: 1 minute`. `pskit validate -p azure -s staging`: valid."""),
]

