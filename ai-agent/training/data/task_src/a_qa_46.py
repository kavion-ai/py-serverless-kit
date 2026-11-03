"""Category A (docs Q&A and how-to), batch 46: studio-first how-tos. On premises: a one-click RabbitMQ queue, a
web UI for Redis, two triggers in one event item (real error), cancelling a workflow run, triggering on another
saved server, where the data lives, hiding print() output, `- cron:` (real error). AWS: an HTTP route in the
wizard, Lambda event['body'] habits, method FETCH (real error), Step Functions run status, a 15-minute schedule,
local SQS records. GCP: switching provider in studio, fifo on Pub/Sub (real warning), path parameter names (real
error), what pskit creates in a project. Azure: 600 s limit (real error), an existing queue in another storage
account. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


PR = "docs/providers.md"
OP = "onprem-on-premises"
ST = "docs/studio.md"
CLI = "docs/cli.md"
EV = "docs/events.md"
HD = "docs/handlers.md"
SV = "docs/resource-guides/onprem/services.md"
WE = "docs/workflow-executions.md"
GC = "gcp-google-cloud-functions-2nd-gen"
OPT = D(PR, OP, start="- **Dependencies:**", words=170)

CONVERSATIONS = [
    A(891, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#in-the-studio", f"{CLI}#pskit-resources-onprem"],
      user="team want rabbitmq for the jobs queue, on our server 192.0.2.20. can pskit start it and connect my worker function?",
      steps=[S("search_docs", query="rabbitmq on premises queue service",
               docs=[D(SV, "one-click-services-for-on-premises-functions", start="| RabbitMQ |", end="| RabbitMQ |")]),
             S("search_docs", query="create one-click service studio trigger functions",
               docs=[D(SV, "in-the-studio", end="6. **Deploy**, then test with **Resources → Test** or `pskit resources send <key>`.")])],
      final="""Yes. pskit starts RabbitMQ in Docker there and uses it through its RabbitMQ queue driver (it adds `pika`) [docs/resource-guides/onprem/services.md#one-click-services-for-on-premises-functions].

**In studio**
1. **Resources > + On-prem service**: pick *RabbitMQ*.
2. **Where**: *SSH server*, host `192.0.2.20`, user, port and *Log in with*.
3. Tick `worker` to trigger it.
4. **Create**, then review the added resource, `env_file` and trigger, and **Save**.
5. **Deploy > Deploy**, then test with **Resources > Test** [docs/resource-guides/onprem/services.md#in-the-studio].

**In the terminal**
```bash
pskit resources onprem create jobs --service rabbitmq --ssh ubuntu@192.0.2.20 --attach worker --save
pskit deploy
pskit resources send jobs -d '{"order_id": 1}'
```"""),

    A(892, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SV}#web-uis"],
      user="i have a redis cache from the one-click services. is there a web page where i can look inside it?",
      steps=[S("search_docs", query="redis web ui companion",
               docs=[D(SV, "web-uis", end="| MongoDB | Mongo Express | 8081 | the MongoDB user and password |")]),
             S("search_docs", query="add web ui existing service",
               docs=[D(SV, "web-uis", start="Start it with *Also start the web UI* when creating", words=40)])],
      final="""Yes: Redis Commander, a companion UI on port 8082. Login is `admin` plus a generated password [docs/resource-guides/onprem/services.md#web-uis].

**In studio**
1. **Resources** > *On-prem services*: open your Redis service, **Details**.
2. **Add web UI**. *Details* then shows the URL and login (the real port, if 8082 was taken).

**In the terminal**
```bash
pskit resources onprem gui cache
```
Use your service's key instead of `cache`. If the server's firewall blocks the port, use `pskit resources onprem tunnel cache --remote-port 8082` and browse `http://127.0.0.1:8082`."""),

    A(893, provider="onprem", stage="dev", mode="ask", page="YAML", persona="pasted_error",
      sources=["docs/troubleshooting.md#configuration"],
      user="Error: pskit.yml is invalid:\n  - functions.worker.events.0: Value error, each event must be a single-key mapping such as `- http: {path: /hello}`; got {'http': 'POST /jobs', 'queue': 'jobs'}",
      steps=[S("search_docs", query="each event must be a single-key mapping",
               docs=[D("docs/troubleshooting.md", "configuration", start="**`each event must be a single-key mapping`**", end=": Write `- http: {path: /x}`")])],
      final="""Each trigger is its own list item; you wrote `http` and `queue` in one item [docs/troubleshooting.md#configuration].

**In code**
```yaml
functions:
  worker:
    handler: app.handlers.worker
    events:
      - http: POST /jobs
      - queue: jobs
```
Note the second `-`."""),

    A(894, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{WE}#following-a-run", f"{WE}#cancel-timeouts-and-restarts-embedded-engine"],
      user="A run of our order-pipeline on the on-prem host is stuck in a long wait state. How do I find it and cancel it? Will the task that is running now be killed?",
      steps=[S("search_docs", query="cancel workflow execution",
               docs=[D(WE, "following-a-run", words=50)]),
             S("search_docs", query="cancel stops before next state wait wakes",
               docs=[D(WE, "cancel-timeouts-and-restarts-embedded-engine", end="Cancelling a finished run returns it unchanged.")])],
      final="""**In the terminal**
```bash
pskit workflow executions order-pipeline --status RUNNING
pskit workflow cancel <id>
pskit workflow status <id>
```
No, a running task is not killed: cancel stops the run before its next state, so a task already running finishes first. A `wait` state wakes up at once, and the status becomes `CANCELLED` shortly after [docs/workflow-executions.md#cancel-timeouts-and-restarts-embedded-engine].

The dashboard's *Executions* tab (`pskit dashboard --serve`) does the same with filters and a detail panel [docs/workflow-executions.md#following-a-run]."""),

    A(895, provider="onprem", stage="dev", mode="ask", page="Test", persona="informal_non_native",
      sources=[f"{SV}#deploy-the-functions-to-a-chosen-machine"],
      user="same stage deployed also on edge2 for test. how i call api function there and see its logs, not edge1?",
      steps=[S("search_docs", query="trigger logs other server",
               docs=[D(SV, "deploy-the-functions-to-a-chosen-machine", start="Logs, triggers and executions follow the same choice", end="Logs, triggers and executions follow the same choice")])],
      final="""Pick the server explicitly; without it they read the host of the last deploy [docs/resource-guides/onprem/services.md#deploy-the-functions-to-a-chosen-machine].

**In the terminal**
```bash
pskit trigger --server edge2 -f api
pskit logs --server edge2
```

**In studio**
1. **Logs** > **Server**: `edge2`.
2. **Test**: choose `edge2` as the server, then **☁ Send to On-premises / dev**.

The host's port (default 8080) must be reachable from your machine."""),

    A(896, provider="onprem", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{PR}#{OP}"],
      user="where does the onprem host keep my queue messages and files? i want to know before we do backups",
      steps=[S("search_docs", query="onprem data directory location",
               docs=[OPT]),
             S("search_docs", query="remove does not delete data_dir",
               docs=[D(PR, OP, start="`pskit deploy` writes the bundle under", end="`pskit deploy` writes the bundle under")])],
      final="""In the host's data directory: by default `.pskit/onprem-data/<service>-<stage>` for a local host, and `<path>/data` on an SSH server. `pskit remove` does not delete it [docs/providers.md#onprem-on-premises].

**In studio**
**Overview & provider** > *On-premises options* > **Data directory** shows it; set it to move the data elsewhere.

**In code**
```yaml
provider:
  name: onprem
  options:
    data_dir: /var/lib/pskit/orders
```
Back up that folder. Queues, buckets or topics that use a driver (Redis, S3, ...) keep their data in that service instead."""),

    A(897, provider="onprem", stage="prod", mode="ask", page="Logs", persona="terse_expert",
      sources=[f"{PR}#{OP}", f"{PR}#logs-and-stats"],
      user="third-party lib prints tons of junk to stdout, flooding pskit logs. keep only logging records",
      steps=[S("search_docs", query="onprem host capture print stdout logs",
               docs=[D(PR, "logs-and-stats", end="- one `invocation` entry per handler call")]),
             S("search_docs", query="capture_output option",
               docs=[OPT])],
      final="""Turn off `capture_output`; it is what records `print()` / stdout / stderr lines [docs/providers.md#onprem-on-premises].

**In studio**
**Overview & provider** > *Host tuning* > **Capture output**: off. **Save**, **Deploy > Deploy**.

**In code**
```yaml
provider:
  name: onprem
  options:
    capture_output: false
```
Or keep it on and filter the view: `pskit logs --source function`."""),

    A(898, provider="onprem", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#schedule"],
      user="Error: pskit.yml is invalid:\n  - functions.nightly.events.0: Value error, unknown event type 'cron'; expected one of http, schedule, queue, storage, topic, smtp",
      steps=[S("search_docs", query="cron schedule event syntax",
               docs=[D(EV, "schedule", words=90)])],
      final="""There is no `cron` trigger; a cron expression goes under `schedule` [docs/events.md#schedule].

**In code**
```yaml
functions:
  nightly:
    handler: app.handlers.nightly
    events:
      - schedule: "0 2 * * *"
```
or the long form `- schedule: {cron: "0 2 * * *"}`.

**In studio**
**Functions** > `nightly` > **Triggers** step > *Add a trigger* > **Schedule**, **Run** = *Cron expression*."""),

    A(899, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{ST}#what-you-can-do"],
      user="studio only: my create-order function needs an http POST /orders url. which buttons?",
      steps=[S("search_docs", query="studio add http trigger function",
               docs=[D(ST, "what-you-can-do", start="| **Functions** |", end="| **Functions** |")])],
      final="""**In studio**
1. **Functions**: click the `create-order` row.
2. Go to the **Triggers** step, and under *Add a trigger* click **HTTP endpoint**.
3. Choose `POST` and type `/orders` in **Route**. Leave **Auth** on `none` for a public endpoint.
4. **Apply changes**, then **Save**.
5. **Deploy > Deploy**; **Deploy > Info** shows the URL."""),

    A(900, provider="aws", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{HD}#httprequest", "docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing"],
      user="My Lambda code does json.loads(event['body']) and event['pathParameters']['id']. What do I write in a pskit handler instead?",
      steps=[S("search_docs", query="lambda event body path parameters pskit",
               docs=[D("docs/migrating-from-aws.md", "step-1-separate-business-logic-from-aws-event-parsing", words=120)]),
             S("search_docs", query="HttpRequest json path_params",
               docs=[D(HD, "httprequest")])],
      final="""Use `event.http` instead of the raw API Gateway dict [docs/handlers.md#httprequest]:

**In code**
```python
from __future__ import annotations


def update_order(event, ctx):
    order_id = event.http.path_params["id"]
    body = event.http.json(default={})
    return {"id": order_id, "status": body.get("status")}
```
- `event.http.json()` parses the body; invalid or empty JSON gives HTTP 400 unless you pass `default`.
- Query strings are `event.http.query`, headers `event.http.headers` (case-insensitive).
- Returning a dict gives 200 JSON, so no `statusCode` / `json.dumps` is needed."""),

    A(901, provider="aws", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#http"],
      user="Error: pskit.yml is invalid:\n  - functions.api.events.0.method: Value error, method must be one of GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, ANY\n\ni used FETCH like the frontend",
      steps=[S("search_docs", query="http method allowed values",
               docs=[D(EV, "http", end="**Path templates**")])],
      final="""`FETCH` isn't an HTTP method; the browser's `fetch()` sends a normal method such as `GET` or `POST` [docs/events.md#http].

**In code**
```yaml
functions:
  api:
    handler: app.handlers.api
    events:
      - http: {path: /orders, method: GET}
```
Use `POST` if the frontend sends a body, or `ANY` to accept every method."""),

    A(902, provider="aws", stage="prod", mode="ask", page="Workflows", persona="informal_non_native",
      sources=[f"{WE}#following-a-run", f"{WE}#aws-step-functions-and-google-cloud-workflows"],
      user="customer say order not finish. how i see the step functions runs of order-pipeline and which step failed?",
      steps=[S("search_docs", query="list workflow executions failed history",
               docs=[D(WE, "following-a-run", words=50)]),
             S("search_docs", query="step functions executions credentials history",
               docs=[D(WE, "aws-step-functions-and-google-cloud-workflows", end="pip install \"py-serverless-kit[gcp]\"")])],
      final="""**In the terminal**
```bash
pip install "py-serverless-kit[aws]"
pskit workflow executions order-pipeline --status FAILED -s prod
pskit workflow status <execution arn> --history -s prod
```
`--history` prints every history event, so you see the state that failed [docs/workflow-executions.md#following-a-run]. It uses your machine's AWS credentials [docs/workflow-executions.md#aws-step-functions-and-google-cloud-workflows].

The dashboard's *Executions* tab (`pskit dashboard --serve`) shows the same with filters and a detail panel."""),

    A(903, provider="aws", stage="dev", mode="ask", page="Functions", persona="beginner",
      sources=[f"{EV}#schedule"],
      user="how can my sync-prices function run every 15 minutes?",
      steps=[S("search_docs", query="schedule every minutes rate",
               docs=[D(EV, "schedule", words=90)])],
      final="""**In studio**
1. **Functions**: click `sync-prices`, **Triggers** step.
2. *Add a trigger* > **Schedule**; **Run** = *Every…*, **Interval** = `15` `minute`.
3. **Apply changes**, **Save**, **Deploy > Deploy**.

**In code**
```yaml
functions:
  sync-prices:
    handler: app.handlers.sync_prices
    events:
      - schedule: 15 minutes
```

**In the terminal**
Test it locally first:
```bash
pskit invoke -f sync-prices
```"""),

    A(904, provider="aws", stage="dev", mode="ask", page="none", persona="terse_expert",
      sources=[f"{CLI}#pskit-invoke"],
      user="cli: run worker locally with two sqs messages",
      steps=[S("search_docs", query="invoke queue type records data",
               docs=[D(CLI, "pskit-invoke")])],
      final="""**In the terminal**
```bash
pskit invoke -f worker -t queue -d '[{"id": 1}, {"id": 2}]'
```
A list for `-t queue` becomes one record per element; use `-d @messages.json` for a file [docs/cli.md#pskit-invoke]."""),

    A(905, provider="gcp", stage="dev", mode="ask", page="Overview", persona="beginner",
      sources=[f"{ST}#what-you-can-do"],
      user="project was made for aws. now i want try gcp. how switch in studio?",
      steps=[S("search_docs", query="studio switch provider",
               docs=[D(ST, "what-you-can-do", start="| **Overview & provider** |", end="| **Overview & provider** |")]),
             S("search_docs", query="gcp project option required",
               docs=[D(PR, GC, end="| Trigger | Implementation |", words=150)])],
      final="""**In studio**
1. **Overview & provider**: click the GCP card. Studio first lists the triggers that would stop working [docs/studio.md#what-you-can-do].
2. Set **Region** (e.g. `europe-west1`) and, in *Google Cloud Functions options*, **Project** (required on GCP).
3. **Save**. Fix anything left in **Problems**.
4. **Setup & credentials**: sign in with **Sign in (gcloud ADC)**, then **Deploy > Deploy**.

Your handler code stays the same. To try GCP once without changing `pskit.yml`, pick GCP in the top bar's provider select instead."""),

    A(906, provider="gcp", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{EV}#queue", f"{PR}#{GC}"],
      user="ingest -> Google Cloud Functions [stable] stage=dev region=europe-west1\n  1 function(s), 0 workflow(s)\n  WARNING: [functions.worker] queue.fifo is not supported by Pub/Sub triggers and is ignored\nConfiguration is valid.\n\norder of messages matter for us",
      steps=[S("search_docs", query="fifo gcp pubsub ignored",
               docs=[D(EV, "queue", start="| Option | aws (SQS) |", end="| `fifo` |")])],
      final="""On GCP a queue is a Pub/Sub topic, and `fifo` is ignored there [docs/events.md#queue], so messages can arrive in any order.

Options:
1. Make the handler order-safe: put a sequence number or timestamp in each message and ignore older updates.
2. Keep this function on AWS, where `fifo` is honoured (`.fifo` queue, content-based dedup).

Remove `fifo: true` from the GCP config so the warning doesn't hide real ones."""),

    A(907, provider="gcp", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=[f"{EV}#http"],
      user="Error: pskit.yml is invalid:\n  - functions.api.events.0.path: Value error, invalid path template '/users/{user-id}'; use /users/{id} or /files/{path+}\n\nwhy dash not ok",
      steps=[S("search_docs", query="path parameter names identifiers",
               docs=[D(EV, "http", start="**Path templates**", end="- Parameter names are identifiers")])],
      final="""Parameter names must be identifiers, like Python names: `{user_id}` is fine, `{user-id}` is not [docs/events.md#http].

**In code**
```yaml
functions:
  api:
    handler: app.handlers.api
    events:
      - http: GET /users/{user_id}
```
In the handler read it as `event.http.path_params["user_id"]`. The URL itself can still contain dashes, e.g. `/users/ab-12`."""),

    A(908, provider="gcp", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{PR}#{GC}"],
      user="Our cloud team asks what resources pskit will create in the GCP project before we deploy. Is there a list, and can we see the exact plan?",
      steps=[S("search_docs", query="gcp resources created terraform",
               docs=[D(PR, GC, start="**Resources:**", end="**Resources:**")]),
             S("search_docs", query="plan without deploying",
               docs=[D(CLI, "pskit-plan")])],
      final="""Yes. pskit uses these Terraform resources on GCP: `google_storage_bucket` (+ object) for the sources, `google_cloudfunctions2_function`, `google_cloud_run_service_iam_member`, `google_service_account`, `google_project_iam_member`, `google_cloud_scheduler_job`, `google_pubsub_topic` and `google_workflows_workflow`, depending on your triggers [docs/providers.md#gcp-google-cloud-functions-2nd-gen].

For the exact list of your project:

**In the terminal**
```bash
pskit plan -s prod
```
It packages and runs `terraform plan`, without changing anything [docs/cli.md#pskit-plan].

**In studio**
**Deploy > Plan**, with `prod` in the top bar."""),

    A(909, provider="azure", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{PR}#providers"],
      user="shop -> Azure Functions [stable] stage=dev region=westeurope\n  1 function(s), 0 workflow(s)\n  ERROR: [functions.export] timeout 900s exceeds Azure Functions max 600s",
      steps=[S("search_docs", query="azure max timeout",
               docs=[D(PR, "providers", start="| Provider | Tier |", end="| [`azure`]")])],
      final="""Azure Functions allows at most 600 s per call [docs/providers.md#providers].

**In studio**
**Functions**: click `export`, set **Timeout (s)** to `600` in **Basics** (its help shows the max), **Apply changes**.

**In code**
```yaml
functions:
  export:
    handler: app.handlers.export
    timeout: 600
```
If the export needs longer, split it: the HTTP call puts a job on a queue and a queue worker does the work in parts."""),

    A(910, provider="azure", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=["docs/resource-guides/azure/queue.md#3-declare-it-in-pskityml"],
      user="queue already exist in other storage account (made in portal). worker never run with it. what i miss?",
      steps=[S("search_docs", query="azure existing queue other storage account trigger",
               docs=[D("docs/resource-guides/azure/queue.md", "3-declare-it-in-pskityml", start="- `storage_connection` is required", end="- `environment` puts the connection string")])],
      final="""You need `options.storage_connection`. Without it the trigger looks for the queue in pskit's own storage account and never fires [docs/resource-guides/azure/queue.md#3-declare-it-in-pskityml].

**In code**
```yaml
provider:
  name: azure
  options:
    storage_connection: ORDERS_QUEUE_CONN
  environment:
    ORDERS_QUEUE_CONN: ${env:ORDERS_QUEUE_CONN}
resources:
  jobs:
    type: queue
    external: true
    name: orders-jobs
functions:
  worker:
    handler: app.handlers.work
    events:
      - queue: {resource: jobs}
```
Export `ORDERS_QUEUE_CONN` (the account's connection string) in the shell that runs `pskit deploy`. It applies to every external queue and container of the service, so keep them in one account.

**In studio**
**Overview & provider** > *Azure Functions options* > **Storage connection setting**: `ORDERS_QUEUE_CONN`."""),
]
