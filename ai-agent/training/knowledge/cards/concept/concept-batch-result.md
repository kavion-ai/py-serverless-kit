# Concept: BatchResult

Return a `BatchResult` from a queue, topic, or storage handler to name the records that failed. Create one, loop `event.records`, and call `result.fail(record)` or `result.fail(record.id)` inside the except block. `BatchResult.of(failed_records)` is the other constructor in the doc. Returning the object reports those ids. Records you do not fail are treated as done.

```python
from py_serverless_kit import BatchResult

def worker(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            process(record.json())
        except Exception:
            result.fail(record)
    return result
```

On AWS SQS the result becomes `batchItemFailures`, so only the failed messages are retried. On premises the host retries only the failed message ids and moves a message to `dead_letter` after `max_receive`. Locally the result is printed as `batchItemFailures`. On every other provider any failure raises `BatchFailure`, so the whole delivery is retried. The queue event table says the same for GCP and Azure: the whole delivery is retried.

The doc says to write idempotent handlers, because redelivery is normal on every cloud. A handler that raises instead of returning `BatchResult` fails the delivery the platform's usual way.

Sources: `docs/handlers.md#batchresult`, `docs/events.md#queue`
