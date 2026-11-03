# Build a full application from the terminal (orders service)

Search terms: end to end, tutorial, walkthrough, full example, orders app, CLI, terminal, from scratch, step by step, deploy to AWS, pskit init, real application

This guide builds one realistic application, the **orders service**, from an empty folder to a deployed AWS stack
with a `dev` and a `prod` stage, using only the `pskit` command. The same application is built by clicking in
[end-to-end-studio.md](end-to-end-studio.md) and run on your own servers in
[end-to-end-onprem-cluster.md](end-to-end-onprem-cluster.md). Words you don't know: [concepts.md](concepts.md).

## What the orders service does

The orders service is a small shop backend with every kind of trigger pskit has for the cloud:

| Function | Trigger | What it does |
|---|---|---|
| `create-order` | HTTP `POST /orders` | stores an order in PostgreSQL, sends a message to the `order-jobs` queue |
| `get-order` | HTTP `GET /orders/{id}` | reads an order (Redis cache first, then the database) |
| `list-orders` | HTTP `GET /orders` | lists orders |
| `process-order` | queue `order-jobs` | marks the order paid, publishes to the `order-events` topic |
| `receipt-uploaded` | storage `receipts` bucket | logs PDF receipts uploaded under `incoming/` |
| `nightly-report` | schedule, 02:00 Berlin time | counts orders |
| `notify-email` | topic `order-events` | gets every event (fan-out) |
| `notify-analytics` | topic `order-events`, filter `status: paid` | gets only paid events |
| `reserve-stock`, `charge-payment`, `ship-order` | none (workflow steps) | the `fulfil-order` workflow |

Resources: a managed queue (`order-jobs`), topic (`order-events`) and bucket (`receipts`), plus an external
PostgreSQL database (`orders-db`) and Redis cache (`cache`). Every function logs with `ctx.logger`.

## Install pskit and check the machine

The `pskit` CLI needs Python 3.9 or newer and, to deploy, Terraform 1.5+ (or OpenTofu) on `PATH`.

1. Install the CLI. The `aws` extra adds `boto3`, which `pskit logs` needs on AWS:

   ```bash
   pip install "py-serverless-kit[aws]"
   pskit --version
   ```

2. Check Terraform, the AWS CLI and your credentials. `pskit doctor` prints what is missing and how to install
   it on your operating system; it exits with code 1 when something required is missing:

   ```bash
   pskit doctor -p aws
   ```

3. If credentials are missing, configure them the usual AWS way (`aws configure`, SSO, `AWS_PROFILE` or
   environment keys). pskit uses the standard AWS credential chain.

You need neither Terraform nor credentials for `pskit dev`, `pskit invoke`, `pskit validate` or `pskit package`.
More: [getting-started.md](../getting-started.md), [providers/aws/README.md](../providers/aws/README.md).

## Scaffold the project with pskit init

`pskit init` creates the folder, a `pskit.yml`, handlers, a test and a `.gitignore`. Templates: `http`, `events`,
`workflow`, `full`.

1. Create the project for AWS with the `full` template (HTTP, schedule, queue, storage and a workflow):

   ```bash
   pskit init orders --provider aws --template full
   cd orders
   ```

   ```text
     create pskit.yml
     create app/__init__.py
     create app/handlers.py
     create requirements.txt
     create tests/test_handlers.py
     create .gitignore
   ```

2. Look around: `pskit.yml` has sample functions (`hello`, `get-item`, `create-item`, ...) and
   `app/handlers.py` their code. This guide replaces both with the orders service.
3. Delete the sample handler file; the next sections write the new modules:

   ```bash
   rm app/handlers.py
   ```

Other options: `--name` (service name), `-l python|javascript|typescript`, `--runtime python3.9..python3.14 or
nodejs18..nodejs24`, `--force` to overwrite. Node.js handlers: [nodejs.md](../nodejs.md).

## Write the provider, package and resources blocks

Open `pskit.yml` and replace its content, block by block. The first blocks set the service, its defaults and
the resources the functions use.

