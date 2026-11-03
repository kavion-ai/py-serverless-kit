# Topics on Cloudflare (`type: topic`)

Cloudflare has no publish/subscribe topic service that pskit can use, and pskit has no `topic` trigger on Cloudflare.
A `topic:` event fails validation with `Cloudflare Workers does not support `topic` events in pskit`, and a managed
`type: topic` resource is rejected too.

## What to use instead

| Need | Option |
|---|---|
| Fan out one message to several consumers | one [queue](queue.md) per consumer; the producer sends to each (one `queue` binding per queue) |
| Call other functions directly | HTTP: each function has its own `workers.dev` URL or route (`pskit info`) |
| Publish to a topic in another cloud | declare it as `type: topic`, `external: true`, and call that cloud's HTTP API with `from js import fetch` (no SDKs on Python Workers) |
| Real topics with filters | deploy the consumers to a cloud that has them (`aws` SNS, `gcp` Pub/Sub, `azure` Service Bus, or `onprem`) |

## Example: an external topic in another cloud

Only connection details are passed; the handler talks to the API itself.

```yaml
resources:
  order-events:
    type: topic
    external: true
    name: order-events
    connection:
      publish_url: https://events.example.com/topics/order-events   # your own HTTP endpoint or a cloud REST API

functions:
  api:
    handler: app.handlers.api
    events: [{http: POST /orders}]
    options:
      bindings:
        - {type: secret_text, name: EVENTS_TOKEN, text: "${env:EVENTS_TOKEN}"}
```

```python
import json

from js import Object, fetch
from pyodide.ffi import to_js
from py_serverless_kit import resource


async def api(event, ctx):
    topic = resource("order-events")
    init = {"method": "POST", "body": json.dumps(event.http.json()),
            "headers": {"Authorization": f"Bearer {ctx.raw.EVENTS_TOKEN}", "Content-Type": "application/json"}}
    resp = await fetch(topic["publish_url"], to_js(init, dict_converter=Object.fromEntries))
    return {"status": resp.status}
```
