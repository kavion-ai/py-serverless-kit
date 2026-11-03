# 11 · Custom Terraform, remote state and hooks

pskit generates Terraform for functions and triggers. Everything else your service needs
(databases, secrets, buckets with special policies, ...) you add as **raw Terraform** in the
same file, and wire it up with `${tf:...}` references.

## `terraform.extra`

```yaml
provider:
  terraform:
    extra:
      resource:
        aws_dynamodb_table:
          orders: {name: ..., billing_mode: PAY_PER_REQUEST, hash_key: id, ...}
```

`extra` is [Terraform JSON syntax](https://developer.hashicorp.com/terraform/language/syntax/json),
deep-merged into the generated `.pskit/<provider>-<stage>/main.tf.json`. It can add
`resource`, `data`, `output`, `locals` and `module` blocks, or override generated attributes.

## `${tf:...}` references

User-supplied strings are escaped so that `${...}` can't accidentally become a Terraform
expression. `${tf:<expression>}` is the explicit opt-in:

```yaml
environment:
  ORDERS_TABLE: "${tf:aws_dynamodb_table.orders.name}"
iam:
  statements:
    - actions: [dynamodb:GetItem, dynamodb:PutItem]
      resources: ["${tf:aws_dynamodb_table.orders.arn}"]
```

In the generated Terraform these become `${aws_dynamodb_table.orders.name}`, and Terraform
orders the resources accordingly (table first, then the Lambda).

## Remote state

`provider.state` configures a [Terraform backend](https://developer.hashicorp.com/terraform/language/backend).
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

```bash
pskit dev
curl -X POST localhost:3000/orders -d '{"item": "book"}'
python -m pytest tests -q
```

Locally the repository falls back to memory, so no AWS credentials are needed.

## Deploy

```bash
export TF_STATE_BUCKET=my-state-bucket TF_LOCK_TABLE=terraform-locks
pskit plan                    # review: DynamoDB table + 2 Lambdas + API
pskit deploy                  # before_deploy runs the tests, after_deploy the smoke test
pskit tf -- state list        # any terraform command, run in the generated workspace
```

This example is AWS-specific by nature, because `extra` contains AWS resources. For
another cloud, add that cloud's resources (e.g. `google_firestore_database`,
`azurerm_cosmosdb_account`) under `providers.<cloud>.terraform.extra` and add one
repository class in `app/repository.py`. The handlers stay the same.
