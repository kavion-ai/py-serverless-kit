# 20 · On premises, watching other clouds

A single on-prem host consumes queues and watches buckets that live in AWS,
Azure, Google Cloud, Alibaba Cloud, Cloudflare and a self-hosted MinIO. The
handlers are ordinary pskit handlers. Retries (`BatchResult`), dead-lettering,
logs, stats and the dashboard work the same as with the built-in queues.

| Resource | Driver | Service |
| --- | --- | --- |
| `aws-jobs` | `sqs` | Amazon SQS |
| `azure-jobs` | `azure_queue` | Azure Storage Queue |
| `gcp-jobs` | `pubsub` | Google Pub/Sub (pull subscription) |
| `alibaba-jobs` | `mns` | Alibaba Cloud MNS |
| `cf-jobs` | `cloudflare_queue` | Cloudflare Queues |
| `aws-media` | `aws` | Amazon S3 |
| `azure-media` | `azure_blob` | Azure Blob Storage |
| `gcp-media` | `gcs` | Google Cloud Storage |
| `r2-media` | `r2` | Cloudflare R2 |
| `minio-media` | `minio` | MinIO / Ceph |

`pskit.yml` also lists the presets for Alibaba OSS, Tencent COS, Huawei OBS, Oracle
Object Storage, IBM COS and DigitalOcean Spaces. For brokers without a built-in
driver (RabbitMQ, Kafka, IBM MQ, OCI Queue, TDMQ, DMS), see
[`19-custom-drivers`](../19-custom-drivers).

## Credentials

Secrets are referenced as `<name>_env: VARIABLE`, so the host reads them from its
own environment at start. Nothing secret is written to `pskit_host.json` or to
Terraform state. Keep only the resources you use, then export their variables on the
machine that runs the host:

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
export AZURE_STORAGE_CONNECTION_STRING='DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...'
export ALIBABA_ACCESS_KEY_ID=... ALIBABA_ACCESS_KEY_SECRET=...
export CLOUDFLARE_API_TOKEN=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=...
export MINIO_ACCESS_KEY=... MINIO_SECRET_KEY=...
gcloud auth login            # pubsub / gcs use `token_command: [gcloud, auth, print-access-token]`
```

Give each credential only what the driver needs: receive/delete/send (and change
visibility) on the queue, plus list/get/put/delete on the bucket or prefix.

## Run it

```bash
pskit validate
pskit deploy                     # starts the host on 127.0.0.1:8092
curl localhost:8092/status       # bound services (names only)
pskit logs -f                    # "job" / "object" entries as messages and files arrive
pskit dashboard --serve          # Logs tab, invocation counts, queue depths
```

An unreachable service or a rejected credential doesn't stop the host. It shows
up as a warning in `pskit logs --source host` and is retried on the next poll.
Pub/Sub and Cloudflare Queues can't report a queue depth, so the dashboard shows
it as unknown.

## Emulators for local testing

Every driver accepts `endpoint:`, so you can point it at LocalStack (SQS/S3),
Azurite (`connection_string: UseDevelopmentStorage=true`), the Pub/Sub emulator
(`emulator: true` or `PUBSUB_EMULATOR_HOST`) or fake-gcs-server (`STORAGE_EMULATOR_HOST`).
