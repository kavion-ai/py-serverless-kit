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
| AccessKey | RAM user with `AliyunOSSReadOnlyAccess` (or a custom policy on this bucket), see [README](README.md#values-you-need-for-every-alibaba-cloud-resource) | `LTAI...` |

```bash
export OSS_ACCESS_KEY_ID=LTAI...
export OSS_ACCESS_KEY_SECRET=...
```

## 3. Declare it in `pskit.yml`

```yaml
service: invoices

provider:
  name: alibaba
  region: cn-hangzhou
  environment:
    OSS_ACCESS_KEY_ID: ${env:OSS_ACCESS_KEY_ID}
    OSS_ACCESS_KEY_SECRET: ${env:OSS_ACCESS_KEY_SECRET}

resources:
  invoices:                       # key used in code: resource("invoices")
    type: storage
    external: true                # created in the console; pskit never creates or deletes it
    name: acme-invoices
    connection:
      endpoint: https://oss-cn-hangzhou.aliyuncs.com
      access_key_env: OSS_ACCESS_KEY_ID          # names of the variables, not the values
      secret_key_env: OSS_ACCESS_KEY_SECRET

functions:
  on-invoice:
    handler: app.handlers.on_invoice
    events:
      - storage: {resource: invoices, prefix: incoming/, suffix: .pdf, events: [created]}
```

- `storage: {resource: invoices}` adds an OSS trigger (`oss:ObjectCreated:*`, and `oss:ObjectRemoved:*` with
  `events: [created, deleted]`) on the existing bucket. No `alicloud_oss_bucket` is created.
- OSS allows only one trigger per bucket for overlapping prefix/suffix filters. If the bucket already has a trigger
  (check **Function Compute → the function → Triggers**, or the bucket's event notification rules), use distinct
  `prefix` / `suffix` values.
- Only reading or writing, no trigger? Drop the event and keep the resource; nothing else changes.

## 4. Use it in a handler

`requirements.txt`: `oss2`

```python
import oss2
from py_serverless_kit import resource


def on_invoice(event, ctx):
    invoices = resource("invoices")
    auth = oss2.Auth(ctx.env[invoices["access_key_env"]], ctx.env[invoices["secret_key_env"]])
    bucket = oss2.Bucket(auth, invoices["endpoint"], invoices.native_name)
    for record in event.records:
        data = bucket.get_object(record.key).read()
        ctx.logger.info("invoice", extra={"key": record.key, "size": len(data)})
```

Records have `bucket`, `key`, `size`, `action` (`created` / `deleted`) and `attributes["event_name"]`.

## 5. Test

```bash
pskit validate
pskit invoke -f on-invoice -t storage -d '{"key": "incoming/a.pdf"}'   # locally
pskit deploy
pskit trigger --list            # prints the ossutil command and console steps for this trigger
printf test > a.pdf && ossutil cp a.pdf oss://acme-invoices/incoming/a.pdf
pskit logs -f --function on-invoice
```

Console: OSS → **Buckets** → `acme-invoices` → **Objects** → **Upload Object** into `incoming/`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails creating the OSS trigger, "conflict" / "already exists" | another trigger covers the same prefix/suffix; change the filters |
| Trigger never fires | the bucket is in another region than `provider.region` |
| `AccessDenied` from `oss2` | the RAM user lacks permission on the bucket, or the keys are swapped |
| `KeyError: 'OSS_ACCESS_KEY_ID'` | add it under `provider.environment` |
