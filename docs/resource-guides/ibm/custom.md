# Other IBM Cloud services (`type: custom`)

`custom` is for any service that isn't a bucket, queue, topic, database or cache: Secrets Manager, Cloudant, watsonx, a
third-party API. pskit only passes its connection details to your functions (`external: true` is required).

The recipe is always the same: find the **endpoint** and an **API key** in the console, keep the key in an environment
variable, and put the rest in `connection`.

## Secrets Manager

Keeps secrets out of Terraform state: only one API key goes into the function environment, and handlers fetch the rest
at run time.

**Create:** Console → **Catalog** → **Secrets Manager** → region, plan → **Create**. In the instance → **Secrets** →
**Add** → *Key-value* or *Other secret type (arbitrary)* → name, secret group → **Add**.

**Collect:**

| Value | Where |
|---|---|
| Service endpoint | instance → **Endpoints** → *Public* (`https://<instance id>.us-south.secrets-manager.appdomain.cloud`) |
| Secret ID | **Secrets** → the secret → *ID* |
| API key | **Manage → Access (IAM) → Service IDs → Create** → **Assign access** → *Secrets Manager*, this instance, role *SecretsReader* → **API keys → Create** |

```yaml
service: payments

provider:
  name: ibm
  region: us-south
  environment:
    SM_API_KEY: ${env:SM_API_KEY}

resources:
  secrets:
    type: custom
    external: true
    connection:
      url: https://0000-1111.us-south.secrets-manager.appdomain.cloud
      stripe_secret_id: 2222-3333
      api_key_env: SM_API_KEY

functions:
  pay:
    handler: app.handlers.pay
    events: [{http: POST /pay}]
```

```python
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator   # requirements.txt: ibm-secrets-manager-sdk
from ibm_secrets_manager_sdk.secrets_manager_v2 import SecretsManagerV2
from py_serverless_kit import resource


def pay(event, ctx):
    s = resource("secrets")
    sm = SecretsManagerV2(authenticator=IAMAuthenticator(ctx.env[s["api_key_env"]]))
    sm.set_service_url(s.url)
    secret = sm.get_secret(id=s["stripe_secret_id"]).get_result()
    stripe_key = secret.get("payload")   # key-value secrets: secret["data"]
    return {"ok": bool(stripe_key)}
```

## Cloudant

**Create:** Console → **Catalog** → **Cloudant** → plan, *Authentication method*: IAM → **Create**. Then **Service
credentials → New credential** (role *Writer*).

**Collect:** the credential's `url` and `apikey`; the database name from **Launch Dashboard → Databases**.

```yaml
resources:
  catalog:
    type: custom
    external: true
    connection:
      url: https://xxxx-bluemix.cloudantnosqldb.appdomain.cloud
      database: products
      api_key_env: CLOUDANT_API_KEY
```

```python
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator   # requirements.txt: ibmcloudant
from ibmcloudant.cloudant_v1 import CloudantV1
from py_serverless_kit import resource



def product(event, ctx):
    c = resource("catalog")
    client = CloudantV1(authenticator=IAMAuthenticator(ctx.env[c["api_key_env"]]))
    client.set_service_url(c.url)
    return client.get_document(db=c["database"], doc_id="sku-1").get_result()
```

(Add `CLOUDANT_API_KEY: ${env:CLOUDANT_API_KEY}` under `provider.environment`.)

## Test

```bash
pskit validate
pskit resources send --list    # PSKIT_RESOURCE_* variables and a snippet for every custom resource
pskit deploy
```
