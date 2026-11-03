# 04 · Queue worker

Shows a batch consumer that retries only the failed messages, a dead-letter queue with its
own consumer, and an HTTP producer.

## How a batch is handled

```python
result = BatchResult()
for record in event.records:
    try:
        handle(record.json())
    except PermanentError:
        log_and_drop()            # retrying a bad payload never helps
    except Exception:
        result.fail(record)       # transient: retry this message
return result
```

| Cloud | What `BatchResult` does |
| --- | --- |
| AWS SQS | partial batch response: only failed messages are retried |
| On-premises | partial batch response: only failed messages are retried, then dead-lettered |
| GCP Pub/Sub, Azure Storage Queues, others | any failure fails the invocation, so the whole batch is redelivered |

Make processing **idempotent**: on most clouds a message can be delivered more than once.

## Queue options

| Option | AWS | GCP | Azure |
| --- | --- | --- | --- |
| `name` | SQS queue | Pub/Sub topic + push subscription | Storage queue |
| `batch_size` | yes | ignored (one message per invocation) | host setting |
| `dead_letter` / `max_receive` | SQS redrive policy | warning, not configured | poison queue `<name>-poison` (built in) |
| `fifo` | SQS FIFO | warning | not supported |
| `existing: true` | look up instead of create | yes | yes |

On premises every option in the YAML is implemented by a directory of message files. `builtin` (the default) creates that directory at start. `{use: directory, path: ...}` under `provider.options.services.queue` uses a directory you already have.

`pskit validate --provider <cloud>` prints the warnings for your configuration.

## The producer

Publishing a message is a cloud SDK call: `boto3` `sqs.send_message`, `google-cloud-pubsub`
`publish`, `azure-storage-queue` `send_message`. py-serverless-kit does **not** wrap these
SDKs, because their delivery guarantees and options differ too much. Keep that one call
behind your own small interface, for example:

```python
def send_job(job: dict) -> None:
    provider = os.environ["PSKIT_PROVIDER"]
    if provider == "aws":
        boto3.client("sqs").send_message(QueueUrl=..., MessageBody=json.dumps(job))
    elif provider == "gcp":
        pubsub_v1.PublisherClient().publish(topic_path, json.dumps(job).encode())
    ...
```

The example's `enqueue` handler logs on a cloud, so it runs anywhere without credentials. On premises (`PSKIT_ONPREM_ROOT`) it writes the job into the file queue with `submit_queue`.

## Run locally

```bash
pskit invoke -f process-jobs -d '[{"kind": "email", "id": 1}, {"kind": "email", "simulate_failure": true}, {"kind": "nope"}]'
```

Expected: the transient failure is reported and the poison message is dropped.

```json
{"batchItemFailures": [{"itemIdentifier": "local-1"}]}
```

```bash
pskit invoke -f enqueue -d '{"kind": "invoice", "id": 7}'    # 202
```

## Deploy

```bash
pskit deploy                    # SQS queues + DLQ + event source mappings
pskit deploy --provider gcp     # Pub/Sub topics + Eventarc triggers
pskit deploy --provider azure   # Storage queues + queue triggers
pskit deploy --provider onprem  # file queues on this machine, http://127.0.0.1:8084
```
