# Azure resources

How to attach Azure services you created in the [Azure portal](https://portal.azure.com) to an Azure Functions
deployment made with pskit.

| `type` | Azure service | Guide |
|---|---|---|
| `queue` | Storage account → Queue | [queue.md](queue.md) |
| `storage` | Storage account → Blob container | [storage.md](storage.md) |
| `topic` | Service Bus namespace → Topic | [topic.md](topic.md) |
| `database` | Azure Database for PostgreSQL / MySQL, Azure SQL | [database.md](database.md) |
| `cache` | Azure Cache for Redis / Azure Managed Redis | [cache.md](cache.md) |
| `custom` | Cosmos DB, Key Vault, Event Hubs, anything else | [custom.md](custom.md) |

## Values you need for every Azure resource

Open the resource in the portal and look at **Overview** (the "Essentials" panel at the top):

| Value | Where |
|---|---|
| Resource group | Overview → *Resource group* |
| Location (region) | Overview → *Location* |
| Subscription ID | Overview → *Subscription ID* |
| Resource ID | Overview → *JSON View* (top right) → *Resource ID*, or **Settings → Properties** |

## How pskit runs on Azure (why some steps matter)

- All functions of a service run in **one Function App**. Its *app settings* are the functions' environment variables,
  and they are shared by every function, so every function sees every resource binding.
- pskit creates its **own storage account** for the Function App. Queue and blob triggers use it (app setting
  `AzureWebJobsStorage`) unless you point them elsewhere. A queue or container you created in a different storage
  account therefore needs `provider.options.storage_connection`: the **name** of an app setting holding that account's
  connection string. See [queue.md](queue.md#3-declare-it-in-pskityml).
- pskit manages the Function App's app settings with Terraform. A setting you add by hand in the portal
  (*Function App → Settings → Environment variables*) is removed on the next `pskit deploy`. Add settings through
  `environment:` in `pskit.yml` instead.
- Topic triggers need `provider.options.servicebus_namespace_id` and `servicebus_connection`. See [topic.md](topic.md).

## Credentials for deploying

```bash
az login
export ARM_SUBSCRIPTION_ID=<subscription id>     # PowerShell: $env:ARM_SUBSCRIPTION_ID = "<id>"
```
