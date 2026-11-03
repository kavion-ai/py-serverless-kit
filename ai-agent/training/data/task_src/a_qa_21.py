"""Category A (docs Q&A and how-to), batch 21: scaling on premises (cluster replicas, reservations, scale command,
master serves, workflow workers, concurrency) and moving AWS Lambda / SAM / serverless.yml projects to on-prem
(event mapping, existing resources, BatchResult, cron, JWT, ASL, logging, side-by-side cut-over). Error texts were
checked with real `pskit validate` runs. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


CL = "docs/cluster.md"
MON = "monitor-scale-and-add-servers-when-it-is-full"
PR = "docs/providers.md"
OP = "onprem-on-premises"
MG = "docs/migrating-from-aws.md"
M1 = "step-1-separate-business-logic-from-aws-event-parsing"
M2 = "step-2-translate-the-sam-serverless-cdk-definition"
TRIG = D(PR, OP, start="| Trigger | Implementation |", end="| workflows | embedded engine")

CONVERSATIONS = [
    A(401, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="terse_expert",
      sources=[f"{CL}#{MON}", f"{CL}#commands"],
      user="cluster prod: 6 web replicas right now for a sale, and keep 6 after the next deploy",
      steps=[S("search_docs", query="scale replicas cluster now and permanent",
               docs=[D(CL, MON, start="**Add capacity on the go.**", end="or `options.cluster.replicas` so the next deploy keeps it."),
                     D(CL, "commands", start="| `pskit cluster scale NAME --replicas N [--stack S]` |", end="| `pskit cluster scale NAME --replicas N [--stack S]` |")])],
      final="""**In the terminal**
