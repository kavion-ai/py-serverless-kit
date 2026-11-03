# Huawei SMN topic (`type: topic`)

Use a Simple Message Notification (SMN) topic you created in the console: pskit adds a FunctionGraph SMN trigger so
every published message runs the function, and handlers can publish to it.

## 1. Create the topic (console)

1. Console → **Simple Message Notification** → **Topic Management → Topics** → **Create Topic**.
2. Topic name (letters, digits, `-`, `_`; for example `order-events`), optional display name → **OK**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic name | SMN → **Topics** → *Topic Name* | `order-events` |
| Topic URN | SMN → **Topics** → *Topic URN* column | `urn:smn:cn-north-4:0a1b2c...:order-events` |
| Region | console header | `cn-north-4` |
| Project ID | **My Credentials → API Credentials** | `0a1b2c...` |

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: huawei
  region: cn-north-4
  iam:
    role: pskit-functions             # agency with SMN permissions, needed to publish

resources:
  order-events:
    type: topic
    external: true
    name: order-events
    connection:
      urn: urn:smn:cn-north-4:0a1b2c3d4e5f:order-events
      project_id: 0a1b2c3d4e5f

functions:
  notify:
    handler: app.handlers.notify
    events:
      - topic: {resource: order-events}
```

- For an external topic pskit looks it up by name (`huaweicloud_smn_topics` data source) and adds the trigger. The
  topic must be in `provider.region`.
- `topic.filter` is not supported on Huawei.

## 4. Use it in a handler

`requirements.txt`: `huaweicloudsdksmn`

```python
import json

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdksmn.v2 import PublishMessageRequest, PublishMessageRequestBody, SmnClient
from huaweicloudsdksmn.v2.region.smn_region import SmnRegion
from py_serverless_kit import resource


def publish(event, ctx):
    topic = resource("order-events")
    creds = BasicCredentials(
        ctx.raw.getSecurityAccessKey(), ctx.raw.getSecuritySecretKey(), topic["project_id"]
    ).with_security_token(ctx.raw.getSecurityToken())
    client = SmnClient.new_builder().with_credentials(creds).with_region(SmnRegion.value_of(ctx.region)).build()
    body = PublishMessageRequestBody(subject="order", message=json.dumps({"id": 1}))
    client.publish_message(PublishMessageRequest(topic_urn=topic["urn"], body=body))


def notify(event, ctx):
    for record in event.records:
        ctx.logger.info("event", extra={"body": record.body, "attributes": record.attributes})
```

## 5. Test

```bash
pskit validate
pskit invoke -f notify -d '{"id": 1}'     # locally
pskit deploy
pskit logs -f --function notify
```

Console: SMN → **Topics** → topic → **Publish Message**. FunctionGraph → `notify` → **Triggers** lists the SMN trigger.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails: topic not found | name or region differs; SMN topic names are case-sensitive |
| Publishing returns 403 | the agency lacks SMN permissions |
