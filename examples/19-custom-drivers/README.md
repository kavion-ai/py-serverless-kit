# 19 · Custom on-premises drivers

When the queue or storage you already run has no built-in driver, write a small
class and point a resource at it. The on-prem host still does the rest: polling,
batching, `BatchResult` retries, dead-lettering, logs, stats and the dashboard.

| Resource | Class | Backed by |
| --- | --- | --- |
| `jobs` | `app.backends:SqliteQueue` | one SQLite file, table `jobs` |
| `jobs-dlq` | `app.backends:SqliteQueue` | the same file, table `jobs_dlq` |
| `inbox` | `app.backends:FolderStorage` | a folder (works for NFS / SMB shares) |

`app/rabbitmq_queue.py` (pika) and `app/kafka_queue.py` (kafka-python) are
templates for brokers that need a client library. Both deliver at least once.

## The contract

```yaml
resources:
  jobs:
    type: queue            # or storage
    external: true
    options:
      driver: custom
      class: app.backends:SqliteQueue   # "<module>:<Class>", importable from the app
      path: data/queues.sqlite3         # every other option -> constructor kwargs
      password_env: QUEUE_PASSWORD      # `<name>_env` -> read from the host's env as `password`
```

A **queue** class implements:

| Method | Called | Must |
| --- | --- | --- |
| `submit(body, attributes) -> id` | `submit_queue()`, `POST /__pskit/queues/<name>`, dead-lettering | store one message |
| `claim(batch, visibility, now) -> [msg]` | every poll | reserve up to `batch` messages for `visibility` seconds; each `msg` has `id`, `body`, `attributes`, `receives`, `enqueued_at` (+ private `_keys` you need later) |
| `settle(claimed, failed_ids, max_receive, dead_letter, now)` | after the handler | delete successes; make failures visible again; when `receives + 1 >= max_receive` and `dead_letter` is given, `dead_letter.submit(...)` then delete |
| `depth() -> int` | stats / dashboard | messages waiting, or `-1` if unknown |
| `recover(now, visibility)` | every few seconds | release reservations a crash left behind (no-op if the broker does it) |

A **storage** class implements `scan() -> {key: (etag, size)}`, `put(key, data)`,
`get(key) -> bytes` and `delete(key) -> bool`. The host diffs consecutive scans to
fire `created` / `deleted`, so `etag` must change whenever the content changes.

Rules of thumb:

- Never lose a message: delete only in `settle`, never in `claim`.
- Raise on connection errors. The host logs a warning and tries again on the next poll.
- `submit` may be called from HTTP threads at the same time as `claim`/`settle` on the poller, so guard shared clients.

## Try it

```bash
pskit validate
pskit deploy                       # starts the host on 127.0.0.1:8091
curl -X POST localhost:8091/jobs -H 'content-type: application/json' -d '{"task": "resize"}'
curl -X POST localhost:8091/jobs -H 'content-type: application/json' -d '{"task": "explode"}'   # retried 3x, then dead-lettered
echo hello > .pskit/onprem-dev/onprem_app/data/inbox/hello.txt                                    # fires on-file
pskit logs -f                      # job done / job failed / dead letter / file event
pskit dashboard --serve            # Logs tab + queue depths
```
