# OCI Queue (`type: queue`)

pskit has **no queue trigger on OCI**: a `queue` event is a validation error. Bind the queue to functions and send or
receive messages with the OCI SDK. (To consume an OCI Queue from an on-premises pskit host, use a
[`custom` driver](../../resources.md#custom-drivers).)

## 1. Create the queue (console)

1. Console → **Developer Services → Application Integration → Queues** → pick the compartment → **Create queue**.
2. Name (for example `orders-jobs`); keep the default visibility timeout, retention and dead-letter settings, or adjust
   them → **Create queue**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Queue OCID | queue details → *OCID* | `ocid1.queue.oc1.iad.aaaa` |
| Messages endpoint | queue details → *Messages endpoint* | `https://cell-1.queue.messaging.us-ashburn-1.oci.oraclecloud.com` |
| Name | queue details | `orders-jobs` |

## 3. Policies

```
Allow dynamic-group pskit-functions to use queues in compartment <name>
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
  jobs:
    type: queue
    external: true                 # required: no managed queues on OCI
    name: orders-jobs
    connection:
      ocid: ocid1.queue.oc1.iad.aaaa
      endpoint: https://cell-1.queue.messaging.us-ashburn-1.oci.oraclecloud.com

functions:
  submit:
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
```

## 5. Use it in a handler

`requirements.txt`: `oci`

```python
import json

import oci
from py_serverless_kit import resource


def submit(event, ctx):
    jobs = resource("jobs")
    client = oci.queue.QueueClient(
        config={}, signer=oci.auth.signers.get_resource_principals_signer(), service_endpoint=jobs["endpoint"]
    )
    entry = oci.queue.models.PutMessagesDetailsEntry(content=json.dumps(event.http.json()))
    client.put_messages(jobs["ocid"], oci.queue.models.PutMessagesDetails(messages=[entry]))
    return {"queued": True}
```

Consuming: `client.get_messages(queue_id, ...)` then `delete_message(queue_id, receipt)`, from an HTTP-called function
or a process outside OCI Functions (there are no schedules on OCI in pskit).

## 6. Test

```bash
pskit validate
pskit deploy
pskit info                          # the submit URL
```

Console: queue → **Send messages** / **Poll for messages** to check what arrived.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` Oracle Cloud Functions does not support `queue` events in pskit `` | no queue triggers on OCI; remove the `queue` event |
| `NotAuthorizedOrNotFound` | dynamic group / `use queues` policy missing, or wrong queue OCID |
| Request hangs | use the queue's *Messages endpoint* as `service_endpoint`; the subnet needs a route to OCI services (service or NAT gateway) |