```yaml
service: orders

custom:
  receipts_bucket: "orders-receipts-${opt:stage}-change-me"   # S3 bucket names are global: make it unique

provider:
  name: aws
  region: us-east-1
  stage: dev                     # default stage; -s prod picks another
  runtime: python3.12
  memory: 256                    # MB, default for every function
  timeout: 15                    # seconds
  log_retention_days: 14
  environment:                   # every function gets these
    LOG_LEVEL: INFO
    ORDERS_DB_URL: "${env:ORDERS_DB_URL, }"   # read from your shell at deploy time
    CACHE_URL: "${env:CACHE_URL, }"
  tags:
    team: shop

package:
  exclude: ["tests/**"]          # keep tests out of the bundle

resources:
  order-jobs:                    # managed SQS queue
    type: queue
  order-events:                  # managed SNS topic
    type: topic
  receipts:                      # managed S3 bucket with its own name
    type: storage
    name: ${self:custom.receipts_bucket}
  orders-db:                     # existing PostgreSQL: pskit never creates or deletes it
    type: database
    external: true
    connection:
      url_env: ORDERS_DB_URL     # the NAME of the variable that holds the URL, never the URL itself
  cache:                         # existing Redis
    type: cache
    external: true
    connection:
      url_env: CACHE_URL
    functions: [get-order, list-orders]   # only these two are bound to the cache
```

- `database` and `cache` resources are always `external: true`; pskit creates only queues, topics and buckets.
- On AWS the bound functions get `PSKIT_RESOURCE_ORDER_JOBS_URL` (the queue URL) and
  `PSKIT_RESOURCE_ORDER_EVENTS_ARN` (the topic ARN), and the IAM permissions to use them.
- A database in a private network needs the Lambda in that network: add `options: {vpc_config: {...}}` to the
  function (AWS only, see [providers/aws/README.md](../providers/aws/README.md)).

Details: [resources.md](../resources.md), [configuration.md](../configuration.md).

## Write the functions block with every trigger

Add the functions under the resources. Each `events:` entry is one trigger; `resource:` points a queue, storage
or topic trigger at a `resources:` key.

```yaml
functions:
  create-order:
    handler: app.api.create_order
    description: Store a new order and queue it for processing
    events:
      - http: {method: POST, path: /orders, cors: true}

  get-order:
    handler: app.api.get_order
    events:
      - http: GET /orders/{id}               # shorthand: METHOD PATH

  list-orders:
    handler: app.api.list_orders
    events:
      - http: GET /orders

  process-order:
    handler: app.worker.process_order
    timeout: 60
    events:
      - queue: {resource: order-jobs, batch_size: 5, max_receive: 3, dead_letter: order-jobs-dlq}

  receipt-uploaded:
    handler: app.files.receipt_uploaded
    events:
      - storage: {resource: receipts, events: [created], prefix: incoming/, suffix: .pdf}

  nightly-report:
    handler: app.reports.nightly_report
    memory: 512
    timeout: 300
    events:
      - schedule: {cron: "0 2 * * *", timezone: Europe/Berlin, input: {report: daily}}

  notify-email:
    handler: app.notify.email
    events:
      - topic: {resource: order-events}

  notify-analytics:
    handler: app.notify.analytics
    events:
      - topic: {resource: order-events, filter: {status: [paid]}}   # only messages with status=paid

  reserve-stock:
    handler: app.fulfil.reserve_stock
  charge-payment:
    handler: app.fulfil.charge_payment
  ship-order:
    handler: app.fulfil.ship_order
```

Every trigger option (rate schedules, `batch_window`, `fifo`, CORS lists, `auth: iam|jwt|key`, ...) is explained
in [triggers/README.md](../triggers/README.md). Function settings:
[functions/configuration.md](../functions/configuration.md).

## Write the workflows, stages and hooks blocks

The `fulfil-order` workflow reserves stock, routes big orders to a manual review wait, charges the card with
retries and ships. On AWS it becomes a Step Functions state machine (`engine: auto` picks native).

```yaml
workflows:
  fulfil-order:
    description: Reserve stock, charge the card, ship
    timeout: 900
    start_at: Reserve
    states:
      Reserve:
        type: task
        function: reserve-stock
        catch:
          - {errors: [OutOfStock], next: Cancelled, result_path: $.error}
        next: CheckAmount
      CheckAmount:
        type: choice
        choices:
          - {variable: $.total, gt: 1000, next: ManualReview}
        default: Charge
      ManualReview:
        type: wait
        seconds: 60
        next: Charge
      Charge:
        type: task
        function: charge-payment
        result_path: $.payment
        retry:
          - {errors: [PaymentGatewayTimeout], max_attempts: 3, interval_seconds: 2, backoff_rate: 2}
        catch:
          - {errors: [PaymentDeclined], next: Cancelled, result_path: $.error}
        next: Ship
      Ship:
        type: task
        function: ship-order
        end: true
      Cancelled:
        type: fail
        error: OrderCancelled
        cause: Out of stock or payment declined

stages:
  prod:                          # deep-merged over everything above when -s prod is used
    provider:
      memory: 512
      environment:
        LOG_LEVEL: WARNING
    functions:
      process-order:
        concurrency: 10          # reserved concurrency in prod

hooks:
  before_deploy: ["pytest -q"]   # a failing hook stops the deploy
```

`retry` and `catch` match the exception class name your handler raises (`PaymentDeclined`). More:
[deployment/workflows.md](../deployment/workflows.md), [deployment/stages.md](../deployment/stages.md).

## Write the store helper for the database and cache

`app/store.py` keeps the database and cache code out of the handlers. It reads the resources' `url_env` values with
`resources()`; without a database URL (for example under `pskit dev`) it keeps orders in memory.

```python
# app/store.py
import json
import os
from typing import Any, Dict, List, Optional

from py_serverless_kit import resources

_MEMORY: Dict[str, Dict[str, Any]] = {}


def _url(key: str) -> str:
    """The URL in the variable the resource's `url_env` names ("" when unset or not bound)."""
    res = resources().get(key)
    return os.environ.get(res.get("url_env") or "", "") if res else ""


def _db():
    import psycopg  # imported here, so pskit dev works without the driver

    conn = psycopg.connect(_url("orders-db"), autocommit=True)
    conn.execute("CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, body JSONB NOT NULL)")
    return conn


def _cache():
    url = _url("cache")  # bound only to get-order and list-orders
    if not url:
        return None
    import redis

    return redis.Redis.from_url(url)


def save(order: Dict[str, Any]) -> None:
    if not _url("orders-db"):
        _MEMORY[order["id"]] = order
        return
    with _db() as conn:
        conn.execute(
            "INSERT INTO orders (id, body) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET body = EXCLUDED.body",
            (order["id"], json.dumps(order)),
        )


def get(order_id: str) -> Optional[Dict[str, Any]]:
    cache = _cache()
    if cache is not None:
        hit = cache.get(f"order:{order_id}")
        if hit:
            return json.loads(hit)
    if not _url("orders-db"):
        return _MEMORY.get(order_id)
    with _db() as conn:
        row = conn.execute("SELECT body FROM orders WHERE id = %s", (order_id,)).fetchone()
    order = row[0] if row else None
    if order and cache is not None:
        cache.setex(f"order:{order_id}", 60, json.dumps(order))
    return order


def all_orders(limit: int = 50) -> List[Dict[str, Any]]:
    if not _url("orders-db"):
        return list(_MEMORY.values())[:limit]
    with _db() as conn:
        rows = conn.execute("SELECT body FROM orders ORDER BY id LIMIT %s", (limit,)).fetchall()
    return [r[0] for r in rows]
```

## Send to the queue and publish to the topic from a handler

pskit has no cross-cloud "send" call: a handler that sends a queue message or publishes to a topic uses the
platform's SDK, with the native name, URL or ARN that `resource()` returns. `app/messaging.py` keeps that in one
place (AWS and on-premises here; `pskit resources usage order-jobs -p gcp` prints the code for other clouds).

