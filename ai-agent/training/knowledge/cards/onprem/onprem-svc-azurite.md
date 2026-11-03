# On-premises service: Azurite (Azure Blob + Queue emulator)

The catalog id is `azurite`. Kind is service. Group is Object storage. Image is mcr.microsoft.com/azure-storage/azurite:3.33.0. Published port is 10000. Extra ports are 10001. Roles are queue, storage. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are none. GUI login choices are none.

Catalog notes: Azure Storage blobs (port 10000) and queues (10001) with your own account name and key: the azure_blob / azure_queue drivers and the Azure SDKs work unchanged. Browse it with Azure Storage Explorer.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-azurite --service azurite
pskit resources onprem status sample-azurite
```

pskit resources onprem usage sample-azurite prints how to connect. pskit resources onprem logs sample-azurite shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
