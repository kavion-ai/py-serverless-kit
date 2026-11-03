"""Category C (fix a validation error), batch 20 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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
    # ------------------------------------------------------------------ 381  aws `s3:` event
    C(381, provider="aws", stage="dev", mode="auto", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#storage"],
      project=proj("""service: receipt-scanner
provider:
  name: aws
  region: eu-west-1
functions:
  scan:
    handler: app.scan.on_upload
    events:
      - s3: receipt-uploads
""", "scan", "on_upload"),
      user="Ported from SAM. `- s3: receipt-uploads` gives unknown event type 's3'. Lambda should fire on new objects in that bucket.",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage event bucket created",
            docs=[D("docs/events.md", "storage", end="Each record has `bucket`, `key`, `size` and `action` (`\"created\"` / `\"deleted\"`).")]),
          S("propose_plan", steps=["Replace `s3: receipt-uploads` with `storage: receipt-uploads` on `scan` (fires on created objects by default)",
                                   "Validate for aws"]),
          S("set_config", path="functions.scan.events.0", value={"storage": "receipt-uploads"}),
      ],
      final="""pskit's portable name for the S3 trigger is `storage` [docs/events.md#storage].

Changed to `- storage: receipt-uploads`. The default is `events: [created]`, so it fires on new objects. `pskit validate` for aws: valid. pskit creates the bucket; if it already exists, add `existing: true`."""),

    # ------------------------------------------------------------------ 382  aws storage events s3:ObjectCreated:*
    C(382, provider="aws", stage="staging", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=proj("""service: avatar-store
provider:
  name: aws
  region: ap-south-1
functions:
  thumb:
    handler: app.avatars.thumb
    events:
      - storage:
          bucket: avatar-originals
          events: ["s3:ObjectCreated:*"]
          suffix: .png
