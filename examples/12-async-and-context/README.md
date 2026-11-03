# 12 · Async handlers and the invocation context

## Async

Any handler can be `async def`. The runtime awaits it, so you can use `asyncio.gather`,
`httpx.AsyncClient`, `asyncpg` and similar libraries directly. The handler signature is
`handler(event, ctx)` or just `handler(event)`.

## Context

| Attribute | Meaning |
| --- | --- |
| `ctx.request_id` | platform request id (Lambda request id, Azure invocation id, ...) |
| `ctx.function` / `ctx.service` / `ctx.stage` / `ctx.region` / `ctx.provider` | where you are |
| `ctx.memory_mb` | configured memory, when the platform reports it |
| `ctx.remaining_time_ms()` | ms until the platform kills the invocation; `None` if unknown |
| `ctx.logger` | structured logger bound to function / request id / provider |
| `ctx.env` | `os.environ` |
| `ctx.raw` | the native context object, as an escape hatch |

`event.to_dict()` gives a compact, JSON-safe summary of any event, which is ideal for logs.

## Logging

```python
ctx.logger.info("aggregated", extra={"sources": 3, "elapsed_ms": 81})
```

In the cloud this produces one JSON line:

```json
{"ts": "2026-10-15T10:00:00+00:00", "level": "INFO", "logger": "pskit.function", "message": "aggregated",
 "function": "aggregate", "request_id": "c0ffee...", "provider": "aws", "sources": 3, "elapsed_ms": 81}
```

Locally the CLI switches to readable text (`PSKIT_LOG_FORMAT=text`). Control the level with
`LOG_LEVEL`.

## Run locally

```bash
pskit invoke -f aggregate
pskit invoke -f inspect -d '{"x": 1}' -H "X-Trace: abc"
pskit invoke -f batch-job
```

Expected (abridged):

```json
{"results": [{"source": "inventory", "latency_ms": 50}, {"source": "pricing", "latency_ms": 80},
             {"source": "reviews", "latency_ms": 30}], "elapsed_ms": 81}
```

Locally `remaining_time_ms()` is `null`. On AWS, Azure and the others it counts down
from the configured timeout.

## Deploy

```bash
pskit deploy && pskit deploy --provider gcp && pskit deploy --provider azure
```
