# On-premises service: PostgreSQL

The catalog id is `postgres`. Kind is service. Group is Databases. Image is postgres:16-alpine. Published port is 5432. Extra ports are none. Roles are database. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is Adminer (database UI). Web UI names are none. GUI login choices are password.

Catalog notes: 

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-postgres --service postgres
pskit resources onprem status sample-postgres
```

pskit resources onprem usage sample-postgres prints how to connect. pskit resources onprem logs sample-postgres shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
