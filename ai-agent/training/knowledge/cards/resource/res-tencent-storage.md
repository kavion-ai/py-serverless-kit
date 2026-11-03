# Tencent Cloud COS bucket (`type: storage`)

Use a COS bucket you created in the console: run a function when an object is uploaded or deleted, read or write
objects from a handler, or both.

## 1. Create the bucket (console)

1. Console → **Cloud Object Storage (COS)** → **Bucket List** → **Create Bucket**.
2. **Region**: the same region as `provider.region` (the trigger is created for that region).
3. Name: lowercase letters, digits and dashes. COS appends `-<APPID>`; the full name (for example
   `invoices-1250000000`) is what pskit needs.
4. Access permissions: *Private Read/Write* → **Create**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Bucket name (with APPID) | COS → **Bucket List** → *Bucket Name* | `invoices-1250000000` |
| Region | bucket → **Overview** → *Region* | `ap-guangzhou` |
| Endpoint | bucket → **Overview** → *Domain Information* → default domain | `invoices-1250000000.cos.ap-guangzhou.myqcloud.com` |
| SecretId / SecretKey | CAM sub-user with `QcloudCOSDataReadOnly` (or a custom policy on this bucket), see README | `AKID...` |

## 3. Declare it in `pskit.yml`

- `storage: {resource: invoices}` adds a COS trigger (`cos:ObjectCreated:*`, and `cos:ObjectRemove:*` with
  `events: [created, deleted]`) to the function. No `tencentcloud_cos_bucket` is created.
- `pskit validate` rejects a bucket name without the `-<APPID>` suffix.
- Only reading or writing, no trigger? Drop the event and keep the resource.

## 4. Use it in a handler

`requirements.txt`: `cos-python-sdk-v5`

Records have `bucket`, `key` (without the `/<APPID>/<bucket>/` prefix COS sends), `size`, `action` and
`attributes["event_name"]` / `attributes["url"]`.

## 5. Test

Console: COS → **Bucket List** → `invoices-1250000000` → **Upload Files** into `incoming/`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `COS bucket ... must be '<name>-<APPID>'` | use the full bucket name shown in the Bucket List |
| Trigger never fires | the bucket is in another region than `provider.region`, or prefix/suffix don't match |
| `AccessDenied` from the SDK | the sub-user lacks COS permissions on the bucket |
| `KeyError: 'COS_SECRET_ID'` | add it under `provider.environment` |

```bash
export COS_SECRET_ID=AKID...
export COS_SECRET_KEY=...
```
