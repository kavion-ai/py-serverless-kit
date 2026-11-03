# Example: 10-stages-and-config

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: Reusable values. Read anywhere with ${self:custom.<key>}. Secrets: never commit them. Inject from CI / a secret manager at deploy time: Per-stage overrides: deep-merged over everything above when --stage matches.

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

Expected output (dev, with `.env`):

`.env` overrides the YAML locally. `TABLE_NAME` is therefore `local-orders` instead of
`shop-config-dev-orders`.

## Deploy each stage

Each stage is fully isolated: its own resource names (`shop-config-prod-config`) and its
own Terraform state (`.pskit/aws-prod/`, or the S3 backend configured for prod).

## Secrets

- **Never commit secrets** to `pskit.yml` or `.env`. Both `.env` and `.env.*` are excluded from
  bundles, and `pskit init` git-ignores `.env`.
- `${env:SECRET}` at deploy time (from CI secrets) is the simplest option. The value ends
  up as a function environment variable, which is visible to anyone with read access to the function.
- Better: store the secret in the cloud's secret manager and pass only its **reference**:

  Then read the value at cold start with the cloud SDK. GCP Secret Manager and Azure Key
  Vault references follow the same pattern.
