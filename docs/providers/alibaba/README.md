# Alibaba Cloud Function Compute provider (`alibaba`)

Search terms: alibaba, alibaba cloud, aliyun, function compute, fc 3.0, fcapp.run, oss trigger, mns topic, timer
trigger, ALICLOUD_ACCESS_KEY, ram role, cn-hangzhou, deploy to alibaba, alicloud

The `alibaba` provider deploys every pskit function as an Alibaba Cloud **Function Compute 3.0** function. pskit writes
Terraform JSON for the `aliyun/alicloud` plug-in (`>= 1.230.0`) and runs Terraform.

| Fact | Value |
|---|---|
| Tier | **beta** (validated with `terraform validate`; event formats follow the vendor documentation) |
| Default region | `cn-hangzhou` |
| Python runtimes | `python3.9`, `python3.10`, `python3.12` (default `python3.12`) |
| Node.js runtimes | `nodejs18`, `nodejs20` (handler `index.handler`) |
| Max timeout | 3600 s (the pskit config limit) |
| Triggers | `http`, `schedule`, `storage` (OSS), `topic` (MNS) |
| Not supported | `queue` events (validation error); native workflows |
| Workflows | embedded engine only |
| Dependencies | pip-installed into the zip (vendored) |

## Set up Alibaba Cloud credentials for pskit

The Alibaba provider uses the credentials the `alicloud` Terraform plug-in reads: an AccessKey pair in environment
variables, or an Alibaba Cloud CLI profile.

1. Create an AccessKey for a RAM user in the console (**RAM** → **Users** → the user → **Create AccessKey**). Prefer a
   RAM user with only the permissions the deploy needs over the root account key.
2. Set the variables in the shell that runs `pskit`:

```bash
export ALICLOUD_ACCESS_KEY=<AccessKey ID>
export ALICLOUD_SECRET_KEY=<AccessKey Secret>
export ALICLOUD_REGION=cn-shanghai            # optional default region
```

   PowerShell: `$env:ALICLOUD_ACCESS_KEY = "<id>"`, and so on.

3. Or use the Alibaba Cloud CLI (`aliyun configure`, stored in `~/.aliyun/config.json`) and set
   `provider.options.profile: <profile name>`.
4. Check:

```bash
pskit doctor -p alibaba
```

`pskit doctor` reports `ALICLOUD_ACCESS_KEY / ALICLOUD_SECRET_KEY set`, or the `~/.aliyun/config.json` file when a
profile is configured.

In studio: sidebar **Setup & credentials** → **Provider** **Alibaba Cloud Function Compute** → in **Environment
variables** type the values next to `ALICLOUD_ACCESS_KEY`, `ALICLOUD_SECRET_KEY` and `ALICLOUD_REGION` → **Set for this
session** → **Check again**.

## Write the Alibaba provider block in pskit.yml

The Alibaba `provider` block has one provider option, `profile`.

```yaml
provider:
  name: alibaba
  region: cn-shanghai                  # default cn-hangzhou
  stage: dev
  runtime: python3.12                  # python3.9 | python3.10 | python3.12 | nodejs18 | nodejs20
  memory: 512
  timeout: 60                          # max 3600
  environment:
    LOG_LEVEL: INFO
  options:
    profile: default                   # optional: Alibaba Cloud CLI profile with the credentials
  iam:
    role: acs:ram::1234567890123456:role/fc-runtime   # optional RAM role ARN the functions run as
```

| Key | Alibaba result |
|---|---|
| `options.profile` | `profile` in the Terraform `provider "alicloud"` block |
| `iam.role` (provider or function) | the function's `role` (a RAM role ARN) |
| `iam.statements` | ignored with a warning: not translated to RAM policies |
| `memory`, `timeout` | `memory_size`, `timeout` |
| `concurrency` | `instance_concurrency` |
| `environment` | `environment_variables` (per function) |
| `functions.<fn>.options` | merged as-is into `alicloud_fcv3_function`, for example `vpc_config`, `layers`, `log_config` |

In studio, **Overview & provider → Alibaba Cloud Function Compute options** shows **CLI profile**.

## What pskit creates on Alibaba Cloud

The Alibaba provider creates these Terraform resources:

