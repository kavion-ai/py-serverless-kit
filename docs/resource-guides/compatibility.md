# Existing cloud code with pskit

You already have code that calls a Lambda by ARN, sends to SQS with boto3, writes to S3, Azure Blob or Cloud
Storage, or calls a function URL. This page shows what keeps working on each provider, what to change (usually one
line), and the pskit way that runs everywhere.

| Your code | On AWS | On premises (`provider: onprem`) | Other clouds |
|---|---|---|---|
| `invoke("billing")` (pskit) | Lambda Invoke | in-process call | HTTP to the function URL (`PSKIT_ENDPOINT_<NAME>`) |
| `invoke("arn:aws:lambda:...:function:shop-dev-billing")` | works | works (the ARN maps to `billing`) | works |
| boto3 / AWS SDK `lambda.invoke(FunctionName=name or ARN)` | unchanged | set `endpoint_url` to the host: it speaks the Lambda Invoke API | call the function's HTTP URL instead |
| boto3 / AWS SDK SQS (`send_message`, `receive_message`, ...) | unchanged | set `endpoint_url` to the host: it speaks the SQS API for its queues | use the provider's queue SDK, or an SQS driver to real SQS |
| S3 SDK code | unchanged | one-click **RustFS**, **MinIO** or **LocalStack** + `endpoint_url` | S3-compatible stores: provider endpoint + HMAC keys |
| Azure Blob / Queue SDK code | (Azure) unchanged | one-click **Azurite** + its connection string | |
| Cloud Storage SDK code | (GCP) unchanged | one-click **fake-gcs-server** + `STORAGE_EMULATOR_HOST` | |
| A function's HTTP URL (API Gateway, Cloud Functions, Azure) | unchanged | same paths on the host URL (`pskit info`); Azure's `/api` prefix is not added | `pskit info` shows each URL |
| A pskit function from a script | `pskit trigger`, the AWS CLI | `PskitClient(host).invoke("billing", data)` or the Lambda API | its HTTP URL |

## Calling functions

### The pskit way (every provider)

```python
from py_serverless_kit import invoke

result = invoke("billing", {"order_id": 1})                    # pskit name
result = invoke("shop-dev-billing", {"order_id": 1})           # deployed name
result = invoke("arn:aws:lambda:eu-west-1:123456789012:function:shop-dev-billing", {"order_id": 1})
invoke("billing", {"order_id": 1}, asynchronous=True)           # fire and forget
```

```js
const { invoke } = require("pskit");
const result = await invoke("billing", { orderId: 1 });
```

Names, deployed names (`<service>-<stage>-<function>`) and Lambda ARNs (with or without an alias) all resolve to the
function of this service, so code copied from a Lambda project keeps working on every provider.

### Existing boto3 / AWS SDK Lambda code, on premises

The on-prem host serves the **Lambda Invoke API** (`POST /2015-03-31/functions/<name or ARN>/invocations`). Point
the client at the host; nothing else changes:

```python
import json
import os

import boto3

lam = boto3.client(
    "lambda",
    endpoint_url=os.environ.get("PSKIT_HOST", "http://10.0.0.5:8080"),
    region_name="eu-west-1",                         # any value
    aws_access_key_id=os.environ.get("PSKIT_ADMIN_TOKEN", "pskit"),   # the host's admin_token, if it sets one
    aws_secret_access_key="unused",
)
out = lam.invoke(FunctionName="arn:aws:lambda:eu-west-1:123456789012:function:shop-dev-billing",
                 Payload=json.dumps({"order_id": 1}))
if out.get("FunctionError"):                         # a handler exception, as on Lambda
    raise RuntimeError(json.loads(out["Payload"].read())["errorMessage"])
print(json.loads(out["Payload"].read()))

lam.invoke(FunctionName="billing", InvocationType="Event", Payload=b"{}")   # asynchronous: 202
```

```js
const { LambdaClient, InvokeCommand } = require("@aws-sdk/client-lambda");

const lambda = new LambdaClient({
  endpoint: process.env.PSKIT_HOST || "http://10.0.0.5:8080",
  region: "eu-west-1",
  credentials: { accessKeyId: process.env.PSKIT_ADMIN_TOKEN || "pskit", secretAccessKey: "unused" },
});
const out = await lambda.send(new InvokeCommand({ FunctionName: "shop-dev-billing", Payload: JSON.stringify({ orderId: 1 }) }));
console.log(JSON.parse(Buffer.from(out.Payload).toString()));
```

Supported: `RequestResponse` (default), `Event` (asynchronous, 202) and `DryRun`; handler errors come back as
`FunctionError: Unhandled` with `errorMessage` / `errorType`. Function URLs, aliases and versions are not separate
things on premises: the qualifier is ignored.

The AWS CLI works too:

