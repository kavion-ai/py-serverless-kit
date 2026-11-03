# Events (triggers)

Each function has a list of `events`. Each entry is a **single-key mapping**: the key is the trigger type.

```yaml
functions:
  worker:
    handler: app.jobs.process
    events:
      - http: POST /jobs
      - schedule: 15 minutes
      - queue: jobs
      - storage: uploads-bucket
      - topic: job-events
```

A function with no events is *invoke-only*: it can be called by workflows, by `invoke()`, or by the provider's own CLI.

Support at a glance (the full detail is below and in [providers.md](providers.md)):

| Trigger | aws | gcp | azure | alibaba | oracle | ibm | digitalocean | tencent | huawei | cloudflare | onprem |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `http` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓¹ | ✓ | ✓ |
| `schedule` | ✓ | ✓ | ✓ | ✓ | – | – | ✓ | ✓ | ✓ | ✓ | ✓ |
| `queue` | ✓ SQS | ✓ Pub/Sub | ✓ Storage Queue | – | – | – | – | – | – | – | ✓ files |
| `storage` | ✓ S3 | ✓ GCS | ✓ Blob (created only) | ✓ OSS | ✓ Object Storage | – | – | ✓ COS | ✓ OBS | – | ✓ directory |
| `topic` | ✓ SNS | ✓ Pub/Sub | ✓ Service Bus | ✓ MNS | – | – | – | – | ✓ SMN | – | ✓ files |
| `smtp` | – | – | – | – | – | – | – | – | – | – | ✓ SMTP service |

¹ Huawei HTTP needs `provider.options.apig_instance_id`.

`pskit validate` reports an error for any trigger or option the selected provider can't honour.

`smtp` (on premises) runs a function when mail arrives for your domain: `- smtp: {resource: inbound-mail}` on the
SMTP server created under *On-prem services* (an `smtp` resource). The handler gets from, to, cc, subject, text, html,
headers and attachments, plus the same mail as an Amazon SES event (`Records[0].ses`). Setup and DNS records:
[smtp/README.md](smtp/README.md).

---

## `http`

```yaml
- http: GET /users/{id}                # shorthand "METHOD /path"
- http: /health                        # shorthand, method GET
- http:
    path: /users
    method: POST                       # GET POST PUT PATCH DELETE HEAD OPTIONS ANY (or "*")
    cors: true                         # or a mapping, see below
    auth: none                         # none | iam | jwt | key
    authorizer: {}                     # used by auth: jwt on AWS
```

**Path templates**

- `{name}` matches one segment and lands in `event.http.path_params["name"]`.
- `{name+}` matches the rest of the path (greedy) and is only allowed as the last segment: `/files/{path+}`.
- Parameter names are identifiers: `{user_id}` is fine, `{user-id}` is not.

pskit's runtime also matches routes itself, so path params and `405 Method Not Allowed` work the same on clouds with no API gateway (GCP, IBM, DigitalOcean, Cloudflare), including when the platform adds or strips a path prefix. Two functions may not declare the same `METHOD /path`.

**CORS**

```yaml
cors:
  origins: ["https://app.example.com"]   # default ["*"]
  methods: [GET, POST]                    # default GET POST PUT PATCH DELETE OPTIONS
  headers: [Content-Type, Authorization]  # default Content-Type Authorization X-Requested-With
  expose_headers: []
  allow_credentials: false
  max_age: 600
```

The runtime answers `OPTIONS` preflights with 204 and adds `Access-Control-*` headers on every cloud. AWS additionally configures CORS on the HTTP API.

**Auth support**

| `auth` | Supported on |
|---|---|
| `none` (public) | all providers |
| `iam` | aws (`AWS_IAM`), gcp (no public invoker binding), huawei (`IAM`) |
| `jwt` | aws only. Needs `authorizer.issuer` and `authorizer.audience`; optional `identity_source`, `scopes` |
| `key` | azure (function key, `AuthLevel.FUNCTION`), huawei (`APP`) |

Example of AWS JWT auth, with a different setting per cloud: [`examples/02-rest-api`](../examples/02-rest-api).

