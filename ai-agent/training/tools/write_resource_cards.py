"""Resource type cards and the first provider cells. Facts from docs/ and schema.py."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KNOW = ROOT / "ai-agent" / "training" / "knowledge"
CARDS = KNOW / "cards" / "resource"
JSONL = KNOW / "cards.jsonl"

PAGES: list[dict] = []


def add(cid: str, title: str, tags: list[str], providers: list[str], sources: list[str], text: str) -> None:
    PAGES.append(
        {
            "id": cid,
            "kind": "resource",
            "title": title,
            "tags": tags,
            "providers": providers,
            "text": text.strip() + "\n",
            "sources": sources,
        }
    )


add(
    "res-type-storage",
    "Resource: storage",
    ["resource", "storage", "bucket"],
    ["aws", "azure", "gcp", "alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean", "cloudflare", "onprem"],
    [
        "docs/resources.md#provider-support",
        "docs/resources.md#what-handlers-receive",
        "docs/events.md#storage",
        "docs/resource-usage.md#queues-buckets-and-topics",
        "docs/resource-guides/README.md#adding-resources-step-by-step-guides",
    ],
    """
# Resource: storage

A storage resource is a bucket or container of files. Use it when a file arriving should run a function, or when a handler reads and writes objects. An HTTP function can accept a request and a second function can process the object.

The guide index names the native service on each cloud: Amazon S3, an Azure Blob container, a Cloud Storage bucket, Alibaba Cloud OSS, Tencent Cloud COS, Huawei OBS, OCI Object Storage, IBM Cloud Object Storage, DigitalOcean Spaces, Cloudflare R2, and an on-premises directory or S3-compatible store.

`type: storage` may be managed. AWS, GCP, Azure, and on premises can keep a standalone managed bucket with no event. On Alibaba, Tencent, Huawei, Oracle, IBM, DigitalOcean, and Cloudflare, a managed storage resource is valid where a storage event uses it. Elsewhere set `external: true`. An external resource already exists. pskit passes its details and leaves the bucket in place.

Put it under `resources` with `type: storage`. `name` is the native bucket name. It defaults to the key, or to the last `:` segment of `connection.arn`. `functions` chooses who receives the binding. With the list omitted, every user function receives it. List a generated `<workflow>-orchestrator` when that function needs the binding. `connection` holds scalars. A `*_env` value is the name of a variable, and the handler reads `ctx.env` for the secret.

A storage event can point at the resource. The event uses the resource's native name, and `existing` follows `external`. The events table marks storage on AWS S3, GCP Cloud Storage, Azure Blob (created only), Alibaba OSS, Oracle Object Storage, Tencent COS, Huawei OBS, and an on-premises directory. Each record has `bucket`, `key`, `size`, and `action` (`created` or `deleted`).

`resource("uploads")` returns `native_name`, `external`, and connection values. The process also gets `PSKIT_RESOURCE_UPLOADS_TYPE`, `_NAME`, `_EXTERNAL`, one variable per connection key, and `_ARN`, `_URL`, or `_ID` when the provider knows them. AWS adds `ARN` for storage. Publishing uses `boto3` or `@aws-sdk/client-s3` on AWS, `google-cloud-storage` on GCP, and `azure-storage-blob` on Azure. Several other clouds use the S3 API with that cloud's endpoint and HMAC keys. On premises, `put_object` in `py_serverless_kit.runtime.onprem_host` writes through the host and follows the storage driver.

Open the form on its own line:

Resources > + Add resource

The guide and the tester are:

Resources > How to use

Resources > Test

```
pskit resources usage uploads -p aws -s dev
pskit invoke -f on-upload -t storage -d '{"bucket": "uploads", "key": "in/a.txt"}'
pskit resources send uploads -d '{"key": "in/a.txt", "content": "test"}'
pskit logs -f --function on-upload
```

`pskit resources check uploads` checks that the resource is reachable. Azure storage events are created or updated blobs. A `deleted` list fails validation. Tencent COS names use the form `<name>-<APPID>`. On AWS, the bucket notification pskit writes replaces other notifications on that bucket.

