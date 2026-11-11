"use strict";
// An Amazon S3 compatible server (Node.js 18+, no dependencies). The code is in lib/ (see ../ARCHITECTURE.md).
//
// boto3, the AWS SDKs (JavaScript v3, Java, Go, ...), the AWS CLI (`aws s3` and `aws s3api`), rclone, s3cmd and
// pskit's `s3` storage driver talk to it unchanged: point their endpoint at this server and sign with an access key /
// secret key it knows. Requests are checked with AWS Signature Version 4 (headers, presigned URLs, streaming chunk
// signatures, browser POST policies) or Version 2, so a wrong secret key is refused.
//
// Buckets: create / delete / head / list, location, versioning (Enabled / Suspended), tags, policies (principals,
// actions, resources and conditions, for signed and anonymous requests), ACLs (canned and grants), CORS (applied),
// lifecycle rules (applied: expiration, noncurrent versions, delete markers, incomplete uploads, transitions), static
// website hosting, object lock (governance / compliance retention, legal hold), public access block, ownership
// controls, default encryption, and logging, notification, replication, accelerate, request payment, metrics,
// analytics, inventory and intelligent-tiering configurations (stored and returned).
//
// Objects: put / get / head / delete / copy, ranges, part numbers, conditional requests (also on writes), user
// metadata and standard headers, response header overrides, tags, ACLs, storage classes, checksums (CRC32, CRC32C,
// CRC64NVME, SHA1, SHA256, Content-MD5), version ids and delete markers, multi-object delete, GetObjectAttributes,
// restore (archive storage classes), multipart uploads (upload part copy, list parts / uploads, composite and
// full-object checksums) and SSE headers (accepted and returned; the data is not encrypted at rest).
//
// A web console (/ui/) browses buckets and folders, uploads, downloads, copies, moves, deletes, shows versions, edits
// metadata and tags, makes share links and edits every bucket setting. It signs in with an access key and its secret
// key (or S3_UI_PASSWORD) and keeps the session in an HttpOnly cookie.
//
// Settings (environment), the same as the Python server (../python/server.py):
//   S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY   the credentials clients sign with
//   S3_CREDENTIALS                            more credentials: id1:secret1,id2:secret2
//   S3_AUTH                                   sigv4 (default: Signature Version 4 and 2) or off (development only)
//   S3_PORT (9000), S3_BIND (0.0.0.0), S3_DATA_DIR (./data), S3_REGION (us-east-1), S3_ACCOUNT_ID (000000000000)
//   S3_DOMAIN (localhost)                     comma-separated domains for virtual-hosted style (<bucket>.<domain>)
//   S3_UI (on), S3_UI_PASSWORD, S3_UI_DIR     the web console, a console password, and the console's files
//                                             (default <server dir>/ui, else <server dir>/../ui)
//   S3_MAX_OBJECT_SIZE (5 GiB), S3_MIN_PART_SIZE (5 MiB), S3_LIFECYCLE_INTERVAL (3600 seconds),
//   S3_LIFECYCLE_DAY_SECONDS (86400)          limits and the lifecycle sweep (a shorter "day" makes rules testable)
//
// The data lives under S3_DATA_DIR/buckets: bucket.json per bucket, one JSON record per key and one file per object
// version, in the same layout and formats as the Python server's, so the two servers can take turns on one data
// directory. `node server.js --check` exits 0 when the server answers on /-/health (a container health check).

require("./lib/main").main();
