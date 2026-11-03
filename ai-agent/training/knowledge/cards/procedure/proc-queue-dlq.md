## In studio
1. Open this path:
Resources > + Add resource

2. Open this path:
Functions > + Create function

## In the terminal
1. Run:

```
pskit invoke -f worker -t queue -d '{"order_id": 1}'
```

2. Run:

```
pskit resources send jobs -d '{"order_id": 1}'
```

## In code

On AWS, dead_letter and max_receive apply when pskit creates the queue. Return a BatchResult to retry only failed records. On premises the file broker implements the same options.

## `queue` The handler gets `event.type == "queue"` and `event.records`, one `Record` per

message. Return a `BatchResult` to retry only failed messages. | Option | aws (SQS) | gcp (Pub/Sub topic) | azure (Storage Queue) | |---|---|---|---| | `batch_size`, `batch_window` | ✓ | ignored | ignored | | `dead_letter`, `max_receive` | ✓ redrive policy | ignored (warning) | ignored: poison messages go to `<queue>-poison` | | `fifo` | ✓ (`.fifo`

## `BatchResult`

Return a `BatchResult` from queue/topic/storage handlers to report the records that failed: | Provider | Behaviour | |---|---| | aws (SQS) | becomes `batchItemFailures`, so only the failed messages are retried | | onprem | the host retries only the failed message ids, and moves a message to `dead_letter` after `max_receive` | | local | printed as `batchItemFailures` | | everyone else | any failure raises `BatchFailure`, so
