# OCI Notifications topic (`type: topic`)

pskit has **no topic trigger on OCI**: a `topic` event is a validation error. Bind the topic to functions and publish
with the OCI SDK. For a durable, Kafka-compatible stream, see Streaming.

## 1. Create the topic (console)

1. Console → **Developer Services → Application Integration → Notifications** → pick the compartment →
   **Create Topic**.
2. Name (for example `order-events`) → **Create**. Add subscriptions (email, HTTPS, Slack, ...) on the topic page.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic OCID | topic details → *OCID* | `ocid1.onstopic.oc1.iad.aaaa` |
| Name | topic details | `order-events` |

## 5. Use it in a handler

`requirements.txt`: `oci`

## 6. Test

Console: topic → **Publish Message** to check the subscriptions receive it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` Oracle Cloud Functions does not support `topic` events in pskit `` | no topic triggers on OCI; remove the `topic` event |
| `NotAuthorizedOrNotFound` | dynamic group / `use ons-topics` policy missing |
| Subscribers get nothing | subscriptions stay *Pending* until confirmed (email, HTTPS) |

```
Allow dynamic-group pskit-functions to use ons-topics in compartment <name>
```
