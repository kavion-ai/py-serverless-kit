# IBM Cloud Object Storage bucket (`type: storage`)

Read and write objects in a Cloud Object Storage (COS) bucket from a handler.

**Not supported on IBM Cloud:** `storage` triggers (a function that runs when an object is uploaded). Watch the bucket
from the [on-premises host](../../resources.md#storage-drivers) with `driver: ibm_cos` instead, or have the uploader call
the function's URL.

## 1. Create the bucket (console)

1. Console → **Catalog** → **Object Storage** → plan (*Standard*, or *Lite* to try) → name → **Create**.
2. In the instance → **Buckets** → **Create bucket** → *Create a custom bucket* (or the quick option).
3. Unique name (3-63 lowercase letters, digits, dots, dashes), resiliency *Regional*, location (for example `us-south`)
   → **Create bucket**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Bucket name | instance → **Buckets** | `acme-invoices` |
| Region | bucket → **Configuration** → *Location* | `us-south` |
| Public endpoint | bucket → **Configuration** → **Endpoints** → *Public* | `s3.us-south.cloud-object-storage.appdomain.cloud` |
| HMAC access key / secret | instance → **Service credentials** → **New credential** → role *Writer*, **Advanced options** → *Include HMAC Credential* **On** → **Add** → **View credentials** → `cos_hmac_keys.access_key_id` / `secret_access_key` | `...` |

HMAC keys let you use the standard S3 SDKs (`boto3`). For `ibm-cos-sdk` with IAM, use `apikey` and
`resource_instance_id` from the same credential instead.

```bash
export COS_ACCESS_KEY='...'
export COS_SECRET_KEY='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: invoices

provider:
  name: ibm
  region: us-south
  environment:
    COS_ACCESS_KEY: ${env:COS_ACCESS_KEY}
    COS_SECRET_KEY: ${env:COS_SECRET_KEY}

resources:
  invoices:
    type: storage
    external: true                 # required on IBM Cloud
    name: acme-invoices
    connection:
      endpoint: https://s3.us-south.cloud-object-storage.appdomain.cloud
      region: us-south
      access_key_env: COS_ACCESS_KEY
      secret_key_env: COS_SECRET_KEY

functions:
  upload:
    handler: app.handlers.upload
    events: [{http: POST /invoices}]
```

## 4. Use it in a handler

`requirements.txt`: `boto3`

```python
import boto3
from py_serverless_kit import resource


def upload(event, ctx):
    b = resource("invoices")
    s3 = boto3.client(
        "s3",
        endpoint_url=b["endpoint"],
        region_name=b["region"],
        aws_access_key_id=ctx.env[b["access_key_env"]],
        aws_secret_access_key=ctx.env[b["secret_key_env"]],
    )
    s3.put_object(Bucket=b.native_name, Key="incoming/a.json", Body=event.http.body)
    return {"stored": True}
```

## 5. Test

```bash
pskit validate
pskit invoke -f upload -d '{"id": 1}'      # locally, against the real bucket
pskit deploy
pskit info                                 # the function URL
pskit resources send --list                # console steps and the ibmcloud CLI command
```

Console: bucket → **Objects** to see the uploaded object.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` IBM Cloud Code Engine does not support `storage` events in pskit `` | IBM Cloud has HTTP triggers only in pskit; drop the `storage` event |
| `managed storage resources ... not supported on IBM Cloud` | add `external: true` |
| `SignatureDoesNotMatch` | the credential has no HMAC keys, or the endpoint's region doesn't match the bucket |
| `AccessDenied` | the credential's role is *Reader*; create one with *Writer* |
