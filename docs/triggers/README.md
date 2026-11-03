# Triggers

Search terms: trigger, event, events, event source, http trigger, schedule trigger, queue trigger, storage trigger, topic trigger, smtp trigger, support matrix, which cloud supports, provider support

A pskit trigger (also called an event) is what makes a function run: an HTTP request, a timer, a queue message, a file
in a bucket, a published message, or an e-mail. You list triggers under a function's `events:` in `pskit.yml`, and
pskit creates the matching native trigger on each cloud.

## Write triggers in pskit.yml

Each pskit trigger is a single-key mapping: the key is the trigger type, the value is its settings or a shorthand
string.

```yaml
functions:
  worker:
    handler: app.jobs.process
    events:
      - http: POST /jobs                 # shorthand "METHOD /path"
      - schedule: 15 minutes             # shorthand rate (or a 5-field cron)
      - queue: jobs                      # shorthand queue name
      - storage: uploads-bucket          # shorthand bucket name
      - topic: job-events                # shorthand topic name
      - smtp: inbound-mail               # shorthand smtp resource key (on premises)
```

A function may have several triggers, of the same or different types. A function with no triggers is invoke-only:
workflows, `invoke()` and `pskit invoke` still call it.

| Type | Page | Handler receives |
|---|---|---|
| `http` | [http.md](http.md) | `event.http` (method, path, headers, query, path params, body) |
| `schedule` | [schedule.md](schedule.md) | `event.data` = the schedule's `input` |
| `queue` | [queue.md](queue.md) | `event.records`, one per message |
| `storage` | [storage.md](storage.md) | `event.records` with `bucket`, `key`, `size`, `action` |
| `topic` | [topic.md](topic.md) | `event.records`, one per published message |
| `smtp` | [smtp.md](smtp.md) | `event.data` = the parsed e-mail |

Other `event.type` values a handler can see without a trigger: `invoke` (from `invoke()` or a direct call) and
`workflow` (a workflow task state).

## Trigger support per provider

This pskit support matrix comes from each provider's `capabilities` in `providers/*.py` (`pskit providers` prints
the same data; `smtp` shows only in `pskit providers --json`). A trigger the provider lacks fails `pskit validate` with
`<Provider> does not support '<type>' events in pskit`.

| Trigger | aws | azure | gcp | alibaba | tencent | huawei | oracle | ibm | digitalocean | cloudflare | onprem |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `http` | yes | yes | yes | yes | yes | yes (1) | yes | yes | yes | yes | yes |
| `schedule` | yes | yes | yes | yes | yes | yes | no | no | yes | yes | yes |
| `queue` | SQS | Storage Queue | Pub/Sub | no | no | no | no | no | no | no | yes (2) |
| `storage` | S3 | Blob (created only) | Cloud Storage | OSS | COS | OBS | Object Storage | no | no | no | yes (2) |
| `topic` | SNS | Service Bus | Pub/Sub | MNS | no | SMN | no | no | no | no | yes (2) |
| `smtp` | no | no | no | no | no | no | no | no | no | no | yes (3) |

(1) Huawei HTTP needs `provider.options.apig_instance_id`. (2) On premises: a file broker by default, or a resource
driver (Redis, S3-compatible stores, cloud queues ...). (3) The SMTP server on-prem service.

## Trigger options each provider rejects or ignores

The pskit studio trigger forms show these rules under **On <provider>:**. They come from each provider's own
validation (`studio/meta.py::trigger_support`). "error" fails validation; "ignored" is a warning.

| Provider | http | schedule | queue | storage | topic |
|---|---|---|---|---|---|
| aws | `auth: key` error | | | | |
| azure | `auth: iam`, `jwt` error | `timezone` ignored | `fifo`, `dead_letter` ignored | `events: [deleted]` error | `filter` ignored; `existing` needs Service Bus options |
| gcp | `auth: jwt`, `key` error | | `fifo`, `dead_letter` ignored | | `filter` not applied |
| alibaba | `auth` other than `none` error | | | | `filter.tag` only |
| tencent | `auth` other than `none` error; `PATCH` error | | | bucket must be `<name>-<APPID>` | |
| huawei | `auth: jwt` error | | | | |
| oracle | `auth` other than `none` error | | | `prefix`/`suffix` ignored | |
| ibm, digitalocean, cloudflare | `auth` other than `none` error | | | | |
| onprem | `auth` other than `none` error | `timezone` needs tzdata (vendored on deploy) | | | |

## Add a trigger in studio

Every pskit trigger is added the same way in studio.

1. Sidebar **Functions** → click the function (or **+ Create function**).
2. Click **Next: Triggers →** (or the **2 Triggers** step).
3. Under **Add a trigger**, click a card: **HTTP endpoint**, **Schedule**, **Queue**, **Storage**, **Topic** or
   **E-mail (SMTP)**. Only cards the current provider supports are shown; a card with "N provider limitations"
   has rules from the table above. A line below the cards lists unsupported types and which providers have them.
4. Fill the form that opens. A **fix** badge marks a trigger with an error.
5. Optional, per trigger: **Disable on <provider>** keeps the trigger for other clouds only; **Remove** deletes it.
6. Click **Apply changes** (or **Create function**), then **Save** in the top bar.

## Add a trigger from the terminal

A pskit trigger is added by editing `pskit.yml`; no command writes it.

1. Open `pskit.yml` and add an entry under `functions.<name>.events`.
2. Run `pskit validate` (and `pskit validate -p <cloud>` for every cloud you target).
3. Test it locally: `pskit invoke -f <name> -t <type> -d '<payload>'`.
4. Deploy: `pskit deploy`. Then `pskit trigger --list` shows how to fire each deployed trigger.

## Attach a trigger to a resource

The pskit `queue`, `storage`, `topic` and `smtp` triggers can point at a `resources:` entry instead of naming the
queue, bucket or topic. The trigger then uses the resource's native name, and `existing` follows `external`.

```yaml
resources:
  jobs: {type: queue}                                   # pskit creates it
  uploads: {type: storage, external: true, name: legacy-uploads}   # already exists
functions:
  worker:
    handler: app.jobs.work
    events:
      - queue: {resource: jobs, batch_size: 5}
      - storage: {resource: uploads, prefix: in/}
```

Setting both `name` (or `bucket`) and `resource` is an error, except a storage trigger on premises, where `bucket`
picks another bucket on the resource's storage service. In studio the trigger form's **Source** switch has
**Create new <noun>**, **Project resource (N)**, **Pick from <provider>** and **Type a name**. Resources:
[../resources.md](../resources.md), on premises [../onprem/resources.md](../onprem/resources.md).

## How payloads reach the handler on HTTP-only clouds

On GCP, IBM, DigitalOcean, Cloudflare and Oracle every call arrives over HTTP. pskit wraps the payloads it sends
itself (schedule inputs, workflow tasks, `invoke()` calls) as `{"__pskit": "<schedule|workflow|invoke>", "data": ...}`.
The adapters unwrap it, so the handler sees the right `event.type` and `event.data` on every cloud.

## See also

- [http.md](http.md), [schedule.md](schedule.md), [queue.md](queue.md), [storage.md](storage.md), [topic.md](topic.md), [smtp.md](smtp.md)
- [../functions/README.md](../functions/README.md)
- [../functions/invoke-and-test.md](../functions/invoke-and-test.md)
- [../events.md](../events.md)
- [../providers/README.md](../providers/README.md)
