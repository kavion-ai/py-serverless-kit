# Handler API

Everything here is importable from `py_serverless_kit` and behaves the same on every cloud. The runtime uses only the standard library and is copied into every deployment bundle. You never add `py-serverless-kit` to your function's `requirements.txt`.

```python
from py_serverless_kit import (
    Event, EventType, HttpRequest, Record, Headers, Context, Response,
    HttpError, BadRequest, Unauthorized, Forbidden, NotFound, MethodNotAllowed,
    Conflict, UnprocessableEntity, TooManyRequests, BatchResult, invoke,
)
```

## Handler signatures

```python
def handler(event: Event, ctx: Context): ...     # two arguments
def handler(event: Event): ...                   # one argument also works
async def handler(event: Event, ctx: Context): ... # coroutines are awaited
```

`handler:` in `pskit.yml` is `package.module.function` or `package.module:function`, relative to `package.source`.

## `Event`

| Attribute | Type | Meaning |
|---|---|---|
| `type` | str | `"http"`, `"schedule"`, `"queue"`, `"storage"`, `"topic"`, `"invoke"`, `"workflow"` (constants on `EventType`) |
| `provider` | str | `aws`, `gcp`, …, or `local` |
| `function` | str | logical function name from the config |
| `http` | `HttpRequest` \| None | set for HTTP events |
| `records` | list[`Record`] | queue / topic / storage batches |
| `data` | Any | payload of schedule (`input`), invoke and workflow events |
| `time` | datetime (UTC) | event time if the platform provides it, else now |
| `source` | str \| None | e.g. queue ARN, topic name |
| `raw` | Any | the untouched native payload (use sparingly: it's not portable) |

Helpers:

- `is_http`, `is_batch`
- `json()`: the parsed HTTP body, the first record's body, or `data`, depending on the type
- `for record in event:` iterates `records`
- `to_dict()`: a summary that is safe to log

## `HttpRequest`

| Attribute / method | Notes |
|---|---|
| `method` | upper case |
| `path` | request path as seen by the function |
| `route` | the matched route template, e.g. `/users/{id}` |
| `headers` | `Headers`: case-insensitive, read-only mapping; repeated headers joined with `", "` |
| `query` | `dict[str, str]` (last value wins) |
| `multi_query` | `dict[str, list[str]]` |
| `path_params` | `dict[str, str]` from `{name}` / `{name+}` |
| `body` | `bytes` (base64 already decoded) |
| `source_ip` | client IP when known |
| `content_type` | e.g. `application/json` (no parameters) |
| `cookies` | `dict` parsed from the `Cookie` header |
| `text(encoding="utf-8")` | body as str |
| `json(default=...)` | parse the body; invalid/empty JSON raises `BadRequest` (HTTP 400) unless you pass `default` |
| `form()` | parse `application/x-www-form-urlencoded` |

## `Record`

| Attribute | Notes |
|---|---|
| `id` | message id (used by `BatchResult`) |
| `body` | message body (str/bytes/dict) |
| `attributes` | message attributes / metadata |
| `source` | queue/topic identifier |
| `bucket`, `key`, `size`, `action` | storage events; `action` is `"created"` or `"deleted"` |
| `raw` | native record |
| `text()`, `json(default=...)` | decode the body |

## `Context`

| Attribute / method | Notes |
|---|---|
| `request_id` | platform request id (or a UUID) |
| `function`, `provider`, `service`, `stage`, `region` | identity of this deployment |
| `memory_mb` | when the platform reports it |
| `remaining_time_ms()` | ms until timeout, or `None` if unknown |
| `logger` | structured logger with `function`, `request_id` and `provider` already bound |
| `env` | `os.environ` |
| `raw` | native context object |

## Returning a response

Whatever an HTTP handler returns is converted:

| Return value | Response |
|---|---|
| `Response(...)` | as is |
| `None` | `204 No Content` |
| `dict`, `list`, numbers, dataclasses, pydantic models | JSON `200` |
| `str` | `text/plain` `200` |
| `bytes` | `application/octet-stream` `200` |
| `(body, status)` / `(body, status, headers)` | Flask-style |

JSON serialisation handles `datetime`/`date` (ISO 8601), `Decimal`, `UUID`, `set` and anything with `model_dump()` or `to_dict()`.

```python
Response.json({"id": 1}, status=201, headers={"x-request": "abc"})
Response.text("ok")
Response.html("<h1>Hi</h1>")
Response.binary(png_bytes, "image/png")   # base64-encoded for gateways automatically
Response.redirect("/login", status=302)
Response.no_content()
Response.json(user).set_cookie("sid", token, max_age=3600, path="/", http_only=True, secure=True, same_site="Lax")
```

For non-HTTP events, the return value goes back to the caller as is: the workflow's next state, the result of `invoke()`, and so on.

## Errors

Raise an `HttpError` subclass to return a JSON error:

| Exception | Status |
|---|---|
| `BadRequest` | 400 |
| `Unauthorized` | 401 |
| `Forbidden` | 403 |
| `NotFound` | 404 |
| `MethodNotAllowed` | 405 |
| `Conflict` | 409 |
| `UnprocessableEntity` | 422 |
| `TooManyRequests` | 429 |
| `HttpError(message, status=..., details=..., headers=...)` | any |

```python
raise UnprocessableEntity("invalid order", details={"field": "amount"})
# -> 422 {"error": "invalid order", "status": 422, "details": {"field": "amount"}}
```

Any other exception in an HTTP handler becomes `500 {"error": "Internal Server Error", "status": 500, "request_id": ...}`, and the traceback goes to the logs. Set `PSKIT_DEBUG=1` to include the exception text in the body (never in production).

For **non-HTTP** events, exceptions are re-raised so the platform's retry and dead-letter behaviour applies. On clouds where every call arrives over HTTP (GCP, IBM, DigitalOcean, Cloudflare, Oracle), workflow, schedule and invoke calls that fail return `500 {"errorType": "<ExceptionClass>", "cause": "<message>"}`. Workflow `retry`/`catch` rules match on that exception class name.

## `BatchResult`

Return a `BatchResult` from queue/topic/storage handlers to report the records that failed:

```python
from py_serverless_kit import BatchResult

def worker(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            process(record.json())
        except Exception:
            result.fail(record)        # or result.fail(record.id)
    return result                      # BatchResult.of(failed_records) also works
```

| Provider | Behaviour |
|---|---|
| aws (SQS) | becomes `batchItemFailures`, so only the failed messages are retried |
| onprem | the host retries only the failed message ids, and moves a message to `dead_letter` after `max_receive` |
| local | printed as `batchItemFailures` |
| everyone else | any failure raises `BatchFailure`, so the whole delivery is retried |

Write idempotent handlers: redelivery is normal on every cloud.

## `invoke()`: calling another function

```python
from py_serverless_kit import invoke

result = invoke("billing", {"order_id": 42})                  # waits for the result
invoke("audit", {"order_id": 42}, asynchronous=True)          # fire and forget (AWS)
```

How the target is resolved:

1. If `PSKIT_ENDPOINT_<NAME>` is set (`billing` → `PSKIT_ENDPOINT_BILLING`, non-alphanumerics become `_`), pskit POSTs to that http(s) URL. This works on any provider.
2. `local` (CLI, tests) and `onprem`: call the handler in-process. `asynchronous=True` still finishes before `invoke()` returns.
3. `aws`: `lambda:InvokeFunction` via boto3 (`pip install py-serverless-kit[aws]`, and add `boto3` to requirements). Grant `lambda:InvokeFunction` in `iam.statements`.
4. `gcp`: authenticated HTTPS call to `https://<region>-<project>.cloudfunctions.net/<service>-<stage>-<name>` with an ID token from the metadata server.
5. Other providers raise `InvokeError` unless `PSKIT_ENDPOINT_<NAME>` is set. Point it at the target's HTTP URL from `pskit info`. On Azure, invoke-only functions expose `POST /_pskit/invoke/<name>` (function key required).

Example: [`examples/09-function-invoke`](../examples/09-function-invoke).

## `get_secret()`: secrets on every provider

```python
from py_serverless_kit import get_secret, get_secrets, put_secret, SecretNotFound

password = get_secret("db-password")                 # plain secret
webhook = get_secret("stripe", "webhook")            # one field of a JSON secret
token = get_secret("optional-token", default="")     # no SecretNotFound
put_secret("last-run", "2026-10-22")                 # Vault / OpenBao and Secrets Manager
```

The store comes from environment variables, so the code does not change: `PSKIT_SECRETS_DRIVER` = `vault`
(HashiCorp Vault / OpenBao, with `PSKIT_SECRETS_URL` and `_TOKEN`), `aws` (AWS Secrets Manager; Lambda's credentials)
or `env` (default: `PSKIT_SECRET_<NAME>`, then `<NAME>`). `store="other"` reads `PSKIT_OTHER_*`. Values are cached for
60 s. On premises a one-click OpenBao, Secrets Manager compatible server or LocalStack writes these variables for you:
[resource-guides/onprem/secrets.md](resource-guides/onprem/secrets.md).

## Environment variables

pskit injects:

| Variable | Value |
|---|---|
| `PSKIT_PROVIDER` | `aws`, `gcp`, `onprem`, … (`local` under the CLI) |
| `PSKIT_ONPREM_ROOT` | on-premises only: directory of the running host. Handlers use it to publish into the file broker |
| `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_REGION` | deployment identity |
| `PSKIT_FUNCTION`, `PSKIT_HANDLER` | the logical function and its handler (not app settings on Azure, where they're passed explicitly) |
| `PSKIT_GCP_PROJECT` | GCP only |

Your own `provider.environment` and `functions.<fn>.environment` are added on top.

Runtime switches you can set:

| Variable | Effect |
|---|---|
| `PSKIT_LOG_FORMAT` | `json` (default in the cloud) or `text` (default under the CLI) |
| `PSKIT_LOG_LEVEL` / `LOG_LEVEL` | log level, default `INFO` |
| `PSKIT_DEBUG` | `1`/`true` adds exception details to 500 responses |

## Logging

```python
ctx.logger.info("order created", extra={"order_id": 42, "amount": 9.5})
```

Output is one JSON object per line, which every cloud's log service can index:

```json
{"ts": "2026-01-01T12:00:00+00:00", "level": "INFO", "logger": "pskit.function", "message": "order created",
 "function": "create-order", "request_id": "…", "provider": "aws", "order_id": 42, "amount": 9.5}
```

`extra` keys that collide with Python `LogRecord` attributes (`name`, `message`, `msg`, `args`, …) are renamed with a trailing underscore (`name_`), so a log call can never crash your handler. For each HTTP request the runtime also logs method, path, status and duration.

Example: [`examples/12-async-and-context`](../examples/12-async-and-context).
