# Concept: IAM statements

`provider.iam.statements` is a list of mappings with `effect`, `actions`, and `resources`. In the schema, `effect` is Allow or Deny and defaults to Allow. `actions` is required. `resources` defaults to `["*"]`. The configuration doc says the same defaults, and that the statements are AWS-style. Clouds that do not map them ignore them with a warning.

`provider.iam.role` is an optional string. The doc says it uses an existing role or agency instead of creating one. The schema description says an existing role or service account.

A function may have its own `iam` block in the same shape. The doc says those statements are added to the provider-level ones, and that a dedicated role is created on AWS. A statement can contain a Terraform reference such as `${tf:aws_dynamodb_table.orders.arn}`. That form is passed through. pskit does not resolve it as a config variable.

`invoke()` on AWS needs `lambda:InvokeFunction` in `iam.statements`, plus `py-serverless-kit[aws]` and `boto3` in requirements, as described in the handlers doc.

Sources: `docs/configuration.md#provider`, `docs/configuration.md#functions`, `docs/handlers.md#invoke-calling-another-function`, `src/py_serverless_kit/config/schema.py`

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
