# Amazon ElastiCache / MemoryDB (`type: cache`)

Redis OSS or Valkey on ElastiCache (serverless or node-based) or MemoryDB. pskit never creates caches: declare them
with `external: true`.

ElastiCache and MemoryDB are **only reachable from inside their VPC**. pskit deploys Lambda functions outside any VPC
unless you set `functions.<fn>.options.vpc_config`, so a function that uses the cache needs it (see step 3).

## 1. Create the cache (console)

1. Console → **ElastiCache** → **Valkey caches** (or **Redis OSS caches**) → **Create cache**.
2. *Serverless* (simplest) or *Design your own cache*; name.
3. **Connectivity**: VPC, subnets, security group. Encryption in transit is on (required for serverless).
4. Optional: **Access control** → a user group with a password (`AUTH`).
5. **Create**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Endpoint | the cache → **Cache details** → *Endpoint* (serverless) or *Primary endpoint* / *Configuration endpoint* (cluster mode) | `orders-cache-abc123.serverless.euw1.cache.amazonaws.com` |
| Port | part of the endpoint | `6379` |
| TLS | *Encryption in transit* | enabled |
| VPC, subnets, security group | **Connectivity and security** | `subnet-...`, `sg-...` |
| Password | the user group's user, if configured | |

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: aws
  region: eu-west-1
  iam:
    statements:                    # ENI permissions for a Lambda in a VPC
      - actions: [ec2:CreateNetworkInterface, ec2:DescribeNetworkInterfaces, ec2:DescribeSubnets,
                  ec2:DeleteNetworkInterface, ec2:AssignPrivateIpAddresses, ec2:UnassignPrivateIpAddresses]
        resources: ["*"]

resources:
  cache:
    type: cache
    external: true
    connection:
      host: orders-cache-abc123.serverless.euw1.cache.amazonaws.com
      port: 6379
      ssl: true

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /hits}]
    options:
      vpc_config:
        subnet_ids: [subnet-0aaa, subnet-0bbb]
        security_group_ids: [sg-0lambda]
```

Allow it in the console: the cache's security group → **Edit inbound rules** → *Custom TCP* 6379, source `sg-0lambda`.

With an `AUTH` password: add `password_env: CACHE_PASSWORD` to `connection` and
`environment: {CACHE_PASSWORD: ${env:CACHE_PASSWORD}}` under `provider`.

## 4. Use it in a handler

`requirements.txt`: `redis`

```python
import redis
from py_serverless_kit import resource

_client = None


def api(event, ctx):
    global _client
    if _client is None:   # reuse the connection across warm invocations
        c = resource("cache")
        password_env = c.get("password_env")   # only set when the cache uses AUTH
        password = ctx.env[password_env] if password_env else None
        _client = redis.Redis(host=c["host"], port=int(c["port"]), ssl=c.get("ssl") == "true", password=password)
    return {"hits": _client.incr("hits")}
```

For a cluster-mode endpoint use `redis.cluster.RedisCluster` instead. Booleans in `connection` arrive as `"true"` /
`"false"`.

## 5. Test

```bash
pskit validate
pskit deploy
pskit trigger -f api -e 0
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Function times out connecting | no `vpc_config`, wrong subnets, or the security group rule is missing |
| `Connection reset by peer` | encryption in transit is on: connect with `ssl=True` |
| `CreateNetworkInterface` permission error on deploy | add the EC2 statement above |
