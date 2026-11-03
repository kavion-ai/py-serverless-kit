# Azure Blob container (`type: storage`)

Use a blob container you created in an Azure storage account: run a function when a blob is uploaded, read or write
blobs from a handler, or both.

## 1. Create the container (portal)

1. Portal → **Storage accounts** → open your account (or **+ Create** one, see [queue.md](queue.md#1-create-the-queue-portal)).
2. Left menu → **Data storage → Containers** → **+ Container**.
3. Name: 3-63 characters, **lowercase** letters, digits and single dashes (for example `invoices`). Anonymous access
   level: *Private* → **Create**.

## 2. Collect the values

| Value | Where in the portal | Example |
|---|---|---|
| Container name | Storage account → **Data storage → Containers** | `invoices` |
| Storage account name | Storage account → **Overview** | `acmeprodstore` |
| Connection string | Storage account → **Security + networking → Access keys** → **Show** → *key1 Connection string* | `DefaultEndpointsProtocol=https;AccountName=acmeprodstore;AccountKey=...` |
| Container URL | Containers → click the container → **Settings → Properties** → *URL* | `https://acmeprodstore.blob.core.windows.net/invoices` |

For a SAS instead of the account key: **Security + networking → Shared access signature** → *Blob* service,
*Container* + *Object* resource types, the permissions you need → **Generate SAS and connection string**.

```bash
export INVOICES_STORAGE_CONN='DefaultEndpointsProtocol=https;AccountName=acmeprodstore;AccountKey=...'
```

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID}
    storage_connection: INVOICES_STORAGE_CONN     # blob trigger connects with this app setting
  environment:
    INVOICES_STORAGE_CONN: ${env:INVOICES_STORAGE_CONN}

resources:
  invoices:
    type: storage
    external: true
    name: invoices
    connection:
      account: acmeprodstore
      url: https://acmeprodstore.blob.core.windows.net/invoices
      connection_string_env: INVOICES_STORAGE_CONN

functions:
  on-invoice:
    handler: app.handlers.on_invoice
    events:
      - storage: {resource: invoices, prefix: incoming/, suffix: .pdf}
```

- Azure blob triggers fire on **created / updated** blobs only; `events: [deleted]` is a validation error.
- `storage_connection` is shared by every external queue and container of the service: keep them in the same storage
  account, or use the SDK with `connection_string_env` for the others (no trigger).

## 4. Use it in a handler

`requirements.txt`: `azure-storage-blob`

```python
from azure.storage.blob import BlobServiceClient
from py_serverless_kit import resource


def on_invoice(event, ctx):
    invoices = resource("invoices")
    service = BlobServiceClient.from_connection_string(ctx.env[invoices["connection_string_env"]])
    for record in event.records:
        blob = service.get_blob_client(invoices.native_name, record.key)
        data = blob.download_blob().readall()
        ctx.logger.info("invoice", extra={"key": record.key, "size": len(data)})
```

## 5. Test

```bash
pskit validate
pskit deploy
export AZURE_STORAGE_CONNECTION_STRING="$INVOICES_STORAGE_CONN"
pskit resources send invoices -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -f --function on-invoice
```

Portal: Containers → `invoices` → **Upload** a file into `incoming/` (use *Advanced → Upload to folder*).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Trigger never fires | `storage_connection` missing, or the setting isn't in `environment` |
| Fires with a delay of minutes | normal on the Consumption plan: blob triggers poll |
| `container name ... must be 3-63 lowercase` | rename the resource's `name` to the container's exact lowercase name |
| `403 AuthorizationPermissionMismatch` | SAS lacks the permission, or **Networking** restricts public access |
