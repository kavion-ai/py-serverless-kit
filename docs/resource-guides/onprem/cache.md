# On-premises caches (`type: cache`)

A Redis / Valkey (or Memcached) server your functions use as a cache. pskit never creates or watches it: declare it
with `external: true`.

To use Redis as a **queue** that triggers functions, see [queue.md](queue.md#redis--valkey) instead. One Redis server can
serve both; give them separate keys or databases (`/0`, `/1`).

## 1. Set up Redis

- **Docker:** `docker run -d --name cache -p 6379:6379 redis:7 redis-server --requirepass <password> --maxmemory 256mb --maxmemory-policy allkeys-lru`
  (Valkey: `valkey/valkey:8`).
- **Linux package:** `sudo apt install redis-server`; in `/etc/redis/redis.conf` set `requirepass`, `bind`,
  `maxmemory` and `maxmemory-policy allkeys-lru`; `sudo systemctl restart redis-server`.
- **Managed:** copy host, port and password from the provider's console (TLS: `rediss://`).

## 2. Collect the values

| Value | Example |
|---|---|
| Host / port | `cache.internal` / `6379` |
| Database number | `1` |
| Password | in `CACHE_PASSWORD` on the host |

Test from the host machine: `redis-cli -h cache.internal -a "$CACHE_PASSWORD" ping`.

## 3. Declare it in `pskit.yml`

```yaml
resources:
  cache:
    type: cache
    external: true                 # required for cache
    connection:
      host: cache.internal
      port: 6379
      db: 1
      ssl: false
      password_env: CACHE_PASSWORD
```

## 4. Use it in a handler

`requirements.txt`: `redis`

```python
import redis
from py_serverless_kit import resource

_client = None


def api(event, ctx):
    global _client
    if _client is None:            # the host is long-running: connect once
        c = resource("cache")
        _client = redis.Redis(host=c["host"], port=int(c["port"]), db=int(c["db"]),
                              ssl=c.get("ssl") == "true", password=ctx.env[c["password_env"]])
    return {"hits": _client.incr("hits")}
```

Booleans in `connection` arrive as the strings `"true"` / `"false"`.

## 5. Test

```bash
pskit validate
CACHE_PASSWORD=... pskit invoke -f api
pskit deploy
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `NOAUTH Authentication required` | `CACHE_PASSWORD` isn't set where the host runs |
| `Connection refused` | `bind` / `protected-mode` in `redis.conf`, or the firewall |
| `options.driver is not used for cache resources` | caches have no driver; to trigger functions use a [queue](queue.md#redis--valkey) |
