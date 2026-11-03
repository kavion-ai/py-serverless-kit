# Example: 09-function-invoke

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: On AWS invoke() needs lambda:InvokeFunction on the sibling functions. Their names are <service>-<stage>-<function>. invoke() calls https://<region>-<project>.cloudfunctions.net/<name> with an ID token. The functions share pskit's invoker service account. Azure has no SDK-level "invoke function" API, so give the caller the URLs. Fill them in from `pskit info` after the first deploy (or in CI).

# 09 · Function-to-function invoke

`quote` (HTTP) calls two internal functions by their logical names:

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

Expected output of the first command:
