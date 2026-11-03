# Alibaba Cloud Tair / Redis (`type: cache`)

Tair (Redis OSS-compatible), formerly ApsaraDB for Redis. pskit never creates caches: declare them with
`external: true`.

## 1. Create the instance (console)

1. Console → **Tair (Redis OSS-Compatible)** → **Instances** → **Create Instance**: region, edition, engine version,
   architecture, **VPC** and vSwitch, password for the default account → buy.
2. Network access, pick one:
   - **Public endpoint**: instance → **Connection Information** → **Apply for Public Endpoint**, then
     **Whitelist Settings** to allow the callers.
   - **VPC** (recommended): run the function in the same VPC (`vpc_config` function option, see
     [database.md](database.md#3-declare-it-in-pskityml)) and whitelist the vSwitch CIDR.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host | instance → **Connection Information** → *VPC endpoint* or *Public endpoint* | `r-xxxx.redis.rds.aliyuncs.com` |
| Port | **Connection Information** | `6379` |
| Password | set at creation (**Account Management** → reset). For an account other than the default one, the password is `<user>:<password>` | `...` |
| TLS | **TLS Settings** (off by default) | |

```bash
export CACHE_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: shop

provider:
  name: alibaba
  region: cn-hangzhou
  environment:
    CACHE_PASSWORD: ${env:CACHE_PASSWORD}

resources:
  cache:
    type: cache
    external: true
    connection:
      host: r-xxxx.redis.rds.aliyuncs.com
      port: 6379
      ssl: false
      password_env: CACHE_PASSWORD

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /hits}]
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
        _client = redis.Redis(host=c["host"], port=int(c["port"]), ssl=c.get("ssl") == "true",
                              password=ctx.env[c["password_env"]])
    return {"hits": _client.incr("hits")}
```

Booleans in `connection` arrive as the strings `"true"` / `"false"`.

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send --list
```

Console: instance → **Logon Database** (DMS) to run `GET hits`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timeout | whitelist the caller, or use the VPC endpoint from inside the VPC |
| `WRONGPASS` / `invalid password` | for a non-default account the password is `<user>:<password>` |
