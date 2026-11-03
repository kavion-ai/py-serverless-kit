# Amazon S3 compatible server: API reference

Search terms: S3 API coverage, supported S3 operations, SigV4, SigV2, aws-chunked, presigned URL, versioning, multipart
upload, bucket policy, lifecycle rules, object lock, S3 error codes, S3_DOMAIN, S3_CREDENTIALS, S3_AUTH

This page lists what pskit's Amazon S3 compatible server (`aws/s3`, services `s3` and `s3-node`) supports, read from
the request routing in `python/server.py` and `nodejs/server.js`. The two implementations route the same
sub-resources the same way and return the same error codes; nothing below is specific to one of them. For creating
the server and client examples see [s3.md](s3.md).

## S3 server authentication (SigV4 and SigV2)

The S3 server checks every request with AWS Signature Version 4 or Version 2, unless `S3_AUTH=off`. Accepted forms:

| Form | How the server recognises it |
|---|---|
| SigV4 header | `Authorization: AWS4-HMAC-SHA256 Credential=...` |
| SigV4 presigned URL | `X-Amz-Signature` in the query; `X-Amz-Expires` 1 to 604800 seconds (7 days) |
| SigV4 streaming upload | `x-amz-content-sha256`: `STREAMING-AWS4-HMAC-SHA256-PAYLOAD`, `STREAMING-AWS4-HMAC-SHA256-PAYLOAD-TRAILER` or `STREAMING-UNSIGNED-PAYLOAD-TRAILER` (chunk and trailer signatures and trailing checksums are checked) |
| Unsigned payload | `x-amz-content-sha256: UNSIGNED-PAYLOAD` |
| SigV2 header | `Authorization: AWS <key>:<signature>` |
| SigV2 presigned URL | `AWSAccessKeyId` and `Signature` in the query |
| Browser POST policy | `POST /<bucket>` with `multipart/form-data` and a signed policy |
| Anonymous | no signature: allowed only where a bucket policy or a `public-read` ACL allows it |

Rules the S3 server applies:

- The request time (`x-amz-date` or `Date`) must be within **15 minutes** of the server's clock, else
  `RequestTimeTooSkewed`.
- The credential scope's service must be `s3` (or `s3-object-lambda`) and its date must match the request date. Any
  region name is accepted.
- `SignedHeaders` must include `host` and only headers that were sent.
- Every valid key has full access to every bucket. Bucket policies and ACLs only decide what unsigned (anonymous)
  requests may do.

## S3 server bucket operations

The S3 server supports these bucket operations (the query sub-resource it routes on is in brackets):

| Area | Operations |
|---|---|
| Buckets | CreateBucket (location constraint, canned ACL, `x-amz-bucket-object-lock-enabled`, `x-amz-object-ownership`), DeleteBucket, HeadBucket, ListBuckets (`prefix`, `max-buckets`, `continuation-token`, `bucket-region`), GetBucketLocation (`?location`) |
| Listing | ListObjects, ListObjectsV2 (`list-type=2`: prefix, delimiter, start-after, continuation tokens, `encoding-type=url`, fetch-owner), ListObjectVersions (`?versions`), ListMultipartUploads (`?uploads`) |
| Versioning | Get/PutBucketVersioning (`?versioning`): Enabled / Suspended |
| Access | Get/Put/DeleteBucketPolicy (`?policy`), GetBucketPolicyStatus (`?policyStatus`), Get/PutBucketAcl (`?acl`), Get/Put/DeletePublicAccessBlock (`?publicAccessBlock`), Get/Put/DeleteBucketOwnershipControls (`?ownershipControls`) |
| Applied settings | CORS (`?cors`, used for preflight and responses), lifecycle (`?lifecycle`), website (`?website`), default encryption (`?encryption`), object lock configuration (`?object-lock`), tagging (`?tagging`) |
| Stored and returned only | accelerate, requestPayment, logging, notification, replication, metrics, analytics, inventory, intelligent-tiering |
| Batch | DeleteObjects (`POST ?delete`, quiet mode, version ids) |

## S3 server object operations

The S3 server supports these object operations:

