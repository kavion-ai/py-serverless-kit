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

## 4. Use it in a handler

`requirements.txt`: `redis`

Booleans in `connection` arrive as the strings `"true"` / `"false"`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| connection reset | TLS is required: `ssl=True` / `rediss://` |
| timed out from the function | trusted sources block it, see README |
| `WRONGPASS` | password reset in the control panel: update `CACHE_PASSWORD` and redeploy |

```bash
export CACHE_PASSWORD='...'
```
