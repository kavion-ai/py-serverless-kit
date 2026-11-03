# Scenarios: step by step

Pick what you're building. Each guide has the `pskit.yml` you need, the commands, and how to check the result. They assume `pip install py-serverless-kit`, Terraform or OpenTofu on `PATH`, and cloud credentials for the target ([getting started](getting-started.md)).

| I want to… | Guide |
|---|---|
| expose an HTTP API on AWS | [A](#a-http-api-on-aws) |
| process jobs from a queue pskit creates | [B](#b-queue-worker-with-a-managed-queue) |
| consume a queue or bucket that already exists | [C](#c-attach-an-existing-queue-or-bucket) |
| run on my own server with Redis and MinIO | [D](#d-on-premises-with-redis-and-minio) |
| run on my own server but consume queues / buckets in AWS, Azure, GCP or another cloud | [K](#k-on-premises-watching-queues-and-buckets-in-other-clouds) |
| give functions a database or any other service | [E](#e-attach-a-database-or-custom-service) |
| orchestrate steps and track each run | [F](#f-workflows-start-get-the-execution-id-watch-it) |
| run jobs on a schedule | [G](#g-scheduled-jobs) |
| deploy dev/prod, or the same code to several clouds | [H](#h-stages-and-several-clouds) |
| read logs of an on-premises deployment | [I](#i-on-premises-logs) |
| develop and test before deploying | [J](#j-local-development-and-tests) |

Every guide ends with `pskit dashboard` (static) or `pskit dashboard --serve` (live). See [dashboard.md](dashboard.md).

---

## A. HTTP API on AWS

```yaml
# pskit.yml
service: orders-api
provider: {name: aws, region: eu-west-1}
functions:
  get-order:
    handler: app.api.get_order
    events: [{http: GET /orders/{id}}]
  create-order:
    handler: app.api.create_order
    events: [{http: {method: POST, path: /orders, cors: true}}]
```

```python
# app/api.py
from py_serverless_kit import NotFound, Response

ORDERS = {"1": {"id": "1", "total": 30}}

def get_order(event, ctx):
    order = ORDERS.get(event.http.path_params["id"])
    if order is None:
        raise NotFound("no such order")
    return order

def create_order(event, ctx):
    body = event.http.json()
    return Response.json({"created": body}, 201)
```

```bash
pskit validate
pskit invoke -f get-order --path /orders/1     # local check
pskit deploy
pskit info                                     # prints the endpoint URLs
curl https://<api-id>.execute-api.eu-west-1.amazonaws.com/orders/1
```

**Verify:** `pskit info` lists both routes with URLs. A missing id returns `404 {"error": ...}`.

## B. Queue worker with a managed queue

```yaml
service: jobs
provider: {name: aws, region: eu-west-1}
resources:
  jobs:
    type: queue                       # pskit creates the SQS queue
functions:
  enqueue:
    handler: app.jobs.enqueue
    events: [{http: POST /jobs}]
  worker:
    handler: app.jobs.work
    events:
      - queue: {resource: jobs, batch_size: 10, dead_letter: jobs-dlq, max_receive: 3}
```

```python
# app/jobs.py
import json, boto3
from py_serverless_kit import BatchResult, resource

def enqueue(event, ctx):
    jobs = resource("jobs")                      # jobs.url is the SQS queue URL on AWS
    boto3.client("sqs").send_message(QueueUrl=jobs.url, MessageBody=json.dumps(event.http.json()))
    return {"queued": True}, 202

def work(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            process(record.json())               # your logic
        except Exception:
            result.fail(record)                  # only this message is retried
    return result
```

pskit gives the `enqueue` role `sqs:SendMessage` on that queue automatically ([IAM grants](resources.md#aws-iam)).

```bash
pskit invoke -f worker -t queue -d '[{"id": 1}, {"id": 2}]'
pskit deploy
curl -X POST https://<api>/jobs -d '{"id": 3}'
```

**Verify:** the worker's CloudWatch logs (console link in `pskit info`) show the message. A message that keeps failing lands in `jobs-dlq` after 3 receives.

## C. Attach an existing queue or bucket

pskit doesn't create or delete an `external` resource. It wires the trigger and hands over the details.

```yaml
resources:
  legacy-orders:
    type: queue
    external: true
    connection:
      arn: arn:aws:sqs:eu-west-1:123456789012:legacy-orders   # native name = "legacy-orders"
  archive:
    type: storage
    external: true
    name: acme-archive-prod                                   # existing S3 bucket
functions:
  importer:
    handler: app.importer.run
    events:
      - queue: {resource: legacy-orders, batch_size: 5}
      - storage: {resource: archive, prefix: incoming/, suffix: .csv}
```

Without `connection.arn`, set `name:` and pskit looks the resource up by name (a Terraform data source) to get its ARN and URL. Handlers get `PSKIT_RESOURCE_LEGACY_ORDERS_ARN`, `_URL` and so on, or `resource("legacy-orders")`.

```bash
pskit plan        # shows only the event source mapping / notification, no new queue or bucket
pskit deploy
```

**Verify:** `pskit plan` creates no `aws_sqs_queue` or `aws_s3_bucket`. Sending to the existing queue invokes `importer`. On providers other than AWS, use the queue/bucket `name` the same way. See [events.md](events.md) for each cloud's `existing` caveats.

## D. On premises with Redis and MinIO

Run on your own machine or server and keep queue messages in Redis and objects in MinIO (any S3-compatible store).

```yaml
service: media
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 8080
    admin_token: ${env:PSKIT_ADMIN_TOKEN}
    deploy: {method: ssh, host: 10.0.0.20, user: deploy, pem: ~/.ssh/media.pem, python: bundle}
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis
      url: redis://:${env:REDIS_PASSWORD}@10.0.0.5:6379/0
      key: media-jobs                      # Redis list name (default: the native name)
  uploads:
    type: storage
    external: true
    name: uploads                          # MinIO bucket
    options:
      driver: s3
      endpoint: http://10.0.0.6:9000
      access_key: ${env:MINIO_ACCESS_KEY}
      secret_key: ${env:MINIO_SECRET_KEY}
      prefix: incoming/
functions:
  transcode:
    handler: app.media.transcode
    events: [{queue: {resource: jobs, batch_size: 5, dead_letter: jobs-dlq}}]
  on-upload:
    handler: app.media.on_upload
    events: [{storage: {resource: uploads, events: [created, deleted]}}]
```

`dead_letter: jobs-dlq` is a builtin directory queue on the host unless you declare a Redis resource named `jobs-dlq`.

```bash
export PSKIT_ADMIN_TOKEN=... REDIS_PASSWORD=... MINIO_ACCESS_KEY=... MINIO_SECRET_KEY=...
pskit validate            # checks driver, url, endpoint and the key pair
pskit deploy              # waits until /__pskit/health answers
redis-cli -a "$REDIS_PASSWORD" LPUSH media-jobs '{"file": "a.mp4"}'
mc cp a.mp4 local/uploads/incoming/a.mp4
pskit logs -f             # see both handlers run
```

**Verify:** `pskit logs --source invocation` shows `queue -> ok` and `storage -> ok`. If Redis or MinIO is unreachable, `pskit logs --source host` shows a note and the host keeps running. `${env:...}` values end up in `pskit_host.json` and Terraform state. To keep them out, write `password_env: REDIS_PASSWORD`-style parameters instead (`access_key_env`, `secret_key_env`, ...) and export the variables where the host runs ([secrets](resources.md#on-premises-drivers)).

## E. Attach a database or custom service

pskit never creates databases, caches or other services, but any function can get their details, on every provider:

```yaml
resources:
  orders-db:
    type: database
    external: true
    connection:
      host: ${env:ORDERS_DB_HOST}
      port: 5432
      database: orders
      user: app
      password_env: ORDERS_DB_PASSWORD     # the variable that holds the secret
    functions: [api]
  payments:
    type: custom
    external: true
    connection: {base_url: https://payments.internal/v2, api_key_env: PAYMENTS_KEY}
functions:
  api:
    handler: app.api.handle
    environment:
      ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}   # or inject it from your secret manager
    events: [{http: GET /orders}]
```

```python
from py_serverless_kit import resource

def handle(event, ctx):
    db = resource("orders-db")
    dsn = f"postgresql://{db['user']}:{ctx.env[db['password_env']]}@{db['host']}:{db['port']}/{db['database']}"
    payments = resource("payments")       # also bound: no `functions:` list
    ...
```

```bash
pskit invoke -f api --path /orders     # bindings are injected locally too
pskit deploy
```

**Verify:** the dashboard's **Resources** tab lists both, with connection key names (never values).

## F. Workflows: start, get the execution id, watch it

```yaml
service: shop
provider: {name: aws, region: eu-west-1}      # or: name: onprem
functions:
  validate: {handler: app.orders.validate}
  charge:   {handler: app.orders.charge}
workflows:
  order-pipeline:
    timeout: 600
    start_at: Validate
    states:
      Validate: {type: task, function: validate, next: Charge}
      Charge:   {type: task, function: charge, retry: [{errors: [TimeoutError], max_attempts: 3}], end: true}
```

Test locally first: `pskit workflow run order-pipeline -i '{"amount": 50}' --history`.

**On AWS** it becomes a Step Functions state machine:

```bash
pip install "py-serverless-kit[aws]"         # boto3, for start/list/status
pskit deploy
pskit workflow start order-pipeline -i '{"amount": 50}'
#   execution_id: arn:aws:states:eu-west-1:123:execution:shop-dev-order-pipeline:5f0c...
pskit workflow status <execution-arn> --watch --history
pskit workflow executions order-pipeline --status FAILED
```

**On premises** (`provider: {name: onprem}`) it runs on the embedded engine inside the host:

```bash
pskit deploy
curl -X POST http://127.0.0.1:8080/workflows/order-pipeline -d '{"amount": 50}' -H 'content-type: application/json'
#   202 {"execution_id": "019a15d2...", "status": "RUNNING", "status_url": "/__pskit/executions/019a15d2..."}
pskit workflow status 019a15d2... --watch
pskit workflow cancel 019a15d2...            # stops before the next state
curl -X POST 'http://127.0.0.1:8080/workflows/order-pipeline?wait=true' -d '{"amount": 5}'   # synchronous
```

On GCP it's the same with `pip install "py-serverless-kit[gcp]"`. On other clouds the run is synchronous and the response includes `execution_id` and `output`.

**Verify:** `pskit dashboard --serve` → deployment → **Executions** shows each run with its status and current state. Click one for the timeline, input and output. **Start execution** starts a new run from the browser. Details: [workflow-executions.md](workflow-executions.md).

## G. Scheduled jobs

```yaml
functions:
  nightly-report:
    handler: app.reports.nightly
    events:
      - schedule: {cron: "0 2 * * *", timezone: Europe/Berlin, input: {kind: daily}}
  heartbeat:
    handler: app.reports.heartbeat
    events:
      - schedule: 5 minutes           # shorthand for {rate: 5 minutes}
```

```bash
pskit invoke -f nightly-report      # uses the configured input
pskit deploy
```

**Verify:** `pskit info` shows `cron(0 2 * * *)` and `rate(5 minutes)`. On premises, `pskit logs --function nightly-report` shows each run. Cron dialects per cloud: [events.md](events.md#schedule).

## H. Stages and several clouds

```yaml
service: orders
provider: {name: aws, region: eu-west-1, stage: dev}
functions:
  api: {handler: app.api.handle, events: [{http: GET /orders}]}
stages:
  prod:
    provider: {memory: 1024, environment: {LOG_LEVEL: WARNING}}
providers:
  gcp:
    region: europe-west1
    options: {project: ${env:GOOGLE_CLOUD_PROJECT}}
  onprem:
    options: {port: 8090}
```

```bash
pskit deploy                         # aws / dev
pskit deploy --stage prod            # aws / prod: separate state, separate resources
pskit deploy --provider gcp          # same code on GCP
pskit deploy --provider onprem       # and on this machine
pskit dashboard --serve              # one page with every deployment
```

**Verify:** `.pskit/` holds one directory per `<provider>-<stage>`, which is also the dashboard's deployment key. More: [configuration.md](configuration.md#overrides-and-layering), [`examples/08-multi-cloud`](../examples/08-multi-cloud).

## I. On-premises logs

The host captures handler logging, `print` output, one entry per invocation, and host notes.

```bash
pskit logs                                   # newest 100
pskit logs -f                                # follow
pskit logs --function worker --level error   # errors from one function
pskit logs --source invocation --json        # durations and status codes as JSON lines
curl -H "x-pskit-token: $PSKIT_ADMIN_TOKEN" "http://127.0.0.1:8080/__pskit/logs?since=0&limit=50"
curl -H "x-pskit-token: $PSKIT_ADMIN_TOKEN" http://127.0.0.1:8080/__pskit/stats
```

Or use `pskit dashboard --serve` → **Logs** for a filterable live tail. Logs persist in `<data_dir>/logs/host.jsonl`. Reference: [providers.md](providers.md#logs-and-stats).

## J. Local development and tests

```bash
pskit dev                                    # http://127.0.0.1:3000, hot reload, routes from pskit.yml
pskit invoke -f worker -t queue -d '[{"id": 1}]'
pskit invoke -f on-upload -t storage -d '{"bucket": "uploads", "key": "in/a.csv"}'
pskit workflow run order-pipeline -i @events/order.json --history
pskit validate --provider gcp                # check another target before switching
pskit plan                                   # review the Terraform before deploying
```

```python
# tests/test_handlers.py
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, build_event

def test_worker():
    runner = LocalRunner(Project.load(), env_file=None)
    result = runner.invoke("worker", build_event("queue", [{"id": 1}, {"fail": True}]))
    assert result.failed == ["local-1"]          # synthetic record ids start at local-0
```

`.env` is loaded by `pskit dev` and `pskit invoke`. Resource bindings are injected locally too, so `resource("jobs")` works in tests. More: [local-development.md](local-development.md), [`examples/14-testing`](../examples/14-testing).

## K. On premises, watching queues and buckets in other clouds

The functions run on your server; the messages and files stay where they are. The host polls each external queue and bucket and triggers the function for every message or object change.

Complete projects: [`examples/20-onprem-external-clouds`](../examples/20-onprem-external-clouds) (every built-in cloud driver) and [`examples/19-custom-drivers`](../examples/19-custom-drivers) (your own driver class for RabbitMQ, Kafka or anything else).

```yaml
service: hybrid
provider:
  name: onprem
  options: {host: 0.0.0.0, port: 8080, admin_token: "${env:PSKIT_ADMIN_TOKEN}"}
resources:
  orders:                                   # AWS SQS
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/orders
      access_key_env: AWS_ACCESS_KEY_ID
      secret_key_env: AWS_SECRET_ACCESS_KEY
      wait_seconds: 10
  invoices:                                 # Azure Blob container
    type: storage
    external: true
    options:
      driver: azure_blob
      connection_string_env: AZURE_STORAGE_CONNECTION_STRING
      container: invoices
      prefix: incoming/
  events:                                   # Google Pub/Sub pull subscription
    type: queue
    external: true
    options:
      driver: pubsub
      project: my-project
      subscription: events-onprem
      token_command: [gcloud, auth, print-access-token]
  archive:                                  # Alibaba OSS bucket
    type: storage
    external: true
    name: archive-bucket
    options: {driver: oss, region: cn-hangzhou, access_key_env: OSS_KEY, secret_key_env: OSS_SECRET}
functions:
  process-order:
    handler: app.orders.process
    events: [{queue: {resource: orders, batch_size: 10, max_receive: 5, dead_letter: orders-dlq}}]
  on-invoice:
    handler: app.invoices.on_upload
    events: [{storage: {resource: invoices, events: [created]}}]
  on-event:
    handler: app.events.handle
    events: [{queue: {resource: events}}]
  on-archive:
    handler: app.archive.on_change
    events: [{storage: {resource: archive, events: [created, deleted]}}]
```

1. Export the variables on the machine that runs the host (systemd `Environment=`, Docker `-e`, or the shell for `method: local`). They are read when the host starts and never written to disk by pskit.
2. `pskit validate` checks each driver's required parameters and key pairs.
3. `pskit deploy`, then send a test message from the cloud side: `aws sqs send-message --queue-url ... --message-body '{"id": 1}'`, upload a blob, `gcloud pubsub topics publish ...`.
4. `pskit logs -f --source invocation` shows each handler run; `pskit logs --source host` shows connection or permission problems.

**Verify:** `GET /__pskit/stats` (and the dashboard) reports the SQS backlog under `queues`; Pub/Sub has no backlog API, so `events` is `null`. A message that keeps failing moves to `orders-dlq` (a builtin queue here) after `max_receive` deliveries.

Other providers: `mns` (Alibaba) and `cloudflare_queue` for queues; `cos`, `obs`, `oci`, `ibm_cos`, `spaces`, `r2`, `minio` for storage. For RabbitMQ, Kafka, IBM MQ, OCI Queue and the rest, write a small `custom` driver class. See the [provider matrix](resources.md#provider-matrix) and the [custom driver example](resources.md#custom-drivers).
