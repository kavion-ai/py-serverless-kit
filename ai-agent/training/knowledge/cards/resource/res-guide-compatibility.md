# Existing cloud code with pskit

You already have code that calls a Lambda by ARN, sends to SQS with boto3, writes to S3, Azure Blob or Cloud Storage, or calls a function URL. This page shows what keeps working on each provider, what to change (usually one line), and the pskit way that runs everywhere. | Your code | On AWS | On premises (`provider: onprem`) | Other clouds | |---|---|---|---| | `invoke("billing")` (pskit) | Lambda Invoke | in-process call | HTTP to the function URL (`PSKIT_ENDPOINT_<NAME>`) | | `invoke("arn:aws:lambda:...:function:shop-dev-billing")` | works | works (the ARN maps to `billing`) | works | | boto3 / AWS SDK `lambda.invoke(FunctionName=name or ARN)` | unchanged | set `endpoint_url` to the host: it speaks the Lambda Invoke API | call the function's HTTP URL instead | | boto3 / AWS SDK SQS (`send_message`, `receive_message`, ...) | unchanged | set `endpoint_url` to the host: it speaks the SQS API for its queues | use the provider's queue SDK, or an SQS driver to real SQS | | S3 SDK code | unchanged | one-click **RustFS**, **MinIO** or **LocalStack** + `endpoint_url` | S3-compatible stores: provider endpoint + HMAC keys | | Azure Blob / Queue SDK code | (Azure) unchanged | one-click **Azurite** + its connection string | | | Cloud Storage SDK code | (GCP) unchanged | one-click **fake-gcs-server** + `STORAGE_EMULATOR_HOST` | | | A function's HTTP URL (API Gateway, Cloud Functions, Azure) | unchanged | same paths on the host URL (`pskit info`); Azure's `/api` prefix is not added | `pskit info` shows each URL | | A pskit function from a script | `pskit trigger`, the AWS CLI | `PskitClient(host).invoke("billing", data)` or the Lambda API | its HTTP URL |
### The pskit way (every provider) Names, deployed names

(`<service>-<stage>-<function>`) and Lambda ARNs (with or without an alias) all resolve to the function of this service, so code copied from a Lambda project keeps working on every provider.
### Existing boto3 / AWS SDK Lambda code, on premises The on-prem host serves the

**Lambda Invoke API** (`POST /2015-03-31/functions/<name or ARN>/invocations`). Point the client at the host; nothing else changes: Supported: `RequestResponse` (default), `Event` (asynchronous, 202) and `DryRun`; handler errors come back as `FunctionError: Unhandled` with `errorMessage` / `errorType`. Function URLs, aliases and versions are not separate things on premises: the qualifier is ignored.

```python
from py_serverless_kit import invoke

result = invoke("billing", {"order_id": 1})                    # pskit name
result = invoke("shop-dev-billing", {"order_id": 1})           # deployed name
result = invoke("arn:aws:lambda:eu-west-1:123456789012:function:shop-dev-billing", {"order_id": 1})
invoke("billing", {"order_id": 1}, asynchronous=True)           # fire and forget
```
