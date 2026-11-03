# Resource: storage

A storage resource is a bucket or container of files. Use it when a file arriving should run a function, or when a handler reads and writes objects. An HTTP function can accept a request and a second function can process the object.

The guide index names the native service on each cloud: Amazon S3, an Azure Blob container, a Cloud Storage bucket, Alibaba Cloud OSS, Tencent Cloud COS, Huawei OBS, OCI Object Storage, IBM Cloud Object Storage, DigitalOcean Spaces, Cloudflare R2, and an on-premises directory or S3-compatible store.

`type: storage` may be managed. AWS, GCP, Azure, and on premises can keep a standalone managed bucket with no event. On Alibaba, Tencent, Huawei, Oracle, IBM, DigitalOcean, and Cloudflare, a managed storage resource is valid where a storage event uses it. Elsewhere set `external: true`. An external resource already exists. pskit passes its details and leaves the bucket in place.

Put it under `resources` with `type: storage`. `name` is the native bucket name. It defaults to the key, or to the last `:` segment of `connection.arn`. `functions` chooses who receives the binding. With the list omitted, every user function receives it. List a generated `<workflow>-orchestrator` when that function needs the binding. `connection` holds scalars. A `*_env` value is the name of a variable, and the handler reads `ctx.env` for the secret.

A storage event can point at the resource. The event uses the resource's native name, and `existing` follows `external`. The events table marks storage on AWS S3, GCP Cloud Storage, Azure Blob (created only), Alibaba OSS, Oracle Object Storage, Tencent COS, Huawei OBS, and an on-premises directory. Each record has `bucket`, `key`, `size`, and `action` (`created` or `deleted`).

`resource("uploads")` returns `native_name`, `external`, and connection values. The process also gets `PSKIT_RESOURCE_UPLOADS_TYPE`, `_NAME`, `_EXTERNAL`, one variable per connection key, and `_ARN`, `_URL`, or `_ID` when the provider knows them. AWS adds `ARN` for storage. Publishing uses `boto3` or `@aws-sdk/client-s3` on AWS, `google-cloud-storage` on GCP, and `azure-storage-blob` on Azure. Several other clouds use the S3 API with that cloud's endpoint and HMAC keys. On premises, `put_object` in `py_serverless_kit.runtime.onprem_host` writes through the host and follows the storage driver.

Open the form on its own line:

Resources > + Add resource

The guide and the tester are: Resources > How to use

Resources > Test

```
pskit resources usage uploads -p aws -s dev
pskit invoke -f on-upload -t storage -d '{"bucket": "uploads", "key": "in/a.txt"}'
pskit resources send uploads -d '{"key": "in/a.txt", "content": "test"}'
pskit logs -f --function on-upload
```

`pskit resources check uploads` checks that the resource is reachable. Azure storage events are created or updated blobs. A `deleted` list fails validation. Tencent COS names use the form `<name>-<APPID>`. On AWS, the bucket notification pskit writes replaces other notifications on that bucket.

Sources: `docs/resources.md#provider-support`, `docs/events.md#storage`, `docs/resource-usage.md#queues-buckets-and-topics`, `docs/resource-guides/README.md#adding-resources-step-by-step-guides`
