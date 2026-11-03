# On-premises service: Typesense (search engine)

The catalog id is `typesense`. Kind is service. Group is Search. Image is typesense/typesense:27.1. Published port is 8108. Extra ports are none. Roles are custom. Backup is no. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are none. GUI login choices are none.

Catalog notes: Fast typo-tolerant search with a REST API (the API key is the password).

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-typesense --service typesense
pskit resources onprem status sample-typesense
```

pskit resources onprem usage sample-typesense prints how to connect. pskit resources onprem logs sample-typesense shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
