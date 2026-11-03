# Resources (storage, queues, topics, databases, any service)

`resources:` names the services your functions use: buckets, queues, topics, databases, caches, or anything else. pskit either **creates** them (managed) or **attaches** ones that already exist (external), then hands each function its connection details in environment variables. Handlers read them with `resource("name")`, so the code does not change between clouds.

```yaml
resources:
  uploads:                    # managed bucket: pskit creates it
    type: storage
    name: acme-uploads-1234
  jobs:                       # managed queue, consumed below
    type: queue
  billing-events:             # an existing SNS topic in another stack
    type: topic
    external: true
    connection:
      arn: arn:aws:sns:us-east-1:123456789012:billing-events
  orders-db:                  # a database pskit never touches
    type: database
    external: true
    connection:
      host: ${env:ORDERS_DB_HOST, localhost}
      port: 5432
      database: orders
      password_env: ORDERS_DB_PASSWORD   # the NAME of a secret variable, not the secret
    functions: [api, worker]

functions:
  api:
    handler: app.handlers.api
    events: [{http: POST /orders}]
  worker:
    handler: app.handlers.work
    events:
      - queue: {resource: jobs, batch_size: 5}
```

```python
from py_serverless_kit import resource

def api(event, ctx):
    uploads = resource("uploads")
    db = resource("orders-db")
    password = ctx.env[db["password_env"]]
    return {"bucket": uploads.native_name, "db": f'{db["host"]}:{db["port"]}'}
```

Full example: [`examples/18-resources`](../examples/18-resources).

Calling it from code (which library, Python and Node.js examples, how to test): [resource-usage.md](resource-usage.md), or **Resources → How to use** in the studio / `pskit resources usage <key>` for your own resources.

Step-by-step console guides (where to find each value, per cloud and type): [resource-guides](resource-guides/README.md), for example [an existing Azure Storage queue](resource-guides/azure/queue.md).

## Fields

| Key | Default | Notes |
|---|---|---|
| `type` | — | required: `storage`, `queue`, `topic`, `database`, `cache` or `custom` |
| `external` | `false` | `true`: the service already exists or runs outside pskit. pskit never creates, changes or destroys it |
| `name` | resource key | native name of the bucket / queue / topic. Without `name`, the last `:` segment of `connection.arn` is used, then the key. Managed names are prefixed by the provider exactly like event names |
| `connection` | `{}` | values handed to handlers. Keys start with a letter and use letters, digits or `_`. Values must be scalars (strings, numbers, booleans; booleans become `true`/`false`). `type`, `name` and `external` are reserved. Keys must be unique ignoring case |
| `functions` | all user functions | functions that receive the binding. Without it, every function you wrote gets it, but generated `<workflow>-orchestrator` functions don't. List an orchestrator explicitly if it needs one |
| `options` | `{}` | provider-specific, for example the on-premises `driver` or AWS queue settings (below) |

Resource keys follow function-name rules and must stay distinct after `my-key` → `MY_KEY` conversion.

`database`, `cache` and `custom` must be `external: true`. pskit only passes their connection details along.

## Using a resource from an event

`queue`, `storage` and `topic` events accept `resource:` instead of `name` / `bucket`:

```yaml
events:
  - queue:   {resource: jobs, batch_size: 10, dead_letter: jobs-dlq}
  - storage: {resource: uploads, prefix: in/, events: [created]}
  - topic:   {resource: billing-events, filter: {kind: [paid]}}
```

The event then behaves exactly like `name: <native name>` plus `existing: <external>`, so every provider supports it. Validation fails if the resource doesn't exist, has a different `type`, or the event also sets a different `name`/`bucket`.

## What handlers receive

For each resource bound to a function:

```
PSKIT_RESOURCES=uploads,jobs
PSKIT_RESOURCE_UPLOADS_TYPE=storage
PSKIT_RESOURCE_UPLOADS_NAME=acme-uploads-1234     # resolved native name
PSKIT_RESOURCE_UPLOADS_EXTERNAL=false
PSKIT_RESOURCE_UPLOADS_<KEY>=...                  # one per connection entry
PSKIT_RESOURCE_UPLOADS_ARN / _URL / _ID=...       # when the provider knows them
```

