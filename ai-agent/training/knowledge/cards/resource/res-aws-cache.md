# Resource: AWS ElastiCache or MemoryDB

On AWS, `type: cache` is Redis OSS or Valkey on ElastiCache (serverless or node-based) or MemoryDB. The schema requires `external: true`. pskit passes the endpoint and leaves the cache in place.

ElastiCache and MemoryDB are reachable from inside their VPC. A function that uses the cache sets `options.vpc_config` with subnet ids and a security group. The same ENI actions as the database guide go under `provider.iam.statements`. Allow custom TCP 6379 from that security group on the cache security group.

Collect the endpoint (serverless Endpoint, or Primary / Configuration endpoint for cluster mode), the port (6379 in the guide), and whether encryption in transit is on. Serverless requires encryption in transit. An optional user-group password is `password_env`, with `CACHE_PASSWORD: ${env:CACHE_PASSWORD}` on the provider environment.

`requirements.txt` gets `redis`. Build the client once and reuse it across warm invocations. `ssl` is true when `resource("cache").get("ssl") == "true"`, because connection booleans arrive as `"true"` and `"false"`. Pass `password` only when `password_env` is set. A cluster-mode endpoint uses `redis.cluster.RedisCluster`.

Open:

Resources > + Add resource

Resources > How to use

```
pskit validate
pskit trigger -f api -e 0
pskit resources send --list
```

A timeout while connecting means `vpc_config` is missing, the subnets are wrong, or the security group rule is missing. `Connection reset by peer` with encryption in transit means the client should connect with TLS.

Sources: `docs/resource-guides/aws/cache.md#amazon-elasticache-memorydb-type-cache`, `docs/resource-guides/aws/cache.md#4-use-it-in-a-handler`
