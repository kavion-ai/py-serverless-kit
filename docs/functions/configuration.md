# Function configuration

Search terms: memory, timeout, environment variables, env vars, runtime, python version, node version, concurrency, architecture, arm64, iam, permissions, role, tags, enabled, disable function, function options

Every key a pskit function accepts under `functions.<name>:` in `pskit.yml`, what it does on each cloud, and where
to set it in studio. Keys you leave out fall back to the `provider:` block.

## All per-function keys

The pskit function keys come from `FunctionConfig` in `config/schema.py`. Unknown keys are an error.

| Key | Type / default | Meaning |
|---|---|---|
| `handler` | string, required | `package.module.function` or `package.module:function` ([create.md](create.md#write-the-handler-path)) |
| `description` | string, `""` | free text, shown in studio and the dashboard |
| `enabled` | bool, `true` | `false` keeps the function in `pskit.yml` but skips it on deploy |
| `runtime` | `provider.runtime` | `python3.9` .. `python3.14`, or `nodejs18`, `nodejs20`, `nodejs22`, `nodejs24` (same language as the service) |
| `memory` | int MB, `provider.memory` (256) | 64 .. 32768 |
| `timeout` | int seconds, `provider.timeout` (30) | 1 .. 3600, and at most the cloud's limit |
| `environment` | map, `{}` | added on top of `provider.environment`; values become strings |
| `tags` | map, `{}` | added on top of `provider.tags` |
| `events` | list, `[]` | triggers ([../triggers/README.md](../triggers/README.md)) |
| `concurrency` | int >= 0 | reserved concurrency / maximum instances |
| `architecture` | `x86_64` or `arm64`, `provider.architecture` | CPU type |
| `iam` | `{statements: [...], role: ...}` | extra permissions, or an existing role |
| `options` | map, `{}` | provider-specific settings merged into the native resource |

```yaml
provider:
  name: aws
  runtime: python3.12
  memory: 256
  timeout: 30
  environment: {LOG_LEVEL: INFO}

functions:
  resize-image:
    handler: functions.resize_image.handler.main
    description: Makes thumbnails
    runtime: python3.13
    memory: 1024
    timeout: 120
    architecture: arm64
    concurrency: 5
    environment:
      THUMB_SIZE: "256"
      PSKIT_LOG_LEVEL: DEBUG
    tags: {team: media}
    iam:
      statements:
        - actions: [s3:GetObject, s3:PutObject]
          resources: ["arn:aws:s3:::media-bucket/*"]
    events:
      - storage: {bucket: media-bucket, prefix: uploads/}
```

## Set function settings in studio

The pskit studio function wizard holds every key. Open **Functions**, click the function name (or **+ Create
function**).

| Step | Fields | YAML |
|---|---|---|
| **1 Basics** | **Function name**, **Deploy**, **Description**, **Handler**, **Runtime**, **Memory (MB)**, **Timeout (s)**, **Architecture** (`inherit`, `x86_64`, `arm64`) | `handler`, `enabled`, `description`, `runtime`, `memory`, `timeout`, `architecture` |
| **2 Triggers** | trigger cards and forms | `events` |
| **3 Environment & permissions** | **Logging** (**Log level**, **Live logs**), **Environment variables**, **Concurrency & tags** (**Reserved concurrency / max instances**, **Tags**), **Permissions (IAM)** (**Existing role**, **+ Add statement**: **Effect**, **Actions**, **Resources**) | `environment.PSKIT_LOG_LEVEL`, `environment`, `concurrency`, `tags`, `iam` |
| **4 Review** | diff of `pskit.yml` | |

Empty **Runtime**, **Memory (MB)** and **Timeout (s)** show `inherit (<provider value>)`. **Timeout (s)** shows the
provider's maximum as help. Click **Apply changes**, then **Save** in the top bar.

The Functions list shows the effective values in the **Runtime** column (`runtime · memory MB · timeout s`):
bold values are set on the function, grey ones are inherited from `provider:`.

## Runtime per function

A pskit function's `runtime` overrides `provider.runtime` for that function only. A service is one language: a
Python service may mix `python3.11` and `python3.13`, a Node.js service may mix Node.js versions, but a Python
service cannot hold a Node.js function (`a service is either Python or Node.js`). Each cloud supports a subset;
`pskit validate` reports a runtime the target does not have.

| Provider | Python | Node.js |
|---|---|---|
| aws | 3.9 - 3.13 | 18, 20, 22 |
| azure | 3.9 - 3.12 | 18, 20, 22 |
| gcp | 3.9 - 3.13 | 18, 20, 22 |
| alibaba | 3.9, 3.10, 3.12 | 18, 20 |
| tencent | 3.9, 3.10 | 18 |
| huawei | 3.9, 3.10, 3.12 | 18 |
| oracle | 3.9, 3.11 | 18, 20 |
| ibm | 3.11 | 18, 20 |
| digitalocean | 3.9, 3.11 | 18 |
| cloudflare | 3.11 - 3.13 | 18, 20, 22 |
| onprem | 3.9 - 3.14 | 18, 20, 22, 24 |

`pskit providers --json` prints these lists (`runtimes`, `node_runtimes`, `max_timeout`) from the installed version.

## Memory and timeout limits per cloud

The pskit `memory` and `timeout` keys are checked against each cloud by `pskit validate`.

| Provider | Max `timeout` | Memory notes |
|---|---|---|
| aws | 900 s | Lambda memory |
| azure | 600 s | not set per function (one Function App) |
| gcp | 3600 s; 540 s for functions with queue / topic / storage triggers | `available_memory` |
| alibaba | 3600 s | |
| tencent | 900 s | 64, 128 or a multiple of 128 MB |
| huawei | 900 s | |
| oracle | 300 s | |
| ibm | 120 s | at most 4096 MB |
| digitalocean | 900 s | 128 - 1024 MB |
| cloudflare | 900 s | |
| onprem | 3600 s | reported as `ctx.memory_mb` |

Errors look like `timeout 1200s exceeds AWS Lambda max 900s`. On premises the timeout sets the deadline that
`ctx.remaining_time_ms()` counts down to, and the default queue visibility timeout (`max(30, 6 x timeout)`).

## Environment variables

A pskit function's `environment` is merged over `provider.environment` (the function wins). pskit also sets
`PSKIT_PROVIDER`, `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_REGION`, `PSKIT_FUNCTION`, `PSKIT_HANDLER` and the
`PSKIT_RESOURCE_<KEY>_*` variables of bound resources. Values are always strings (`null` becomes `""`).

```yaml
functions:
  report:
    handler: app.jobs.report
    environment:
      API_URL: https://api.example.com
      API_KEY: ${env:REPORT_API_KEY}     # read from your shell at deploy time
      PSKIT_LOG_LEVEL: WARNING           # what studio's "Log level" writes
      PSKIT_ENDPOINT_BILLING: https://.../billing   # where invoke("billing") posts (see invoke-and-test.md)
```

Notes:

- Azure: all functions share one Function App, so the variables are app-wide. `pskit validate` warns
  `environment X differs between functions` when two functions set different values.
- Locally (`pskit invoke`, `pskit dev`) a `.env` file (or `--env-file`) is loaded too.
- Use secrets through `${env:...}` or `get_secret()`, never as plain text in `pskit.yml`
  ([../handlers.md](../handlers.md#get_secret-secrets-on-every-provider)).

## Concurrency, architecture and tags

The pskit `concurrency` key maps to each cloud's limit. Where nothing is listed, the key is not used.

| Provider | `concurrency` becomes |
|---|---|
| aws | `reserved_concurrent_executions` (0 stops the function) |
| gcp | `max_instance_count` |
| alibaba | `instance_concurrency` |
| huawei | `concurrency_num` |
| ibm | `scale_concurrency` |

`architecture` is used per function by AWS (`x86_64` or `arm64` Lambda). Oracle uses `provider.architecture` for
the image and shape. On premises `provider.architecture` picks the wheels pip installs. Other clouds ignore it.

`tags` are merged over `provider.tags` and pskit's own `pskit-service`, `pskit-stage` and
`managed-by: py-serverless-kit` tags, on clouds whose resources take tags.

## Permissions (iam)

A pskit function's `iam` adds permissions to the role it runs as, or names an existing role.

```yaml
functions:
  billing:
    handler: app.billing.charge
    iam:
      statements:
        - effect: Allow                  # Allow (default) or Deny
          actions: [lambda:InvokeFunction]
          resources: ["*"]               # default ["*"]
      # role: arn:aws:iam::123456789012:role/existing-role
```

| Provider | `iam.statements` | `iam.role` |
|---|---|---|
| aws | a function with its own statements or role gets its own role (provider statements + its own); others share one role | used as the Lambda role |
| alibaba | ignored, with a warning | RAM role ARN |
| tencent | ignored (provider-level warning) | CAM role name |
| huawei | ignored (provider-level warning) | IAM agency name |
| gcp, azure | ignored (provider-level warning) | GCP: grant roles to `options.service_account` |
| others | not used | not used |

## Disable a function without deleting it

The pskit `enabled: false` key keeps a function in `pskit.yml` but leaves it out of the deploy. To skip it on one
cloud only, set it under `providers.<cloud>`:

```yaml
functions:
  gpu-job:
    handler: app.jobs.gpu
providers:
  cloudflare:
    functions:
      gpu-job: {enabled: false}       # deployed everywhere except Cloudflare
```

In studio the **Deploy** column of the Functions page (and **Deploy** in step 1) has **Enabled**, **Disabled on
<provider>** and **Disabled everywhere**. A workflow that calls a disabled function fails validation
(`disable the workflow too`); resources that list it drop it.

## Turn off one trigger on one cloud

A pskit trigger can be kept for other clouds but not created on the current one. In studio's **Triggers** step click
**Disable on <provider>** on the trigger (the badge **off on <provider>** appears). This writes the reduced list to
`providers.<cloud>.functions.<name>.events`. Lists are replaced, not merged, by `providers:` and `stages:`
overrides, so that list holds every trigger the cloud keeps.

## Provider-specific options

The pskit function `options:` map is merged into the native resource body as an escape hatch, for example AWS
`vpc_config` or `layers`. It is not portable: each cloud reads only its own keys.

| Provider | `functions.<name>.options` |
|---|---|
| aws, gcp, alibaba, tencent, huawei, oracle | merged into the function's Terraform resource |
| ibm | `visibility` (domain mapping, default `local_public`); the rest merged into the resource |
| cloudflare | `route` (needs `provider.options.zone_id`); the rest merged into the Worker script |
| digitalocean | merged into the function's `project.yml` entry |
| azure, onprem | not used |

Put options under `providers.<cloud>.functions.<name>.options` when you deploy the same project to several clouds.
Per-cloud detail: [../providers/README.md](../providers/README.md).

## See also

- [README.md](README.md)
- [create.md](create.md)
- [invoke-and-test.md](invoke-and-test.md)
- [../configuration.md](../configuration.md)
- [../deployment/stages.md](../deployment/stages.md)
- [../providers/README.md](../providers/README.md)
- [../studio-guide/functions.md](../studio-guide/functions.md)
