# Attach cloud resources to on-prem functions

Search terms: hybrid, on-prem with AWS, SQS driver, S3 driver, Azure Queue, Azure Blob, Pub/Sub, GCS, MNS, OSS, COS,
OBS, Oracle Object Storage, IBM COS, Spaces, R2, Cloudflare Queues, Wasabi, Backblaze B2, access_key_env, driver picker

On-premises functions can consume a queue or watch a bucket that lives in another cloud: an Amazon SQS queue, an S3
bucket, an Azure Storage queue or blob container, a Pub/Sub subscription, a Google Cloud Storage bucket, Alibaba MNS
and OSS, Tencent COS, Huawei OBS, Oracle Object Storage, IBM COS, DigitalOcean Spaces, Cloudflare Queues and R2, and
other S3-compatible clouds. The host polls them with a **driver**; the handlers stay the same as for built-in queues
and buckets.

## Cloud drivers for on-prem queues

On-prem queue resources reach another cloud with these drivers (`options.driver`). *Secret* fields can also be given
as `<name>_env: VARIABLE`.

| Driver | Service | Fields (required in bold) |
|---|---|---|
| `sqs` | Amazon SQS | **`queue_url`** (or **`account_id`** + **`region`** + `name`), `access_key` / `secret_key` / `session_token` (secret; fall back to `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` on the host), `wait_seconds` (0-20), `message_group_id` (FIFO, default `pskit`), `create_queue`, `endpoint` |
| `azure_queue` | Azure Storage Queue | `queue` (default: the resource name), **`connection_string`** or **`account`** + **`account_key`** / **`sas_token`** (secret), `endpoint`, `message_encoding` (`base64` default, or `text`) |
| `pubsub` | Google Pub/Sub | **`subscription`** (`projects/.../subscriptions/...`), `topic` (to publish), `project` (needed for short names), `access_token` (secret) or `token_command` (for example `gcloud auth print-access-token`, cached about 45 minutes), `endpoint`, `emulator`, `return_immediately` |
| `mns` | Alibaba Cloud MNS | **`account_id`** + **`region`** (or `endpoint`), `queue`, **`access_key`** + **`secret_key`** (secret), `wait_seconds` (0-30), `message_encoding` |
| `cloudflare_queue` | Cloudflare Queues | **`account_id`**, **`queue_id`**, **`api_token`** (secret), `endpoint` |
| `custom` | anything else | **`class`**: RabbitMQ, Kafka, IBM MQ, OCI Queue, TDMQ, DMS ... (see `examples/19-custom-drivers`) |

Pub/Sub and Cloudflare Queues cannot report a queue depth. Azure queues do not support message attributes.

## Cloud drivers for on-prem buckets

On-prem storage resources reach another cloud's buckets with these drivers. Every S3-style preset takes `bucket`
(default: the resource name), `access_key` and `secret_key` (HMAC; set both or neither, then the `AWS_*` variables,
then anonymous), `prefix` (only watch keys below it, strongly advised on large buckets) and `endpoint`.

| Driver | Service | Extra fields (required in bold) |
|---|---|---|
| `aws` | Amazon S3 | `region` (default `us-east-1`) |
| `s3` | S3 / S3-compatible | `endpoint` (empty = AWS; set it for MinIO, Ceph, SeaweedFS, Garage, RustFS, LocalStack), `region`, `session_token`, `path_style`, `signing_region` |
| `oss` | Alibaba OSS | **`region`** (for example `cn-hangzhou`) |
| `cos` | Tencent COS | **`region`** (`ap-guangzhou`); bucket names end in `-<APPID>` |
| `obs` | Huawei OBS | **`region`** (`cn-north-4`) |
| `oci` | Oracle Object Storage | **`region`** (`eu-frankfurt-1`), **`namespace`**; use Customer Secret Keys |
| `ibm_cos` | IBM Cloud Object Storage | **`region`** (`us-south`); HMAC credentials, not an API key |
| `spaces` | DigitalOcean Spaces | **`region`** (`nyc3`) |
| `r2` | Cloudflare R2 | **`account_id`** |
| `minio` | MinIO | **`endpoint`** (`http://minio:9000`) |
| `wasabi` | Wasabi | `region` (default `us-east-1`) |
| `b2` | Backblaze B2 | **`region`** (`us-west-004`); the application key ID is the access key |
| `linode` | Akamai (Linode) Object Storage | **`region`** (`us-east-1`) |
| `scaleway` | Scaleway Object Storage | **`region`** (`fr-par`) |
| `azure_blob` | Azure Blob Storage | `container` (default: the resource name), **`connection_string`** or **`account`** + **`account_key`** / **`sas_token`**, `endpoint`, `prefix` |
| `gcs` | Google Cloud Storage | `bucket`, `project`, `access_token` or `token_command`, `endpoint`, `emulator`, `prefix` |
| `custom` | anything else | **`class`** implementing scan / put / get / delete |

