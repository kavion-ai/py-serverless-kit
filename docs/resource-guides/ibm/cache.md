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

```bash
export CACHE_PASSWORD='...'
export CACHE_CA_B64='LS0tLS1CRUdJTi...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: shop

provider:
  name: ibm
  region: us-south
  environment:
    CACHE_PASSWORD: ${env:CACHE_PASSWORD}
    CACHE_CA_B64: ${env:CACHE_CA_B64}

resources:
  cache:
    type: cache
    external: true
    connection:
      host: xxxx.databases.appdomain.cloud
      port: 30123
      user: admin
      password_env: CACHE_PASSWORD
      ca_cert_env: CACHE_CA_B64

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /hits}]
```

## 4. Use it in a handler

`requirements.txt`: `redis`

```python
import base64
import os
import tempfile

import redis
from py_serverless_kit import resource

_client = None


def api(event, ctx):
    global _client
    if _client is None:   # reuse the connection across warm invocations
        c = resource("cache")
        ca_path = os.path.join(tempfile.gettempdir(), "cache-ca.pem")
        with open(ca_path, "wb") as f:
            f.write(base64.b64decode(ctx.env[c["ca_cert_env"]]))
        _client = redis.Redis(host=c["host"], port=int(c["port"]), username=c["user"],
                              password=ctx.env[c["password_env"]], ssl=True, ssl_ca_certs=ca_path)
    return {"hits": _client.incr("hits")}
```

## 5. Test

```bash
pskit validate
pskit invoke -f api
pskit deploy
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `certificate verify failed` | pass the instance's CA certificate (`ssl_ca_certs`) |
| `WRONGPASS` | pass `username` as well as `password` (Redis 6+ ACL users) |
| connection timed out | enable the *Public* endpoint or check **Settings → Allowlist** |
