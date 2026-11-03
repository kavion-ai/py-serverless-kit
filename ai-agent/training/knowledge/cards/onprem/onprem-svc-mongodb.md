# On-premises service: MongoDB

The catalog id is `mongodb`. Kind is service. Group is Databases. Image is mongo:7. Published port is 27017. Extra ports are none. Roles are database. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is Mongo Express. Web UI names are none. GUI login choices are password, none.

Catalog notes: 

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-mongodb --service mongodb
pskit resources onprem status sample-mongodb
```

pskit resources onprem usage sample-mongodb prints how to connect. pskit resources onprem logs sample-mongodb shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
