# Example: 11-custom-terraform

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: ${tf:...} is passed to Terraform untouched -> the real table name after apply. Remote state: required for teams and CI so everyone shares one state file. Create the bucket (versioning on) and lock table once, outside this service. Raw Terraform JSON, deep-merged into the generated main.tf.json. On this machine there is no DynamoDB table and no S3 state bucket. The handler already uses an in-memory repository when PSKIT_PROVIDER is not aws. Shell commands run from the project root. PSKIT_SERVICE, PSKIT_STAGE, PSKIT_PROVIDER and PSKIT_WORK_DIR are set for them.

# 11 · Custom Terraform, remote state and hooks

pskit generates Terraform for functions and triggers. Everything else your service needs
(databases, secrets, buckets with special policies, ...) you add as **raw Terraform** in the
same file, and wire it up with `${tf:...}` references.

## `terraform.extra`

`extra` is Terraform JSON syntax,
deep-merged into the generated `.pskit/<provider>-<stage>/main.tf.json`. It can add
`resource`, `data`, `output`, `locals` and `module` blocks, or override generated attributes.

## `${tf:...}` references

User-supplied strings are escaped so that `${...}` can't accidentally become a Terraform
expression. `${tf:<expression>}` is the explicit opt-in: In the generated Terraform these become `${aws_dynamodb_table.orders.name}`, and Terraform
orders the resources accordingly (table first, then the Lambda).

## Remote state

`provider.state` configures a Terraform backend.
Use one for any shared environment, so CI and teammates see the same state:

| Cloud | backend | config keys |
| --- | --- | --- |
| AWS | `s3` | `bucket`, `key`, `region`, `dynamodb_table` (locking), `encrypt` |
| GCP | `gcs` | `bucket`, `prefix` |
| Azure | `azurerm` | `resource_group_name`, `storage_account_name`, `container_name`, `key` |
| any | `http`, `remote` (Terraform Cloud), `pg`, ... | see the Terraform docs |

Without `state`, the state lives in `.pskit/<provider>-<stage>/terraform.tfstate` on your
machine, which is fine for experiments only.

## Hooks

`hooks.before_package`, `after_package`, `before_deploy`, `after_deploy`, `before_remove`
and `after_remove` run shell commands from the project root. A failing command aborts
the deploy. Here, the tests must pass before deploying, and a smoke test runs against the
new endpoint afterwards (`scripts/smoke_test.py` reads `$PSKIT_WORK_DIR/deployment.json`).

## Run locally

Locally the repository falls back to memory, so no AWS credentials are needed.

## Deploy

This example is AWS-specific by nature, because `extra` contains AWS resources. For
another cloud, add that cloud's resources (e.g. `google_firestore_database`,
`azurerm_cosmosdb_account`) under `providers.<cloud>.terraform.extra` and add one
repository class in `app/repository.py`. The handlers stay the same.
