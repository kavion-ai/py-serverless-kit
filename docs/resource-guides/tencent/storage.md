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
| SecretId / SecretKey | CAM sub-user with `QcloudCOSDataReadOnly` (or a custom policy on this bucket), see [README](README.md#values-you-need-for-every-tencent-cloud-resource) | `AKID...` |

```bash
export COS_SECRET_ID=AKID...
export COS_SECRET_KEY=...
```

## 3. Declare it in `pskit.yml`

```yaml
service: invoices

provider:
  name: tencent
  region: ap-guangzhou
  environment:
    COS_SECRET_ID: ${env:COS_SECRET_ID}
    COS_SECRET_KEY: ${env:COS_SECRET_KEY}

resources:
  invoices:                       # key used in code: resource("invoices")
    type: storage
    external: true                # created in the console; pskit never creates or deletes it
    name: invoices-1250000000     # must end with -<APPID>
    connection:
      region: ap-guangzhou
      secret_id_env: COS_SECRET_ID              # names of the variables, not the values
      secret_key_env: COS_SECRET_KEY

functions:
  on-invoice:
    handler: app.handlers.on_invoice
    events:
      - storage: {resource: invoices, prefix: incoming/, suffix: .pdf, events: [created]}
```

- `storage: {resource: invoices}` adds a COS trigger (`cos:ObjectCreated:*`, and `cos:ObjectRemove:*` with
  `events: [created, deleted]`) to the function. No `tencentcloud_cos_bucket` is created.
- `pskit validate` rejects a bucket name without the `-<APPID>` suffix.
- Only reading or writing, no trigger? Drop the event and keep the resource.

## 4. Use it in a handler

`requirements.txt`: `cos-python-sdk-v5`

```python
from qcloud_cos import CosConfig, CosS3Client
from py_serverless_kit import resource


def on_invoice(event, ctx):
    invoices = resource("invoices")
    config = CosConfig(Region=invoices["region"], SecretId=ctx.env[invoices["secret_id_env"]],
                       SecretKey=ctx.env[invoices["secret_key_env"]])
    client = CosS3Client(config)
    for record in event.records:
        data = client.get_object(Bucket=invoices.native_name, Key=record.key)["Body"].get_raw_stream().read()
        ctx.logger.info("invoice", extra={"key": record.key, "size": len(data)})
```

Records have `bucket`, `key` (without the `/<APPID>/<bucket>/` prefix COS sends), `size`, `action` and
`attributes["event_name"]` / `attributes["url"]`.

## 5. Test

```bash
pskit validate
pskit invoke -f on-invoice -t storage -d '{"key": "incoming/a.pdf"}'   # locally
pskit deploy
pskit trigger --list           # prints the coscli command and console steps for this trigger
printf test > a.pdf && coscli cp a.pdf cos://invoices-1250000000/incoming/a.pdf
pskit logs -f --function on-invoice
```

Console: COS → **Bucket List** → `invoices-1250000000` → **Upload Files** into `incoming/`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `COS bucket ... must be '<name>-<APPID>'` | use the full bucket name shown in the Bucket List |
| Trigger never fires | the bucket is in another region than `provider.region`, or prefix/suffix don't match |
| `AccessDenied` from the SDK | the sub-user lacks COS permissions on the bucket |
| `KeyError: 'COS_SECRET_ID'` | add it under `provider.environment` |
