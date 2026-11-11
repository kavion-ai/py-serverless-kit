"""An Amazon S3 compatible server (Python, standard library only).

boto3, the AWS SDKs (JavaScript v3, Java, Go, ...), the AWS CLI (``aws s3`` and ``aws s3api``), rclone, s3cmd and
pskit's ``s3`` storage driver talk to it unchanged: point their endpoint at this server and sign with an access key /
secret key it knows. Requests are checked with AWS Signature Version 4 (headers, presigned URLs, streaming chunk
signatures, browser POST policies) or Version 2, so a wrong secret key is refused.

Buckets: create / delete / head / list, location, versioning (Enabled / Suspended), tags, policies (evaluated for
anonymous and signed requests), ACLs (canned and grants), CORS (applied), lifecycle rules (applied: expiration,
noncurrent versions, delete markers, incomplete uploads, transitions), static website hosting, object lock
(governance / compliance retention, legal hold), public access block, ownership controls, default encryption, and
logging, notification, replication, accelerate, request payment, metrics, analytics, inventory and intelligent-tiering
configurations (stored and returned).

Objects: put / get / head / delete / copy, ranges, part numbers, conditional requests (If-Match, If-None-Match,
If-Modified-Since, If-Unmodified-Since, also on writes), user metadata and standard headers, response header
overrides, tags, ACLs, storage classes, checksums (CRC32, CRC32C, CRC64NVME, SHA1, SHA256, Content-MD5), version ids
and delete markers, multi-object delete, GetObjectAttributes, restore (archive storage classes), multipart uploads
(upload part copy, list parts / uploads, composite and full-object checksums) and SSE headers (accepted and returned;
the data is not encrypted at rest).

A web console (``/ui/``) browses buckets and folders, uploads (drag and drop), downloads, copies, moves, deletes,
shows versions, edits metadata and tags, makes share links and edits every bucket setting. It signs in with an access
key and its secret key (or ``S3_UI_PASSWORD``) and keeps the session in an HttpOnly cookie.

Settings (environment):

``S3_ACCESS_KEY_ID`` / ``S3_SECRET_ACCESS_KEY``
    The credentials clients sign with (``aws_access_key_id`` / ``aws_secret_access_key``).
``S3_CREDENTIALS``
    More credentials: ``id1:secret1,id2:secret2``.
``S3_AUTH``
    ``sigv4`` (default: Signature Version 4 and 2) or ``off`` (no authentication: development only).
``S3_PORT`` (9000), ``S3_BIND`` (0.0.0.0), ``S3_DATA_DIR`` (./data), ``S3_REGION`` (us-east-1),
``S3_ACCOUNT_ID`` (000000000000)
    Where it listens, where the data lives, and the region / account it reports.
``S3_DOMAIN`` (``localhost``)
    Comma-separated domains for virtual-hosted style requests (``<bucket>.<domain>``).
``S3_UI`` (``on``), ``S3_UI_PASSWORD``, ``S3_UI_DIR``
    The web console, a console password other than the secret key, and the folder holding the console's files.
``S3_MAX_OBJECT_SIZE`` (5 GiB), ``S3_MIN_PART_SIZE`` (5 MiB), ``S3_LIFECYCLE_INTERVAL`` (3600 seconds),
``S3_LIFECYCLE_DAY_SECONDS`` (86400)
    Limits and the lifecycle sweep (a shorter "day" makes lifecycle rules testable).

The data lives under ``S3_DATA_DIR/buckets``: ``bucket.json`` per bucket, one JSON record per key and one file per
object version. The Node.js server (``../nodejs/server.js``) reads and writes the same layout.

The modules are laid out in ``aws/s3/ARCHITECTURE.md``. ``python server.py --check`` exits 0 when the server answers
on ``/-/health`` (a container health check).
"""
