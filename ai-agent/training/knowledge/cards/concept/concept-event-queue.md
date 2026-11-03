# Concept: queue events

`- queue: jobs` is shorthand. The long form sets `name`, `existing` (default false: pskit creates the queue), `batch_size` (1–10000, example 10), `batch_window` (0–300 seconds), `visibility_timeout` (the doc says the AWS default is max(30, 6 times the function timeout)), `dead_letter`, `max_receive`, and `fifo`.

The handler gets `event.type == "queue"` and `event.records`, one `Record` per message. Return a `BatchResult` to retry only the failed messages where the provider supports that.

On AWS SQS, batch size, batch window, dead-letter, max receive, and fifo are used. Fifo adds a `.fifo` suffix and content-based deduplication. Partial failure uses `batchItemFailures`. On GCP the queue is a Pub/Sub topic with a push trigger, because GCP has no SQS-style pull trigger. Batch size, batch window, dead-letter, and fifo are ignored. A dead-letter or fifo setting warns. The whole delivery is retried. On Azure Storage Queue those options are ignored. Poison messages go to `<queue>-poison`. Azure queue names must be 3–63 lowercase letters, digits, and dashes. The whole delivery is retried.

On premises a file broker implements batch size, batch window, visibility, dead-letter, max receive, and fifo. `BatchResult` retries only the failed ids, as on AWS. `provider.options.services.queue` is `builtin` or `{use: directory, path: ...}`. `existing: true` waits for that directory.

An event can point at a resource: `- queue: {resource: jobs, batch_size: 5}`. The event uses the resource's native name and `existing` follows `external`.

Sources: `docs/events.md#queue`, `docs/events.md#events-backed-by-a-resource`

```text
- queue: jobs                          # shorthand
- queue:
    name: jobs
    existing: false                    # true = use an existing queue, don't create it
    batch_size: 10                     # 1-10000
    batch_window: 0                    # seconds to wait to fill a batch (0-300)
    visibility_timeout: 120            # default (AWS): max(30, 6 x function timeout)
    dead_letter: jobs-dlq              # queue that receives messages after max_receive attempts
    max_receive: 5
    fifo: false
```
