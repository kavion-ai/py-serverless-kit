# Concept: the __pskit envelope

Payloads that pskit itself produces are wrapped as `{"__pskit": "<schedule|workflow|invoke>", "data": ...}`. The architecture doc says these are schedule inputs, workflow task inputs, and `invoke()` calls. The events doc says the same for schedules that have `input`, workflow tasks, and `invoke()` calls. `envelope()` in `runtime/adapters/base.py` builds that object. The key constant is `ENVELOPE_KEY = "__pskit"`. Extra keyword arguments are copied onto the object beside `__pskit` and `data`.

`unwrap_envelope` reads a dict, or JSON text or bytes. When `__pskit` is present it returns the kind, `data`, and any other fields. A kind that is not in `EventType.ALL` is returned as `invoke`. Known kinds, including `smtp`, stay as written. If the value is not an envelope, the function returns None.

The adapter unwraps the envelope before the handler runs, so the handler sees `event.type` and `event.data`. That matters on clouds where everything arrives as HTTP: GCP, IBM, DigitalOcean, Cloudflare, and Oracle. On those clouds, failures come back as `500 {"errorType", "cause"}` so a native workflow can match the error by exception name. A schedule handler still sees `event.type == "schedule"` and `event.data` equal to the configured `input`. A workflow task still sees `event.type == "workflow"`.

Sources: `docs/architecture.md#runtime-flow`, `docs/events.md#schedule-invoke-envelope`, `src/py_serverless_kit/runtime/adapters/base.py`
