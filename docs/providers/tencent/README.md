# Tencent Cloud SCF provider (`tencent`)

Search terms: tencent, tencent cloud, scf, serverless cloud function, api gateway, cos trigger, timer trigger,
TENCENTCLOUD_SECRET_ID, cam role, appid, ap-guangzhou, deploy to tencent, tencentcloud, tccli

The `tencent` provider deploys every pskit function as a Tencent Cloud **Serverless Cloud Function (SCF)**, with HTTP
served by **API Gateway**. pskit writes Terraform JSON for the `tencentcloudstack/tencentcloud` plug-in (`>= 1.81.0`)
and runs Terraform.

| Fact | Value |
|---|---|
| Tier | **beta** (validated with `terraform validate`; event formats follow the vendor documentation) |
| Default region | `ap-guangzhou` |
| Python runtimes | `python3.9`, `python3.10` (SCF `Python3.9` / `Python3.10`); default `python3.10` |
| Node.js runtimes | `nodejs18` (SCF `Nodejs18.15`, handler `index.main_handler`) |
| Max timeout | 900 s |
| Triggers | `http` (API Gateway), `schedule` (timer), `storage` (COS) |
| Not supported | `queue` and `topic` events (validation errors); native workflows |
| Workflows | embedded engine only |
| Dependencies | pip-installed into the zip (vendored) |

## Set up Tencent Cloud credentials for pskit

The Tencent provider uses the credentials the `tencentcloud` Terraform plug-in reads: a SecretId / SecretKey pair in
environment variables, or a TCCLI profile.

1. Create an API key in the console: **Cloud Access Management (CAM)** → **Access Key** → **API Key Management**.
   Better: a CAM sub-user with programmatic access and only the policies the deploy needs.
2. Set the variables in the shell that runs `pskit`:

```bash
export TENCENTCLOUD_SECRET_ID=<SecretId>
export TENCENTCLOUD_SECRET_KEY=<SecretKey>
export TENCENTCLOUD_REGION=ap-guangzhou       # optional default region
```

3. Or install TCCLI (`pip install tccli`), run `tccli configure`, and set `provider.options.profile: <profile>`.
4. Check:

```bash
pskit doctor -p tencent
```

In studio: sidebar **Setup & credentials** → **Provider** **Tencent Cloud SCF** → in **Environment variables** fill
`TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` and `TENCENTCLOUD_REGION` → **Set for this session** → **Check
again**.

## Write the Tencent provider block in pskit.yml

The Tencent `provider` block needs a runtime Tencent supports. `pskit init -p tencent` writes `runtime: python3.12`,
which SCF does not have: change it to `python3.10` (or remove the line to get the default).

```yaml
provider:
  name: tencent
  region: ap-guangzhou                 # default ap-guangzhou
  stage: dev
  runtime: python3.10                  # python3.9 | python3.10 | nodejs18
  memory: 256                          # 64, 128 or a multiple of 128 MB
  timeout: 30                          # max 900
  environment:
    LOG_LEVEL: INFO
  options:
    namespace: default                 # SCF namespace, default "default"
    profile: default                   # optional TCCLI profile
  iam:
    role: SCF_QcsRole                  # optional: existing CAM role name the functions run as
```

| Key | Tencent result |
|---|---|
| `options.namespace` | the SCF namespace of every function, and the `ns=` of console links |
| `options.profile` | `profile` in the Terraform `provider "tencentcloud"` block |
| `iam.role` (provider or function) | the function's `role` (an existing CAM role name) |
| `iam.statements` | ignored with a warning: not translated to CAM policies |
| `memory` / `timeout` | `mem_size` / `timeout` |
| `environment` | `environment` (per function) |
| `functions.<fn>.options` | merged as-is into `tencentcloud_scf_function`, for example `vpc_id`, `subnet_id`, `layers`, `cls_*` |

`concurrency` and `architecture` are not used. In studio, **Overview & provider → Tencent Cloud SCF options** shows
**SCF namespace** and **CLI profile**.

## What pskit creates on Tencent Cloud

The Tencent provider creates these Terraform resources:

