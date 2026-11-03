# 10 · Stages, variables and secrets

Shows one config with dev / staging / prod stages, every variable source, local `.env`
files, and how to handle secrets.

## Variables

| Syntax | Resolves to |
| --- | --- |
| `${env:NAME}` | environment variable; error if unset |
| `${env:NAME, default}` | environment variable or the default |
| `${opt:stage}` / `${opt:region}` / `${opt:provider}` | effective CLI values |
| `${self:path.to.value}` | any value in the merged config, e.g. `${self:custom.table}` |
| `${file(config/limits.json)}` | parsed JSON / YAML, or raw text for other files |
| `${tf:aws_x.y.attr}` | left for Terraform (example 11) |
| anything else, e.g. `${aws:username}` | kept verbatim (IAM policy variables) |

A value that is *only* a variable keeps its type, so
`memory: "${self:custom.limits.prod.memory}"` is the number `1024`.

## Precedence (later wins)

1. `extends:` parent files
2. this file
3. `providers.<cloud>`
4. `stages.<stage>`
5. CLI flags `--provider`, `--stage`, `--region`

Overrides deep-merge mappings and replace lists.

## Run locally

```bash
cp .env.example .env
pskit invoke -f config
pskit invoke -f config --stage prod      # see the prod values without deploying
```

Expected output (dev, with `.env`):

```json
{"stage": "dev", "table": "local-orders", "log_level": "DEBUG", "new_checkout": true,
 "api_base_url": "https://api-dev.example.com", "payment_api_key_configured": true, "memory_mb": null}
```

`.env` overrides the YAML locally. `TABLE_NAME` is therefore `local-orders` instead of
`shop-config-dev-orders`.

## Deploy each stage

```bash
pskit deploy                                       # dev
pskit deploy --stage staging
PAYMENT_API_KEY=$PROD_KEY pskit deploy --stage prod
pskit info --stage prod
```

Each stage is fully isolated: its own resource names (`shop-config-prod-config`) and its
own Terraform state (`.pskit/aws-prod/`, or the S3 backend configured for prod).

## Secrets

- **Never commit secrets** to `pskit.yml` or `.env`. Both `.env` and `.env.*` are excluded from
  bundles, and `pskit init` git-ignores `.env`.
- `${env:SECRET}` at deploy time (from CI secrets) is the simplest option. The value ends
  up as a function environment variable, which is visible to anyone with read access to the function.
- Better: store the secret in the cloud's secret manager and pass only its **reference**:

  ```yaml
  environment:
    PAYMENT_SECRET_ARN: "${tf:aws_secretsmanager_secret.payment.arn}"   # resource added via terraform.extra
  iam:
    statements:
      - {actions: ["secretsmanager:GetSecretValue"], resources: ["${tf:aws_secretsmanager_secret.payment.arn}"]}
  ```

  Then read the value at cold start with the cloud SDK. GCP Secret Manager and Azure Key
  Vault references follow the same pattern.