| Resource | When | Notes |
|---|---|---|
| `alicloud_fcv3_function` | every function | name `<service>-<stage>-<function>`, handler `index.handler`, internet access on, code uploaded inline from `artifact.zip` |
| `alicloud_fcv3_trigger` (type `http`) | HTTP events | one anonymous trigger named `http` per function |
| `alicloud_fcv3_trigger` (type `timer`) | schedule events | one per schedule |
| `alicloud_oss_bucket` + `alicloud_fcv3_trigger` (type `oss`) | storage events | bucket skipped with `existing: true` |
| `alicloud_message_service_topic` + trigger (type `mns_topic`) | topic events | topic skipped with `existing: true` |
| `alicloud_ram_role` + `alicloud_ram_role_policy_attachment` | any storage or topic event | role `<service>-<stage>-triggers` trusted by OSS and MNS, with `AliyunFCInvocationAccess` |

Every trigger uses the `LATEST` qualifier. The code zip is sent inline (base64) in the function resource, so keep the
bundle small.

## Alibaba HTTP trigger: fcapp.run URL

An Alibaba `http` event gives the function one anonymous HTTP trigger with a public `fcapp.run` URL. All HTTP events of
the function share that trigger: its method list is the union of the events' methods (`ANY` = GET, POST, PUT, DELETE,
PATCH, HEAD, OPTIONS), plus `OPTIONS` when an event has `cors`. The pskit runtime routes paths and methods inside the
function.

- Each HTTP function has its **own** URL; `pskit info` shows it as `url`, and the service `endpoint` is the first one.
- A path `/hello` is called as `<function URL>/hello`.
- `auth` must be `none`. Any other value is a validation error: check tokens in the handler.

## Alibaba schedule trigger: timer

An Alibaba `schedule` event becomes a timer trigger.

| pskit key | Timer setting |
|---|---|
| `rate: 5 minutes` | `@every 5m` (`2 hours` → `@every 2h`, `1 day` → `@every 1d`) |
| `cron: "0 2 * * 1"` | `0 0 2 * * MON` (seconds added; weekday numbers become names) |
| `timezone` with `cron` | prefix `CRON_TZ=<zone>` when the zone is not `UTC` |
| `timezone` with `rate` | not used |
| `enabled` | `enable` |
| `input` | payload `{"__pskit": "schedule", "data": <input>}`; handlers see `event.data` |
| `name` | trigger name (default `timer-<n>`) |

## Alibaba storage trigger: OSS

An Alibaba `storage` event creates an OSS bucket (unless `existing: true`) and an OSS trigger.

- `events: [created]` → `oss:ObjectCreated:*`; `events: [deleted]` → `oss:ObjectRemoved:*`.
- `prefix` and `suffix` become the trigger's key filter.
- The trigger is built for the provider `region`: an existing bucket must be in that region.
- OSS invokes the function through the pskit trigger RAM role.

Test it by uploading a file in the OSS console, or `ossutil cp hello.txt oss://<bucket>/<key>` (`pskit trigger --list`
prints the command).

## Alibaba topic trigger: MNS

An Alibaba `topic` event creates an MNS (Simple Message Queue) topic (unless `existing: true`) and an `mns_topic`
trigger with `notifyContentFormat: JSON` and `notifyStrategy: BACKOFF_RETRY`.

- `filter: {tag: orders}` becomes the trigger's `filterTag`. Only a string `tag` is used; other filter keys are ignored.
- The trigger uses the pskit trigger RAM role and the account id read with the `alicloud_account` data source.

## Alibaba resources: managed and external

An Alibaba `resources:` entry works only where an event uses it, or as `external: true`.

| Case | What pskit does on Alibaba |
|---|---|
| managed `storage` / `topic` used by an event | the event creates the OSS bucket or MNS topic |
| managed `storage` / `queue` / `topic` that no event uses | validation error: create it in the console and set `external: true` |
| `external: true` used by an event | not created; pskit only adds the trigger |
| `database`, `cache`, `custom` | must be `external: true`; only `connection` values reach handlers |

Bound functions get `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL` and one variable per `connection` entry. No ARN
or URL is added. Console walkthroughs: [Alibaba resource guides](../../resource-guides/alibaba/README.md).

## Alibaba workflows: embedded engine

Alibaba has no native workflow engine in pskit, so every workflow runs on the embedded engine. pskit adds a function
`<workflow>-orchestrator` with an HTTP trigger and the route `POST /workflows/<workflow>`. It runs the states and
calls the task handlers in the same bundle, and the whole run must finish within the function timeout (3600 s at most).
`engine: native` is a validation error.

```bash
pskit workflow start order-pipeline -i '{"amount": 50}'   # POSTs to the orchestrator URL
```

