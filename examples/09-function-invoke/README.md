# 09 · Function-to-function invoke

`quote` (HTTP) calls two internal functions by their logical names:

```python
from py_serverless_kit import invoke

price = invoke("price-calculator", {"items": [...], "country": "DE"})        # returns the result
invoke("audit-log", {...}, asynchronous=True)                                 # fire-and-forget (AWS)
```

The target sees `event.type == "invoke"` and `event.data == payload`.

## How each cloud resolves the target

`invoke()` tries these in order:

1. **`PSKIT_ENDPOINT_<NAME>`** env var set (name upper-cased, `-` becomes `_`): HTTP POST to that
   URL. This works on **every** cloud and always wins.
2. **local** (`pskit invoke`, `pskit dev`, tests): in-process call, no network.
3. **AWS:** `lambda:Invoke` via boto3 on `<service>-<stage>-<name>`. boto3 is preinstalled in
   the Lambda runtime. The role needs `lambda:InvokeFunction`, granted in `provider.iam` here.
   `asynchronous=True` uses `InvocationType=Event`.
4. **GCP:** authenticated HTTPS call to `https://<region>-<project>.cloudfunctions.net/<name>`
   with an ID token from the metadata server.
5. **Everything else:** raises `InvokeError` and tells you which `PSKIT_ENDPOINT_*` variable to set.

| Cloud | Setup needed |
| --- | --- |
| AWS | IAM statement (shown in `pskit.yml`) |
| GCP | none |
| Azure, Alibaba, Tencent, Huawei, Oracle, IBM, DigitalOcean, Cloudflare | set `PSKIT_ENDPOINT_<NAME>` in the caller's `environment` (URL from `pskit info`) |

On Azure an invoke-only function is exposed at `/_pskit/invoke/<name>` and protected by a
function key. Put that URL, including `?code=<key>`, into `PRICE_CALCULATOR_URL` /
`AUDIT_LOG_URL` and redeploy. The `providers.azure` block wires them up.

> Prefer queues/topics (examples 04 and 06) for work that may be retried or slow.
> Use `invoke()` for quick request/response calls, and workflows (example 07) for multi-step processes.

## Run locally

```bash
pskit invoke -f quote -d '{"country": "DE", "items": [{"sku": "a", "qty": 2, "unit_price": 10}]}'
pskit invoke -f price-calculator -d '{"country": "IN", "items": [{"sku": "a", "qty": 1, "unit_price": 100}]}'
```

Expected output of the first command:

```json
{"status": 200, "body": {"quote": {"subtotal": 20.0, "tax": 3.8, "total": 23.8, "tax_rate": 0.19}, "request_id": "..."}}
```

## Deploy

```bash
pskit deploy
pskit deploy --provider gcp
pskit deploy --provider azure && pskit info --provider azure   # copy the URLs, then:
PRICE_CALCULATOR_URL=... AUDIT_LOG_URL=... pskit deploy --provider azure
```
