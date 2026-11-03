# On-premises storage (`type: storage`)

Run functions when files appear in a bucket, and read or write objects: the host's built-in buckets, a shared folder, MinIO or another S3-compatible store, or a bucket in a cloud (S3, R2, Azure Blob, GCS, ...). The host lists each watched bucket every `poll_seconds` and compares ETags: a new or changed object emits `created`, a missing one `deleted`. Objects already there at the first start are recorded, not emitted.
## pskit's Amazon S3 compatible server (one click)

*Resources → On-prem services → + Create service → Object storage → Amazon S3 compatible* (`s3` in Python, `s3-node` in Node.js), or the CLI: It runs pskit's own S3 server, whose code is in `aws/s3`, on the stock `python` / `node` image (nothing is built or pushed). Unlike LocalStack it **checks every request's signature** (AWS Signature Version 4 or 2): the service's *user* is the access key ID and its *password* the secret access key. The resource is a `storage` bucket on the `s3` driver (created on first use), so storage triggers work, and the env file gets `PSKIT_<KEY>_URL`, `_ACCESS_KEY` and `_SECRET_KEY` for any other program: It covers the S3 API that applications use: buckets, ListObjects / ListObjectsV2 / ListObjectVersions, put / get / head / delete / copy with ranges, conditions, metadata, tags and checksums (CRC32, CRC32C, CRC64NVME, SHA1, SHA256), multipart uploads, versioning and delete markers, presigned URLs and browser POST uploads, bucket policies (they decide what unsigned requests may do), ACLs, block public access, CORS, lifecycle rules (applied hourly), static website hosting, object lock (retention and legal hold) and default encryption; logging, notification and replication settings are stored. S3 Select, torrents and directory buckets are not supported, and objects are not encrypted at rest. Its **web console** (`http://<server>:<port>/ui/`, *Web UI → S3 console* on the service) signs in with the same user and password: buckets and every bucket setting, folders, drag-and-drop uploads of files and folders, downloads, previews, share links, copy / move / rename, versions (restore an old one), metadata, tags, ACLs and object lock. *Browse → Buckets (S3)* in the studio works on it too. Back it up with *Backup* (a `.tar.gz` of the data volume). Run it without pskit with the Dockerfiles in `aws/s3` (see its README).

```text
resources:
  uploads:
    type: storage                # a directory under data_dir, created at start

functions:
  ingest:
    handler: app.handlers.ingest
    events:
      - storage: {resource: uploads, prefix: in/, suffix: .csv, events: [created, deleted]}
```
