# On-premises queues (`type: queue`)

Trigger functions on the host from a queue: the host's built-in queue, Redis / Valkey, RabbitMQ or Kafka through a
custom driver, or a queue in a cloud. Every option gives the same at-least-once handling: `batch_size`,
`visibility_timeout`, `max_receive`, `dead_letter` and `BatchResult` work the same way.

## Create one in one click

The studio (*Resources → On-prem services → + Create service*) or the CLI starts the broker with Docker, here or on
any SSH server, writes the resource and adds the trigger:

```bash
pskit resources onprem create jobs --service redis --attach worker --save                 # Redis list
pskit resources onprem create jobs --service valkey --role stream --attach worker --save  # Valkey stream
pskit resources onprem create events --service kafka --attach worker --save               # Kafka (Redpanda)
pskit resources onprem create tasks --service nats --ssh ubuntu@10.0.0.7 --pem k.pem --save
```

Details, backups and removal: [services.md](services.md). The sections below show the same setups by hand.

## Built-in queue

No setup. The queue is a directory under the host's `data_dir`.

```yaml
provider:
  name: onprem
  region: local
  options: {host: 127.0.0.1, port: 8080}

resources:
  jobs:
    type: queue                  # managed: created when the host starts
  jobs-dlq:
    type: queue

functions:
  api:
    handler: app.handlers.api
    events: [{http: POST /jobs}]
  worker:
    handler: app.handlers.work
    events:
      - queue: {resource: jobs, batch_size: 10, max_receive: 3, dead_letter: jobs-dlq}
```

Use a shared folder (NFS, SMB) instead: `options: {driver: directory, path: /mnt/shared/queues}` with
`external: true`.

## Redis / Valkey

### 1. Set up Redis

- **Docker:** `docker run -d --name redis -p 6379:6379 redis:7 redis-server --requirepass <password>`
  (Valkey: `valkey/valkey:8`).
- **Linux package:** `sudo apt install redis-server`; in `/etc/redis/redis.conf` set `requirepass <password>` and
  `bind` to an address the host can reach; `sudo systemctl restart redis-server`.
- **Managed Redis** (Azure Cache, ElastiCache, Upstash, DigitalOcean): copy the host, port and password from its
  console; TLS endpoints use `rediss://`.

### 2. Collect the values

