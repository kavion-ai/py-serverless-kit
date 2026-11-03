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

## Cloudant

**Create:** Console → **Catalog** → **Cloudant** → plan, *Authentication method*: IAM → **Create**. Then **Service
credentials → New credential** (role *Writer*).

**Collect:** the credential's `url` and `apikey`; the database name from **Launch Dashboard → Databases**.

(Add `CLOUDANT_API_KEY: ${env:CLOUDANT_API_KEY}` under `provider.environment`.)

```text
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
