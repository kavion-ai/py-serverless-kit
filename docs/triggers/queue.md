# Queue trigger

Search terms: queue, message queue, SQS, Storage Queue, Pub/Sub, worker, consumer, batch, batch size, dead letter, DLQ, max receive, visibility timeout, fifo, BatchResult, retry failed messages, Redis queue

The pskit `queue` trigger runs a function for messages on a queue, in batches where the cloud supports it, with
retries and an optional dead-letter queue. On AWS it is SQS, on Azure a Storage Queue, on GCP a Pub/Sub topic, and on
premises a file broker or a resource driver such as Redis.

## Write a queue trigger in pskit.yml

The pskit `queue` trigger needs `name` or `resource`.

```yaml
events:
  - queue: jobs                        # shorthand: the queue name
  - queue:
      name: jobs
      existing: false                  # true: attach to a queue that already exists
      batch_size: 10                   # 1-10000 messages per call
      batch_window: 5                  # 0-300 seconds to wait to fill a batch
      visibility_timeout: 120          # seconds; default max(30, 6 x function timeout)
      dead_letter: jobs-dlq            # queue that receives a message after max_receive failures
      max_receive: 5
      fifo: false                      # AWS: ordered FIFO queue, ".fifo" added to the name
  - queue: {resource: orders-queue, batch_size: 5}   # a resources: entry of type queue
```

| Key | Default | Meaning |
|---|---|---|
| `name` | | native queue name (AWS uses it as given) |
| `resource` | | key of a `resources:` entry of type `queue` (instead of `name`) |
| `existing` | `false` | `true`: pskit attaches the trigger but never creates or deletes the queue |
| `batch_size` | 10 | messages per invocation, 1 - 10000 |
| `batch_window` | 0 | seconds, 0 - 300 |
| `visibility_timeout` | `max(30, 6 x timeout)` | seconds a received message stays hidden |
| `dead_letter` | | name of the dead-letter queue (pskit creates it on AWS and on premises) |
| `max_receive` | 5 | deliveries before a message moves to `dead_letter` |
| `fifo` | `false` | ordered queue with content-based de-duplication (AWS) |

## Read queue messages in the handler

For a `queue` trigger `event.type == "queue"` and `event.records` holds one `Record` per message.

```python
from py_serverless_kit import BatchResult, Context, Event


def process_jobs(event: Event, ctx: Context) -> BatchResult:
    result = BatchResult()
    for record in event.records:              # or: for record in event:
        try:
            job = record.json()               # body parsed as JSON (record.text() for plain text)
            ctx.logger.info("job", extra={"id": record.id, "job": job, "attrs": record.attributes})
        except Exception:
            result.fail(record)               # retry only this message
    return result
```

| `Record` field | Meaning |
|---|---|
| `id` | message id (what `BatchResult` reports) |
| `body`, `text()`, `json(default=...)` | the message body |
| `attributes` | message attributes / metadata (SQS attributes and message attributes on AWS) |
| `source` | queue identifier (the queue ARN on AWS) |
| `raw` | the native record (not portable) |

`event.json()` returns the first record's body. Write idempotent handlers: redelivery is normal on every cloud.

## Retry only the failed messages with BatchResult

A pskit queue handler returns `BatchResult` to report the failed records: `result.fail(record)` (or a record id),
or `BatchResult.of(failed_records)`.

| Provider | What happens to failed records |
|---|---|
| aws | becomes `batchItemFailures` (the event source mapping has `ReportBatchItemFailures`): only failed messages return |
| onprem | the host retries only the failed ids, then moves a message to `dead_letter` after `max_receive` |
| local | printed as `{"batchItemFailures": [...]}` |
| gcp, azure | any failure raises `BatchFailure`, so the whole delivery is retried |

Raising an exception instead fails the whole batch on every cloud.

## Add a queue trigger in studio

1. Sidebar **Functions** → open the function → **2 Triggers** → card **Queue** (default name `<function>-jobs`,
   `batch_size: 10`).
2. **Source**:
   - **Create new queue**: type **Queue name**; pskit creates it on deploy. **Create & select** also adds it to
     **Resources** (and switches to it) so other functions can bind it.
   - **Project resource (N)**: pick a `resources:` queue in **Resource** (disabled when there is none).
   - **Pick from <provider>**: lists existing queues with this machine's credentials (AWS with boto3; GCP with
     `google-cloud-pubsub`; Azure with `azure-storage-queue` and `AZURE_STORAGE_CONNECTION_STRING`; on premises).
     **Also add to Resources (external)** is on by default. **Refresh** reloads the list.
   - **Type a name**: an existing queue; pskit only attaches the trigger (`existing: true`).
