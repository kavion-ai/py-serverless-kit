# AWS triggers, resources, IAM and workflows

Search terms: api gateway, http api, eventbridge scheduler, sqs, sns, s3 notification, step functions, state machine,
iam role, lambda permission, dead letter queue, fifo, jwt authorizer, aws_iam, aws resources, external resource

This page explains how each pskit trigger, resource and workflow becomes AWS infrastructure. For credentials, the
`provider` block and deploy commands, see the [AWS provider page](README.md).

## AWS HTTP trigger: API Gateway HTTP API

An AWS `http` event becomes a route on one **API Gateway HTTP API** per service (`aws_apigatewayv2_api`, protocol
`HTTP`) with a `$default` stage that deploys automatically. Each function with HTTP events gets one Lambda proxy
integration (payload format 2.0) and one route per event.

```yaml
functions:
  api:
    handler: app.api.handler
    events:
      - http: GET /users/{id}          # route "GET /users/{id}"
      - http: ANY /files/{path+}       # greedy path, any method
      - http:
          method: POST
          path: /orders
          cors: {origins: ["https://app.example.com"], allow_credentials: true}
          auth: jwt
          authorizer:
            issuer: https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_AbC
            audience: [my-client-id]
            scopes: [orders/write]                       # optional
            identity_source: $request.header.Authorization  # optional, this is the default
```

| Setting | AWS result |
|---|---|
| `auth: none` | public route |
| `auth: iam` | `authorization_type: AWS_IAM` (callers sign requests with SigV4) |
| `auth: jwt` | an `aws_apigatewayv2_authorizer` of type JWT; `issuer` and `audience` are required |
| `auth: key` | validation error: HTTP APIs have no API keys |
| `cors` | merged for the whole API: the union of origins, methods and headers, the largest `max_age`, `allow_credentials` if any event sets it |

The integration timeout is the function timeout, capped at 30 s. pskit adds an `aws_lambda_permission` so API Gateway
may invoke the function. The URL is `https://<api-id>.execute-api.<region>.amazonaws.com/<path>`.

## AWS schedule trigger: EventBridge Scheduler

An AWS `schedule` event becomes an `aws_scheduler_schedule` in the `default` schedule group. pskit creates one shared
`scheduler` IAM role that may call `lambda:InvokeFunction`.

