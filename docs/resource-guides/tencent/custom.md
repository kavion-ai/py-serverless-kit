# Other Tencent Cloud services (`type: custom`)

`custom` is for any service that isn't a bucket, queue, topic, database or cache: Secrets Manager, a third-party API,
anything else. pskit only passes its connection details to your functions (`external: true` is required).

The recipe is always the same: find the **endpoint** and the **names** in the console, keep the keys in environment
variables, and put the rest in `connection`.

## Secrets Manager (SSM)

**Create:** Console → **Secrets Manager** → **Secret List** → **Create**: name `stripe-key`, the secret value, an
encryption key (the default KMS key is fine) → **OK**.

**Collect:** the secret name, the region, and a CAM sub-user (or `iam.role`) allowed to read it (for example the
`QcloudSSMReadOnlyAccess` preset policy).

```yaml
provider:
  name: tencent
  environment:
    SSM_SECRET_ID: ${env:SSM_SECRET_ID}
    SSM_SECRET_KEY: ${env:SSM_SECRET_KEY}

resources:
  vault:
    type: custom
    external: true
    connection:
      region: ap-guangzhou
      secret: stripe-key
      secret_id_env: SSM_SECRET_ID
      secret_key_env: SSM_SECRET_KEY
```

```python
# requirements.txt: tencentcloud-sdk-python-ssm
from tencentcloud.common import credential
from tencentcloud.ssm.v20190923 import models, ssm_client
from py_serverless_kit import resource


def charge(event, ctx):
    v = resource("vault")
    client = ssm_client.SsmClient(credential.Credential(ctx.env[v["secret_id_env"]], ctx.env[v["secret_key_env"]]),
                                  v["region"])
    req = models.GetSecretValueRequest()
    req.SecretName = v["secret"]
    req.VersionId = "SSM_Current"         # the current version; or the version id from the console
    api_key = client.GetSecretValue(req).SecretString
    ...
```

Reading secrets at run time keeps them out of Terraform state; only the keys for SSM are passed as environment
variables.

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