```python
# app/messaging.py
import json
import os
from typing import Any, Dict

from py_serverless_kit import resource


def send_job(message: Dict[str, Any]) -> None:
    queue = resource("order-jobs")
    provider = os.environ.get("PSKIT_PROVIDER", "local")
    if provider == "aws":
        import boto3

        boto3.client("sqs").send_message(QueueUrl=queue.url, MessageBody=json.dumps(message))
    elif provider == "onprem":
        from py_serverless_kit.runtime.onprem_host import submit_queue

        submit_queue(queue.native_name, message)
    else:  # pskit dev / pskit invoke: nothing to send to
        print(f"[local] would send to {queue.native_name}: {message}")


def publish_event(message: Dict[str, Any], status: str) -> None:
    topic = resource("order-events")
    provider = os.environ.get("PSKIT_PROVIDER", "local")
    if provider == "aws":
        import boto3

        boto3.client("sns").publish(
            TopicArn=topic.arn,
            Message=json.dumps(message),
            MessageAttributes={"status": {"DataType": "String", "StringValue": status}},
        )
    elif provider == "onprem":
        from py_serverless_kit.runtime.onprem_host import submit_topic

        submit_topic(topic.native_name, message, {"status": status})
    else:
        print(f"[local] would publish to {topic.native_name} ({status}): {message}")
```

The `status` message attribute is what the `filter: {status: [paid]}` of `notify-analytics` matches.

## Write the HTTP handlers

The three HTTP handlers use the portable `Event` and `Response` API. Raising `UnprocessableEntity` or `NotFound`
returns a JSON error with status 422 or 404.

```python
# app/api.py
import uuid

from py_serverless_kit import Context, Event, NotFound, Response, UnprocessableEntity

from app import messaging, store


def create_order(event: Event, ctx: Context):
    body = event.http.json()                       # invalid JSON -> 400
    items = body.get("items") or []
    if not items:
        raise UnprocessableEntity("an order needs at least one item", details={"field": "items"})
    order = {
        "id": uuid.uuid4().hex[:12],
        "customer": body.get("customer", "anonymous"),
        "items": items,
        "total": sum(float(i.get("price", 0)) * int(i.get("qty", 1)) for i in items),
        "status": "new",
    }
    store.save(order)
    messaging.send_job({"order_id": order["id"]})
    ctx.logger.info("order created", extra={"order_id": order["id"], "total": order["total"]})
    return Response.json(order, status=201)


def get_order(event: Event, ctx: Context):
    order_id = event.http.path_params["id"]
    order = store.get(order_id)
    if order is None:
        raise NotFound(f"order {order_id} does not exist")
    return order                                   # a dict becomes JSON 200


def list_orders(event: Event, ctx: Context):
    limit = int(event.http.query.get("limit", "50"))
    return {"orders": store.all_orders(limit)}
```

Everything the handler API offers: [handlers.md](../handlers.md).

## Write the queue, storage, schedule and topic handlers

Batch handlers loop over `event.records`. Returning a `BatchResult` from the queue consumer retries only the
failed messages (SQS partial batch response on AWS).

```python
# app/worker.py
from py_serverless_kit import BatchResult, Context, Event

from app import messaging, store


def process_order(event: Event, ctx: Context):
    result = BatchResult()
    for record in event.records:
        try:
            job = record.json()
            order = store.get(job["order_id"]) or {"id": job["order_id"]}
            order["status"] = "paid"
            store.save(order)
            messaging.publish_event(order, status="paid")
        except Exception:  # retry only this message
            ctx.logger.exception("order failed", extra={"record": record.id})
            result.fail(record)
    return result
```

```python
# app/files.py
from py_serverless_kit import Context, Event


def receipt_uploaded(event: Event, ctx: Context):
    for record in event.records:                   # record.action is "created" or "deleted"
        ctx.logger.info("receipt stored", extra={"bucket": record.bucket, "key": record.key, "size": record.size})
```

```python
# app/reports.py
from py_serverless_kit import Context, Event

from app import store


def nightly_report(event: Event, ctx: Context):
    report = {"report": (event.data or {}).get("report", "daily"), "orders": len(store.all_orders(limit=10000))}
    ctx.logger.info("nightly report", extra=report)  # event.data is the schedule's `input`
    return report
```

```python
# app/notify.py
from py_serverless_kit import Context, Event


def email(event: Event, ctx: Context):
    for record in event.records:
        ctx.logger.info("send e-mail", extra={"order": record.json()})


def analytics(event: Event, ctx: Context):
    for record in event.records:                   # only status=paid arrives here
        ctx.logger.info("track paid order", extra={"order": record.json()})
```