```bash
aws lambda invoke --endpoint-url http://10.0.0.5:8080 --function-name shop-dev-billing \
  --cli-binary-format raw-in-base64-out --payload '{"order_id": 1}' out.json && cat out.json
```

## Queues

### Existing SQS code, on premises

The host serves the **SQS API** (JSON protocol) for its queues: `SendMessage`, `SendMessageBatch`, `ReceiveMessage`
(with `WaitTimeSeconds` long polling), `DeleteMessage`, `DeleteMessageBatch`, `ChangeMessageVisibility`,
`GetQueueUrl`, `GetQueueAttributes`, `ListQueues`, `CreateQueue` and `PurgeQueue`. Queue URLs look like
`http://host:8080/000000000000/<queue>`, and inside functions `resource("jobs").url` is that URL, exactly like on AWS:

```python
import os

import boto3
from py_serverless_kit import resource

sqs = boto3.client("sqs", endpoint_url=os.environ["PSKIT_ENDPOINT"], region_name="us-east-1",
                   aws_access_key_id="pskit", aws_secret_access_key="pskit")


def api(event, ctx):
    sqs.send_message(QueueUrl=resource("jobs").url, MessageBody=event.http.text())   # same line as on AWS
    return {"queued": True}
```

Sending works for every queue driver (the host forwards to Redis, Kafka, SQS, ...). Receiving through this API needs
a built-in queue; driver-backed queues are consumed by pskit triggers or with the service's own client.

### Other clouds' queue SDKs

| Your code uses | On premises |
|---|---|
| Azure Storage queues (`azure-storage-queue`, `@azure/storage-queue`) | one-click **Azurite**: the same SDK with its connection string, and the `azure_queue` driver for triggers |
| Amazon SQS against AWS | the `sqs` driver: the host consumes the real queue; your code keeps calling AWS |
| SQS without AWS | one-click **LocalStack** or **ElasticMQ** + `endpoint_url` |
| Pub/Sub | the `pubsub` driver against Google Cloud |
| RabbitMQ / AMQP | one-click **RabbitMQ** or **LavinMQ**: `pika` / `amqplib` unchanged |
| Kafka | one-click **Kafka (Redpanda)** or **Apache Kafka**: `kafka-python` / `kafkajs` unchanged |
| Redis lists / streams | one-click **Redis**, **Valkey**, **KeyDB** or **Dragonfly** |

## Buckets

| Your code uses | On premises |
|---|---|
| S3 (`boto3`, `@aws-sdk/client-s3`, AWS CLI) | one-click **RustFS**, **MinIO** or **LocalStack**; add `endpoint_url` (path-style) and their keys |
| Azure Blob | one-click **Azurite** + connection string |
| Cloud Storage | one-click **fake-gcs-server**: `STORAGE_EMULATOR_HOST=http://host:4443` makes `google-cloud-storage` use it |
| Files on disk | the built-in bucket: a folder on the host, also reachable through the pskit client |

The host itself does not speak the S3 API; use one of the S3-compatible services above, or the pskit client.

## Names, ARNs and URLs in handlers

`resource("<key>")` gives the values your code needs, whatever the provider:

| Value | AWS | On premises | Others |
|---|---|---|---|
| `native_name` / `nativeName` | queue / bucket / topic name | same | same |
| `arn` | the real ARN | | |
| `url` | SQS queue URL | SQS-compatible queue URL on the host | |
| `id` | | | GCP Pub/Sub topic id |
| `PSKIT_ENDPOINT` | | the host's URL | |

Code that needs an ARN on AWS and a URL elsewhere can branch on `ctx.provider`, or use the portable calls
(`invoke`, `submit_queue`, the pskit client) and skip the SDK entirely.

## Not compatible (and what to use)

| AWS API | Use instead |
|---|---|
| S3 API on the host | RustFS / MinIO / LocalStack, or the pskit client for built-in buckets |
| SNS | pskit topics: `submit_topic` / `client.topic(...).publish` |
| Step Functions | pskit workflows (`pskit workflow run`, `client.start_workflow`) |
| DynamoDB | a `database` resource (PostgreSQL, MongoDB, ...) or DynamoDB Local as a `custom` service |
| IAM policies | the host's `admin_token` (one token for the admin and AWS-compatible APIs) |

## Test it

```bash
pskit deploy -p onprem
aws lambda invoke --endpoint-url "$(pskit info --json -p onprem | python -c 'import json,sys; print(json.load(sys.stdin)["endpoint"])')" \
  --function-name billing --payload '{}' --cli-binary-format raw-in-base64-out out.json
aws sqs send-message --endpoint-url http://127.0.0.1:8080 --queue-url http://127.0.0.1:8080/000000000000/jobs --message-body hello
pskit logs -f
```
