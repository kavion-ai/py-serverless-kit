# Resource: queue

A queue resource decouples a slow job from the request that created it. The HTTP function publishes a message and returns. A worker function runs when the message is available, and a failed message can be retried or sent to a dead-letter queue.

The guide index names the native service: Amazon SQS, an Azure Storage queue, a Pub/Sub topic used as a queue, Alibaba SMQ / MNS, Tencent TDMQ for CMQ, Huawei DMS (RabbitMQ or Kafka), OCI Queue, IBM MQ, a DigitalOcean Managed Valkey list, Cloudflare Queues, and an on-premises broker (built-in files, Redis, Kafka, NATS, RabbitMQ, or another host).

`type: queue` may be managed. AWS, GCP, Azure, and on premises can keep a standalone managed queue. On the other clouds, a managed queue is valid where a queue event uses it. Elsewhere set `external: true`. On AWS, a standalone managed queue takes `fifo`, `visibility_timeout`, `dead_letter`, and `max_receive` from the first event that uses it, or from `options`.

Declare `type: queue` under `resources`. Bind it with `functions`, or leave the list off so every user function receives `PSKIT_RESOURCE_<KEY>_*`. A queue event can say `resource: jobs` plus `batch_size`, `batch_window`, `dead_letter`, and `max_receive`. The event uses the resource native name, and `existing` follows `external`. The events table marks a queue trigger on AWS SQS, GCP Pub/Sub, Azure Storage Queue, and on-premises files. On GCP the queue is a Pub/Sub topic with a push trigger. Azure queue names are 3–63 lowercase letters, digits, and dashes. On premises the file broker implements batch size, visibility, dead-letter, `max_receive`, and `fifo`.

The worker sees `event.type == "queue"` and `event.records`. A `BatchResult` retries only the failed record ids on AWS and on premises. GCP and Azure retry the whole delivery. Publishing uses `boto3` or `@aws-sdk/client-sqs` with `resource("jobs").url` on AWS, `google-cloud-pubsub` on GCP, and `azure-storage-queue` on Azure. On premises, `submit_queue` follows the queue driver.

Open:

Resources > + Add resource

Resources > How to use

Resources > Test

```
pskit invoke -f worker -t queue -d @message.json
pskit resources send jobs -d '{"order_id": 1}'
pskit logs -f --function worker
pskit resources usage jobs -p aws -s dev
```

On AWS, `dead_letter`, `max_receive`, `visibility_timeout`, and `fifo` on the event apply when pskit creates the queue. An external SQS queue keeps them in the console. On premises the file broker implements the same options.

Sources: `docs/events.md#queue`, `docs/resources.md#provider-support`, `docs/resource-usage.md#queues-buckets-and-topics`, `docs/handlers.md#batchresult`
