# Alibaba Cloud SMQ / MNS topic (`type: topic`)

Use a Simple Message Queue (SMQ, formerly MNS) topic you created in the console: pskit adds an MNS topic trigger to the
function, and handlers can publish to the topic.

## 1. Create the topic (console)

1. Console → **Simple Message Queue (formerly MNS)** → pick the **same region** as `provider.region` → **Topics** →
   **Create Topic**.
2. Name (for example `order-events`) → **OK**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic name | SMQ → **Topics** | `order-events` |
| Endpoint | SMQ → **Topics** → **Get Endpoint**, or the topic's details page | `https://1234567890.mns.cn-hangzhou.aliyuncs.com` |
| AccessKey (to publish) | RAM user with `AliyunMNSFullAccess` (or a custom policy on this topic) | `LTAI...` |

```bash
export MNS_ACCESS_KEY_ID=LTAI...
export MNS_ACCESS_KEY_SECRET=...
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: alibaba
  region: cn-hangzhou
  environment:
    MNS_ACCESS_KEY_ID: ${env:MNS_ACCESS_KEY_ID}
    MNS_ACCESS_KEY_SECRET: ${env:MNS_ACCESS_KEY_SECRET}

resources:
  order-events:
    type: topic
    external: true
    name: order-events
    connection:
      endpoint: https://1234567890.mns.cn-hangzhou.aliyuncs.com
      access_key_env: MNS_ACCESS_KEY_ID
      secret_key_env: MNS_ACCESS_KEY_SECRET

functions:
  notify:
    handler: app.handlers.notify
    events:
      - topic: {resource: order-events, filter: {tag: paid}}   # optional: only messages tagged "paid"
  publish:
    handler: app.handlers.publish
    events: [{http: POST /events}]
```

- `topic: {resource: order-events}` adds an `mns_topic` trigger on the existing topic (JSON notify format,
  `BACKOFF_RETRY`). No `alicloud_message_service_topic` is created.
- `filter` supports a single string `tag` only.
- The trigger is created for `provider.region`; the topic must be there.

## 4. Use it in a handler

`requirements.txt`: `aliyun-mns-sdk`

```python
import json

from mns.account import Account
from mns.topic import TopicMessage
from py_serverless_kit import resource


def publish(event, ctx):
    t = resource("order-events")
    topic = Account(t["endpoint"], ctx.env[t["access_key_env"]], ctx.env[t["secret_key_env"]]).get_topic(t.native_name)
    topic.publish_message(TopicMessage(json.dumps(event.http.json()), "paid"))   # body, tag
    return {"published": True}


def notify(event, ctx):
    for record in event.records:
        ctx.logger.info("event", extra={"body": record.body, "attributes": record.attributes})
```

`record.body` is the message, `record.attributes` holds the other notification fields (`TopicName`, `MessageId`,
`PublishTime`, ...).

## 5. Test

```bash
pskit validate
pskit invoke -f notify -t topic -d '{"id": 1}'     # locally
pskit deploy
pskit trigger --list          # console steps for the MNS trigger
pskit logs -f --function notify
```

Console: SMQ → **Topics** → `order-events` → **Publish Message** (set the tag if you used `filter.tag`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails creating the trigger, topic not found | the topic is in another region, or the name differs |
| Messages published but `notify` never runs | the message tag doesn't match `filter.tag` |
| Publishing fails with `AccessDenied` | the RAM user lacks MNS permissions |