Sources: `docs/resources.md#provider-support`, `docs/events.md#storage`, `docs/resource-usage.md#queues-buckets-and-topics`, `docs/resource-guides/README.md#adding-resources-step-by-step-guides`
""",
)

add(
    "res-type-queue",
    "Resource: queue",
    ["resource", "queue"],
    ["aws", "azure", "gcp", "alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean", "cloudflare", "onprem"],
    [
        "docs/resources.md#provider-support",
        "docs/events.md#queue",
        "docs/resource-usage.md#queues-buckets-and-topics",
        "docs/resource-guides/README.md#adding-resources-step-by-step-guides",
        "docs/handlers.md#batchresult",
    ],
    """
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
""",
)

add(
    "res-type-topic",
    "Resource: topic",
    ["resource", "topic"],
    ["aws", "azure", "gcp", "alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean", "cloudflare", "onprem"],
    [
        "docs/events.md#topic",
        "docs/resources.md#provider-support",
        "docs/resources.md#aws-iam",
        "docs/resource-usage.md#queues-buckets-and-topics",
        "docs/resource-guides/README.md#adding-resources-step-by-step-guides",
    ],
    """
# Resource: topic

A topic resource fans one message out to every subscribed function. Use it for "order paid" style events: the publisher does not name the workers, and each subscriber gets a copy.

The guide index names the native service: Amazon SNS, an Azure Service Bus topic, a Pub/Sub topic, Alibaba SMQ / MNS, Tencent TDMQ for CMQ, Huawei SMN, OCI Notifications, IBM Event Streams, DigitalOcean Managed Kafka, and an on-premises file topic. The Cloudflare topic guide is the page of alternatives, because the events table leaves topic unmarked on Cloudflare.

`type: topic` may be managed. AWS, GCP, Azure, and on premises can keep a standalone managed topic. On the other clouds, a managed topic is valid where a topic event uses it. Elsewhere set `external: true`. Azure app settings belong to the whole Function App, so every function in that app sees every binding.

Declare `type: topic` under `resources`. A topic event can say `resource: order-events` and, where the provider applies it, `filter`. The events table marks topic on AWS SNS (filter policy), GCP Pub/Sub (filter left to the handler, with a warning), Azure Service Bus (filter left to the handler; an existing topic needs `options.servicebus_namespace_id` and `options.servicebus_connection`), Alibaba MNS (`filter.tag` as a string), Huawei SMN, and on-premises files (exact match on attributes, then on JSON body fields).

`resource("order-events").arn` is the publish target on AWS. The library table lists `boto3` or `@aws-sdk/client-sns` on AWS, `google-cloud-pubsub` on GCP, and `azure-servicebus` or `@azure/service-bus` on Azure. On premises, `submit_topic` publishes through the host. Topics there support the `builtin` and `directory` drivers. AWS adds `ARN` for a topic. GCP adds `ID` for a managed topic. The function also receives `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL`, and connection keys.

Open:

Resources > + Add resource

Resources > How to use

Resources > Test

```
pskit resources send order-events -d '{"message": {"id": 1}}'
pskit logs -f --function notify
pskit resources usage order-events -p aws -s dev
```

On AWS, each role pskit creates gets `sns:Publish` for the topics bound to its functions. A role set with `iam.role` is left unchanged, and the plan warns.

Sources: `docs/events.md#topic`, `docs/resources.md#provider-support`, `docs/resources.md#aws-iam`, `docs/resource-usage.md#queues-buckets-and-topics`
""",
)

add(
    "res-type-database",
    "Resource: database",
    ["resource", "database"],
    ["aws", "azure", "gcp", "alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean", "cloudflare", "onprem"],
    [
        "docs/resources.md#fields",
        "docs/resources.md#provider-support",
        "docs/resource-usage.md#databases-caches-and-other-services",
        "docs/resource-guides/README.md#adding-resources-step-by-step-guides",
        "src/py_serverless_kit/config/schema.py",
    ],
    """
# Resource: database

A database resource is a SQL or document store the functions query. Use it for orders, users, and any data that must stay after the invocation ends. pskit passes connection details. It leaves the database itself in place.

The schema requires `external: true` for `type: database`. A managed database is rejected with the message that pskit does not create that type. The guide index names Amazon RDS / Aurora, Azure PostgreSQL / MySQL / SQL, Cloud SQL, Alibaba ApsaraDB RDS / PolarDB, TencentDB, Huawei RDS, OCI Autonomous DB or MySQL HeatWave, IBM Databases for PostgreSQL / MySQL, DigitalOcean managed databases, Cloudflare D1 / Hyperdrive, and on-premises PostgreSQL / MySQL.

