# Resource: custom

A custom resource is any service that is not a bucket, queue, topic, database, or cache. Use it for DynamoDB, a secret store, an internal HTTP API, or a vendor endpoint. pskit passes the details you write. It leaves the service in place.

The schema requires `external: true` for `type: custom`. The guide index points at DynamoDB and Secrets Manager on AWS, Cosmos DB and Key Vault on Azure, Firestore and Secret Manager on GCP, and the matching "other services" page on every other cloud. On premises the custom page covers SMTP, LDAP, and internal APIs. Secret managers are also on-prem services read with `get_secret()`. `secrets` is not a `type` in `RESOURCE_TYPES`.

Declare `type: custom`, `external: true`, a `name` when the service has one, and `connection` scalars. Reserved connection keys are `type`, `name`, and `external`. Keys start with a letter and use letters, digits, or `_`. Nested maps and lists are rejected. Put secrets in `*_env` or in `${env:NAME}`. `functions` limits the binding.

There is no custom event. The handler calls the service SDK with `resource("orders-table").native_name` or a connection field such as `secret_arn`. pskit grants no portable IAM policy for custom resources. On AWS, add `provider.iam.statements` yourself. A role you bring with `iam.role` is also left unchanged, and the plan warns.

Open:

Resources > + Add resource

Resources > How to use

Resources > Test

```
pskit resources usage orders-table -p aws -s dev
pskit resources send --list
pskit validate
```

The testing checklist lists `pskit resources send --list` as every resource at once. The AWS custom guide says that command prints the variables and a snippet. `pskit invoke` and `pskit dev` inject the same variables locally.

Sources: `docs/resources.md#fields`, `docs/resources.md#provider-support`, `src/py_serverless_kit/config/schema.py`
