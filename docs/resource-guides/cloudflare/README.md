# Cloudflare resources

How to attach services you created in the [Cloudflare dashboard](https://dash.cloudflare.com) (R2, Queues, D1,
Workers KV, Hyperdrive, ...) to Workers deployed with pskit.

| `type` | Cloudflare service | Guide |
|---|---|---|
| `storage` | R2 bucket | [storage.md](storage.md) |
| `queue` | Queues | [queue.md](queue.md) |
| `topic` | none (no pub/sub service) | [topic.md](topic.md) |
| `database` | D1 (Hyperdrive for PostgreSQL) | [database.md](database.md) |
| `cache` | Workers KV | [cache.md](cache.md) |
| `custom` | secrets, Workers AI, Vectorize, any HTTP API | [custom.md](custom.md) |

## What pskit supports on Cloudflare

Read this first: Cloudflare is the most limited target.

| | Supported |
|---|---|
| Triggers | `http` and `schedule` only. A `queue`, `storage` or `topic` event is a validation error: `Cloudflare Workers does not support `queue` events in pskit (supported: http, schedule)` |
| Managed resources | no. `type: storage` / `queue` / `topic` without `external: true` fails with `managed storage resources that no event uses are not supported on Cloudflare Workers yet; create it outside pskit and set `external: true`` |
| External resources | yes: `external: true` + `name` + `connection`. Handlers get the usual `PSKIT_RESOURCE_*` variables |
| Python dependencies | **none**: Python Workers run on Pyodide, so only the standard library and Pyodide's built-in packages exist. `requirements.txt` is not bundled (cloud SDKs like `boto3` won't work) |
| Node.js / TypeScript | npm dependencies are bundled with esbuild |

So on Cloudflare you always create the resource in the dashboard, then reach it from a handler in one of two ways:

1. **A Workers binding** (recommended for R2, Queues, D1, KV, Hyperdrive). Add it with `functions.<fn>.options.bindings`.
   pskit merges a function's `options` into its `cloudflare_workers_script` resource (the documented escape hatch, see
   [configuration.md](../../configuration.md#escape-hatches)). In a Python handler the Workers `env` object is
   `ctx.raw`, so a binding named `UPLOADS` is `ctx.raw.UPLOADS`.
2. **The service's HTTP API** with an API token, called through `from js import fetch` (Python) or `fetch` (JavaScript).

```yaml
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

Bindings are per function: list them on every function that uses them.

**Node.js / TypeScript services:** pskit already sets `bindings` on the script: one `plain_text` binding per
environment variable, including the `PSKIT_RESOURCE_*` ones. `options.bindings` **replaces** that list, so on such a
function `resource()` and `environment` values are gone unless you list them again as
`{type: plain_text, name: ..., text: ...}`. Read the binding itself from `context.raw` (the Workers `env`). Python
services don't have this problem: their environment is embedded in the script.

`ctx.raw` is `None` under `pskit invoke` / `pskit dev`, so code that uses bindings only runs on Cloudflare. Keep the
binding code in small functions you can stub in tests.

## Values you need for every Cloudflare resource

| Value | Where |
|---|---|
| Account ID | Dashboard → **Account home** → the **⋯** menu next to your account → **Copy account ID**; or **Workers & Pages → Overview** → *Account details* on the right; or the first segment of the dashboard URL `dash.cloudflare.com/<account id>/...` |
| API token (for deploying) | Avatar → **My Profile → API Tokens → Create Token** → template *Edit Cloudflare Workers* (add the products you bind, e.g. *D1 Edit*, *Workers KV Storage Edit*, *Queues Edit*) |
| `workers_subdomain` | **Workers & Pages → Overview** → *Subdomain* (`<name>.workers.dev`) |

```bash
export CLOUDFLARE_API_TOKEN=...          # used by Terraform
export CLOUDFLARE_ACCOUNT_ID=...
```

```yaml
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID}
    workers_subdomain: my-team
```

## Secrets

For Python Workers, pskit writes `environment` and `connection` values **into the generated Worker script**, so they are
visible in the script and in Terraform state. For a secret, use a `secret_text` binding and read it from `ctx.raw`:

```yaml
    options:
      bindings:
        - {type: secret_text, name: STRIPE_KEY, text: "${env:STRIPE_KEY}"}   # still in Terraform state (marked sensitive)
```

```python
token = ctx.raw.STRIPE_KEY
```

## Testing

`pskit trigger` / `pskit resources send` can only send HTTP requests on Cloudflare; `pskit resources send --list` prints
the dashboard steps and the command line to use for each resource. Logs: the Worker's **Logs** tab in the dashboard
(`pskit info` prints the console link) or `wrangler tail <worker name>`; `pskit logs` doesn't read Cloudflare logs.
