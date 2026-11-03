# Storage trigger

Search terms: storage, bucket, file upload, object created, object deleted, S3 event, blob trigger, GCS, OSS, COS, OBS, object storage, prefix, suffix, MinIO, directory watch

The pskit `storage` trigger runs a function when objects are created or deleted in a bucket: S3 on AWS, Blob Storage
on Azure, Cloud Storage on GCP, OSS, COS, OBS and OCI Object Storage, or on premises a directory or an S3-compatible
store such as MinIO.

## Write a storage trigger in pskit.yml

The pskit `storage` trigger needs `bucket` or `resource`.

```yaml
events:
  - storage: uploads-bucket            # shorthand: the bucket name
  - storage:
      bucket: uploads-bucket
      existing: false                  # true: the bucket already exists
      events: [created, deleted]       # default [created]
      prefix: incoming/                # only keys that start with this
      suffix: .csv                     # only keys that end with this
  - storage: {resource: uploads, prefix: in/}       # a resources: entry of type storage
```

| Key | Default | Meaning |
|---|---|---|
| `bucket` | | native bucket (container) name |
| `resource` | | key of a `resources:` entry of type `storage` |
| `existing` | `false` | `true`: pskit attaches the trigger, never creates or deletes the bucket |
| `events` | `[created]` | `created`, `deleted` or both |
| `prefix`, `suffix` | | key filters |

On premises only, `bucket` and `resource` may be combined: the trigger watches bucket `bucket` on the storage
service (endpoint, keys, driver) of resource `resource`. Elsewhere that is an error.

## Read storage records in the handler

For a `storage` trigger `event.type == "storage"` and `event.records` holds one `Record` per object.

```python
from py_serverless_kit import Context, Event


def on_upload(event: Event, ctx: Context):
    for record in event.records:
        if record.action == "deleted":
            ctx.logger.info("removed", extra={"bucket": record.bucket, "key": record.key})
            continue
        ctx.logger.info("new file", extra={"bucket": record.bucket, "key": record.key, "size": record.size})
        # read the object with your storage client, e.g. boto3 on AWS or resource("uploads") on premises
```

| `Record` field | Meaning |
|---|---|
| `bucket` | bucket or container name |
| `key` | object key (URL-decoded on AWS) |
| `size` | bytes, when the cloud reports it |
| `action` | `created` or `deleted` |
| `id`, `attributes`, `raw` | e.g. on AWS `attributes` has `etag` and `event_name` |

