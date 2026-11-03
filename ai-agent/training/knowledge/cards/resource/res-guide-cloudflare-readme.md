# Cloudflare resources

How to attach services you created in the Cloudflare dashboard (R2, Queues, D1, Workers KV, Hyperdrive, ...) to Workers deployed with pskit. | `type` | Cloudflare service | Guide | |---|---|---| | `storage` | R2 bucket | storage.md | | `queue` | Queues | queue.md | | `topic` | none (no pub/sub service) | topic.md | | `database` | D1 (Hyperdrive for PostgreSQL) | database.md | | `cache` | Workers KV | cache.md | | `custom` | secrets, Workers AI, Vectorize, any HTTP API | custom.md |
## What pskit supports on Cloudflare Read this first: Cloudflare is the most limited target.

| | Supported | |---|---| | Triggers | `http` and `schedule` only. A `queue`, `storage` or `topic` event is a validation error: `Cloudflare Workers does not support `queue` events in pskit (supported: http, schedule)` | | Managed resources | no. `type: storage` / `queue` / `topic` without `external: true` fails with `managed storage resources that no event uses are not supported on Cloudflare Workers yet; create it outside pskit and set `external: true`` | | External resources | yes: `external: true` + `name` + `connection`. Handlers get the usual `PSKIT_RESOURCE_*` variables | | Python dependencies | **none**: Python Workers run on Pyodide, so only the standard library and Pyodide's built-in packages exist. `requirements.txt` is not bundled (cloud SDKs like `boto3` won't work) | | Node.js / TypeScript | npm dependencies are bundled with esbuild | So on Cloudflare you always create the resource in the dashboard, then reach it from a handler in one of two ways: 1. **A Workers binding** (recommended for R2, Queues, D1, KV, Hyperdrive). Add it with `functions.<fn>.options.bindings`. pskit merges a function's `options` into its `cloudflare_workers_script` resource (the documented escape hatch, see configuration.md). In a Python handler the Workers `env` object is `ctx.raw`, so a binding named `UPLOADS` is `ctx.raw.UPLOADS`. 2. **The service's HTTP API** with an API token, called through `from js import fetch` (Python) or `fetch` (JavaScript). Bindings are per function: list them on every function that uses them. **Node.js / TypeScript services:** pskit already sets `bindings` on the script: one `plain_text` binding per environment variable, including the `PSKIT_RESOURCE_*` ones. `options.bindings` **replaces** that list, so on such a function `resource()` and `environment` values are gone unless you list them again as `{type: plain_text, name: ..., text: ...}`. Read the binding itself from `context.raw` (the Workers `env`). Python services don't have this problem: their environment is embedded in the script. `ctx.raw` is `None` under `pskit invoke` / `pskit dev`, so code that uses bindings only runs on Cloudflare.

```text
functions:
  api:
    handler: app.handlers.api
    events: [{http: POST /orders}]
    options:
      bindings:                 # arguments of cloudflare_workers_script.bindings (provider 5.x)
        - {type: r2_bucket,    name: UPLOADS, bucket_name: shop-uploads}
        - {type: queue,        name: JOBS,    queue_name: shop-jobs}
        - {type: d1,           name: DB,      id: <database id>}
        - {type: kv_namespace, name: CACHE,   namespace_id: <namespace id>}
        - {type: hyperdrive,   name: PG,      id: <hyperdrive config id>}
```
