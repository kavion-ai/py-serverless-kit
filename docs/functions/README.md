# Functions

Search terms: function, handler, serverless function, lambda, cloud function, create function, invoke-only, function kind, functions block, pskit.yml functions

A pskit function is one Python (or Node.js) handler plus the triggers that call it. You describe it once under
`functions:` in `pskit.yml`, and pskit deploys it to any supported cloud or to your own servers. The handler code
does not change between clouds.

## What a function is made of

A pskit function has three parts:

| Part | Where | Example |
|---|---|---|
| A name | the key under `functions:` | `get-item` |
| A handler | `handler:`, a dotted path to the Python (or Node.js) function | `app.handlers.get_item` |
| Triggers (optional) | `events:`, a list of `http`, `schedule`, `queue`, `storage`, `topic`, `smtp` | `- http: GET /items/{id}` |

```yaml
functions:
  get-item:
    handler: app.handlers.get_item
    events:
      - http: GET /items/{id}
```

```python
# app/handlers.py
from py_serverless_kit import Context, Event, NotFound


def get_item(event: Event, ctx: Context):
    item_id = event.http.path_params["id"]
    if item_id != "1":
        raise NotFound("no such item")
    return {"id": item_id, "name": "lamp"}
```

The other settings (memory, timeout, environment, permissions, runtime) are optional. Without them a function
uses the values under `provider:`. See [configuration.md](configuration.md).

## Function kinds shown in studio and the dashboard

The pskit function kind is derived from its triggers. Studio's **Functions** page shows it in the **Kind** column.

| Kind | Triggers |
|---|---|
| `http` | only `http` |
| `scheduled` | only `schedule` |
| `http+event` | `http` and at least one other trigger |
| `event-driven` | any mix without `http` (queue, storage, topic, smtp, schedule) |
| `invoke-only` | no triggers: called by a workflow, by `invoke()` or by `pskit invoke` |

A function with no triggers still deploys. Studio shows "direct invoke" in its **Triggers** column.

## Pages in this section

| Page | What it covers |
|---|---|
| [create.md](create.md) | Create a function in studio and from the terminal; single code file vs its own folder (`functions/<name>/` with its own `requirements.txt`); Python and Node.js / TypeScript handlers |
| [configuration.md](configuration.md) | Every per-function key: `handler`, `description`, `enabled`, `runtime`, `memory`, `timeout`, `environment`, `tags`, `events`, `concurrency`, `architecture`, `iam`, `options`; per-cloud limits |
| [invoke-and-test.md](invoke-and-test.md) | Return values and HTTP responses, errors, `invoke()` between functions, `pskit invoke`, `pskit dev`, `pskit trigger`, studio Test page, pytest with `LocalRunner` |
| [../triggers/README.md](../triggers/README.md) | Every trigger type and which cloud supports it |

## The handler API in one table

The pskit handler API is importable from `py_serverless_kit` and is the same on every cloud. You never add
`py-serverless-kit` to the function's `requirements.txt`: pskit copies its standard-library runtime into every bundle.

| Name | Use |
|---|---|
| `Event` | what triggered the call: `type`, `http`, `records`, `data`, `time`, `source`, `raw` |
| `Context` | `request_id`, `function`, `provider`, `service`, `stage`, `region`, `memory_mb`, `remaining_time_ms()`, `logger` |
| `Response` | `Response.json(...)`, `.text`, `.html`, `.binary`, `.redirect`, `.no_content`, `.set_cookie` |
| `HttpError` and subclasses | `BadRequest` 400, `Unauthorized` 401, `Forbidden` 403, `NotFound` 404, `MethodNotAllowed` 405, `Conflict` 409, `UnprocessableEntity` 422, `TooManyRequests` 429 |
| `BatchResult` | report failed queue / topic / storage records |
| `invoke()` | call another function of the same service |
| `resource()`, `resources()` | connection details of bound `resources:` entries |
| `get_secret()`, `get_secrets()`, `put_secret()` | secrets from Vault / OpenBao, AWS Secrets Manager or environment variables |

The full reference is [../handlers.md](../handlers.md). Node.js names are camelCase: [../nodejs.md](../nodejs.md).

## See also

- [create.md](create.md)
- [configuration.md](configuration.md)
- [invoke-and-test.md](invoke-and-test.md)
- [../triggers/README.md](../triggers/README.md)
- [../guide/concepts.md](../guide/concepts.md)
- [../studio-guide/functions.md](../studio-guide/functions.md)
- [../handlers.md](../handlers.md)
