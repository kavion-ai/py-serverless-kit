# Resource: Azure Blob container

On Azure, `type: storage` is a blob container in a storage account. Use it when an upload should run a function, or when a handler reads and writes blobs. Azure can also create a managed container. The guide is the path for a container that already exists.

Container names are 3–63 characters: lowercase letters, digits, and single dashes. Anonymous access in the guide is Private. Collect the container name, the storage account name, and a connection string or a SAS. Keep the connection string in an environment variable. The guide maps `INVOICES_STORAGE_CONN: ${env:INVOICES_STORAGE_CONN}` and sets `provider.options.storage_connection` to that app setting name so the blob trigger can connect. `connection` holds `account`, `url`, and `connection_string_env`.

A storage event names the resource and can set `prefix` and `suffix`. Azure blob triggers fire on created or updated blobs. `events: [deleted]` is a validation error. `storage_connection` is shared by every external queue and container of the service, so those triggers stay in one storage account. Another account is read with the SDK and `connection_string_env`, with no trigger.

`requirements.txt` gets `azure-storage-blob`. `BlobServiceClient.from_connection_string(ctx.env[invoices["connection_string_env"]])` opens the account, and `get_blob_client(native_name, record.key)` reads one blob. Node.js uses `@azure/storage-blob`.

Open:

Resources > + Add resource

Resources > Browse account

```
pskit validate
pskit resources send invoices -d '{"key": "incoming/a.pdf", "content": "test"}'
pskit logs -f --function on-invoice
```

The guide sets `AZURE_STORAGE_CONNECTION_STRING` from that same variable before `pskit resources send`. A missing `storage_connection`, or a value absent from `environment`, means the trigger never fires. On the Consumption plan the trigger polls, so a delay of minutes is described as normal. A container name that is not 3–63 lowercase fails validation.

Sources: `docs/resource-guides/azure/storage.md#azure-blob-container-type-storage`, `docs/events.md#storage`
