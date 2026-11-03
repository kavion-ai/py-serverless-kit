# Azure Redis (`type: cache`)

Azure Cache for Redis or Azure Managed Redis. pskit never creates caches: declare them with `external: true`.

## 1. Create the cache (portal)

1. Portal → **Azure Managed Redis** (or **Azure Cache for Redis**) → **+ Create**.
2. Resource group, DNS name, region, SKU.
3. **Networking**: *Public endpoint* (the Consumption Function App can't use a private endpoint).
4. **Advanced**: keep *Access keys authentication* enabled → **Review + create**.

## 2. Collect the values

| Value | Where in the portal | Example |
|---|---|---|
| Host name | Cache → **Overview** → *Host name* (or *Endpoint*) | `acme-cache.redis.cache.windows.net` |
| Port | Azure Cache for Redis: **Settings → Advanced settings** → SSL port `6380`. Azure Managed Redis: Overview → *Endpoint* (port `10000`) | `6380` |
| Access key | **Settings → Authentication** (or *Access keys*) → *Primary* | `...` |
| TLS | always on; the non-TLS port `6379` is disabled by default | |

```bash
export CACHE_KEY='...'
```

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: azure
  environment:
    CACHE_KEY: ${env:CACHE_KEY}

resources:
  cache:
    type: cache
    external: true
    connection:
      host: acme-cache.redis.cache.windows.net
      port: 6380
      ssl: true
      password_env: CACHE_KEY
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
pskit resources send --list    # the variables and a Python / Node.js snippet for this cache
```

Portal: Cache → **Console** to run `GET hits`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection reset / timeout | use the TLS port (6380 / 10000) with `ssl=True`; check **Networking** allows public access |
| `WRONGPASS` / `NOAUTH` | key regenerated: update `CACHE_KEY` and redeploy |
