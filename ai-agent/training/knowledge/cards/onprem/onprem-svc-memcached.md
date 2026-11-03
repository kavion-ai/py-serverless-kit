# On-premises service: Memcached

The catalog id is `memcached`. Kind is service. Group is Caches and queues. Image is memcached:1.6-alpine. Published port is 11211. Extra ports are none. Roles are cache. Backup is no. Persistent data is no. Auth is no. Default user is pskit. Companion UI is none. Web UI names are none. GUI login choices are none.

Catalog notes: In-memory cache; nothing to back up.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-memcached --service memcached
pskit resources onprem status sample-memcached
```

pskit resources onprem usage sample-memcached prints how to connect. pskit resources onprem logs sample-memcached shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
