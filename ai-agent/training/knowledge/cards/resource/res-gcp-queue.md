# Pub/Sub as a queue (`type: queue`)

GCP has no SQS-style queue trigger, so a pskit `queue` on GCP is a **Pub/Sub topic** with a push trigger (Eventarc).
To use one you created in the console, you create a **topic**, not a subscription: Eventarc creates and manages the
push subscription that feeds the function.

## 1. Create the topic (console)

1. Console → **Pub/Sub** → **Topics** → **Create topic**.
2. Topic ID, for example `orders-jobs`. Leave *Add a default subscription* unticked (pskit's trigger brings its own;
   tick it only if another consumer needs one).
3. **Create**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic ID | Pub/Sub → **Topics** → *Topic ID* column | `orders-jobs` |
| Topic name (full path) | the topic → **Details** → *Topic name* | `projects/my-project/topics/orders-jobs` |
| Project ID | the project picker | `my-project` |

The topic must be in the project set in `provider.options.project`. No keys are needed: grant roles to the runtime
service account instead (step 3).

## 3. Declare it in `pskit.yml`

What pskit does with it: looks the topic up by name (`data "google_pubsub_topic"`), deploys `worker` with an Eventarc
Pub/Sub trigger on it (retry on failure), and grants its own invoker service account `roles/eventarc.eventReceiver`.

Grant the runtime service account the right to publish: **Pub/Sub → Topics** → tick the topic → **Permissions**
(info panel) → **Add principal** → the service account → role **Pub/Sub Publisher**.

Not applied on GCP (validation warnings): `batch_size`, `batch_window`, `dead_letter`, `max_receive`, `fifo`. Each
message is delivered on its own, and a failing message is retried by Pub/Sub. For a dead-letter topic, edit the
Eventarc-created subscription in the console (**Pub/Sub → Subscriptions → Edit → Dead lettering**); note that a
redeploy may recreate it.

## 4. Use it in a handler

`requirements.txt`: `google-cloud-pubsub`

The function receives:

## 5. Test

Console: the topic → **Messages** tab → **Publish message** → paste the body → **Publish**.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy: topic not found | wrong `name` (use the topic ID, not the full path), or the topic is in another project |
| Deploy: permission error creating the trigger | the deploying account needs Eventarc / IAM admin rights; enable the Eventarc and Pub/Sub APIs |
| Publish fails with `403 PERMISSION_DENIED` | grant **Pub/Sub Publisher** on the topic to the runtime service account |
| The same message is processed again and again | the handler raises; Pub/Sub retries until it succeeds or the message expires |

```text
service: orders

provider:
  name: gcp
  region: europe-west1
  options:
    project: my-project
    service_account: orders-runtime@my-project.iam.gserviceaccount.com   # optional, recommended

resources:
  jobs:                          # key used in code: resource("jobs")
    type: queue
    external: true               # created in the console; pskit never creates or deletes it
    name: orders-jobs            # the topic ID from step 2

functions:
  worker:                        # triggered by every message
    handler: app.handlers.work
    events:
      - queue: {resource: jobs}
  api:                           # publishes messages
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
```
