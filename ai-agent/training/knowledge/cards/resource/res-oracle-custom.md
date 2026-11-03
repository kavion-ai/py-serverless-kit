# Other OCI services (`type: custom`)

`custom` is for anything that isn't a bucket, queue, topic, database or cache: Vault secrets, Streaming, NoSQL
Database, a third-party API. pskit only passes connection details to your functions (`external: true` is required).

The recipe is always the same: copy the **OCID** and **endpoint** from the console, add a policy for the functions'
dynamic group (see README.md), and put the values in
`connection`.

## Vault secrets

Keeps passwords and API keys out of the function configuration and Terraform state.

**Create:** Console → **Identity & Security → Vault** → **Create Vault**; open it → **Master Encryption Keys** →
**Create Key**; then **Secrets** → **Create Secret** → name, the key, the secret contents.

**Collect:** secret details → *OCID*.

**Policy:**

## Streaming

A durable, partitioned log (Kafka-compatible) when Notifications isn't enough.

**Create:** Console → **Analytics & AI → Messaging → Streaming** → **Create Stream** → name, partitions.

**Collect:** stream details → *OCID* and *Messages endpoint*.

**Policy:** `Allow dynamic-group pskit-functions to use stream-push in compartment <name>`
(`use stream-pull` to read).

pskit has no Streaming trigger.

```
Allow dynamic-group pskit-functions to read secret-bundles in compartment <name>
```
