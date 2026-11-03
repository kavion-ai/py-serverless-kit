# Azure Storage queue (`type: queue`)

Use a queue you created in an Azure storage account: trigger a function with its messages, send messages to it from a
handler, or both.

## 1. Create the queue (portal)

Skip this if the queue already exists.

1. Portal → search **Storage accounts** → open your account (or **+ Create**: pick a resource group, a globally unique
   name of 3-24 lowercase letters and digits, the region, *Standard* performance; keep the other defaults).
2. Left menu → **Data storage → Queues** → **+ Queue**.
3. Name it: 3-63 characters, **lowercase** letters, digits and single dashes (for example `orders-jobs`) → **OK**.

## 2. Collect the values

| Value | Where in the portal | Example |
|---|---|---|
| Queue name | Storage account → **Data storage → Queues** → the list | `orders-jobs` |
| Storage account name | Storage account → **Overview** → title at the top | `acmeprodstore` |
| Connection string | Storage account → **Security + networking → Access keys** → **Show** next to *key1 → Connection string* → copy | `DefaultEndpointsProtocol=https;AccountName=acmeprodstore;AccountKey=...;EndpointSuffix=core.windows.net` |
| Queue URL | Queues → click the queue → **Properties** (or build it) | `https://acmeprodstore.queue.core.windows.net/orders-jobs` |
| Resource group / region | Storage account → **Overview** | `acme-rg` / `westeurope` |

Prefer a narrower credential? Use **Security + networking → Shared access signature**: tick *Queue* service,
*Object* resource type, *Read, Add, Update, Process* permissions, set an expiry, **Generate SAS and connection string**,
then copy *Connection string*. Remember to renew it before it expires.

Store the connection string as an environment variable on the machine (or CI) that runs `pskit deploy`. Do not put it in
`pskit.yml`:

```bash
export ORDERS_QUEUE_CONN='DefaultEndpointsProtocol=https;AccountName=acmeprodstore;AccountKey=...'
# PowerShell: $env:ORDERS_QUEUE_CONN = 'DefaultEndpointsProtocol=https;...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID}
    storage_connection: ORDERS_QUEUE_CONN          # app setting the queue trigger connects with
  environment:
    ORDERS_QUEUE_CONN: ${env:ORDERS_QUEUE_CONN}    # creates that app setting on the Function App

resources:
  jobs:                          # key used in code: resource("jobs")
    type: queue
    external: true               # created in the portal; pskit never creates or deletes it
    name: orders-jobs            # the queue name from step 2
    connection:
      account: acmeprodstore
      url: https://acmeprodstore.queue.core.windows.net/orders-jobs
      connection_string_env: ORDERS_QUEUE_CONN    # the NAME of the app setting, not its value

functions:
  worker:                        # triggered by every message
    handler: app.handlers.work
    events:
      - queue: {resource: jobs, batch_size: 16}
  api:                           # sends messages to the queue
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
```

What each part does:

- `external: true` + `name` tells pskit the queue exists. It creates no `azurerm_storage_queue`.
- `queue: {resource: jobs}` adds a queue trigger on `orders-jobs`.
- `storage_connection` is required when the queue is in **another storage account** than the one pskit creates (it
  always is, when you made it in the portal). Without it, the trigger looks for `orders-jobs` in pskit's own account and
  never fires. `storage_connection` applies to every external queue and blob container of the service, so keep them in
  one storage account.
- `environment` puts the connection string into the Function App's app settings.

Only sending, no trigger? Drop the `worker` function and `storage_connection`; keep the resource, the `environment`
entry and `connection_string_env`.

## 4. Use it in a handler

`requirements.txt`:

```
azure-storage-queue
```

`app/handlers.py`:

```python
import json

from azure.storage.queue import QueueClient, TextBase64EncodePolicy
from py_serverless_kit import resource


def submit(event, ctx):
    jobs = resource("jobs")
    client = QueueClient.from_connection_string(
        ctx.env[jobs["connection_string_env"]],
        jobs.native_name,                              # "orders-jobs"
        message_encode_policy=TextBase64EncodePolicy(),  # the Functions trigger expects base64
    )
    client.send_message(json.dumps(event.http.json()))
    return {"queued": True}


def work(event, ctx):
    for record in event.records:
        ctx.logger.info("job received", extra={"id": record.id, "body": record.body})
```

Messages must be **base64-encoded**: the Azure Functions queue trigger decodes base64 by default. Messages sent as plain
text from another tool end up in the poison queue `orders-jobs-poison`.

The function also receives these app settings:

```
PSKIT_RESOURCE_JOBS_TYPE=queue
PSKIT_RESOURCE_JOBS_NAME=orders-jobs
PSKIT_RESOURCE_JOBS_EXTERNAL=true
PSKIT_RESOURCE_JOBS_ACCOUNT=acmeprodstore
PSKIT_RESOURCE_JOBS_URL=https://acmeprodstore.queue.core.windows.net/orders-jobs
PSKIT_RESOURCE_JOBS_CONNECTION_STRING_ENV=ORDERS_QUEUE_CONN
```

## 5. Test

```bash
pskit validate
pskit invoke -f worker -d '{"order_id": 1}'      # locally, no cloud needed
pskit deploy

# send a real message to the queue (uses the queue's own account)
export AZURE_STORAGE_CONNECTION_STRING="$ORDERS_QUEUE_CONN"
pskit resources send jobs -d '{"order_id": 1}'
pskit logs -f --function worker
```

In the portal: Storage account → **Queues** → `orders-jobs` → **+ Add message** (leave *Encode the message body in
Base64* ticked) to send one by hand; the message disappears once `worker` has processed it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Messages stay in the queue, `worker` never runs | `provider.options.storage_connection` is missing, or the app setting it names is not in `environment` |
| Messages move to `<queue>-poison` | the handler raised 5 times, or the message wasn't base64 (use `TextBase64EncodePolicy`) |
| `KeyError: 'ORDERS_QUEUE_CONN'` in the handler | add it under `provider.environment` |
| `environment variable ORDERS_QUEUE_CONN is not set` during deploy | export it in the shell that runs `pskit deploy` |
| `AuthorizationFailure` / `403` | the storage account's **Networking** blocks public access, or the SAS lacks permissions / has expired |
| A setting added in the portal disappeared | pskit owns the app settings; declare it in `environment` |
