# Amazon SNS topic (`type: topic`)

Use an SNS topic you created in the console: subscribe functions to it (with an optional filter policy), publish to it
from a handler, or both.

## 1. Create the topic (console)

1. Console → **Simple Notification Service** → **Topics** → **Create topic**.
2. Type: *Standard* (Lambda subscriptions need a Standard topic). Name, for example `order-events`.
3. **Create topic**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic name | SNS → **Topics** | `order-events` |
| Topic ARN | the topic → **Details** → *ARN* | `arn:aws:sns:eu-west-1:123456789012:order-events` |
| Encryption | the topic → **Encryption** | none, or a KMS key ARN |

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: aws
  region: eu-west-1

resources:
  order-events:
    type: topic
    external: true
    name: order-events

functions:
  notify:
    handler: app.handlers.notify
    events:
      - topic: {resource: order-events, filter: {type: [paid]}}
  publisher:
    handler: app.handlers.publish
    events: [{http: POST /orders}]
```

What pskit does with it: looks the topic up by name (`data "aws_sns_topic"`), creates a Lambda subscription for
`notify` with the filter policy, allows SNS to invoke it, adds `sns:Publish` on the topic to the IAM role of bound functions,
and sets `PSKIT_RESOURCE_ORDER_EVENTS_ARN`. `pskit remove` deletes the subscription, never the topic.

Topic encrypted with a customer-managed KMS key: add `kms:GenerateDataKey` and `kms:Decrypt` on the key under
`provider.iam.statements` for publishers.

## 4. Use it in a handler

```python
import json

import boto3
from py_serverless_kit import resource

sns = boto3.client("sns")


def publish(event, ctx):
    topic = resource("order-events")
    sns.publish(
        TopicArn=topic.arn,
        Message=json.dumps(event.http.json()),
        MessageAttributes={"type": {"DataType": "String", "StringValue": "paid"}},
    )
    return {"published": True}


def notify(event, ctx):
    for record in event.records:
        ctx.logger.info("event", extra={"body": record.body, "attributes": record.attributes})
```

The filter policy matches **message attributes**, so publish with `MessageAttributes` as above.

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send order-events -d '{"message": {"id": 1}, "attributes": {"type": "paid"}}'
pskit logs -f --function notify
```

Console: the topic → **Publish message** → body and a *Message attribute* `type` = `paid` → **Publish message**. The
topic's **Subscriptions** tab shows the pskit Lambda subscription.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy: `no matching SNS Topic found` | wrong `name`, or another region/account |
| `notify` never runs | the filter policy doesn't match: check the attribute names/values you publish |
| Publish `AuthorizationError` | own `iam.role`, KMS key permissions, or a topic access policy that denies the role |
