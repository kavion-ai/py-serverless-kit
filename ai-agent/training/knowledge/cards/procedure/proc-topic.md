## In studio
1. Open this path:
Resources > + Add resource

2. Open this path:
Functions > + Create function

## In the terminal
1. Run:

```
pskit resources send order-events -d '{"message": {"id": 1}}'
```

## In code

A topic event can name a resource. AWS applies a filter policy to message attributes. Other clouds document whether filter is applied.

## `topic` | Provider | Service | `filter` | |---|---|---| | aws | SNS

subscription | ✓ filter policy | | gcp | Pub/Sub | not applied (warning) – filter in the handler | | azure | Service Bus topic + subscription | not applied (warning); `existing` needs `options.servicebus_namespace_id` and `options.servicebus_connection` | | alibaba | MNS topic | `filter.tag` (string) only | | huawei | SMN topic | – |

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
