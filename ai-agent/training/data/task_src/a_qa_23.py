"""Category A (docs Q&A and how-to), batch 23: aws / gcp / azure. HTTP CORS and auth, schedules with timezones,
GCP splitting, Azure app-wide settings, invoke(), logs retention, native workflows, local runs.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(431, provider="aws", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#http"],
      user="Our React app on https://shop.example.com calls GET and POST /cart on our Lambda API and the browser blocks it with a CORS error. Only that origin should be allowed, with the Authorization header. How do I set this up?",
      steps=[S("search_docs", query="cors origins headers http route",
               docs=[D("docs/events.md", "http", start="**CORS**", end="AWS additionally configures CORS on the HTTP API.")])],
      final="""Turn on CORS on both `/cart` routes and list your origin. The runtime answers `OPTIONS` preflights with 204 and adds the `Access-Control-*` headers; on AWS pskit also configures CORS on the HTTP API [docs/events.md#http].

**In studio**
1. Open **Functions** and click the function that owns `/cart`.
2. In its HTTP trigger, open *CORS*, click *Add origin* and enter `https://shop.example.com` under *Allowed origins*.
3. Do the same for the other `/cart` route, then click **Save**.

**In code**
```yaml
functions:
  cart:
    handler: app.cart.handler
    events:
      - http:
          path: /cart
          method: GET
          cors:
            origins: ["https://shop.example.com"]
            methods: [GET, POST]
            headers: [Content-Type, Authorization]
      - http:
          path: /cart
          method: POST
          cors:
            origins: ["https://shop.example.com"]
            methods: [GET, POST]
            headers: [Content-Type, Authorization]
```

**In the terminal**
```bash
pskit validate
pskit deploy
```
`Authorization` and `Content-Type` are already in the default headers; listing them keeps it explicit."""),

    A(432, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http", "docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      user="can i put auth: key on my gcp http function? want simple api key for partner",
      steps=[S("search_docs", query="http auth key gcp support",
               docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` | azure (function key, `AuthLevel.FUNCTION`), huawei (`APP`) |")]),
             S("search_docs", query="gcp limits auth jwt key",
               docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="**Limits:**")])],
      final="""No. On GCP, `auth: jwt` and `auth: key` aren't supported; `pskit validate` reports an error [docs/providers.md#gcp-google-cloud-functions-2nd-gen]. On GCP you can use [docs/events.md#http]:

- `auth: iam`: pskit doesn't add the public invoker binding, so only callers with Google credentials (and the invoker role) get in.
- `auth: none` and check the key yourself in the handler.

**In code** (key check in the handler):
```yaml
functions:
  partner-api:
    handler: app.partner.handler
    environment:
      PARTNER_KEY: ${env:PARTNER_KEY}
    events:
      - http: {path: /partner/orders, method: GET, auth: none}
```
```python
from __future__ import annotations

from py_serverless_kit import Unauthorized


def handler(event, ctx):
    if event.http.headers.get("x-api-key") != ctx.env.get("PARTNER_KEY"):
        raise Unauthorized("bad api key")
    return {"orders": []}
```
`PARTNER_KEY` comes from your environment at deploy time, never written in the file."""),

    A(433, provider="azure", stage="staging", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#storage", "docs/providers.md#azure-azure-functions"],
      user="azure: storage trigger with events [created, deleted] on container uploads. supported?",
      steps=[S("search_docs", query="azure blob trigger deleted events",
               docs=[D("docs/events.md", "storage", start="| azure | Blob trigger", end="| azure | Blob trigger")]),
             S("search_docs", query="azure functions limits blob deleted",
               docs=[D("docs/providers.md", "azure-azure-functions", start="**Limits:**")])],
      final="""No. Azure blob triggers fire on **created/updated** blobs only; `deleted` isn't available, and `pskit validate` reports `Azure blob triggers only fire on created/updated blobs` [docs/events.md#storage] [docs/providers.md#azure-azure-functions].

Options:
1. Keep `events: [created]` on Azure (the default).
2. If you also deploy elsewhere, keep `[created, deleted]` in the base file and override only Azure:
```yaml
providers:
  azure:
    functions:
      on-upload:
        events:
          - storage: {bucket: uploads, events: [created]}
```
Lists replace, so on Azure the function gets just this trigger.
3. If you need delete handling on Azure, have the code that deletes blobs publish a message to a queue or topic, and trigger a function from that.

Container names must be 3–63 lowercase characters."""),

    A(434, provider="aws", stage="prod", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#schedule"],
      user="i need my report function to run monday to friday at 8:30 in the morning, berlin time not utc. how?",
      steps=[S("search_docs", query="schedule cron weekdays timezone",
               docs=[D("docs/events.md", "schedule", end="| aws | EventBridge Scheduler |"),
                     D("docs/events.md", "schedule", start="A rate that can't be expressed")])],
      final="""Use a cron schedule with a timezone. AWS EventBridge Scheduler honours `timezone` [docs/events.md#schedule].

**In studio**
1. Open **Functions** and click your report function.
2. Under *Add a trigger*, choose **Schedule**.
3. Pick the preset *Weekdays 08:30* (or set the time in the cron editor).
4. Set *Timezone* to `Europe/Berlin`. The time above is in this zone.
5. Click **Save**.

**In code**
```yaml
functions:
  report:
    handler: app.report.run
    events:
      - schedule:
          cron: "30 8 * * 1-5"
          timezone: Europe/Berlin
```
pskit converts the 5-field cron to AWS's own format for you.

**In the terminal**
Run it once locally to check the handler:
```bash
pskit invoke -f report -t schedule
```"""),

    A(435, provider="gcp", stage="dev", mode="auto", page="Overview", persona="terse_expert",
      sources=["docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      user="gcp console shows worker, worker-queue0 and worker-storage0 but my yml has one function 'worker'. why",
      steps=[S("search_docs", query="gcp split function queue0 storage0",
               docs=[D("docs/events.md", "gcp-multi-trigger-functions-are-split-automatically")])],
      final="""That's expected. A Cloud Function (gen2) has at most one event trigger and can't mix HTTP with events, so pskit deploys one logical function as several Cloud Functions with the same code and handler [docs/events.md#gcp-multi-trigger-functions-are-split-automatically]:

- `worker`: the HTTP deployment (it exists when the function has `http` events, no triggers, is a workflow task, or has schedules with no Pub/Sub trigger to publish to).
- `worker-queue0`, `worker-storage0`: one per event trigger.

`pskit info` and the dashboard still show one `worker`; the extra deployments are in its `extra` output. The event deployments are limited to a 540 s timeout. Your handler doesn't change."""),

    A(436, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/providers.md#azure-azure-functions"],
      user="on azure do my urls get /api in front like normal azure functions? my route is /orders",
      steps=[S("search_docs", query="azure route prefix api path",
               docs=[D("docs/providers.md", "azure-azure-functions", start="One **Linux Consumption Function App**", end="`{path+}` becomes Azure's `{*path}`.")])],
      final="""No. pskit sets `routePrefix` to empty, so `/orders` is served as `/orders`, without `/api` [docs/providers.md#azure-azure-functions].

All functions of the service live in one Linux Consumption Function App, so the URL is `https://<function app host>/orders`. Run `pskit info` after deploying to see the exact URL. A greedy path like `/files/{path+}` becomes Azure's `{*path}` for you."""),

    A(437, provider="aws", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition", "docs/events.md#storage"],
      user="My SAM template has an S3 event: Type S3, Events s3:ObjectCreated:*, Filter suffix .csv on our existing bucket acme-imports. The bucket must stay owned by the old stack for now. What's the pskit.yml equivalent?",
      steps=[S("search_docs", query="SAM S3 event translate storage existing suffix",
               docs=[D("docs/migrating-from-aws.md", "step-2-translate-the-sam-serverless-cdk-definition")])],
      final="""Use a `storage` event with `existing: true`, so pskit uses the bucket and doesn't create it [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition].

**In code**
```yaml
functions:
  import-csv:
    handler: app.imports.handle
    events:
      - storage:
          bucket: acme-imports
          existing: true
          events: [created]
          suffix: .csv
```
In the handler, each record has `bucket`, `key`, `size` and `action`:
```python
from __future__ import annotations


def handle(event, ctx):
    for record in event.records:
        ctx.logger.info("new file", extra={"key": record.key, "size": record.size})
```

Keep `existing: true` while the old stack owns the bucket."""),

    A(438, provider="gcp", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/cli.md#pskit-workflow"],
      user="cli only: start the deployed order-pipeline on gcp prod with input {\"id\": 7} and follow it until it finishes",
      steps=[S("search_docs", query="workflow start status watch deployed",
               docs=[D("docs/cli.md", "pskit-workflow", start="Deployed workflows", end="| `status` |")])],
      final="""**In the terminal**
```bash
pskit workflow start order-pipeline -s prod -i '{"id": 7}'
pskit workflow status <execution_id> -s prod -w order-pipeline --watch --history
```
`start` prints the `execution_id`, the status and a console link. `--watch` polls every 2 s until the run finishes; `-w` helps GCP resolve the id. These need `pip install "py-serverless-kit[gcp]"` and read `.pskit/gcp-prod/deployment.json`, so deploy first [docs/cli.md#pskit-workflow]."""),

    A(439, provider="azure", stage="dev", mode="ask", page="Functions", persona="detailed_spec",
      sources=["docs/events.md#azure-one-function-app-per-service"],
      user="On Azure, I set LOG_LEVEL=DEBUG on the worker function and LOG_LEVEL=INFO on the api function. Validate shows a warning and both seem to get the same value. Can't functions have their own environment on Azure?",
      steps=[S("search_docs", query="azure environment app-wide function app warning",
               docs=[D("docs/events.md", "azure-one-function-app-per-service")])],
      final="""No. Every function of a service lives in one Function App, so `environment` is app-wide. pskit merges all functions' variables and warns when two functions set the same key to different values; only one value can win [docs/events.md#azure-one-function-app-per-service].

Use different keys and read the right one in each handler:

**In code**
```yaml
functions:
  api:
    handler: app.api.handler
    environment: {API_LOG_LEVEL: INFO}
  worker:
    handler: app.worker.handler
    environment: {WORKER_LOG_LEVEL: DEBUG}
```

**In studio**
1. Open **Functions**, click `api`, and rename the variable under *Environment variables*.
2. Do the same for `worker`, then click **Save**. The warning disappears from the Problems list.

For the pskit log level you can also set it per function in the function's *Logging* section."""),

    A(440, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#invoke-calling-another-function"],
      user="I used boto3.client('lambda').invoke to call the billing Lambda from orders. What's the pskit way, and what permissions does it need on AWS?",
      steps=[S("search_docs", query="invoke another function aws permissions",
               docs=[D("docs/handlers.md", "invoke-calling-another-function")])],
      final="""Use `invoke()`. On AWS it calls `lambda:InvokeFunction` through boto3, so you need boto3 in `requirements.txt` and an IAM grant [docs/handlers.md#invoke-calling-another-function].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import invoke


def create(event, ctx):
    order = event.http.json()
    bill = invoke("billing", {"order_id": order["id"]})          # waits for the result
    invoke("audit", {"order_id": order["id"]}, asynchronous=True)  # fire and forget
    return {"order": order["id"], "bill": bill}
```
```yaml
functions:
  orders:
    handler: app.orders.create
    iam:
      statements:
        - {actions: ["lambda:InvokeFunction"], resources: ["arn:aws:lambda:*:*:function:shop-dev-*"]}
    events:
      - http: POST /orders
```
Deployed functions are named `<service>-<stage>-<function>`, so replace `shop` with your service name.

**In the terminal**
```bash
pip install "py-serverless-kit[aws]"
pskit invoke -f orders -d '{"id": 1}'
```
Locally, `invoke()` runs the other handler in-process, so no AWS call is made."""),

    A(441, provider="gcp", stage="staging", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen", "docs/events.md#gcp-multi-trigger-functions-are-split-automatically"],
      user="ERROR: [functions.export] event-triggered functions are limited to 540s on GCP\n\ni set timeout 900 because export is slow",
      steps=[S("search_docs", query="gcp event-triggered functions 540s timeout",
               docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="**Limits:**")])],
      final="""On GCP, functions triggered by an event (queue, topic, storage) can run at most 540 s. HTTP functions can go to 3600 s [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

Choices:
1. Set `timeout: 540` or less and make the export faster or smaller (process fewer records per message).
2. Split the work: the event function puts chunks on a queue, and each chunk is handled within 540 s.
3. If you deploy the same file to other clouds, lower it only on GCP:
```yaml
providers:
  gcp:
    functions:
      export: {timeout: 540}
```

**In studio**
1. Open **Functions**, click `export`, and set *Timeout (s)* to 540.
2. Click **Save**; the error leaves the Problems list.

**In the terminal**
```bash
pskit validate -p gcp -s staging
```"""),

    A(442, provider="azure", stage="dev", mode="ask", page="Overview", persona="informal_non_native",
      sources=["docs/providers.md", "docs/configuration.md#default-runtime"],
      user="python 3.13 is ok on azure functions with pskit?",
      steps=[S("search_docs", query="azure runtimes supported python versions",
               docs=[D("docs/providers.md", "providers", start="| Provider | Tier |", end="| [`azure`]")]),
             S("search_docs", query="default runtime pinned runtime",
               docs=[D("docs/configuration.md", "default-runtime")])],
      final="""No. Azure supports Python 3.9–3.12 with pskit [docs/providers.md]. With `runtime: python3.13`, `pskit validate` reports an error.

Easiest fix: don't pin `runtime`. pskit then uses python3.12 where the cloud supports it, which Azure does [docs/configuration.md#default-runtime].

**In code**
```yaml
provider:
  name: azure
  runtime: python3.12
```
(or remove the `runtime` line). Keep your handlers Python 3.9 compatible anyway, so they run on every version."""),

    A(443, provider="aws", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#provider"],
      user="Compliance wants Lambda logs kept for 90 days in CloudWatch for prod only; dev can stay at the default. Where is that configured?",
      steps=[S("search_docs", query="log retention cloudwatch days",
               docs=[D("docs/configuration.md", "provider", start="| `log_retention_days` |", end="| `log_retention_days` |")]),
             S("search_docs", query="stage overrides prod",
               docs=[D("docs/configuration.md", "stages-per-stage-overrides")])],
      final="""Use `provider.log_retention_days` (default 14, AWS CloudWatch log group retention) and set it only for `prod` with a stage override [docs/configuration.md#provider] [docs/configuration.md#stages-per-stage-overrides].

**In code**
```yaml
stages:
  prod:
    provider:
      log_retention_days: 90
```

**In studio**
1. Open **Overview & provider** with stage `prod` in the top bar.
2. Set *Log retention (days)* to 90 and click **Save**.
Check the YAML page afterwards: the value should sit under `stages.prod` if you want dev to keep 14.

**In the terminal**
```bash
pskit plan -s prod
```
The plan shows the log group retention change before you deploy."""),

    A(444, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen"],
      user="i add iam statements for read gcs bucket but on gcp still permission denied. why not working",
      steps=[S("search_docs", query="gcp iam statements ignored service account",
               docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="provider:", end="| Trigger | Implementation |")]),
             S("search_docs", query="gcp limits iam",
               docs=[D("docs/providers.md", "gcp-google-cloud-functions-2nd-gen", start="**Limits:**")])],
      final="""On GCP, `iam.statements` are ignored (they're AWS-style). Give the needed roles to a service account and run the functions as it with `options.service_account` [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

**In code**
```yaml
provider:
  name: gcp
  options:
    project: my-gcp-project
    service_account: runtime@my-gcp-project.iam.gserviceaccount.com
```
Then grant that service account read access to the bucket (for example the Storage Object Viewer role) in your GCP project, outside pskit or with `provider.terraform.extra`.

**In studio**
1. Open **Overview & provider**.
2. Fill in the provider option *service_account* and click **Save**.

Then redeploy so the functions use that account."""),

    A(445, provider="azure", stage="dev", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/providers.md#azure-azure-functions", "docs/workflows.md#workflow-keys"],
      user="azure: run my workflow as a Logic App instead of the orchestrator function. how, and how do i start it after deploy",
      steps=[S("search_docs", query="azure native workflow logic app start",
               docs=[D("docs/providers.md", "azure-azure-functions", start="**Native workflows (Logic Apps, opt-in).**", end="**Native workflows (Logic Apps, opt-in).**")])],
      final="""Set `engine: native` on the workflow. `auto` keeps the embedded engine on Azure; `native` deploys a Logic App with an HTTP request trigger [docs/providers.md#azure-azure-functions].

**In code**
```yaml
workflows:
  order-pipeline:
    engine: native
    start_at: Validate
    states:
      Validate: {type: task, function: validate, end: true}
```

**In studio**
1. Open **Workflows** and open the workflow.
2. Set *Engine* to native and click **Save**.

**In the terminal**
```bash
pskit deploy
pskit info
```
`pskit info` shows the workflow `url`, the trigger's callback URL. Start a run with a `POST` of the JSON input to it. The URL contains a SAS signature, so treat it like a secret. Each task function gets a `POST /_pskit/invoke/<function>` route that the Logic App calls with the function key."""),

    A(446, provider="aws", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflows.md#workflow-keys"],
      user="for aws step functions there is standard and express. which one pskit uses and can i change it?",
      steps=[S("search_docs", query="step functions standard express type",
               docs=[D("docs/workflows.md", "workflow-keys", end="| `options.type` |")])],
      final="""pskit uses `STANDARD` by default. You can change it per workflow with `options.type: EXPRESS`; it's AWS only [docs/workflows.md#workflow-keys].

**In code**
```yaml
workflows:
  order-pipeline:
    options:
      type: EXPRESS
    start_at: Validate
    states:
      Validate: {type: task, function: validate, end: true}
```
The only two values are `STANDARD` and `EXPRESS`. Leave the key out to keep the default. On other clouds `options.type` has no effect."""),

    A(447, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=["docs/studio.md#what-you-can-do"],
      user="only studio steps please: where do i type my google cloud project id?",
      steps=[S("search_docs", query="studio provider options project id",
               docs=[D("docs/studio.md", "what-you-can-do", start="| **Overview & provider** |", end="| **Overview & provider** |")])],
      final="""**In studio**
1. Open **Overview & provider**.
2. Make sure Google Cloud is the selected provider.
3. In the provider's own options, fill in *project* with your GCP project id [docs/studio.md#what-you-can-do].
4. Click **Save**. The `GCP needs provider.options.project` problem disappears from the Problems list."""),

    A(448, provider="aws", stage="dev", mode="auto", page="Code", persona="terse_expert",
      sources=["docs/handlers.md#context"],
      user="handler code only: stop my batch loop before the lambda timeout hits",
      steps=[S("search_docs", query="context remaining time timeout",
               docs=[D("docs/handlers.md", "context")])],
      final="""**In code**
```python
from __future__ import annotations


def handler(event, ctx):
    done = 0
    for record in event.records:
        left = ctx.remaining_time_ms()
        if left is not None and left < 5000:
            ctx.logger.warning("stopping early", extra={"done": done})
            break
        process(record.json())
        done += 1
    return {"done": done}
```
`ctx.remaining_time_ms()` returns the ms until the timeout, or `None` when the platform doesn't say [docs/handlers.md#context]. Replace `process` with your own function."""),

    A(449, provider="azure", stage="staging", mode="ask", page="Test", persona="detailed_spec",
      sources=["docs/cli.md#pskit-trigger", "docs/studio.md#setup-logs-and-provider-differences"],
      user="Our queue worker is deployed to Azure staging. I want to drop a real message on its Storage Queue from my laptop and see what happens. What does pskit need for that?",
      steps=[S("search_docs", query="trigger azure storage queue send message",
               docs=[D("docs/cli.md", "pskit-trigger", start="What pskit can send itself", end="`oci`, `ibmcloud`, `tccli`, `doctl`, `curl`) and the console steps instead.")])],
      final="""`pskit trigger` can send a real Storage Queue message on Azure. It needs `AZURE_STORAGE_CONNECTION_STRING` set to the connection string of the Function App's storage account [docs/cli.md#pskit-trigger].

**In studio**
1. Open **Setup & credentials**, enter `AZURE_STORAGE_CONNECTION_STRING` under *Environment variables* and click **Set for this session**. It isn't written to disk.
2. Open **Test** with azure / staging in the top bar, pick the worker and its queue trigger.
3. Edit the payload, turn on *Show the function's logs* and click **☁ Send to azure / staging**.

**In the terminal**
```bash
export AZURE_STORAGE_CONNECTION_STRING='<connection string from the portal>'
pskit trigger -s staging -f worker -e 0 -d '{"id": 1}'
pskit logs -s staging -f --function worker
```
Logs on Azure come from Log Analytics and lag a few seconds."""),

    A(450, provider="gcp", stage="dev", mode="ask", page="Test", persona="beginner",
      sources=["docs/local-development.md#local-development", "docs/getting-started.md#1-install"],
      user="do i need to login with gcloud before i can run my functions on my laptop?",
      steps=[S("search_docs", query="local run without credentials terraform",
               docs=[D("docs/local-development.md", "local-development", end="Only the cloud-specific adapter is skipped.")]),
             S("search_docs", query="no terraform credentials local development validate package",
               docs=[D("docs/getting-started.md", "1-install", start="You don't need Terraform or credentials")])],
      final="""No. Running locally needs no cloud credentials and no Terraform. Handlers run through the same dispatcher as in the cloud; only the GCP adapter is skipped [docs/local-development.md#local-development]. `pskit validate` and `pskit package` don't need them either [docs/getting-started.md#1-install].

**In studio**
1. Open **Test** and pick the function and its event.
2. Click **▶ Run locally**.

**In the terminal**
```bash
pskit dev
pskit invoke -f hello --path "/hello?name=Ada"
```
You need `gcloud auth application-default login` only when you deploy or send events to the deployed functions."""),
]