## Write the workflow step handlers

Workflow steps get the workflow data in `event.data` and return the new data. The exception class name is what
`retry` / `catch` in `pskit.yml` match.

```python
# app/fulfil.py
from py_serverless_kit import Context, Event


class OutOfStock(Exception):
    pass


class PaymentDeclined(Exception):
    pass


def reserve_stock(event: Event, ctx: Context):
    order = dict(event.data or {})
    if any(int(i.get("qty", 1)) > 100 for i in order.get("items", [])):
        raise OutOfStock("not enough stock")
    order["reserved"] = True
    return order


def charge_payment(event: Event, ctx: Context):
    order = dict(event.data or {})
    if order.get("card") == "declined":
        raise PaymentDeclined("the card was declined")
    return {"charged": order.get("total", 0), "currency": "EUR"}   # stored at $.payment


def ship_order(event: Event, ctx: Context):
    order = dict(event.data or {})
    order["status"] = "shipped"
    return order
```

## List the dependencies in requirements.txt

`requirements.txt` lists what the handlers import. pskit installs it into the bundle on `pskit package` and
`pskit deploy` (Linux wheels for Lambda). Never add `py-serverless-kit` itself: its runtime is copied into every
bundle.

```text
boto3
psycopg[binary]
redis
```

Install them locally too, so `pskit dev` and the tests can import them: `pip install -r requirements.txt`.
Per-function requirements (each function in its own folder): [functions/create.md](../functions/create.md).

## Validate the configuration

`pskit validate` checks `pskit.yml` against the schema and against what the selected provider supports. It needs
no credentials.

```bash
pskit validate
pskit validate -s prod
pskit validate -p onprem        # what would change on another provider
```

```text
orders -> AWS Lambda [stable] stage=dev region=us-east-1
  11 function(s), 1 workflow(s)
  workflow fulfil-order: native engine
Configuration is valid.
```

Errors name the exact key (for example `functions.get-order`); fix it and run again. Common errors:
[troubleshooting.md](../troubleshooting.md).

## Run and test the service locally

Local runs need no cloud. `PSKIT_PROVIDER` is `local`, so `app/messaging.py` only prints, and without
`ORDERS_DB_URL` the store keeps orders in memory. Put local values in `.env` (git-ignored, never bundled).

1. Start the local server with hot reload and call it from another terminal:

   ```bash
   pskit dev                      # http://127.0.0.1:3000
   curl -X POST localhost:3000/orders -H "content-type: application/json" \
        -d '{"customer": "ada", "items": [{"sku": "A1", "price": 5, "qty": 2}]}'
   curl localhost:3000/orders
   ```

2. Call one function with a synthetic event, for any trigger type:

   ```bash
   pskit invoke -f create-order -d '{"items": [{"sku": "A1", "price": 5, "qty": 2}]}'
   pskit invoke -f get-order --path /orders/abc          # 404: not found
   pskit invoke -f process-order -d '{"order_id": "abc"}'   # a queue batch of one message
   pskit invoke -f nightly-report
   ```

3. Run the workflow on the embedded engine (`--history` prints every state; `--sleep` honours the wait):

   ```bash
   pskit workflow run fulfil-order -i '{"id": "o1", "total": 20, "items": [{"sku": "A1", "qty": 1}]}' --history
   pskit workflow run fulfil-order -i '{"id": "o2", "total": 20, "card": "declined", "items": []}'
   # FAILED OrderCancelled: Out of stock or payment declined
   ```

4. Write tests with `LocalRunner` and run `pytest` (next section). More:
   [functions/invoke-and-test.md](../functions/invoke-and-test.md).

## Write pytest tests with LocalRunner

`LocalRunner` runs handlers in-process from `pytest`, the same way `pskit invoke` does. The `before_deploy` hook
runs these tests before every deploy.

