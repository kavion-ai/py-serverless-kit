# Huawei Cloud FunctionGraph provider

Search terms: huawei, huawei cloud, FunctionGraph, APIG, dedicated API Gateway, apig_instance_id, OBS, SMN, agency,
HW_ACCESS_KEY, HW_SECRET_KEY, cn-north-4, huaweicloud terraform

The Huawei Cloud provider (`provider.name: huawei`) deploys each function as a **FunctionGraph** function. HTTP routes
go through a **dedicated API Gateway (APIG)** instance that you create first. Tier: **beta** (passes
`terraform validate`; event formats follow Huawei's documentation).

| Item | Value |
|---|---|
| Terraform plugin | `huaweicloud/huaweicloud >= 1.60.0` |
| Default region | `cn-north-4` |
| Triggers | http, schedule, storage (OBS), topic (SMN). No queue trigger. |
| Workflows | embedded orchestrator function (capped by its timeout) |
| Python | `python3.9`, `python3.10`, `python3.12` (default `python3.12`) |
| Node.js | `nodejs18` (FunctionGraph `Node.js18.15`) |
| Max timeout | 900 s |
| Dependencies | `requirements.txt` is pip-installed into the zip by pskit |

## Set up Huawei Cloud credentials step by step

The Huawei Terraform plugin reads an access key pair from environment variables.

1. Sign in to the Huawei Cloud console. Click your account name (top right) -> **My Credentials** -> **Access Keys**.
2. Click **Create Access Key** and download the CSV (it is shown once).
3. Export the keys in the shell that runs `pskit` (or `pskit studio`):

   ```bash
   export HW_ACCESS_KEY=<access key>
   export HW_SECRET_KEY=<secret key>
   export HW_REGION_NAME=cn-north-4
   ```

   On Windows PowerShell: `$env:HW_ACCESS_KEY = "<access key>"`, and so on.
4. If you use HTTP triggers, create a dedicated gateway: console -> **API Gateway** -> **Dedicated Gateways** ->
   **Buy Gateway** in the same region. Copy its **instance ID** (32 hex characters).
5. Check the machine: `pskit doctor -p huawei`. It looks for Terraform, the KooCLI (`hcloud`, optional) and the
   variables above.

In studio, open **Setup & credentials**, pick **Provider** `huawei`, and in **Environment variables** type each value
and click **Set for this session** (kept until studio stops; nothing is written to disk).

## Configure the huawei provider block in pskit.yml

These are all the Huawei options pskit reads:

```yaml
provider:
  name: huawei
  region: cn-north-4
  options:
    apig_instance_id: 0123456789abcdef0123456789abcdef   # required when any function has an http event
    app: default                  # FunctionGraph application (default "default")
    enterprise_project_id: "0"    # optional, passed to the Terraform provider block
    profile: my-profile           # optional, passed to the Terraform provider block
  iam:
    role: my-functiongraph-agency # IAM agency name for every function
functions:
  api:
    handler: app.api.handler
    iam:
      role: other-agency          # per-function agency (wins over provider.iam.role)
    concurrency: 10               # -> concurrency_num
    options:                      # merged into huaweicloud_fgs_function
      vpc_id: <vpc id>
      network_id: <subnet id>
```

| Option | Required | Meaning |
|---|---|---|
| `options.apig_instance_id` | for http | Dedicated APIG instance. Without it, any http event is a validation error. |
| `options.app` | no | FunctionGraph app name. Default `default`. |
| `options.enterprise_project_id` | no | Enterprise project, set on the Terraform provider. |
| `options.profile` | no | Profile for the Terraform provider instead of the environment keys. |
| `iam.role` | no | Agency the functions run as. `iam.statements` are ignored (warning). |
| `functions.<fn>.options` | no | Any `huaweicloud_fgs_function` argument (`vpc_id`, `network_id`, `depend_list`, ...). |

Studio: **Overview & provider** -> **Huawei Cloud FunctionGraph options** shows **FunctionGraph app** and **APIG
instance ID**. Set `enterprise_project_id` and `profile` on the **YAML** page.

## Terraform resources pskit creates on Huawei Cloud

| Resource | When |
|---|---|
| `huaweicloud_fgs_function` | one per function (zip uploaded inline, handler `index.handler`) |
| `huaweicloud_apig_group`, `huaweicloud_apig_environment` (`pskit_<stage>`), data `huaweicloud_apig_groups` | once, when any http event exists |
| `huaweicloud_apig_api` + `huaweicloud_apig_api_publishment` | one per http event |
| `huaweicloud_fgs_trigger` type `TIMER` | one per schedule |
| `huaweicloud_obs_bucket` (private) + `huaweicloud_fgs_trigger` type `OBS` | per storage event (no bucket when `existing: true`) |
| `huaweicloud_smn_topic` (or data `huaweicloud_smn_topics` when `existing: true`) + trigger type `SMN` | per topic event |

Environment variables (yours plus `PSKIT_*` and resource bindings) are written to the function's `user_data` as JSON,
so they are visible in the console and stored in Terraform state. Names are `<service>-<stage>-<function>`, lowercase,
max 60 characters; a name that does not start with a letter gets an `f` prefix.

## How triggers map to Huawei Cloud services

| pskit trigger | Huawei Cloud implementation |
|---|---|
| `http` | APIG API in the pskit group, published to environment `pskit_<stage>`. `auth: none / iam / key` -> `NONE` / `IAM` / `APP`. `cors: true` turns on APIG CORS. `{path+}` becomes a prefix-match route. Path parameters `{id}` are passed through. Backend timeout = function timeout (max 600 s). |
| `schedule` | Timer trigger. `rate: 5 minutes` -> `Rate` `5m`. `cron` -> 6-field cron with seconds and `?` (weekday numbers become `SUN`..`SAT`). `enabled: false` -> trigger `DISABLED`. `input` reaches the handler as `event.data`. |
| `storage` | OBS trigger on `created` (`ObjectCreated`) and `deleted` (`ObjectRemoved`), with `prefix` / `suffix`. |
| `topic` | SMN trigger on the topic. |
| `queue` | Not available (validation error). Use a queue from the handler through the SDK. |

pskit does not apply a schedule `timezone` or a topic `filter` on Huawei and does not warn about them; filter in the
handler. Details per trigger: [triggers/README.md](../../triggers/README.md).

## Use resources on Huawei Cloud

On Huawei, a managed `storage` or `topic` resource must be used by a trigger; a managed resource that no event uses is
a validation error. Create other services (RDS, DCS, DMS, CSMS) in the console and declare them with `external: true`.
They reach handlers as `PSKIT_RESOURCE_<KEY>_*` variables. Step-by-step guides:
[resource-guides/huawei/README.md](../../resource-guides/huawei/README.md).

## Run workflows on Huawei Cloud

Huawei has no native workflow engine in pskit, so each workflow runs on the embedded engine inside a generated
function `<workflow>-orchestrator`. That function gets an HTTP route `POST /workflows/<name>` on the APIG group
(turn it off with `workflows.<name>.options.http: false`). Validation warns that the whole run must finish within the
orchestrator's timeout (max 900 s). Start a run:

```bash
pskit workflow start order -i '{"id": 1}' -p huawei
```

The response carries the `execution_id`; there is no browsable execution history on a cloud function. See
[deployment/workflows.md](../../deployment/workflows.md).

## Find Huawei endpoints after deploy

`pskit info -p huawei` shows each function's `id` (its name), `arn` (its URN), the APIG `base_url`
(`https://<group subdomain>`) and a console link. HTTP routes are `<base_url><path>`. The deployment `endpoint` is the
same group URL.

## Permissions on Huawei Cloud

- The deploying user needs rights for FunctionGraph, APIG, OBS and SMN in the region.
- Functions get cloud permissions through an **agency** in `iam.role`: **Identity and Access Management** ->
  **Agencies** -> **Create Agency** -> *Cloud service* -> **FunctionGraph**, then attach the policies the code needs.
- `auth: iam` and `auth: key` on an http event are enforced by APIG (IAM or APP authentication).

## Read logs of a Huawei deployment

`pskit logs` cannot read FunctionGraph logs yet; it prints *pskit can't read Huawei Cloud FunctionGraph logs yet. Open
the function's console link instead.* Use the `console` link from `pskit info` (FunctionGraph -> function ->
**Monitoring** -> **Logs**). The studio **Logs** page shows the same message. See
[deployment/logs.md](../../deployment/logs.md).

