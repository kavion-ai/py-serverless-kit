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

## 4. Use it in a handler

`requirements.txt`: `redis`

Booleans in `connection` arrive as the strings `"true"` / `"false"`.

## 5. Test

Portal: Cache → **Console** to run `GET hits`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection reset / timeout | use the TLS port (6380 / 10000) with `ssl=True`; check **Networking** allows public access |
| `WRONGPASS` / `NOAUTH` | key regenerated: update `CACHE_KEY` and redeploy |

```bash
export CACHE_KEY='...'
```