The record does not carry the file content. Read it with the cloud's SDK or, on premises, through the resource's
connection ([../onprem/resources.md](../onprem/resources.md)). Return a `BatchResult` to report failed records
([queue.md](queue.md#retry-only-the-failed-messages-with-batchresult)).

## Add a storage trigger in studio

1. Sidebar **Functions** → open the function → **2 Triggers** → card **Storage** (default bucket
   `<function>-uploads`, `events: [created]`).
2. **Source**: **Create new bucket** (**Bucket name**, optionally **Create & select** to add it to Resources),
   **Project resource (N)**, **Pick from <provider>** (AWS, GCP with `google-cloud-storage`, Azure with
   `azure-storage-blob` and `AZURE_STORAGE_CONNECTION_STRING`, on premises) or **Type a name** (existing bucket).
3. On premises with **Project resource**, the field is called **Storage service**; a **Bucket** field below picks any
   bucket on that service (empty = the resource's own bucket).
4. **Fire on**: tick **created**, **deleted** or both.
5. **prefix** and **suffix** have suggestions (`uploads/`, `.csv`, `.jpg`, ...).
6. **Apply changes**, then **Save**.

## Storage triggers per provider

The pskit storage trigger maps to each cloud's notification service.

| Provider | Native | `prefix` / `suffix` | `deleted` | Notes |
|---|---|---|---|---|
| aws | S3 bucket notification | native | yes | buckets pskit creates block public access |
| azure | Blob trigger in the Function App's storage account | path pattern | no (error) | container names 3 - 63 lowercase; an `existing` container elsewhere needs `provider.options.storage_connection` |
| gcp | Cloud Storage via Eventarc | applied by the runtime | yes | `created` and `deleted` are separate Cloud Functions; event functions max 540 s |
| alibaba | OSS trigger | native | yes | |
| tencent | COS trigger | native | yes | bucket must be `<name>-<APPID>`, e.g. `uploads-1250000000` |
| huawei | OBS trigger | native | yes | |
| oracle | Events rule | ignored, warning: filter in the handler | yes | an `existing` bucket needs "Emit Object Events" enabled |
| onprem | the host watches a directory or a storage service | in the host | yes | the first start records current files and does not emit them |
| ibm, digitalocean, cloudflare | not supported | | | |

On premises the default is a folder under the host's data directory (`provider.options.services.storage`:
`builtin` or `{use: directory, path: ...}`). A `resources:` storage entry can use another driver: `directory`, `s3`,
`azure_blob`, `gcs`, `custom` or an S3 preset (`aws`, `oss`, `cos`, `obs`, `oci`, `ibm_cos`, `spaces`, `r2`, `minio`,
`wasabi`, `b2`, `linode`, `scaleway`). See [../onprem/resources.md](../onprem/resources.md).

## Attach to a new or an existing bucket

A pskit storage trigger either creates the bucket or attaches to one that exists.

| You want | YAML |
|---|---|
| pskit creates the bucket | `- storage: my-uploads` |
| an existing bucket | `- storage: {bucket: legacy-uploads, existing: true}` |
| a bucket other functions also read or write | `resources: {uploads: {type: storage}}` and `- storage: {resource: uploads}` |
| an existing bucket as a resource | `resources: {uploads: {type: storage, external: true, name: legacy-uploads}}` |
| on premises: another bucket on a MinIO resource | `- storage: {resource: minio-store, bucket: invoices}` |

Bucket names are global on most clouds; pick a unique name. pskit never deletes an `existing` bucket or an
`external` resource.

## Test a storage trigger

- Locally: `pskit invoke -f on-upload -t storage -d '{"bucket": "b", "key": "in/a.csv", "size": 10}'`. Add
  `"action": "deleted"` for a delete; a list gives several records.
- Studio: **Test** → the function → the `bucket <name>` card → **Payload (JSON)** `{"key": "...", "content": "..."}`
  → **▶ Run locally**, or **☁ Send to <provider> / <stage>** to upload the object for real (the confirm dialog says
  "The object is uploaded to the bucket").
- Deployed: `pskit trigger -f on-upload -e 0 -d '{"key": "in/a.csv", "content": "a,b"}'` uploads on AWS, GCP, Azure
  and on premises; `{"key": "...", "action": "deleted"}` deletes on AWS. For a resource:
  `pskit resources send uploads -d '{"key": "in/a.csv", "content": "a,b"}'`.
- Watch: `pskit logs -f --function on-upload`.

## Common storage trigger errors

| Message or symptom | Fix |
|---|---|
| `storage event needs 'bucket' or 'resource'` | set one |
| `storage event sets both 'resource: x' and 'bucket: y'; another bucket on a resource's service is on-premises only` | use one of them |
| `Azure blob triggers only fire on created/updated blobs` | remove `deleted` |
| `container name 'X' must be 3-63 lowercase letters, digits, dashes` (Azure) | rename |
| `COS bucket 'x' must be '<name>-<APPID>'` (Tencent) | add your APPID |
| `OCI Events rules cannot filter by prefix/suffix; filter in the handler` | filter in code |
| nothing fires for existing files on premises | expected: only changes after the first start are emitted |
| the function writes into the same bucket and loops | write to another prefix and filter with `prefix` |

## See also

- [README.md](README.md)
- [queue.md](queue.md)
- [../resources.md](../resources.md)
- [../onprem/resources.md](../onprem/resources.md)
- [../functions/invoke-and-test.md](../functions/invoke-and-test.md)
- [../events.md](../events.md)
