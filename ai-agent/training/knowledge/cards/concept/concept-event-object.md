# Concept: the Event object

`Event.type` in the handlers doc is listed as http, schedule, queue, storage, topic, invoke, or workflow, with constants on `EventType`. `EventType` in `runtime/event.py` also defines `SMTP = "smtp"`. `EventType.ALL` is http, schedule, queue, storage, topic, invoke, workflow, and smtp. The code comment says smtp `data` is the parsed mail. The handlers table omits smtp. The code wins. invoke and workflow are runtime types. They are not entries in `EVENT_TYPES`.

Other attributes: `provider` is the cloud name or `local`. `function` is the logical name. `http` is an `HttpRequest` or None. `records` is a list of `Record` for queue, topic, and storage batches. `data` is the payload of schedule, invoke, and workflow events. `time` is UTC from the platform, or now. `source` is optional, for example a queue ARN. `raw` is the untouched native payload. Helpers are `is_http`, `is_batch`, `json()`, iteration over `records`, and `to_dict()`.

`HttpRequest` has upper-case `method`, `path`, `route`, case-insensitive `headers` (repeated headers joined with `", "`), `query` (last value wins), `multi_query`, `path_params`, `body` as bytes, `source_ip`, `content_type`, and `cookies`. `text()`, `json(default=...)`, and `form()` decode the body. Invalid or empty JSON raises `BadRequest` unless you pass `default`.

A `Record` has `id`, `body`, `attributes`, `source`, and storage fields `bucket`, `key`, `size`, and `action` (`created` or `deleted`), plus `raw`, `text()`, and `json()`.

Sources: `docs/handlers.md#event`, `docs/handlers.md#httprequest`, `docs/handlers.md#record`, `src/py_serverless_kit/runtime/event.py`
