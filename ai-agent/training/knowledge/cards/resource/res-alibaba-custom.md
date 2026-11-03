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

## KMS secrets (Secrets Manager)

**Create:** Console → **Key Management Service** → **Secrets** → **Create Secret** → *Generic Secret*, name
`stripe-key`, value.

**Collect:** the secret name, the region, and a RAM user (or `iam.role`) allowed to call `kms:GetSecretValue` on it.

Reading secrets at run time keeps them out of Terraform state; only the
AccessKey for KMS is passed as an environment variable.

```text
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
