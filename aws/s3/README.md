# Amazon S3 compatible server

A self-hosted server that speaks the **Amazon S3 API**, in two interchangeable implementations:

| | Path | Needs | Docker image (build it) |
|---|---|---|---|
| Python | `python/server.py` | Python 3.9+, standard library only | `python/Dockerfile` (`python:3.12-alpine`) |
| Node.js | `nodejs/server.js` | Node.js 18+, no npm packages | `nodejs/Dockerfile` (`node:22-alpine`) |
| Web console | `ui/index.html` | served by both at `/ui/` | included in both images |

boto3, the AWS SDKs (JavaScript v3, Java, Go, .NET ...), the AWS CLI (`aws s3` and `aws s3api`), rclone, s3cmd and
pskit's `s3` storage driver work with it unchanged: give them its endpoint and an access key / secret key it knows.
Every request is checked with **AWS Signature Version 4** (Authorization header, presigned URLs, `aws-chunked`
streaming uploads with chunk and trailer signatures, browser POST policies) or Version 2, so a wrong secret key, an
unknown access key, an expired link or a request more than 15 minutes old is refused.

pskit runs it as a one-click on-prem service (`s3` / `s3-node`, see
[docs/resource-guides/onprem/storage.md](../../docs/resource-guides/onprem/storage.md)). You can also run it on its
own, as below.

## Run it

```bash
cd aws/s3

# Docker (Python or Node.js; build from this folder so the console is included)
docker build -f python/Dockerfile -t pskit/s3:python .
docker run -d --name s3 -p 127.0.0.1:9000:9000 -v s3-data:/data \
  -e S3_ACCESS_KEY_ID=AKIAPROD -e S3_SECRET_ACCESS_KEY='a-long-random-secret' pskit/s3:python

# or docker compose (pick one of the two services)
S3_SECRET_ACCESS_KEY='a-long-random-secret' docker compose up -d s3-nodejs

# or no Docker at all
S3_SECRET_ACCESS_KEY='a-long-random-secret' python python/server.py
S3_SECRET_ACCESS_KEY='a-long-random-secret' node nodejs/server.js
```

The images run as an unprivileged user (uid 10001), keep the data in `/data` and have a health check
(`server.py --check` / `server.js --check`, which reads `/-/health`).

## Settings

| Variable | Default | |
|---|---|---|
| `S3_ACCESS_KEY_ID` | `pskit` | the access key ID clients sign with |
| `S3_SECRET_ACCESS_KEY` | (required) | its secret access key; also the console password |
| `S3_CREDENTIALS` | | more keys: `id1:secret1,id2:secret2` |
| `S3_AUTH` | `sigv4` | `off` turns authentication off (development only) |
| `S3_PORT` / `S3_BIND` | `9000` / `0.0.0.0` | where it listens |
| `S3_DATA_DIR` | `./data` (`/data` in the images) | holds the buckets |
| `S3_REGION` / `S3_ACCOUNT_ID` | `us-east-1` / `000000000000` | the default bucket region and the account for `x-amz-expected-bucket-owner` |
| `S3_DOMAIN` | `localhost` | domains for virtual-hosted style (`<bucket>.<domain>`), comma-separated |
| `S3_UI` | `on` | `off` removes the web console |
| `S3_UI_PASSWORD` | | a console password other than the secret keys |
| `S3_MAX_OBJECT_SIZE` | 5 GiB | the largest single PUT, part or copy |
| `S3_MIN_PART_SIZE` | 5 MiB | the smallest multipart part except the last |
| `S3_LIFECYCLE_INTERVAL` | `3600` | seconds between lifecycle sweeps |
| `S3_LIFECYCLE_DAY_SECONDS` | `86400` | the length of a lifecycle "day" (shorten it to test rules) |

The server refuses to start without a credential unless `S3_AUTH=off`.

## Use it

