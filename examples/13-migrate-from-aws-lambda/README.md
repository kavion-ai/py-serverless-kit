# 13 · Migrating AWS Lambda + Step Functions to any cloud

`before/` is a typical AWS-only service: Lambda handlers that parse API Gateway / SQS
events by hand, a SAM template and a hand-written ASL state machine. `after/` is the same
service on py-serverless-kit. It deploys to AWS first, unchanged in behaviour, and then
to GCP, Azure or any other supported cloud by changing the provider.

```
before/                              after/
  lambda_function.py   ──────────►     app/orders.py      (business logic kept)
  template.yaml        ──┐
  state_machine.asl.json ┴─────────►   pskit.yml          (functions + triggers + workflow)
```

## Step 1 · Inventory what you have

For every Lambda, list its trigger (API Gateway route, SQS, S3, SNS, schedule,
Step Functions task, direct invoke) and the AWS APIs it calls. Each trigger maps 1:1 to a
pskit event:

| AWS | pskit.yml |
| --- | --- |
| API Gateway `POST /orders` | `- http: POST /orders` |
| SQS event source mapping | `- queue: {name: ..., batch_size: 10}` |
| S3 notification | `- storage: {bucket: ..., events: [created], prefix: ...}` |
| SNS subscription | `- topic: name` |
| EventBridge schedule | `- schedule: "0 9 * * *"` or `- schedule: 5 minutes` |
| Step Functions task | a function without events + a `workflows:` task state |
| `lambda.invoke(...)` | `invoke("function-name", payload)` |

## Step 2 · Strip the event plumbing out of the handlers

| Before | After |
| --- | --- |
| `json.loads(base64...(event["body"]))` | `event.http.json()` |
| `event["pathParameters"]["id"]` | `event.http.path_params["id"]` |
| `event["queryStringParameters"]` | `event.http.query` |
| `return {"statusCode": 400, "body": json.dumps(...)}` | `raise BadRequest(...)` |
| `return {"statusCode": 202, "body": ...}` | `return data, 202` or `Response.json(data, 202)` |
| `for r in event["Records"]: json.loads(r["body"])` | `for r in event.records: r.json()` |
| `{"batchItemFailures": [...]}` | `BatchResult().fail(record)` |
| task Lambda `event` (raw state) | `event.data` |
| `context.aws_request_id` | `ctx.request_id` |
| `print(...)` | `ctx.logger.info(..., extra={...})` |

Business logic stays where it was. Diff `before/lambda_function.py` against
`after/app/orders.py` to see how little changes.

## Step 3 · Translate the state machine

ASL maps directly to the `workflows:` block:

| ASL | pskit |
| --- | --- |
| `"Type": "Task", "Resource": "<lambda arn>"` | `type: task, function: <logical name>` |
| `"Choice"` + `NumericGreaterThan` | `type: choice`, `{variable: $.total, gt: 500, next: ...}` |
| `StringEquals`, `BooleanEquals`, `IsPresent`, `And`/`Or`/`Not` | `equals`, `is_present`, `and`/`or`/`not` |
| `"Wait"`, `"Pass"`, `"Parallel"`, `"Map"` | `wait`, `pass`, `parallel`, `map` |
| `"Retry"` / `"Catch"` with `ErrorEquals` | `retry` / `catch` with `errors` (`States.ALL` → `"*"`) |
| `ResultPath` / `InputPath` | `result_path` / `input_path` |
| `"Succeed"` / `"Fail"` | `succeed` / `fail` |

Check the result: `pskit workflow show order-processing --format asl` prints the ASL that
pskit generates. It should be equivalent to `before/state_machine.asl.json`, with ARNs
filled in automatically.

## Step 4 · Test locally

```bash
cd after
pskit invoke -f create-order -d '{"items": [{"qty": 2, "price": 300}]}'
pskit invoke -f email-worker -d '[{"to": "a@b.c"}, "broken"]'
pskit workflow run order-processing -i '{"items": [{"qty": 2, "price": 300}]}'
pskit workflow run order-processing -i '{"items": [{"qty": 0, "price": 1}]}'   # FAILED OrderRejected
```

## Step 5 · Redeploy to AWS first (no behaviour change)

```bash
pskit deploy           # Lambdas + HTTP API + SQS + Step Functions, via Terraform
```

Run your existing integration tests against the new endpoint. Then switch traffic over
(DNS / API mapping) and delete the old SAM stack.

## Step 6 · Move to the target cloud

```bash
pskit validate --provider gcp      # lists anything the target can't do
pskit deploy --provider gcp        # Cloud Functions + Pub/Sub + Cloud Workflows
pskit deploy --provider azure      # Function App + Storage Queue + embedded workflow engine
```

### Starting the workflow

`before/` called `stepfunctions.start_execution` from boto3. Choose one of:

- **Portable:** set `engine: embedded` on the workflow. Every cloud then exposes
  `POST /workflows/order-processing`, which runs the workflow and returns its output.
  `create-order` (or any client) POSTs the order there. Limit: the workflow must finish
  within one function timeout.
- **Native engines** (Step Functions, Cloud Workflows): start executions with the cloud's
  CLI/SDK behind a small function of your own, as with queue producers in example 04.

### Other AWS APIs your code calls

DynamoDB, S3 and Secrets Manager calls are data-plane code that pskit doesn't abstract.
Hide each behind a small repository class (see example 11), with one implementation per
cloud, selected by `PSKIT_PROVIDER`.

## Checklist

- [ ] every trigger expressed in `pskit.yml`; `pskit validate --provider <target>` clean
- [ ] no `event["..."]` parsing or `statusCode` dicts left in handlers
- [ ] state machine translated; `pskit workflow show --format asl` reviewed
- [ ] unit tests run with `LocalRunner` / `WorkflowEngine` (example 14)
- [ ] remote Terraform state configured (example 11)
- [ ] data-plane SDK calls behind interfaces
- [ ] deployed to AWS via pskit, traffic switched, old stack removed
- [ ] deployed to the target cloud; dashboard (`pskit dashboard`) shows both
