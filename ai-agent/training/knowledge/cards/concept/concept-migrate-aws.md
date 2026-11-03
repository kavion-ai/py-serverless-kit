# Migrating from AWS Lambda and Step Functions The goal is to move existing

Lambda functions (API Gateway, SQS, S3, SNS, EventBridge triggers) and Step Functions state machines to pskit once. After that, moving to another cloud means changing `provider.name`. The worked example with real before/after code is `examples/13-migrate-from-aws-lambda`: `before/` holds a raw Lambda, a SAM template and an ASL file, and `after/` holds the pskit version.
## Step 1: separate business logic from AWS event parsing

Typical Lambda code pskit version: | Lambda | pskit | |---|---| | `event["body"]` + `json.loads` / `isBase64Encoded` | `event.http.json()`, `event.http.body`, `event.http.text()` | | `event["pathParameters"]` | `event.http.path_params` | | `event["queryStringParameters"]` | `event.http.query` / `multi_query` | | `event["headers"]` (case varies) | `event.http.headers` (case-insensitive) | | `event["requestContext"]["http"]["method"]` | `event.http.method` | | `{"statusCode", "headers", "body"}` | return a dict/str, or `Response.json(...)`; raise `NotFound`, `BadRequest`, … | | `for r in event["Records"]` (SQS/SNS/S3) | `for r in event.records` → `r.body`, `r.json()`, `r.bucket`, `r.key`, `r.action` | | `{"batchItemFailures": [...]}` | return `BatchResult` | | `context.aws_request_id` / `get_remaining_time_in_millis()` | `ctx.request_id` / `ctx.remaining_time_ms()` | | `boto3.client("lambda").invoke(...)` | `invoke("other-fn", payload)` | | `print` / `logging` | `ctx.logger.info(..., extra={...})` (structured JSON) | Calls to other AWS services (DynamoDB, S3 SDK, …) stay as they are, but they tie that function to AWS. Put them behind a small interface of your own if you plan to move clouds.
## Step 2: translate the SAM / Serverless / CDK definition | SAM `Events` |

`pskit.yml` | |---|---| | `Type: HttpApi` / `Api`, `Path: /orders/{id}`, `Method: get` | `- http: GET /orders/{id}` | | `Type: Schedule`, `Schedule: rate(5 minutes)` | `- schedule: 5 minutes` | | `Schedule: cron(0 12 * * ? *)` | `- schedule: "0 12 * * *"` (standard 5-field cron) | | `Type: SQS`, `BatchSize: 10` | `- queue: {name: jobs, batch_size: 10, existing: true}` | | `Type: S3`, `Events: s3:ObjectCreated:*`, filter suffix | `- storage: {bucket: b, events: [created], suffix: .csv, existing: true}` | | `Type: SNS` | `- topic: {name: t, existing: true}` | | `Policies` / IAM statements | `iam.statements` (AWS) | | `MemorySize`, `Timeout`, `Runtime`, `Environment` | `memory`, `timeout`, `runtime`, `environment` | | Auth: JWT authorizer | `auth: jwt` + `authorizer: {issuer, audience}` | Use `existing: true` while existing queues, buckets and topics are still owned by your old stack.
## Step 3: translate

Step Functions Convert the ASL with the mapping table in workflows.md, then check it: Error names in `Retry`/`Catch` become your **Python exception class names**. `Parameters`/`ResultSelector`/intrinsic functions aren't supported: move that shaping into a small task function.

```python
def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}")
    order_id = event["pathParameters"]["id"]
    ...
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": json.dumps(result)}
```
