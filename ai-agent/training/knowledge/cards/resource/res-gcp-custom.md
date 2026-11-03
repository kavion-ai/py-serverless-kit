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

## Secret Manager

Better than environment variables for passwords: the secret never lands in Terraform state.

**Create:** Console → **Security → Secret Manager** → **Create secret** → name `stripe-key`, secret value → **Create
secret**.

**Collect:** the secret → *Resource ID* (`projects/my-project/secrets/stripe-key`).

**Grant:** the secret → **Permissions** → **Grant access** → the runtime service account → **Secret Manager Secret
Accessor**.

## Anything else

Same recipe: find the resource's ID on its detail page, put non-secret values in `connection`, grant the runtime
service account the narrowest role that works, and keep secrets in Secret Manager.

```text
resources:
  orders-store:
    type: custom
    external: true
    connection:
      database: (default)
      collection: orders
```
