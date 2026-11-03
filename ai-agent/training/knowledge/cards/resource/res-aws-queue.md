# Resource: AWS SQS queue

On AWS, `type: queue` is an Amazon SQS queue. Use it to take work off an HTTP request. AWS can also create a managed queue. The guide is the path for a queue that already exists in the console.

A standard queue name is up to 80 letters, digits, `-`, and `_`. A FIFO queue name ends in `.fifo`. Set the visibility timeout to at least the function timeout. The events page says the AWS default, when pskit creates the queue, is `max(30, 6 x function timeout)`. A dead-letter queue and a maximum receive count are optional and are set in the console for an external queue.

Declare `type: queue`, `external: true`, and `name`. A worker event can set `resource`, `batch_size`, and `batch_window`. pskit looks the queue up with `data.aws_sqs_queue` in the deploy account and region, creates an event source mapping with partial batch failures, adds `sqs:SendMessage`, `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`, `GetQueueAttributes`, and `GetQueueUrl` on the queue ARN, and sets `PSKIT_RESOURCE_<KEY>_ARN` and `_URL`. `dead_letter`, `max_receive`, `visibility_timeout`, and `fifo` on the event apply when pskit creates the queue.

Send with `boto3` (already on Lambda; pin it in `requirements.txt` when you need a version) and `QueueUrl=resource("jobs").url`. Node.js uses `@aws-sdk/client-sqs`. The worker reads `event.records`. Return a `BatchResult` to retry only the failed messages. A customer-managed KMS key needs `kms:Decrypt` and `kms:GenerateDataKey` in `provider.iam.statements`. Another account or region can be a send target via `connection.arn` and `connection.url`. The trigger lookup stays in the deploy account and region.

Open:

Resources > + Add resource

Resources > Browse account

```
pskit invoke -f worker -t queue -d '{"order_id": 1}'
pskit resources send jobs -d '{"order_id": 1}'
pskit logs -f --function worker
```

`no matching SQS Queue found` means the name or the region does not match. A visibility timeout below the function timeout is raised on the queue in the console.

Sources: `docs/resource-guides/aws/queue.md#amazon-sqs-queue-type-queue`, `docs/events.md#queue`, `docs/resources.md#aws-iam`
