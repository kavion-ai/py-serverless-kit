# Amazon SQS queue (`type: queue`)

Use an SQS queue you created in the console: trigger a function with its messages, send messages to it from a handler,
or both.

## 1. Create the queue (console)

Skip this if the queue already exists.

1. Console → **Simple Queue Service** → **Create queue**.
2. Type: *Standard* (or *FIFO*: the name must then end in `.fifo`). Name: up to 80 letters, digits, `-` and `_`, for
   example `orders-jobs`.
3. **Configuration** → *Visibility timeout*: at least the Lambda timeout (pskit's default timeout is 30 s; AWS
   recommends 6 × the function timeout, so `180` seconds is a good value).
4. Optional: **Dead-letter queue** → *Enabled*, pick a queue you created first, *Maximum receives* `5`.
5. **Create queue**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Queue name | SQS → **Queues** → the list | `orders-jobs` |
| Queue URL | Queues → the queue → **Details** → *URL* | `https://sqs.eu-west-1.amazonaws.com/123456789012/orders-jobs` |
| Queue ARN | Queues → the queue → **Details** → *ARN* | `arn:aws:sqs:eu-west-1:123456789012:orders-jobs` |
| Region | the region selector, or the URL | `eu-west-1` |
| Encryption | Queues → the queue → **Encryption** tab | *SSE-SQS* (nothing to do) or a KMS key ARN |

No keys or passwords are needed: the Lambda role gets SQS permissions from pskit.

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: aws
  region: eu-west-1

resources:
  jobs:                          # key used in code: resource("jobs")
    type: queue
    external: true               # created in the console; pskit never creates or deletes it
    name: orders-jobs            # the queue name from step 2

functions:
  worker:                        # triggered by every message
    handler: app.handlers.work
    events:
      - queue: {resource: jobs, batch_size: 10, batch_window: 5}
  api:                           # sends messages to the queue
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
```

What pskit does with it:

- looks the queue up by name (`data "aws_sqs_queue"`) in the deploy account and region,
- creates an event source mapping (`batch_size`, `batch_window`, partial batch failures) for `worker`,
- adds `sqs:SendMessage`, `ReceiveMessage`, `DeleteMessage`, ... on the queue ARN to the functions' IAM role,
- sets `PSKIT_RESOURCE_JOBS_ARN` and `PSKIT_RESOURCE_JOBS_URL`.

Notes:

- `dead_letter`, `max_receive`, `visibility_timeout` and `fifo` on the event only apply when pskit **creates** the
  queue. For an external queue, set them in the console (step 1).
- FIFO queue: put the full name, including `.fifo`, in `name`.
- Queue encrypted with a **customer-managed KMS key**: add `kms:Decrypt` and `kms:GenerateDataKey` on that key under
  `provider.iam.statements`.
- Queue in **another account or region**: you can send to it (set `connection: {arn: ..., url: ...}`), but you can't
  trigger a function from it with pskit; the trigger lookup only searches the deploy account and region.

## 4. Use it in a handler

`boto3` is already available in the Lambda Python runtime; add it to `requirements.txt` only to pin a version.

```python
import json

import boto3
from py_serverless_kit import resource

sqs = boto3.client("sqs")


def submit(event, ctx):
    jobs = resource("jobs")
    sqs.send_message(QueueUrl=jobs.url, MessageBody=json.dumps(event.http.json()))
    return {"queued": True}


def work(event, ctx):
    for record in event.records:
        ctx.logger.info("job received", extra={"id": record.id, "body": record.body})
```

The function receives:

```
PSKIT_RESOURCE_JOBS_TYPE=queue
PSKIT_RESOURCE_JOBS_NAME=orders-jobs
PSKIT_RESOURCE_JOBS_EXTERNAL=true
PSKIT_RESOURCE_JOBS_ARN=arn:aws:sqs:eu-west-1:123456789012:orders-jobs
PSKIT_RESOURCE_JOBS_URL=https://sqs.eu-west-1.amazonaws.com/123456789012/orders-jobs
```

Return a `BatchResult` from `work` to retry only the failed messages (see [handlers.md](../../handlers.md#batchresult)).

## 5. Test

```bash
pskit validate
pskit invoke -f worker -d '{"order_id": 1}'      # locally, no cloud needed
pskit deploy
pskit resources send jobs -d '{"order_id": 1}'   # real SQS message (boto3 + your AWS credentials)
pskit logs -f --function worker
```

Console: SQS → the queue → **Send and receive messages** → *Message body* → **Send message**. The message is gone
from *Messages available* once `worker` has processed it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy: `no matching SQS Queue found` | wrong `name`, or the queue is in another region/account than `provider.region` / your credentials |
| Deploy: `Queue visibility timeout ... is less than Function timeout` | raise the queue's *Visibility timeout* in the console (≥ function timeout) |
| Messages processed again and again | the handler fails; configure a dead-letter queue on the queue in the console |
| `AccessDenied` / `KMS.AccessDeniedException` | customer-managed KMS key: add `kms:Decrypt` / `kms:GenerateDataKey` in `iam.statements`; own `iam.role`: grant SQS yourself |
| `resource 'jobs' is not bound to this function` | add the function to the resource's `functions:` list, or remove the list |
