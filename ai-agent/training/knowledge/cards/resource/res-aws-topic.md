# Resource: AWS SNS topic

On AWS, `type: topic` is an Amazon SNS topic. Use it to publish one event and run every subscribed function. AWS can also create a managed topic. The guide is the path for a topic that already exists.

Create a Standard topic. The guide says Lambda subscriptions need a Standard topic. Collect the topic name and the topic ARN. Declare `type: topic`, `external: true`, and `name`. A subscriber event can set `resource` and `filter`, for example `filter: {type: [paid]}`. pskit looks the topic up with `data.aws_sns_topic`, creates a Lambda subscription with that filter policy, allows SNS to invoke the function, adds `sns:Publish` on the topic to the role of bound functions, and sets `PSKIT_RESOURCE_<KEY>_ARN`. `pskit remove` deletes the subscription and leaves the topic.

The filter policy matches message attributes. Publish with `boto3` and `TopicArn=resource("order-events").arn`, and set `MessageAttributes` so the filter can match. Node.js uses `@aws-sdk/client-sns`. The subscriber reads `event.records`, including `record.body` and `record.attributes`. A customer-managed KMS key needs `kms:GenerateDataKey` and `kms:Decrypt` on that key for publishers.

Open:

Resources > + Add resource

Resources > Browse account

```
pskit validate
pskit resources send order-events -d '{"message": {"id": 1}, "attributes": {"type": "paid"}}'
pskit logs -f --function notify
```

The console path is the topic, Publish message, a message attribute `type` = `paid`, then Publish message. The Subscriptions tab lists the Lambda subscription pskit added.

Sources: `docs/resource-guides/aws/topic.md#amazon-sns-topic-type-topic`, `docs/events.md#topic`, `docs/resources.md#aws-iam`