```bash
pskit cluster scale prod --replicas 6
```
That lasts until the next deploy [docs/cluster.md#commands].

**In code**
To keep it:
```yaml
provider:
  name: onprem
  options:
    cluster:
      name: prod
      replicas: 6
```
[docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full]"""),

    A(402, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="pasted_error",
      sources=[f"{CL}#{MON}", f"{CL}#set-up"],
      user="pskit cluster status prod\n  workload pskit-shop-prod_web: 4/6 running\n  pending  pskit-shop-prod_web.5: no suitable node (insufficient resources on 2 nodes)\n\nservers are only at 40% cpu! why can't it place them?",
      steps=[S("search_docs", query="replicas cannot be placed reserve cpu memory",
               docs=[D(CL, MON, start="The cluster counts as **full** when any of these holds:", end="* no server is ready."),
                     D(CL, "set-up", start="4. **Point the functions at the cluster**", end="admin_token:")])],
      final="""Placement goes by what each replica **reserves**, not by measured CPU. The orchestrator found no server with the CPU / memory a replica reserves free [docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full]. Each replica reserves `cpu` cores (default 0.25) and `memory` MB (default 256) [docs/cluster.md#set-up].

Options:
1. Lower the reservations if your replicas use less:
```yaml
provider:
  options:
    cluster:
      name: prod
      replicas: 6
      cpu: 0.25
      memory: 256
```
2. Use fewer replicas: `pskit cluster scale prod --replicas 4`.
3. Add a server: `pskit cluster join prod app-3`."""),

    A(403, provider="onprem", stage="prod", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#functions", "docs/cluster.md#how-the-functions-run-in-a-cluster"],
      user="Our Lambda had reserved concurrency 10, so we have concurrency: 10 in pskit.yml. Validate on onprem accepts it. Does the on-prem host limit concurrent runs to 10?",
      steps=[S("search_docs", query="concurrency reserved max instances onprem",
               docs=[D("docs/configuration.md", "functions", start="    concurrency: 10", end="    concurrency: 10"),
                     D(CL, "how-the-functions-run-in-a-cluster", start="* **web** replicas serve your HTTP routes", end="* **web** replicas serve your HTTP routes")])],
      final="""Don't count on it. `concurrency` is "reserved concurrency / max instances **where supported**" [docs/configuration.md#functions], and the on-prem docs don't list it among the host's options. Validate doesn't warn about it either.

On-prem, capacity comes from the cluster: more web replicas, or more servers, add HTTP capacity [docs/cluster.md#how-the-functions-run-in-a-cluster]. If a function must not overload a database, limit that in your code, or feed it from a queue with a small `batch_size`."""),

    A(404, provider="onprem", stage="prod", mode="ask", page="Workflows", persona="detailed_spec",
      sources=[f"{PR}#{OP}"],
      user="We start about 50 workflow runs at once on one on-prem host. Only 8 seem to run and the rest wait. Is that a limit we can raise?",
      steps=[S("search_docs", query="workflow runs at once workers onprem",
               docs=[D(PR, OP, start="- **Dependencies:**", words=60)])],
      final="""Yes. `workflow_workers` is the number of workflow runs executing at once; further starts wait for a worker. The default is 8 [docs/providers.md#onprem-on-premises].

**In code**
```yaml
provider:
  name: onprem
  options:
    workflow_workers: 32
```
Deploy again. Raise it only as far as the server and the services your task functions call can handle. Waiting runs are not lost; they start when a worker is free."""),

    A(405, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="informal_non_native",
      sources=[f"{CL}#commands", f"{CL}#how-the-functions-run-in-a-cluster"],
      user="night time no users. can i scale web replicas to 0 to save, and schedules still run?",
      steps=[S("search_docs", query="scale replicas zero main replica schedules",
               docs=[D(CL, "how-the-functions-run-in-a-cluster", start="* **web** replicas serve your HTTP routes", end="there; queue, storage and topic triggers run there.")])],
      final="""Yes. Schedules, built-in queues, buckets, topics and workflow runs live on the **main** replica on the master, not on the web replicas [docs/cluster.md#how-the-functions-run-in-a-cluster]. With 0 web replicas they keep running; only the web replicas' HTTP capacity goes away.

**In the terminal**
```bash
pskit cluster scale prod --replicas 0
pskit cluster scale prod --replicas 3
```
The next `pskit deploy` sets the number from `options.cluster.replicas` again."""),

    A(406, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=[f"{CL}#the-master-and-requests"],
      user="Our Swarm master also holds the schedules and queues. Under load, HTTP traffic on the master slows those down. Can we keep requests off the master?",
      steps=[S("search_docs", query="master serves requests off swarm",
               docs=[D(CL, "the-master-and-requests", start="| Master serves requests | What happens |", end="(off on Nomad, on on Swarm and k3s).")])],
      final="""Yes: turn *Master serves requests* off. Load balancers then list the master only as a backup, and Swarm keeps web replicas off it while another server can run them [docs/cluster.md#the-master-and-requests].

**In the terminal**
```bash
pskit cluster set prod --no-master-serves
pskit deploy -s prod
```
Load balancers change at once. The web replicas move off the master at the next deploy.

**In studio**
1. **Scaling cluster**: open `prod`, switch off *Master serves requests*.
2. **Deploy > Deploy**.

Users who call the master's own address still reach it, so give them the load balancer's URL."""),

    A(407, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{MG}#{M2}", "docs/events.md#queue"],
      user="The migration guide says use existing: true for our SQS queue while the old stack owns it. We deploy to on-prem though. What does existing: true do there?",
      steps=[S("search_docs", query="existing true on premises queue directory",
               docs=[D(MG, M2, start="Use `existing: true` while existing queues", end="Use `existing: true` while existing queues"),
                     D("docs/events.md", "queue", start="On premises the same options are implemented by a file broker",
                       end="On premises the same options are implemented by a file broker"),
                     D("docs/resources.md", "queue-drivers", start="| `sqs` |", end="| `sqs` |")])],
      final="""Something different. On-prem, a built-in queue is a directory on the host, and `existing: true` means "don't create it, wait until that directory appears" [docs/events.md#queue]. It doesn't connect to your SQS queue. The AWS meaning is for deploys to AWS [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition].

To consume the real SQS queue from on-prem, declare it as a resource with the `sqs` driver. Without keys in the options, the host uses `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` from its environment [docs/resources.md#queue-drivers]:

**In code**
```yaml
resources:
  orders:
    type: queue
    external: true
    name: orders
    options:
      driver: sqs
      queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/orders
functions:
  worker:
    handler: app.orders.work
    events:
      - queue: {resource: orders}
```
For a fresh on-prem queue, just drop `existing: true`."""),

    A(408, provider="onprem", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{MG}#{M1}"],
      user="handler code only: convert this Lambda for our on-prem deploy\n\ndef lambda_handler(event, context):\n    order_id = event['pathParameters']['id']\n    body = json.loads(event.get('body') or '{}')\n    return {'statusCode': 200, 'body': json.dumps({'id': order_id, 'qty': body.get('qty')})}",
      steps=[S("search_docs", query="lambda event pathParameters body pskit handler",
               docs=[D(MG, M1, start="| Lambda | pskit |", end="| `{\"statusCode\", \"headers\", \"body\"}` |")])],
      final="""**In code**
```python
from __future__ import annotations

from py_serverless_kit import Context, Event


def get_order(event: Event, ctx: Context):
    order_id = event.http.path_params["id"]
    body = event.http.json(default={})
    return {"id": order_id, "qty": body.get("qty")}
```
`path_params` replaces `pathParameters`, `event.http.json()` replaces `json.loads(event["body"])`, and a returned dict becomes a 200 JSON response [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing]. The same code runs on AWS too."""),

    A(409, provider="onprem", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=["docs/handlers.md#batchresult"],
      user="Our SQS Lambda returns {'batchItemFailures': [...]} so only failed messages come back. Does that partial retry work on the on-prem host?",
      steps=[S("search_docs", query="batchItemFailures BatchResult onprem retry failed ids",
               docs=[D("docs/handlers.md", "batchresult", start="| Provider | Behaviour |", end="Write idempotent handlers")])],
      final="""Yes, if you return a `BatchResult` instead of the AWS dict. On-prem, the host retries only the failed message ids, and moves a message to `dead_letter` after `max_receive` [docs/handlers.md#batchresult]. On AWS the same object becomes `batchItemFailures`.

**In code**
```python
from __future__ import annotations

from py_serverless_kit import BatchResult


def worker(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            handle(record.json())
        except Exception:
            result.fail(record)
    return result


def handle(order: dict) -> None:
    ...
```
Keep the handler idempotent: redelivery is normal everywhere."""),

    A(410, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{MG}#{M2}", f"{PR}#{OP}"],
      user="In SAM we have an S3 event on bucket uploads, s3:ObjectCreated:*, filter suffix .csv. What is the on-prem version?",
      steps=[S("search_docs", query="S3 event suffix storage trigger on premises",
               docs=[D(MG, M2, start="| `Type: S3`", end="| `Type: S3`"), TRIG])],
      final="""**In code**
```yaml
functions:
  import-csv:
    handler: app.imports.on_upload
    events:
      - storage:
          bucket: uploads
          events: [created]
          suffix: .csv
```
[docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition]

On-prem the bucket is a folder on the host, `<bucket>/<key>`, and `prefix`, `suffix`, `created` and `deleted` all work. The host's first start records the files already there and doesn't emit them [docs/providers.md#onprem-on-premises]. Leave out `existing: true` here: on-prem it would make the host wait for that folder.

**In the terminal**
```bash
pskit invoke -f import-csv -t storage -d '{"key": "in/a.csv"}'
```"""),

    A(411, provider="onprem", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{MG}#{M2}"],
      user="functions.report.events.0: Value error, cron must be a standard 5-field expression: 'min hour dom month dow'\n\ncopied from EventBridge: cron(0 12 * * ? *)",
      steps=[S("search_docs", query="EventBridge cron convert 5-field",
               docs=[D(MG, M2, start="| `Type: Schedule`, `Schedule: rate(5 minutes)` |", end="| `Schedule: cron(0 12 * * ? *)` |")])],
      final="""EventBridge cron has 6 fields (with year, and `?`). pskit wants the standard 5 fields [docs/migrating-from-aws.md#step-2-translate-the-sam-serverless-cdk-definition].

**In code**
```yaml
functions:
  report:
    handler: app.reports.daily
    events:
      - schedule: "0 12 * * *"
```
`rate(5 minutes)` becomes `- schedule: 5 minutes`. On-prem the host's schedule runs any number of minutes, hours or days, even ones cron can't express."""),

    A(412, provider="onprem", stage="dev", mode="ask", page="Functions", persona="pasted_error",
      sources=[f"{PR}#{OP}"],
      user="ERROR: [functions.api] auth `jwt` is not enforced on-premises; use auth: none and check tokens in the handler\n\nworked with our Cognito authorizer on AWS",
      steps=[S("search_docs", query="onprem http auth none check tokens handler",
               docs=[D(PR, OP, start="| http | the host process.", end="| http | the host process.")])],
      final="""The on-prem host has no cloud authorizer, so `auth` must be `none` there [docs/providers.md#onprem-on-premises]. Keep `jwt` for AWS and override the route only for onprem:

**In code**
```yaml
providers:
  onprem:
    functions:
      api:
        events:
          - http: {path: /orders, method: GET, auth: none}
```
Then check the token in the handler:
```python
from __future__ import annotations

from py_serverless_kit import Unauthorized


def list_orders(event, ctx):
    auth_header = event.http.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise Unauthorized("missing token")
    ...
```
Verify the signature with a JWT library against your Cognito issuer. The override replaces the whole `events` list on onprem, so list every route."""),

    A(413, provider="onprem", stage="dev", mode="ask", page="Workflows", persona="aws_migrator",
      sources=[f"{MG}#step-3-translate-step-functions", "docs/workflows.md#migrating-step-functions-asl"],
      user="We're converting a Step Functions ASL to pskit for on-prem. How do we check the converted workflow before deploying, and what ASL features won't come across?",
      steps=[S("search_docs", query="convert ASL check workflow run show not supported",
               docs=[D(MG, "step-3-translate-step-functions", words=60),
                     D("docs/workflows.md", "migrating-step-functions-asl", start="Not supported:")])],
      final="""**In the terminal**
```bash
pskit workflow run order-pipeline -i @events/order.json --history
pskit workflow show order-pipeline --format asl
```
The first runs it on your machine, the second prints ASL to compare with the old file [docs/migrating-from-aws.md#step-3-translate-step-functions].

Not supported: `Parameters` / `ResultSelector` / `OutputPath`, intrinsic functions, `.sync` / callback integrations, and timestamp waits. Do that shaping in a small task function [docs/workflows.md#migrating-step-functions-asl]. Error names in `Retry` / `Catch` become your Python exception class names.

On-prem the workflow runs in the host's embedded engine, so it isn't cut off by a function timeout."""),

    A(414, provider="onprem", stage="dev", mode="ask", page="YAML", persona="aws_migrator",
      sources=[f"{PR}#{OP}", "docs/resource-guides/onprem/README.md#secrets-name_env"],
      user="Our serverless.yml has environment: DB_PASSWORD: ${ssm:/shop/db-password}. Moving to on-prem servers without AWS. Where does that secret go?",
      steps=[S("search_docs", query="onprem secrets env_file not in terraform state",
               docs=[D(PR, OP, start="- **Dependencies:**", words=60)])],
      final="""Into an env file next to the host. `options.env_file` holds `KEY=VALUE` lines that are copied to the host (`host.env`) and loaded at start. Handlers read them, and they are never written to Terraform state [docs/providers.md#onprem-on-premises]. `${ssm:...}` isn't a pskit variable.

**In code**
```yaml
provider:
  name: onprem
  options:
    env_file: .env.onprem
```
`.env.onprem` (keep it out of git):
```text
DB_PASSWORD=...
```
```python
def handler(event, ctx):
    db_pw = ctx.env.get("DB_PASSWORD")
```
For a real secret store, the one-click OpenBao with `get_secret()` also works on-prem."""),

    A(415, provider="onprem", stage="dev", mode="ask", page="none", persona="beginner",
      sources=["docs/migrating-from-aws.md#migrating-from-aws-lambda-and-step-functions"],
      user="is there a full example of moving a lambda project to pskit? i learn better from code",
      steps=[S("search_docs", query="migrate lambda example before after",
               docs=[D(MG, "migrating-from-aws-lambda-and-step-functions", end="holds the pskit version.")])],
      final="""Yes: `examples/13-migrate-from-aws-lambda`. `before/` has a raw Lambda, a SAM template and an ASL file; `after/` has the pskit version [docs/migrating-from-aws.md#migrating-from-aws-lambda-and-step-functions].

**In the terminal**
To try the `after/` version on-prem on your machine:
```bash
cd examples/13-migrate-from-aws-lambda/after
pskit validate -p onprem
pskit dev
```
After the move, changing `provider.name` is enough to go to another target."""),

    A(416, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{MG}#step-4-deploy-to-aws-side-by-side", f"{MG}#step-5-move-to-another-cloud"],
      user="We want to move production from Lambda to our own servers without a big-bang switch. What's the recommended order of steps with pskit?",
      steps=[S("search_docs", query="side by side migration switch traffic",
               docs=[D(MG, "step-4-deploy-to-aws-side-by-side"), D(MG, "step-5-move-to-another-cloud", words=50)])],
      final="""Run both side by side, then switch [docs/migrating-from-aws.md#step-4-deploy-to-aws-side-by-side]:
1. Port the handlers and `pskit.yml`, and deploy them to AWS as a new stage, next to the old stack.
2. Check with `pskit validate --provider onprem` what isn't portable, such as `auth: jwt` or AWS-only options [docs/migrating-from-aws.md#step-5-move-to-another-cloud].
3. Put the on-prem changes in a `providers.onprem:` block or a `pskit.onprem.yml` with `extends: pskit.yml`.
4. Deploy on-prem as its own stage, e.g. `pskit deploy -p onprem -s prod`, and test it.
5. Switch traffic: DNS, or the event sources.
6. Remove the old stack.

On-prem has no API Gateway, so point DNS at the host's port, or at a pskit load balancer."""),

    A(417, provider="onprem", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=["docs/handlers.md#logging", f"{PR}#logs-and-stats"],
      user="in lambda i use print and see it in cloudwatch. on onprem what is best way to log, and where i see?",
      steps=[S("search_docs", query="logging ctx.logger structured onprem logs",
               docs=[D("docs/handlers.md", "logging", end="so a log call can never crash your handler."),
                     D(PR, "logs-and-stats", end="the listen address.")])],
      final="""Use `ctx.logger`. It writes one JSON object per line, with `function` and `request_id` [docs/handlers.md#logging]. `print()` still works on-prem: it's recorded as source `stdout` [docs/providers.md#logs-and-stats].

**In code**
```python
def handler(event, ctx):
    ctx.logger.info("order created", extra={"order_id": 42})
```

**In the terminal**
```bash
pskit logs -f --function create-order
pskit logs --level error -n 500
```

**In studio**
1. **Logs**: the deployed stage's logs, live."""),

    A(418, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=["docs/configuration.md#provider", f"{PR}#{OP}"],
      user="Our SAM function has Timeout: 900 and MemorySize: 3008. Are those valid on-prem, and do they mean the same thing?",
      steps=[S("search_docs", query="timeout memory limits onprem killed",
               docs=[D("docs/configuration.md", "provider", start="| `memory` |", end="| `timeout` |"),
                     D(PR, OP, start="**Limits:**", words=80)])],
      final="""Both validate: `memory` is 64-32768 MB and `timeout` 1-3600 s, within the provider's max [docs/configuration.md#provider].

The meaning differs: the on-prem host doesn't kill a handler at `timeout`. `ctx.remaining_time_ms()` still counts down, so a handler can check it itself [docs/providers.md#onprem-on-premises]. The host runs on the server's own CPU and memory.

**In code**
```yaml
functions:
  export:
    handler: app.export.run
    memory: 3008
    timeout: 900
```
For a hard limit on-prem, stop long work in the handler when `ctx.remaining_time_ms()` gets low."""),

    A(419, provider="onprem", stage="dev", mode="ask", page="Functions", persona="aws_migrator",
      sources=[f"{PR}#{OP}", "docs/events.md#topic"],
      user="SNS subscription with a filter policy on attribute type = order.paid. How does that look on-prem, and is the filter the same?",
      steps=[S("search_docs", query="topic filter attributes on premises",
               docs=[TRIG])],
      final="""On-prem a topic is a fan-out in the host. `filter` is an **exact match** on message attributes, then on JSON body fields [docs/providers.md#onprem-on-premises]. SNS filter policies with prefixes, numeric ranges and the like don't come across.

**In code**
```yaml
functions:
  on-paid:
    handler: app.billing.on_paid
    events:
      - topic:
          name: orders
          filter: {type: order.paid}
```

**In the terminal**
```bash
pskit invoke -f on-paid -t topic -d '{"id": 7}'
```"""),

    A(420, provider="onprem", stage="dev", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{MG}#{M1}", "docs/handlers.md#context"],
      user="code only: our Lambda uses context.aws_request_id and context.get_remaining_time_in_millis() to stop a long loop. pskit equivalents?",
      steps=[S("search_docs", query="aws_request_id remaining time pskit context",
               docs=[D(MG, M1, start="| `context.aws_request_id`", end="| `context.aws_request_id`")])],
      final="""**In code**
```python
from __future__ import annotations


def export(event, ctx):
    done = 0
    for item in event.data or []:
        if ctx.remaining_time_ms() < 10_000:
            ctx.logger.warning("stopping early", extra={"request_id": ctx.request_id, "done": done})
            break
        process(item)
        done += 1
    return {"done": done}


def process(item) -> None:
    ...
```
`ctx.request_id` replaces `aws_request_id`, and `ctx.remaining_time_ms()` replaces `get_remaining_time_in_millis()` [docs/migrating-from-aws.md#step-1-separate-business-logic-from-aws-event-parsing]."""),
]