```python
# tests/test_handlers.py
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, http_event

runner = LocalRunner(Project.load())


def test_create_order():
    resp = runner.invoke("create-order", http_event("POST", "/orders", body={"items": [{"sku": "A1", "price": 5}]}))
    assert resp.status == 201


def test_order_needs_items():
    resp = runner.invoke("create-order", http_event("POST", "/orders", body={"items": []}))
    assert resp.status == 422


def test_workflow_ships_small_orders():
    out = runner.run_workflow("fulfil-order", {"id": "o1", "total": 20, "items": [{"sku": "A1", "qty": 1}]})
    assert out["output"]["status"] == "shipped"
```

```bash
pytest -q
```

## Package and plan before the first deploy

`pskit package` builds `.pskit/aws-dev/artifact.zip` and `.pskit/aws-dev/main.tf.json` without touching AWS.
`pskit plan` runs `terraform plan` to show what would be created.

```bash
pskit package                    # --skip-deps skips pip install
pskit plan
```

```text
Packaging orders for AWS Lambda (dev)
  artifact artifact.zip: 64 files, 154.7 KiB, sha256 4278862bc8b8
  terraform: 58 resource(s) -> .pskit\aws-dev\main.tf.json
```

Change the `receipts_bucket` value in `custom:` to a globally unique name before you deploy.

## Deploy the dev stage to AWS

`pskit deploy` packages, runs the hooks and `terraform apply`, then prints the endpoints and writes the
dashboard.

1. Export the database and cache URLs in the shell (they become Lambda environment variables):

   ```bash
   export ORDERS_DB_URL="postgresql://app:secret@db.example.internal:5432/orders"
   export CACHE_URL="redis://cache.example.internal:6379/0"
   ```

2. Deploy:

   ```bash
   pskit deploy                   # stage dev from provider.stage
   ```

3. See what is deployed: function names, the HTTP endpoint, ids and console links:

   ```bash
   pskit info
   pskit info --refresh --json    # re-read the Terraform outputs, machine readable
   ```

On AWS pskit creates the Lambda functions and their role, one API Gateway HTTP API, the SQS queue (and its
dead-letter queue), the SNS topic and subscriptions, the S3 bucket and its notification, an EventBridge Scheduler
schedule, CloudWatch log groups and the Step Functions state machine. The deploying identity needs permission for
all of them. Details: [deployment/deploy-remove-info.md](../deployment/deploy-remove-info.md).

## Call the deployed endpoints and send real events

Use the endpoint printed by `pskit info` (shown here as `$API`).

1. Call the HTTP API:

   ```bash
   curl -X POST "$API/orders" -H "content-type: application/json" \
        -d '{"customer": "ada", "items": [{"sku": "A1", "price": 5, "qty": 2}]}'
   curl "$API/orders/<id from the answer>"
   ```

2. Send real events through the triggers. `--list` shows, for every function, the payload and the commands:

   ```bash
   pskit trigger --list
   pskit trigger -f process-order -e 0 -d '{"order_id": "<id>"}'    # an SQS message
   pskit trigger -f receipt-uploaded -e 0 -d '{"key": "incoming/r1.pdf", "content": "x"}'
   pskit trigger -f nightly-report --direct                          # run it now, not at 02:00
   ```

3. Or send to a resource; every function bound to it through a trigger runs:

   ```bash
   pskit resources send order-events -d '{"message": {"id": "o1"}, "attributes": {"status": "paid"}}'
   pskit resources check order-jobs                # how many messages wait
   ```

4. Start the workflow and follow its executions:

   ```bash
   pskit workflow start fulfil-order -i '{"id": "o1", "total": 20, "items": [{"sku": "A1", "qty": 1}]}'
   pskit workflow executions fulfil-order --status FAILED
   pskit workflow status <execution-id> --watch
   ```

More: [deployment/workflows.md](../deployment/workflows.md), [workflow-executions.md](../workflow-executions.md).

## Read the logs of the deployed functions

`pskit logs` reads CloudWatch Logs on AWS (it needs `boto3`, installed with the `aws` extra).

```bash
pskit logs -n 50                                 # recent entries of every function
pskit logs -f --function process-order           # follow one function
pskit logs --level ERROR -q "order failed"       # filter by level and text
pskit logs --streams                             # list log streams
pskit logs --delete-all --function nightly-report --yes
```

