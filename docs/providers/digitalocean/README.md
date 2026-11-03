# DigitalOcean Functions provider

Search terms: digitalocean, DO, DigitalOcean Functions, doctl, doctl serverless, namespace, api_host, web raw,
scheduled trigger, DO_FUNCTIONS_NAMESPACE, DIGITALOCEAN_TOKEN, project.yml

The DigitalOcean provider (`provider.name: digitalocean`) deploys functions to **DigitalOcean Functions**. The
DigitalOcean Terraform plugin has no Functions resource, so pskit writes a standard `doctl serverless` project and
deploys it from a Terraform `terraform_data` resource that runs `doctl` on this machine. Tier: **beta**.

| Item | Value |
|---|---|
| Terraform plugin | none (Terraform's built-in `terraform_data`) |
| Tool needed | `doctl`, installed and authenticated |
| Default region | none (the namespace decides the region; `pskit init` writes `nyc1`) |
| Triggers | http (`web: raw`, public), schedule. No queue, storage or topic. |
| Workflows | embedded orchestrator function (capped by its timeout) |
| Python | `python3.9`, `python3.11` (`python:3.9`, `python:3.11`; default `python3.11`) |
| Node.js | `nodejs18` (`nodejs:18`) |
| Max timeout | 900 s |
| Memory | 128-1024 MB |
| Dependencies | `requirements.txt` is pip-installed into each function folder by pskit |

## Set up DigitalOcean credentials step by step

`doctl` holds the DigitalOcean login; pskit only calls it.

1. Install `doctl`: `brew install doctl` (macOS), `sudo snap install doctl` (Linux), or the Windows zip from the
   DigitalOcean docs, then put it on `PATH`. `pskit doctor -p digitalocean` shows the steps for your OS.
2. Create a personal access token: DigitalOcean control panel -> **API** -> **Generate New Token** (read and write).
3. Run `doctl auth init` and paste the token.
4. Create a Functions namespace if you have none: `doctl serverless namespaces create --label pskit --region nyc1`.
5. List namespaces and copy the id (`fn-...`): `doctl serverless namespaces list`.
6. Export it so the scaffold's `${env:DO_FUNCTIONS_NAMESPACE}` resolves:

   ```bash
   export DO_FUNCTIONS_NAMESPACE=fn-00000000-0000-0000-0000-000000000000
   ```

7. Optional: get the API host for URLs in `pskit info`: `doctl serverless status` prints the connected namespace and
   its API host.

Validation warns when `doctl` is not on `PATH`: *`doctl` is not on PATH; deploy will fail until it is installed and
authenticated (`doctl auth init`)*.

## Configure the digitalocean provider block in pskit.yml

These are all the DigitalOcean options pskit reads:

```yaml
provider:
  name: digitalocean
  runtime: python3.11
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE}          # required
    api_host: https://faas-nyc1-2ef2e6cc.doserverless.co   # optional: enables URLs in pskit info
functions:
  api:
    handler: app.api.handler
    memory: 256                                       # 128-1024
    options:                                          # top-level keys of this function's entry in project.yml
      annotations: {provide-api-key: false}
```

| Option | Required | Meaning |
|---|---|---|
| `namespace` | yes | Functions namespace id. `doctl serverless connect <namespace>` runs before every deploy. |
| `api_host` | no | Namespace API host. Without it, `pskit info` has no URLs. |
| `region` | no | Only sets `PSKIT_REGION` (also `provider.region`). |
| `functions.<fn>.options` | no | Copied over the function's entry in `project.yml`. A key replaces pskit's value whole: `limits` here drops pskit's timeout and memory, so repeat them. |

Studio: **Overview & provider** -> **DigitalOcean Functions options** shows **Functions namespace** (default
`${env:DO_FUNCTIONS_NAMESPACE}`) and **API host**.

## What pskit generates for DigitalOcean

| Item | What it is |
|---|---|
| `.pskit/digitalocean-<stage>/do_project/project.yml` | One package `<service>-<stage>` with one function per pskit function: `runtime`, `main: main`, `web: raw` (http functions) or `false`, `limits` (timeout in ms, memory), `environment`, scheduled `triggers`. |
| `do_project/packages/<service>-<stage>/<fn>/` | A full copy of the bundle per function, with `__main__.py` (Python) or `index.js` (Node.js) calling the pskit adapter. |
| `terraform_data.deploy` | Runs `doctl serverless connect <namespace> && doctl serverless deploy do_project`. Replaced when the artifact or `project.yml` changes. On destroy: `doctl serverless undeploy --packages <service>-<stage>`. |

## How triggers map to DigitalOcean features

| pskit trigger | DigitalOcean implementation |
|---|---|
| `http` | The function is a public web function (`web: raw`). All methods and paths reach it; the pskit runtime routes them. Only `auth: none`. |
| `schedule` | A `scheduler` trigger in `project.yml` with a 5-field cron. `rate` is converted to cron (it must divide 60 minutes or 24 hours, or be whole days up to 31). `input` is sent as the trigger body. `enabled: false` leaves the trigger out. |
| `queue`, `storage`, `topic` | Not available (validation error). |

pskit does not apply a schedule `timezone` on DigitalOcean and does not warn about it.

## Use resources on DigitalOcean

Managed `storage`, `queue` and `topic` resources cannot be created on DigitalOcean. Create Spaces, Managed Databases or
Valkey/Redis in the control panel and declare them with `external: true`. Guides:
[resource-guides/digitalocean/README.md](../../resource-guides/digitalocean/README.md).

## Run workflows on DigitalOcean

Each workflow runs on the embedded engine in a generated function `<workflow>-orchestrator`, reachable at
`POST <its URL>/workflows/<name>` when `api_host` is set. The run must finish within the orchestrator's timeout (max
900 s). See [deployment/workflows.md](../../deployment/workflows.md).

