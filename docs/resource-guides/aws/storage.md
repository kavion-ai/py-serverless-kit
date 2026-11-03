# Amazon S3 bucket (`type: storage`)

Use an S3 bucket you created in the console: run a function when objects are created or deleted, read or write objects
from a handler, or both.

## 1. Create the bucket (console)

1. Console → **S3** → **Create bucket**.
2. Region: the same as `provider.region`. Name: globally unique, 3-63 lowercase letters, digits, `.` and `-`
   (for example `acme-invoices-prod`).
3. Keep **Block all public access** on, *Bucket Versioning* as you need → **Create bucket**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Bucket name | S3 → **Buckets** | `acme-invoices-prod` |
| Region | Buckets list → *AWS Region* column | `eu-west-1` |
| Bucket ARN | the bucket → **Properties** → *Bucket overview* → *Amazon Resource Name (ARN)* | `arn:aws:s3:::acme-invoices-prod` |
| Encryption | the bucket → **Properties** → *Default encryption* | SSE-S3 (nothing to do) or SSE-KMS with a key ARN |
| Existing notifications | the bucket → **Properties** → *Event notifications* | should be empty, see below |

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: aws
  region: eu-west-1

resources:
  invoices:
    type: storage
    external: true
    name: acme-invoices-prod

functions:
  on-invoice:
    handler: app.handlers.on_invoice
    events:
      - storage: {resource: invoices, prefix: incoming/, suffix: .pdf, events: [created]}
```

What pskit does with it: looks the bucket up by name (`data "aws_s3_bucket"`), allows S3 to invoke the function,
creates an `aws_s3_bucket_notification` on the bucket, adds `s3:GetObject`, `PutObject`, `DeleteObject`, `ListBucket`
(bucket and `/*`) to the IAM role of bound functions, and sets `PSKIT_RESOURCE_INVOICES_ARN`.

> **Warning: S3 has one notification configuration per bucket.** The `aws_s3_bucket_notification` pskit creates
> replaces any event notifications already configured on the bucket (in the console or another stack), and
> `pskit remove` deletes it. If the bucket already sends notifications elsewhere, don't add a `storage` event: bind the
> bucket without an event, or route the existing notification to an SQS queue / SNS topic and trigger from that.

Only reading/writing, no trigger? Drop the `events` entry; the resource binding still grants the S3 permissions.

Bucket encrypted with **SSE-KMS**: add `kms:Decrypt` and `kms:GenerateDataKey` on the key under
`provider.iam.statements`.

## 4. Use it in a handler

```python
import boto3
from py_serverless_kit import resource

s3 = boto3.client("s3")


def on_invoice(event, ctx):
    invoices = resource("invoices")
    for record in event.records:
        obj = s3.get_object(Bucket=invoices.native_name, Key=record.key)
        data = obj["Body"].read()
        ctx.logger.info("invoice", extra={"key": record.key, "size": len(data), "action": record.action})
```

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send invoices -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -f --function on-invoice
```

Console: the bucket → **Create folder** `incoming` → **Upload** a `.pdf` into it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy: `couldn't find resource` for the bucket | wrong `name`, or the bucket is in another account |
| Notifications configured by others disappeared | see the warning above |
| Trigger never fires | check `prefix` / `suffix`; *Properties → Event notifications* should list the pskit entry |
| `AccessDenied` on `GetObject` | SSE-KMS key permissions, a bucket policy that denies the role, or own `iam.role` |
