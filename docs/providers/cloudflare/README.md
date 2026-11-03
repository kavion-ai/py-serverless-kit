# Cloudflare Workers provider

Search terms: cloudflare, Cloudflare Workers, worker, workers.dev, Pyodide, Python Workers, esbuild, nodejs_compat,
cron triggers, zone route, account_id, CLOUDFLARE_API_TOKEN, compatibility_date

The Cloudflare provider (`provider.name: cloudflare`) deploys **one Worker script per function**. Python functions run
as Python Workers on **Pyodide**; JavaScript and TypeScript functions are bundled with esbuild. Tier: **experimental**.

| Item | Value |
|---|---|
| Terraform plugin | `cloudflare/cloudflare >= 5.28, < 6.0` |
| Region | not used |
| Triggers | http (`workers.dev` and/or a zone route), schedule (Cron Triggers, UTC). No queue, storage or topic. |
| Workflows | embedded orchestrator Worker (capped by its timeout) |
| Python | `python3.11`, `python3.12`, `python3.13` (default `python3.12`) |
| Node.js | `nodejs18`, `nodejs20`, `nodejs22` (Workers run JavaScript; the version only selects the language) |
| Max timeout | 900 s |
| Python dependencies | **not bundled**: standard library and Pyodide's built-in packages only |
| Node.js dependencies | bundled into one ES module per Worker by esbuild |

## Set up Cloudflare credentials step by step

The Cloudflare Terraform plugin reads an API token from `CLOUDFLARE_API_TOKEN`.

1. Cloudflare dashboard -> profile -> **API Tokens** -> **Create Token** -> template **Edit Cloudflare Workers** (add
   *Zone - Workers Routes - Edit* when you use routes). Copy the token.
2. Find the account id: dashboard -> **Workers & Pages** -> *Account ID* in the right column (or the URL
   `dash.cloudflare.com/<account id>`).
3. Find your `workers.dev` subdomain: **Workers & Pages** -> *Subdomain* (`<name>.workers.dev`).
4. Export:

   ```bash
   export CLOUDFLARE_API_TOKEN=<token>
   export CLOUDFLARE_ACCOUNT_ID=<account id>   # read by the scaffold's ${env:CLOUDFLARE_ACCOUNT_ID}
   ```

5. For JavaScript or TypeScript, install Node.js and npm (esbuild runs during `pskit package`).
6. Run `pskit doctor -p cloudflare`. Wrangler is listed as the Cloudflare CLI but pskit does not need it to deploy.

In studio: **Setup & credentials** -> **Provider** `cloudflare` -> **Environment variables** -> set both values ->
**Set for this session**.

## Configure the cloudflare provider block in pskit.yml

These are all the Cloudflare options pskit reads:

```yaml
provider:
  name: cloudflare
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID}   # required
    workers_subdomain: my-team                 # <worker>.my-team.workers.dev URLs in pskit info
    workers_dev: true                          # default true: enable the workers.dev URL for http functions
    zone_id: abcdef0123...                     # needed for routes
    compatibility_date: "2025-09-01"           # default 2025-09-01
functions:
  api:
    handler: app.api.handler
    options:
      route: api.example.com/*                 # zone route for this Worker (needs zone_id)
      # any other cloudflare_workers_script argument
```

| Option | Required | Meaning |
|---|---|---|
| `account_id` | yes | Cloudflare account. |
| `workers_subdomain` | no | Your `workers.dev` subdomain; only used to print URLs. |
| `workers_dev` | no | `false` skips the `workers.dev` subdomain resource (then use a route). |
| `zone_id` | for routes | Zone of `functions.<fn>.options.route`. A route without it is a validation error. |
| `compatibility_date` | no | Workers compatibility date. Keep `2025-09-01` or later for Node.js (`node:fs`). |
| `functions.<fn>.options.route` | no | Route pattern, for example `api.example.com/*`. Other keys merge into `cloudflare_workers_script`. |

Studio: **Overview & provider** -> **Cloudflare Workers options** shows **Account ID**, **Zone ID**, **Route**,
**workers.dev subdomain** (the `workers_dev` switch), **workers.dev account subdomain** and **Compatibility date**.
pskit reads `route` only per function: set it on the **YAML** page under `functions.<fn>.options.route`; a provider-level
**Route** value is ignored.

## How pskit builds Cloudflare Workers

- **Python:** for each function pskit writes `.pskit/cloudflare-<stage>/cloudflare/<fn>.py`, one module that embeds
  every `.py` file of the bundle (your code plus the pskit runtime) and an import hook, so packages and relative imports
  keep working. It is uploaded as `worker.py` with `compatibility_flags: [python_workers]`. Non-Python files are not
  uploaded (warning). `requirements.txt` is not bundled (warning on every validate).
