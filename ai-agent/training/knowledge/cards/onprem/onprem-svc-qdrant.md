# On-premises service: Qdrant (vector database)

The catalog id is `qdrant`. Kind is service. Group is Databases. Image is qdrant/qdrant:v1.12.4. Published port is 6333. Extra ports are 6334. Roles are database. Backup is no. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Dashboard. GUI login choices are none.

Catalog notes: Vector similarity search for embeddings (RAG, recommendations). REST on the port, gRPC on 6334; the API key is the password.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-qdrant --service qdrant
pskit resources onprem status sample-qdrant
```

pskit resources onprem usage sample-qdrant prints how to connect. pskit resources onprem logs sample-qdrant shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