| Resource | When | Notes |
|---|---|---|
| `tencentcloud_scf_function` | every function | name `<service>-<stage>-<function>` (a trailing `-` or `_` is removed), public network on, timer and COS triggers inline |
| `tencentcloud_scf_trigger_config` | a schedule with `input` or `enabled: false` | sets the timer's argument and on/off state |
| `tencentcloud_api_gateway_service` | any HTTP event | one service per pskit service, `http&https`, outer network |
| `tencentcloud_api_gateway_api` | each HTTP event | one API per route, SCF integration with integrated response |
| `tencentcloud_api_gateway_service_release` | any HTTP event | releases the service to the `release` environment |
| `tencentcloud_cos_bucket` | storage events | private bucket; skipped with `existing: true` |

SCF re-uploads code only when the zip **path** changes, so pskit copies each new artifact to
`.pskit/tencent-<stage>/artifact-<hash>.zip` and deletes older copies.

## Tencent HTTP trigger: API Gateway

A Tencent `http` event becomes one API Gateway API on the service, with `auth_type: NONE` and the SCF function as
backend (`$LATEST`, integrated response, timeout = the function timeout up to 1800 s).

- URL: `https://<service-subdomain>/release` plus your path, for example `https://<service-subdomain>/release/hello`.
  `<service-subdomain>` is the API Gateway service's outer sub-domain; `pskit info` shows the full URL as `base_url`
  and `endpoint`.
- Path parameters such as `/users/{id}` become required `PATH` request parameters.
- `{path+}` becomes a prefix route: `/files/{path+}` is published as `/files`.
- `method: PATCH` is a validation error: use `ANY`.
- `auth` must be `none`. `cors: true` (or a CORS mapping) turns on `enable_cors` for that API.

## Tencent schedule trigger: timer

A Tencent `schedule` event becomes a timer trigger with a 7-field cron (seconds first, year last).

| pskit key | Timer setting |
|---|---|
| `cron: "0 2 * * 1"` | `0 0 2 * * MON *` (weekday numbers become names) |
| `rate: 15 minutes` | converted to cron first: `0 */15 * * * * *` (a rate that does not divide 60 minutes or 24 hours is an error) |
| `input` | the timer's custom argument `{"__pskit": "schedule", "data": <input>}` |
| `enabled: false` | `enable: CLOSE` |
| `name` | trigger name (default `timer-<n>`) |
| `timezone` | **not applied**, and no warning is printed: write the cron in the timer's own time |

## Tencent storage trigger: COS

A Tencent `storage` event creates a COS bucket (unless `existing: true`) and a COS trigger per action.

- The bucket name must be `<name>-<APPID>`, for example `uploads-1250000000`; otherwise validation fails. Your APPID is
  in the console under the avatar menu → **Account Information**.
- `events: [created]` → `cos:ObjectCreated:*`; `events: [deleted]` → `cos:ObjectRemove:*`.
- `prefix` and `suffix` become the trigger filter.
- The trigger is named `<bucket>.cos.<region>.myqcloud.com`: an existing bucket must be in the provider region.

Test it by uploading in the COS console, or `coscli cp hello.txt cos://<bucket>/<key>`.

## Tencent resources: managed and external

A Tencent `resources:` entry of type `storage` works through a storage event; `queue` and `topic` resources can only be
external and used from the SDK.

| Case | What pskit does on Tencent |
|---|---|
| managed `storage` used by an event | the event creates the COS bucket |
| managed `storage` / `queue` / `topic` that no event uses | validation error: create it in the console and set `external: true` |
| `external: true` | not created; a storage event only adds the COS trigger |
| `database`, `cache`, `custom` | must be `external: true`; only `connection` values reach handlers |

Bound functions get `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL` and one variable per `connection` entry. Console
walkthroughs: [Tencent resource guides](../../resource-guides/tencent/README.md).

## Tencent workflows: embedded engine

Tencent has no native workflow engine in pskit, so every workflow runs on the embedded engine. pskit adds a function
`<workflow>-orchestrator` with the API Gateway route `POST /workflows/<workflow>`; it runs the states and calls the task
handlers in the same bundle. The whole run must finish within 900 s. `engine: native` is a validation error.

```bash
pskit workflow start order-pipeline -i '{"amount": 50}'   # POSTs to .../release/workflows/order-pipeline
```

