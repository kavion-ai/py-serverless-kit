# Resource: other AWS services

On AWS, `type: custom` is any service that is not a bucket, queue, topic, database, or cache. The guide names DynamoDB, Secrets Manager, Kinesis, EventBridge, Bedrock, and a third-party API. `external: true` is required. pskit passes `name` and `connection` and grants no IAM for the custom resource. Add `provider.iam.statements` yourself. Use `${tf:...}` only for resources you also define in `provider.terraform.extra`. For a console-created resource, paste the ARN.

DynamoDB: create a table, copy the table ARN from General information, set `name` to the table name and `connection.arn` to the ARN, and allow `dynamodb:GetItem`, `PutItem`, `UpdateItem`, and `Query` on that ARN. The handler uses `boto3.resource("dynamodb").Table(resource("orders-table").native_name)`.

Secrets Manager: store a secret, copy the secret ARN, and put it in `connection.secret_arn`. Allow `secretsmanager:GetSecretValue` on that ARN. The secret stays out of Terraform state. Read it once per container with `get_secret_value` and cache it in the module. A customer-managed KMS key also needs `kms:Decrypt` on that key. The same pattern fits any other service: non-secret values in `connection`, actions in `iam.statements`, secrets in Secrets Manager or a `*_env` variable.

Open:

Resources > + Add resource

Resources > How to use

```
pskit validate
pskit resources send --list
```

`pskit resources send --list` prints the `PSKIT_RESOURCE_*` variables and a snippet for every custom resource. There is no custom trigger.

Sources: `docs/resource-guides/aws/custom.md#other-aws-services-type-custom`, `docs/resource-guides/aws/custom.md#dynamodb`, `docs/resources.md#fields`
