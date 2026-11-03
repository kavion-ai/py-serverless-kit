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

```yaml
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

```python
from huaweicloudsdkcore.auth.credentials import BasicCredentials        # requirements.txt: huaweicloudsdkcsms
from huaweicloudsdkcsms.v1 import CsmsClient, ShowSecretVersionRequest
from huaweicloudsdkcsms.v1.region.csms_region import CsmsRegion
from py_serverless_kit import resource


def api(event, ctx):
    s = resource("secrets")
    creds = BasicCredentials(
        ctx.raw.getSecurityAccessKey(), ctx.raw.getSecuritySecretKey(), s["project_id"]
    ).with_security_token(ctx.raw.getSecurityToken())
    client = CsmsClient.new_builder().with_credentials(creds).with_region(CsmsRegion.value_of(ctx.region)).build()
    resp = client.show_secret_version(ShowSecretVersionRequest(secret_name=s["stripe_secret"], version_id="latest"))
    key = resp.version.secret_string
    ...
```

## Document Database Service (DDS, MongoDB-compatible)

**Create:** Console → **Document Database Service** → **Buy DB Instance** → VPC, subnet, security group,
administrator password.

**Collect:** instance → **Basic Information** → *Connection* → private IP addresses and port (`8635`), and the
connection string under **Connections**. The function must join the VPC (`functions.<name>.options.vpc_id` /
`network_id`, see [database.md](database.md)).

```yaml
provider:
  environment:
    DDS_PASSWORD: ${env:DDS_PASSWORD}

resources:
  catalog:
    type: custom
    external: true
    connection:
      host: 192.168.0.30
      port: 8635
      user: rwuser
      database: catalog
      password_env: DDS_PASSWORD
```

```python
from pymongo import MongoClient          # requirements.txt: pymongo
from py_serverless_kit import resource


def api(event, ctx):
    c = resource("catalog")
    db = MongoClient(host=c["host"], port=int(c["port"]), username=c["user"],
                     password=ctx.env[c["password_env"]], authSource="admin")[c["database"]]
    return {"products": db.products.count_documents({})}
```

## Test

```bash
pskit validate
pskit resources send --list    # PSKIT_RESOURCE_* variables and a snippet for every custom resource
pskit deploy
```
