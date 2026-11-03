# Resource: GCP Cloud Storage bucket

On GCP, `type: storage` is a Cloud Storage bucket. Use it when an object create or delete should run a function, or when a handler reads and writes objects. GCP can also create a managed bucket. The guide is the path for a bucket that already exists.

The bucket name is globally unique and lowercase. Location type Region must be the same region as `provider.region`. pskit creates the Eventarc trigger in `provider.region`, and a Cloud Storage trigger must be in the bucket's location, so a dual-region or multi-region bucket cannot trigger a pskit function. The guide's provider example sets `options.project` and `options.service_account`.

Declare `type: storage`, `external: true`, and `name`. A storage event can set `resource`, `prefix`, `suffix`, and `events: [created]`. pskit deploys the function with an Eventarc trigger filtered on the bucket (`google.cloud.storage.object.v1.finalized`). `deleted` events get a second Cloud Function. pskit grants the project's Cloud Storage service agent `roles/pubsub.publisher` and pskit's invoker service account `roles/eventarc.eventReceiver`. `prefix` and `suffix` are applied by the pskit runtime, so the function is still invoked for other objects and returns immediately.

Grant the runtime service account access on the bucket: Storage Object User for read and write, or Storage Object Viewer for read-only. `requirements.txt` gets `google-cloud-storage`. `storage.Client().bucket(resource("invoices").native_name).blob(record.key).download_as_bytes()` reads the object. Node.js uses `@google-cloud/storage`. Each record has `key`, `size`, and `action`.

Open:

Resources > + Add resource

Resources > Browse account

```
pskit validate
pskit resources send invoices -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -f --function on-invoice
```

Sources: `docs/resource-guides/gcp/storage.md#cloud-storage-bucket-type-storage`, `docs/events.md#storage`
