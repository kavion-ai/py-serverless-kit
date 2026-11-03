# Example: 12-async-and-context

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: 

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

In the cloud this produces one JSON line:

Locally the CLI switches to readable text (`PSKIT_LOG_FORMAT=text`). Control the level with
`LOG_LEVEL`.

## Run locally

Expected (abridged):

Locally `remaining_time_ms()` is `null`. On AWS, Azure and the others it counts down
from the configured timeout.
