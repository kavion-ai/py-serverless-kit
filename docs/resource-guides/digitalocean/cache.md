# DigitalOcean Managed Valkey (`type: cache`)

Managed Valkey is DigitalOcean's Redis-compatible cache (it replaced Managed Redis). pskit never creates caches: declare
them with `external: true`.

## 1. Create the cluster (control panel)

Control panel → **Databases** → **Create Database Cluster** → engine **Valkey** → datacenter region, plan, name →
**Create Database Cluster**.

## 2. Collect the values

| Value | Where in the control panel | Example |
|---|---|---|
| Host / port | cluster → **Overview** → **Connection details** → *Public network* | `acme-cache-do-user-0.db.ondigitalocean.com`, `25061` |
| User / password | same panel | `default` / `...` |
| Connection string | same panel → *Connection string* | `rediss://default:...@acme-cache-do-user-0.db.ondigitalocean.com:25061` |

TLS is required (`rediss://`).

```bash
export CACHE_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: shop

provider:
  name: digitalocean
  region: nyc1
  options:
    namespace: fn-00000000-0000-0000-0000-000000000000
  environment:
    CACHE_PASSWORD: ${env:CACHE_PASSWORD}

resources:
  cache:
    type: cache
    external: true
    connection:
      host: acme-cache-do-user-0.db.ondigitalocean.com
      port: 25061
      user: default
      ssl: true
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
        _client = redis.Redis(host=c["host"], port=int(c["port"]), username=c["user"],
                              password=ctx.env[c["password_env"]], ssl=c.get("ssl") == "true")
    return {"hits": _client.incr("hits")}
```

Booleans in `connection` arrive as the strings `"true"` / `"false"`.

## 5. Test

```bash
pskit validate
pskit invoke -f api
pskit deploy
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| connection reset | TLS is required: `ssl=True` / `rediss://` |
| timed out from the function | trusted sources block it, see [README](README.md#values-you-need-for-most-digitalocean-services) |
| `WRONGPASS` | password reset in the control panel: update `CACHE_PASSWORD` and redeploy |
