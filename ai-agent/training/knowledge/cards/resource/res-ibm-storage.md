# IBM Cloud Object Storage bucket (`type: storage`)

Read and write objects in a Cloud Object Storage (COS) bucket from a handler.

**Not supported on IBM Cloud:** `storage` triggers (a function that runs when an object is uploaded). Watch the bucket
from the on-premises host with `driver: ibm_cos` instead, or have the uploader call
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

## 4. Use it in a handler

`requirements.txt`: `boto3`

## 5. Test

Console: bucket → **Objects** to see the uploaded object.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` IBM Cloud Code Engine does not support `storage` events in pskit `` | IBM Cloud has HTTP triggers only in pskit; drop the `storage` event |
| `managed storage resources ... not supported on IBM Cloud` | add `external: true` |
| `SignatureDoesNotMatch` | the credential has no HMAC keys, or the endpoint's region doesn't match the bucket |
| `AccessDenied` | the credential's role is *Reader*; create one with *Writer* |

```bash
export COS_ACCESS_KEY='...'
export COS_SECRET_KEY='...'
```
