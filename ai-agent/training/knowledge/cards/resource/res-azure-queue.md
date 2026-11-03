# Azure Storage queue (`type: queue`)

Use a queue you created in an Azure storage account: trigger a function with its messages, send messages to it from a handler, or both.
## 1. Create the queue (portal) Skip this if the queue already exists.

1. Portal → search **Storage accounts** → open your account (or **+ Create**: pick a resource group, a globally unique name of 3-24 lowercase letters and digits, the region, *Standard* performance; keep the other defaults). 2. Left menu → **Data storage → Queues** → **+ Queue**. 3. Name it: 3-63 characters, **lowercase** letters, digits and single dashes (for example `orders-jobs`) → **OK**.
## 2. Collect the values | Value | Where in the portal | Example | |---|---|---| |

Queue name | Storage account → **Data storage → Queues** → the list | `orders-jobs` | | Storage account name | Storage account → **Overview** → title at the top | `acmeprodstore` | | Connection string | Storage account → **Security + networking → Access keys** → **Show** next to *key1 → Connection string* → copy | `DefaultEndpointsProtocol=https;AccountName=acmeprodstore;AccountKey=...;EndpointSuffix=core.windows.net` | | Queue URL | Queues → click the queue → **Properties** (or build it) | `https://acmeprodstore.queue.core.windows.net/orders-jobs` | | Resource group / region | Storage account → **Overview** | `acme-rg` / `westeurope` | Prefer a narrower credential? Use **Security + networking → Shared access signature**: tick *Queue* service, *Object* resource type, *Read, Add, Update, Process* permissions, set an expiry, **Generate SAS and connection string**, then copy *Connection string*. Remember to renew it before it expires. Store the connection string as an environment variable on the machine (or CI) that runs `pskit deploy`. Do not put it in `pskit.yml`:
## 3. Declare it in `pskit.yml`

What each part does: - `external: true` + `name` tells pskit the queue exists. It creates no `azurerm_storage_queue`. - `queue: {resource: jobs}` adds a queue trigger on `orders-jobs`. - `storage_connection` is required when the queue is in **another storage account** than the one pskit creates (it always is, when you made it in the portal). Without it, the trigger looks for `orders-jobs` in pskit's own account and never fires. `storage_connection` applies to every external queue and blob container of the service, so keep them in one storage account. - `environment` puts the connection string into the Function App's app settings. Only sending, no trigger? Drop the `worker` function and `storage_connection`; keep the resource, the `environment` entry and `connection_string_env`.
## 4. Use it in a handler `requirements.txt`: `app/handlers.py`: Messages must be

**base64-encoded**: the Azure Functions queue trigger decodes base64 by default.

```bash
export ORDERS_QUEUE_CONN='DefaultEndpointsProtocol=https;AccountName=acmeprodstore;AccountKey=...'
# PowerShell: $env:ORDERS_QUEUE_CONN = 'DefaultEndpointsProtocol=https;...'
```