## Huawei limits and gotchas

- No queue trigger. HTTP needs a dedicated APIG instance (shared gateways are not used).
- `iam.statements` are ignored; use an agency.
- Environment values are stored in `user_data` and in Terraform state: keep real secrets in CSMS.
- `{path+}` becomes a prefix route on APIG; the pskit runtime still matches the full path.
- Functions reach RDS / DCS private addresses only with `vpc_id` and `network_id` in `functions.<fn>.options`.

## Deploy to Huawei Cloud from the terminal

```bash
pskit doctor -p huawei              # tools and credentials
pskit validate -p huawei -s dev     # APIG id, auth values, unsupported triggers
pskit deploy -p huawei -s dev       # package + terraform apply
pskit info -p huawei -s dev         # URLs and ids
pskit remove -p huawei -s dev --yes # destroy the stage
```

`pskit plan` shows the Terraform plan first; `pskit deploy --confirm` asks before applying. `pskit remove
--keep-resources` keeps managed buckets and topics. See [deployment/deploy-remove-info.md](../../deployment/deploy-remove-info.md).

## Deploy to Huawei Cloud in studio

1. Run `pskit studio --open`.
2. **Overview & provider** -> **Provider** -> click the **Huawei Cloud FunctionGraph** card -> confirm the switch.
3. In **Huawei Cloud FunctionGraph options**, set **APIG instance ID** (and **FunctionGraph app** if not `default`).
4. Click **Save** in the top bar.
5. **Setup & credentials** -> set `HW_ACCESS_KEY`, `HW_SECRET_KEY`, `HW_REGION_NAME` -> **Set for this session**.
6. **Deploy** -> check the top bar says `huawei` and your stage -> click **Deploy** -> confirm. The job log streams
   below the action cards.
7. Click **Info** to see URLs. To destroy, click **Remove** and type `huawei/<stage>` in the dialog.

## Minimal Huawei Cloud example

```yaml
service: hello-hw
provider:
  name: huawei
  region: cn-north-4
  options:
    apig_instance_id: ${env:HUAWEI_APIG_INSTANCE_ID}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
      - schedule: {rate: 1 hour, input: {source: timer}}
```

```python
from py_serverless_kit import Context, Event


def hello(event: Event, ctx: Context):
    if event.http is None:          # the timer
        return {"tick": event.data}
    return {"message": "Hello from FunctionGraph", "provider": event.provider}
```

## See also

- [Providers index](../README.md)
- [resource-guides/huawei/README.md](../../resource-guides/huawei/README.md)
- [triggers/README.md](../../triggers/README.md)
- [deployment/workflows.md](../../deployment/workflows.md)
- [studio-guide/README.md](../../studio-guide/README.md)
