# Resource: topic

A topic resource fans one message out to every subscribed function. Use it for "order paid" style events: the publisher does not name the workers, and each subscriber gets a copy.

The guide index names the native service: Amazon SNS, an Azure Service Bus topic, a Pub/Sub topic, Alibaba SMQ / MNS, Tencent TDMQ for CMQ, Huawei SMN, OCI Notifications, IBM Event Streams, DigitalOcean Managed Kafka, and an on-premises file topic. The Cloudflare topic guide is the page of alternatives, because the events table leaves topic unmarked on Cloudflare.

`type: topic` may be managed. AWS, GCP, Azure, and on premises can keep a standalone managed topic. On the other clouds, a managed topic is valid where a topic event uses it. Elsewhere set `external: true`. Azure app settings belong to the whole Function App, so every function in that app sees every binding.

Declare `type: topic` under `resources`. A topic event can say `resource: order-events` and, where the provider applies it, `filter`. The events table marks topic on AWS SNS (filter policy), GCP Pub/Sub (filter left to the handler, with a warning), Azure Service Bus (filter left to the handler; an existing topic needs `options.servicebus_namespace_id` and `options.servicebus_connection`), Alibaba MNS (`filter.tag` as a string), Huawei SMN, and on-premises files (exact match on attributes, then on JSON body fields).

`resource("order-events").arn` is the publish target on AWS. The library table lists `boto3` or `@aws-sdk/client-sns` on AWS, `google-cloud-pubsub` on GCP, and `azure-servicebus` or `@azure/service-bus` on Azure. On premises, `submit_topic` publishes through the host. Topics there support the `builtin` and `directory` drivers. AWS adds `ARN` for a topic. GCP adds `ID` for a managed topic. The function also receives `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL`, and connection keys.

Open:

Resources > + Add resource

Resources > How to use

Resources > Test

```
pskit resources send order-events -d '{"message": {"id": 1}}'
pskit logs -f --function notify
pskit resources usage order-events -p aws -s dev
```

On AWS, each role pskit creates gets `sns:Publish` for the topics bound to its functions. A role set with `iam.role` is left unchanged, and the plan warns.

Sources: `docs/events.md#topic`, `docs/resources.md#provider-support`, `docs/resources.md#aws-iam`, `docs/resource-usage.md#queues-buckets-and-topics`
