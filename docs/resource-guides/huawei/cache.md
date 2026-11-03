# Huawei DCS for Redis (`type: cache`)

Distributed Cache Service (DCS) for Redis. pskit never creates caches: declare them with `external: true`.

## 1. Create the instance (console)

1. Console → **Distributed Cache Service for Redis** → **Buy DCS Instance**.
2. Region (same as the functions), Redis version, instance type, capacity; **VPC** and **subnet**; password (or
   password-free access, not recommended) → **Submit**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host | instance → **Basic Information** → *Connection* → *Connection Address* (or *Domain Name Address*) | `redis-abc.dcs.huaweicloud.com` |
| Port | same panel | `6379` |
| Password | set when buying (reset with **More → Reset Password**) | |
| VPC / subnet | **Basic Information** → *Network* | |

```bash
export CACHE_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: shop

provider:
  name: huawei
  region: cn-north-4
  options:
    apig_instance_id: 0123456789abcdef0123456789abcdef
  iam:
    role: pskit-functions
  environment:
    CACHE_PASSWORD: ${env:CACHE_PASSWORD}

resources:
  cache:
    type: cache
    external: true
    connection:
      host: redis-abc.dcs.huaweicloud.com
      port: 6379
      password_env: CACHE_PASSWORD

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /hits}]
    options:
      vpc_id: 11111111-2222-3333-4444-555555555555
      network_id: 66666666-7777-8888-9999-000000000000
```

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
        _client = redis.Redis(host=c["host"], port=int(c["port"]), password=ctx.env[c["password_env"]])
    return {"hits": _client.incr("hits")}
```

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send --list
```

Console: DCS instance → **Connect to Redis** (Web CLI) → `GET hits`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timed out | function not in the instance's VPC (`vpc_id` / `network_id`, agency with VPC permissions) |
| `NOAUTH` / `WRONGPASS` | password changed: update `CACHE_PASSWORD` and redeploy |
