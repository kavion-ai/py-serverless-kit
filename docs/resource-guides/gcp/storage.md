# Cloud Storage bucket (`type: storage`)

Use a Cloud Storage bucket you created in the console: run a function when objects are created or deleted, read or
write objects from a handler, or both.

## 1. Create the bucket (console)

1. Console → **Cloud Storage** → **Buckets** → **Create**.
2. Name: globally unique, lowercase (for example `acme-invoices-prod`).
3. **Location type: Region**, the **same region as `provider.region`** (for example `europe-west1`). pskit creates the
   Eventarc trigger in `provider.region`, and Cloud Storage triggers must be in the bucket's location, so dual- and
   multi-region buckets can't trigger pskit functions.
4. Access control: *Uniform* → **Create**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Bucket name | Cloud Storage → **Buckets** | `acme-invoices-prod` |
| Location | Buckets list → *Location* column | `europe-west1` |
| gsutil URI | the bucket → **Configuration** → *gsutil URI* | `gs://acme-invoices-prod` |

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: gcp
  region: europe-west1
  options:
    project: my-project
    service_account: orders-runtime@my-project.iam.gserviceaccount.com

resources:
  invoices:
    type: storage
    external: true
    name: acme-invoices-prod

functions:
  on-invoice:
    handler: app.handlers.on_invoice
    events:
      - storage: {resource: invoices, prefix: incoming/, suffix: .pdf, events: [created]}
```

What pskit does with it: deploys `on-invoice` with an Eventarc trigger filtered on the bucket
(`google.cloud.storage.object.v1.finalized`; `deleted` events get a second Cloud Function), grants the project's Cloud
Storage service agent `roles/pubsub.publisher` (required by Cloud Storage triggers), and grants pskit's invoker
service account `roles/eventarc.eventReceiver`. `prefix` and `suffix` are applied by the pskit runtime, so the
function is still invoked (and returns immediately) for other objects.

Grant the runtime service account access to the bucket: the bucket → **Permissions** → **Grant access** → the service
account → **Storage Object User** (read/write) or **Storage Object Viewer** (read-only).

## 4. Use it in a handler

`requirements.txt`: `google-cloud-storage`

```python
from google.cloud import storage
from py_serverless_kit import resource

client = storage.Client()


def on_invoice(event, ctx):
    invoices = resource("invoices")
    bucket = client.bucket(invoices.native_name)
    for record in event.records:
        data = bucket.blob(record.key).download_as_bytes()
        ctx.logger.info("invoice", extra={"key": record.key, "size": len(data), "action": record.action})
```

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send invoices -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -f --function on-invoice
```

Console: the bucket → **Create folder** `incoming` → open it → **Upload files**.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy: trigger location doesn't match the bucket | the bucket must be a single-region bucket in `provider.region` |
| Deploy: Cloud Storage service agent / Pub/Sub permission error | the deploying account needs rights to grant project IAM roles; enable the Eventarc API |
| Function runs for every object | expected: `prefix` / `suffix` are filtered by the runtime |
| `403` reading objects | grant a Storage role on the bucket to the runtime service account |
