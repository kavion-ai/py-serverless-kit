# Other Azure services (`type: custom`)

`custom` is for any service that isn't a bucket, queue, topic, database or cache: Cosmos DB, Key Vault, Event Hubs,
Azure AI services, a third-party API. pskit only passes its connection details to your functions (`external: true` is
required).

The recipe is always the same: find the **endpoint** and a **key or connection string** in the portal, keep the secret
in an app setting, and put the rest in `connection`.

## Cosmos DB (NoSQL)

**Create:** Portal → **Azure Cosmos DB** → **+ Create** → *Azure Cosmos DB for NoSQL* → resource group, account name,
region → **Review + create**. Then **Data Explorer** → **New Container** → database id `shop`, container id `orders`,
partition key `/customerId`.

**Collect:**

| Value | Where |
|---|---|
| URI | Account → **Settings → Keys** → *URI* (`https://acme-cosmos.documents.azure.com:443/`) |
| Key | **Settings → Keys** → *PRIMARY KEY* (use the *Read-only Keys* tab if you only read) |
| Database / container | **Data Explorer** |

## Key Vault

**Create:** Portal → **Key vaults** → **+ Create** → resource group, name, region; *Access configuration*:
*Azure role-based access control*. Then **Objects → Secrets → + Generate/Import**.

**Collect:** Vault → **Overview** → *Vault URI* (`https://acme-kv.vault.azure.net/`), and the secret names.

Reading secrets with `azure-keyvault-secrets` needs an identity. The Function App pskit creates has no managed identity,
so use a service principal: **Microsoft Entra ID → App registrations → + New registration**, then
**Certificates & secrets → + New client secret**; give it the *Key Vault Secrets User* role on the vault
(**Access control (IAM) → + Add role assignment**). Pass its tenant id, client id and secret like any other secret:

## Event Hubs

**Collect:** Namespace → **Overview** → *Host name*; **Entities → Event Hubs** → the hub name; hub → **Settings →
Shared access policies** → **+ Add** (*Send*) → *Connection string-primary key*.

pskit has no Event Hubs trigger; send from a handler with `azure-eventhub`, or consume from a `schedule` function.

```text
provider:
  environment:
    COSMOS_KEY: ${env:COSMOS_KEY}

resources:
  orders-store:
    type: custom
    external: true
    connection:
      endpoint: https://acme-cosmos.documents.azure.com:443/
      database: shop
      container: orders
      key_env: COSMOS_KEY
```
