# IBM Cloud Code Engine functions provider

Search terms: ibm, IBM Cloud, Code Engine, Code Engine functions, IC_API_KEY, project_id, resource group,
code_reference, managed_domain_mappings, visibility, us-south, ibm terraform

The IBM provider (`provider.name: ibm`) deploys each function as an **IBM Cloud Code Engine function**. Every function
gets its own public HTTPS endpoint, and the pskit runtime routes requests to the right handler by path. Code Engine
functions have no event subscriptions in Terraform, so IBM supports **HTTP only**. Tier: **beta**.

| Item | Value |
|---|---|
| Terraform plugin | `IBM-Cloud/ibm >= 1.70` |
| Default region | `us-south` |
| Triggers | http only |
| Workflows | embedded orchestrator function (capped by its timeout) |
| Python | `python3.11` only (Code Engine `python-3.11`) |
| Node.js | `nodejs18`, `nodejs20` (`nodejs-18`, `nodejs-20`) |
| Max timeout | 120 s |
| Max memory | 4096 MB |
| Dependencies | `requirements.txt` is pip-installed into the zip by pskit |

## Set up IBM Cloud credentials step by step

The IBM Terraform plugin reads an API key from `IC_API_KEY`.

1. Sign in to cloud.ibm.com -> **Manage** -> **Access (IAM)** -> **API keys** -> **Create**. Copy the key (shown once).
2. Export it in the shell that runs `pskit`:

   ```bash
   export IC_API_KEY=<API key>
   ```

3. Optional: install the IBM Cloud CLI (`ibmcloud`) to look at projects and logs. `pskit doctor -p ibm` shows the
   install command for your OS.
4. Optional: find your resource group (**Manage** -> **Account** -> **Resource groups**) and, to reuse a project, its
   ID (**Code Engine** -> **Projects** -> project -> *ID*).

In studio: **Setup & credentials** -> **Provider** `ibm` -> **Environment variables** -> `IC_API_KEY` -> type the key ->
**Set for this session**.

## Configure the ibm provider block in pskit.yml

These are all the IBM options pskit reads:

```yaml
provider:
  name: ibm
  region: us-south
  runtime: python3.11
  options:
    resource_group: Default        # optional: Terraform provider resource group
    project_id: 1234abcd-...       # optional: an existing Code Engine project (else one is created)
    resource_group_id: abcd1234... # optional: resource group of the created project
    visibility: local_public       # optional: managed_domain_mappings for every function (default local_public)
    code_reference: icr.io/ns/bundle:tag   # optional: a code bundle image instead of the inline upload
functions:
  api:
    handler: app.api.handler
    concurrency: 50                # -> scale_concurrency
    options:
      visibility: local_private    # per function
      # any other ibm_code_engine_function argument
```

| Option | Meaning |
|---|---|
| `resource_group` | Set on the Terraform `ibm` provider block. |
| `project_id` | Use this Code Engine project; no `ibm_code_engine_project` is created. |
| `resource_group_id` | Resource group of the project pskit creates. |
| `visibility` | Sent as `managed_domain_mappings`. Code Engine values: `local_public` (default), `local_private`, `local`. Also per function in `functions.<fn>.options.visibility`. |
| `code_reference` | Code bundle image. Without it, the zip is uploaded inline as a base64 data URL (`code_binary: true`). |

Studio: **Overview & provider** -> **IBM Cloud Code Engine options** shows **Resource group**, **Resource group ID**,
**Code Engine project ID**, **Code reference** and **Visibility**. The **Visibility** list offers `public`, `private`
and `project`, which are not Code Engine values: leave it empty (default `local_public`) or set `visibility` on the
**YAML** page.

## Terraform resources pskit creates on IBM Cloud

| Resource | When |
|---|---|
| `ibm_code_engine_project` | unless `options.project_id` is set; named `<service>-<stage>` |
| `ibm_code_engine_function` | one per function, `code_main: main` |

