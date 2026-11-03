# OCI Cache (`type: cache`)

OCI Cache is a managed Redis / Valkey cluster. pskit never creates caches: declare them with `external: true`.

## 1. Create the cluster (console)

1. Console → **Databases → OCI Cache → Clusters** → **Create cluster**.
2. Name, software version, node count and memory; the **VCN and subnet** (use the functions' VCN, or one routed to
   it) → **Create**.
3. Allow port `6379` from the functions' subnet in the cluster subnet's security list / NSG.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Primary endpoint | cluster details → *Primary endpoint* (FQDN) | `aaaa-p.redis.us-ashburn-1.oci.oraclecloud.com` |
| Port | `6379` | |
| TLS | always on | |

OCI Cache relies on network access control; if you configured a user with a password (cluster → **Users**, where
available), keep it in an environment variable.

## 3. Declare it in `pskit.yml`

```yaml
service: shop

provider:
  name: oracle
  region: us-ashburn-1
  options:
    compartment_id: ocid1.compartment.oc1..aaaa
    subnet_ids: [ocid1.subnet.oc1..aaaa]
    image: iad.ocir.io/axabc12345/shop:1.0

resources:
  cache:
    type: cache
    external: true
    connection:
      host: aaaa-p.redis.us-ashburn-1.oci.oraclecloud.com
      port: 6379
      ssl: true

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
        _client = redis.Redis(host=c["host"], port=int(c["port"]), ssl=c.get("ssl") == "true")
    return {"hits": _client.incr("hits")}
```

Booleans in `connection` arrive as the strings `"true"` / `"false"`.

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send --list
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timed out | functions' subnet can't reach the cluster subnet, or port 6379 is closed |
| Connection reset | connect with TLS (`ssl=True`) |
