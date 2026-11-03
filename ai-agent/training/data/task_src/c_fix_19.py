"""Category C (fix a validation error), batch 19 (aws/gcp/azure). Hand-written; assembled by tools/assemble.py."""

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


def proj(yml, module, *names):
    return dict(files={"pskit.yml": yml, "app/__init__.py": "", f"app/{module}.py": handlers(*names)})


CONVERSATIONS = [
    # ------------------------------------------------------------------ 361  aws: serverless.yml `sqs:` event
    C(361, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/events.md#queue"],
      project=proj("""service: invoice-ingest
provider:
  name: aws
  region: us-east-1
functions:
  ingest:
    handler: app.ingest.handle
    timeout: 60
    events:
      - sqs: arn:aws:sqs:us-east-1:123456789012:invoice-jobs
""", "ingest", "handle"),
      user="I copied the events block from my serverless.yml (`- sqs: <queue arn>`). The queue invoice-jobs already exists in the account. pskit says unknown event type 'sqs'.",
      steps=[
          S("get_validation"),
          S("search_docs", query="queue event existing queue",
            docs=[D("docs/events.md", "queue", start="```yaml", end="fifo: false")]),
          S("propose_plan", steps=["Replace the `sqs:` event of `ingest` with `queue: {name: invoice-jobs, existing: true}`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.ingest.events", value=[{"queue": {"name": "invoice-jobs", "existing": True}}]),
      ],
      final="""pskit has no `sqs` event: the portable trigger is `queue`, which becomes SQS on AWS, and it takes the queue name, not the ARN [docs/events.md#queue].

Changed `ingest` to:

```yaml
events:
  - queue: {name: invoice-jobs, existing: true}
```

`existing: true` tells pskit to use your queue instead of creating one. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 362  aws runtime python3.14
    C(362, provider="aws", stage="staging", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/providers.md#providers", "docs/configuration.md#default-runtime"],
      project=proj("""service: pricing-engine
provider:
  name: aws
  region: eu-west-1
  runtime: python3.14
functions:
  quote:
    handler: app.pricing.quote
    events:
      - http: POST /quote
""", "pricing", "quote"),
      user="pricing-engine staging fails on runtime. want the newest python lambda has.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `provider.runtime` to python3.13 (newest that AWS Lambda accepts in pskit)",
                                   "Validate for aws, stage staging"]),
          S("set_config", path="provider.runtime", value="python3.13"),
      ],
      final="""AWS Lambda runs python3.9-3.13 in pskit, so the pinned `python3.14` is rejected [docs/providers.md#providers].

Set `provider.runtime: python3.13`. `pskit validate -p aws -s staging`: valid. Make sure your dependencies have 3.13 wheels; otherwise drop the pin and pskit uses python3.12 [docs/configuration.md#default-runtime]."""),

    # ------------------------------------------------------------------ 363  gcp project at the wrong level
    C(363, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: recipe-box
provider:
  name: gcp
  region: europe-west1
  project: recipe-box-dev-20417
functions:
  recipes:
    handler: app.recipes.list_recipes
    events:
      - http: GET /recipes
""", "recipes", "list_recipes"),
      user="I added my google project id like the error said but now it says \"provider.project: Extra inputs are not permitted\". What did I do wrong?",
      steps=[
          S("get_validation"),
          S("search_docs", query="gcp project option",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="```yaml", end="service_account:")]),
          S("propose_plan", steps=["Remove `provider.project`",
                                   "Add `provider.options.project: recipe-box-dev-20417`",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.project", value=None),
          S("set_config", path="provider.options.project", value="recipe-box-dev-20417"),
      ],
      final="""The project id was right, only one level too high. It belongs under `provider.options`, not directly under `provider` [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Now it reads:

```yaml
provider:
  name: gcp
  region: europe-west1
  options:
    project: recipe-box-dev-20417
```

Validate says the configuration is valid."""),

    # ------------------------------------------------------------------ 364  azure container name
    C(364, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#storage"],
      project=proj("""service: invoice-ocr
provider:
  name: azure
  region: westeurope
functions:
  read-invoice:
    handler: app.ocr.read_invoice
    events:
      - storage:
          bucket: Invoice_Uploads
          suffix: .pdf
""", "ocr", "read_invoice"),
      user="azure say container name 'Invoice_Uploads' must be lowercase. can you fix name, i dont care how its called",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the container of `read-invoice` to `invoice-uploads`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.read-invoice.events.0.storage.bucket", value="invoice-uploads"),
      ],
      final="""Azure blob container names must be 3-63 lowercase letters, digits and dashes, so capitals and `_` are not allowed [docs/events.md#storage].

I changed the bucket to `invoice-uploads` (the `.pdf` suffix stays). `pskit validate` for azure: valid. Upload your files into the `invoice-uploads` container after deploy."""),

    # ------------------------------------------------------------------ 365  gcp auth jwt
    C(365, provider="gcp", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: partner-feed
provider:
  name: gcp
  region: us-central1
  options:
    project: partner-feed-prod
functions:
  feed:
    handler: app.feed.get_feed
    events:
      - http:
          path: /feed
          method: GET
          auth: jwt
          authorizer:
            issuer: https://auth.example.com/
            audience: [partner-feed]
""", "feed", "get_feed"),
      user="""ERROR: [functions.feed] http auth 'jwt' is not supported on GCP; use none or iam

prod, gcp. what do I pick?""",
      steps=[
          S("get_validation"),
          S("search_docs", query="http auth iam gcp",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("ask_user", question="On GCP, `auth: iam` means only callers with Google credentials (Cloud Run invoker) may call /feed; `auth: none` makes it public and you check the JWT in the handler. Which one?",
            options=["iam", "none (check the token in my code)"],
            answer="iam, partners get a service account"),
          S("propose_plan", steps=["Set `functions.feed.events.0.http.auth` to `iam`",
                                   "Remove the `authorizer` block (only used by jwt on AWS)",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.feed.events.0.http.auth", value="iam"),
          S("set_config", path="functions.feed.events.0.http.authorizer", value=None),
      ],
      final="""JWT authorizers are an AWS API Gateway feature; on GCP pskit supports `none` or `iam` [docs/events.md#http].

Changed `/feed` to `auth: iam` and removed the unused `authorizer`. With `iam` pskit doesn't add the public `allUsers` invoker binding [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. `pskit validate -p gcp -s prod`: valid.

Give each partner's service account the invoker role on the function; they call it with a Google ID token."""),

    # ------------------------------------------------------------------ 366  azure timeout 900
    C(366, provider="azure", stage="prod", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/providers.md#providers"],
      project=proj("""service: video-transcode
provider:
  name: azure
  region: northeurope
functions:
  transcode:
    handler: app.media.transcode
    timeout: 900
    memory: 1536
    events:
      - queue: transcode-jobs
  status:
    handler: app.media.status
    events:
      - http: GET /status/{job_id}
""", "media", "transcode", "status"),
      user="We are moving video-transcode from AWS to Azure (prod). The transcode worker had timeout 900 on Lambda and validation now fails for it. Jobs normally finish within 8 minutes. Please set the highest value Azure allows and leave everything else alone.",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure max timeout",
            docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| [`alibaba`]")]),
          S("propose_plan", steps=["Set `functions.transcode.timeout` to 600 (Azure Functions maximum in pskit)",
                                   "Validate for azure, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.transcode.timeout", value=600),
      ],
      final="""Azure Functions allow at most 600 s in pskit (AWS allowed 900) [docs/providers.md#providers].

Set `functions.transcode.timeout: 600`; nothing else changed. `pskit validate -p azure -s prod`: valid. Your 8-minute jobs fit in 10 minutes, but with little margin: if a file runs longer, Azure stops it and the message goes back to the queue."""),

    # ------------------------------------------------------------------ 367  aws artifact_upload inline
    C(367, provider="aws", stage="dev", mode="auto", page="Overview", persona="pasted_error",
      sources=["docs/providers.md#aws-aws-lambda"],
      project=proj("""service: tiny-webhook
provider:
  name: aws
  region: ap-southeast-2
  options:
    artifact_upload: inline
functions:
  hook:
    handler: app.hook.receive
    events:
      - http: POST /hook
""", "hook", "receive"),
      user="""ERROR: [provider.options.artifact_upload] artifact_upload must be 's3' or 'direct'

I want to skip the S3 code bucket, it's a 2 KB function""",
      steps=[
          S("get_validation"),
          S("search_docs", query="aws artifact_upload direct",
            docs=[D("docs/providers.md", "aws-aws-lambda", start="**Options**", end="(inline zip; only for small bundles)")]),
          S("propose_plan", steps=["Set `provider.options.artifact_upload` to `direct` (inline zip, no S3 bucket)",
                                   "Validate for aws"]),
          S("set_config", path="provider.options.artifact_upload", value="direct"),
      ],
      final="""The inline option is called `direct`, not `inline`; the only values are `s3` (default) and `direct` [docs/providers.md#aws-aws-lambda].

Set `provider.options.artifact_upload: direct`. `pskit validate` for aws: valid. Fine for a 2 KB bundle; switch back to `s3` if the bundle grows (inline uploads hit the 50 MB limit)."""),

    # ------------------------------------------------------------------ 368  aws storage resource + bucket
    C(368, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#events-backed-by-a-resource"],
      project=proj("""service: photo-resizer
provider:
  name: aws
  region: eu-central-1
resources:
  photos: {type: storage}
functions:
  resize:
    handler: app.photos.resize
    events:
      - storage:
          resource: photos
          bucket: photos-incoming
          prefix: raw/
""", "photos", "resize"),
      user="Fix the problems on the Functions page",
      steps=[
          S("get_validation"),
          S("search_docs", query="storage event resource and bucket",
            docs=[D("docs/events.md", "events-backed-by-a-resource")]),
          S("ask_user", question="`resize` names both the `photos` resource and a bucket `photos-incoming`. On AWS it can be only one. Which bucket should trigger it?",
            options=["The `photos` resource (pskit creates it)", "A bucket called photos-incoming"],
            answer="The `photos` resource (pskit creates it)"),
          S("propose_plan", steps=["Remove `bucket: photos-incoming` from the storage event of `resize` (keep `resource: photos`, `prefix: raw/`)",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.resize.events.0.storage.bucket", value=None),
      ],
      final="""The storage trigger of `resize` named both a resource and a bucket. Only on-premises can a resource carry a second bucket; on AWS you pick one [docs/events.md#events-backed-by-a-resource].

I removed `bucket: photos-incoming`, so the trigger is `storage: {resource: photos, prefix: raw/}`. The Functions page has no errors now, and `pskit validate` for aws says valid."""),

    # ------------------------------------------------------------------ 369  gcp provider timeout 900 with queue function
    C(369, provider="gcp", stage="staging", mode="auto", page="Functions", persona="terse_expert",
      sources=["docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      project=proj("""service: etl-runner
provider:
  name: gcp
  region: europe-west4
  timeout: 900
  options:
    project: etl-runner-staging
functions:
  export:
    handler: app.etl.export
    events:
      - http: POST /export
  load:
    handler: app.etl.load
    events:
      - queue: etl-batches
""", "etl", "export", "load"),
      user="gcp staging validate: load limited to 540s. keep 900 for the http export.",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Add `functions.load.timeout: 540` (event functions max); keep `provider.timeout: 900` for export",
                                   "Validate for gcp, stage staging"]),
          S("set_config", path="functions.load.timeout", value=540),
      ],
      final="""`provider.timeout: 900` was inherited by `load`, and event-triggered Cloud Functions are capped at 540 s [docs/events.md#gcp-multi-trigger-functions-are-split-automatically].

Added `functions.load.timeout: 540`; `export` (HTTP) keeps 900. `pskit validate -p gcp -s staging`: valid."""),

    # ------------------------------------------------------------------ 370  azure auth iam
    C(370, provider="azure", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/events.md#http", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: inventory-api
provider:
  name: azure
  region: eastus
functions:
  stock:
    handler: app.stock.get_stock
    events:
      - http:
          path: /stock/{sku}
          method: GET
          auth: iam
""", "stock", "get_stock"),
      user="On AWS this route used AWS_IAM so only our backend could call it. Azure rejects auth iam. What's the closest thing?",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure auth key function key",
            docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` |")]),
          S("propose_plan", steps=["Set `functions.stock.events.0.http.auth` to `key` (Azure function key)",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.stock.events.0.http.auth", value="key"),
      ],
      final="""Azure has no IAM-signed requests in pskit; the closest built-in option is `auth: key`, an Azure function key (`AuthLevel.FUNCTION`) [docs/events.md#http].

Changed `/stock/{sku}` to `auth: key`. `pskit validate` for azure: valid. Your backend must now send the function key instead of signing requests. For identity-based access, the validate message suggests API Management or Easy Auth in front [docs/providers.md#azure-azure-functions]."""),

    # ------------------------------------------------------------------ 371  aws EventBridge cron syntax
    C(371, provider="aws", stage="prod", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#schedule"],
      project=proj("""service: backup-runner
provider:
  name: aws
  region: us-west-2
functions:
  nightly-backup:
    handler: app.backup.run
    timeout: 600
    events:
      - schedule: "cron(0 3 * * ? *)"
""", "backup", "run"),
      user="i put cron(0 3 * * ? *) like in aws console, pskit say must be 5-field. is same thing no?",
      steps=[
          S("get_validation"),
          S("search_docs", query="schedule cron format aws",
            docs=[D("docs/events.md", "schedule", start="pskit converts the portable syntax", end="| gcp |")]),
          S("propose_plan", steps=["Change the schedule of `nightly-backup` to `0 3 * * *` (every day 03:00)",
                                   "Validate for aws, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.nightly-backup.events.0", value={"schedule": "0 3 * * *"}),
      ],
      final="""Same time, different format. pskit wants the standard 5-field cron (`0 3 * * *`) and writes the AWS form `cron(0 3 * * ? *)` for you [docs/events.md#schedule].

Changed the schedule to `"0 3 * * *"` (every day 03:00 UTC). `pskit validate -p aws -s prod`: valid."""),

    # ------------------------------------------------------------------ 372  smtp function on gcp -> disable there
    C(372, provider="gcp", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/events.md#events-triggers", "docs/configuration.md#switch-something-off-on-one-cloud"],
      project=proj("""service: helpdesk
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1
    port: 8120
providers:
  gcp:
    region: europe-west1
    options:
      project: helpdesk-prod-3391
resources:
  inbound-mail: {type: smtp}
functions:
  tickets:
    handler: app.desk.tickets
    events:
      - http: GET /tickets
  mail-in:
    handler: app.desk.mail_in
    events:
      - smtp: {resource: inbound-mail}
""", "desk", "tickets", "mail_in"),
      user="helpdesk runs on our own server and I now want the same service on GCP for prod. Validation for gcp fails because of mail-in. The mail intake must stay on-prem; the tickets API should go to GCP.",
      steps=[
          S("get_validation"),
          S("search_docs", query="smtp event provider support",
            docs=[D("docs/events.md", "events-triggers", start="| `smtp` |", end="[smtp/README.md](smtp/README.md).")]),
          S("propose_plan", steps=["Add `providers.gcp.functions.mail-in.enabled: false` (mail-in stays on-prem only)",
                                   "Mark the `inbound-mail` SMTP resource `external: true` on GCP only, so pskit doesn't create it there",
                                   "Validate for gcp, stage prod"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="providers.gcp.functions.mail-in.enabled", value=False),
          S("set_config", say="Now the GCP-only override for the SMTP resource.",
            path="providers.gcp.resources.inbound-mail.external", value=True),
      ],
      final="""`smtp` events and SMTP resources exist only on premises, so Google Cloud Functions can't run `mail-in` [docs/events.md#events-triggers].

Added, for GCP only:

```yaml
providers:
  gcp:
    functions:
      mail-in: {enabled: false}
    resources:
      inbound-mail: {external: true}
```

`pskit validate -p gcp -s prod` has no errors now (it lists `mail-in` as disabled). On-prem nothing changed, so mail intake keeps running there [docs/configuration.md#switch-something-off-on-one-cloud]."""),

    # ------------------------------------------------------------------ 373  azure existing topic needs servicebus options
    C(373, provider="azure", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#topic", "docs/providers.md#azure-azure-functions"],
      project=proj("""service: order-audit
provider:
  name: azure
  region: westeurope
functions:
  audit:
    handler: app.audit.record
    events:
      - topic:
          name: order-events
          existing: true
""", "audit", "record"),
      user="""ERROR: [functions.audit] existing topics need options.servicebus_namespace_id and options.servicebus_connection (name of an app setting)

the topic is in our shared service bus""",
      steps=[
          S("get_validation"),
          S("search_docs", query="azure existing topic servicebus options",
            docs=[D("docs/providers.md", "azure-azure-functions", start="```yaml", end="servicebus_connection: SB_CONNECTION                          # app setting with its connection string")]),
          S("ask_user", question="I need two values: the resource id of the shared Service Bus namespace, and the name of the app setting that will hold its connection string.",
            answer="/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/shared-rg/providers/Microsoft.ServiceBus/namespaces/acme-bus and call the setting SHARED_SB"),
          S("propose_plan", steps=["Set `provider.options.servicebus_namespace_id` to the given namespace id",
                                   "Set `provider.options.servicebus_connection: SHARED_SB`",
                                   "Validate for azure, stage staging"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.options.servicebus_namespace_id",
            value="/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/shared-rg/providers/Microsoft.ServiceBus/namespaces/acme-bus"),
          S("set_config", path="provider.options.servicebus_connection", value="SHARED_SB"),
      ],
      final="""With `existing: true` pskit doesn't create the topic, so it needs to know which namespace has it and which app setting has the connection string [docs/events.md#topic].

Added under `provider.options`: `servicebus_namespace_id: /subscriptions/.../namespaces/acme-bus` and `servicebus_connection: SHARED_SB`. `pskit validate -p azure -s staging`: valid.

The Function App needs an app setting `SHARED_SB` with the connection string. Keep that string out of pskit.yml: read it with `${env:SHARED_SB}` [docs/providers.md#azure-azure-functions]."""),

    # ------------------------------------------------------------------ 374  aws iam statements in CloudFormation case
    C(374, provider="aws", stage="dev", mode="ask", page="YAML", persona="beginner",
      sources=["docs/configuration.md#provider", "docs/providers.md#aws-aws-lambda"],
      project=proj("""service: file-share
provider:
  name: aws
  region: eu-west-2
  iam:
    statements:
      - Effect: Allow
        Action: ["s3:GetObject", "s3:PutObject"]
        Resource: "arn:aws:s3:::file-share-data/*"
functions:
  upload:
    handler: app.files.upload
    events:
      - http: POST /files
""", "files", "upload"),
      user="I pasted the permission from an AWS policy and now there are 4 red errors about Effect, Action and Resource. I don't understand them.",
      steps=[
          S("get_validation"),
          S("search_docs", query="iam statements effect actions resources",
            docs=[D("docs/configuration.md", "provider", start="| `iam.statements` |", end="Ignored (with a warning) on clouds that don't map it |")]),
          S("propose_plan", steps=["Rewrite `provider.iam.statements` with pskit's lowercase keys: `effect`, `actions`, `resources`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="provider.iam.statements",
            value=[{"effect": "Allow", "actions": ["s3:GetObject", "s3:PutObject"], "resources": ["arn:aws:s3:::file-share-data/*"]}]),
      ],
      final="""pskit uses its own lowercase keys for permissions: `effect`, `actions` and `resources` (a list). The AWS policy spelling `Effect` / `Action` / `Resource` is not accepted [docs/configuration.md#provider].

Now it is:

```yaml
iam:
  statements:
    - effect: Allow
      actions: ["s3:GetObject", "s3:PutObject"]
      resources: ["arn:aws:s3:::file-share-data/*"]
```

The same permission, only written the pskit way. Validate: valid."""),

    # ------------------------------------------------------------------ 375  gcp `pubsub:` event
    C(375, provider="gcp", stage="dev", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#topic", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      project=proj("""service: signup-events
provider:
  name: gcp
  region: asia-northeast1
  options:
    project: signup-events-dev
functions:
  on-signup:
    handler: app.signup.on_signup
    events:
      - pubsub: user-signups
""", "signup", "on_signup"),
      user="i want function run when message come in pubsub topic user-signups. i write pubsub: but error unknown event type",
      steps=[
          S("get_validation"),
          S("search_docs", query="pubsub topic trigger gcp",
            docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="| Trigger |", end="| workflows |")]),
          S("propose_plan", steps=["Replace `pubsub: user-signups` with `topic: user-signups` on `on-signup`",
                                   "Validate for gcp"]),
          S("set_config", path="functions.on-signup.events.0", value={"topic": "user-signups"}),
      ],
      final="""In pskit the trigger is called `topic`; on GCP it becomes a Pub/Sub topic with an Eventarc trigger [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Changed the event to `- topic: user-signups`. `pskit validate` for gcp: valid. Each message comes as one record in `event.records` [docs/events.md#topic]."""),

    # ------------------------------------------------------------------ 376  azure Logic Apps matches glob
    C(376, provider="azure", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/workflows.md#compiler-notes-and-limits", "docs/workflows.md#workflow-keys"],
      project=proj("""service: claims-flow
provider:
  name: azure
  region: westeurope
functions:
  fast-track:
    handler: app.claims.fast_track
  review:
    handler: app.claims.review
workflows:
  route-claim:
    engine: native
    start_at: Route
    states:
      Route:
        type: choice
        choices:
          - {variable: "$.code", matches: "CL-??-*", next: FastTrack}
        default: Review
      FastTrack: {type: task, function: fast-track, end: true}
      Review: {type: task, function: review, end: true}
""", "claims", "fast_track", "review"),
      user="native workflow on azure fails on the matches pattern. options?",
      steps=[
          S("get_validation"),
          S("search_docs", query="logic apps matches pattern",
            docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="`matches` accepts", end="other globs are a validation error.")]),
          S("ask_user", question="Logic Apps only accept `abc`, `abc*`, `*abc`, `*abc*` or `*`. Change the rule to `CL-*` (looser: no 2-character check), or keep `CL-??-*` and run the workflow on the embedded engine?",
            options=["Use CL-* and stay on Logic Apps", "Keep the pattern, engine: embedded"],
            answer="Keep the pattern, engine: embedded"),
          S("propose_plan", steps=["Set `workflows.route-claim.engine` to `embedded`",
                                   "Validate for azure"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.route-claim.engine", value="embedded"),
      ],
      final="""Logic Apps can't express a `?` glob, so `CL-??-*` fails when compiling to a native workflow [docs/workflows.md#compiler-notes-and-limits].

Set `engine: embedded` on `route-claim`: the pattern stays, and the workflow runs in pskit's orchestrator function [docs/workflows.md#workflow-keys]. `pskit validate -p azure`: valid. The warning that remains is expected: the whole run must fit in one function call (600 s max on Azure)."""),

    # ------------------------------------------------------------------ 377  aws retry max_attempts -1
    C(377, provider="aws", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#retry-and-catch"],
      project=proj("""service: payout-flow
provider:
  name: aws
  region: eu-west-1
functions:
  send-payout:
    handler: app.payouts.send
  alert:
    handler: app.payouts.alert
workflows:
  payout:
    start_at: SendPayout
    states:
      SendPayout:
        type: task
        function: send-payout
        retry:
          - errors: ["*"]
            max_attempts: -1
        catch:
          - errors: ["*"]
            next: Alert
        end: true
      Alert: {type: task, function: alert, end: true}
""", "payouts", "send", "alert"),
      user="In the payout workflow, SendPayout must never be retried (a retry could pay twice); any failure goes straight to Alert. I set max_attempts: -1 to switch retries off but validation rejects it. Fix it the right way.",
      steps=[
          S("get_validation"),
          S("search_docs", query="workflow retry max_attempts",
            docs=[D("docs/workflows.md", "retry-and-catch")]),
          S("propose_plan", steps=["Remove the `retry` list of `SendPayout` (no retrier = no retries); keep the catch to Alert",
                                   "Validate for aws"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="workflows.payout.states.SendPayout.retry", value=None),
      ],
      final="""`max_attempts` must be 0 or more; the clean way to say "never retry" is to have no `retry` rule at all [docs/workflows.md#retry-and-catch].

I removed `retry` from `SendPayout`. The `catch` with `errors: ["*"]` still sends every failure to `Alert`. `pskit validate` for aws: valid."""),

    # ------------------------------------------------------------------ 378  gcp memory "1GB"
    C(378, provider="gcp", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/configuration.md#functions"],
      project=proj("""service: pdf-maker
provider:
  name: gcp
  region: us-east1
  options:
    project: pdf-maker-dev-77
functions:
  render:
    handler: app.pdf.render
    memory: 1GB
    events:
      - http: POST /render
""", "pdf", "render"),
      user="I gave render more memory (1GB) and now it says unable to parse string as an integer?",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Set `functions.render.memory` to 1024 (MB)",
                                   "Validate for gcp"],
            result={"decision": "approved", "note": ""}),
          S("set_config", path="functions.render.memory", value=1024),
      ],
      final="""`memory` is a plain number of MB (64-32768), so `1GB` can't be read [docs/configuration.md#functions].

I wrote it as `memory: 1024`, which is 1 GB. Validate: valid. In studio you can set the same on **Functions** > `render` > *Memory (MB)*."""),

    # ------------------------------------------------------------------ 379  azure queue name with dots
    C(379, provider="azure", stage="staging", mode="auto", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue"],
      project=proj("""service: mail-queue
provider:
  name: azure
  region: uksouth
functions:
  sender:
    handler: app.mail.send
    events:
      - queue:
          name: mail.outbound
          batch_size: 16
""", "mail", "send"),
      user="queue mail.outbound not ok in azure? we use dots everywhere in names :(",
      steps=[
          S("get_validation"),
          S("propose_plan", steps=["Rename the queue of `sender` to `mail-outbound`",
                                   "Validate for azure, stage staging"]),
          S("set_config", path="functions.sender.events.0.queue.name", value="mail-outbound"),
      ],
      final="""Azure Storage Queue names can only have lowercase letters, digits and dashes (3-63), so dots are not allowed [docs/events.md#queue].

Renamed the queue to `mail-outbound`. `pskit validate -p azure -s staging`: valid. Note: `batch_size` is ignored on Azure Storage Queues."""),

    # ------------------------------------------------------------------ 380  aws {path+} not last
    C(380, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/events.md#http"],
      project=proj("""service: doc-store
provider:
  name: aws
  region: us-east-2
functions:
  get-file:
    handler: app.docs.get_file
    events:
      - http: GET /files/{path+}
  file-meta:
    handler: app.docs.file_meta
    events:
      - http: GET /files/{path+}/meta
""", "docs", "get_file", "file_meta"),
      user="""Error: pskit.yml is invalid:
  - functions.file-meta.events.0.path: Value error, invalid path template '/files/{path+}/meta'; use /users/{id} or /files/{path+}

need metadata for nested paths like a/b/c.pdf""",
      steps=[
          S("get_validation"),
          S("search_docs", query="greedy path parameter last segment",
            docs=[D("docs/events.md", "http", start="**Path templates**", end="`{user-id}` is not.")]),
          S("propose_plan", steps=["Move the greedy part to the end: `file-meta` route becomes `GET /meta/{path+}`",
                                   "Validate for aws"],
            result={"decision": "approved", "note": "ok, clients can call /meta/..."}),
          S("set_config", path="functions.file-meta.events.0.http", value="GET /meta/{path+}"),
      ],
      final="""`{path+}` takes the rest of the path, so it can only be the last segment; `/files/{path+}/meta` can't be routed [docs/events.md#http].

Changed `file-meta` to `GET /meta/{path+}` (e.g. `/meta/a/b/c.pdf`, `path_params["path"] == "a/b/c.pdf"`). `get-file` is unchanged. `pskit validate` for aws: valid."""),
]