Memory maps to fixed Code Engine sizes: up to 512 MB -> 0.125 vCPU / 0.5G, 1024 -> 0.25 / 1G, 2048 -> 0.5 / 2G,
4096 -> 1 / 4G. `timeout` becomes `scale_max_execution_time`. Environment variables are literal `run_env_variables`, so
they are stored in Terraform state.

## How triggers map to IBM Cloud services

| pskit trigger | IBM implementation |
|---|---|
| `http` | The function's own endpoint. All methods and paths reach the function; the pskit runtime matches `method` and `path` (and answers 404 / 405). Only `auth: none`. |
| `schedule`, `queue`, `storage`, `topic` | Not available (validation error). |

To run a scheduled job, call the endpoint from an outside scheduler, or drop the trigger for IBM only:

```yaml
providers:
  ibm:
    functions:
      ticker:
        events: []      # invoke-only on IBM
```

## Use resources on IBM Cloud

Managed `storage`, `queue` and `topic` resources cannot be created on IBM; create the service (Cloud Object Storage,
Event Streams, Databases, Secrets Manager) in the console and declare it with `external: true`. Guides:
[resource-guides/ibm/README.md](../../resource-guides/ibm/README.md).

## Run workflows on IBM Cloud

Each workflow runs on the embedded engine in a generated function `<workflow>-orchestrator`, reached at
`POST <its endpoint>/workflows/<name>`. The whole run must finish within 120 s. Start one with
`pskit workflow start <name> -p ibm`. See [deployment/workflows.md](../../deployment/workflows.md).

## Find IBM endpoints after deploy

`pskit info -p ibm` shows each function's `id`, its `url` (the Code Engine endpoint) and a console link to the
project's functions. Because every function has its own endpoint, a route `GET /hello` of function `api` is at
`<api url>/hello`. `invoke()` between functions needs the target's URL in `PSKIT_ENDPOINT_<NAME>` (see
[functions/invoke-and-test.md](../../functions/invoke-and-test.md)).

## Permissions on IBM Cloud

The API key's user needs IAM access to create Code Engine projects and functions in the resource group (or to
update the project given in `project_id`). Endpoints are public
with `local_public`; check tokens in your handler because `auth` must be `none`.

## Read logs of an IBM deployment

`pskit logs` and the studio **Logs** page cannot read Code Engine logs yet; they say so and point at the console link.
Open the `console` link from `pskit info` (the project's functions page in the IBM Cloud console).

## IBM limits and gotchas

- HTTP only; max 120 s; max 4096 MB; Python 3.11 only.
- The bundle is uploaded inline as base64 inside Terraform: keep it small, or use `code_reference`.
- `auth` must be `none`.
- Environment values are stored in Terraform state; keep secrets in Secrets Manager.

## Deploy to IBM Cloud from the terminal

```bash
pskit doctor -p ibm
pskit validate -p ibm -s dev
pskit deploy -p ibm -s dev
pskit info -p ibm -s dev
pskit remove -p ibm -s dev --yes
```

## Deploy to IBM Cloud in studio

1. Run `pskit studio --open`.
2. **Overview & provider** -> click **IBM Cloud Code Engine**. If the dialog lists unsupported triggers, click
   **Switch & disable on IBM Cloud Code Engine** to keep them for the other clouds.
3. Set **Runtime** to `python3.11` (or leave the default) and fill **IBM Cloud Code Engine options**. Click **Save**.
4. **Setup & credentials** -> set `IC_API_KEY` -> **Set for this session**.
5. **Deploy** -> **Deploy** -> confirm. Then **Info** for the URLs. **Remove** destroys the stage.

## Minimal IBM Cloud example

```yaml
service: hello-ibm
provider:
  name: ibm
  region: us-south
  runtime: python3.11
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
```

## See also

- [Providers index](../README.md)
- [resource-guides/ibm/README.md](../../resource-guides/ibm/README.md)
- [triggers/http.md](../../triggers/http.md)
- [deployment/deploy-remove-info.md](../../deployment/deploy-remove-info.md)
