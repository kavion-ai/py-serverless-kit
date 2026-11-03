# Resource: AWS S3 bucket

On AWS, `type: storage` is an Amazon S3 bucket. Use an existing bucket when objects should start a function, or when a handler reads and writes objects. A managed bucket is also allowed on AWS, including a standalone bucket with no event. The guide walks through a bucket you already created.

Create it in S3 in the same region as `provider.region`. Names are globally unique, 3–63 characters, lowercase letters, digits, `.`, and `-`. Leave Block all public access on. Collect the bucket name, the region, and the bucket ARN. For SSE-KMS, collect the key ARN.

Declare `type: storage`, `external: true`, and `name` set to the bucket name. A storage event can set `resource`, `prefix`, `suffix`, and `events: [created]`. pskit looks the bucket up with `data.aws_s3_bucket`, allows S3 to invoke the function, writes `aws_s3_bucket_notification`, adds `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, and `s3:ListBucket` on the bucket and `/*` to the role of bound functions, and sets `PSKIT_RESOURCE_<KEY>_ARN`. Drop the event when the function only reads and writes. The binding still grants those S3 actions.

S3 keeps one notification configuration per bucket. The configuration pskit writes replaces notifications already on the bucket, and `pskit remove` deletes that configuration. When the bucket already notifies another stack, bind it with no storage event, or trigger from the queue or topic that already receives those notifications.

`boto3` is in the Lambda Python runtime. Add it to `requirements.txt` to pin a version. Node.js uses `@aws-sdk/client-s3`. Call `get_object` with `Bucket=resource("invoices").native_name` and `Key=record.key`. SSE-KMS needs `kms:Decrypt` and `kms:GenerateDataKey` in `provider.iam.statements`. A role you set with `iam.role` is left unchanged.

Open:

Resources > + Add resource

Resources > Browse account

```
pskit validate
pskit resources send invoices -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -f --function on-invoice
```

A deploy error `couldn't find resource` means the name is wrong or the bucket is in another account.

Sources: `docs/resource-guides/aws/storage.md#amazon-s3-bucket-type-storage`, `docs/resources.md#aws-iam`
