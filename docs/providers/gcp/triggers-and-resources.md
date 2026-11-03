# GCP triggers, resources and workflows

Search terms: cloud functions http, cloud scheduler, pub/sub, pubsub topic, eventarc, cloud storage trigger, gcs,
cloud workflows, invoker service account, run.invoker, oidc, gcp resources, external topic

This page explains how each pskit trigger, resource and workflow becomes Google Cloud infrastructure. For credentials,
the `provider` block and deploy commands, see the [GCP provider page](README.md).

## GCP HTTP trigger: function URL

A GCP `http` event is served by the function's HTTP deployment (entry point `pskit_http`) on its own Cloud Run URL. The
pskit runtime routes every path and method listed in the function's HTTP events, answers `405` for other methods, and
handles CORS.

| Setting | GCP result |
|---|---|
| `auth: none` | an `allUsers` `roles/run.invoker` binding: public URL |
| `auth: iam` | no public binding: callers send an identity token with `run.invoker` permission |
| `auth: jwt`, `auth: key` | validation error |
| `path`, `method`, `cors` | handled by the pskit runtime inside the function |

Ingress is `ALLOW_ALL` and all traffic goes to the latest revision.

## GCP schedule trigger: Cloud Scheduler

A GCP `schedule` event becomes a `google_cloud_scheduler_job` in the provider region.

| pskit key | Cloud Scheduler setting |
|---|---|
| `rate` / `cron` | a 5-field cron (`rate: 15 minutes` → `*/15 * * * *`; a rate that is not a divisor of 60 minutes or 24 hours is an error) |
| `timezone` | `time_zone` (IANA, default `UTC`) |
| `enabled: false` | `paused: true` |
| `input` | the body `{"__pskit": "schedule", "data": <input>}`; your handler sees `event.data` |

The job POSTs to the function's HTTP deployment with an OIDC token of the invoker service account (attempt deadline:
the function timeout, between 15 s and 1800 s). When the function has no HTTP deployment but has a queue or topic
trigger, the job publishes the same envelope to that Pub/Sub topic instead.

## GCP queue and topic triggers: Pub/Sub

A GCP `queue` event and a GCP `topic` event both become a Pub/Sub topic (`google_pubsub_topic`) and an Eventarc
trigger of type `google.cloud.pubsub.topic.v1.messagePublished` on a dedicated Cloud Function. GCP has no push queue
like SQS, so a pskit queue is a Pub/Sub topic. The runtime still reports `event.type` as `queue` or `topic`.

- Retry policy: `RETRY_POLICY_RETRY` (a failed delivery is retried by Pub/Sub).
- `dead_letter` and `fifo` warn and are not applied; `batch_size` and `batch_window` are not used (one message per call).
- `filter` on topics warns and is not applied.
- `existing: true` reads the topic by name with a data source in `options.project`.

```bash
pskit trigger -f worker -e 0 -d '{"order_id": 1}'
gcloud pubsub topics publish hello-gcp-jobs --message='{"order_id": 1}' --project <project>
```

## GCP storage trigger: Cloud Storage

A GCP `storage` event creates a Cloud Storage bucket (uniform bucket-level access, location = the region in capitals)
and an Eventarc trigger with a `bucket` filter.

| pskit key | GCP result |
|---|---|
| `events: [created]` | `google.cloud.storage.object.v1.finalized` |
| `events: [deleted]` | `google.cloud.storage.object.v1.deleted` |
| both | two Cloud Functions, `<name>-storage0` and `<name>-storage1` |
| `prefix`, `suffix` | `PSKIT_STORAGE_PREFIX` / `PSKIT_STORAGE_SUFFIX`: the runtime skips non-matching objects |
| `existing: true` | the bucket is not created; the trigger filters on its name |

pskit grants `roles/pubsub.publisher` to the project's Cloud Storage service agent, which Eventarc needs for storage
triggers.

## GCP resources: managed, standalone and external

A `resources:` entry of type `storage` is a Cloud Storage bucket on GCP; `queue` and `topic` are Pub/Sub topics.

| Case | What pskit does on GCP |
|---|---|
| managed, used by an event | the event creates it |
| managed, no event uses it | created anyway (standalone): a bucket, or a Pub/Sub topic |
| `external: true` | not created; a queue or topic used by an event is read with a data source |
| `database`, `cache`, `custom` | must be `external: true`; only `connection` values reach handlers |

Bound functions get `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL`, one variable per `connection` entry, and `_ID`
(the full Pub/Sub topic id) for managed queues and topics.

pskit grants **no roles** for resources on GCP. Grant the runtime service account (`options.service_account`, or the
default compute account) the roles your code needs, for example `roles/pubsub.publisher` or
`roles/storage.objectAdmin`, in **IAM & Admin → IAM → Grant access**. Functions do not run in a VPC; private-IP
services need a Serverless VPC Access connector added through `provider.terraform.extra`
(see the [GCP resource guides](../../resource-guides/gcp/README.md)).

## GCP workflows: Cloud Workflows

GCP workflows run natively on **Google Cloud Workflows**. With `engine: auto` (default) or `engine: native`, each
workflow becomes a `google_workflows_workflow` whose task steps are HTTP calls to the task functions' URLs with an OIDC
token of the invoker service account. Every task function therefore gets an HTTP deployment.

```yaml
workflows:
  order-pipeline:
    description: Validate then charge an order
    start_at: Validate
    states:
      Validate: {type: task, function: validate-order, next: Charge}
      Charge: {type: task, function: charge-order, end: true}
```

```bash
pskit workflow show order-pipeline --format gcp        # the compiled Cloud Workflows source
pskit workflow start order-pipeline -i '{"amount": 50}'
pskit workflow executions order-pipeline
pskit workflow status <execution-name> --watch
```

Execution commands need `pip install "py-serverless-kit[gcp]"` (google-cloud-workflows) on your machine. Compiler
limits: only the first retry rule of a task is used, `retry` / `catch` work on `task` states only, task HTTP timeouts
are capped at 1800 s. See [workflows.md](../../workflows.md#compiler-notes-and-limits). `engine: embedded` deploys a
`<workflow>-orchestrator` function with `POST /workflows/<workflow>` instead.

## Call another function with invoke() on GCP

`invoke("billing", {...})` on GCP POSTs to `https://<region>-<project>.cloudfunctions.net/<service>-<stage>-billing`
with an identity token from the metadata server. The caller runs as the runtime service account, so that account needs
`roles/run.invoker` on the target. A `PSKIT_ENDPOINT_<NAME>` variable overrides the URL.

## Send test events to GCP triggers

`pskit trigger` and the studio **Test** page fire GCP triggers with your local ADC.

| Trigger | Sent by pskit | Needs |
|---|---|---|
| http | an HTTP request to the function URL | an identity token for `auth: iam` |
| queue, topic | a Pub/Sub publish | `google-cloud-pubsub` |
| storage | a Cloud Storage upload | `google-cloud-storage` |
| schedule, invoke | a POST with the `__pskit` envelope to the function URL | a public URL, or run the job with **Force run** in Cloud Scheduler |

## See also

- [GCP provider page](README.md)
- [GCP resource guides](../../resource-guides/gcp/README.md)
- [events.md](../../events.md), [workflows.md](../../workflows.md), [resources.md](../../resources.md)
- [Triggers overview](../../triggers/README.md), [Workflows guide](../../deployment/workflows.md)
- [workflow-executions.md](../../workflow-executions.md)
