# On-premises storage (`type: storage`)

Run functions when files appear in a bucket, and read or write objects: the host's built-in buckets, a shared folder,
MinIO or another S3-compatible store, or a bucket in a cloud (S3, R2, Azure Blob, GCS, ...).

The host lists each watched bucket every `poll_seconds` and compares ETags: a new or changed object emits `created`, a
missing one `deleted`. Objects already there at the first start are recorded, not emitted.

## Built-in bucket

```yaml
resources:
  uploads:
    type: storage                # a directory under data_dir, created at start

functions:
  ingest:
    handler: app.handlers.ingest
    events:
      - storage: {resource: uploads, prefix: in/, suffix: .csv, events: [created, deleted]}
```

A folder you already have (NFS, SMB, a scanner's output directory):

```yaml
resources:
  inbox:
    type: storage
    external: true
    options: {driver: directory, path: /mnt/scans}
```

## pskit's Amazon S3 compatible server (one click)

*Resources → On-prem services → + Create service → Object storage → Amazon S3 compatible* (`s3` in Python, `s3-node`
in Node.js), or the CLI:

```bash
pskit resources onprem create files --service s3 --user AKIAPROD --save                  # this machine
pskit resources onprem create files --service s3-node --server edge1 --save              # a saved SSH server
```

It runs pskit's own S3 server, whose code is in [`aws/s3`](../../../aws/s3/README.md), on the stock `python` / `node`
image (nothing is built or pushed). Unlike LocalStack it **checks every request's signature** (AWS Signature Version 4
or 2): the service's *user* is the access key ID and its *password* the secret access key. The resource is a `storage`
bucket on the `s3` driver (created on first use), so storage triggers work, and the env file gets
`PSKIT_<KEY>_URL`, `_ACCESS_KEY` and `_SECRET_KEY` for any other program:

```python
import os, boto3
from botocore.config import Config

s3 = boto3.client("s3", endpoint_url=os.environ["PSKIT_FILES_URL"], region_name="us-east-1",
                  aws_access_key_id=os.environ["PSKIT_FILES_ACCESS_KEY"],
                  aws_secret_access_key=os.environ["PSKIT_FILES_SECRET_KEY"],
                  config=Config(s3={"addressing_style": "path"}))
s3.upload_file("report.pdf", "files", "reports/2024/report.pdf")
print(s3.generate_presigned_url("get_object", Params={"Bucket": "files", "Key": "reports/2024/report.pdf"}))
```

It covers the S3 API that applications use: buckets, ListObjects / ListObjectsV2 / ListObjectVersions, put / get /
head / delete / copy with ranges, conditions, metadata, tags and checksums (CRC32, CRC32C, CRC64NVME, SHA1, SHA256),
multipart uploads, versioning and delete markers, presigned URLs and browser POST uploads, bucket policies (they decide
what unsigned requests may do), ACLs, block public access, CORS, lifecycle rules (applied hourly), static website
hosting, object lock (retention and legal hold) and default encryption; logging, notification and replication settings
are stored. S3 Select, torrents and directory buckets are not supported, and objects are not encrypted at rest.

Its **web console** (`http://<server>:<port>/ui/`, *Web UI → S3 console* on the service) signs in with the same user
and password: buckets and every bucket setting, folders, drag-and-drop uploads of files and folders, downloads,
previews, share links, copy / move / rename, versions (restore an old one), metadata, tags, ACLs and object lock.
*Browse → Buckets (S3)* in the studio works on it too. Back it up with *Backup* (a `.tar.gz` of the data volume).

Run it without pskit with the Dockerfiles in `aws/s3` (see its README).

## MinIO (or Ceph, Garage, SeaweedFS, any S3-compatible store)

### 1. Create the bucket and keys (MinIO console)

1. Run MinIO if you don't have it:
   `docker run -d -p 9000:9000 -p 9001:9001 -e MINIO_ROOT_USER=admin -e MINIO_ROOT_PASSWORD=<password> minio/minio server /data --console-address :9001`
2. Open the console at `http://<minio-host>:9001` and sign in.
3. **Buckets → Create Bucket** → name (for example `uploads`) → **Create Bucket**.
4. **Access Keys → Create access key** → optionally restrict it with a policy for that bucket → **Create** → copy the
   *Access Key* and *Secret Key* (or download them; the secret is shown once).