`pskit dashboard --serve --open` shows the deployment, live logs and workflow executions in the browser. Other
clouds and on premises: [deployment/logs.md](../deployment/logs.md),
[deployment/monitoring-and-dashboard.md](../deployment/monitoring-and-dashboard.md).

## Deploy the prod stage

A stage is an independent copy with its own Terraform state in `.pskit/aws-prod/`. The `stages.prod` block gives
it more memory, a quieter log level and reserved concurrency for `process-order`.

1. Point the variables at the production database and cache, then validate and look at the plan:

   ```bash
   export ORDERS_DB_URL="postgresql://app:***@prod-db.internal:5432/orders"
   export CACHE_URL="redis://prod-cache.internal:6379/0"
   pskit validate -s prod
   pskit plan -s prod
   ```

2. Deploy with a confirmation step (the plan is shown and you approve it):

   ```bash
   pskit deploy -s prod --confirm
   pskit info -s prod
   ```

3. Every command takes `-s`: `pskit logs -s prod -f`, `pskit trigger -s prod --list`,
   `pskit workflow start fulfil-order -s prod -i @order.json`.

Keep `prod` state in a remote backend for teams (`provider.state.backend: s3` under `stages.prod`). See
[deployment/stages.md](../deployment/stages.md).

## Update the service after a change

An update is the same command as the first deploy. Terraform changes only what differs, and the artifact is
byte-reproducible, so unchanged code is not uploaded again.

1. Change code or `pskit.yml` (for example add `- http: DELETE /orders/{id}` to a new function).
2. Check and look at the difference:

   ```bash
   pskit validate && pskit plan
   ```

3. Apply it to `dev`, test, then to `prod`:

   ```bash
   pskit deploy
   pskit deploy -s prod --confirm
   ```

To keep a function in the file but skip it on deploy, set `enabled: false` on it. `pskit deploy --upgrade`
updates the Terraform provider plugins. CI/CD pipelines: [examples/15-ci-cd-deploy](../../examples/15-ci-cd-deploy).

## Switch the orders service to another cloud

The handlers stay the same; the provider block changes. Add overrides under `providers:` and select them with
`-p`:

```yaml
providers:
  gcp:
    region: europe-west1
    options: {project: "${env:GOOGLE_CLOUD_PROJECT}"}
  azure:
    region: westeurope
    options: {subscription_id: "${env:ARM_SUBSCRIPTION_ID}"}
```

```bash
pskit doctor -p gcp
pskit validate -p gcp
pskit deploy -p gcp -s dev
```

- **GCP and Azure** support all five cloud triggers and native workflows. Add a `gcp` / `azure` branch to
  `app/messaging.py` (Pub/Sub, Service Bus); `pskit resources usage order-jobs -p gcp` prints the code.
- **Other clouds** lack some triggers (`pskit providers` shows the matrix). `validate` reports each one; set
  `enabled: false` on that function under `providers.<cloud>.functions.<name>` to skip it there.
- **On premises**: [end-to-end-onprem-cluster.md](end-to-end-onprem-cluster.md).

Every provider's options and credentials: [providers/README.md](../providers/README.md).

## Remove a stage

`pskit remove` destroys every resource of one stage with `terraform destroy`. External resources (`orders-db`,
`cache`) are never touched.

```bash
pskit remove -s dev                     # asks for confirmation
pskit remove -s dev --keep-resources    # keep the bucket, queue and topic (and their data)
pskit resources list -s dev             # what is deployed or kept
pskit resources delete --all-kept -s dev   # delete what --keep-resources kept
pskit remove -s prod --yes              # no question (CI)
```

`pskit plan --destroy` shows what would be removed. A non-empty S3 bucket blocks the destroy on AWS: empty it, or
use `--keep-resources`. More: [deployment/deploy-remove-info.md](../deployment/deploy-remove-info.md).

## See also

- [Learning path](README.md) and [concepts](concepts.md)
- [The same app in studio](end-to-end-studio.md)
- [The same app on your own servers](end-to-end-onprem-cluster.md)
- [CLI reference](../cli.md)
- [Handler API](../handlers.md)
- [Triggers](../triggers/README.md)
- [Deployment](../deployment/README.md)
- [AWS provider](../providers/aws/README.md)
