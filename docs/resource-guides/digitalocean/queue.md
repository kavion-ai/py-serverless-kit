# Queues on DigitalOcean (`type: queue`)

DigitalOcean has **no managed queue service**, and pskit has no `queue` trigger on DigitalOcean. The usual replacement
is a Redis-compatible list in a **Managed Valkey** cluster: producers `LPUSH`, a `schedule` function pops a batch every
minute.

| Need | Option |
|---|---|
| Simple work queue | Managed Valkey list (this page) |
| Durable stream, many consumers | Managed Kafka, see [topic.md](topic.md) |
| Messages handled the moment they arrive | the [on-premises host](../../resources.md#queue-drivers) with `driver: redis` on the same Valkey list |

## 1. Create the Valkey cluster (control panel)

1. Control panel → **Databases** → **Create Database Cluster** → engine **Valkey** (older accounts may show *Caching*
   / Redis).
2. Datacenter region, plan, cluster name → **Create Database Cluster**. Provisioning takes a few minutes.

## 2. Collect the values

| Value | Where in the control panel | Example |
|---|---|---|
| Connection string | cluster → **Overview** → **Connection details** → *Public network* → *Connection string* | `rediss://default:...@acme-valkey-do-user-0.db.ondigitalocean.com:25061` |
| Host / port / user / password | same panel, *Connection parameters* | `acme-valkey-do-user-0.db.ondigitalocean.com`, `25061`, `default` |
| Queue name | your choice: the Redis key of the list | `orders:jobs` |

TLS is required (`rediss://`).

```bash
export JOBS_REDIS_URL='rediss://default:...@acme-valkey-do-user-0.db.ondigitalocean.com:25061'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: digitalocean
  region: nyc1
  options:
    namespace: fn-00000000-0000-0000-0000-000000000000
  environment:
    JOBS_REDIS_URL: ${env:JOBS_REDIS_URL}

resources:
  jobs:
    type: queue
    external: true                  # required on DigitalOcean
    name: orders:jobs               # the list key
    connection:
      url_env: JOBS_REDIS_URL

functions:
  submit:                           # producer
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
  worker:                           # consumer, polls every minute
    handler: app.handlers.work
    events:
      - schedule: 1 minute
```

## 4. Use it in a handler

`requirements.txt`: `redis`

```python
import json

import redis
from py_serverless_kit import resource


def _client(ctx):
    return redis.Redis.from_url(ctx.env[resource("jobs")["url_env"]])


def submit(event, ctx):
    _client(ctx).lpush(resource("jobs").native_name, json.dumps(event.http.json()))
    return {"queued": True}


def work(event, ctx):
    r, key = _client(ctx), resource("jobs").native_name
    for _ in range(50):                       # at most 50 jobs per run
        raw = r.rpop(key)
        if raw is None:
            break
        ctx.logger.info("job", extra={"body": json.loads(raw)})
```

`RPOP` removes the message before it is processed, so a crash loses it. For at-least-once handling use `LMOVE` to a
`<key>:processing` list and remove it after success (the layout the on-premises `redis` driver uses, described in
[resources.md](../../resources.md#queue-drivers)).

## 5. Test

```bash
pskit validate
pskit invoke -f worker              # locally, against the real cluster
pskit deploy
pskit logs -f --function worker
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` DigitalOcean Functions does not support `queue` events in pskit `` | DigitalOcean has HTTP and schedule triggers only in pskit; use a `schedule` consumer |
| `rate ... can't be expressed as cron` | use a rate that divides 60 minutes (`1 minute`, `5 minutes`) |
| connection refused / timed out from the function | trusted sources on the cluster block it, see [README](README.md#values-you-need-for-most-digitalocean-services) |
| `SSL` errors | use the `rediss://` URL from *Public network* |