### 2. Collect the values

| Value | Where | Example |
|---|---|---|
| Endpoint | the S3 API port (not the console port) | `http://minio.internal:9000` |
| Bucket | **Buckets** | `uploads` |
| Access key / secret key | **Access Keys** | |

```bash
export MINIO_ACCESS_KEY=... MINIO_SECRET_KEY=...      # on the host
```

### 3. Declare it

```yaml
resources:
  uploads:
    type: storage
    external: true
    name: uploads                 # the bucket
    options:
      driver: minio               # path-style requests to `endpoint`
      endpoint: http://minio.internal:9000
      access_key_env: MINIO_ACCESS_KEY
      secret_key_env: MINIO_SECRET_KEY
      prefix: incoming/           # only watch keys below it (recommended on large buckets)

functions:
  ingest:
    handler: app.handlers.ingest
    events: [{storage: {resource: uploads}}]
```

Other S3-compatible stores: `driver: s3` with `endpoint` (and `path_style: true` if needed).

Watch another bucket on the same MinIO (same endpoint and keys) without a second resource:
`events: [{storage: {resource: uploads, bucket: invoices}}]`. In the studio, pick the resource under *Storage service*
and type the bucket. See [resources.md](../../resources.md#storage-drivers).

## A bucket in a cloud

| Bucket | Driver | Required | Where to find the values |
|---|---|---|---|
| Amazon S3 | `aws` | `region` (+ `access_key_env` / `secret_key_env`, or `AWS_*` on the host) | S3 console → bucket → *Properties → AWS Region*; IAM access key |
| Cloudflare R2 | `r2` | `account_id`, `access_key_env`, `secret_key_env` | [cloudflare/storage.md](../cloudflare/storage.md#2-collect-the-values) (*Manage R2 API Tokens*) |
| Azure Blob | `azure_blob` | `connection_string_env` (or `account` + key / SAS), `container` | [azure/storage.md](../azure/storage.md#2-collect-the-values) |
| Google Cloud Storage | `gcs` | `token_command` or `access_token_env` | bucket name from the Cloud Storage console |
| Alibaba OSS, Tencent COS, Huawei OBS, Oracle, IBM COS, DigitalOcean Spaces, Wasabi, Backblaze B2, Akamai (Linode), Scaleway | `oss`, `cos`, `obs`, `oci`, `ibm_cos`, `spaces`, `wasabi`, `b2`, `linode`, `scaleway` | `region` (+ `namespace` for `oci`), HMAC / S3 keys | each console's bucket overview and access-key page; presets in [resources.md](../../resources.md#storage-drivers) |

```yaml
resources:
  media:
    type: storage
    external: true
    name: company-media
    options:
      driver: r2
      account_id: 0123456789abcdef0123456789abcdef
      access_key_env: R2_ACCESS_KEY_ID
      secret_key_env: R2_SECRET_ACCESS_KEY
      prefix: incoming/
```

## Use it in a handler

```python
from py_serverless_kit import resource
from py_serverless_kit.runtime.onprem_host import put_object


def ingest(event, ctx):
    for record in event.records:
        ctx.logger.info("file", extra={"bucket": record.bucket, "key": record.key, "action": record.action})
        if record.action == "created":
            put_object(resource("uploads").native_name, "done/" + record.key, b"processed")
```

`record.key` has `prefix` stripped. `put_object` / `delete_object` go through the driver, so the same code writes to a
directory, MinIO or S3. To read object contents, use the store's client (`boto3`, `minio`, `azure-storage-blob`) or, for
built-in buckets, the file under `data_dir`.

## Test

```bash
pskit validate
pskit deploy
pskit resources send uploads -d '{"key": "incoming/a.csv", "content": "a,b"}'
curl -X PUT --data 'a,b' http://127.0.0.1:8080/__pskit/storage/uploads/incoming/b.csv
pskit logs -f --function ingest
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Existing files never trigger | expected: the first start records them; upload a new one |
| `SignatureDoesNotMatch` against MinIO | use the API port (9000), not the console (9001); check the keys |
| Slow polls on a big bucket | set `prefix`, raise `poll_seconds` |
| `set both access_key and secret_key (or neither)` | give both, or neither to use the `AWS_*` variables |
