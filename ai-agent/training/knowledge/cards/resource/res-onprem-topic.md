# On-premises topics (`type: topic`)

A topic fans each message out to every function subscribed to it. On premises topics are **built in** (directories
under `data_dir`) or a **shared directory**. There are no drivers for external brokers.

## Built-in topic

A shared directory (several hosts on one NFS share, for example):

With `external: true` the host doesn't create the directory; it waits until it appears.

## Kafka, RabbitMQ exchanges, NATS, MQTT, cloud topics

Not available as topic drivers. Options:

- consume a broker subscription as a **queue** with a custom queue driver
  (one consumer group / queue per function),
- consume a cloud topic through a queue it delivers to: an SQS queue subscribed to SNS, a Pub/Sub pull subscription
  (`pubsub` driver), an Azure Storage queue,
- publish to an external broker from a handler with its client library, describing it as a `custom` resource.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `on-premises topic driver must be one of builtin, directory` | topics have no other drivers; see above |
| A function doesn't receive a message | its `filter` doesn't match the attributes / body fields exactly |

```text
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
