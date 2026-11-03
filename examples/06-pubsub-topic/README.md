# 06 · Pub/Sub topic fan-out

One topic with two subscribers: every message goes to both. One subscriber uses a filter
policy so it only receives `order.shipped` events.

## The YAML

```yaml
update-analytics:
  events:
    - topic: order-events
notify-customer:
  events:
    - topic:
        name: order-events
        filter: {event_type: ["order.shipped"]}
```

| Cloud | Topic | Subscription | `filter` |
| --- | --- | --- | --- |
| AWS | SNS topic | Lambda subscription per function | SNS filter policy (native) |
| GCP | Pub/Sub topic | Eventarc trigger per function | not configured, so the handler filters |
| Azure | Service Bus topic | one subscription per function | warning, so the handler filters |

Because filters are not available everywhere, `notify_customer` repeats the check in code
(`_wants`). Doing that in your own handlers keeps them correct on every cloud.

Use `existing: true` to subscribe to a topic owned by another service. On Azure that also
needs `options.servicebus_namespace_id` and `options.servicebus_connection`.

## Run locally

```bash
pskit invoke -f update-analytics -d '[{"order_id": 1}, {"order_id": 2}]'
```

Local events have no attributes, so the counts come out as `unknown`:

```json
{"counts": {"unknown": 2}}
```

Use the dev server's internal endpoint the same way:
`curl -X POST "localhost:3000/__pskit/invoke/update-analytics?type=topic" -d '{"order_id": 1}'`.

To test the filter, write a unit test that builds `Record(attributes={"event_type": "order.shipped"}, ...)`
(see example 14).

## Deploy

```bash
pskit deploy
pskit deploy --provider gcp
pskit deploy --provider azure
```

Publish a test message on AWS:

```bash
aws sns publish --topic-arn <arn from pskit info> --message '{"order_id": 9, "email": "a@b.c"}' \
  --message-attributes '{"event_type": {"DataType": "String", "StringValue": "order.shipped"}}'
```