| Value | Where | Example |
|---|---|---|
| URL | `redis://[user:password@]host:port/db`, `rediss://` for TLS | `redis://:s3cret@10.0.0.5:6379/0` |
| Key | the Redis list the queue uses (default: the resource's native name) | `jobs` |

Check it with `redis-cli -u "$REDIS_URL" ping` from the host machine.

```bash
export REDIS_URL='redis://:s3cret@10.0.0.5:6379/0'      # on the host
```

### 3. Declare it in `pskit.yml`

```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis
      url_env: REDIS_URL         # or url: redis://... (then it's written into the generated files)
      key: jobs

functions:
  worker:
    handler: app.handlers.work
    events:
      - queue: {resource: jobs, batch_size: 10, visibility_timeout: 60}
```

Other producers can `LPUSH jobs '<text>'`; plain strings are delivered as the record body. How messages are leased:
[resources.md → Redis layout](../../resources.md#queue-drivers).

## Redis / Valkey stream (`redis_stream`)

A stream with a consumer group instead of a list: native leases and delivery counts, several hosts can share one group,
and other services can read the same stream with groups of their own. Needs Redis 6.2+ or Valkey.

```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis_stream
      url_env: REDIS_URL
      key: jobs                  # the stream (default: native name)
      group: pskit               # consumer group (default pskit); hosts in one group share the work
      maxlen: 100000             # optional: trim to about this many entries
```

Messages are `XADD jobs * body <text> attributes <json>`; another producer may `XADD` any fields (the `body` field,
else the first field's value, becomes the record body). An entry is acknowledged and deleted once the handler
succeeded. A failed entry is claimable again at once; after `max_receive` deliveries it goes to `dead_letter`. An entry a
crashed host never settled is taken over (`XAUTOCLAIM`) once it has been idle for `visibility_timeout`.

## Kafka and NATS JetStream

Both use a driver class that one-click creation copies into `pskit_drivers/` (with `kafka-python` or `nats-py` in
`requirements.txt`). By hand:

```yaml
resources:
  events:                        # Kafka / Redpanda topic
    type: queue
    external: true
    options:
      driver: custom
      class: pskit_drivers.kafka_queue:KafkaQueue
      bootstrap_servers: 10.0.0.7:9092
      topic: events
      group_id: shop-events
  tasks:                         # NATS JetStream stream + durable pull consumer
    type: queue
    external: true
    options:
      driver: custom
      class: pskit_drivers.nats_queue:NatsQueue
      url_env: NATS_URL          # nats://user:pass@10.0.0.7:4222
      stream: tasks
      subject: tasks.jobs
      durable: pskit
```

Templates: [`examples/19-custom-drivers/app/kafka_queue.py`](../../../examples/19-custom-drivers/app/kafka_queue.py)
and `pskit_drivers/nats_queue.py` after a one-click NATS creation. Kafka reports no queue depth; NATS reports pending
plus unacknowledged messages.

## A queue on another on-prem host (`pskit_host`)

Functions on host A can consume the **built-in** queue of host B (another pskit deployment, possibly another
project), with no broker installed anywhere:

```yaml
# host A (the consumer)
resources:
  orders:
    type: queue
    external: true
    options:
      driver: pskit_host
      endpoint: http://10.0.0.6:8080     # host B; it must bind options.host: 0.0.0.0
      queue: orders                       # the queue's name on B (default: native name)
      token_env: HOST_B_TOKEN             # B's provider.options.admin_token, if B sets one
functions:
  worker:
    handler: app.handlers.work
    events: [{queue: {resource: orders, max_receive: 3, dead_letter: orders-dlq}}]
```

Host B only needs the queue (a managed `type: queue` resource, or any queue its functions publish to). A leases
messages through B's admin API (`POST /__pskit/queues/orders/lease`, then `ack` / `nack`): B hides a leased message for
`visibility_timeout` seconds, so if A crashes it is delivered again. Publish to it from A with
`submit_queue(resource("orders").native_name, ...)`, from B as usual, or with `curl -X POST .../__pskit/queues/orders`.

## RabbitMQ (or other brokers) via a custom driver

pskit ships no RabbitMQ driver (the management HTTP API can't lease messages safely). A small class in your app does it.

### 1. Create the queue (RabbitMQ management UI)

1. Open `http://<rabbit-host>:15672` (enable it with `rabbitmq-plugins enable rabbitmq_management`; Docker image
   `rabbitmq:3-management`).
2. **Admin → Users → Add a user** (`pskit`, a password, no tags) → click the user → **Set permission** on the virtual
   host `/`.
3. **Queues and Streams → Add a new queue** → type *Quorum* (counts deliveries) or *Classic*, name `orders`, durable.

### 2. Declare it

```bash
export RABBITMQ_URL='amqp://pskit:s3cret@rabbit.internal:5672/%2F'    # on the host
```

```yaml
resources:
  orders:
    type: queue
    external: true
    options:
      driver: custom
      class: app.rabbitmq_queue:RabbitQueue   # your class
      url_env: RABBITMQ_URL                   # -> RabbitQueue(url=os.environ["RABBITMQ_URL"], queue="orders")
      queue: orders

functions:
  worker:
    handler: app.handlers.work
    events: [{queue: {resource: orders}}]
```

Copy the class from [`examples/19-custom-drivers/app/rabbitmq_queue.py`](../../../examples/19-custom-drivers/app/rabbitmq_queue.py)
(Kafka: `kafka_queue.py` next to it) and add `pika` to `requirements.txt`. The interface a class needs is in
[resources.md → Custom drivers](../../resources.md#custom-drivers).

## A queue in a cloud

Find the values with the cloud's guide, then use the matching driver:

| Queue | Driver and required parameters | Where to find the values |
|---|---|---|
| Amazon SQS | `sqs`: `queue_url` (+ `access_key_env`, `secret_key_env`; or `AWS_*` on the host) | SQS console → queue → *Details → URL*; IAM → user → *Security credentials → Create access key* |
| Azure Storage queue | `azure_queue`: `connection_string_env` (or `account` + `account_key_env` / `sas_token_env`), `queue` | [azure/queue.md](../azure/queue.md#2-collect-the-values) |
| Google Pub/Sub | `pubsub`: `subscription` (pull), `token_command` or `access_token_env` | Pub/Sub console → *Subscriptions* → create a **Pull** subscription → its full name |
| Alibaba MNS | `mns`: `account_id` + `region` (or `endpoint`), `access_key_env`, `secret_key_env`, `queue` | MNS console → queue → *Endpoint*; RAM → AccessKey |
| Cloudflare Queues | `cloudflare_queue`: `account_id`, `queue_id`, `api_token_env` (queue needs an HTTP pull consumer) | [cloudflare/queue.md](../cloudflare/queue.md#2-collect-the-values) |

```yaml
resources:
  azure-jobs:
    type: queue
    external: true
    options:
      driver: azure_queue
      connection_string_env: AZURE_STORAGE_CONNECTION_STRING
      queue: orders-jobs
  aws-jobs:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/jobs
      access_key_env: AWS_ACCESS_KEY_ID
      secret_key_env: AWS_SECRET_ACCESS_KEY
      wait_seconds: 10
```

A working host that watches all of them: [`examples/20-onprem-external-clouds`](../../../examples/20-onprem-external-clouds).

## Use it in a handler

```python
from py_serverless_kit import BatchResult, resource
from py_serverless_kit.runtime.onprem_host import submit_queue


def api(event, ctx):
    message_id = submit_queue(resource("jobs").native_name, event.http.json())
    return {"id": message_id}


def work(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            ctx.logger.info("job", extra={"id": record.id, "body": record.body})
        except Exception:
            result.fail(record)
    return result
```

`submit_queue` goes through the resource's driver, so the same code writes to the built-in queue, Redis or SQS.

## Test

```bash
pskit validate
pskit deploy
pskit resources send jobs -d '{"order_id": 1}'
curl -X POST -d '{"order_id": 2}' http://127.0.0.1:8080/__pskit/queues/jobs
curl http://127.0.0.1:8080/__pskit/queues/jobs           # {"depth": n}
pskit logs -f --function worker
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `the redis driver needs url: redis://host:6379/0` | set `url` or `url_env` |
| `environment variable X (option ..._env ...) is not set on the host` | export `X` where the host runs (see [README](README.md#secrets-name_env)) |
| `custom driver (queue orders): cannot import 'app.rabbitmq_queue'` | the module must be in the bundle; its library in `requirements.txt` |
| `sqs: request failed (400): ... QueueDoesNotExist` | check `queue_url` / `region` and the credentials |
| Messages pile up, no errors | check `pskit logs --source host` for host notes about the endpoint |
| `pskit_host: ... request failed (401)` | set `token_env` to the other host's `admin_token` |
| `queue x uses a driver; consume it from that service directly` | `pskit_host` only reaches the other host's built-in queues |
| Kafka consumer never receives anything | update `pskit_drivers/kafka_queue.py` from the template: older copies polled with a zero timeout and never joined the consumer group |