| pskit key | Scheduler setting |
|---|---|
| `rate: 5 minutes` | `rate(5 minutes)` |
| `cron: "0 2 * * 1-5"` | `cron(0 2 ? * 2-6 *)` (weekday numbers move to AWS's 1 = Sunday; `?` fills the unused day field) |
| `timezone` | `schedule_expression_timezone` (IANA name, default `UTC`) |
| `enabled: false` | `state: DISABLED` |
| `input` | the target input, wrapped as `{"__pskit": "schedule", "data": <input>}`; your handler sees `event.data` |
| `name` | schedule name `<service>-<stage>-<function>-<name>` (max 64 characters) |

The flexible time window is off and the target retries twice. A cron that restricts both day-of-month and
day-of-week is rejected, because AWS cron allows only one of them.

## AWS queue trigger: SQS

An AWS `queue` event creates an SQS queue (`aws_sqs_queue`) and an `aws_lambda_event_source_mapping` with
`ReportBatchItemFailures`, so a `BatchResult` retries only the failed messages.

```yaml
- queue:
    name: orders                 # .fifo is appended when fifo: true
    batch_size: 10               # 1-10000
    batch_window: 5              # seconds to wait for a full batch (maximum_batching_window_in_seconds)
    visibility_timeout: 120      # default: max(30, 6 x function timeout)
    dead_letter: orders-dlq      # created for you; messages move there after max_receive
    max_receive: 5               # default 5
    fifo: false                  # true: FIFO queue with content-based deduplication
    existing: false              # true: look the queue up by name, don't create it
```

Message retention is 14 days on the queue and on the dead-letter queue. The role gets the managed policy
`AWSLambdaSQSQueueExecutionRole` when any function has a queue event. Send a test message with
`pskit trigger -f <fn> -e 0 -d '{"id": 1}'` or `aws sqs send-message` (`pskit trigger --list` prints the full command).

## AWS storage trigger: S3 bucket notifications

An AWS `storage` event creates an S3 bucket (`aws_s3_bucket`, all public access blocked) and one
`aws_s3_bucket_notification` per bucket that lists every function subscribed to it.

| pskit key | S3 result |
|---|---|
| `bucket` | bucket name (global in S3: pick a unique name) |
| `events: [created]` | `s3:ObjectCreated:*` |
| `events: [deleted]` | `s3:ObjectRemoved:*` |
| `prefix` / `suffix` | `filter_prefix` / `filter_suffix` |
| `existing: true` | the bucket is read with a data source; pskit adds only the notification and permission |

S3 keeps one notification configuration per bucket. pskit writes the whole list, so a notification you add to the
same bucket outside pskit is replaced on the next deploy.

## AWS topic trigger: SNS

An AWS `topic` event creates an SNS topic (`aws_sns_topic`), an `aws_sns_topic_subscription` with protocol `lambda`, and
an `aws_lambda_permission` for SNS. `filter` becomes the subscription's `filter_policy` as written:

```yaml
- topic:
    name: order-events
    filter: {type: [created, paid]}   # SNS filter policy on message attributes
    existing: false
```

## AWS resources: managed, standalone and external

A `resources:` entry of type `storage`, `queue` or `topic` is an S3 bucket, SQS queue or SNS topic on AWS.

| Case | What pskit does on AWS |
|---|---|
| managed, used by an event | the event creates it (see the trigger sections above) |
| managed, no event uses it | pskit creates it anyway (standalone): bucket, queue or topic. A standalone queue takes `fifo`, `visibility_timeout`, `dead_letter`, `max_receive` from the first event that uses it, else from `options` |
| `external: true`, bound by name | looked up with a Terraform data source (`data.aws_s3_bucket`, `data.aws_sqs_queue`, `data.aws_sns_topic`) |
| `external: true` with `connection.arn` | that ARN is used as-is; nothing is looked up |
| `database`, `cache`, `custom` | must be `external: true`; pskit only passes `connection` values to handlers |

Bound functions get `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL`, one variable per `connection` entry, `_ARN` for
storage, queue and topic, and `_URL` for queues. Read them with `py_serverless_kit.resource("<key>")`.

```yaml
resources:
  uploads: {type: storage}                                   # managed bucket "uploads"
  jobs: {type: queue, options: {fifo: true}}                 # managed standalone FIFO queue
  legacy: {type: queue, external: true, name: legacy-jobs}   # looked up by name
  orders-db:
    type: database
    external: true
    connection: {host: db.example.internal, port: 5432, password: "${env:DB_PASSWORD}"}
```

Console walkthroughs for each type: [AWS resource guides](../../resource-guides/aws/README.md).

## IAM roles and permissions on AWS

The AWS provider creates IAM roles for Lambda, EventBridge Scheduler and Step Functions.

| Role | When | Permissions |
|---|---|---|
| `<service>-<stage>-lambda` | always (shared by functions without their own `iam`) | `AWSLambdaBasicExecutionRole`; `AWSLambdaSQSQueueExecutionRole` if any queue event; `provider.iam.statements` as policy `pskit-custom`; resource access as policy `pskit-resources` |
| `<service>-<stage>-fn-<function>` | a function sets `iam.statements` or `iam.role` | the provider statements plus the function's own |
| `<service>-<stage>-scheduler` | any schedule event | `lambda:InvokeFunction` |
| `<service>-<stage>-states` | any native workflow | `lambda:InvokeFunction` on the task functions |

The `pskit-resources` policy grants, for the resources bound to the role's functions: S3 `GetObject`, `PutObject`,
`DeleteObject`, `ListBucket` (bucket and `/*`); SQS `SendMessage`, `ReceiveMessage`, `DeleteMessage`,
`ChangeMessageVisibility`, `GetQueueAttributes`, `GetQueueUrl`; SNS `Publish`.

`iam.role` (provider or function) uses an existing role ARN instead. pskit then creates no role and does not change
yours; validation warns that you must grant resource access yourself. See
[resources.md](../../resources.md#aws-iam).

## Call another function with invoke() on AWS

`invoke("billing", {...})` from a handler calls `lambda:InvokeFunction` through `boto3` (present in the Lambda runtime)
on the function `<service>-<stage>-billing`. pskit does not grant that action, so add it:

```yaml
provider:
  iam:
    statements:
      - actions: ["lambda:InvokeFunction"]
        resources: ["arn:aws:lambda:*:*:function:${self:service}-${opt:stage}-*"]
```

`invoke(..., asynchronous=True)` uses invocation type `Event` and returns `None`. A `PSKIT_ENDPOINT_<NAME>` variable
overrides this with an HTTP POST to that URL. See [handlers.md](../../handlers.md) and `examples/09-function-invoke`.

## AWS workflows: Step Functions

AWS workflows run natively on **AWS Step Functions**. With `engine: auto` (the default) or `engine: native`, each
workflow becomes an `aws_sfn_state_machine` compiled to Amazon States Language, plus the shared `states` role.

```yaml
workflows:
  order-pipeline:
    engine: auto                 # auto = native on AWS; embedded runs it inside one Lambda
    timeout: 3600                # TimeoutSeconds of the state machine
    options:
      type: STANDARD             # STANDARD (default) | EXPRESS
    start_at: Validate
    states:
      Validate: {type: task, function: validate-order, next: Charge}
      Charge: {type: task, function: charge-order, end: true}
```

```bash
pskit workflow show order-pipeline --format asl     # the compiled ASL
pskit workflow start order-pipeline -i '{"amount": 50}'
pskit workflow executions order-pipeline --status FAILED
pskit workflow status <execution-arn> --watch
pskit workflow cancel <execution-arn>
```

Execution commands use `boto3` locally. `engine: embedded` deploys an extra Lambda `<workflow>-orchestrator` with the
route `POST /workflows/<workflow>`; the whole run must then finish within 900 s. Compiler details:
[workflows.md](../../workflows.md#compiler-notes-and-limits). In studio, build the workflow on the **Workflows** page
and pick **Engine** there.

## Send test events to AWS triggers

`pskit trigger` and the studio **Test** page can fire every AWS trigger type with your local credentials (`boto3`).

| Trigger | What pskit sends | AWS CLI equivalent (`pskit trigger --list` prints it) |
|---|---|---|
| http | an HTTP request to the API URL | `curl` |
| schedule, invoke | a direct Lambda invoke with the `__pskit` envelope | `aws lambda invoke` |
| queue | an SQS message | `aws sqs send-message` |
| topic | an SNS publish | `aws sns publish` |
| storage | an S3 upload | `aws s3 cp` |

`pskit resources send <key> -d '{...}'` sends to a queue, bucket or topic resource directly. In studio: **Resources →
Test** on the resource row.

## See also

- [AWS provider page](README.md)
- [AWS resource guides](../../resource-guides/aws/README.md)
- [events.md](../../events.md), [resources.md](../../resources.md), [workflows.md](../../workflows.md)
- [Triggers overview](../../triggers/README.md), [Workflows guide](../../deployment/workflows.md)
- [workflow-executions.md](../../workflow-executions.md)
