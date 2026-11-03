# Other OCI services (`type: custom`)

`custom` is for anything that isn't a bucket, queue, topic, database or cache: Vault secrets, Streaming, NoSQL
Database, a third-party API. pskit only passes connection details to your functions (`external: true` is required).

The recipe is always the same: copy the **OCID** and **endpoint** from the console, add a policy for the functions'
dynamic group (see [README.md](README.md#how-pskit-runs-on-oci-why-some-steps-matter)), and put the values in
`connection`.

## Vault secrets

Keeps passwords and API keys out of the function configuration and Terraform state.

**Create:** Console → **Identity & Security → Vault** → **Create Vault**; open it → **Master Encryption Keys** →
**Create Key**; then **Secrets** → **Create Secret** → name, the key, the secret contents.

**Collect:** secret details → *OCID*.

**Policy:**

```
Allow dynamic-group pskit-functions to read secret-bundles in compartment <name>
```

```yaml
resources:
  secrets:
    type: custom
    external: true
    connection:
      db_password_ocid: ocid1.vaultsecret.oc1.iad.aaaa
```

```python
import base64

import oci                                   # requirements.txt: oci
from py_serverless_kit import resource


def api(event, ctx):
    s = resource("secrets")
    client = oci.secrets.SecretsClient(config={}, signer=oci.auth.signers.get_resource_principals_signer())
    bundle = client.get_secret_bundle(s["db_password_ocid"]).data
    password = base64.b64decode(bundle.secret_bundle_content.content).decode()
    ...
```

## Streaming

A durable, partitioned log (Kafka-compatible) when Notifications isn't enough.

**Create:** Console → **Analytics & AI → Messaging → Streaming** → **Create Stream** → name, partitions.

**Collect:** stream details → *OCID* and *Messages endpoint*.

**Policy:** `Allow dynamic-group pskit-functions to use stream-push in compartment <name>`
(`use stream-pull` to read).

```yaml
resources:
  clicks:
    type: custom
    external: true
    connection:
      ocid: ocid1.stream.oc1.iad.aaaa
      endpoint: https://cell-1.streaming.us-ashburn-1.oci.oraclecloud.com
```

```python
import base64
import json

import oci
from py_serverless_kit import resource


def track(event, ctx):
    s = resource("clicks")
    client = oci.streaming.StreamClient(
        config={}, signer=oci.auth.signers.get_resource_principals_signer(), service_endpoint=s["endpoint"]
    )
    value = base64.b64encode(json.dumps(event.http.json()).encode()).decode()
    entry = oci.streaming.models.PutMessagesDetailsEntry(value=value)
    client.put_messages(s["ocid"], oci.streaming.models.PutMessagesDetails(messages=[entry]))
```

pskit has no Streaming trigger.

## Test

```bash
pskit validate
pskit resources send --list    # PSKIT_RESOURCE_* variables and a snippet for every custom resource
pskit deploy
```
