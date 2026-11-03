# Huawei OBS bucket (`type: storage`)

Use an OBS bucket you created in the console: run a function when objects are uploaded or deleted, read or write
objects from a handler, or both.

## 1. Create the bucket (console)

1. Console → **Object Storage Service** → **Create Bucket**.
2. Region: the same as `provider.region` (OBS triggers only work within one region). Bucket name: 3-63 lowercase
   letters, digits, `-` and `.`, globally unique (for example `acme-invoices`). Storage class *Standard*, bucket policy
   *Private* → **Create Now**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Bucket name | OBS → **Buckets** list | `acme-invoices` |
| Region | Buckets list → *Region* column | `cn-north-4` |
| Endpoint | bucket → **Overview** → *Basic Information* → *Endpoint* | `obs.cn-north-4.myhuaweicloud.com` |
| Access domain name | bucket → **Overview** → *Domain Name Details* | `acme-invoices.obs.cn-north-4.myhuaweicloud.com` |

## 3. Declare it in `pskit.yml`

```yaml
service: invoices

provider:
  name: huawei
  region: cn-north-4
  iam:
    role: pskit-functions          # agency with OBS permissions, see README.md

resources:
  invoices:
    type: storage
    external: true                 # created in the console; pskit never creates or deletes it
    name: acme-invoices
    connection:
      endpoint: https://obs.cn-north-4.myhuaweicloud.com

functions:
  on-invoice:
    handler: app.handlers.on_invoice
    events:
      - storage: {resource: invoices, prefix: incoming/, suffix: .pdf, events: [created]}
```

- `external: true` creates only the OBS trigger (`huaweicloud_fgs_trigger` of type `OBS`), no bucket.
- `prefix`, `suffix` and `events` (`created`, `deleted`) are applied natively by OBS.

## 4. Use it in a handler

`requirements.txt`: `esdk-obs-python`

```python
from obs import ObsClient
from py_serverless_kit import resource


def on_invoice(event, ctx):
    invoices = resource("invoices")
    client = ObsClient(
        access_key_id=ctx.raw.getSecurityAccessKey(),      # temporary credentials from the agency
        secret_access_key=ctx.raw.getSecuritySecretKey(),
        security_token=ctx.raw.getSecurityToken(),
        server=invoices["endpoint"],
    )
    for record in event.records:
        resp = client.getObject(invoices.native_name, record.key, loadStreamInMemory=True)
        ctx.logger.info("invoice", extra={"key": record.key, "size": len(resp.body.buffer)})
```

## 5. Test

```bash
pskit validate
pskit invoke -f on-invoice -d '{"key": "incoming/a.pdf"}'    # locally
pskit deploy
pskit trigger --list                                          # console steps for the OBS trigger
pskit logs -f --function on-invoice
```

Console: OBS → bucket → **Objects** → **Upload Object** into `incoming/`. FunctionGraph → function → **Monitoring →
Logs** shows the run.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails creating the trigger | bucket in another region, or the deploying user can't manage the bucket's event notifications |
| Trigger doesn't fire | the object doesn't match `prefix` / `suffix`; check **Triggers** on the function |
| `AccessDenied` in the handler | the agency lacks OBS permissions, or `iam.role` isn't set |
