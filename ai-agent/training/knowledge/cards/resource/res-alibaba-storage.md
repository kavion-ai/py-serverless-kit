# Alibaba Cloud OSS bucket (`type: storage`)

Use an OSS bucket you created in the console: run a function when an object is uploaded or deleted, read or write
objects from a handler, or both.

## 1. Create the bucket (console)

1. Console → **Object Storage Service (OSS)** → **Buckets** → **Create Bucket**.
2. Bucket name: 3-63 characters, lowercase letters, digits and dashes, globally unique (for example `acme-invoices`).
3. **Region**: the same region as `provider.region` (the trigger is created for that region).
4. ACL: *Private* → **OK**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Bucket name | OSS → **Buckets** | `acme-invoices` |
| Region | bucket → **Overview** → *Region* | `cn-hangzhou` |
| Endpoint | bucket → **Overview** → *Port* / *Access Port* table: *Internet* and *ECS (internal network)* endpoints | `oss-cn-hangzhou.aliyuncs.com`, `oss-cn-hangzhou-internal.aliyuncs.com` |
| AccessKey | RAM user with `AliyunOSSReadOnlyAccess` (or a custom policy on this bucket), see README | `LTAI...` |

## 3. Declare it in `pskit.yml`

- `storage: {resource: invoices}` adds an OSS trigger (`oss:ObjectCreated:*`, and `oss:ObjectRemoved:*` with
  `events: [created, deleted]`) on the existing bucket. No `alicloud_oss_bucket` is created.
- OSS allows only one trigger per bucket for overlapping prefix/suffix filters. If the bucket already has a trigger
  (check **Function Compute → the function → Triggers**, or the bucket's event notification rules), use distinct
  `prefix` / `suffix` values.
- Only reading or writing, no trigger? Drop the event and keep the resource; nothing else changes.

## 4. Use it in a handler

`requirements.txt`: `oss2`

Records have `bucket`, `key`, `size`, `action` (`created` / `deleted`) and `attributes["event_name"]`.

## 5. Test

Console: OSS → **Buckets** → `acme-invoices` → **Objects** → **Upload Object** into `incoming/`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails creating the OSS trigger, "conflict" / "already exists" | another trigger covers the same prefix/suffix; change the filters |
| Trigger never fires | the bucket is in another region than `provider.region` |
| `AccessDenied` from `oss2` | the RAM user lacks permission on the bucket, or the keys are swapped |
| `KeyError: 'OSS_ACCESS_KEY_ID'` | add it under `provider.environment` |

```bash
export OSS_ACCESS_KEY_ID=LTAI...
export OSS_ACCESS_KEY_SECRET=...
```