Declare `type: database`, `external: true`, and a `connection` map of scalars: `host`, `port`, `database`, `user`, and `password_env`. `password_env` is the name of a variable. Put the secret in `${env:ORDERS_DB_PASSWORD}` on the provider environment, or in the on-prem `env_file`. `functions` limits the binding. With the list omitted, every user function receives `PSKIT_RESOURCE_ORDERS_DB_*` for a key `orders-db`.

There is no database event. Call the database from an HTTP, queue, or schedule handler. The library table lists `psycopg[binary]` and `pg` for PostgreSQL, `pymysql` and `mysql2` for MySQL or MariaDB, and `pymongo` and `mongodb` for MongoDB. Read the password with `ctx.env[db["password_env"]]` in Python and `process.env[r.get("password_env")]` in Node.js. `resource("orders-db")["host"]` is the host string.

Open:

Resources > + Add resource

Resources > How to use

Resources > Test

The tester shows the variables and a snippet for a database. It sends messages for queues, buckets, and topics.

```
pskit resources usage orders-db -p aws -s dev
pskit resources send --list
pskit trigger -f api -e 0
```

On premises, a one-click database is still `type: database` with `external: true`, created with the on-prem service form. Cloud databases often sit on a private network. The function must be able to open that network, which each cloud guide describes.

Sources: `docs/resources.md#fields`, `docs/resource-usage.md#databases-caches-and-other-services`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "res-type-cache",
    "Resource: cache",
    ["resource", "cache"],
    ["aws", "azure", "gcp", "alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean", "cloudflare", "onprem"],
    [
        "docs/resources.md#fields",
        "docs/resources.md#provider-support",
        "docs/resource-usage.md#databases-caches-and-other-services",
        "docs/resource-guides/README.md#adding-resources-step-by-step-guides",
        "src/py_serverless_kit/config/schema.py",
    ],
    """
# Resource: cache

A cache resource is a fast key-value store in front of a database or a slow API. Use it for session data, counters, and results you can rebuild. pskit passes the connection. It leaves the cache in place.

The schema requires `external: true` for `type: cache`. The guide index names Amazon ElastiCache / MemoryDB, Azure Redis, Memorystore, Alibaba Tair (Redis), TencentDB for Redis, Huawei DCS, OCI Cache, IBM Databases for Redis, DigitalOcean Managed Valkey, Cloudflare Workers KV, and on-premises Redis / Valkey.

Declare `type: cache`, `external: true`, and `connection` scalars such as `host`, `port`, and `ssl`. A password is `password_env` naming a variable, with the value supplied by `${env:NAME}` or the on-prem env file. Booleans in `connection` arrive as the strings `true` and `false`. `functions` limits who sees `PSKIT_RESOURCE_<KEY>_*`.

There is no cache trigger. A handler calls the client with `resource("cache")`. The library table lists `redis` and `ioredis` for Redis or Valkey, and `pymemcache` and `memjs` for Memcached. Workers KV is the Cloudflare cache guide's service, and that guide is the place for its client. On premises, a one-click Redis, Valkey, Dragonfly, or KeyDB service can fill this resource.

Open:

Resources > + Add resource

Resources > How to use

Resources > Test

```
pskit resources usage cache -p aws -s dev
pskit resources send --list
pskit trigger -f api -e 0
```

Managed caches on AWS, GCP, and Azure are reached from inside their network. The function options for that network are in each cloud's cache guide. `pskit resources check` reports whether the resource is reachable.

Sources: `docs/resources.md#fields`, `docs/resource-usage.md#databases-caches-and-other-services`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "res-type-custom",
    "Resource: custom",
    ["resource", "custom"],
    ["aws", "azure", "gcp", "alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean", "cloudflare", "onprem"],
    [
        "docs/resources.md#fields",
        "docs/resources.md#provider-support",
        "docs/resource-usage.md#the-five-steps-for-any-resource",
        "docs/resource-guides/README.md#adding-resources-step-by-step-guides",
        "src/py_serverless_kit/config/schema.py",
    ],
    """
# Resource: custom

A custom resource is any service that is not a bucket, queue, topic, database, or cache. Use it for DynamoDB, a secret store, an internal HTTP API, or a vendor endpoint. pskit passes the details you write. It leaves the service in place.