The host polls each bucket (`provider.options.poll_seconds`) and turns new and deleted objects into storage events.

## Attach a cloud resource in studio

The studio attaches a cloud queue or bucket to on-prem functions through the resource drawer's driver picker.

1. Open **Resources** and click **+ Add resource**.
2. **Key**: for example `aws-jobs`. **Type**: **queue** or **storage**.
3. **Mode**: **External / existing** (pskit must not create or delete a bucket in another cloud).
4. **Native name**: the bucket or queue name, when it differs from the key.
5. In the **On-premises driver** box, the driver chips are grouped by cloud: *AWS*, *Azure*, *Google Cloud*,
   *Alibaba Cloud*, *Tencent Cloud*, *Huawei Cloud*, *Oracle Cloud*, *IBM Cloud*, *DigitalOcean*, *Cloudflare*,
   *Other S3-compatible clouds*, *Self-hosted*, *Built-in & custom*. Click one, for example **Amazon SQS**. Its note
   shows under the chips (hover a chip for it too).
6. Fill the fields. For each secret field the switch **Value** / **From env var** is set to *From env var*: type the
   variable name (for example `AWS_SECRET_ACCESS_KEY`); pskit writes `secret_key_env: AWS_SECRET_ACCESS_KEY`. A
   literal secret shows a warning: it would be written to `pskit.yml` and the deployed config.
7. Click **Add**, then attach the trigger: open **Functions**, pick the function and add a **queue** or **storage**
   trigger on `aws-jobs` (see [queue trigger](../triggers/queue.md) and [storage trigger](../triggers/storage.md)).
8. Click **Save**, put the variables on the host (next section), and deploy.

When the main provider is another cloud (for example AWS), the drawer says the driver is *Used when you deploy with
`--provider onprem`* and stores it in `providers.onprem.resources.KEY.options`, so the AWS deploy is not affected.

## Attach a cloud resource in pskit.yml

A cloud queue or bucket on premises is an external resource with a driver. This example (from
`examples/20-onprem-external-clouds`) watches an SQS queue, an Azure queue, a Pub/Sub subscription, S3 and R2:

```yaml
provider:
  name: onprem
  options:
    env_file: .env.onprem            # optional: the host loads these variables at start
    poll_seconds: 2

resources:
  aws-jobs:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: https://sqs.eu-west-1.amazonaws.com/123456789012/jobs
      access_key_env: AWS_ACCESS_KEY_ID
      secret_key_env: AWS_SECRET_ACCESS_KEY
  azure-jobs:
    type: queue
    external: true
    options: {driver: azure_queue, queue: jobs, connection_string_env: AZURE_STORAGE_CONNECTION_STRING}
  gcp-jobs:
    type: queue
    external: true
    options:
      driver: pubsub
      subscription: projects/my-project/subscriptions/jobs-sub
      token_command: [gcloud, auth, print-access-token]
  aws-media:
    type: storage
    external: true
    name: company-media
    options: {driver: aws, region: eu-west-1, prefix: incoming/,
              access_key_env: AWS_ACCESS_KEY_ID, secret_key_env: AWS_SECRET_ACCESS_KEY}
  r2-media:
    type: storage
    external: true
    name: media
    options: {driver: r2, account_id: 0123456789abcdef0123456789abcdef,
              access_key_env: R2_ACCESS_KEY_ID, secret_key_env: R2_SECRET_ACCESS_KEY}

functions:
  jobs:
    handler: app.handlers.process
    events:
      - queue: {resource: aws-jobs, batch_size: 10}
      - queue: {resource: azure-jobs}
      - queue: {resource: gcp-jobs}
  media:
    handler: app.handlers.on_object
    events:
      - storage: {resource: aws-media}
      - storage: {resource: r2-media}
```

In a project whose main provider is a cloud, put only the driver under the on-prem override, so the same resource is
native on that cloud and driver-based on premises:

```yaml
resources:
  jobs: {type: queue}
providers:
  onprem:
    resources:
      jobs:
        options: {driver: sqs, queue_url: "https://sqs.eu-west-1.amazonaws.com/123456789012/jobs",
                  access_key_env: AWS_ACCESS_KEY_ID, secret_key_env: AWS_SECRET_ACCESS_KEY}
```

## Give the host its cloud credentials

The on-prem host reads every `<name>_env` variable from its own environment when it starts. Nothing secret is written
to `pskit_host.json` or Terraform state. Two ways to set them:

- **The on-prem env file** (recommended): add lines to `.env.onprem` (or the file in `provider.options.env_file`).
  `pskit deploy` ships it to the host, which loads it at start. Keep it out of git.

  ```text
  AWS_ACCESS_KEY_ID=AKIA...
  AWS_SECRET_ACCESS_KEY=...
  AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...
  R2_ACCESS_KEY_ID=...
  R2_SECRET_ACCESS_KEY=...
  ```

- **The host's environment**: export the variables on the machine that runs the host before it starts (for
  `deploy.method: local`, in the shell that runs `pskit deploy`).

`gcs` and `pubsub` can use `token_command: [gcloud, auth, print-access-token]` instead of a stored token: the host
runs it and caches the token about 45 minutes. A missing variable stops the host with an error that names it; a
rejected credential or an unreachable cloud shows as a warning in `pskit logs --source host` and is retried on the
next poll. Give each credential only what the driver needs: receive, delete, send (and change visibility) on the
queue; list, get, put and delete on the bucket or prefix.

## Handle cloud messages and objects in a handler

Handlers for cloud-backed on-prem resources are the same as for built-in ones: `event.records` holds the messages or
objects, and `record.source` says which resource delivered them.

```python
from py_serverless_kit import BatchResult


def process(event, ctx):
    """Trigger: queue on aws-jobs, azure-jobs and gcp-jobs."""
    result = BatchResult()
    for record in event.records:
        try:
            payload = record.json()
        except ValueError:
            payload = record.text()
        if isinstance(payload, dict) and payload.get("poison"):
            result.fail(record)          # retried by the driver, dead-lettered after max_receive
            continue
        ctx.logger.info("job", extra={"id": record.id, "source": record.source})
    return result


def on_object(event, ctx):
    """Trigger: storage on aws-media and r2-media."""
    for record in event.records:
        ctx.logger.info("object", extra={"bucket": record.bucket, "key": record.key, "action": record.action})
```

To publish to a cloud queue or write to a cloud bucket from a handler, `submit_queue` and `put_object` from
`py_serverless_kit.runtime.onprem_host` go through the host and its driver, so the cloud's SDK is not needed (see
[on-prem resources](resources.md#use-an-on-prem-resource-from-a-handler)).

## Test a cloud resource from on premises

Cloud-backed on-prem resources are tested like any other resource once the host is deployed:

```bash
pskit validate                                   # driver fields are checked here
pskit deploy
pskit resources check aws-jobs                   # reachable? queue depth / object count
pskit resources send aws-jobs -d '{"order_id": 1}'
pskit resources data aws-media --prefix incoming/
pskit logs -f
```

In studio: **Resources → Test** on the row, and **Data** for buckets. Queues of SQS, Azure, Pub/Sub, MNS and
Cloudflare show their depth only (looking at a message would count as a delivery).

## Try a cloud driver against a local emulator

Every cloud driver above can first run against an on-prem emulator created with one click: ElasticMQ, LocalStack or
LocalEmu for `sqs` and `s3`; Azurite for `azure_queue` and `azure_blob`; fake-gcs-server for `gcs`; MinIO, RustFS or
pskit's Amazon S3 compatible server for `s3` / `minio`. The emulator's page shows the exact driver options it writes
(`endpoint`, `create_queue`, `create_bucket`, `emulator: true`). Switching to the real cloud means changing the
driver options only; handler code stays the same.

## See also

- [On-prem resources and drivers](resources.md)
- [On-prem services](services/README.md)
- [Queue trigger](../triggers/queue.md), [storage trigger](../triggers/storage.md)
- [Compatibility of cloud APIs](../resource-guides/compatibility.md)
- [Existing on-prem queue guide](../resource-guides/onprem/queue.md) and [storage guide](../resource-guides/onprem/storage.md)
- `examples/20-onprem-external-clouds` and `examples/19-custom-drivers`