| Area | Operations and features |
|---|---|
| Objects | PutObject, GetObject, HeadObject, DeleteObject, CopyObject (`x-amz-copy-source`, metadata and tagging directives, copy conditions), GetObjectAttributes (`?attributes`), RestoreObject (`POST ?restore`) |
| Reads | `Range`, `partNumber`, `If-Match` / `If-None-Match` / `If-Modified-Since` / `If-Unmodified-Since`, `response-*` header overrides, `x-amz-checksum-mode` |
| Writes | user metadata, Content-Type / Cache-Control / Content-Disposition / Content-Encoding / Content-Language / Expires, storage classes, tags, ACLs, website redirects, conditional writes (`If-None-Match: *`, `If-Match`), `Content-MD5`, checksums CRC32, CRC32C, CRC64NVME, SHA1, SHA256 (header or trailer) |
| Multipart | CreateMultipartUpload (`POST ?uploads`), UploadPart, UploadPartCopy (ranges), CompleteMultipartUpload (composite and full-object checksums), AbortMultipartUpload, ListParts |
| Versions | version ids, `null` versions, delete markers, GET / HEAD / DELETE of a version (`versionId`) |
| Object settings | Get/PutObjectTagging, DeleteObjectTagging (`?tagging`), Get/PutObjectAcl (`?acl`), Get/PutObjectRetention (`?retention`: GOVERNANCE with `x-amz-bypass-governance-retention`, COMPLIANCE), Get/PutObjectLegalHold (`?legal-hold`) |
| Encryption headers | SSE headers are accepted and returned; the data is **not** encrypted at rest |

Archive storage classes (GLACIER, DEEP_ARCHIVE) behave like AWS: GetObject answers `InvalidObjectState` until
RestoreObject, but a restore is immediate.

## Features the S3 server does not support

The S3 server answers `NotImplemented` (HTTP 501) for:

- S3 Select (`SelectObjectContent`, `?select`) and S3 Select restore requests;
- torrents (`GetObjectTorrent`, `?torrent`);
- copying from an access point ARN, and S3 Express directory buckets;
- `If-None-Match` on a write with a value other than `*`;
- other `x-amz-content-sha256` streaming modes than the three listed above.

Notifications, replication and logging configurations are stored and returned, not acted on. Bucket policies are
evaluated for anonymous requests only.

## S3 server lifecycle rules, website hosting and public access

The S3 server applies these bucket settings itself:

- **Lifecycle**: a background sweep runs every `S3_LIFECYCLE_INTERVAL` seconds (default 3600; the first one a minute
  after start) and applies expiration by days or date, noncurrent version expiration, expired delete markers, abort of
  incomplete multipart uploads, and transitions (they change the storage class). `S3_LIFECYCLE_DAY_SECONDS` shortens a
  "day" for tests. The console's *Run lifecycle now* sweeps at once.
- **Website**: served at `http://<host>:<port>/-/website/<bucket>/` and at `<bucket>.s3-website.<domain>` (index and
  error documents, redirects, routing rules).
- **Private by default**: unsigned requests get `403 AccessDenied` unless a bucket policy allows `Principal: "*"` or an
  ACL is `public-read`. With all four *block public access* switches on (console: *Block all*; studio: *Make
  private*), public policies and public object ACLs are ignored and the website endpoint refuses too.
- **Presigned URLs** work on a private bucket until they expire.

## S3 server settings