Embedded runs keep no history: each response carries its `execution_id`. Set `options.http: false` on a workflow to
deploy the orchestrator without an HTTP trigger.

## Deploy to Alibaba Cloud from the terminal

Deploying to Alibaba runs `terraform init` and `terraform apply` in `.pskit/alibaba-<stage>/`.

```bash
pskit init my-api --provider alibaba      # use -t http or -t workflow: the events template has a queue
cd my-api
export ALICLOUD_ACCESS_KEY=... ALICLOUD_SECRET_KEY=...
pskit validate
pskit deploy -s dev                       # or --confirm
pskit info -s dev                         # fcapp.run URLs and console links
```

## Deploy to Alibaba Cloud from studio

Deploying to Alibaba from studio uses the credentials of the machine running studio.

1. Sidebar **Overview & provider** → **Provider** → click the **Alibaba Cloud Function Compute** card (marked
   **beta**). The dialog lists queue triggers and native workflows that won't run there; pick **Switch & disable on
   Alibaba Cloud Function Compute** to keep them for other clouds.
2. Pick the **Region** under **Defaults for every function**; fill **CLI profile** if you use one.
3. Click **Save**. Check **validate & deploy as** and the **stage** in the top bar.
4. Sidebar **Deploy** → **Validate** → **Plan** → **Deploy**. Then **Info**.

## Read Alibaba logs and test functions

`pskit logs` can't read Alibaba logs yet: it prints the function's console link
(`https://fcnext.console.aliyun.com/<region>/functions/<name>`). Configure logging for the function in the console, or
pass `log_config` through `functions.<fn>.options`.

`pskit trigger` sends HTTP requests to the function URLs. For OSS and MNS triggers, `pskit trigger --list` and the
studio **Test** page show the console steps and the `ossutil` command instead.

## Remove an Alibaba deployment

Removing an Alibaba stage runs `terraform destroy`.

```bash
pskit remove -s dev --yes
pskit remove -s dev --keep-resources       # keep OSS buckets and MNS topics
```

In studio: **Deploy** → set the remove switch → **Remove** → type `alibaba/<stage>`.

## Alibaba limits and gotchas

- No `queue` events. Use an MNS topic, or send to a queue with the SDK from a handler.
- HTTP `auth` must be `none`.
- `iam.statements` are not translated (warning); set `iam.role` to a RAM role ARN.
- No standalone managed resources: unused managed storage, queue or topic resources are validation errors.
- `pskit init -t events` or `-t full` writes a queue function, which fails validation on Alibaba.
- `timezone` is applied only to `cron` schedules.

## Complete minimal Alibaba example project

The minimal Alibaba project below has an HTTP function, a timer in Shanghai time and an OSS upload handler.

```yaml
service: hello-ali

provider:
  name: alibaba
  region: cn-shanghai
  stage: dev
  timeout: 15

functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello

  nightly:
    handler: app.handlers.nightly
    events:
      - schedule: {cron: "0 2 * * *", timezone: Asia/Shanghai, input: {report: daily}}

  on-upload:
    handler: app.handlers.on_upload
    events:
      - storage: {bucket: hello-ali-uploads-12345, suffix: .csv}
```

```python
from py_serverless_kit import Context, Event


def hello(event: Event, ctx: Context):
    return {"message": f"Hello, {event.http.query.get('name', 'world')}!", "provider": event.provider}


def nightly(event: Event, ctx: Context):
    ctx.logger.info("nightly run", extra={"input": event.data})
    return {"ok": True}


def on_upload(event: Event, ctx: Context):
    for record in event.records:
        ctx.logger.info("uploaded", extra={"bucket": record.bucket, "key": record.key})
```

```bash
pskit deploy -s dev
pskit info -s dev
pskit remove -s dev --yes
```

This config creates nine Terraform resources: three functions, three triggers, the OSS bucket, and the trigger RAM role
with its policy attachment. OSS bucket names are global: change `hello-ali-uploads-12345` to your own.

## See also

- [Alibaba resource guides](../../resource-guides/alibaba/README.md): console steps for OSS, MNS, ApsaraDB, Tair
- [providers.md](../../providers.md#alibaba-function-compute-30), [configuration.md](../../configuration.md)
- [events.md](../../events.md), [workflows.md](../../workflows.md#embedded-orchestrator)
- [Deploy, remove and info](../../deployment/deploy-remove-info.md), [Logs](../../deployment/logs.md)
- [All providers](../README.md), [Tencent](../tencent/README.md)