```python
import boto3
from botocore.config import Config

s3 = boto3.client("s3", endpoint_url="http://127.0.0.1:9000", region_name="us-east-1",
                  aws_access_key_id="AKIAPROD", aws_secret_access_key="a-long-random-secret",
                  config=Config(s3={"addressing_style": "path"}))
s3.create_bucket(Bucket="photos")
s3.put_object(Bucket="photos", Key="2024/cat.jpg", Body=open("cat.jpg", "rb"), ContentType="image/jpeg")
s3.upload_file("video.mp4", "photos", "2024/video.mp4")   # multipart above 8 MB
print(s3.generate_presigned_url("get_object", Params={"Bucket": "photos", "Key": "2024/cat.jpg"}, ExpiresIn=3600))
```

```js
const { S3Client, PutObjectCommand } = require("@aws-sdk/client-s3");

const s3 = new S3Client({
  endpoint: "http://127.0.0.1:9000", region: "us-east-1", forcePathStyle: true,
  credentials: { accessKeyId: "AKIAPROD", secretAccessKey: "a-long-random-secret" },
});
await s3.send(new PutObjectCommand({ Bucket: "photos", Key: "hello.txt", Body: "hi" }));
```

```bash
export AWS_ACCESS_KEY_ID=AKIAPROD AWS_SECRET_ACCESS_KEY='a-long-random-secret' AWS_DEFAULT_REGION=us-east-1
aws --endpoint-url http://127.0.0.1:9000 s3 sync ./site s3://photos/site
aws --endpoint-url http://127.0.0.1:9000 s3api list-object-versions --bucket photos
```

Path-style addressing (`http://host:9000/bucket/key`) works everywhere. Virtual-hosted style
(`http://bucket.localhost:9000/key`) works for the domains in `S3_DOMAIN` when the name resolves to the server.

### Operations

| Area | Supported |
|---|---|
| Buckets | CreateBucket (location constraint, canned ACL, object lock, object ownership), DeleteBucket, HeadBucket, ListBuckets (prefix, paging), GetBucketLocation |
| Listing | ListObjects, ListObjectsV2 (prefix, delimiter, start-after, continuation tokens, `encoding-type=url`, fetch-owner), ListObjectVersions, ListMultipartUploads, ListParts |
| Objects | PutObject, GetObject, HeadObject, DeleteObject, DeleteObjects (quiet, versions), CopyObject (metadata and tagging directives, conditions), GetObjectAttributes, RestoreObject |
| Reads | `Range`, `partNumber`, `If-Match` / `If-None-Match` / `If-Modified-Since` / `If-Unmodified-Since`, `response-*` header overrides, `x-amz-checksum-mode` |
| Writes | user metadata, Content-Type / Cache-Control / Content-Disposition / Content-Encoding / Content-Language / Expires, storage classes, tags, ACLs, website redirects, conditional writes (`If-None-Match: *`, `If-Match`), `Content-MD5` and checksums CRC32, CRC32C, CRC64NVME, SHA1, SHA256 (header or trailer) |
| Multipart | CreateMultipartUpload, UploadPart, UploadPartCopy (ranges), CompleteMultipartUpload (composite and full-object checksums), AbortMultipartUpload |
| Versioning | Enabled / Suspended, version ids, `null` versions, delete markers, GET / DELETE of a version |
| Access | bucket policies (statements for `Principal: "*"` decide what unsigned requests may do), canned and grant ACLs, public access block, ownership controls (BucketOwnerEnforced), policy status, presigned URLs (V4 and V2), POST policy uploads |
| Bucket settings | tagging, CORS (applied to preflight and responses), lifecycle (applied: expiration by days or date, noncurrent version expiration, expired delete markers, abort incomplete uploads, transitions change the storage class), website (served at `/-/website/<bucket>/` and `<bucket>.s3-website.<domain>`: index and error documents, redirects, routing rules), default encryption, object lock (default retention), accelerate, request payment, logging, notification, replication, metrics, analytics, inventory, intelligent-tiering (stored and returned) |
| Object lock | retention (GOVERNANCE with `x-amz-bypass-governance-retention`, COMPLIANCE), legal hold, enforced on version deletes |

