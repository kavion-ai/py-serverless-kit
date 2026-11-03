# On-premises topics (`type: topic`)

A topic fans each message out to every function subscribed to it. On premises topics are **built in** (directories
under `data_dir`) or a **shared directory**. There are no drivers for external brokers.

## Built-in topic

```yaml
resources:
  order-events:
    type: topic                       # created when the host starts

functions:
  billing:
    handler: app.handlers.billing
    events:
      - topic: {resource: order-events, filter: {type: [paid]}}   # exact match on attributes, then JSON body fields
  audit:
    handler: app.handlers.audit
    events:
      - topic: {resource: order-events}
```

A shared directory (several hosts on one NFS share, for example):

```yaml
resources:
  order-events:
    type: topic
    external: true
    options: {driver: directory, path: /mnt/shared/topics}
```

With `external: true` the host doesn't create the directory; it waits until it appears.

## Use it in a handler

```python
from py_serverless_kit import resource
from py_serverless_kit.runtime.onprem_host import submit_topic


def api(event, ctx):
    order = event.http.json()
    submit_topic(resource("order-events").native_name, order, {"type": "paid"})
    return {"published": True}


def billing(event, ctx):
    for record in event.records:
        ctx.logger.info("paid", extra={"body": record.body, "attributes": record.attributes})
```

## Kafka, RabbitMQ exchanges, NATS, MQTT, cloud topics

Not available as topic drivers. Options:

- consume a broker subscription as a **queue** with a [custom queue driver](queue.md#rabbitmq-or-kafka-nats--via-a-custom-driver)
  (one consumer group / queue per function),
- consume a cloud topic through a queue it delivers to: an SQS queue subscribed to SNS, a Pub/Sub pull subscription
  (`pubsub` driver), an Azure Storage queue,
- publish to an external broker from a handler with its client library, describing it as a `custom` resource.

## Test

```bash
pskit validate
pskit deploy
pskit resources send order-events -d '{"message": {"id": 1}, "attributes": {"type": "paid"}}'
curl -X POST -d '{"message": {"id": 2}, "attributes": {"type": "paid"}}' http://127.0.0.1:8080/__pskit/topics/order-events
pskit logs -f
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `on-premises topic driver must be one of builtin, directory` | topics have no other drivers; see above |
| A function doesn't receive a message | its `filter` doesn't match the attributes / body fields exactly |
