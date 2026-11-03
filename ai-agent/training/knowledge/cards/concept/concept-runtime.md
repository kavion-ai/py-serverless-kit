# Concept: the runtime

Deploy-time is the CLI: pskit.yml becomes a zip and Terraform JSON, then Terraform runs. Run-time is `py_serverless_kit.runtime`, copied into every bundle. It uses only the standard library. CLAUDE.md says it must run on Python 3.9: no third-party imports, no `match`, and no runtime-evaluated union types. The rest of the package also supports Python 3.9.

A native event hits a generated shim, then `runtime/adapters/<cloud>.py`. `to_event` builds an `Event`. `to_context` builds a `Context`. `runtime/dispatch.py` `execute` looks up the function in `pskit_manifest.json` (or `PSKIT_FUNCTION` / `PSKIT_HANDLER`), matches HTTP routes, imports the handler, calls it, and awaits a coroutine. HTTP results become a `Response`. `HttpError` and other exceptions become JSON errors. Other event types return the result or re-raise so the platform can retry. `BatchResult` has its own meaning. The adapter turns the result back into the native response.

The zip holds your code, `py_serverless_kit` with `__init__.py`, `_version.py`, and `runtime/` only (no CLI, pydantic, yaml, or click), `pskit_manifest.json`, a cloud shim, and either installed dependencies or `requirements.txt`. The artifact is byte-identical for identical inputs: sorted zip entries and fixed timestamps. Unchanged code keeps the same hash.

`resources` become `PSKIT_RESOURCE_<KEY>_*` variables. `runtime/resources.py` reads them. On premises, a driver binding can make the host broker use `runtime/drivers/redis.py` or `runtime/drivers/s3.py` instead of directories.

Sources: `docs/architecture.md#runtime-flow`, `docs/architecture.md#bundle-layout`, `CLAUDE.md`
