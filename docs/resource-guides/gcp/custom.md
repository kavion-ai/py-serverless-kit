# Other Google Cloud services (`type: custom`)

`custom` is for any service that isn't a bucket, queue, topic, database or cache: Firestore, Secret Manager,
BigQuery, Vertex AI, a third-party API. pskit only passes its details to your functions (`external: true` is required).

Google Cloud client libraries authenticate as the function's service account, so most services need **no keys**:
grant the runtime service account a role, and put names and IDs in `connection`.

## Firestore

**Create:** Console → **Firestore** → **Create database** → *Native mode*, database ID `(default)` or your own,
location → **Create**.

**Collect:** Firestore → **Databases** → *Database ID*; the collection names you use.

**Grant:** **IAM & Admin → IAM** → **Grant access** → the runtime service account → **Cloud Datastore User**.

```yaml
resources:
  orders-store:
    type: custom
    external: true
    connection:
      database: (default)
      collection: orders
```

```python
from google.cloud import firestore              # requirements.txt: google-cloud-firestore
from py_serverless_kit import resource


def api(event, ctx):
    c = resource("orders-store")
    db = firestore.Client(project=ctx.env["PSKIT_GCP_PROJECT"], database=c["database"])
    db.collection(c["collection"]).document("1").set({"total": 10})
    return db.collection(c["collection"]).document("1").get().to_dict()
```

## Secret Manager

Better than environment variables for passwords: the secret never lands in Terraform state.

**Create:** Console → **Security → Secret Manager** → **Create secret** → name `stripe-key`, secret value → **Create
secret**.

**Collect:** the secret → *Resource ID* (`projects/my-project/secrets/stripe-key`).

**Grant:** the secret → **Permissions** → **Grant access** → the runtime service account → **Secret Manager Secret
Accessor**.

```yaml
resources:
  stripe:
    type: custom
    external: true
    connection:
      secret: projects/my-project/secrets/stripe-key
```

```python
from google.cloud import secretmanager          # requirements.txt: google-cloud-secret-manager
from py_serverless_kit import resource

_value = None


def api(event, ctx):
    global _value
    if _value is None:   # fetch once per instance
        client = secretmanager.SecretManagerServiceClient()
        name = resource("stripe")["secret"] + "/versions/latest"
        _value = client.access_secret_version(name=name).payload.data.decode("utf-8")
    return {"has_key": bool(_value)}
```

## Anything else

Same recipe: find the resource's ID on its detail page, put non-secret values in `connection`, grant the runtime
service account the narrowest role that works, and keep secrets in Secret Manager.

## Test

```bash
pskit validate
pskit resources send --list    # PSKIT_RESOURCE_* variables and a snippet for every custom resource
pskit deploy
```
