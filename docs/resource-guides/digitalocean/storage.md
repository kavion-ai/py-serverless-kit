# DigitalOcean Spaces bucket (`type: storage`)

Read and write objects in a Spaces bucket (S3-compatible) from a handler.

**Not supported on DigitalOcean:** `storage` triggers. To run code when objects arrive, list the bucket from a
`schedule` function, or watch it from the [on-premises host](../../resources.md#storage-drivers) with `driver: spaces`.

## 1. Create the bucket (control panel)

1. Control panel → **Spaces Object Storage** → **Create Spaces Bucket**.
2. Datacenter region (for example `NYC3`), CDN off unless you need it, a unique name (for example `acme-invoices`),
   project → **Create a Spaces Bucket**.

## 2. Collect the values

| Value | Where in the control panel | Example |
|---|---|---|
| Bucket name | **Spaces Object Storage** → the list | `acme-invoices` |
| Region | the bucket's page header | `nyc3` |
| Endpoint | bucket → **Settings** → *Endpoint* (or `https://<region>.digitaloceanspaces.com`) | `https://nyc3.digitaloceanspaces.com` |
| Access key / secret | **Spaces Object Storage** → **Access Keys** → **Create Access Key** → *Limited access* to this bucket (Read/Write/Delete) or *Full access* → copy both; the secret is shown **once** | `DO00...` / `...` |

```bash
export SPACES_KEY='DO00...'
export SPACES_SECRET='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: invoices

provider:
  name: digitalocean
  region: nyc1
  options:
    namespace: fn-00000000-0000-0000-0000-000000000000
  environment:
    SPACES_KEY: ${env:SPACES_KEY}
    SPACES_SECRET: ${env:SPACES_SECRET}

resources:
  invoices:
    type: storage
    external: true                  # required on DigitalOcean
    name: acme-invoices
    connection:
      endpoint: https://nyc3.digitaloceanspaces.com
      region: nyc3
      access_key_env: SPACES_KEY
      secret_key_env: SPACES_SECRET

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
pskit resources send --list                # console steps and the doctl / s3 CLI commands
```

Control panel: the bucket → **Files** shows the uploaded object.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` DigitalOcean Functions does not support `storage` events in pskit `` | DigitalOcean has HTTP and schedule triggers only in pskit |
| `managed storage resources ... not supported` | add `external: true` |
| `SignatureDoesNotMatch` | key/secret swapped, or the endpoint region differs from the bucket's |
| `AccessDenied` | a *Limited access* key doesn't cover this bucket or permission |