""", "avatars", "thumb"),
      user="i write events s3:ObjectCreated:* like aws doc, pskit say should be created or deleted. ok so what i write",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.thumb.events.0.storage.events` to `[created]`",
                                   "Validate for aws, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.thumb.events.0.storage.events", value=["created"]),
      ],
      final="""pskit uses its own short names: `created` and `deleted`. It maps them to the S3 events for you [docs/events.md#storage].

I set `events: [created]` on `thumb` (the `.png` suffix stays). `pskit validate -p aws -s staging`: valid. Because `created` is the default, you could also remove the `events:` line."""),

    # ------------------------------------------------------------------ 383  gcp storage events finalize
    C(383, provider="gcp", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#storage", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: csv-loader
provider:
  name: gcp
  region: europe-west1
  options:
    project: csv-loader-dev
functions:
  load-csv:
    handler: app.loader.load_csv
    events:
      - storage:
          bucket: csv-landing
          events: [finalize, delete]
          suffix: .csv
""", "loader", "load_csv"),
      user="load-csv should run when a CSV is finalized in csv-landing and also when one is deleted (so we can drop the rows). I used the GCS event names finalize/delete and validation rejects both. Use whatever pskit expects.",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage events created deleted gcp",
            docs=[D("docs/events.md", "storage", start="| Provider | Service | Filters | Notes |", end="| azure |")]),
          S("propose_plan", steps=["Set `functions.load-csv.events.0.storage.events` to `[created, deleted]`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.load-csv.events.0.storage.events", value=["created", "deleted"]),
      ],
      final="""pskit's storage events are named `created` and `deleted`; on GCP they become the Eventarc `finalized` and `deleted` triggers [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Set `events: [created, deleted]` on `load-csv`. `pskit validate` for gcp: valid. On GCP the two events are deployed as separate Cloud Functions with the same handler, so check `event.records[0].action` (`"created"` or `"deleted"`) in the code [docs/events.md#storage]."""),

    # ------------------------------------------------------------------ 384  azure blob created+deleted, ask
    C(384, provider="azure", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#storage", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=proj("""service: asset-index
provider:
  name: aws
  region: us-east-1
providers:
  azure:
    region: westeurope
functions:
  index:
    handler: app.index.update
    events:
      - storage:
          bucket: shared-assets
          events: [created, deleted]
""", "index", "update"),
      user="""ERROR: [functions.index] Azure blob triggers only fire on created/updated blobs

works on aws. prod on azure is new""",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure blob trigger deleted",
            docs=[D("docs/events.md", "storage", start="| azure |", end="in another account need `options.storage_connection` |")]),
          S("ask_user", question="Azure can't tell `index` about deleted blobs. On Azure only, should I keep the trigger for created blobs, or turn `index` off there?",
            options=["Keep created only on Azure", "Disable index on Azure"],
            answer="Keep created only on Azure"),
          S("propose_plan", steps=["Add `providers.azure.functions.index.events: [{storage: {bucket: shared-assets, events: [created]}}]` (AWS keeps created + deleted)",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.azure.functions.index.events",
            value=[{"storage": {"bucket": "shared-assets", "events": ["created"]}}]),
      ],
      final="""Azure blob triggers fire only for created or updated blobs, so `deleted` can't be used there [docs/events.md#storage].

On Azure only, `index` now has `storage: {bucket: shared-assets, events: [created]}`; AWS keeps both events (a `providers:` list replaces the base list for that cloud) [docs/configuration.md#switch-something-off-on-one-cloud]. `pskit validate -p azure -s prod`: valid.

On Azure the index won't remove entries for deleted assets. Plan a cleanup job for that, e.g. a schedule that checks for missing blobs."""),

    # ------------------------------------------------------------------ 385  aws dead_letter as a mapping
    C(385, provider="aws", stage="dev", mode="auto", page="Functions", persona="terse_expert",
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
          name: outbound-hooks
          dead_letter: {name: outbound-hooks-dlq}
          max_receive: 3
""", "relay", "forward"),
      user="dead_letter: Input should be a valid string. dlq name is outbound-hooks-dlq, 3 receives",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.relay.events.0.queue.dead_letter` to the string `outbound-hooks-dlq`",
                                   "Validate for aws"]),
          S("set_config", path="functions.relay.events.0.queue.dead_letter", value="outbound-hooks-dlq"),
      ],
      final="""`dead_letter` takes the DLQ name as a plain string, not a mapping [docs/events.md#queue].

Set `dead_letter: outbound-hooks-dlq`; `max_receive: 3` stays, so SQS moves a message there after 3 receives. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 386  azure Logic Apps result_path index
    C(386, provider="azure", stage="staging", mode="ask", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#compiler-notes-and-limits", "docs/workflows.md#data-flow"],
      project=proj("""service: kyc-check
provider:
  name: azure
  region: francecentral
functions:
  fetch-docs:
    handler: app.kyc.fetch_docs
  score:
    handler: app.kyc.score
workflows:
  verify:
    engine: native
    start_at: FetchDocs
    states:
      FetchDocs:
        type: task
        function: fetch-docs
        result_path: "$.documents[0]"
        next: Score
      Score: {type: task, function: score, end: true}
""", "kyc", "fetch_docs", "score"),
      user="""workflow verify: native engine
  ERROR: [workflows.verify] result_path '$.documents[0]' uses an array index, which Logic Apps can't write

score reads the first document. how do I keep that working?""",
      steps=[
          S("get_validation"),
          S("search_docs", query="result_path logic apps array index",
            docs=[D("docs/workflows.md", "data-flow")]),
          S("propose_plan", steps=["Change `FetchDocs.result_path` to `$.document` (a plain key)",
                                   "Validate for azure, stage staging",
                                   "Then `score` reads `event.data[\"document\"]` instead of the first list item"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.verify.states.FetchDocs.result_path", value="$.document"),
      ],
      final="""Logic Apps can't write a result into a list position, so `result_path` may not contain `[0]` on the native Azure engine [docs/workflows.md#compiler-notes-and-limits].

`FetchDocs` now stores its result under `$.document` (the rest of the data is kept) [docs/workflows.md#data-flow]. `pskit validate -p azure -s staging`: valid.

Update `score` to read `event.data["document"]` instead of the first element of `documents`. Want me to change the handler too?"""),

    # ------------------------------------------------------------------ 387  gcp ${env:GOOGLE_CLOUD_PROJECT} unset
    C(387, provider="gcp", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: quiz-app
provider:
  name: gcp
  region: us-west1
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT}
functions:
  questions:
    handler: app.quiz.questions
    events:
      - http: GET /questions
""", "quiz", "questions"),
      user="validate says unresolved variables: env:GOOGLE_CLOUD_PROJECT. my teammate said it works on his laptop",
      steps=[
          S("get_validation"),
          S("search_docs", query="unresolved variables env default",
            docs=[D("docs/configuration.md", "variables", end="| `${opt:stage}` / `${opt:provider}` / `${opt:region}` | effective CLI values (`${opt:x, default}` allowed) |")]),
          S("ask_user", question="The project id comes from the environment variable GOOGLE_CLOUD_PROJECT, which is set on your teammate's laptop but not here. Which project id should be the default when it is not set?",
            answer="quiz-app-dev-5521"),
          S("propose_plan", steps=["Change `provider.options.project` to `${env:GOOGLE_CLOUD_PROJECT, quiz-app-dev-5521}`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.project", value="${env:GOOGLE_CLOUD_PROJECT, quiz-app-dev-5521}"),
      ],
      final="""`${env:GOOGLE_CLOUD_PROJECT}` reads an environment variable. Your teammate has it set; your computer doesn't, and without a default that is an error [docs/configuration.md#variables].

Now it is `project: ${env:GOOGLE_CLOUD_PROJECT, quiz-app-dev-5521}`: the variable wins when it is set, otherwise `quiz-app-dev-5521` is used. Validate: valid.

To use the variable here too: **Setup & credentials** > *Environment variables* > **Set for this session**."""),

    # ------------------------------------------------------------------ 388  aws ${opt:tenant}
    C(388, provider="aws", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: tenant-portal
provider:
  name: aws
  region: eu-central-1
  environment:
    TENANT: ${opt:tenant}
functions:
  portal:
    handler: app.portal.home
    events:
      - http: GET /
""", "portal", "home"),
      user="I wanted to pass the tenant on the command line, so I wrote TENANT: ${opt:tenant}. Validation for prod says `unresolved variables: opt:tenant`. The tenant is fixed per deployment anyway (acme for now). Make it reusable from one place.",
      steps=[
          S("get_validation"),
          S("search_docs", query="opt variables stage provider region",
            docs=[D("docs/configuration.md", "variables", end="| `${file(path.json)}` | file content relative to the config: `.json` / `.yml` parsed, other files as stripped text |")]),
          S("propose_plan", steps=["Add `custom.tenant: acme`",
                                   "Change `provider.environment.TENANT` to `${self:custom.tenant}`",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="custom.tenant", value="acme"),
          S("set_config", path="provider.environment.TENANT", value="${self:custom.tenant}"),
      ],
      final="""`${opt:...}` only knows `stage`, `provider` and `region` (the CLI values), so `opt:tenant` can't resolve [docs/configuration.md#variables].

Now the tenant lives in one place:

```yaml
custom:
  tenant: acme
provider:
  environment:
    TENANT: ${self:custom.tenant}
```

`pskit validate -p aws -s prod`: valid. If you later want to choose it per machine or CI job, use `${env:TENANT, acme}` instead."""),

    # ------------------------------------------------------------------ 389  azure ${file(settings.json)} missing
    C(389, provider="azure", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/configuration.md#variables"],
      project=proj("""service: label-printer
provider:
  name: azure
  region: westeurope
  environment: ${file(settings.json)}
functions:
  print-label:
    handler: app.labels.print_label
    events:
      - http: POST /labels
""", "labels", "print_label"),
      user="i want keep env settings in settings.json file, but validate say file not exist. i not created it yet. settings are PRINTER_DPI 300 and LABEL_SIZE 4x6",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Create `settings.json` next to pskit.yml with PRINTER_DPI and LABEL_SIZE",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("write_file", path="settings.json", content="{\n  \"PRINTER_DPI\": \"300\",\n  \"LABEL_SIZE\": \"4x6\"\n}\n"),
          S("validate"),
      ],
      final="""`${file(settings.json)}` reads a file next to pskit.yml, and that file didn't exist yet [docs/configuration.md#variables].

I created `settings.json`:

```json
{
  "PRINTER_DPI": "300",
  "LABEL_SIZE": "4x6"
}
```

Validate now passes. Keep only normal settings in this file; passwords still go in `${env:NAME}`."""),

    # ------------------------------------------------------------------ 390  aws concurrency -1
    C(390, provider="aws", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: search-api
provider:
  name: aws
  region: us-west-2
functions:
  search:
    handler: app.search.query
    concurrency: -1
    events:
      - http: GET /search
""", "search", "query"),
      user="concurrency -1 = unreserved in lambda. pskit rejects it",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `functions.search.concurrency` (no reserved concurrency)",
                                   "Validate for aws"]),
          S("set_config", path="functions.search.concurrency", value=None),
      ],
      final="""pskit's `concurrency` is an int ≥ 0 and has no default; unreserved is expressed by leaving it out [docs/configuration.md#functions].

Removed `concurrency` from `search`. `pskit validate` for aws: valid. Don't use `0`: it reserves zero."""),

    # ------------------------------------------------------------------ 391  gcp architecture arm
    C(391, provider="gcp", stage="staging", mode="ask", page="Overview", persona="beginner",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: weather-bot
provider:
  name: gcp
  region: europe-north1
  architecture: arm
  options:
    project: weather-bot-staging
functions:
  forecast:
    handler: app.weather.forecast
    events:
      - schedule: "0 7 * * *"
""", "weather", "forecast"),
      user="I read ARM is cheaper so I set architecture: arm on the Overview page. Now there's an error. Did I break it?",
      steps=[
          S("get_validation"),
          S("search_docs", query="architecture x86_64 arm64",
            docs=[D("docs/configuration.md", "provider", start="| `architecture` |", end="used by AWS and for pip wheel selection |")]),
          S("propose_plan", steps=["Remove `provider.architecture` (GCP doesn't use it; default x86_64)",
                                   "Validate for gcp, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.architecture", value=None),
      ],
      final="""Nothing is broken. The value can only be `x86_64` or `arm64`, and on GCP the setting isn't used anyway: it matters for AWS and for picking pip wheels [docs/configuration.md#provider].

I removed `architecture`, so the default `x86_64` applies. Validate for staging: valid."""),

    # ------------------------------------------------------------------ 392  aws architecture aarch64
    C(392, provider="aws", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/configuration.md#provider"],
      project=proj("""service: image-tagger
provider:
  name: aws
  region: eu-west-1
  architecture: aarch64
functions:
  tag:
    handler: app.tagger.tag
    memory: 2048
    events:
      - storage: tagger-images
""", "tagger", "tag"),
      user="graviton lambda want, i put aarch64 but error. prod",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.architecture` to `arm64` (Graviton)",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.architecture", value="arm64"),
      ],
      final="""pskit calls it `arm64`, not `aarch64` (the only values are `x86_64` and `arm64`) [docs/configuration.md#provider].

Set `provider.architecture: arm64`, so Lambda runs on Graviton and pip picks arm64 wheels for the bundle. `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 393  azure environment differs (warning)
    C(393, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#azure-one-function-app-per-service"],
      project=proj("""service: shop-backend
provider:
  name: azure
  region: westeurope
functions:
  cart:
    handler: app.shop.cart
    environment:
      LOG_LEVEL: DEBUG
    events:
      - http: GET /cart
  checkout:
    handler: app.shop.checkout
    environment:
      LOG_LEVEL: INFO
    events:
      - http: POST /checkout
""", "shop", "cart", "checkout"),
      user="The Functions page shows a yellow warning for checkout about LOG_LEVEL. Validation passes, but I want it clean. cart uses DEBUG and checkout INFO.",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure environment app-wide",
            docs=[D("docs/events.md", "azure-one-function-app-per-service")]),
          S("ask_user", question="On Azure both functions share one Function App, so there is only one LOG_LEVEL. Which value should it be?",
            options=["INFO", "DEBUG"], answer="INFO"),
          S("propose_plan", steps=["Set `provider.environment.LOG_LEVEL: INFO`",
                                   "Remove `LOG_LEVEL` from `cart` and `checkout`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.environment.LOG_LEVEL", value="INFO"),
          S("set_config", path="functions.cart.environment", value=None),
          S("set_config", path="functions.checkout.environment", value=None),
      ],
      final="""On Azure every function of a service runs in one Function App, so `environment` is app-wide and the two LOG_LEVEL values fought each other (last one wins) [docs/events.md#azure-one-function-app-per-service].

Now `LOG_LEVEL: INFO` is set once under `provider.environment`, and the per-function values are gone. `pskit validate` for azure: valid, no warnings."""),

    # ------------------------------------------------------------------ 394  gcp iam.statements warning -> service account
    C(394, provider="gcp", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: report-mailer
provider:
  name: gcp
  region: europe-west2
  options:
    project: report-mailer-prod
  iam:
    statements:
      - actions: ["storage.objects.get"]
        resources: ["*"]
functions:
  mail-report:
    handler: app.reports.mail_report
    events:
      - schedule: "0 6 * * 1"
""", "reports", "mail_report"),
      user="Validate on gcp prod passes but warns that iam.statements are ignored. On AWS that block is how my Lambda got permissions. How do I give this function bucket read access on GCP?",
      steps=[
          S("get_validation"),
          S("search_docs", query="gcp service account iam statements ignored",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="```yaml", end="# optional runtime identity")]),
          S("ask_user", question="On GCP the function runs as a service account, and you grant roles to it in GCP. Which service account should `report-mailer` run as?",
            answer="reports-runtime@report-mailer-prod.iam.gserviceaccount.com, it already has Storage Object Viewer"),
          S("propose_plan", steps=["Set `provider.options.service_account` to reports-runtime@report-mailer-prod.iam.gserviceaccount.com",
                                   "Remove `provider.iam` (AWS-style, ignored on GCP)",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.service_account", value="reports-runtime@report-mailer-prod.iam.gserviceaccount.com"),
          S("set_config", path="provider.iam", value=None),
      ],
      final="""GCP doesn't take AWS-style statements; the function gets its permissions from the service account it runs as [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Set `provider.options.service_account: reports-runtime@report-mailer-prod.iam.gserviceaccount.com` and removed the ignored `iam` block. `pskit validate -p gcp -s prod`: valid, no warning. Bucket read access comes from that account's Storage Object Viewer role."""),

    # ------------------------------------------------------------------ 395  aws engine stepfunctions
    C(395, provider="aws", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=["docs/workflows.md#workflow-keys", "docs/workflows.md#engines"],
      project=proj("""service: refund-flow
provider:
  name: aws
  region: us-east-1
functions:
  check:
    handler: app.refunds.check
  refund:
    handler: app.refunds.refund
workflows:
  refund:
    engine: stepfunctions
    start_at: Check
    states:
      Check: {type: task, function: check, next: Refund}
      Refund: {type: task, function: refund, end: true}
""", "refunds", "check", "refund"),
      user="I want this workflow to be a real Step Functions state machine, so I wrote engine: stepfunctions. pskit doesn't accept it.",
      steps=[
          S("get_validation"),
          S("search_docs", query="workflow engine native auto embedded",
            docs=[D("docs/workflows.md", "workflow-keys", start="| `engine` |", end="`embedded` forces the engine everywhere |")]),
          S("propose_plan", steps=["Set `workflows.refund.engine` to `native` (Step Functions on AWS)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.refund.engine", value="native"),
      ],
      final="""`engine` takes `auto`, `native` or `embedded`; on AWS "native" means Step Functions [docs/workflows.md#workflow-keys].

Set `engine: native` on `refund`. `pskit validate` for aws: valid, and it reports the native engine. `auto` (the default) would also give Step Functions on AWS; `native` makes validate fail if you ever point the file at a cloud without a native engine [docs/workflows.md#engines]."""),

    # ------------------------------------------------------------------ 396  gcp state types capitalized
    C(396, provider="gcp", stage="dev", mode="auto", page="Workflows", persona="pasted_error",
      sources=["docs/workflows.md#state-types"],
      project=proj("""service: signup-wf
provider:
  name: gcp
  region: us-central1
  options:
    project: signup-wf-dev
functions:
  create-user:
    handler: app.users.create_user
workflows:
  signup:
    start_at: CreateUser
    states:
      CreateUser: {type: Task, function: create-user, next: Done}
      Done: {type: Succeed}
""", "users", "create_user"),
      user="""Error: pskit.yml is invalid:
  - workflows.signup.states.CreateUser.type: Input should be 'task', 'choice', 'wait', 'pass', 'parallel', 'map', 'succeed' or 'fail'
  - workflows.signup.states.Done.type: Input should be 'task', 'choice', 'wait', 'pass', 'parallel', 'map', 'succeed' or 'fail'""",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `CreateUser.type` to `task` and `Done.type` to `succeed` (lowercase)",
                                   "Validate for gcp"]),
          S("set_config", path="workflows.signup.states.CreateUser.type", value="task"),
          S("set_config", path="workflows.signup.states.Done.type", value="succeed"),
      ],
      final="""State types are lowercase in pskit (`task`, `succeed`, ...), unlike ASL's `Task` / `Succeed` [docs/workflows.md#state-types].

Changed `CreateUser` → `type: task` and `Done` → `type: succeed`. `pskit validate` for gcp: valid (native Cloud Workflows)."""),

    # ------------------------------------------------------------------ 397  azure function-level python3.13
    C(397, provider="azure", stage="staging", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/providers.md#providers"],
      project=proj("""service: geo-tools
provider:
  name: azure
  region: westus2
functions:
  distance:
    handler: app.geo.distance
    events:
      - http: GET /distance
  tiles:
    handler: app.geo.tiles
    runtime: python3.13
    events:
      - http: GET /tiles/{z}/{x}/{y}
""", "geo", "distance", "tiles"),
      user="tiles pinned to 3.13 for a newer lib, azure staging rejects it. options?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure python runtimes",
            docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| [`alibaba`]")]),
          S("propose_plan", steps=["Remove `functions.tiles.runtime` (falls back to python3.12, Azure's newest)",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.tiles.runtime", value=None),
      ],
      final="""Azure Functions run python3.9-3.12 in pskit; 3.13 isn't available there [docs/providers.md#providers].

Removed the pin on `tiles`, so it uses python3.12 like `distance`. `pskit validate -p azure -s staging`: valid. Check that the library version you need still supports 3.12; if it requires 3.13, that function has to run on aws or gcp."""),

    # ------------------------------------------------------------------ 398  aws provider-level timeout 1000
    C(398, provider="aws", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/providers.md#providers", "docs/configuration.md#provider"],
      project=proj("""service: survey-tool
provider:
  name: aws
  region: ca-central-1
  timeout: 1000
functions:
  submit:
    handler: app.survey.submit
    events:
      - http: POST /answers
  results:
    handler: app.survey.results
    events:
      - http: GET /results
""", "survey", "submit", "results"),
      user="why can't I deploy to aws? both functions are red",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Remove `provider.timeout: 1000`, so both functions use the default 30 s",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.timeout", value=None),
      ],
      final="""Both functions inherit `provider.timeout: 1000`, and AWS Lambda allows at most 900 seconds [docs/providers.md#providers].

These are web routes, and API Gateway gives up after 30 s anyway, so I removed the line and both use the default 30 s [docs/configuration.md#provider]. Validate: valid. You can deploy from the **Deploy** page now."""),

    # ------------------------------------------------------------------ 399  gcp rate 90 seconds
    C(399, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=proj("""service: price-watch
provider:
  name: gcp
  region: asia-southeast1
  options:
    project: price-watch-dev
functions:
  poll-prices:
    handler: app.prices.poll
    events:
      - schedule: {rate: 90 seconds}
""", "prices", "poll"),
      user="i want poll every 90 second, pskit say rate must look like minutes hours days",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule rate minutes",
            docs=[D("docs/events.md", "schedule", end="name: morning-report               # optional, used in the resource name")]),
          S("ask_user", question="Schedules are in minutes at the smallest. Every 1 minute or every 2 minutes?",
            options=["1 minute", "2 minutes"], answer="2 minutes is ok"),
          S("propose_plan", steps=["Set the rate of `poll-prices` to `2 minutes`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.poll-prices.events.0.schedule.rate", value="2 minutes"),
      ],
      final="""A schedule rate is `<n> minutes|hours|days`, so seconds can't be used [docs/events.md#schedule].

Set `rate: 2 minutes` on `poll-prices`; on GCP Cloud Scheduler gets it as cron `*/2 * * * *`. Validate: valid."""),

    # ------------------------------------------------------------------ 400  azure timer timezone (warning)
    C(400, provider="azure", stage="prod", mode="auto", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#schedule", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: payroll-jobs
provider:
  name: azure
  region: japaneast
functions:
  payslips:
    handler: app.payroll.payslips
    events:
      - schedule:
          cron: "0 9 25 * *"
          timezone: Asia/Tokyo
""", "payroll", "payslips"),
      user="Prod validation passes but warns that the timezone is ignored for payslips. Payslips must go out at 09:00 Tokyo time on the 25th. Fix it so it really runs then.",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure timer timezone utc",
            docs=[D("docs/events.md", "schedule", start="A rate that can't be expressed as cron")]),
          S("propose_plan", steps=["Change the cron of `payslips` to `0 0 25 * *` (09:00 Asia/Tokyo = 00:00 UTC)",
                                   "Remove `timezone` (Azure timers run in UTC)",
                                   "Validate for azure, stage prod"]),
          S("set_config", path="functions.payslips.events.0.schedule.cron", value="0 0 25 * *"),
          S("set_config", path="functions.payslips.events.0.schedule.timezone", value=None),
      ],
      final="""Azure Linux Consumption timers always run in UTC, so `timezone: Asia/Tokyo` was ignored and the job would have run at 09:00 UTC (18:00 Tokyo) [docs/providers.md#azure-azure-functions].

Changed the cron to `0 0 25 * *` and removed `timezone`. 00:00 UTC is 09:00 in Tokyo, and Japan has no daylight-saving time, so it stays correct all year. `pskit validate -p azure -s prod`: valid, no warning."""),
]
