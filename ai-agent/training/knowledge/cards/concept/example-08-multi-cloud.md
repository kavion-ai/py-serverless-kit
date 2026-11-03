# Example: 08-multi-cloud

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.aws.yml, pskit.azure.yml, pskit.gcp.yml, pskit.yml, requirements.txt. Comments in pskit.yml: One file for every provider, including an on-premises host. Pick the target with: pskit deploy -> provider.name below (aws) pskit deploy --provider gcp -> applies providers.gcp on top Everything under `providers.<cloud>` is merged over the base config only when that cloud is selected. Top-level ProviderConfig keys (region, runtime, timeout, options, ...) may be written directly under the cloud name.
# 08 · Multi-cloud: same code, every provider `app/handlers.py` deploys unchanged to all

eleven providers, including an on-premises host. Only the configuration differs, and you can organise it in either of two ways.
## Option A: one file with `providers:` overrides `pskit.yml` holds the shared definition

plus a `providers.<cloud>` block per cloud:
## Option B: one small file per cloud with `extends:`

Each child file names the cloud in `provider.name` and sets its own values under `providers.<cloud>`, so they take precedence over the parent's block for that cloud. Every combination gets its own Terraform workspace (`.pskit/<provider>-<stage>/`), so the same service can be live on several clouds at once. `pskit dashboard` then shows all of them on one page.
## What each cloud needs | Cloud | Tier | Required settings | Notes | | --- |

| --- | --- | | aws | stable | AWS credentials | HTTP API, EventBridge Scheduler | | gcp | stable | `options.project` | Cloud Functions gen2, Cloud Scheduler | | azure | stable | `options.subscription_id` | Function App (Linux consumption) | | alibaba | beta | `ALICLOUD_*` credentials | FC 3.0 HTTP + timer triggers | | tencent | beta | `TENCENTCLOUD_*` credentials | SCF + API Gateway; Python 3.9/3.10 | | huawei | beta | `options.apig_instance_id` | FunctionGraph + dedicated APIG | | oracle | experimental | `compartment_id`, `subnet_ids`, `image` or `image_repository` | container images; no schedules | | ibm | beta | `IC_API_KEY` | Code Engine functions; HTTP only, Python 3.11, max 120 s | | digitalocean | beta | `options.namespace`, `doctl` on PATH | deployed with `doctl serverless` | | cloudflare | experimental | `options.account_id` | Python Workers (stdlib + Pyodide packages only) | | onprem | experimental | nothing (optional `options.port`) | a Python process on this machine; queues, storage and topics are directories | Where a cloud lacks a feature, the override says so explicitly. For example `functions.ticker.events: []` on IBM and Oracle deploys `ticker` without a schedule instead of failing.
