# Concept: return values and HTTP errors

An HTTP handler's return value is converted. `Response(...)` is used as is. `None` becomes 204 No Content. A dict, list, number, dataclass, or pydantic model becomes JSON 200. A str is `text/plain` 200. Bytes are `application/octet-stream` 200. A pair `(body, status)` or a triple `(body, status, headers)` is Flask-style. JSON serialisation handles datetime and date as ISO 8601, plus Decimal, UUID, set, and objects with `model_dump()` or `to_dict()`.

`Response` constructors in the doc are `json`, `text`, `html`, `binary`, `redirect` (status 302 in the example), and `no_content`. `set_cookie` takes `max_age`, `path`, `http_only`, `secure`, and `same_site`. Binary bodies are base64-encoded for gateways. For a non-HTTP event, the return value goes back to the caller as is, including the workflow's next state and the result of `invoke()`.

Raise an `HttpError` subclass for a JSON error. The status table is BadRequest 400, Unauthorized 401, Forbidden 403, NotFound 404, MethodNotAllowed 405, Conflict 409, UnprocessableEntity 422, and TooManyRequests 429.

`Context` carries `request_id`, `function`, `provider`, `service`, `stage`, `region`, `memory_mb` when the platform reports it, `remaining_time_ms()` (or None), a `logger` with function, request_id, and provider bound, `env` as `os.environ`, and `raw` as the native context.

Sources: `docs/handlers.md#returning-a-response`, `docs/handlers.md#errors`, `docs/handlers.md#context`

```python
Response.json({"id": 1}, status=201, headers={"x-request": "abc"})
Response.text("ok")
Response.html("<h1>Hi</h1>")
Response.binary(png_bytes, "image/png")   # base64-encoded for gateways automatically
Response.redirect("/login", status=302)
Response.no_content()
Response.json(user).set_cookie("sid", token, max_age=3600, path="/", http_only=True, secure=True, same_site="Lax")
```