`<KEY>` is the key with every non-alphanumeric character replaced by `_`, in upper case (`orders-db` → `ORDERS_DB`). A `connection` entry wins over a provider value with the same name.

| Provider | Values added |
|---|---|
| aws | `ARN` for storage, queue and topic. Queues also get `URL`. External resources bound by name are looked up with a Terraform data source. With `connection.arn`, that ARN is used as-is |
| gcp | `ID` for managed queues and topics (the Pub/Sub topic id) |
| others | only `TYPE`, `NAME`, `EXTERNAL` and your `connection` values |

`pskit invoke` and `pskit dev` inject the same variables locally.

### Runtime API

```python
from py_serverless_kit import resource, resources, Resource

jobs = resource("jobs")          # KeyError listing the bound names if it isn't bound here
jobs.name                        # "jobs" (the key)
jobs.type                        # "queue"
jobs.native_name                 # e.g. "orders-dev-jobs"
jobs.external                    # False
jobs.connection                  # {"region": "...", ...}: keys in lower case
jobs.get("region", "us-east-1")  # case-insensitive, with a default
jobs["region"]                   # KeyError when missing
jobs.arn, jobs.url, jobs.id      # shortcuts for get("arn") / get("url") / get("id")

resources()                      # {"jobs": Resource(...), ...} for the current function
```

pskit does not ship a portable "send to queue" helper for the clouds: use the cloud SDK (`boto3`, `google-cloud-pubsub`, `azure-storage-queue`, ...) with the binding values. On premises, `py_serverless_kit.runtime.onprem_host.submit_queue/submit_topic/put_object/delete_object` publish through the host and honour the drivers below.

## Provider support