3. The remaining fields (**batch_size**, **batch_window**, **visibility_timeout**, **dead_letter**, **max_receive**,
   **fifo**) have suggestions such as 1, 5, 10, 25, 100, 1000 for the batch size.
4. The **On <provider>:** box lists options the provider ignores or rejects. **Apply changes**, then **Save**.

## Queues per provider

The pskit queue options are honoured differently per cloud.

| Option | aws (SQS) | gcp (Pub/Sub topic + push) | azure (Storage Queue) | onprem |
|---|---|---|---|---|
| `batch_size`, `batch_window` | yes | not used | not used | yes |
| `visibility_timeout` | yes | not used | not used | yes |
| `dead_letter`, `max_receive` | redrive policy | ignored, warning | ignored, warning: poison messages go to `<queue>-poison` | yes |
| `fifo` | yes (`.fifo` suffix) | ignored, warning | ignored, warning | yes |
| partial batch failure | yes | whole delivery | whole delivery | yes |
| `existing: true` | data source lookup | existing topic | needs `provider.options.storage_connection` for another account | waits for the directory to appear |

Other notes:

- GCP has no pull-queue trigger, so a "queue" is a Pub/Sub topic with a push trigger; event-triggered functions are
  limited to 540 s.
- Azure queue names must be 3 - 63 lowercase letters, digits and dashes.
- Alibaba, Tencent, Huawei, Oracle, IBM, DigitalOcean and Cloudflare have no queue trigger in pskit. Use `topic` where
  available, or an HTTP trigger.
- On premises the queue is a directory of JSON files by default (`provider.options.services.queue`: `builtin` or
  `{use: directory, path: ...}`). A `resources:` queue can use another driver: `redis`, `redis_stream`, `sqs`,
  `azure_queue`, `pubsub`, `mns`, `cloudflare_queue`, `pskit_host`, `custom`. See
  [../onprem/resources.md](../onprem/resources.md) and [../onprem/cloud-resources.md](../onprem/cloud-resources.md).

## Attach to a new or an existing queue

A pskit queue trigger either creates the queue or attaches to one that exists.

| You want | YAML |
|---|---|
| pskit creates the queue | `- queue: jobs` |
| an existing queue, by name | `- queue: {name: legacy-jobs, existing: true}` |
| a queue other functions also use (sending side gets its connection) | `resources: {jobs: {type: queue}}` and `- queue: {resource: jobs}` |
| an existing queue as a resource | `resources: {jobs: {type: queue, external: true, name: legacy-jobs}}` and `- queue: {resource: jobs}` |

pskit never deletes an `existing` queue or an `external` resource on `pskit remove`.

## Test a queue trigger

- Locally: `pskit invoke -f process-jobs -t queue -d '[{"job": 1}, {"job": 2}]'` (a list gives one record each, ids
  `local-0`, `local-1`).
- `pskit dev`: `curl -X POST "localhost:3000/__pskit/invoke/process-jobs?type=queue" -d '[{"job": 1}]'`.
- Studio: **Test** → the function → the `queue <name>` card → **Payload (JSON)** (one message or a list) →
  **▶ Run locally** or **☁ Send to <provider> / <stage>** (a real message).
- Deployed: `pskit trigger -f process-jobs -e 0 -d '{"order_id": 1}'` sends a real message on AWS, GCP, Azure and on
  premises. For a queue resource: `pskit resources send jobs -d '{"order_id": 1}'`. Then
  `pskit logs -f --function process-jobs`.

## Common queue trigger errors

| Message or symptom | Fix |
|---|---|
| `queue event needs 'name' or 'resource'` | set one |
| `set either 'name' or 'resource' on the queue event, not both` | remove one |
| `function 'x' has a queue event on resource 'y', which is a storage` | point at a queue resource |
| `queue name 'Jobs' must be 3-63 lowercase letters, digits, dashes` (Azure) | rename |
| `<Provider> does not support 'queue' events in pskit` | use aws, azure, gcp or onprem |
| `event-triggered functions are limited to 540s on GCP` | lower `timeout` |
| the same message arrives twice | normal at-least-once delivery: make the handler idempotent |
| messages pile up in `jobs-dlq` | the handler failed `max_receive` times: check `pskit logs` |

## See also

- [README.md](README.md)
- [topic.md](topic.md)
- [../functions/invoke-and-test.md](../functions/invoke-and-test.md)
- [../resources.md](../resources.md)
- [../onprem/resources.md](../onprem/resources.md)
- [../events.md](../events.md)
