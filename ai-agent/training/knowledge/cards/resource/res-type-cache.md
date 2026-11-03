# Resource: cache

A cache resource is a fast key-value store in front of a database or a slow API. Use it for session data, counters, and results you can rebuild. pskit passes the connection. It leaves the cache in place.

The schema requires `external: true` for `type: cache`. The guide index names Amazon ElastiCache / MemoryDB, Azure Redis, Memorystore, Alibaba Tair (Redis), TencentDB for Redis, Huawei DCS, OCI Cache, IBM Databases for Redis, DigitalOcean Managed Valkey, Cloudflare Workers KV, and on-premises Redis / Valkey.

Declare `type: cache`, `external: true`, and `connection` scalars such as `host`, `port`, and `ssl`. A password is `password_env` naming a variable, with the value supplied by `${env:NAME}` or the on-prem env file. Booleans in `connection` arrive as the strings `true` and `false`. `functions` limits who sees `PSKIT_RESOURCE_<KEY>_*`.

There is no cache trigger. A handler calls the client with `resource("cache")`. The library table lists `redis` and `ioredis` for Redis or Valkey, and `pymemcache` and `memjs` for Memcached. Workers KV is the Cloudflare cache guide's service, and that guide is the place for its client. On premises, a one-click Redis, Valkey, Dragonfly, or KeyDB service can fill this resource.

Open:

Resources > + Add resource

Resources > How to use

Resources > Test

```
pskit resources usage cache -p aws -s dev
pskit resources send --list
pskit trigger -f api -e 0
```

Managed caches on AWS, GCP, and Azure are reached from inside their network. The function options for that network are in each cloud's cache guide. `pskit resources check` reports whether the resource is reachable.

Sources: `docs/resources.md#fields`, `docs/resource-usage.md#databases-caches-and-other-services`, `src/py_serverless_kit/config/schema.py`