Provider notes: Tencent's API Gateway has no `PATCH` (use `ANY`). On Tencent and Huawei, `{path+}` becomes a prefix route; on Oracle it becomes `{path*}`.

---

## `schedule`

```yaml
- schedule: 5 minutes                  # shorthand rate
- schedule: "0 3 * * *"                # shorthand cron (5 fields)
- schedule:
    rate: 1 hour                       # "<n> minute(s)|hour(s)|day(s)"
    # cron: "30 8 * * 1-5"             # OR standard 5-field unix cron (exactly one of rate/cron)
    input: {report: daily}             # becomes event.data
    timezone: Europe/Berlin            # default UTC
    enabled: true
    name: morning-report               # optional, used in the resource name
```

The handler gets `event.type == "schedule"` and `event.data == input`.

pskit converts the portable syntax to each cloud's dialect:

| Provider | Service | Expression |
|---|---|---|
| aws | EventBridge Scheduler | `rate(5 minutes)`, `cron(0 3 * * ? *)` (day-of-week converted to 1-7, `?` inserted; restricting both day-of-month and day-of-week is an error) |
| gcp | Cloud Scheduler | 5-field cron; rates converted to cron (`*/5 * * * *`) |
| azure | timer trigger | 6-field NCRONTAB (`0 */5 * * * *`); always UTC on Linux Consumption |
| alibaba | timer trigger | `@every 5m`, or 6-field cron with `CRON_TZ=` when a timezone is set |
| tencent | timer trigger | 7-field cron (seconds … year) |
| huawei | timer trigger | `Rate` (`5m`) or 6-field cron with `?` |
| digitalocean | `project.yml` scheduler trigger | 5-field cron |
| cloudflare | Cron Triggers | 5-field cron |
| onprem | in-process scheduler | rate in seconds, or 5-field cron. A rate such as `7 minutes` is valid here |

A rate that can't be expressed as cron on cron-only clouds (e.g. `7 minutes`) fails validation; use a divisor of 60 minutes or 24 hours. `timezone` is honoured by AWS, GCP and Alibaba (cron form); Azure ignores it with a warning.

---

## `queue`

```yaml
- queue: jobs                          # shorthand
- queue:
    name: jobs
    existing: false                    # true = use an existing queue, don't create it
    batch_size: 10                     # 1-10000
    batch_window: 0                    # seconds to wait to fill a batch (0-300)
    visibility_timeout: 120            # default (AWS): max(30, 6 x function timeout)
    dead_letter: jobs-dlq              # queue that receives messages after max_receive attempts
    max_receive: 5
    fifo: false
```

