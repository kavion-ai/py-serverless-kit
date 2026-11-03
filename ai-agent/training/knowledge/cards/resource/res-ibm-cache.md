# IBM Databases for Redis (`type: cache`)

pskit never creates caches: declare them with `external: true`.

## 1. Create the instance (console)

1. Console → **Catalog** → **Databases for Redis** → region, plan, resources → *Endpoints*: **Public** (or *Both*) →
   **Create**.
2. In the instance → **Settings** → **Change Database Admin password**, or create a user with **Service credentials →
   New credential**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host / port | instance → **Overview** → **Endpoints** → *Redis* tab → *Public* | `xxxx.databases.appdomain.cloud`, `30123` |
| User / password | `admin` and the password you set, or **Service credentials** → `connection.rediss.authentication` | `admin` / `...` |
| CA certificate | **Endpoints** tab → *TLS certificate* (base64) | `LS0tLS1CRUdJTi...` |

TLS is always on (`rediss://`), with the instance's self-signed CA.

## 4. Use it in a handler

`requirements.txt`: `redis`

## Troubleshooting

| Symptom | Fix |
|---|---|
| `certificate verify failed` | pass the instance's CA certificate (`ssl_ca_certs`) |
| `WRONGPASS` | pass `username` as well as `password` (Redis 6+ ACL users) |
| connection timed out | enable the *Public* endpoint or check **Settings → Allowlist** |

```bash
export CACHE_PASSWORD='...'
export CACHE_CA_B64='LS0tLS1CRUdJTi...'
```