- **JavaScript / TypeScript:** pskit writes `_pskit_cf/<fn>.mjs`, which imports your handler modules, the manifest and
  the adapter, and esbuild bundles it to `_pskit_cf/<fn>.bundle.mjs` (uploaded as `worker.mjs` with
  `compatibility_flags: [nodejs_compat]`). npm dependencies are included. `require()` of `assert buffer crypto events
  fs path stream string_decoder url util` works through a generated shim; other Node.js built-ins are not available.
  `package.node.bundle: false` is a validation error.
- Environment variables: Python Workers get them embedded in the module; JavaScript Workers get `plain_text` bindings
  copied into `process.env`.

## Terraform resources pskit creates on Cloudflare

| Resource | When |
|---|---|
| `cloudflare_workers_script` | one per function, named `<service>-<stage>-<function>` |
| `cloudflare_workers_script_subdomain` | per http function while `workers_dev` is true |
| `cloudflare_workers_route` | per function with `options.route` |
| `cloudflare_workers_cron_trigger` | per function with enabled schedules |

## How triggers map to Cloudflare features

| pskit trigger | Cloudflare implementation |
|---|---|
| `http` | The Worker's `fetch`. All paths of that Worker reach it; the pskit runtime routes them. Only `auth: none` (check tokens in the handler, or use Cloudflare Access). |
| `schedule` | Cron Triggers, 5-field cron in UTC. `rate` is converted to cron. The schedule's `input` is delivered as `event.data`. `enabled: false` leaves it out. |
| `queue`, `storage`, `topic` | Not available (validation error). |

## Use resources on Cloudflare

Managed `storage`, `queue` and `topic` resources cannot be created on Cloudflare. Create R2, D1, KV or Queues in the
dashboard and declare them with `external: true`. Guides:
[resource-guides/cloudflare/README.md](../../resource-guides/cloudflare/README.md).

## Run workflows on Cloudflare

Each workflow runs on the embedded engine in a generated Worker `<workflow>-orchestrator`, started with
`POST <its URL>/workflows/<name>` (URLs appear when `workers_subdomain` or a route is set). See
[deployment/workflows.md](../../deployment/workflows.md).

## Find Cloudflare URLs after deploy

`pskit info -p cloudflare` shows each Worker's `id` (script name), a dashboard console link, and a URL:
`https://<script>.<workers_subdomain>.workers.dev` when `workers_dev` is on and `workers_subdomain` is set, else
`https://<route without the trailing *>`. A route `GET /hello` is at `<url>/hello`.

## Read logs of a Cloudflare deployment

`pskit logs` and the studio **Logs** page cannot read Workers logs yet. Open the `console` link from `pskit info`
(**Workers & Pages** -> the Worker -> **Logs**), or run `wrangler tail <script name>`.

## Cloudflare limits and gotchas

- Python Workers: no third-party packages beyond Pyodide's; non-`.py` files are dropped.
- HTTP and schedule only; `auth` must be `none`; Cron Triggers run in UTC.
- One Worker per function, so each function has its own URL.
- `invoke()` between Workers needs `PSKIT_ENDPOINT_<NAME>` set to the target's URL.

## Deploy to Cloudflare from the terminal

```bash
pskit doctor -p cloudflare
pskit validate -p cloudflare -s dev
pskit deploy -p cloudflare -s dev
pskit info -p cloudflare -s dev
pskit remove -p cloudflare -s dev --yes
```

## Deploy to Cloudflare in studio

1. Run `pskit studio --open`.
2. **Overview & provider** -> click **Cloudflare Workers** -> confirm the switch (unsupported triggers are listed).
3. Fill **Account ID** and **workers.dev account subdomain**. Click **Save**.
4. **Setup & credentials** -> set `CLOUDFLARE_API_TOKEN` -> **Set for this session**.
5. **Deploy** -> **Deploy** -> confirm. **Info** shows the Worker URLs. **Remove** deletes the Workers.

## Minimal Cloudflare example

```yaml
service: hello-cf
provider:
  name: cloudflare
  runtime: python3.12
  options:
    account_id: ${env:CLOUDFLARE_ACCOUNT_ID}
    workers_subdomain: my-team
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
      - schedule: {cron: "*/30 * * * *"}
```

## See also

- [Providers index](../README.md)
- [resource-guides/cloudflare/README.md](../../resource-guides/cloudflare/README.md)
- [nodejs.md](../../nodejs.md): JavaScript and TypeScript functions
- [deployment/deploy-remove-info.md](../../deployment/deploy-remove-info.md)
