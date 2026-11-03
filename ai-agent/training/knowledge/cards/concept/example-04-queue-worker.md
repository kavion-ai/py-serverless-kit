# Example: 04-queue-worker

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: fifo: true              # ordered, exactly-once processing (AWS SQS FIFO only)

# 04 · Queue worker

Shows a batch consumer that retries only the failed messages, a dead-letter queue with its
own consumer, and an HTTP producer.

## How a batch is handled

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

The example's `enqueue` handler logs on a cloud, so it runs anywhere without credentials. On premises (`PSKIT_ONPREM_ROOT`) it writes the job into the file queue with `submit_queue`.

## Run locally

Expected: the transient failure is reported and the poison message is dropped.
