# Tencent Cloud Redis (`type: cache`)

TencentDB for Redis. pskit never creates caches: declare them with `external: true`.

## 1. Create the instance (console)

1. Console → **TencentDB for Redis** → **Instance List** → **Create**: region, version, architecture, specification,
   **VPC** and subnet, password → buy.
2. Network access: TencentDB for Redis is reached through its **VPC** address. Run the function in the same VPC and
   subnet (`vpc_id` / `subnet_id` function options, see [database.md](database.md#3-declare-it-in-pskityml)) and allow
   the subnet in the instance's security group. Some versions also offer a public network address in **Instance
   Details**; check your console.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host / port | instance → **Instance Details** → *Private Network Address* | `10.0.0.20:6379` |
| Password | set at creation (**Account Management** → reset). For an account other than the default one, use the format shown in the console's connection example | `...` |
| VPC / subnet IDs | **Instance Details** → *Network* | `vpc-xxxx` / `subnet-xxxx` |

```bash
export CACHE_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: shop

provider:
  name: tencent
  region: ap-guangzhou
  environment:
    CACHE_PASSWORD: ${env:CACHE_PASSWORD}

resources:
  cache:
    type: cache
    external: true
    connection:
      host: 10.0.0.20
      port: 6379
      password_env: CACHE_PASSWORD

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /hits}]
    options:
      vpc_id: vpc-xxxx
      subnet_id: subnet-xxxx
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

Console: instance → **Log in to database** (DMC) to run `GET hits`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timeout | the function isn't in the instance's VPC / subnet, or the security group blocks it |
| `WRONGPASS` / `invalid password` | check the password format for non-default accounts in the console |
