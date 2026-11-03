# On-premises service: Redis

The catalog id is `redis`. Kind is service. Group is Caches and queues. Image is redis:7-alpine. Published port is 6379. Extra ports are none. Roles are queue, stream, cache. Backup is yes. Persistent data is yes. Auth is yes. Default user is default. Companion UI is Redis Commander. Web UI names are none. GUI login choices are password, none.

Catalog notes: Queue (redis driver: leased lists), stream (redis_stream driver: consumer group, several hosts) or a cache for handlers.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-redis --service redis
pskit resources onprem status sample-redis
```

pskit resources onprem usage sample-redis prints how to connect. pskit resources onprem logs sample-redis shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
