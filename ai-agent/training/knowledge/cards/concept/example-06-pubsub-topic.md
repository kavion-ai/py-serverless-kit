# Example: 06-pubsub-topic

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: 

# 06 · Pub/Sub topic fan-out One topic with two subscribers: every message goes to both.

One subscriber uses a filter
policy so it only receives `order.shipped` events.

## The YAML

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

Local events have no attributes, so the counts come out as `unknown`:

Use the dev server's internal endpoint the same way:
`curl -X POST "localhost:3000/__pskit/invoke/update-analytics?type=topic" -d '{"order_id": 1}'`.

To test the filter, write a unit test that builds `Record(attributes={"event_type": "order.shipped"}, ...)`
(see example 14).

## Deploy

Publish a test message on AWS:
