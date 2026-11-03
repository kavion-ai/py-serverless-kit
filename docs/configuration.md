# Configuration reference (`pskit.yml`)

pskit looks for `pskit.yml`, `pskit.yaml`, `serverless_kit.yml` or `serverless_kit.yaml` in the current directory. Pass `-c FILE` to use another file. Unknown keys are rejected, so typos fail fast.

```yaml
service: orders                 # required
provider:                       # required
  name: aws
  region: us-east-1
package: {...}
functions: {...}
workflows: {...}
hooks: {...}
custom: {...}                   # free-form values for ${self:custom.x}
providers: {...}                # per-cloud overrides (see below)
stages: {...}                   # per-stage overrides (see below)
extends: base.yml               # inherit another file (see below)
```

## Top level

| Key | Type | Default | Rules |
|---|---|---|---|
| `service` | string | — | 2–32 chars, lowercase letters, digits, `-`, starts with a letter |
| `provider` | mapping or string | — | `provider: aws` is shorthand for `provider: {name: aws}` |
| `package` | mapping | see [package](#package) | |
| `functions` | map name → [function](#functions) | `{}` | names: start with a letter, letters/digits/`-`/`_`, max 63 |
| `workflows` | map name → workflow | `{}` | see [workflows.md](workflows.md) |
| `resources` | map name → resource | `{}` | buckets, queues, topics, databases, caches, other services; see [resources](#resources) |
| `hooks` | map hook → list of shell commands | `{}` | see [hooks](#hooks) |
| `custom` | any mapping | `{}` | only for `${self:custom...}` |

## `provider`

| Key | Type | Default | Notes |
|---|---|---|---|
| `name` | `aws` \| `azure` \| `gcp` \| `alibaba` \| `oracle` \| `ibm` \| `digitalocean` \| `tencent` \| `huawei` \| `cloudflare` \| `onprem` | — | required (or `--provider`) |
| `region` | string | provider default | e.g. `us-east-1`, `europe-west1`, `eastus` |
| `stage` | string | `dev` | `[a-z][a-z0-9-]{0,15}`; overridden by `--stage` |
| `runtime` | `python3.9` … `python3.14` | see [default runtime](#default-runtime) | provider support varies |
| `memory` | int MB | `256` | 64–32768 |
| `timeout` | int seconds | `30` | 1–3600, and ≤ the provider's max |
| `architecture` | `x86_64` \| `arm64` | `x86_64` | used by AWS and for pip wheel selection |
| `environment` | map | `{}` | values are converted to strings |
| `tags` | map | `{}` | merged with `pskit-service`, `pskit-stage`, `managed-by` |
| `iam.statements` | list of `{effect, actions, resources}` | `[]` | AWS-style; `effect` defaults to `Allow`, `resources` to `["*"]`. Ignored (with a warning) on clouds that don't map it |
| `iam.role` | string | — | use an existing role / agency instead of creating one |
| `log_retention_days` | int or null | `14` | AWS CloudWatch log group retention |
| `options` | mapping | `{}` | provider-specific settings, see [providers.md](providers.md). On-premises: `deploy.method` is `local`, `ssh`, `scp` (same as `ssh`), or `docker`. Remote SSH copies one archive and waits for `/__pskit/health`. Remote Docker uses `deploy.host` and `deploy.pem` (a `.pem` key; `pskit deploy` asks when it is missing) and installs Docker on the server when it is absent. `python: bundle` ships an interpreter when the server has none. `placement` puts groups of functions on different servers ([placement](placement.md)); `balancer` puts the project on a shared load balancer by path ([load balancers](load-balancers.md)) |
| `state` | mapping | local state | see [state](#state-remote-terraform-backend) |
| `terraform` | mapping | | see [terraform](#terraform) |

### Default runtime

If you don't pin `provider.runtime`, pskit uses **python3.12** when the target cloud supports it. Otherwise it uses the newest supported version below 3.12: python3.11 on DigitalOcean, IBM and Oracle, python3.10 on Tencent. This is what makes "change only the provider" work. If you *do* pin a runtime the cloud lacks, `pskit validate` reports an error.

### State: remote Terraform backend

By default Terraform state lives in `.pskit/<provider>-<stage>/terraform.tfstate`, which is git-ignored. For teams and CI, use a remote backend:

```yaml
provider:
  state:
    backend: s3                      # any terraform backend type: s3, gcs, azurerm, http, remote, ...
    config:
      bucket: my-tf-state
      key: orders/${opt:stage}.tfstate
      region: us-east-1
      dynamodb_table: tf-locks
```

### `terraform`

| Key | Default | Notes |
|---|---|---|
| `binary` | autodetect `terraform`, then `tofu` | or env `PSKIT_TERRAFORM_BIN` |
| `required_version` | `>= 1.5.0` | written into `terraform { required_version }` |
| `provider_version` | provider's built-in constraint | e.g. `~> 5.70` for `hashicorp/aws` |
| `extra` | `{}` | raw Terraform JSON deep-merged into the generated config (see [escape hatches](#escape-hatches)) |

## `functions`

```yaml
functions:
  create-order:
    handler: app.orders.create      # package.module.function  (or package.module:function)
    description: Creates an order
    runtime: python3.12             # override provider.runtime
    memory: 512                     # MB, 64-32768
    timeout: 20                     # s, 1-3600
    architecture: arm64
    concurrency: 10                 # reserved concurrency / max instances where supported
    environment: {TABLE: orders}
    tags: {team: checkout}
    iam:
      statements:
        - {actions: ["dynamodb:PutItem"], resources: ["${tf:aws_dynamodb_table.orders.arn}"]}
    events:
      - http: POST /orders
    options: {}                     # merged into the provider's function resource (escape hatch)
```

| Key | Type | Default |
|---|---|---|
| `handler` | string, required | — |
| `description` | string | `""` |
| `enabled` | bool | `true`; `false` keeps the function in the file but skips it on deploy (workflows take `enabled` too) |
| `runtime`, `memory`, `timeout`, `architecture` | as provider | inherit from `provider` |
| `environment`, `tags` | map | `{}` (merged over provider-level) |
| `events` | list | `[]` (no events = invoke-only function) |
| `concurrency` | int ≥ 0 | — |
| `iam` | like `provider.iam` | statements are added to the provider-level ones; a dedicated role is created (AWS) |
| `options` | mapping | `{}` |

Event syntax is in [events.md](events.md). Deployed functions are named `<service>-<stage>-<function>`, lowercased, with invalid characters replaced and long names shortened with a stable hash.

Two functions can't declare the same `METHOD /path`.

## `resources`

Services the functions use, created by pskit (managed) or already existing (`external: true`). Every bound function gets `PSKIT_RESOURCE_<KEY>_*` variables, and handlers read them with `resource("key")`.

```yaml
resources:
  jobs: {type: queue}                       # managed
  uploads:
    type: storage
    external: true
    name: legacy-uploads-bucket             # existing bucket
  orders-db:
    type: database                          # database / cache / custom: always external
    external: true
    connection: {host: db.internal, port: 5432, password_env: ORDERS_DB_PASSWORD}
    functions: [api]                        # default: every user function
```

| Key | Default | |
|---|---|---|
| `type` | — | `storage`, `queue`, `topic`, `database`, `cache`, `custom` |
| `external` | `false` | pskit never creates or destroys an external resource |
| `name` | the key (or the tail of `connection.arn`) | native name |
| `connection` | `{}` | scalar values exposed to handlers |
| `functions` | all user functions | which functions get the binding |
| `options` | `{}` | provider-specific (on-prem `driver`, AWS queue settings) |

`queue`, `storage` and `topic` events can name a resource instead of a queue/bucket: `- queue: {resource: jobs}`. The event then uses the resource's native name and `existing: <external>`. Full reference: [resources.md](resources.md).

## `package`

| Key | Default | Notes |
|---|---|---|
| `source` | `.` | directory (relative to the config) whose files are bundled |
| `include` | `["**/*"]` | gitignore-style globs (`**` = any depth) |
| `exclude` | `[]` | added to the default excludes below |
| `requirements` | `requirements.txt` | lines naming `py-serverless-kit` are dropped (the runtime is vendored) |
| `pip_args` | `[]` | extra `pip install` flags when vendoring |
| `vendor` | provider default | `true` forces `pip install` into the bundle, `false` ships `requirements.txt` instead |

Always excluded: `.git/**`, `.hg/**`, `.pskit/**`, `.terraform/**`, `.venv/**`, `venv/**`, `env/**`, `**/__pycache__/**`, `**/*.pyc`, `**/*.pyo`, `.pytest_cache/**`, `.mypy_cache/**`, `.ruff_cache/**`, `.idea/**`, `.vscode/**`, `node_modules/**`, `tests/**`, `dist/**`, `build/**`, `*.egg-info/**`, `**/.DS_Store`, `.env`, `.env.*`, `**/*.tfstate`, `**/*.tfstate.*`, `pskit*.yml`, `pskit*.yaml`, `serverless_kit*.yml`.

Providers that build remotely (GCP, Azure, Oracle, Cloudflare) get a `requirements.txt` in the bundle. The others (AWS, Alibaba, IBM, DigitalOcean, Tencent, Huawei) get dependencies pip-installed into the zip as Linux (`manylinux2014`) wheels for the target runtime and architecture.

## `hooks`

```yaml
hooks:
  before_package: ["python scripts/gen_schema.py"]
  after_deploy:   ["python scripts/smoke_test.py"]
```

Allowed hooks: `before_package`, `after_package`, `before_deploy`, `after_deploy`, `before_remove`, `after_remove`. Commands run through the shell in the project root, with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and `PSKIT_WORK_DIR` set. A non-zero exit aborts the command.

## Overrides and layering

### `providers:`: per-cloud overrides

```yaml
provider:
  name: aws
  region: us-east-1
providers:
  gcp:
    region: europe-west1            # shorthand for provider.region
    options: {project: my-proj}     # shorthand for provider.options
  azure:
    region: westeurope
    functions:                      # any top-level key can be overridden too
      create-order: {memory: 1024}
```

The block for the active provider (`provider.name` or `--provider`) is deep-merged into the config. Inside a block, `ProviderConfig` keys (`region`, `stage`, `runtime`, `memory`, `timeout`, `architecture`, `environment`, `tags`, `iam`, `log_retention_days`, `options`, `state`, `terraform`) may be written directly as shorthand for `provider: {...}`.

#### Switch something off on one cloud

Not every cloud runs every trigger. Keep the function for the others and turn it (or one of its triggers) off only where it can't run:

```yaml
providers:
  cloudflare:
    functions:
      thumbnails: {enabled: false}          # not deployed to Cloudflare
      api: {events: [{http: GET /orders}]}  # on Cloudflare `api` gets only this trigger (lists replace)
    workflows:
      order-pipeline: {enabled: false}
```

Disabled functions and workflows are reported as warnings by `pskit validate`; a workflow that calls a disabled function is an error. Studio writes these overrides for you (Deploy page, provider switch, function wizard).

### `stages:`: per-stage overrides

```yaml
stages:
  prod:
    provider: {memory: 1024}
    functions:
      create-order: {concurrency: 50}
```

### `extends:`: inherit files

```yaml
# pskit.gcp.yml
extends: pskit.yml            # or a list: [base.yml, team.yml]
provider:
  name: gcp
  options: {project: my-proj}
```

Relative paths resolve from the extending file. Circular `extends` is an error.

### Precedence (later wins)

1. For each file in the `extends` chain, parents first:
   1. that file's own values;
   2. that file's `providers.<active provider>` block.

   So a child file's explicit values beat its parent's per-provider overrides.
2. `stages.<active stage>` (merged across all files; the child wins).
3. `stages.<active stage>.providers.<active provider>`, when that stage must differ for one target (for example a cloud state backend on `prod` and local state for `onprem`).
4. CLI flags: `--provider`, `--stage`, `--region`.

Dicts are deep-merged; lists are replaced, not appended.

## Variables

| Syntax | Resolves to |
|---|---|
| `${env:NAME}` | environment variable; error if unset |
| `${env:NAME, default}` | environment variable or `default` |
| `${opt:stage}` / `${opt:provider}` / `${opt:region}` | effective CLI values (`${opt:x, default}` allowed) |
| `${self:dotted.path}` | any value of the merged config, e.g. `${self:service}`, `${self:custom.table}` |
| `${file(path.json)}` | file content relative to the config: `.json` / `.yml` parsed, other files as stripped text |

When a value is exactly one variable, its type is kept (`memory: ${self:custom.mem}` stays an int). Variables can nest across passes; unresolved variables are reported together.

Two forms are **not** resolved by pskit and are passed through verbatim:

- `${tf:<terraform expression>}` becomes a live Terraform reference, e.g. `${tf:aws_dynamodb_table.orders.arn}` in an IAM statement or environment value. Every other `${` in user values is escaped, so Terraform never interprets it.
- Any other `${...}`, such as IAM policy variables like `${aws:username}`, stays literal.

Secrets: don't put them in YAML. Use `${env:...}` for CI-provided values, or reference a secret manager via `${tf:...}`. See [`examples/10-stages-and-config`](../examples/10-stages-and-config).

## Escape hatches

| Need | Use |
|---|---|
| Set an argument pskit doesn't model (VPC, layers, tracing…) | `functions.<fn>.options`: merged into the provider's function resource (e.g. `aws_lambda_function`) |
| Provider-level settings | `provider.options`: see [providers.md](providers.md) |
| Extra cloud resources (tables, buckets, alarms…) | `provider.terraform.extra`: raw Terraform JSON, deep-merged |
| Reference those resources | `${tf:...}` in `iam.statements`, `environment`, etc. |

```yaml
provider:
  name: aws
  terraform:
    extra:
      resource:
        aws_dynamodb_table:
          orders:
            name: orders-${opt:stage}
            billing_mode: PAY_PER_REQUEST
            hash_key: id
            attribute: [{name: id, type: S}]
functions:
  create-order:
    handler: app.orders.create
    environment:
      TABLE_NAME: ${tf:aws_dynamodb_table.orders.name}
    options:
      tracing_config: {mode: Active}
```

Full example: [`examples/11-custom-terraform`](../examples/11-custom-terraform).
