# Tencent Cloud TDMQ for CMQ topic (`type: topic`)

Publish to a topic from your functions. Tencent's original CMQ topics have moved to **TDMQ for CMQ**.

> **No topic trigger on Tencent Cloud.** pskit's Tencent provider has no `topic` event: `pskit validate` rejects
> `- topic: ...` there. Declare the topic as an external resource and publish with the Tencent Cloud SDK. Subscribers
> (queues, HTTP endpoints) are configured on the topic in the console.

## 1. Create the topic (console)

1. Console → **TDMQ** → **CMQ** → **Topic Subscription** (the exact label can differ by console version) → pick the
   region → **Create**.
2. Name (for example `order-events`) → **Submit**.
3. Optional: open the topic → **Subscription** → **Create** to deliver its messages to a queue or an HTTP endpoint
   (for example the URL of a pskit `http` function from `pskit info`).

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic name | TDMQ for CMQ → topic list | `order-events` |
| Region | the region selector | `ap-guangzhou` |
| SecretId / SecretKey | CAM sub-user with a TDMQ policy | `AKID...` |

```bash
export TDMQ_SECRET_ID=AKID...
export TDMQ_SECRET_KEY=...
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: tencent
  region: ap-guangzhou
  environment:
    TDMQ_SECRET_ID: ${env:TDMQ_SECRET_ID}
    TDMQ_SECRET_KEY: ${env:TDMQ_SECRET_KEY}

resources:
  order-events:
    type: topic
    external: true
    name: order-events
    connection:
      region: ap-guangzhou
      secret_id_env: TDMQ_SECRET_ID
      secret_key_env: TDMQ_SECRET_KEY

functions:
  publish:
    handler: app.handlers.publish
    events: [{http: POST /events}]
  receive:                        # target of an HTTP subscription on the topic
    handler: app.handlers.receive
    events: [{http: POST /hooks/order-events}]
```

## 4. Use it in a handler

`requirements.txt`: `tencentcloud-sdk-python-tdmq`

```python
import json

from tencentcloud.common import credential
from tencentcloud.tdmq.v20200217 import models, tdmq_client
from py_serverless_kit import resource


def publish(event, ctx):
    t = resource("order-events")
    client = tdmq_client.TdmqClient(
        credential.Credential(ctx.env[t["secret_id_env"]], ctx.env[t["secret_key_env"]]), t["region"]
    )
    req = models.PublishCmqMsgRequest()
    req.TopicName = t.native_name
    req.MsgContent = json.dumps(event.http.json())
    req.MsgTag = "paid"               # optional, matched by subscription filter tags
    client.PublishCmqMsg(req)
    return {"published": True}


def receive(event, ctx):
    ctx.logger.info("event", extra={"body": event.http.json(default=None)})
    return {"ok": True}
```

## 5. Test

```bash
pskit validate
pskit deploy
pskit info                         # the URL of `receive`, for the HTTP subscription
pskit resources send --list
```

Console: the topic → **Publish Message** (label depends on the console version).

## Troubleshooting

| Symptom | Fix |
|---|---|
| ``does not support `topic` events in pskit`` (validate) | expected: publish with the SDK and subscribe via the console |
| `AuthFailure` | wrong keys, or the sub-user lacks TDMQ permissions |
| HTTP subscription doesn't reach `receive` | check the URL from `pskit info` and the subscription's push settings |