| | Managed, used by an event | Managed, no event (standalone) | External | database / cache / custom |
|---|---|---|---|---|
| aws | yes | yes (S3 bucket, SQS queue, SNS topic) | yes | yes (env only) |
| gcp | yes | yes (bucket; Pub/Sub topic for queue and topic) | yes | yes |
| azure | yes | yes (storage container, storage queue, Service Bus topic) | yes | yes |
| onprem | yes | yes (builtin directories, created when the host starts) | yes, with [drivers](#on-premises-drivers) | yes |
| alibaba, tencent, huawei, oracle, ibm, digitalocean, cloudflare | yes, where the event type is supported | validation error: create it outside pskit and set `external: true` | yes | yes |

On AWS, standalone managed queues take their settings from the first event that uses the resource, otherwise from `options`: `fifo`, `visibility_timeout`, `dead_letter`, `max_receive`.

On Azure, app settings belong to the whole Function App, so every function there sees every binding.

### AWS IAM

Each role pskit creates gets a `pskit-resources` policy for the storage, queue and topic resources bound to its functions:

| Type | Actions |
|---|---|
| storage | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket` (bucket and `/*`) |
| queue | `sqs:SendMessage`, `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`, `GetQueueAttributes`, `GetQueueUrl` |
| topic | `sns:Publish` |

If you bring your own role (`iam.role`), pskit can't change it. The plan prints a warning, and granting access is up to you. Narrow the grant by listing `functions:` on the resource.

## On-premises drivers

The host normally keeps queues, buckets and topics in directories (`builtin`). A resource can point at a queue or bucket that lives in another provider or in a service you already run. The host then **watches** it: queues are polled and leased, buckets are listed and diffed every `poll_seconds`, and each message or object change triggers the function like any local event.

Set `options.driver` (a string, or a mapping with `use` plus parameters). `connection.driver` works too. Parameters are read from the driver mapping, then `options`, then `connection`.

The driver applies wherever the resource's native name is used: triggers, `submit_queue` / `put_object` from handlers,
`pskit resources send`, and `dead_letter` (which may name a resource key). A queue that is only published to still goes
through its driver.

To have pskit start the service for you (Redis, Valkey, Kafka, NATS, RabbitMQ, MinIO, databases, ...) on this machine
or an SSH server, see [one-click services](resource-guides/onprem/services.md).

A resource of `type: smtp` (on premises) is the SMTP server one-click service: a Node.js container that receives
mail for your domains and posts it to the host. Functions use it with the `smtp` trigger: see
[E-mail triggers](smtp/README.md).

**Secrets.** Any parameter can be given as `<name>_env: VARIABLE` instead of `<name>: value`. The host reads `VARIABLE` from its own environment when it starts, so the secret never lands in Terraform state or `pskit_host.json`. A variable that isn't set stops the host with an error naming it. `provider.options.env_file: .env.onprem` ships a `KEY=VALUE` file with the host (as `host.env`) and loads it at start, for local, SSH and Docker deploys alike; only its digest is recorded. `${env:...}`, by contrast, is resolved on the machine running `pskit deploy` and *is* written into the files.

**Emulators and private endpoints.** Every HTTP driver accepts `endpoint: http(s)://...` (LocalStack, Azurite, the Pub/Sub emulator, fake-gcs-server, a VPC endpoint).

### Provider matrix

| Provider | Storage driver | Queue driver |
|---|---|---|
| AWS | `s3` (or `aws`) | `sqs` |
| Azure | `azure_blob` | `azure_queue` |
| Google Cloud | `gcs` | `pubsub` (pull subscription) |
| Alibaba Cloud | `oss` | `mns` |
| Tencent Cloud | `cos` | `custom` (TDMQ) |
| Huawei Cloud | `obs` | `custom` (DMS for RabbitMQ / Kafka) |
| Oracle Cloud | `oci` | `custom` (OCI Queue signs requests with RSA keys, which the standard library can't do) |
| IBM Cloud | `ibm_cos` | `custom` (IBM MQ, Event Streams / Kafka) |
| DigitalOcean | `spaces` | no queue service: `redis` (Managed Redis / Valkey) or `custom` |
| Cloudflare | `r2` | `cloudflare_queue` |
| Self-hosted | `minio`, `s3` with `endpoint`, `directory` | `redis`, `redis_stream`, `directory`, `custom` (RabbitMQ, Kafka, NATS, ...) |
| Another pskit on-prem host | | `pskit_host` (its built-in queues) |

Topics only support `builtin` and `directory`.

### Queue drivers

| Driver | Parameters (`*` = required) |
|---|---|
| `redis` | `url`* (`redis://[user:pass@]host:6379/0`, `rediss://`), `key` (default: native name) |
| `redis_stream` | `url`*, `key` (the stream, default native name), `group` (consumer group, default `pskit`), `consumer` (default host name + pid), `maxlen` (approximate trim). Redis 6.2+ or Valkey |
| `pskit_host` | `endpoint`* (the other host's URL), `queue` (default: native name), `token` (its `admin_token`; use `token_env`) |
| (all HTTP drivers) | `create_queue` (`azure_queue`, `sqs`) / `create_bucket` (`s3` family, `azure_blob`, `gcs`): create the queue or bucket on first use and again if it disappears (emulators). One-click services set it |
| `sqs` | `create_queue` (create the queue when the service reports it missing; default `true` when `endpoint` is not an `amazonaws.com` host, e.g. ElasticMQ). `queue_url`*, or `account_id`* + `region`* (+ `name`, default native name). `access_key` + `secret_key` (+ `session_token`); without them `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` on the host. `region` (default: from the URL), `wait_seconds` (long poll, 0-20, default 0), `message_group_id` (`.fifo` queues, default `pskit`), `endpoint` |
| `azure_queue` | `connection_string`*, or `account`* / `endpoint`* with `account_key`* or `sas_token`*. `queue` (default: native name), `message_encoding` (`base64` default, like the Azure SDKs, or `text`). `UseDevelopmentStorage=true` targets Azurite |
| `pubsub` | `subscription`* (default: native name; `projects/<p>/subscriptions/<s>` or a short name with `project`), `topic` (needed only to publish), auth: `access_token`, `token_command` (e.g. `[gcloud, auth, print-access-token]`, cached 45 min) or the GCE/GKE metadata server. `endpoint` + `emulator: true`, or `PUBSUB_EMULATOR_HOST` on the host, for the emulator. `return_immediately` (default `true`) |
| `mns` | `endpoint`*, or `account_id`* + `region`* (`https://<account_id>.mns.<region>.aliyuncs.com`). `access_key`*, `secret_key`*, `queue` (default: native name), `wait_seconds` (0-30), `message_encoding` (`base64` default, like the MNS SDKs, or `text`) |
| `cloudflare_queue` | `account_id`*, `queue_id`*, `api_token`* (the queue needs an HTTP pull consumer; token with Queues read/write), `endpoint` |
| `custom` | `class`* (`package.module:ClassName` in your app); every other parameter is passed to the constructor as a keyword argument |

How each one leases messages, so a crashed host never loses one (at-least-once):

- **sqs, azure_queue, mns, cloudflare_queue, pubsub**: the service's own visibility timeout / lease / ack deadline is set to the event's `visibility_timeout`. A failed message is made visible again at once; one that has failed `max_receive` times goes to `dead_letter` and is deleted. `receives` comes from the service (`ApproximateReceiveCount`, `DequeueCount`, `attempts`, `deliveryAttempt`); Pub/Sub without a dead-letter policy doesn't report attempts, so the host counts them itself (reset on restart).
- **redis**: see the layout below.
- **redis_stream**: entries stay in the consumer group's pending list until settled; an entry idle for longer than
  `visibility_timeout` is taken over with `XAUTOCLAIM`, and `receives` is the stream's delivery counter.
- **pskit_host**: the other host hides a leased message for `visibility_timeout` and counts failures; unsettled leases
  expire there.
- Azure Storage Queue, MNS and Cloudflare Queues messages have no attributes; attributes given to `submit` are dropped.
- Queue depth (`/__pskit/stats`, the dashboard) is `null` for Pub/Sub, Cloudflare Queues and custom classes without `depth()`.

**Redis layout.** A message is a JSON envelope `{id, body, attributes, receives, enqueued_at}` in the list `<key>` (`LPUSH`). Claiming moves it with `RPOPLPUSH` to `<key>:processing` and records the claim time in the hash `<key>:claims`. Delivered messages are removed. Failed ones go back to `<key>` until `max_receive`, then to `dead_letter`, which is another driver queue of that name or a builtin queue. Every few seconds the host requeues claims older than `visibility_timeout`, plus any message in `processing` that has no claim. Plain strings that another producer `LPUSH`es onto `<key>` are accepted and delivered as the record body.

### Storage drivers

| Driver | Parameters (`*` = required) |
|---|---|
| `s3` | `bucket` (default: native name), `access_key` + `secret_key` (both or neither; neither = the `AWS_*` variables, then anonymous), `session_token`, `prefix`, `region`, `path_style`. With `endpoint` (MinIO, Ceph, ...) requests go there path-style. Without one they go to AWS: `https://s3.<region>.amazonaws.com`, virtual-host style. `provider:` picks a preset below |
| `aws`, `oss`, `cos`, `obs`, `oci`, `ibm_cos`, `spaces`, `r2`, `minio`, `wasabi`, `b2`, `linode`, `scaleway` | the same parameters; the preset fills in the endpoint, addressing style and signing region (also usable as `driver: s3` + `provider: <name>`) |
| `azure_blob` | auth as `azure_queue`, `container` (default: native name), `prefix` |
| `gcs` | auth as `pubsub`, `bucket` (default: native name), `prefix`, `endpoint` (default `https://storage.googleapis.com`; fake-gcs-server via `endpoint` + `emulator: true`, or `STORAGE_EMULATOR_HOST`) |
| `custom` | `class`*, keyword arguments as for queues |

| Preset | Endpoint | Style | Extra required | Notes |
|---|---|---|---|---|
| `aws` | `https://s3.<region>.amazonaws.com` | virtual-host | | `region` defaults to `us-east-1` |
| `oss` | `https://oss-<region>.aliyuncs.com` | virtual-host | `region` (`cn-hangzhou`) | OSS's S3-compatible API with SigV4. If OSS rejects the signature, set `signing_region` to the region form it expects |
| `cos` | `https://cos.<region>.myqcloud.com` | virtual-host | `region` (`ap-guangzhou`) | the bucket name includes `-<APPID>` |
| `obs` | `https://obs.<region>.myhuaweicloud.com` | virtual-host | `region` (`cn-north-4`) | OBS's S3-compatible API; confirm SigV4 is accepted in your region |
| `oci` | `https://<namespace>.compat.objectstorage.<region>.oraclecloud.com` | path | `region`, `namespace` | Customer Secret Keys as `access_key` / `secret_key` |
| `ibm_cos` | `https://s3.<region>.cloud-object-storage.appdomain.cloud` | path | `region` (`us-south`) | HMAC credentials, not an API key |
| `spaces` | `https://<region>.digitaloceanspaces.com` | virtual-host | `region` (`nyc3`) | |
| `r2` | `https://<account_id>.r2.cloudflarestorage.com` | path | `account_id` | signing region `auto` |
| `minio` | your `endpoint` | path | `endpoint` | |
| `wasabi` | `https://s3.<region>.wasabisys.com` | virtual-host | | `region` defaults to `us-east-1` |
| `b2` | `https://s3.<region>.backblazeb2.com` | virtual-host | `region` (`us-west-004`) | application key ID as `access_key` |
| `linode` | `https://<region>.linodeobjects.com` | virtual-host | `region` (`us-east-1`) | Akamai / Linode Object Storage |
| `scaleway` | `https://s3.<region>.scw.cloud` | virtual-host | `region` (`fr-par`) | |

Ceph RGW, SeaweedFS, Garage, RustFS, LocalStack, pskit's own `s3` service and other self-hosted stores: `driver: s3` with `endpoint` (path-style by default).

`endpoint`, `path_style` and `signing_region` override any preset. The S3 driver also: signs for and talks to the bucket's real region when AWS (or a store that copies it) answers that the bucket lives elsewhere; falls back to the original ListObjects API on stores without ListObjectsV2; uses path-style for dotted bucket names over HTTPS (their TLS certificate does not cover them); and, with `create_bucket: true`, sends the region as `LocationConstraint` outside `us-east-1` and accepts a bucket the keys may use but not create.

**One storage service, many buckets (on premises).** A storage event can name a storage resource *and* a bucket: the resource is the service (driver, endpoint, keys) and `bucket` is any bucket on it. Without `bucket`, the event watches the resource's own bucket.

```yaml
resources:
  minio:                                   # the service: one set of keys for every bucket
    type: storage
    external: true
    options: {driver: minio, endpoint: http://minio.internal:9000, bucket: uploads,
              access_key_env: MINIO_ACCESS_KEY, secret_key_env: MINIO_SECRET_KEY}
functions:
  ingest:   {handler: app.handlers.ingest,   events: [{storage: {resource: minio}}]}                    # uploads
  invoices: {handler: app.handlers.invoices, events: [{storage: {resource: minio, bucket: invoices}}]}
```

`builtin` resources make it another bucket folder under `data_dir`; a `directory` resource is a single folder and cannot. Cloud providers reject `resource` + a different `bucket` (use one of them). In the studio: *Functions → trigger → Storage → Project resource*, pick the service, then type the bucket. The drivers are tested against local fakes of each documented API, not against the live services; try a new provider with a test bucket first.

Every storage driver lists the bucket (all pages) on each poll. A new or changed ETag emits `created`, a missing key emits `deleted`. Objects present at first start are recorded and not emitted. `prefix` limits the host to keys below it and is stripped from `record.key`. On a large bucket, always set `prefix`.

### Examples

```yaml
providers:
  onprem:
    resources:
      jobs:                       # an SQS queue in AWS, watched from your data centre
        external: true
        options:
          driver: sqs
          queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/jobs
          access_key_env: AWS_ACCESS_KEY_ID_JOBS
          secret_key_env: AWS_SECRET_ACCESS_KEY_JOBS
          wait_seconds: 10
      uploads:                    # an Azure Blob container
        external: true
        options:
          driver: azure_blob
          connection_string_env: AZURE_STORAGE_CONNECTION_STRING
          container: uploads
          prefix: incoming/
      events:                     # a Pub/Sub subscription
        external: true
        options:
          driver: pubsub
          project: my-project
          subscription: orders-onprem
          token_command: [gcloud, auth, print-access-token]
      media:                      # Cloudflare R2
        external: true
        options: {driver: r2, account_id: 0123abcd, access_key_env: R2_KEY, secret_key_env: R2_SECRET}
```

### Custom drivers

`custom` loads a class from your app, so any broker works: RabbitMQ, Kafka, NATS, IBM MQ, Tencent TDMQ, Huawei DMS, OCI Queue. Put its client library in `requirements.txt`; pskit itself doesn't import it.

Working examples: [`examples/19-custom-drivers`](../examples/19-custom-drivers) has a runnable SQLite queue (with a dead-letter table) and folder storage, plus RabbitMQ and Kafka templates. [`examples/20-onprem-external-clouds`](../examples/20-onprem-external-clouds) wires every built-in cloud driver into one host.

```yaml
resources:
  orders:
    type: queue
    external: true
    options:
      driver: custom
      class: app.backends:RabbitQueue
      url_env: RABBITMQ_URL          # -> RabbitQueue(url=os.environ["RABBITMQ_URL"], queue="orders")
      queue: orders
```

A queue class needs `submit(body, attributes) -> id`, `claim(batch, visibility, now) -> [message]` and `settle(claimed, failed_ids, max_receive, dead_letter, now)`; `depth()` and `recover(now, visibility)` are optional. A message is a dict with `id`, `body`, `attributes`, `receives`, `enqueued_at`, plus any private `_` keys you need in `settle`. A storage class needs `scan() -> {key: (etag, size)}`, `put`, `get` and `delete -> bool`. Import errors, constructor errors and missing methods stop the host with a message naming the class.

**Why RabbitMQ is `custom`.** The management HTTP API (`POST /api/queues/<vhost>/<queue>/get`) settles a message as it is read: `ack_requeue_false` removes it before the handler runs (lost if the handler fails), and `ack_requeue_true` puts it straight back (delivered again while still being processed, and it can't be acknowledged later). Neither is a lease, so pskit doesn't ship a lossy driver. AMQP with manual acks, as below, is at-least-once: unacknowledged messages return to the queue when the connection closes.

```python
# app/backends.py  (requirements.txt: pika)
import threading
import uuid

import pika


class RabbitQueue:
    def __init__(self, url, queue):
        self.params = pika.URLParameters(url)
        self.queue = queue
        self.lock = threading.Lock()  # pika connections are not thread-safe
        self.channel = None

    def _ch(self):
        if self.channel is None or self.channel.is_closed:
            self.channel = pika.BlockingConnection(self.params).channel()
            self.channel.queue_declare(queue=self.queue, durable=True)
        return self.channel

    def submit(self, body, attributes):
        message_id = uuid.uuid4().hex
        props = pika.BasicProperties(message_id=message_id, headers=attributes or None, delivery_mode=2)
        with self.lock:
            self._ch().basic_publish(exchange="", routing_key=self.queue, body=body.encode(), properties=props)
        return message_id

    def claim(self, batch, visibility, now):
        out = []
        with self.lock:
            ch = self._ch()
            for _ in range(batch):
                method, props, body = ch.basic_get(queue=self.queue, auto_ack=False)
                if method is None:
                    break
                headers = dict(props.headers or {})
                # Quorum queues count deliveries; classic queues only flag a redelivery.
                receives = int(headers.get("x-delivery-count", 0)) + 1 if "x-delivery-count" in headers else (
                    2 if method.redelivered else 1
                )
                out.append({
                    "id": props.message_id or str(method.delivery_tag),
                    "body": body.decode("utf-8"),
                    "attributes": headers,
                    "receives": receives,
                    "enqueued_at": now,
                    "_tag": method.delivery_tag,
                })
        return out

    def settle(self, claimed, failed_ids, max_receive, dead_letter, now):
        with self.lock:
            ch = self._ch()
            for msg in claimed:
                if msg["id"] not in failed_ids:
                    ch.basic_ack(delivery_tag=msg["_tag"])
                elif dead_letter is not None and msg["receives"] >= max_receive:
                    dead_letter.submit(msg["body"], msg["attributes"])
                    ch.basic_ack(delivery_tag=msg["_tag"])
                else:
                    ch.basic_nack(delivery_tag=msg["_tag"], requeue=True)

    def depth(self):
        with self.lock:
            return self._ch().queue_declare(queue=self.queue, passive=True).method.message_count
```

A connection drop between `claim` and `settle` makes the stored delivery tags invalid; the messages are redelivered by RabbitMQ and `settle` fails once (logged as a host note).

An endpoint that can't be reached shows up as a host note (`/__pskit/health`, `pskit logs --source host`). The host keeps serving other triggers and retries on the next poll.

**Browsing.** `GET /__pskit/resources/<key>/data?offset=&limit=&prefix=` returns a page of messages (peeked) or
objects, `GET /__pskit/resources/<key>/object?key=` previews an object, `DELETE .../object?key=` and
`DELETE .../message?id=` (built-in queues) delete one, `GET /__pskit/queues/<name>/peek` serves the `pskit_host`
driver. A custom queue class can add `peek(offset, limit) -> (items, total)` to be browsable.

`pskit validate` rejects a driver that isn't allowed for the type, missing required parameters, one of a key pair without the other, a non-http(s) `endpoint`, and a malformed `class`.

## Secrets

Connection values become environment variables. They're stored in Terraform state and, on premises, in `.pskit/onprem-<stage>/onprem_app/pskit_host.json`. Treat both as sensitive, or keep secrets out of them:

- Put the **name** of a secret variable in `connection` (`password_env: ORDERS_DB_PASSWORD`) and read the secret at run time (`ctx.env[db["password_env"]]`) from the platform's secret store or function environment.
- `${env:...}` resolves on the machine that runs `pskit deploy`, so the value is written into state. Use it knowingly, typically for on-prem driver credentials.

`pskit info --json` and the dashboard list connection **key names** only, never values.

## Troubleshooting

| Message | Fix |
|---|---|
| `pskit does not create `database` resources; set `external: true`` | database / cache / custom are always external |
| `function 'x' uses unknown resource 'y'` | add `y` under `resources:` or fix the key |
| `function 'x' has a queue event on resource 'y', which is a storage` | the resource `type` must match the event kind |
| `set either `name` or `resource` on the queue event, not both` | drop the event's `name` / `bucket` |
| `managed queue resources that no event uses are not supported on X yet` | create it outside pskit, set `external: true` and `name` |
| `resource 'x' is not bound to this function` (runtime) | add the function to the resource's `functions:` list, or remove the list |
| `the redis driver needs url: redis://host:6379/0` | set `options.url` (or `connection.url`) |
| `environment variable X (option secret_key_env ...) is not set on the host` | export `X` where the on-prem host runs (systemd unit, Docker `-e`, shell) |
| `custom driver (queue jobs): cannot import 'app.backends'` | the module must be in the bundle (`package.source`); its dependencies in `requirements.txt` |
| `custom driver ...: X does not implement claim, settle` | add the missing methods; `depth` and `recover` are optional |
| `sqs: request failed (400): ... QueueDoesNotExist` | check `queue_url` / `region` and that the credentials can see the queue |
