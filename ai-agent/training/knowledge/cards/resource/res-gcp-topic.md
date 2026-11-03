# Pub/Sub topic (`type: topic`)

Use a Pub/Sub topic you created in the console: every subscribed function gets every message (fan-out), and handlers
can publish to it. On GCP `queue` and `topic` are both Pub/Sub topics; use `topic` when several functions should
receive the same message.

## 1. Create the topic (console)

1. Console → **Pub/Sub** → **Topics** → **Create topic**.
2. Topic ID, for example `order-events` → **Create**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic ID | Pub/Sub → **Topics** | `order-events` |
| Topic name (full path) | the topic → **Details** | `projects/my-project/topics/order-events` |

## 3. Declare it in `pskit.yml`

What pskit does with it: looks the topic up by name, and deploys `notify` and `audit` each with its own Eventarc
trigger (each gets its own push subscription, so both receive every message). `pskit remove` deletes the triggers,
never the topic.

`filter` is **not applied** on GCP (warning): filter on `record.attributes` in the handler.

Grant the runtime service account **Pub/Sub Publisher** on the topic for `publisher` (the topic → **Permissions** →
**Add principal**).

## 4. Use it in a handler

`requirements.txt`: `google-cloud-pubsub`

Keyword arguments to `publish()` become message attributes.

## 5. Test

Console: the topic → **Messages** → **Publish message** → body and an attribute `type` = `paid` → **Publish**. The
topic's **Subscriptions** tab lists the Eventarc subscriptions.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy: topic not found | use the topic ID, in `provider.options.project` |
| Function gets messages it should ignore | filters aren't applied on GCP; check `record.attributes` |
| Publish `403` | grant **Pub/Sub Publisher** to the runtime service account |

```text
provider:
  name: gcp
  region: europe-west1
  options:
    project: my-project
    service_account: orders-runtime@my-project.iam.gserviceaccount.com

resources:
  order-events:
    type: topic
    external: true
    name: order-events

functions:
  notify:
    handler: app.handlers.notify
    events:
      - topic: {resource: order-events}
  audit:
    handler: app.handlers.audit
    events:
      - topic: {resource: order-events}
  publisher:
    handler: app.handlers.publish
    events: [{http: POST /orders}]
```
