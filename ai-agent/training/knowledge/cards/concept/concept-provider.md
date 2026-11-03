# Concept: the provider block

`provider.name` is required unless you pass `--provider`. The names in `PROVIDERS` are aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, and onprem. `region` is a string and falls back to the provider default. `stage` defaults to `dev` and must match `[a-z][a-z0-9-]{0,15}`. `--stage` overrides the file.

`runtime` is one of python3.9 through python3.14. If you do not pin it, pskit uses python3.12 when the cloud supports it, otherwise the newest supported version below 3.12: python3.11 on DigitalOcean, IBM, and Oracle, and python3.10 on Tencent. Pinning a runtime the cloud lacks is a `pskit validate` error.

`memory` defaults to 256 MB and is an int from 64 to 32768. `timeout` defaults to 30 seconds, from 1 to 3600, and must also be at or under that provider's maximum. `architecture` is `x86_64` or `arm64` and defaults to `x86_64`. The doc says it is used by AWS and for pip wheel selection.

`environment` and `tags` are maps. Environment values are converted to strings. Tags merge with `pskit-service`, `pskit-stage`, and `managed-by`. `log_retention_days` is an int or null and defaults to 14 for the AWS CloudWatch log group. `options` holds provider-specific settings. `state` and `terraform` configure the Terraform backend and the Terraform binary.

Sources: `docs/configuration.md#provider`, `docs/configuration.md#default-runtime`, `src/py_serverless_kit/config/schema.py`

```text
provider:
  state:
    backend: s3                      # any terraform backend type: s3, gcs, azurerm, http, remote, ...
    config:
      bucket: my-tf-state
      key: orders/${opt:stage}.tfstate
      region: us-east-1
      dynamodb_table: tf-locks
```