The schema requires `external: true` for `type: custom`. The guide index points at DynamoDB and Secrets Manager on AWS, Cosmos DB and Key Vault on Azure, Firestore and Secret Manager on GCP, and the matching "other services" page on every other cloud. On premises the custom page covers SMTP, LDAP, and internal APIs. Secret managers are also on-prem services read with `get_secret()`. `secrets` is not a `type` in `RESOURCE_TYPES`.

Declare `type: custom`, `external: true`, a `name` when the service has one, and `connection` scalars. Reserved connection keys are `type`, `name`, and `external`. Keys start with a letter and use letters, digits, or `_`. Nested maps and lists are rejected. Put secrets in `*_env` or in `${env:NAME}`. `functions` limits the binding.

There is no custom event. The handler calls the service SDK with `resource("orders-table").native_name` or a connection field such as `secret_arn`. pskit grants no portable IAM policy for custom resources. On AWS, add `provider.iam.statements` yourself. A role you bring with `iam.role` is also left unchanged, and the plan warns.

Open:

Resources > + Add resource

Resources > How to use

Resources > Test

```
pskit resources usage orders-table -p aws -s dev
pskit resources send --list
pskit validate
```

The testing checklist lists `pskit resources send --list` as every resource at once. The AWS custom guide says that command prints the variables and a snippet. `pskit invoke` and `pskit dev` inject the same variables locally.

Sources: `docs/resources.md#fields`, `docs/resources.md#provider-support`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "res-type-smtp",
    "Resource: smtp",
    ["resource", "smtp", "onprem"],
    ["onprem"],
    [
        "docs/events.md#events-triggers",
        "docs/smtp/README.md#create-it",
        "docs/smtp/README.md#what-the-handler-receives",
        "docs/resources.md#on-premises-drivers",
        "src/py_serverless_kit/config/schema.py",
        "ai-agent/training/knowledge/conflicts.md",
    ],
    """
# Resource: smtp

An smtp resource is the on-premises SMTP server that receives mail for your domains and runs functions. Use it when a message to `inbox@inbound.example.com` should start a handler. The events table marks smtp on on premises only.

`RESOURCE_TYPES` includes `smtp`, and `EVENT_RESOURCE_TYPES` includes it, so the schema allows the resource with `external` false or true. The Fields table in `docs/resources.md#fields` lists six types and omits smtp. The code wins. The create guide's example sets `external: true` and stores `host`, `port`, `domains`, and `hostname` in `connection`.

The server is a Node.js container from the on-prem catalog (`smtp`, port 25). It accepts mail for the domains you list and their subdomains, and it posts each message to the pskit host. It is receive-only. It is not an open relay.

In the studio, open:

Resources > + SMTP server

The form asks for a resource key, domains such as `inbound.example.com`, where it runs, port 25, and the functions to trigger. The same server is:

```
pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --attach on-mail --ssh deploy@203.0.113.10
```

The guide prints that command with a different SSH login. This card uses `deploy`. `203.0.113.10` is a documentation address. `--attach` adds the smtp trigger on that function. Deploy so the host learns the trigger.

The event is `smtp: {resource: inbound-mail}`, or the shorthand `smtp: inbound-mail`. `event.type` is `smtp`. `event.data` holds from, to, cc, subject, text, html, headers, and attachments. The same mail is also an Amazon SES-shaped object at `Records[0].ses`.

DNS is an A record for the mail host and an MX record for the domain. Open:

Resources > DNS guide

Keep the root MX when Microsoft 365 or Google Workspace already receives company mail, and use a subdomain. Allow inbound TCP 25. The largest mail defaults to 25 MB.

```
pskit resources onprem usage inbound-mail
pskit invoke -f on-mail -t smtp
```

Sources: `docs/smtp/README.md#create-it`, `docs/events.md#events-triggers`, `docs/resources.md#on-premises-drivers`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "res-aws-storage",
    "Resource: AWS S3 bucket",
    ["resource", "storage", "aws"],
    ["aws"],
    [
        "docs/resource-guides/aws/storage.md#amazon-s3-bucket-type-storage",
        "docs/resource-guides/aws/storage.md#3-declare-it-in-pskityml",
        "docs/resource-guides/aws/storage.md#5-test",
        "docs/resources.md#aws-iam",
    ],
    """
# Resource: AWS S3 bucket

On AWS, `type: storage` is an Amazon S3 bucket. Use an existing bucket when objects should start a function, or when a handler reads and writes objects. A managed bucket is also allowed on AWS, including a standalone bucket with no event. The guide walks through a bucket you already created.

Create it in S3 in the same region as `provider.region`. Names are globally unique, 3–63 characters, lowercase letters, digits, `.`, and `-`. Leave Block all public access on. Collect the bucket name, the region, and the bucket ARN. For SSE-KMS, collect the key ARN.

Declare `type: storage`, `external: true`, and `name` set to the bucket name. A storage event can set `resource`, `prefix`, `suffix`, and `events: [created]`. pskit looks the bucket up with `data.aws_s3_bucket`, allows S3 to invoke the function, writes `aws_s3_bucket_notification`, adds `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, and `s3:ListBucket` on the bucket and `/*` to the role of bound functions, and sets `PSKIT_RESOURCE_<KEY>_ARN`. Drop the event when the function only reads and writes. The binding still grants those S3 actions.

S3 keeps one notification configuration per bucket. The configuration pskit writes replaces notifications already on the bucket, and `pskit remove` deletes that configuration. When the bucket already notifies another stack, bind it with no storage event, or trigger from the queue or topic that already receives those notifications.

`boto3` is in the Lambda Python runtime. Add it to `requirements.txt` to pin a version. Node.js uses `@aws-sdk/client-s3`. Call `get_object` with `Bucket=resource("invoices").native_name` and `Key=record.key`. SSE-KMS needs `kms:Decrypt` and `kms:GenerateDataKey` in `provider.iam.statements`. A role you set with `iam.role` is left unchanged.

Open:

Resources > + Add resource

Resources > Browse account

```
pskit validate
pskit resources send invoices -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -f --function on-invoice
```

A deploy error `couldn't find resource` means the name is wrong or the bucket is in another account.

Sources: `docs/resource-guides/aws/storage.md#amazon-s3-bucket-type-storage`, `docs/resources.md#aws-iam`
""",
)

add(
    "res-aws-queue",
    "Resource: AWS SQS queue",
    ["resource", "queue", "aws"],
    ["aws"],
    [
        "docs/resource-guides/aws/queue.md#amazon-sqs-queue-type-queue",
        "docs/resource-guides/aws/queue.md#3-declare-it-in-pskityml",
        "docs/resource-guides/aws/queue.md#5-test",
        "docs/events.md#queue",
        "docs/resources.md#aws-iam",
    ],
    """
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
""",
)

add(
    "res-aws-topic",
    "Resource: AWS SNS topic",
    ["resource", "topic", "aws"],
    ["aws"],
    [
        "docs/resource-guides/aws/topic.md#amazon-sns-topic-type-topic",
        "docs/resource-guides/aws/topic.md#3-declare-it-in-pskityml",
        "docs/resource-guides/aws/topic.md#5-test",
        "docs/events.md#topic",
        "docs/resources.md#aws-iam",
    ],
    """
# Resource: AWS SNS topic

On AWS, `type: topic` is an Amazon SNS topic. Use it to publish one event and run every subscribed function. AWS can also create a managed topic. The guide is the path for a topic that already exists.

Create a Standard topic. The guide says Lambda subscriptions need a Standard topic. Collect the topic name and the topic ARN. Declare `type: topic`, `external: true`, and `name`. A subscriber event can set `resource` and `filter`, for example `filter: {type: [paid]}`. pskit looks the topic up with `data.aws_sns_topic`, creates a Lambda subscription with that filter policy, allows SNS to invoke the function, adds `sns:Publish` on the topic to the role of bound functions, and sets `PSKIT_RESOURCE_<KEY>_ARN`. `pskit remove` deletes the subscription and leaves the topic.

The filter policy matches message attributes. Publish with `boto3` and `TopicArn=resource("order-events").arn`, and set `MessageAttributes` so the filter can match. Node.js uses `@aws-sdk/client-sns`. The subscriber reads `event.records`, including `record.body` and `record.attributes`. A customer-managed KMS key needs `kms:GenerateDataKey` and `kms:Decrypt` on that key for publishers.

Open:

Resources > + Add resource

Resources > Browse account

```
pskit validate
pskit resources send order-events -d '{"message": {"id": 1}, "attributes": {"type": "paid"}}'
pskit logs -f --function notify
```

The console path is the topic, Publish message, a message attribute `type` = `paid`, then Publish message. The Subscriptions tab lists the Lambda subscription pskit added.

Sources: `docs/resource-guides/aws/topic.md#amazon-sns-topic-type-topic`, `docs/events.md#topic`, `docs/resources.md#aws-iam`
""",
)

add(
    "res-aws-database",
    "Resource: AWS RDS or Aurora",
    ["resource", "database", "aws"],
    ["aws"],
    [
        "docs/resource-guides/aws/database.md#amazon-rds-aurora-type-database",
        "docs/resource-guides/aws/database.md#networking-first",
        "docs/resource-guides/aws/database.md#4-use-it-in-a-handler",
        "docs/resource-guides/aws/database.md#5-test",
        "docs/resource-usage.md#databases-caches-and-other-services",
    ],
    """
# Resource: AWS RDS or Aurora

On AWS, `type: database` is Amazon RDS or Aurora (PostgreSQL, MySQL, or Aurora PostgreSQL/MySQL). pskit requires `external: true` and passes host, port, database, user, and the name of the password variable. It leaves the database in place.

RDS lives in a VPC. pskit deploys Lambda outside any VPC unless the function sets `options.vpc_config` (`subnet_ids` and `security_group_ids`), which is merged into `aws_lambda_function`. For a private database, put the function in the VPC, add the ENI actions the guide lists (`ec2:CreateNetworkInterface`, `DescribeNetworkInterfaces`, `DescribeSubnets`, `DeleteNetworkInterface`, `AssignPrivateIpAddresses`, `UnassignPrivateIpAddresses`) under `provider.iam.statements`, and allow that security group on the database security group inbound rule for 5432 or 3306. A function in a VPC reaches other AWS APIs when the subnets have a NAT gateway or VPC endpoints. A publicly accessible database is described in the guide as a quick test, with a wide inbound rule, because the Lambda has no fixed IP.

Collect the endpoint (Aurora: the writer endpoint), port, DB name, master username, and either the password or the Secrets Manager credentials ARN. Store the password as `ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}` and set `connection.password_env` to that name. `sslmode: require` is in the guide's connection map. `functions` can list only the handlers that should see the binding.

`requirements.txt` gets `psycopg[binary]` for PostgreSQL or `pymysql` for MySQL. Connect with `host`, `port`, `dbname`, `user`, and `password=ctx.env[db["password_env"]]`. Many concurrent Lambdas can exhaust connections. RDS Proxy pools them. Use the proxy endpoint as `host`. A password in Secrets Manager uses `secret_arn` plus `secretsmanager:GetSecretValue`, and the function still needs a path to Secrets Manager.

Open:

Resources > + Add resource

Resources > How to use

```
pskit validate
pskit trigger -f api -e 0
pskit resources send --list
```

`pskit resources send --list` prints the variables and a snippet. It sends messages for queues, buckets, and topics.

Sources: `docs/resource-guides/aws/database.md#amazon-rds-aurora-type-database`, `docs/resource-guides/aws/database.md#networking-first`
""",
)

add(
    "res-aws-cache",
    "Resource: AWS ElastiCache or MemoryDB",
    ["resource", "cache", "aws"],
    ["aws"],
    [
        "docs/resource-guides/aws/cache.md#amazon-elasticache-memorydb-type-cache",
        "docs/resource-guides/aws/cache.md#3-declare-it-in-pskityml",
        "docs/resource-guides/aws/cache.md#4-use-it-in-a-handler",
        "docs/resource-guides/aws/cache.md#5-test",
    ],
    """
# Resource: AWS ElastiCache or MemoryDB

On AWS, `type: cache` is Redis OSS or Valkey on ElastiCache (serverless or node-based) or MemoryDB. The schema requires `external: true`. pskit passes the endpoint and leaves the cache in place.

ElastiCache and MemoryDB are reachable from inside their VPC. A function that uses the cache sets `options.vpc_config` with subnet ids and a security group. The same ENI actions as the database guide go under `provider.iam.statements`. Allow custom TCP 6379 from that security group on the cache security group.

Collect the endpoint (serverless Endpoint, or Primary / Configuration endpoint for cluster mode), the port (6379 in the guide), and whether encryption in transit is on. Serverless requires encryption in transit. An optional user-group password is `password_env`, with `CACHE_PASSWORD: ${env:CACHE_PASSWORD}` on the provider environment.

`requirements.txt` gets `redis`. Build the client once and reuse it across warm invocations. `ssl` is true when `resource("cache").get("ssl") == "true"`, because connection booleans arrive as `"true"` and `"false"`. Pass `password` only when `password_env` is set. A cluster-mode endpoint uses `redis.cluster.RedisCluster`.

Open:

Resources > + Add resource

Resources > How to use

```
pskit validate
pskit trigger -f api -e 0
pskit resources send --list
```

A timeout while connecting means `vpc_config` is missing, the subnets are wrong, or the security group rule is missing. `Connection reset by peer` with encryption in transit means the client should connect with TLS.

Sources: `docs/resource-guides/aws/cache.md#amazon-elasticache-memorydb-type-cache`, `docs/resource-guides/aws/cache.md#4-use-it-in-a-handler`
""",
)

add(
    "res-aws-custom",
    "Resource: other AWS services",
    ["resource", "custom", "aws"],
    ["aws"],
    [
        "docs/resource-guides/aws/custom.md#other-aws-services-type-custom",
        "docs/resource-guides/aws/custom.md#dynamodb",
        "docs/resource-guides/aws/custom.md#secrets-manager",
        "docs/resource-guides/aws/custom.md#test",
        "docs/resources.md#fields",
    ],
    """
# Resource: other AWS services

On AWS, `type: custom` is any service that is not a bucket, queue, topic, database, or cache. The guide names DynamoDB, Secrets Manager, Kinesis, EventBridge, Bedrock, and a third-party API. `external: true` is required. pskit passes `name` and `connection` and grants no IAM for the custom resource. Add `provider.iam.statements` yourself. Use `${tf:...}` only for resources you also define in `provider.terraform.extra`. For a console-created resource, paste the ARN.

DynamoDB: create a table, copy the table ARN from General information, set `name` to the table name and `connection.arn` to the ARN, and allow `dynamodb:GetItem`, `PutItem`, `UpdateItem`, and `Query` on that ARN. The handler uses `boto3.resource("dynamodb").Table(resource("orders-table").native_name)`.

Secrets Manager: store a secret, copy the secret ARN, and put it in `connection.secret_arn`. Allow `secretsmanager:GetSecretValue` on that ARN. The secret stays out of Terraform state. Read it once per container with `get_secret_value` and cache it in the module. A customer-managed KMS key also needs `kms:Decrypt` on that key. The same pattern fits any other service: non-secret values in `connection`, actions in `iam.statements`, secrets in Secrets Manager or a `*_env` variable.

Open:

Resources > + Add resource

Resources > How to use

```
pskit validate
pskit resources send --list
```

`pskit resources send --list` prints the `PSKIT_RESOURCE_*` variables and a snippet for every custom resource. There is no custom trigger.

Sources: `docs/resource-guides/aws/custom.md#other-aws-services-type-custom`, `docs/resource-guides/aws/custom.md#dynamodb`, `docs/resources.md#fields`
""",
)

add(
    "res-azure-storage",
    "Resource: Azure Blob container",
    ["resource", "storage", "azure"],
    ["azure"],
    [
        "docs/resource-guides/azure/storage.md#azure-blob-container-type-storage",
        "docs/resource-guides/azure/storage.md#3-declare-it-in-pskityml",
        "docs/resource-guides/azure/storage.md#5-test",
        "docs/events.md#storage",
        "docs/resource-usage.md#queues-buckets-and-topics",
    ],
    """
# Resource: Azure Blob container

On Azure, `type: storage` is a blob container in a storage account. Use it when an upload should run a function, or when a handler reads and writes blobs. Azure can also create a managed container. The guide is the path for a container that already exists.

Container names are 3–63 characters: lowercase letters, digits, and single dashes. Anonymous access in the guide is Private. Collect the container name, the storage account name, and a connection string or a SAS. Keep the connection string in an environment variable. The guide maps `INVOICES_STORAGE_CONN: ${env:INVOICES_STORAGE_CONN}` and sets `provider.options.storage_connection` to that app setting name so the blob trigger can connect. `connection` holds `account`, `url`, and `connection_string_env`.

A storage event names the resource and can set `prefix` and `suffix`. Azure blob triggers fire on created or updated blobs. `events: [deleted]` is a validation error. `storage_connection` is shared by every external queue and container of the service, so those triggers stay in one storage account. Another account is read with the SDK and `connection_string_env`, with no trigger.

`requirements.txt` gets `azure-storage-blob`. `BlobServiceClient.from_connection_string(ctx.env[invoices["connection_string_env"]])` opens the account, and `get_blob_client(native_name, record.key)` reads one blob. Node.js uses `@azure/storage-blob`.

Open:

Resources > + Add resource

Resources > Browse account

```
pskit validate
pskit resources send invoices -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -f --function on-invoice
```

The guide sets `AZURE_STORAGE_CONNECTION_STRING` from that same variable before `pskit resources send`. A missing `storage_connection`, or a value absent from `environment`, means the trigger never fires. On the Consumption plan the trigger polls, so a delay of minutes is described as normal. A container name that is not 3–63 lowercase fails validation.

Sources: `docs/resource-guides/azure/storage.md#azure-blob-container-type-storage`, `docs/events.md#storage`
""",
)

add(
    "res-gcp-storage",
    "Resource: GCP Cloud Storage bucket",
    ["resource", "storage", "gcp"],
    ["gcp"],
    [
        "docs/resource-guides/gcp/storage.md#cloud-storage-bucket-type-storage",
        "docs/resource-guides/gcp/storage.md#3-declare-it-in-pskityml",
        "docs/resource-guides/gcp/storage.md#4-use-it-in-a-handler",
        "docs/resource-guides/gcp/storage.md#5-test",
        "docs/events.md#storage",
    ],
    """
# Resource: GCP Cloud Storage bucket

On GCP, `type: storage` is a Cloud Storage bucket. Use it when an object create or delete should run a function, or when a handler reads and writes objects. GCP can also create a managed bucket. The guide is the path for a bucket that already exists.

The bucket name is globally unique and lowercase. Location type Region must be the same region as `provider.region`. pskit creates the Eventarc trigger in `provider.region`, and a Cloud Storage trigger must be in the bucket's location, so a dual-region or multi-region bucket cannot trigger a pskit function. The guide's provider example sets `options.project` and `options.service_account`.

Declare `type: storage`, `external: true`, and `name`. A storage event can set `resource`, `prefix`, `suffix`, and `events: [created]`. pskit deploys the function with an Eventarc trigger filtered on the bucket (`google.cloud.storage.object.v1.finalized`). `deleted` events get a second Cloud Function. pskit grants the project's Cloud Storage service agent `roles/pubsub.publisher` and pskit's invoker service account `roles/eventarc.eventReceiver`. `prefix` and `suffix` are applied by the pskit runtime, so the function is still invoked for other objects and returns immediately.

Grant the runtime service account access on the bucket: Storage Object User for read and write, or Storage Object Viewer for read-only. `requirements.txt` gets `google-cloud-storage`. `storage.Client().bucket(resource("invoices").native_name).blob(record.key).download_as_bytes()` reads the object. Node.js uses `@google-cloud/storage`. Each record has `key`, `size`, and `action`.

Open:

Resources > + Add resource

Resources > Browse account

```
pskit validate
pskit resources send invoices -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -f --function on-invoice
```

Sources: `docs/resource-guides/gcp/storage.md#cloud-storage-bucket-type-storage`, `docs/events.md#storage`
""",
)


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def main() -> None:
    CARDS.mkdir(parents=True, exist_ok=True)
    rows = []
    if JSONL.is_file():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    by_id = {row["id"]: row for row in rows}
    bad = []
    for page in PAGES:
        n = words(page["text"])
        print(f"{page['id']} {n}")
        if n < 150 or n > 500:
            bad.append(f"{page['id']} has {n} words")
    if bad:
        raise SystemExit("\n".join(bad))
    for page in PAGES:
        path = CARDS / f"{page['id']}.md"
        path.write_bytes(page["text"].encode("utf-8"))
        by_id[page["id"]] = page
    ordered = [by_id[key] for key in sorted(by_id)]
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered)
    JSONL.write_bytes(payload.encode("utf-8"))
    print(f"jsonl={len(ordered)} resources={len(PAGES)}")


if __name__ == "__main__":
    main()
