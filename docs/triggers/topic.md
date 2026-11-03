# Topic trigger

Search terms: topic, pub/sub, publish subscribe, fan-out, SNS, Service Bus, Pub/Sub, MNS, SMN, subscription, filter policy, message attributes, event bus, notifications

The pskit `topic` trigger subscribes a function to a publish/subscribe topic: every message published to the topic
runs every subscribed function (fan-out). On AWS it is SNS, on Azure a Service Bus topic, on GCP Pub/Sub, on Alibaba
MNS, on Huawei SMN, and on premises a file topic.

## Write a topic trigger in pskit.yml

The pskit `topic` trigger needs `name` or `resource`.

```yaml
events:
  - topic: order-events                # shorthand: the topic name
  - topic:
      name: order-events
      existing: false                  # true: the topic already exists
      filter: {type: [created]}        # deliver only matching messages (AWS SNS filter policy)
  - topic: {resource: events}          # a resources: entry of type topic
```

| Key | Default | Meaning |
|---|---|---|
| `name` | | native topic name |
| `resource` | | key of a `resources:` entry of type `topic` |
| `existing` | `false` | `true`: attach to an existing topic, never create or delete it |
| `filter` | | attribute filter; support differs per cloud (below) |

## Read topic messages in the handler

For a `topic` trigger `event.type == "topic"` and `event.records` holds one `Record` per published message.

```python
from py_serverless_kit import Context, Event


def on_order_event(event: Event, ctx: Context):
    for record in event.records:
        message = record.json(default={})          # the published message
        kind = record.attributes.get("type")       # message attributes
        ctx.logger.info("order event", extra={"id": record.id, "type": kind, "order": message.get("id")})
```

| `Record` field | Meaning |
|---|---|
| `id` | message id |
| `body`, `text()`, `json(default=...)` | the published message |
| `attributes` | message attributes (SNS `MessageAttributes` values on AWS) |
| `source` | topic identifier (the topic ARN on AWS) |

`event.source` is the topic and, on AWS, `event.time` is the publish time. A raised exception makes the cloud retry
the delivery. `BatchResult` works as for queues ([queue.md](queue.md#retry-only-the-failed-messages-with-batchresult)).

## Add a topic trigger in studio

1. Sidebar **Functions** → open the function → **2 Triggers** → card **Topic** (default name `<function>-events`).
2. **Source**: **Create new topic** (**Topic name**, optionally **Create & select**), **Project resource (N)**,
   **Pick from <provider>** (AWS, GCP with `google-cloud-pubsub`, on premises; others ask you to type the name) or
   **Type a name** (existing topic).
3. **filter**: a mapping such as `{"type": ["created"]}`.
4. The **On <provider>:** box shows whether the provider applies `filter` and what `existing` needs there.
5. **Apply changes**, then **Save**.

## Topics per provider

The pskit topic trigger and its `filter` per cloud:

| Provider | Native | `filter` | `existing` |
|---|---|---|---|
| aws | SNS subscription | SNS filter policy | data source lookup by name |
| azure | Service Bus topic + subscription | not applied, warning | needs `provider.options.servicebus_namespace_id` and `provider.options.servicebus_connection` (an app setting name) |
| gcp | Pub/Sub `messagePublished` | not applied, warning at package time | yes |
| alibaba | MNS topic | only `filter.tag` (a string) | yes |
| huawei | SMN topic | not applied | yes |
| onprem | file topic in the host, fan-out | exact match on message attributes, then on JSON body fields | waits for the directory |
| tencent, oracle, ibm, digitalocean, cloudflare | not supported | | |

On premises a `filter` value may be one value or a list of allowed values: `{type: [created, updated]}` matches when
the attribute (or top-level body field) `type` equals one of them. Topic resources on premises use the `builtin`
or `directory` driver ([../onprem/resources.md](../onprem/resources.md)). Where the filter is not applied, check the
attributes in the handler.

## Topic or queue

Use a pskit topic when several functions must each get every message (fan-out). Use a queue when one worker pool
shares the messages and failed ones should be retried and dead-lettered ([queue.md](queue.md)). On GCP both are
Pub/Sub topics.

## Attach to a new or an existing topic

A pskit topic trigger either creates the topic or attaches to one that exists.

| You want | YAML |
|---|---|
| pskit creates the topic | `- topic: order-events` |
| an existing topic | `- topic: {name: legacy-events, existing: true}` |
| a topic other functions publish to | `resources: {events: {type: topic}}` and `- topic: {resource: events}` |
| an existing topic as a resource | `resources: {events: {type: topic, external: true, name: legacy-events}}` |

## Test a topic trigger

- Locally: `pskit invoke -f on-order-event -t topic -d '[{"type": "created", "id": 1}]'` (a list gives one record
  each; local records have no attributes).
- Studio: **Test** → the function → the `topic <name>` card → **Payload (JSON)**
  `{"message": {...}, "attributes": {...}}` → **▶ Run locally**, or **☁ Send to <provider> / <stage>** (delivered to
  every subscriber).
- Deployed: `pskit trigger -f on-order-event -e 0 -d '{"message": {"id": 1}, "attributes": {"type": "created"}}'`
  publishes on AWS, GCP, Azure and on premises. For a resource:
  `pskit resources send events -d '{"message": {"id": 1}, "attributes": {"type": "order"}}'`.
- Watch: `pskit logs -f --function on-order-event`.

## Common topic trigger errors

| Message or symptom | Fix |
|---|---|
| `topic event needs 'name' or 'resource'` | set one |
| `existing topics need options.servicebus_namespace_id and options.servicebus_connection` (Azure) | set both provider options |
| `topic.filter is not applied on Azure Service Bus subscriptions` | filter in the handler |
| `<Provider> does not support 'topic' events in pskit` | use a provider from the table |
| the handler gets messages it should skip | the cloud does not apply `filter`: check attributes in code |

## See also

- [README.md](README.md)
- [queue.md](queue.md)
- [../resources.md](../resources.md)
- [../onprem/resources.md](../onprem/resources.md)
- [../functions/invoke-and-test.md](../functions/invoke-and-test.md)
- [../events.md](../events.md)
