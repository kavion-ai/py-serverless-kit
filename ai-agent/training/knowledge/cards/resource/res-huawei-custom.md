# Other Huawei Cloud services (`type: custom`)

`custom` is for anything that isn't a bucket, queue, topic, database or cache: CSMS secrets, Document Database (DDS),
Cloud Search Service, a third-party API. pskit only passes connection details to your functions (`external: true` is
required).

The recipe is always the same: find the **endpoint** and the **identifiers** in the console, give the function
permissions through an agency (or keep a secret in an environment variable), and put the rest in `connection`.

## CSMS secrets (Data Encryption Workshop)

Keeping secrets in Cloud Secret Management Service avoids putting them in `user_data` and Terraform state.

**Create:** Console → **Data Encryption Workshop** → **Cloud Secret Management Service** → **Secrets** →
**Create Secret** → name (for example `stripe-key`), value → **OK**.

**Collect:** the secret name, your region and project ID (**My Credentials → API Credentials**). Add the *CSMS
ReadOnlyAccess* (or *KMS Administrator*) policy to the function's agency.

## Document Database Service (DDS, MongoDB-compatible)

**Create:** Console → **Document Database Service** → **Buy DB Instance** → VPC, subnet, security group,
administrator password.

**Collect:** instance → **Basic Information** → *Connection* → private IP addresses and port (`8635`), and the
connection string under **Connections**. The function must join the VPC (`functions.<name>.options.vpc_id` /
`network_id`, see database.md).

```text
provider:
  name: huawei
  iam:
    role: pskit-functions

resources:
  secrets:
    type: custom
    external: true
    connection:
      project_id: 0a1b2c3d4e5f
      stripe_secret: stripe-key
```