## Find DigitalOcean URLs after deploy

With `api_host`, `pskit info -p digitalocean` shows each http function's URL:
`<api_host>/api/v1/web/<namespace>/<service>-<stage>/<function>`. The `endpoint` is the package URL. Function ids are
`<service>-<stage>/<function>`. Without `api_host`, find URLs with `doctl serverless functions get <id> --url`.

## Permissions on DigitalOcean

The token used by `doctl auth init` needs write access. Web functions are public; validate tokens in the handler.

## Read logs of a DigitalOcean deployment

`pskit logs` and the studio **Logs** page cannot read DigitalOcean logs yet. Use `doctl serverless activations logs
--follow` or the Functions page in the control panel (the `console` link in `pskit info`).

## DigitalOcean limits and gotchas

- HTTP and schedule only. Memory 128-1024 MB. `auth` must be `none`.
- `doctl` must be installed and logged in on the machine that runs `pskit deploy` and `pskit remove`.
- Each function folder gets a full copy of the bundle under `.pskit/digitalocean-<stage>/do_project/`. On Windows keep
  the project path short or enable long paths.
- `invoke()` between functions needs `PSKIT_ENDPOINT_<NAME>` set to the target's URL.

## Deploy to DigitalOcean from the terminal

```bash
pskit doctor -p digitalocean
pskit validate -p digitalocean -s dev
pskit deploy -p digitalocean -s dev     # terraform apply -> doctl serverless deploy
pskit info -p digitalocean -s dev
pskit remove -p digitalocean -s dev --yes   # doctl serverless undeploy
```

## Deploy to DigitalOcean in studio

1. Run `pskit studio --open` from a shell where `doctl auth init` was done.
2. **Overview & provider** -> click **DigitalOcean Functions** -> confirm the switch.
3. Fill **Functions namespace** and **API host** in **DigitalOcean Functions options**. Click **Save**.
4. **Setup & credentials** shows whether `doctl` is found; set `DO_FUNCTIONS_NAMESPACE` with **Set for this session**
   if you use the `${env:...}` default.
5. **Deploy** -> **Deploy** -> confirm. **Info** shows the URLs; **Remove** undeploys the package.

## Minimal DigitalOcean example

```yaml
service: hello-do
provider:
  name: digitalocean
  runtime: python3.11
  options:
    namespace: ${env:DO_FUNCTIONS_NAMESPACE}
    api_host: ${env:DO_API_HOST}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
      - schedule: {cron: "0 6 * * *", input: {report: daily}}
```

## See also

- [Providers index](../README.md)
- [resource-guides/digitalocean/README.md](../../resource-guides/digitalocean/README.md)
- [triggers/schedule.md](../../triggers/schedule.md)
- [deployment/deploy-remove-info.md](../../deployment/deploy-remove-info.md)
