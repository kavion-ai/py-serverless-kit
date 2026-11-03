# DigitalOcean Spaces bucket (`type: storage`)

Read and write objects in a Spaces bucket (S3-compatible) from a handler.

**Not supported on DigitalOcean:** `storage` triggers. To run code when objects arrive, list the bucket from a
`schedule` function, or watch it from the on-premises host with `driver: spaces`.

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

## 4. Use it in a handler

`requirements.txt`: `boto3`

## 5. Test

Control panel: the bucket → **Files** shows the uploaded object.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` DigitalOcean Functions does not support `storage` events in pskit `` | DigitalOcean has HTTP and schedule triggers only in pskit |
| `managed storage resources ... not supported` | add `external: true` |
| `SignatureDoesNotMatch` | key/secret swapped, or the endpoint region differs from the bucket's |
| `AccessDenied` | a *Limited access* key doesn't cover this bucket or permission |

```bash
export SPACES_KEY='DO00...'
export SPACES_SECRET='...'
```
