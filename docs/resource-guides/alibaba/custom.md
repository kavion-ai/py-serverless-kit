# Other Alibaba Cloud services (`type: custom`)

`custom` is for any service that isn't a bucket, queue, topic, database or cache: Tablestore, KMS secrets, a
third-party API. pskit only passes its connection details to your functions (`external: true` is required).

The recipe is always the same: find the **endpoint** and the **names** in the console, keep the AccessKey in an
environment variable, and put the rest in `connection`.

## Tablestore

**Create:** Console → **Tablestore** → **Create Instance** (region, name, instance type) → open it → **Create Table**
(name `orders`, primary key `id` string).

**Collect:**

| Value | Where |
|---|---|
| Instance name | Tablestore → instance list |
| Endpoint | instance → **Instance Details** / **Instance Management** → *Endpoint* (public or VPC) |
| Table | instance → **Tables** |
| AccessKey | RAM user with `AliyunOTSFullAccess` (or a custom policy) |

```yaml
provider:
  name: alibaba
  environment:
    OTS_ACCESS_KEY_ID: ${env:OTS_ACCESS_KEY_ID}
    OTS_ACCESS_KEY_SECRET: ${env:OTS_ACCESS_KEY_SECRET}

resources:
  orders-store:
    type: custom
    external: true
    connection:
      endpoint: https://acme-orders.cn-hangzhou.ots.aliyuncs.com
      instance: acme-orders
      table: orders
      access_key_env: OTS_ACCESS_KEY_ID
      secret_key_env: OTS_ACCESS_KEY_SECRET
```

```python
from tablestore import OTSClient, Row          # requirements.txt: tablestore
from py_serverless_kit import resource


def api(event, ctx):
    c = resource("orders-store")
    client = OTSClient(c["endpoint"], ctx.env[c["access_key_env"]], ctx.env[c["secret_key_env"]], c["instance"])
    client.put_row(c["table"], Row([("id", "1")], [("total", 10)]))
```

## KMS secrets (Secrets Manager)

**Create:** Console → **Key Management Service** → **Secrets** → **Create Secret** → *Generic Secret*, name
`stripe-key`, value.

**Collect:** the secret name, the region, and a RAM user (or `iam.role`) allowed to call `kms:GetSecretValue` on it.

```yaml
resources:
  vault:
    type: custom
    external: true
    connection:
      region: cn-hangzhou
      secret: stripe-key
      access_key_env: KMS_ACCESS_KEY_ID
      secret_key_env: KMS_ACCESS_KEY_SECRET
```

```python
# requirements.txt: alibabacloud_kms20160120
from alibabacloud_kms20160120.client import Client
from alibabacloud_kms20160120.models import GetSecretValueRequest
from alibabacloud_tea_openapi.models import Config
from py_serverless_kit import resource



def charge(event, ctx):
    v = resource("vault")
    client = Client(Config(access_key_id=ctx.env[v["access_key_env"]], access_key_secret=ctx.env[v["secret_key_env"]],
                           endpoint=f"kms.{v['region']}.aliyuncs.com"))
    api_key = client.get_secret_value(GetSecretValueRequest(secret_name=v["secret"])).body.secret_data
    ...
```

Reading secrets at run time keeps them out of Terraform state; only the
AccessKey for KMS is passed as an environment variable.

## A third-party API

```yaml
resources:
  payments:
    type: custom
    external: true
    connection:
      base_url: https://api.example.com/v1
      api_key_env: PAYMENTS_API_KEY
```

## Test

```bash
pskit validate
pskit resources send --list    # PSKIT_RESOURCE_* variables and a snippet for every custom resource
pskit deploy
```