The S3 server reads these environment variables (pskit sets the first group itself, see
[README.md](README.md#how-pskit-runs-the-aws-compatible-servers)):

| Variable | Default | Meaning |
|---|---|---|
| `S3_ACCESS_KEY_ID` | `pskit` | access key ID clients sign with |
| `S3_SECRET_ACCESS_KEY` | (required) | its secret access key; also the console password |
| `S3_CREDENTIALS` | | more keys: `id1:secret1,id2:secret2` |
| `S3_AUTH` | `sigv4` | `off` turns authentication off (development only) |
| `S3_PORT` / `S3_BIND` | `9000` / `0.0.0.0` | where it listens |
| `S3_DATA_DIR` | `./data` (`/data` in the images) | holds the buckets |
| `S3_REGION` / `S3_ACCOUNT_ID` | `us-east-1` / `000000000000` | default bucket region; account checked against `x-amz-expected-bucket-owner` |
| `S3_DOMAIN` | `localhost` | comma-separated domains for virtual-hosted style (`<bucket>.<domain>`) |
| `S3_UI` | `on` | `off` removes the web console |
| `S3_UI_PASSWORD` | | a console password other than the secret keys |
| `S3_UI_FILE` | | path of another console page to serve instead of `index.html` |
| `S3_MAX_OBJECT_SIZE` | 5 GiB | largest single PUT, part or copy |
| `S3_MIN_PART_SIZE` | 5 MiB | smallest multipart part except the last |
| `S3_LIFECYCLE_INTERVAL` | `3600` | seconds between lifecycle sweeps |
| `S3_LIFECYCLE_DAY_SECONDS` | `86400` | length of a lifecycle "day" |

Fixed limits: 10,000 parts per upload, 256 MiB per browser POST upload, 4 MiB per XML request body, 1024-byte keys.
The pskit one-click service does not expose the optional variables (`S3_DOMAIN`, `S3_CREDENTIALS`, `S3_UI_PASSWORD`,
limits); run the server standalone to change them.

Command-line flags: `server.py --check` / `server.js --check` exits 0 when `/-/health` answers (the container health
check). Health endpoints `/-/health` and `/-/healthz` need no signature; `/health` and `/healthz` answer the same when
the request carries no `Authorization` header and no query.

## S3 server error codes

The S3 server answers errors in the S3 XML format with these codes (both implementations):

| HTTP | Codes |
|---|---|
| 400 | `AuthorizationHeaderMalformed`, `AuthorizationQueryParametersError`, `BadDigest`, `BadRequest`, `EntityTooLarge`, `EntityTooSmall`, `IncompleteBody`, `InvalidArgument`, `InvalidBucketAclWithObjectOwnership`, `InvalidBucketName`, `InvalidDigest`, `InvalidPart`, `InvalidPartOrder`, `InvalidPartNumber`, `InvalidRequest`, `InvalidStorageClass`, `InvalidTag`, `KeyTooLongError`, `MalformedPOSTRequest`, `MalformedPolicy`, `MalformedXML`, `MetadataTooLarge`, `AccessControlListNotSupported` |
| 403 | `AccessDenied`, `InvalidAccessKeyId`, `SignatureDoesNotMatch`, `RequestTimeTooSkewed`, `CORSResponse`, `InvalidObjectState` |
| 404 | `NoSuchBucket`, `NoSuchKey`, `NoSuchVersion`, `NoSuchUpload`, `NoSuchBucketPolicy`, `NoSuchTagSet`, `NoSuchConfiguration`, `NoSuchObjectLockConfiguration` |
| 405 | `MethodNotAllowed` |
| 409 | `BucketAlreadyOwnedByYou`, `BucketNotEmpty`, `InvalidBucketState` |
| 411 | `MissingContentLength` |
| 412 / 304 / 416 | `PreconditionFailed`, `NotModified`, `InvalidRange` |
| 429 | `SlowDown` (console only: ten failed sign-ins from one address) |
| 500 / 501 | `InternalError`, `NotImplemented` |

The HTTP status shown is the usual one for the code; check the response for the exact status.

## S3 server data layout and backups

The S3 server stores data under `S3_DATA_DIR` (`/data` in the container):

```text
<S3_DATA_DIR>/buckets/<bucket>/bucket.json                       bucket settings
<S3_DATA_DIR>/buckets/<bucket>/objects/<h[:2]>/<h>.json          one record per key (h = sha256 of the key): its versions
<S3_DATA_DIR>/buckets/<bucket>/blobs/<id[:2]>/<id>               one file per object version
<S3_DATA_DIR>/buckets/<bucket>/uploads/<upload id>/              parts of an unfinished multipart upload
```

Writes are atomic (temporary file, then rename). The Python and Node.js servers use the same layout. Objects are plain
files, not encrypted at rest: protect the disk, the volume and the backups. pskit's *Backup* (studio) and
`pskit resources onprem backup <key>` run `tar czf - -C /data .` in the container and save a `.tar.gz`.

## See also

- [s3.md](s3.md): create the server, console, clients, troubleshooting
- [README.md](README.md): the AWS-compatible servers
- [secretsmanager.md](secretsmanager.md)
- [../services/s3.md](../services/s3.md)
- Amazon S3 API reference: <https://docs.aws.amazon.com/AmazonS3/latest/API/Welcome.html>
