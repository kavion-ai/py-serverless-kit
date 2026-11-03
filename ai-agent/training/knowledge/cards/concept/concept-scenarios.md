# Scenarios: step by step Pick what you're building

. Each guide has the `pskit.yml` you need, the commands, and how to check the result. They assume `pip install py-serverless-kit`, Terraform or OpenTofu on `PATH`, and cloud credentials for the target (getting started). | I want to… | Guide | |---|---| | expose an HTTP API on AWS | A | | process jobs from a queue pskit creates | B | | consume a queue or bucket that already exists | C | | run on my own server with Redis and MinIO | D | | run on my own server but consume queues / buckets in AWS, Azure, GCP or another cloud | K | | give functions a database or any other service | E | | orchestrate steps and track each run | F | | run jobs on a schedule | G | | deploy dev/prod, or the same code to several clouds | H | | read logs of an on-premises deployment | I | | develop and test before deploying | J | Every guide ends with `pskit dashboard` (static) or `pskit dashboard --serve` (live). See dashboard.md. ---
## A. HTTP API on AWS **Verify:** `pskit info` lists both routes with URLs.

A missing id returns `404 {"error": ...}`.
## B. Queue worker with a managed queue pskit gives the `enqueue` role

`sqs:SendMessage` on that queue automatically (IAM grants). **Verify:** the worker's CloudWatch logs (console link in `pskit info`) show the message. A message that keeps failing lands in `jobs-dlq` after 3 receives.
## C. Attach an existing queue or bucket pskit doesn't create or delete an `external`

resource. It wires the trigger and hands over the details. Without `connection.arn`, set `name:` and pskit looks the resource up by name (a Terraform data source) to get its ARN and URL. Handlers get `PSKIT_RESOURCE_LEGACY_ORDERS_ARN`, `_URL` and so on, or `resource("legacy-orders")`. **Verify:** `pskit plan` creates no `aws_sqs_queue` or `aws_s3_bucket`. Sending to the existing queue invokes `importer`. On providers other than AWS, use the queue/bucket `name` the same way. See events.md for each cloud's `existing` caveats.
## D. On premises with Redis and MinIO

Run on your own machine or server and keep queue messages in Redis and objects in MinIO (any S3-compatible store). `dead_letter: jobs-dlq` is a builtin directory queue on the host unless you declare a Redis resource named `jobs-dlq`.

```text
# pskit.yml
service: orders-api
provider: {name: aws, region: eu-west-1}
functions:
  get-order:
    handler: app.api.get_order
    events: [{http: GET /orders/{id}}]
  create-order:
    handler: app.api.create_order
    events: [{http: {method: POST, path: /orders, cors: true}}]
```
