# Google Cloud resources

How to attach Google Cloud services you created in the [Google Cloud console](https://console.cloud.google.com) to a
Cloud Functions (2nd gen) deployment made with pskit.

| `type` | Google Cloud service | Guide |
|---|---|---|
| `queue` | Pub/Sub topic (a "queue" is a topic on GCP) | [queue.md](queue.md) |
| `storage` | Cloud Storage bucket | [storage.md](storage.md) |
| `topic` | Pub/Sub topic | [topic.md](topic.md) |
| `database` | Cloud SQL (PostgreSQL, MySQL, SQL Server) | [database.md](database.md) |
| `cache` | Memorystore for Redis / Valkey | [cache.md](cache.md) |
| `custom` | Firestore, Secret Manager, anything else | [custom.md](custom.md) |

## Values you need for every Google Cloud resource

| Value | Where |
|---|---|
| Project ID | project picker at the top of the console → *ID* column (not the project *name*); goes in `provider.options.project` |
| Project number | **IAM & Admin → Settings** → *Project number* (used in the default service account's email) |
| Region | the resource's detail page → *Location* / *Region*; compare with `provider.region` |

## How pskit runs on Google Cloud (why some steps matter)

- Every function is a **Cloud Function (2nd gen)**; a function with several triggers is split into several Cloud
  Functions.
- Functions run as `provider.options.service_account`, or the project's **default compute service account**
  (`<project number>-compute@developer.gserviceaccount.com`) when that option isn't set.
- **pskit grants no roles for resources on GCP**, and `iam.statements` are ignored. Grant the runtime service account
  the roles it needs in **IAM & Admin → IAM → Grant access** (each guide lists them). Whether the default compute
  account already has broad access depends on your organization's policy; don't rely on it.
- An external Pub/Sub topic (`queue` or `topic`) is **looked up by name** in `provider.options.project` with a Terraform
  data source. External resources get only `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL` and your `connection`
  values (managed queues and topics also get `_ID`). Every function also has `PSKIT_GCP_PROJECT`.
- Functions don't run in a VPC. pskit has no VPC option on GCP; services with only a private IP (Memorystore,
  private-IP Cloud SQL) need a Serverless VPC Access connector added through `provider.terraform.extra`
  (see [cache.md](cache.md#3-declare-it-in-pskityml)).

## Credentials for deploying

```bash
gcloud auth application-default login
gcloud config set project <project id>
```

`pskit resources send` / `pskit trigger` publish and upload with your local credentials and need
`pip install google-cloud-pubsub google-cloud-storage` on your machine.
