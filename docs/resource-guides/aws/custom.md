# Other AWS services (`type: custom`)

`custom` is for any service that isn't a bucket, queue, topic, database or cache: DynamoDB, Secrets Manager, Kinesis,
EventBridge, Bedrock, a third-party API. pskit only passes its details to your functions (`external: true` is required).

pskit grants **no IAM permissions** for `custom` resources: add them under `provider.iam.statements`. Use `${tf:...}`
only for resources you also define in `provider.terraform.extra`; for console-created ones, paste the ARN.

## DynamoDB

**Create:** Console → **DynamoDB** → **Tables** → **Create table** → table name `orders`, partition key `id` (String)
→ **Create table**.

**Collect:** the table → **Overview** → **General information** → *Amazon Resource Name (ARN)*
(`arn:aws:dynamodb:eu-west-1:123456789012:table/orders`).

```yaml
provider:
  name: aws
  region: eu-west-1
  iam:
    statements:
      - actions: [dynamodb:GetItem, dynamodb:PutItem, dynamodb:UpdateItem, dynamodb:Query]
        resources: ["arn:aws:dynamodb:eu-west-1:123456789012:table/orders"]

resources:
  orders-table:
    type: custom
    external: true
    name: orders
    connection:
      arn: arn:aws:dynamodb:eu-west-1:123456789012:table/orders
```

```python
import boto3
from py_serverless_kit import resource

table = boto3.resource("dynamodb").Table(resource("orders-table").native_name)


def api(event, ctx):
    table.put_item(Item={"id": "1", "total": 10})
    return table.get_item(Key={"id": "1"}).get("Item")
```

## Secrets Manager

Better than environment variables for passwords: the secret never lands in Terraform state.

**Create:** Console → **Secrets Manager** → **Store a new secret** → *Other type of secret* → key/value pairs (or
plaintext) → name `orders/stripe` → **Store**.

**Collect:** the secret → **Secret details** → *Secret ARN* (`arn:aws:secretsmanager:eu-west-1:123456789012:secret:orders/stripe-AbCdEf`).

```yaml
provider:
  iam:
    statements:
      - actions: [secretsmanager:GetSecretValue]
        resources: ["arn:aws:secretsmanager:eu-west-1:123456789012:secret:orders/stripe-*"]

resources:
  stripe:
    type: custom
    external: true
    connection:
      secret_arn: arn:aws:secretsmanager:eu-west-1:123456789012:secret:orders/stripe-AbCdEf
```

```python
import json

import boto3
from py_serverless_kit import resource

_secret = None


def api(event, ctx):
    global _secret
    if _secret is None:   # fetch once per container
        arn = resource("stripe")["secret_arn"]
        _secret = json.loads(boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"])
    return {"has_key": "api_key" in _secret}
```

A secret encrypted with a customer-managed KMS key also needs `kms:Decrypt` on that key.

## Anything else

Same recipe: find the ARN / endpoint on the service's detail page, put non-secret values in `connection`, grant the
actions in `iam.statements`, and keep secrets in Secrets Manager or an environment variable named by `*_env`.

## Test

```bash
pskit validate
pskit resources send --list    # PSKIT_RESOURCE_* variables and a snippet for every custom resource
pskit deploy
```
