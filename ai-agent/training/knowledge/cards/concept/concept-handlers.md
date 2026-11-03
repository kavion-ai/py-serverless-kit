# Concept: handler signatures

The handler API is importable from `py_serverless_kit` and behaves the same on every cloud. The runtime uses only the standard library and is copied into every deployment bundle. You do not add `py-serverless-kit` to the function's `requirements.txt`.

The documented import list is Event, EventType, HttpRequest, Record, Headers, Context, Response, HttpError, BadRequest, Unauthorized, Forbidden, NotFound, MethodNotAllowed, Conflict, UnprocessableEntity, TooManyRequests, BatchResult, and invoke. Later sections also import `invoke` on its own, and `get_secret`, `get_secrets`, `put_secret`, and `SecretNotFound`.

A handler may take `(event, ctx)`, or only `event`. An `async def` is awaited. `handler` in pskit.yml is `package.module.function` or `package.module:function`, relative to `package.source`.

`get_secret("db-password")` reads a plain secret. `get_secret("stripe", "webhook")` reads one field of a JSON secret. `default=""` avoids `SecretNotFound`. `put_secret` writes on Vault / OpenBao and Secrets Manager. The store comes from `PSKIT_SECRETS_DRIVER`: `vault`, `aws`, or `env` (the default). Values are cached for 60 seconds. `store="other"` reads `PSKIT_OTHER_*`.

Sources: `docs/handlers.md#handler-api`, `docs/handlers.md#handler-signatures`, `docs/handlers.md#get_secret-secrets-on-every-provider`

```python
from py_serverless_kit import (
    Event, EventType, HttpRequest, Record, Headers, Context, Response,
    HttpError, BadRequest, Unauthorized, Forbidden, NotFound, MethodNotAllowed,
    Conflict, UnprocessableEntity, TooManyRequests, BatchResult, invoke,
)
```