## Deploy to Tencent Cloud from the terminal

Deploying to Tencent runs `terraform init` and `terraform apply` in `.pskit/tencent-<stage>/`.

```bash
pskit init my-api --provider tencent      # then set runtime: python3.10 in pskit.yml
cd my-api
export TENCENTCLOUD_SECRET_ID=... TENCENTCLOUD_SECRET_KEY=...
pskit validate
pskit deploy -s dev                       # or --confirm
pskit info -s dev
```

## Deploy to Tencent Cloud from studio

Deploying to Tencent from studio uses the credentials of the machine running studio.

1. Sidebar **Overview & provider** → **Provider** → click the **Tencent Cloud SCF** card (marked **beta**). The dialog
   lists queue and topic triggers and native workflows that won't run there; pick **Switch & disable on Tencent Cloud
   SCF** to keep them for other clouds. When the runtime is not supported, studio clears it so the default applies.
2. Under **Defaults for every function**, check **Runtime** (python3.9 or python3.10) and **Memory (MB)** (64, 128 or a
   multiple of 128).
3. Click **Save**. Check **validate & deploy as** and the **stage** in the top bar.
4. Sidebar **Deploy** → **Validate** → **Plan** → **Deploy**. Then **Info**.

## Read Tencent logs and test functions

`pskit logs` can't read Tencent logs yet: it prints the function's console link
(`https://console.cloud.tencent.com/scf/list-detail?ns=<namespace>&id=<name>`). Send logs to CLS with the `cls_*`
arguments through `functions.<fn>.options`.

`pskit trigger` sends HTTP requests to the API Gateway URL. For timers and direct invokes, `pskit trigger --list` prints
a `tccli scf Invoke` command; for COS it prints the console steps and a `coscli` command.

## Remove a Tencent deployment

Removing a Tencent stage runs `terraform destroy`.

```bash
pskit remove -s dev --yes
pskit remove -s dev --keep-resources       # keep COS buckets
```

In studio: **Deploy** → set the remove switch → **Remove** → type `tencent/<stage>`.

## Tencent limits and gotchas

- No `queue` or `topic` events.
- HTTP `auth` must be `none`; no `PATCH`; `{path+}` is a prefix route.
- Memory must be 64, 128 or a multiple of 128 MB.
- Only python3.9 and python3.10. `pskit init` writes python3.12: change it.
- Schedule `timezone` is silently ignored.
- `iam.statements` are not translated (warning): set `iam.role` to a CAM role name.
- COS bucket names need the `-<APPID>` suffix.

## Complete minimal Tencent example project

The minimal Tencent project below has an HTTP function behind API Gateway, a timer and a COS upload handler.

```yaml
service: hello-tc

provider:
  name: tencent
  region: ap-guangzhou
  stage: dev
  runtime: python3.10
  memory: 256
  timeout: 15
  options:
    namespace: default

functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello

  nightly:
    handler: app.handlers.nightly
    events:
      - schedule: {cron: "0 2 * * *", input: {report: daily}}

  on-upload:
    handler: app.handlers.on_upload
    events:
      - storage: {bucket: hello-tc-uploads-1250000000, suffix: .csv}
```

Use the same `app/handlers.py` as the [Alibaba example](../alibaba/README.md#complete-minimal-alibaba-example-project);
replace `1250000000` with your APPID.

```bash
pskit deploy -s dev
pskit info -s dev                          # https://<subdomain>/release/hello
pskit remove -s dev --yes
```

This config creates eight Terraform resources: three SCF functions, one trigger config (the timer's input), the API
Gateway service, its API and release, and the COS bucket.

## See also

- [Tencent resource guides](../../resource-guides/tencent/README.md): console steps for COS, TDMQ, TencentDB
- [providers.md](../../providers.md#tencent-serverless-cloud-function-scf), [configuration.md](../../configuration.md)
- [events.md](../../events.md), [workflows.md](../../workflows.md#embedded-orchestrator)
- [Deploy, remove and info](../../deployment/deploy-remove-info.md), [Logs](../../deployment/logs.md)
- [All providers](../README.md), [Alibaba](../alibaba/README.md)
