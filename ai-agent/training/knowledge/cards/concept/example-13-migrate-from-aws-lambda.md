# Example: 13-migrate-from-aws-lambda

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md. Comments in pskit.yml: AFTER: replaces before/template.yaml AND before/state_machine.asl.json. step 2: switch clouds by adding a block and running `pskit deploy --provider gcp`
# 13 · Migrating AWS Lambda + Step Functions to any cloud `before/` is a typical

AWS-only service: Lambda handlers that parse API Gateway / SQS events by hand, a SAM template and a hand-written ASL state machine. `after/` is the same service on py-serverless-kit. It deploys to AWS first, unchanged in behaviour, and then to GCP, Azure or any other supported cloud by changing the provider.
## Step 1 · Inventory what you have For every Lambda, list its trigger (API Gateway route,

SQS, S3, SNS, schedule, Step Functions task, direct invoke) and the AWS APIs it calls. Each trigger maps 1:1 to a pskit event: | AWS | pskit.yml | | --- | --- | | API Gateway `POST /orders` | `- http: POST /orders` | | SQS event source mapping | `- queue: {name: ..., batch_size: 10}` | | S3 notification | `- storage: {bucket: ..., events: [created], prefix: ...}` | | SNS subscription | `- topic: name` | | EventBridge schedule | `- schedule: "0 9 * * *"` or `- schedule: 5 minutes` | | Step Functions task | a function without events + a `workflows:` task state | | `lambda.invoke(...)` | `invoke("function-name", payload)` |
## Step 2 · Strip the event plumbing out of the handlers | Before | After | |

| --- | | `json.loads(base64...(event["body"]))` | `event.http.json()` | | `event["pathParameters"]["id"]` | `event.http.path_params["id"]` | | `event["queryStringParameters"]` | `event.http.query` | | `return {"statusCode": 400, "body": json.dumps(...)}` | `raise BadRequest(...)` | | `return {"statusCode": 202, "body": ...}` | `return data, 202` or `Response.json(data, 202)` | | `for r in event["Records"]: json.loads(r["body"])` | `for r in event.records: r.json()` | | `{"batchItemFailures": [...]}` | `BatchResult().fail(record)` | | task Lambda `event` (raw state) | `event.data` | | `context.aws_request_id` | `ctx.request_id` | | `print(...)` | `ctx.logger.info(..., extra={...})` | Business logic stays where it was. Diff `before/lambda_function.py` against `after/app/orders.py` to see how little changes.
