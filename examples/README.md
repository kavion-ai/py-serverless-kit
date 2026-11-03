# Examples

Every directory is a complete project: `cd` into it and run `pskit dev`, `pskit invoke`,
`pskit workflow run` or `pskit deploy`. Handlers use only the public API
(`from py_serverless_kit import ...`), so each example deploys to every cloud listed for it
by changing only the provider (`pskit deploy --provider gcp`).

| # | Example | Shows | Validated on |
| --- | --- | --- | --- |
| 01 | [hello-http](01-hello-http) | the smallest deployable function | AWS, GCP, Azure |
| 02 | [rest-api](02-rest-api) | CRUD, path/query params, validation errors, CORS, cookies, binary, redirect, JWT auth | AWS, GCP, Azure |
| 03 | [scheduled-jobs](03-scheduled-jobs) | rate + cron schedules, `input`, time zones, disabling schedules | AWS, GCP, Azure |
| 04 | [queue-worker](04-queue-worker) | batch consumer, `BatchResult` partial failures, dead-letter queue, producer notes | AWS, GCP, Azure |
| 05 | [storage-events](05-storage-events) | object created/deleted, prefix/suffix filters, existing buckets | AWS, GCP, Azure* |
| 06 | [pubsub-topic](06-pubsub-topic) | topic fan-out to two subscribers, filter policies | AWS, GCP, Azure |
| 07 | [workflow-orders](07-workflow-orders) | Step Functions-style workflow with every state type, retry/catch, native vs embedded engine | AWS, GCP, Azure |
| 08 | [multi-cloud](08-multi-cloud) | one codebase, **all 11 providers**: `providers:` overrides and `extends:` files | all 11 |
| 09 | [function-invoke](09-function-invoke) | `invoke()` between functions, per-cloud resolution | AWS, GCP, Azure |
| 10 | [stages-and-config](10-stages-and-config) | dev/staging/prod, `${env:}`, `${opt:}`, `${self:}`, `${file()}`, `.env`, secrets | AWS, GCP, Azure |
| 11 | [custom-terraform](11-custom-terraform) | `terraform.extra` (DynamoDB), `${tf:...}` references, remote state, hooks | AWS |
| 12 | [async-and-context](12-async-and-context) | `async def` handlers, structured logging, `ctx.remaining_time_ms()` | AWS, GCP, Azure |
| 13 | [migrate-from-aws-lambda](13-migrate-from-aws-lambda) | step-by-step migration of raw Lambdas + Step Functions (before/after) | AWS, GCP, Azure |
| 14 | [testing](14-testing) | pytest with `LocalRunner`, synthetic events, workflow tests, CI validation | AWS, GCP, Azure |
| 15 | [ci-cd-deploy](15-ci-cd-deploy) | GitHub Actions per-stage deploys with OIDC, remote state, dashboard artifact | AWS, GCP, Azure |
| 16 | [on-premises](16-on-premises) | one process on this machine: HTTP, schedule, queue, directory storage, topic, embedded workflow | on-premises |
| 17 | [on-premises-remote](17-on-premises-remote) | SSH/SCP or Docker onto a server, with a `.pem` and a bundled CPython when it has no Python | on-premises |
| 18 | [resources](18-resources) | `resources:`: a managed bucket, queue and topic, an external database, `resource()` bindings, Redis/MinIO drivers on premises | AWS, GCP, Azure |
| 19 | [custom-drivers](19-custom-drivers) | `driver: custom`: your own queue/storage class (SQLite queue with dead-letter, folder storage) plus RabbitMQ and Kafka templates | On-premises |
| 20 | [onprem-external-clouds](20-onprem-external-clouds) | one on-prem host watching SQS, Azure Queue/Blob, Pub/Sub, GCS, MNS, Cloudflare Queues, R2 and MinIO; secrets via `*_env` | On-premises |

\* Azure blob triggers can't fire on deletions; the example's `providers.azure` block
handles that explicitly.

"Validated on" means `pskit validate` passes for that provider. `tests/test_examples.py`
checks this, packages every example, and runs its HTTP functions and workflows locally.
Most examples also work on the other clouds when the trigger types are supported. Run
`pskit providers` for the capability matrix, and `pskit validate --provider <cloud>` to check
one cloud.

## Placeholders

The configs use `${env:NAME, placeholder}` for account-specific values (GCP project,
Azure subscription, bucket names). Validation and local runs therefore work out of the
box; export the real values before `pskit deploy`.
