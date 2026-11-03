"""Category A (docs Q&A and how-to), batch 24: aws / gcp / azure. Queue options per cloud (FIFO, DLQ, poison,
partial failures), escape hatches, hooks, concurrency, function keys, logs, workflow limits and executions,
moving clouds. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CONVERSATIONS = [
    A(451, provider="aws", stage="dev", mode="ask", page="Functions", persona="terse_expert",
      sources=["docs/events.md#queue"],
      user="fifo sqs for ledger fn, batch 5, after 3 failed receives -> ledger-dlq. keys?",
      steps=[S("search_docs", query="queue fifo dead_letter max_receive batch_size",
               docs=[D("docs/events.md", "queue", end="| partial batch failure |")])],
      final="""**In code**
```yaml
functions:
  ledger:
    handler: app.ledger.handle
    events:
      - queue:
          name: ledger
          fifo: true
          batch_size: 5
          dead_letter: ledger-dlq
          max_receive: 3
```
On AWS, `fifo` gives the `.fifo` suffix and content-based dedup; `dead_letter` + `max_receive` become the SQS redrive policy [docs/events.md#queue]. Return a `BatchResult` so only failed messages are retried.

**In studio**
1. Open **Functions**, click `ledger`, and under *Add a trigger* pick **Queue**.
2. Fill in the name, batch size 5, dead letter `ledger-dlq`, max receive 3 and turn on fifo.
3. Click **Save**.

**In the terminal**
```bash
pskit validate
pskit invoke -f ledger -t queue -d '[{"id": 1}, {"id": 2}]'
```"""),

    A(452, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#queue", "docs/handlers.md#batchresult"],
      user="on gcp i set dead_letter for my queue but validate say warning ignored. so no dlq on gcp??",
      steps=[S("search_docs", query="gcp queue dead_letter ignored warning",
               docs=[D("docs/events.md", "queue", start="| Option | aws (SQS)", end="| partial batch failure |")])],
      final="""Right, on GCP pskit doesn't apply `dead_letter` / `max_receive`; a "queue" there is a Pub/Sub topic with a push trigger, and those options are ignored with a warning [docs/events.md#queue]. A failed delivery is retried as a whole.

What you can do:
1. Make the handler idempotent, because redelivery is normal.
2. Catch the errors you can't fix and park the message yourself, for example by writing it to a bucket or another topic with the Google Cloud SDK, then return normally so it isn't retried forever.
3. If you also deploy to AWS, keep `dead_letter` in the file: there it becomes a real SQS redrive policy.

Remove `dead_letter` from the GCP config (or a `providers.gcp` override) if you want the warning gone."""),

    A(453, provider="azure", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=["docs/events.md#queue", "docs/providers.md#azure-azure-functions"],
      user="when my azure queue function crashes many times on a message, where does the message go?",
      steps=[S("search_docs", query="azure storage queue failed messages poison",
               docs=[D("docs/events.md", "queue", start="| Option | aws (SQS)", end="| partial batch failure |")])],
      final="""On Azure it goes to a poison queue named `<queue>-poison`. For a queue called `jobs`, look in `jobs-poison` in the Function App's storage account. `dead_letter` and `max_receive` are ignored on Azure; Azure Storage Queues handle poison messages themselves [docs/events.md#queue].

A failed delivery is retried as a whole (no partial batch failure on Azure), so make the handler safe to run twice on the same message."""),

    A(454, provider="gcp", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=["docs/handlers.md#batchresult"],
      user="Our worker returns BatchResult and marks only the bad records as failed. On AWS that worked great. After moving to GCP it looks like good messages get processed twice. Is BatchResult different on GCP?",
      steps=[S("search_docs", query="BatchResult provider behaviour gcp whole delivery",
               docs=[D("docs/handlers.md", "batchresult", start="| Provider | Behaviour |")])],
      final="""Yes. Only AWS (SQS `batchItemFailures`) and on-premises retry just the failed records. On GCP any failure in a `BatchResult` raises `BatchFailure`, so the whole delivery is retried, including the records that already worked [docs/handlers.md#batchresult].

What to do:
1. Make processing idempotent, for example skip a record whose `record.id` you already stored.
2. Keep returning `BatchResult`: the code stays portable, and on AWS you keep the partial retry.

**In code**
```python
from __future__ import annotations

from py_serverless_kit import BatchResult


def worker(event, ctx):
    result = BatchResult()
    for record in event.records:
        if already_done(record.id):
            continue
        try:
            process(record.json())
            mark_done(record.id)
        except Exception:
            result.fail(record)
    return result
```
`already_done`, `mark_done` and `process` are your own functions (for example backed by a table)."""),

    A(455, provider="aws", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=["docs/configuration.md#escape-hatches"],
      user="yaml only: create a dynamodb table with the service and pass its name to create-order",
      steps=[S("search_docs", query="terraform extra dynamodb table tf reference",
               docs=[D("docs/configuration.md", "escape-hatches")])],
      final="""**In code**
```yaml
provider:
  name: aws
  terraform:
    extra:
      resource:
        aws_dynamodb_table:
          orders:
            name: orders-${opt:stage}
            billing_mode: PAY_PER_REQUEST
            hash_key: id
            attribute: [{name: id, type: S}]
functions:
  create-order:
    handler: app.orders.create
    environment:
      TABLE_NAME: ${tf:aws_dynamodb_table.orders.name}
    iam:
      statements:
        - {actions: ["dynamodb:PutItem"], resources: ["${tf:aws_dynamodb_table.orders.arn}"]}
```
`provider.terraform.extra` is raw Terraform JSON deep-merged into the generated config, and `${tf:...}` becomes a live Terraform reference [docs/configuration.md#escape-hatches]."""),

    A(456, provider="azure", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/providers.md#azure-azure-functions"],
      user="Our Azure admins only let us deploy into the existing resource group rg-orders-prod; we can't create resource groups. Can pskit deploy into that one?",
      steps=[S("search_docs", query="azure existing resource group option",
               docs=[D("docs/providers.md", "azure-azure-functions", start="provider:", end="One **Linux Consumption Function App**")])],
      final="""Yes. Set `options.resource_group` to the existing group, and pskit uses it instead of creating one [docs/providers.md#azure-azure-functions].

**In code**
```yaml
stages:
  prod:
    provider:
      options:
        resource_group: rg-orders-prod
```
Put it under `stages.prod` if only prod must use it, or under `provider.options` for every stage.

**In studio**
1. Open **Overview & provider** with azure / prod in the top bar.
2. Fill in the provider option *resource_group* and click **Save**.

**In the terminal**
```bash
pskit plan -s prod
```
The plan should show no `azurerm_resource_group` being created. Deploying still needs your subscription id (`ARM_SUBSCRIPTION_ID` or `options.subscription_id`)."""),

    A(457, provider="gcp", stage="staging", mode="ask", page="Deploy", persona="detailed_spec",
      sources=["docs/configuration.md#hooks"],
      user="After every deploy to staging I want to run scripts/smoke_test.py against the new endpoints, and the deploy should be marked as failed if the smoke test fails. Does pskit have hooks for that?",
      steps=[S("search_docs", query="hooks after_deploy script exit code",
               docs=[D("docs/configuration.md", "hooks")])],
      final="""Yes, use the `after_deploy` hook. Commands run through the shell in the project root with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set, and a non-zero exit aborts the command [docs/configuration.md#hooks].

**In code**
```yaml
hooks:
  after_deploy: ["python scripts/smoke_test.py"]
```
In the script, read `PSKIT_STAGE` to know which stage you're testing, and exit with a non-zero code on failure. If you only want it on staging, check `PSKIT_STAGE` in the script and exit 0 for the other stages.

**In the terminal**
```bash
pskit deploy -s staging
```
The hook runs after `terraform apply`, so the resources are already deployed when it fails; the failure makes `pskit deploy` exit with an error."""),

    A(458, provider="aws", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#functions"],
      user="In SAM I had ReservedConcurrentExecutions: 20 on the payments function so it doesn't hammer our database. Where does that go now?",
      steps=[S("search_docs", query="reserved concurrency function key",
               docs=[D("docs/configuration.md", "functions", start="    concurrency: 10", end="    concurrency: 10"),
                     D("docs/configuration.md", "functions", start="| `concurrency` |", end="| `concurrency` |")])],
      final="""Use `concurrency` on the function: reserved concurrency (or max instances where the cloud supports it) [docs/configuration.md#functions].

**In code**
```yaml
functions:
  payments:
    handler: app.payments.handler
    concurrency: 20
```

**In studio**
1. Open **Functions** and click `payments`.
2. In the *Concurrency & tags* section, set *Reserved concurrency / max instances* to 20.
3. Click **Save**.

To use it only in prod, put it under `stages.prod.functions.payments`."""),

    A(459, provider="azure", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=["docs/events.md#http"],
      user="i put auth key on my azure route. now how the caller send the key?",
      steps=[S("search_docs", query="auth key azure function key",
               docs=[D("docs/events.md", "http", start="**Auth support**", end="| `key` | azure (function key, `AuthLevel.FUNCTION`), huawei (`APP`) |")])],
      final="""On Azure, `auth: key` makes the route need an Azure Functions **function key** (`AuthLevel.FUNCTION`) [docs/events.md#http]. pskit doesn't create or hand out the key for you, and the pskit docs don't describe how callers attach it; that is standard Azure Functions behaviour, so check the Azure Functions documentation on function keys.

What you need on the pskit side:
1. Deploy, then get the route URL with `pskit info`.
2. Read the function key from the Function App in the Azure portal and give it to the caller like a password.
3. Keep the key out of pskit.yml and your code."""),

    A(460, provider="aws", stage="dev", mode="ask", page="Logs", persona="beginner",
      sources=["docs/cli.md#pskit-logs", "docs/dashboard.md#log-sources"],
      user="there are lots of old log streams for my worker lambda. how do i clean them?",
      steps=[S("search_docs", query="delete log streams aws",
               docs=[D("docs/dashboard.md", "log-sources", start="| AWS |", end="| AWS |")]),
             S("search_docs", query="pskit logs streams delete-all",
               docs=[D("docs/cli.md", "pskit-logs", start="| `--streams` |", end="| `-y, --yes` |")])],
      final="""You can delete CloudWatch log streams; the log group itself is kept because Terraform owns it [docs/dashboard.md#log-sources].

**In studio**
1. Open **Logs** with aws / dev in the top bar.
2. Open *Stored logs*, select the streams of `worker` and click *Delete*.
3. Confirm.

**In the terminal**
```bash
pskit logs --streams
pskit logs --function worker --delete-all
```
Add `-y` to skip the question [docs/cli.md#pskit-logs]. Your AWS credentials need `logs:DescribeLogStreams` and `logs:DeleteLogStream`, and boto3 (`pip install "py-serverless-kit[aws]"`). Old streams also expire by themselves after `provider.log_retention_days` (14 by default)."""),

    A(461, provider="gcp", stage="prod", mode="ask", page="Logs", persona="terse_expert",
      sources=["docs/dashboard.md#log-sources"],
      user="can i delete gcp function logs from studio like on aws?",
      steps=[S("search_docs", query="gcp logs delete cloud logging",
               docs=[D("docs/dashboard.md", "log-sources", start="| Provider | Read | Delete | Needs |", end="| GCP |")])],
      final="""No. On GCP pskit reads Cloud Logging entries but can't delete them. Control how long they stay with the retention of the log bucket in your GCP project [docs/dashboard.md#log-sources].

Reading works in **Logs** and with `pskit logs -s prod` once `google-cloud-logging` is installed and application-default credentials are set:
```bash
pip install google-cloud-logging
gcloud auth application-default login
pskit logs -s prod -f
```
Deleting log streams is only available for AWS and on-premises."""),

    A(462, provider="azure", stage="dev", mode="ask", page="Workflows", persona="beginner",
      sources=["docs/workflow-executions.md#embedded-orchestrator-on-a-cloud", "docs/cli.md#pskit-workflow"],
      user="can i see a list of old workflow runs on azure with pskit workflow executions?",
      steps=[S("search_docs", query="workflow executions list embedded cloud history",
               docs=[D("docs/workflow-executions.md", "embedded-orchestrator-on-a-cloud")])],
      final="""No. On Azure the workflow runs by default on the embedded orchestrator function. The run happens inside that one call, so the response carries the result and no history is kept. `pskit workflow executions` explains why there's nothing to list [docs/workflow-executions.md#embedded-orchestrator-on-a-cloud].

What you can do instead:
1. Keep the response of each run: it has `execution_id`, `status`, `output` (or `error` and `cause`) and `duration_ms`.
2. Read the orchestrator's logs:
```bash
pskit logs --function order-pipeline-orchestrator
```
(Azure logs need the Log Analytics workspace output and `pip install azure-monitor-query azure-identity`.)

Execution lists with history are available for AWS Step Functions, Google Cloud Workflows and on-premises."""),

    A(463, provider="aws", stage="prod", mode="ask", page="Workflows", persona="terse_expert",
      sources=["docs/cli.md#pskit-workflow", "docs/workflow-executions.md#aws-step-functions-and-google-cloud-workflows"],
      user="list failed step functions runs of order-pipeline in prod and show history of one",
      steps=[S("search_docs", query="workflow executions status failed history aws",
               docs=[D("docs/cli.md", "pskit-workflow", start="| `executions` |", end="| `status` |")]),
             S("search_docs", query="aws step functions executions permissions",
               docs=[D("docs/workflow-executions.md", "aws-step-functions-and-google-cloud-workflows", end="| History |")])],
      final="""**In the terminal**
```bash
pip install "py-serverless-kit[aws]"
pskit workflow executions order-pipeline -s prod --status FAILED
pskit workflow status <execution_id> -s prod -w order-pipeline --history
```
Lists are newest first, 20 per page by default (`-n`); use `--token` from the output for the next page [docs/cli.md#pskit-workflow]. Your credentials need `states:ListExecutions`, `DescribeExecution` and `GetExecutionHistory` [docs/workflow-executions.md#aws-step-functions-and-google-cloud-workflows]."""),

    A(464, provider="gcp", stage="dev", mode="ask", page="Overview", persona="aws_migrator",
      sources=["docs/migrating-from-aws.md#step-5-move-to-another-cloud"],
      user="Our pskit project runs on AWS today, with a JWT-protected admin route and a DynamoDB table in terraform.extra. We want to try GCP next. What do we have to change?",
      steps=[S("search_docs", query="move from aws to gcp what changes",
               docs=[D("docs/migrating-from-aws.md", "step-5-move-to-another-cloud")])],
      final="""Handlers stay the same; the changes are in YAML [docs/migrating-from-aws.md#step-5-move-to-another-cloud]:
1. Add `options.project` for GCP.
2. Replace `auth: jwt` (AWS only): use `auth: iam`, or validate the token in the handler.
3. Remove the AWS-only `terraform.extra` table and `functions.<fn>.options`, or add a GCP equivalent.
4. Drop `existing: true` for resources that GCP should create.

**In code**
```yaml
providers:
  gcp:
    region: europe-west1
    options: {project: my-gcp-project}
    functions:
      admin:
        events: [{http: {path: /admin, method: GET, auth: iam}}]
```
Lists replace, so `admin` gets only this trigger on GCP. A `terraform.extra` block can be overridden the same way under `providers.aws` / `providers.gcp`.

**In the terminal**
```bash
pskit validate --provider gcp
pskit deploy --provider gcp
```
`validate` lists everything that isn't portable before you deploy. Step Functions become Cloud Workflows on GCP."""),

    A(465, provider="azure", stage="dev", mode="ask", page="Workflows", persona="detailed_spec",
      sources=["docs/workflows.md#embedded-orchestrator", "docs/workflows.md#compiler-notes-and-limits"],
      user="Our approval workflow has a wait state of 30 minutes before reminding the approver. Will that work on Azure?",
      steps=[S("search_docs", query="embedded orchestrator long wait time limit azure",
               docs=[D("docs/workflows.md", "embedded-orchestrator", start="- The **whole run must fit in one function invocation**", end="- The **whole run must fit in one function invocation**")]),
             S("search_docs", query="azure logic apps limits sync timeout",
               docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="- **Azure (Logic Apps):**")])],
      final="""Not with the default engine. On Azure the embedded orchestrator runs the whole workflow inside one function call, which must finish within Azure's 600 s, so a 30-minute wait doesn't fit [docs/workflows.md#embedded-orchestrator].

Use the Logic Apps engine instead:
```yaml
workflows:
  approval:
    engine: native
    options:
      sync: false
    start_at: Ask
    states:
      Ask:    {type: task, function: ask-approver, next: Wait}
      Wait:   {type: wait, seconds: 1800, next: Remind}
      Remind: {type: task, function: remind-approver, end: true}
```
`options.sync: false` matters: a synchronous Logic App response must come within about 2 minutes, so with `false` the caller gets `202` at once. A Logic App run stops after `timeout` (default 1 hour), so raise `timeout` if the whole workflow can take longer [docs/workflows.md#compiler-notes-and-limits].

Check it with `pskit validate`, which warns about embedded runs that can't fit."""),

    A(466, provider="aws", stage="prod", mode="ask", page="Functions", persona="pasted_error",
      sources=["docs/providers.md#aws-aws-lambda", "docs/troubleshooting.md#provider-gotchas"],
      user="{\"message\":\"Service Unavailable\"}\n\nmy export endpoint returns this after exactly 30 seconds, but the function timeout is 120",
      steps=[S("search_docs", query="api gateway 30 s integration timeout",
               docs=[D("docs/providers.md", "aws-aws-lambda", start="**Limits:**")])],
      final="""API Gateway caps the integration at 30 s, whatever the Lambda timeout is [docs/providers.md#aws-aws-lambda]. The function may keep running, but the HTTP caller gets an error after 30 s.

Fix: make the HTTP call short and do the slow part elsewhere:
1. The endpoint puts a job on a queue and returns `202` with a job id.
2. A queue worker (timeout up to 900 s on Lambda) does the export and stores the result.
3. The client polls a status endpoint or gets notified.

**In code**
```yaml
functions:
  export-start:
    handler: app.export.start
    events:
      - http: POST /exports
  export-worker:
    handler: app.export.work
    timeout: 600
    events:
      - queue: exports
```
Return `("", 202)` or `Response.json({"job": job_id}, status=202)` from `export-start`."""),

    A(467, provider="gcp", stage="dev", mode="ask", page="Workflows", persona="informal_non_native",
      sources=["docs/workflows.md#compiler-notes-and-limits"],
      user="gcp workflow call my function that run 45 min. it is ok?",
      steps=[S("search_docs", query="gcp workflows task http timeout",
               docs=[D("docs/workflows.md", "compiler-notes-and-limits", start="- **GCP:**", end="Task HTTP timeouts are capped at 1800 s.")])],
      final="""No. On Google Cloud Workflows each task is an HTTP call to the function, and task HTTP timeouts are capped at 1800 s (30 minutes) [docs/workflows.md#compiler-notes-and-limits].

Split the 45-minute job:
1. Use a `map` state over chunks (for example days or file parts), so each task call stays well under 30 minutes.
2. Or let the task start the work (put it on a queue) and use a `wait` + `choice` loop that checks a status function until it's done.

Test the new flow locally:
```bash
pskit workflow run my-workflow -i '{"day": "2026-11-01"}' --history
```"""),

    A(468, provider="azure", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=["docs/troubleshooting.md#provider-gotchas"],
      user="after deploy to azure my function app and storage account have a strange random ending in the name. did something go wrong?",
      steps=[S("search_docs", query="azure function app storage name hash suffix",
               docs=[D("docs/troubleshooting.md", "provider-gotchas", start="| azure |", end="| azure |")])],
      final="""No, that's on purpose. Function App and storage account names must be globally unique in Azure, so pskit adds a hash suffix to them [docs/troubleshooting.md#provider-gotchas]. The suffix comes from your names, so it stays the same on the next deploy.

Run `pskit info` to see the deployed names and URLs."""),

    A(469, provider="aws", stage="dev", mode="ask", page="Overview", persona="detailed_spec",
      sources=["docs/configuration.md#provider", "docs/providers.md#aws-aws-lambda"],
      user="We want our Lambdas on Graviton (arm64) for cost. One function uses numpy. Does pskit handle the wheels, and where do I switch it?",
      steps=[S("search_docs", query="architecture arm64 wheels",
               docs=[D("docs/configuration.md", "provider", start="| `architecture` |", end="| `architecture` |")]),
             S("search_docs", query="aws dependencies manylinux arm64",
               docs=[D("docs/providers.md", "aws-aws-lambda", start="- **Dependencies:**", end="- **Dependencies:**")])],
      final="""Yes. `architecture: arm64` is used by AWS and for pip wheel selection, and on AWS the dependencies are pip-installed into the zip as manylinux wheels for `x86_64` or `arm64` [docs/configuration.md#provider] [docs/providers.md#aws-aws-lambda]. numpy publishes arm64 manylinux wheels.

**In studio**
1. Open **Overview & provider**.
2. Set *Architecture* to `arm64` and click **Save**.
(Or set it for one function only in **Functions**, under *Architecture*.)

**In code**
```yaml
provider:
  name: aws
  architecture: arm64
```

**In the terminal**
```bash
pskit package
```
This builds the zip with the arm64 wheels, so you see any wheel problem before deploying."""),

    A(470, provider="gcp", stage="dev", mode="auto", page="Code", persona="beginner",
      sources=["docs/providers.md#gcp-google-cloud-functions-2nd-gen", "docs/troubleshooting.md#provider-gotchas"],
      user="i have a main.py in my project root with some helpers. a friend says this breaks on gcp. true?",
      steps=[S("search_docs", query="gcp main.py root generated",
               docs=[D("docs/troubleshooting.md", "provider-gotchas", start="| gcp |", end="| gcp |")])],
      final="""Yes. For GCP, pskit generates the bundle's root `main.py` itself, so don't put your own `main.py` at the source root [docs/troubleshooting.md#provider-gotchas].

Move the helpers into your package, for example `app/helpers.py`, and import them with `from app.helpers import ...`. Then check:
```bash
pskit validate -p gcp
pskit package -p gcp
```"""),
]
