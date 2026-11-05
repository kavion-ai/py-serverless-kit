# Dead-letter queues and replay

A message that keeps failing should not be lost, and should not block or retry forever. With `dlq` on a function, it moves
to a dead-letter queue after a set number of retries. From there you can list it, read it and, once the bug is fixed, send
it back.

Dead-letter queues work on AWS, Azure, GCP and on premises. On other providers `dlq` is a validation error.

## Configure

```yaml
functions:
  worker:
    handler: app.jobs.worker
    dlq:
      queue: orders-dlq   # a name or a queue resource. Default: <function>-dlq
      max_retries: 3      # retries after the first delivery. Default: 4
    events:
      - queue: {name: orders}
```

Shorter forms: `dlq: true` (all defaults) and `dlq: orders-dlq`. `dlq: false` turns it off, for example in one stage.

`dlq` applies to the function's **queue triggers**; on a function without one it is a warning. A message is moved after
`max_retries + 1` failed deliveries. `dead_letter` or `max_receive` set on a queue event win over `dlq` for that event. On
GCP, `dead_letter` on an event without `dlq` on its function is not applied, and validation warns.

## What each provider does

| Provider | Where messages go | Retries | Good to know |
|---|---|---|---|
| **AWS** | The SQS queue you name, through a redrive policy | `maxReceiveCount` | An `existing: true` queue is not changed: set its redrive policy yourself (validation warns). Messages are kept for 14 days. |
| **Azure** | Always `<queue>-poison`, which Azure Functions moves them to | `maxDequeueCount` in `host.json` | A `queue` name can't be used (warning). A Function App has one limit for all its queues: if functions ask for different ones, the highest applies (warning). |
| **GCP** | The Pub/Sub topic you name, kept by the subscription `<dlq>-sub` for 7 days | `max_delivery_attempts` | `max_retries` must be 4 to 99. See below. |
| **On premises** | The queue you name, built-in or with a driver | Counted by the host | Also keeps the handler's error when the whole batch failed (`pskit_error`). |

### GCP: how delivery changes

An Eventarc trigger's subscription can't have a dead-letter policy. So a queue function with `dlq` gets its own Pub/Sub
**push subscription** instead of an Eventarc trigger, and its entry point becomes `pskit_http`. Handlers don't change.
Without `dlq` nothing changes. Adding `dlq` to a deployed function replaces its trigger, so plan it for a quiet moment.

The Pub/Sub service agent gets publish rights on the dead-letter topic and subscribe rights on the source subscription.
Projects created before April 2021 must also give that agent `roles/iam.serviceAccountTokenCreator` on the invoker service
account.

## Commands

```bash
pskit dlq list                       # every dead-letter queue and how many messages it holds
pskit dlq list worker                # the messages of worker's dead-letter queue
pskit dlq list worker --offset 20 -n 20
pskit dlq inspect worker MESSAGE_ID  # one message in full: body and attributes
pskit dlq replay worker MESSAGE_ID [MESSAGE_ID...]
pskit dlq replay worker --all        # asks first; -y skips the question
pskit dlq replay worker --all --to orders-retry
```

`worker` can be a function or the name of a dead-letter queue. If a function has several, name the queue. All of these take
`--json`, and the usual `-s`, `-p` and `-c`.

**Replay** sends each message back to the queue it came from, and its function runs it again. A message is deleted from the
dead-letter queue only after its queue has accepted the copy, so a crash may replay a message twice but never loses one.
Handlers should therefore tolerate a repeat. If it fails again, it returns to the dead-letter queue, with `pskit_replays`
in its attributes counting the replays. `replay` exits with 1 if any message could not be sent or was not found; those
stay where they are.

The source queue comes from what the message recorded (on premises, and SQS's `DeadLetterQueueSourceArn`), then from
`pskit.yml` if the dead-letter queue has one source. If a dead-letter queue has several sources and the message does not
say which, use `--to`.

**Reading is not free of side effects on the clouds.** Their queues can't be read without receiving, so `list` and `inspect`
hide the messages they read for up to 2 minutes and then give them back. It is harmless because nothing normally consumes a
dead-letter queue, but two people listing at once may each see part of it. Depths on AWS and Azure are approximate and on
GCP unknown (`?`).

**Permissions and credentials.** In a project with a vault, `list` and `inspect` need read on Resources, and `replay` needs
update. Messages can hold customer data. On the clouds the commands use the same credentials as `pskit resources send`: the
AWS credential chain with `boto3` installed, the deployment's storage connection string or
`AZURE_STORAGE_CONNECTION_STRING`, and `gcloud auth print-access-token` or `GOOGLE_OAUTH_ACCESS_TOKEN`.