Not supported: S3 Select (`SelectObjectContent`), torrents, S3 Express directory buckets and access points; they
answer `NotImplemented`. Archive storage classes (GLACIER, DEEP_ARCHIVE) behave like AWS (`InvalidObjectState` until
RestoreObject), but a restore is immediate. Notifications, replication and logging are stored, not acted on.

## Web console

Open `http://127.0.0.1:9000/ui/` and sign in with an access key ID and its secret access key (or the
`S3_UI_PASSWORD`). Buckets: create (versioning, object lock), delete (optionally emptying it first), and every setting:
versioning, tags, default encryption, website hosting, object lock, block public access (*Block all* makes the
bucket private), bucket policy, object
ownership, ACL, CORS, lifecycle (with *Run lifecycle now*), unfinished multipart uploads, replication, notifications,
logging. Objects: browse folders, search, upload files and whole folders (drag and drop, with progress), create
folders, download, preview images, video, audio and text, share links (presigned GET or PUT, valid for a preset or any custom time from 1 second to 7 days), copy,
move and rename (also folders), delete, versions (download, delete, make current, show deleted objects), metadata and
storage class, tags, ACLs, object lock retention and legal hold.

The session lives in an `HttpOnly`, `SameSite=Strict` cookie for 12 hours and every console request carries a
token only the page knows, so other sites cannot use it. Ten failed sign-ins from one address lock that address out
for five minutes. The page sets a strict Content-Security-Policy and cannot be framed; downloads are sent as
attachments (only images, video, audio, plain text and PDF can be previewed inline).

## Security notes

- Run it behind TLS (a reverse proxy) when clients reach it over a network you do not trust: SigV4 protects the
  keys and the request from changes, not the object data.
- Every valid key has full access to every bucket; bucket policies and ACLs only decide what unsigned (anonymous)
  requests may do.
- Objects are plain files on disk, **not encrypted at rest** (SSE headers are accepted and returned): protect the
  disk, the volume and backups.

## Data layout

```
<S3_DATA_DIR>/buckets/<bucket>/bucket.json                       bucket settings
<S3_DATA_DIR>/buckets/<bucket>/objects/<h[:2]>/<h>.json          one record per key (h = sha256 of the key): its versions
<S3_DATA_DIR>/buckets/<bucket>/blobs/<id[:2]>/<id>               one file per object version
<S3_DATA_DIR>/buckets/<bucket>/uploads/<upload id>/              parts of an unfinished multipart upload
```

The Python and Node.js servers read and write the same layout, so you can switch between them on the same volume.
Writes are atomic (temporary file, then rename). Back up `/data` (`tar czf - -C /data .`), which is what pskit's
*Backup* does.

## Private buckets and share links

A bucket is private by default: requests without keys get `403 AccessDenied`. Anonymous access only happens when a
bucket policy allows `Principal: "*"` or an ACL is `public-read` (the bucket's, or an object's). To make sure nothing
in a bucket is reachable without keys, turn on all four *block public access* switches (console: *Block all*; pskit
studio: *Make private*): public policies and public object ACLs are then ignored, and the website endpoint refuses
too.

Presigned URLs still work on a private bucket, until they expire. Pick any expiry from 1 second to 7 days
(604800 seconds, the S3 maximum); a longer one, or a link used after it expired, is refused with `403`:

```python
url = s3.generate_presigned_url("get_object", Params={"Bucket": "photos", "Key": "2024/cat.jpg"}, ExpiresIn=90)
```

```bash
aws --endpoint-url http://127.0.0.1:9000 s3 presign s3://photos/2024/cat.jpg --expires-in 600
```
