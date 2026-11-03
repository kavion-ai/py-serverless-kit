# Concept: Terraform state

Each provider and stage has its own directory, `.pskit/<provider>-<stage>/`, with its own Terraform workspace and state. `aws-dev` and `gcp-prod` do not share state. By default the state file is `terraform.tfstate` in that directory. pskit writes a `.gitignore` inside `.pskit/`, and the architecture doc says not to commit `.pskit/`.

For a team or CI, set `provider.state` to a remote backend:

```text
provider:
  state:
    backend: s3
    config:
      bucket: my-tf-state
      key: orders/${opt:stage}.tfstate
      region: us-east-1
      dynamodb_table: tf-locks
```

`backend` is any Terraform backend type. The doc names s3, gcs, azurerm, http, and remote. `config` is that backend's settings. The architecture doc names S3 with a DynamoDB lock, GCS, azurerm, and Terraform Cloud as the team options. When `provider.state` is set, the local `terraform.tfstate` line in the deploy diagram does not apply.

`provider.terraform.binary` autodetects `terraform`, then `tofu`, or uses `PSKIT_TERRAFORM_BIN`. `required_version` defaults to `>= 1.5.0`. User strings in the generated JSON are escaped (`${` becomes `$${`) unless they are written as `${tf:...}`.

Sources: `docs/architecture.md#state-handling`, `docs/architecture.md#deploy-pipeline`, `docs/configuration.md#state-remote-terraform-backend`, `docs/configuration.md#terraform`
