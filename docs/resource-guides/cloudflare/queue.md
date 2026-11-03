# Cloudflare Queues (`type: queue`)

Send messages to a Cloudflare queue from a Worker, and consume them. pskit has **no queue trigger on Cloudflare**, so a
Worker can't be a push consumer. Consume with a scheduled function that pulls over HTTP, or from an on-premises host.

## 1. Create the queue (dashboard)

1. Dashboard → **Workers & Pages → Queues** (also listed under *Storage & databases*) → **Create queue**.
2. Name: lowercase letters, digits and dashes (for example `shop-jobs`) → **Create**.
3. To consume it over HTTP: queue → **Settings** (or *Consumers*) → **Add consumer** → type **HTTP pull** → set the
   visibility timeout and retries → **Add**. A queue has only one consumer.

## 2. Collect the values

| Value | Where | Example |
|---|---|---|
| Queue name | **Queues** → the list | `shop-jobs` |
| Queue ID | queue → **Settings** → *Queue ID* (or the queue's URL) | `fedcba9876543210fedcba9876543210` |
| Account ID | see [README](README.md#values-you-need-for-every-cloudflare-resource) | |
| API token (pull consumer only) | **My Profile → API Tokens → Create Token** → *Custom token* → permission **Account → Queues → Edit** | |

```bash
export CF_QUEUES_TOKEN=...
```

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID}
    workers_subdomain: my-team

resources:
  jobs:
    type: queue
    external: true                       # required on Cloudflare
    name: shop-jobs
    connection:
      binding: JOBS
      queue_id: fedcba9876543210fedcba9876543210
      account_id: ${env:CLOUDFLARE_ACCOUNT_ID}

functions:
  api:                                   # producer
    handler: app.handlers.api
    events: [{http: POST /jobs}]
    options:
      bindings:
        - {type: queue, name: JOBS, queue_name: shop-jobs}
  drain:                                 # consumer: pulls every minute
    handler: app.handlers.drain
    events: [{schedule: 1 minute}]
    options:
      bindings:
        - {type: secret_text, name: CF_QUEUES_TOKEN, text: "${env:CF_QUEUES_TOKEN}"}
```

## 4. Use it in a handler

```python
import json

from js import Object, fetch
from pyodide.ffi import to_js
from py_serverless_kit import resource


def _js(value):
    return to_js(value, dict_converter=Object.fromEntries)


async def api(event, ctx):
    jobs = resource("jobs")
    queue = getattr(ctx.raw, jobs["binding"])
    # content type "text" so the HTTP pull consumer gets the JSON string back unchanged
    await queue.send(json.dumps(event.http.json()), _js({"contentType": "text"}))
    return {"queued": True}


async def drain(event, ctx):
    jobs = resource("jobs")
    base = f'https://api.cloudflare.com/client/v4/accounts/{jobs["account_id"]}/queues/{jobs["queue_id"]}/messages'
    headers = {"Authorization": f"Bearer {ctx.raw.CF_QUEUES_TOKEN}", "Content-Type": "application/json"}

    async def post(path, payload):
        resp = await fetch(base + path, _js({"method": "POST", "headers": headers, "body": json.dumps(payload)}))
        return json.loads(await resp.text())["result"]

    pulled = await post("/pull", {"batch_size": 10, "visibility_timeout_ms": 30000})
    acks, retries = [], []
    for msg in pulled.get("messages", []):
        try:
            ctx.logger.info("job", extra={"body": msg["body"]})
            acks.append({"lease_id": msg["lease_id"]})
        except Exception:
            retries.append({"lease_id": msg["lease_id"]})
    if acks or retries:
        await post("/ack", {"acks": acks, "retries": retries})
```

Messages that aren't acknowledged before the visibility timeout are delivered again; after the consumer's retry limit
they go to its dead-letter queue (if you set one in the consumer settings).

**Alternative consumer:** an [on-premises host](../onprem/queue.md) with `driver: cloudflare_queue` pulls the same
queue and runs a normal `queue` event handler, with batching, retries and dead letters handled by pskit.

## 5. Test

```bash
pskit validate
pskit deploy
curl -X POST -H 'content-type: application/json' -d '{"order_id": 1}' https://shop-dev-api.my-team.workers.dev/jobs
# logs: dashboard → Workers & Pages → shop-dev-drain → Logs
```

Dashboard: queue → **Messages** → **Send message** / **List messages** (only with an HTTP pull consumer).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `does not support `queue` events` | remove the `queue:` event; consume with a `schedule` function or an on-prem host |
| `/pull` returns an error about consumers | add an **HTTP pull** consumer to the queue |
| `401` / `10000 Authentication error` on `/pull` | the token needs **Queues Edit** on that account |
| Bodies arrive base64-encoded | the producer sent the default content type; pass `{"contentType": "text"}` |