The handler gets `event.type == "queue"` and `event.records`, one `Record` per message. Return a [`BatchResult`](handlers.md#batchresult) to retry only failed messages.

| Option | aws (SQS) | gcp (Pub/Sub topic) | azure (Storage Queue) |
|---|---|---|---|
| `batch_size`, `batch_window` | ✓ | ignored | ignored |
| `dead_letter`, `max_receive` | ✓ redrive policy | ignored (warning) | ignored: poison messages go to `<queue>-poison` |
| `fifo` | ✓ (`.fifo` suffix, content-based dedup) | ignored (warning) | ignored (warning) |
| partial batch failure | ✓ `batchItemFailures` | whole delivery retried | whole delivery retried |

On premises the same options are implemented by a file broker (`batch_size`, `batch_window`, visibility, dead-letter, `max_receive`, `fifo`). `BatchResult` retries only the failed message ids, as on AWS. Set `provider.options.services.queue` to `builtin` (created at start) or `{use: directory, path: ...}`. `existing: true` waits for that directory. Example: [`examples/04-queue-worker`](../examples/04-queue-worker) and [`examples/16-on-premises`](../examples/16-on-premises).

On GCP a "queue" is a Pub/Sub topic with a push trigger, because GCP has no SQS-style pull trigger. Azure queue names must be 3–63 lowercase letters, digits and dashes. Example: [`examples/04-queue-worker`](../examples/04-queue-worker).

---

## `storage`

```yaml
- storage: uploads-bucket              # shorthand
- storage:
    bucket: uploads-bucket
    existing: false                    # true = bucket already exists
    events: [created, deleted]         # default [created]
    prefix: incoming/
    suffix: .csv
```

Each record has `bucket`, `key`, `size` and `action` (`"created"` / `"deleted"`).

| Provider | Service | Filters | Notes |
|---|---|---|---|
| aws | S3 notification | native | created buckets block public access |
| gcp | Cloud Storage via Eventarc | applied by the runtime | `created` and `deleted` become separate deployments |
| azure | Blob trigger in the app's storage account | path pattern | **created/updated only**; container name 3–63 lowercase; `existing` buckets in another account need `options.storage_connection` |
| alibaba | OSS trigger | native | |
| oracle | Events rule | not supported (warning) – filter in your handler | bucket must have "Emit Object Events" enabled |
| tencent | COS trigger | native | bucket name must be `<name>-<APPID>`, e.g. `uploads-1250000000` |
| huawei | OBS trigger | native | |
| onprem | a directory of files | prefix/suffix in the host | `created` and `deleted`. `builtin` creates the directory; `{use: directory, path}` uses one you already have. The first start records current files and does not emit them |

Example: [`examples/05-storage-events`](../examples/05-storage-events).

---

## `topic`

```yaml
- topic: order-events                  # shorthand
- topic:
    name: order-events
    existing: false
    filter: {type: ["created"]}        # AWS SNS filter policy
```

| Provider | Service | `filter` |
|---|---|---|
| aws | SNS subscription | ✓ filter policy |
| gcp | Pub/Sub | not applied (warning) – filter in the handler |
| azure | Service Bus topic + subscription | not applied (warning); `existing` needs `options.servicebus_namespace_id` and `options.servicebus_connection` |
| alibaba | MNS topic | `filter.tag` (string) only |
| huawei | SMN topic | – |
| onprem | file topic, fan-out | exact match on attributes, then on JSON body fields |

Example: [`examples/06-pubsub-topic`](../examples/06-pubsub-topic).

---

## Events backed by a resource

`queue`, `storage` and `topic` events can point at a [`resources:`](resources.md) entry instead of naming the queue, bucket or topic:

```yaml
resources:
  jobs: {type: queue}
  uploads: {type: storage, external: true, name: legacy-uploads}
functions:
  worker:
    handler: app.jobs.work
    events:
      - queue:   {resource: jobs, batch_size: 5}
      - storage: {resource: uploads, prefix: in/}
```

The event uses the resource's native name and `existing: <external>`. The functions also get the resource's connection details. On premises, a resource can move the queue to Redis or the bucket to an S3-compatible store, and a storage event may set both `resource` and `bucket`: that bucket on the resource's storage service ([details](resources.md#storage-drivers)).

## Provider-specific behaviour worth knowing

### GCP: multi-trigger functions are split automatically

A Cloud Function (gen2) has at most one event trigger and can't mix HTTP with events. pskit keeps your YAML portable by deploying one *logical* function as several Cloud Functions that share the code and handler:

- `<name>`: the HTTP deployment. It exists when the function has `http` events, has no triggers, is a workflow task, or has schedules but no Pub/Sub trigger to publish them to.
- `<name>-<kind><i>`: one per event trigger, e.g. `worker-queue0`, `worker-storage0`.

`pskit info` and the dashboard still show a single function. The extra deployments appear in its `extra` output. Event-triggered deployments are limited to 540 s timeout.

### Azure: one Function App per service

Every function of a service lives in one Function App, so `environment` is app-wide. pskit merges all functions' variables and warns when two functions set the same key to different values. Invoke-only functions get a key-protected `POST /_pskit/invoke/<name>` route.

### Schedule + invoke envelope

Schedules with `input`, workflow tasks and `invoke()` calls deliver a small JSON envelope (`{"__pskit": "<type>", "data": ...}`). The adapters unwrap it, so the handler simply sees `event.type` and `event.data`.
