# 08 · Multi-cloud: same code, every provider

`app/handlers.py` deploys unchanged to all eleven providers, including an on-premises
host. Only the configuration differs, and you can organise it in either of two ways.

## Option A: one file with `providers:` overrides

`pskit.yml` holds the shared definition plus a `providers.<cloud>` block per cloud:

```bash
pskit deploy                          # provider.name (aws)
pskit deploy --provider gcp
pskit deploy --provider azure
pskit deploy --provider alibaba
pskit deploy --provider tencent
pskit deploy --provider huawei
pskit deploy --provider oracle
pskit deploy --provider ibm
pskit deploy --provider digitalocean
pskit deploy --provider cloudflare
pskit deploy --provider onprem
```

## Option B: one small file per cloud with `extends:`

```bash
pskit deploy -c pskit.aws.yml
pskit deploy -c pskit.gcp.yml
pskit deploy -c pskit.azure.yml
```

Each child file names the cloud in `provider.name` and sets its own values under
`providers.<cloud>`, so they take precedence over the parent's block for that cloud.

Every combination gets its own Terraform workspace (`.pskit/<provider>-<stage>/`), so
the same service can be live on several clouds at once. `pskit dashboard` then shows all
of them on one page.

## What each cloud needs

| Cloud | Tier | Required settings | Notes |
| --- | --- | --- | --- |
| aws | stable | AWS credentials | HTTP API, EventBridge Scheduler |
| gcp | stable | `options.project` | Cloud Functions gen2, Cloud Scheduler |
| azure | stable | `options.subscription_id` | Function App (Linux consumption) |
| alibaba | beta | `ALICLOUD_*` credentials | FC 3.0 HTTP + timer triggers |
| tencent | beta | `TENCENTCLOUD_*` credentials | SCF + API Gateway; Python 3.9/3.10 |
| huawei | beta | `options.apig_instance_id` | FunctionGraph + dedicated APIG |
| oracle | experimental | `compartment_id`, `subnet_ids`, `image` or `image_repository` | container images; no schedules |
| ibm | beta | `IC_API_KEY` | Code Engine functions; HTTP only, Python 3.11, max 120 s |
| digitalocean | beta | `options.namespace`, `doctl` on PATH | deployed with `doctl serverless` |
| cloudflare | experimental | `options.account_id` | Python Workers (stdlib + Pyodide packages only) |
| onprem | experimental | nothing (optional `options.port`) | a Python process on this machine; queues, storage and topics are directories |

Where a cloud lacks a feature, the override says so explicitly. For example
`functions.ticker.events: []` on IBM and Oracle deploys `ticker` without a schedule
instead of failing. Run `pskit providers` for the full capability matrix, and
`pskit validate --provider <cloud>` to check your config before deploying.

The placeholder values (`${env:X, default}`) let `pskit validate` run without credentials.
Export the real values before `pskit deploy`.

## Run locally

```bash
pskit dev
curl localhost:3000/whoami
curl -X POST "localhost:3000/echo?debug=1" -d '{"hello": "world"}'
pskit invoke -f ticker
```

`whoami` returns `"provider": "local"` locally and `"aws"`, `"gcp"`, ... once deployed.
That field is the only thing that changes.
