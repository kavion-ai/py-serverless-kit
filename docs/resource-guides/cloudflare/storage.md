# Cloudflare R2 bucket (`type: storage`)

Read and write an R2 bucket from a Worker. pskit has **no storage trigger on Cloudflare**: a function can't run when an
object is uploaded (see [Reacting to uploads](#reacting-to-uploads)).

## 1. Create the bucket (dashboard)

1. Dashboard → **R2 Object Storage** → **Create bucket** (subscribe to R2 first if asked; there is a free tier).
2. Name: 3-63 lowercase letters, digits and dashes (for example `shop-uploads`); location *Automatic* → **Create bucket**.

## 2. Collect the values

| Value | Where | Example |
|---|---|---|
| Bucket name | **R2 Object Storage** → the bucket list | `shop-uploads` |
| Account ID | see [README](README.md#values-you-need-for-every-cloudflare-resource) | `0123...cdef` |
| S3 endpoint | bucket → **Settings** → *S3 API* | `https://<account id>.r2.cloudflarestorage.com` |
| Public URL (optional) | bucket → **Settings → Public access** → *R2.dev subdomain* or *Custom Domains* | `https://pub-xxxx.r2.dev` |
| S3 access keys (only for S3 clients outside Workers) | **R2 Object Storage → Manage R2 API Tokens** (*API* menu) → **Create API token** → *Object Read & Write*, apply to the bucket → copy *Access Key ID* and *Secret Access Key* (shown once) | |

A Worker uses a **binding** and needs no keys. The S3 keys are for other tools, such as the
[on-premises `r2` driver](../onprem/storage.md).

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID}
    workers_subdomain: my-team

resources:
  uploads:
    type: storage
    external: true              # required on Cloudflare
    name: shop-uploads
    connection:
      binding: UPLOADS          # tells the handler which binding to use
      public_url: https://pub-xxxx.r2.dev

functions:
  api:
    handler: app.handlers.api
    events: [{http: "POST /files/{name}"}]
    options:
      bindings:
        - {type: r2_bucket, name: UPLOADS, bucket_name: shop-uploads}
```

## 4. Use it in a handler

```python
from py_serverless_kit import resource


async def api(event, ctx):
    uploads = resource("uploads")
    bucket = getattr(ctx.raw, uploads["binding"])        # the R2 binding (ctx.raw is the Workers env)
    key = "in/" + event.http.path_params["name"]
    await bucket.put(key, event.http.text())
    obj = await bucket.get(key)
    return {"key": key, "size": obj.size, "url": f'{uploads["public_url"]}/{key}'}
```

Handlers on Cloudflare may be `async`; the binding methods (`put`, `get`, `delete`, `list`) return awaitables.

## Reacting to uploads

pskit can't attach a function to R2 event notifications. Options:

- poll the bucket from a `schedule` function (`await bucket.list()`),
- or let an [on-premises host](../onprem/storage.md) watch the bucket with the `r2` driver and run the function there.

## 5. Test

```bash
pskit validate
pskit deploy
curl -X POST --data 'hello' https://shop-dev-api.my-team.workers.dev/files/a.txt
```

Dashboard: **R2 Object Storage** → bucket → **Objects** shows `in/a.txt`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `does not support `storage` events` | remove the `storage:` event; see [Reacting to uploads](#reacting-to-uploads) |
| `managed storage resources ... not supported` | add `external: true` and create the bucket in the dashboard |
| `AttributeError: UPLOADS` at run time | the function has no `r2_bucket` binding: add it under that function's `options.bindings` |
| `'NoneType' object has no attribute` locally | `ctx.raw` is `None` outside Cloudflare; stub the binding in tests |
| Deploy fails with an authentication error | the API token needs R2 edit permission as well as Workers |
