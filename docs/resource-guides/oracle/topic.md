# OCI Notifications topic (`type: topic`)

pskit has **no topic trigger on OCI**: a `topic` event is a validation error. Bind the topic to functions and publish
with the OCI SDK. For a durable, Kafka-compatible stream, see [Streaming](custom.md#streaming).

## 1. Create the topic (console)

1. Console → **Developer Services → Application Integration → Notifications** → pick the compartment →
   **Create Topic**.
2. Name (for example `order-events`) → **Create**. Add subscriptions (email, HTTPS, Slack, ...) on the topic page.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic OCID | topic details → *OCID* | `ocid1.onstopic.oc1.iad.aaaa` |
| Name | topic details | `order-events` |

## 3. Policies

```
Allow dynamic-group pskit-functions to use ons-topics in compartment <name>
```

## 4. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: oracle
  region: us-ashburn-1
  options:
    compartment_id: ocid1.compartment.oc1..aaaa
    subnet_ids: [ocid1.subnet.oc1..aaaa]
    image: iad.ocir.io/axabc12345/orders:1.0

resources:
  order-events:
    type: topic
    external: true
    name: order-events
    connection:
      ocid: ocid1.onstopic.oc1.iad.aaaa

functions:
  api:
    handler: app.handlers.api
    events: [{http: POST /orders}]
```

## 5. Use it in a handler

`requirements.txt`: `oci`

```python
import json

import oci
from py_serverless_kit import resource


def api(event, ctx):
    topic = resource("order-events")
    client = oci.ons.NotificationDataPlaneClient(config={}, signer=oci.auth.signers.get_resource_principals_signer())
    client.publish_message(topic["ocid"], oci.ons.models.MessageDetails(title="order", body=json.dumps(event.http.json())))
    return {"published": True}
```

## 6. Test

```bash
pskit validate
pskit deploy
```

Console: topic → **Publish Message** to check the subscriptions receive it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` Oracle Cloud Functions does not support `topic` events in pskit `` | no topic triggers on OCI; remove the `topic` event |
| `NotAuthorizedOrNotFound` | dynamic group / `use ons-topics` policy missing |
| Subscribers get nothing | subscriptions stay *Pending* until confirmed (email, HTTPS) |
