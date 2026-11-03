# Concept: topic events

`- topic: order-events` is shorthand. The long form sets `name`, `existing` (default false), and `filter`. The example filter is `{type: ["created"]}`, described as an AWS SNS filter policy.

AWS applies the filter policy on the SNS subscription. GCP Pub/Sub does not apply `filter` and warns. Filter in the handler. Azure Service Bus uses a topic plus a subscription. `filter` is not applied and warns. `existing` needs `options.servicebus_namespace_id` and `options.servicebus_connection`. Alibaba MNS accepts `filter.tag` as a string only. Huawei SMN is listed with no filter mark. On premises the topic is a file topic with fan-out. The filter is an exact match on attributes, then on JSON body fields.

The events support table marks topic on AWS, GCP, Azure, Alibaba, Huawei, and on premises. Oracle, IBM, DigitalOcean, Tencent, and Cloudflare are unmarked. `pskit validate` reports a trigger the selected provider cannot honour.

A topic event can name a resource instead of a topic name. The event uses that resource's native name, and `existing` follows whether the resource is external. The function also receives the resource's connection details.

Sources: `docs/events.md#topic`, `docs/events.md#events-triggers`, `docs/events.md#events-backed-by-a-resource`

```text
- topic: order-events                  # shorthand
- topic:
    name: order-events
    existing: false
    filter: {type: ["created"]}        # AWS SNS filter policy
```
