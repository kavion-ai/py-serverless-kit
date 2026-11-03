# Memorystore for Redis / Valkey (`type: cache`)

Memorystore has **only private IPs** in a VPC network. pskit's Cloud Functions don't run in a VPC and pskit has no VPC
option on GCP, so you need a **Serverless VPC Access connector** and add it to the function through
`provider.terraform.extra` (step 3).

## 1. Create the cache and the connector (console)

1. Console → **Memorystore** → **Redis** (or **Valkey**) → **Create instance**.
2. Instance ID, tier, capacity, region (`provider.region`), **Network**: your VPC (for example `default`).
3. Optional: **Security** → *Enable AUTH* and *In-transit encryption*. **Create instance**.
4. Console → **VPC network** → **Serverless VPC access** → **Create connector** → name `pskit-conn`, region
   `provider.region`, the same network, an unused `/28` range (for example `10.8.0.0/28`) → **Create**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host | the instance → **Overview** → *Primary endpoint* (IP) | `10.0.0.3` |
| Port | **Overview** → *Port* | `6379` (`6378` with in-transit encryption) |
| AUTH string | **Security** → *AUTH string* → show | |
| TLS CA | **Security** → *Download* the server CA (with in-transit encryption) | |
| Connector | **Serverless VPC access** → the connector | `projects/my-project/locations/europe-west1/connectors/pskit-conn` |

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: gcp
  region: europe-west1
  options:
    project: my-project
  environment:
    CACHE_PASSWORD: ${env:CACHE_PASSWORD}
  terraform:
    extra:
      resource:
        google_cloudfunctions2_function:
          api:                     # pskit's Terraform label for function `api`
            service_config:
              vpc_connector: projects/my-project/locations/europe-west1/connectors/pskit-conn
              vpc_connector_egress_settings: PRIVATE_RANGES_ONLY

resources:
  cache:
    type: cache
    external: true
    connection:
      host: 10.0.0.3
      port: 6379
      password_env: CACHE_PASSWORD

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /hits}]
```

`terraform.extra` is deep-merged into the generated config, so these two keys are added to the function's
`service_config` and pskit's other settings stay. The label is usually the function name with `-` replaced by `_`
(`on-invoice` → `on_invoice`); a function with several triggers is split into several Cloud Functions with other
labels. Run `pskit package` and look up
`google_cloudfunctions2_function` in `.pskit/gcp-<stage>/main.tf.json` to be sure.

Don't use `functions.<fn>.options.service_config`: function `options` replace top-level keys and would drop pskit's
`service_config` (memory, timeout, environment variables).

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
        password_env = c.get("password_env")
        _client = redis.Redis(host=c["host"], port=int(c["port"]),
                              password=ctx.env[password_env] if password_env else None)
    return {"hits": _client.incr("hits")}
```

With in-transit encryption: port `6378`, `ssl=True`, `ssl_ca_certs=` the downloaded CA bundled with your code.

## 5. Test

```bash
pskit validate
pskit package            # check the vpc_connector landed on the right function
pskit deploy
pskit trigger -f api -e 0
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Function times out connecting | no connector on that function (check the label), or the connector is in another region/network |
| Deploy: `vpc_connector` permission error | enable the Serverless VPC Access API; with a Shared VPC, the Cloud Functions service agent needs *Serverless VPC Access User* in the host project |
| `NOAUTH Authentication required` | AUTH is enabled: set `password_env` and the environment variable |
