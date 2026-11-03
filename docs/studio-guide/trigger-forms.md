# Trigger forms in studio

Search terms: trigger form, add trigger, HTTP route, CORS, auth, jwt authorizer, schedule, cron, rate, timezone, queue trigger, storage trigger, topic trigger, smtp trigger, browse account, pick from cloud, create and select, provider limitations

Trigger forms open in step 2 (**Triggers**) of the [Create function wizard](functions.md). Each trigger type has its
own form. The form writes one entry of `functions.<name>.events` in `pskit.yml`. The meaning of every option is
explained in the [trigger guides](../triggers/README.md).

## Read the provider limitations box on a trigger

The "On <Provider>:" box at the top of a trigger form lists what this provider rejects (**not supported**) or ignores
(**ignored**) for this trigger type, worked out from the provider's own validation. Each line names the key, the
value and the reason. Lines that apply to the current settings are highlighted and end with "(used here)". For
example, `auth: jwt` is not supported on Azure, and a timezone is ignored by some schedule engines.

## Add an HTTP endpoint trigger in studio

The HTTP endpoint form ("Call the function with an HTTP request (API route)") writes an `http:` event.

1. **Route** (required): pick the method (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `ANY`, ...) and type the path,
   for example `/users/{id}` or `/files/{path+}`. A `/` is added in front if missing. The default is
   `GET /<function-name>`.
2. When the path has parameters, a box lists them and shows how to read them:
   `event.http.path_params["id"]`.
3. **Auth**: `none` (public), `iam`, `jwt` or `key`. Options the provider cannot enforce are disabled; hover for why.
4. With `jwt`, **Authorizer** takes JSON such as `{"issuer": "https://...", "audience": ["api"]}`.
5. **CORS**: toggle **enabled** writes `cors: true`. **Allowed origins** (**Add origin**) writes `cors.origins`;
   empty = any origin (`*`).

Two functions cannot use the same method and path; the wizard shows "route GET /x is already used by another
function".

```yaml
events:
  - http: {method: GET, path: /users/{id}, auth: jwt, authorizer: {issuer: "https://login.example.com"}, cors: true}
```

More: [HTTP triggers](../triggers/http.md).

## Add a schedule trigger in studio

The Schedule form ("Run on a timer: every N minutes, at a set time, or a cron expression") writes a `schedule:` event.
**Run** has three modes:

| Mode | Fields | Written |
|---|---|---|
| **Every…** | **Interval**: every N minute / hour / day, or a preset chip (`1 minute`, `5 minutes`, `15 minutes`, `1 hour`, `6 hours`, `1 day`) | `rate: 5 minutes` |
| **At a specific time** | **Repeat** (**Every day**, **Weekdays**, **On days…** with day boxes, **Monthly**, **Yearly**), **On** (month and day), **At** (HH:MM) | `cron: "30 8 * * 1-5"` |
| **Cron expression** | **Cron** (5 fields: minute hour day-of-month month day-of-week) and preset chips (**Every day 09:00**, **Weekdays 08:30**, **Every hour**, **1st of month**) | `cron: ...` |

- Under the time or cron, studio shows the schedule in plain English and the cron it wrote.
- **Timezone** (not for rates): every IANA zone your browser knows; empty = UTC.
- **Input**: JSON passed as `event.data` on every run, for example `{"report": "daily"}`.
- **Enabled**: **active** or **paused** (`enabled: false`).

A rate runs every N units from deploy time. Days after the 28th are skipped in shorter months.

More: [Schedule triggers](../triggers/schedule.md).

## Add a queue, storage or topic trigger in studio

The Queue, Storage and Topic forms share one layout. **Source** has four choices:

| Source | What it does | Written |
|---|---|---|
| **Create new <queue / bucket / topic>** | pskit creates it on deploy. Type the name (default `<function>-jobs`, `-uploads` or `-events`) | `name:` / `bucket:` |
| **Project resource (N)** | Pick a `resources:` entry of that type; disabled when there is none | `resource: <key>` |
| **Pick from <Provider>** | Lists what already exists in the account ("Browse account") | `existing: true` plus the name, or a resource |
| **Type a name** | An existing one; you type its exact name, pskit only attaches the trigger | `existing: true` plus the name |

**Create & select** (next to the name in **Create new**) adds the queue, bucket or topic to Resources as a managed
resource and selects it, so other functions can bind it and it shows in the **Project resource** list.

Other fields:

- **Storage**: **Fire on** `created` and / or `deleted`, plus prefix and suffix filters.
- **Queue**: batch size (default 10), batch window, visibility timeout, dead letter queue, max receive and FIFO.
- **Topic**: a message filter.
- **On premises, storage**: with **Project resource**, the field is **Storage service** (the storage resource whose
  driver, endpoint and keys the trigger uses: MinIO, RustFS, Ceph, AWS S3, R2, Wasabi or any S3-compatible store)
  plus **Bucket** (any bucket on that service; empty = the resource's own bucket).

More: [Queue](../triggers/queue.md), [Storage](../triggers/storage.md), [Topic](../triggers/topic.md).

## Pick an existing queue, bucket or topic from your cloud account

The **Pick from <Provider>** source of a trigger form lists the queues, buckets or topics that exist in your account,
using the credentials of the machine running studio and the region in Overview.

1. Choose **Pick from <Provider>** under **Source**.
2. **Existing <queues / buckets / topics>** loads the list. Use **Filter…** to search and **Refresh** to reload.
3. **Also add to Resources (external)** is on by default: picking an item adds an external resource (with its ARN or
   URL as `connection`) and selects it. Off, the trigger gets `existing: true` and the name.
4. Click an item.

If listing is not available ("Listing isn't available here", a missing SDK or credential), click **Type the name
instead**. What each provider can list:

| Provider | Lists | Needs |
|---|---|---|
| AWS | SQS queues, S3 buckets, SNS topics, Step Functions state machines | `pip install "py-serverless-kit[aws]"` and AWS credentials |
| GCP | Pub/Sub topics and subscriptions, Cloud Storage buckets | `google-cloud-pubsub` / `google-cloud-storage`, `provider.options.project` or `GOOGLE_CLOUD_PROJECT` |
| Azure | Storage queues and blob containers | `azure-storage-queue` / `azure-storage-blob`, `AZURE_STORAGE_CONNECTION_STRING` |
| On premises | Existing queue and bucket folders under the host's data directory | nothing |
| Others | Not available | type the name |

## Add an e-mail (SMTP) trigger in studio

The E-mail (SMTP) form ("Run when mail arrives for your domain", on premises) writes an `smtp:` event.

1. **SMTP server** (required): pick an `smtp` resource. Create one first under
   [Resources → + SMTP server](resources.md) (or On-prem services → Mail); its DNS guide lists the records to add at
   your domain provider.
2. The handler gets `event.data` with from, from_name, to, cc, bcc, reply_to, subject, text, html, headers,
   attachments (filename, content_type, size, content in base64), the SMTP envelope, and the same mail as an Amazon
   SES event (`Records[0].ses`, raw message in `content`).

More: [SMTP triggers](../triggers/smtp.md) and [E-mail triggers](../smtp/README.md).

## See also

- [Functions page](functions.md)
- [Triggers overview and provider matrix](../triggers/README.md)
- [Resources page](resources.md)
