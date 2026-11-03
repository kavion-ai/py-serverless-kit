# Concepts and glossary

Search terms: glossary, concepts, terms, what is a service, function, handler, trigger, event, resource, stage, provider, workflow, deployment, binding, on-prem, cluster

This page explains every word pskit uses, in the order you meet them. Each entry says where it lives in `pskit.yml`
(the keys come from `src/py_serverless_kit/config/schema.py`) and links to the page with the details.

## Project, service and pskit.yml

A **pskit project** is a folder with a `pskit.yml` file, your handler code (for example `app/*.py`) and a
`requirements.txt`. `pskit init` or the studio's *Create a pskit project* screen creates one.

A **service** is the name of the project inside `pskit.yml` (`service: orders`). It is 2 to 32 lowercase letters,
digits and dashes. pskit uses it to name every cloud resource: `orders-dev-create-order`, and so on.

**`pskit.yml`** describes the whole service. Its top-level keys are:

| Key | What it holds |
|---|---|
| `service` | the service name |
| `provider` | the target cloud and the defaults for every function |
| `package` | what goes into the deployment bundle |
| `functions` | the functions and their triggers |
| `workflows` | state machines that chain functions |
| `resources` | buckets, queues, topics, databases, caches and other services |
| `hooks` | shell commands run before / after package, deploy and remove |
| `custom` | free values you reuse with `${self:custom.x}` |
| `providers` | per-provider overrides of any key above |
| `stages` | per-stage overrides of any key above |
| `extends` | a parent file deep-merged first |

Full reference: [configuration.md](../configuration.md).

## Function and handler

A **function** is one deployable unit: a handler plus the triggers that call it. It lives under
`functions.<name>` (name: a letter, then letters, digits, `-` or `_`).

The **handler** is the Python function that runs, written as `package.module.function` (or `module:function`),
relative to `package.source`. `handler: app.api.create_order` means `create_order()` in `app/api.py`. It takes
`(event, ctx)` and returns a value pskit converts to the platform's response.

Per-function settings override the provider defaults: `runtime`, `memory` (MB), `timeout` (seconds),
`environment`, `tags`, `concurrency`, `architecture`, `iam`, `options` and `enabled` (`false` keeps it in the
file but skips it on deploy). See [functions/configuration.md](../functions/configuration.md) and
[handlers.md](../handlers.md).

A function **without triggers** is *invoke-only*: other code calls it with `invoke()`, or a workflow runs it.

## Event, trigger, Event object and Context

A **trigger** (also called an **event** in `pskit.yml`) is what makes a function run. It is written as a one-key
mapping in the function's `events:` list. pskit has six types:

| Type | Runs the function when | Example |
|---|---|---|
| `http` | an HTTP request hits a route | `- http: GET /orders/{id}` |
| `schedule` | a timer fires (`rate` or 5-field `cron`) | `- schedule: {cron: "0 2 * * *"}` |
| `queue` | messages wait in a queue (batches) | `- queue: {resource: order-jobs}` |
| `storage` | a file is created or deleted in a bucket | `- storage: {resource: receipts}` |
| `topic` | a message is published to a topic (fan-out) | `- topic: {resource: order-events}` |
| `smtp` | mail arrives at an on-prem SMTP server | `- smtp: inbound-mail` |

Inside the handler, the **`Event`** object is the same on every cloud: `event.type`, `event.http` (method, path,
`path_params`, `query`, `json()`), `event.records` (queue, topic and storage batches) and `event.data` (schedule
input, workflow data, invoke payload). The **`Context`** object has `request_id`, `function`, `stage`,
`provider`, `ctx.logger` and `remaining_time_ms()`. Trigger pages: [triggers/README.md](../triggers/README.md).

## Resource, managed or external, and binding

A **resource** is a service your functions use, declared once under `resources.<key>`. Its `type` is `storage`,
`queue`, `topic`, `database`, `cache`, `custom` or `smtp`.

- **Managed** (default for `storage`, `queue`, `topic`): pskit creates it on deploy and deletes it on remove
  (unless you pass `--keep-resources`).
- **External** (`external: true`): it already exists or runs elsewhere. pskit never creates or deletes it and only
  hands its details to the handlers. `database`, `cache` and `custom` must be external.

A **binding** is how a function sees a resource. Each bound function gets `PSKIT_RESOURCES` and
`PSKIT_RESOURCE_<KEY>_*` environment variables (`TYPE`, `NAME`, `EXTERNAL`, one per `connection:` entry, plus
`ARN` / `URL` / `ID` when the provider knows them). In code, `resource("orders-db")` reads them back.
`functions: [a, b]` on a resource limits the binding to those functions; without it every function is bound.

`connection:` holds scalar values for the handlers (host, port, `url_env`, `password_env`). Never put a password
there; put the *name* of an environment variable that holds it. See [resources.md](../resources.md).

## Provider, region, tier and options

The **provider** is the target platform: `aws`, `azure`, `gcp`, `alibaba`, `oracle`, `ibm`, `digitalocean`,
`tencent`, `huawei`, `cloudflare` or `onprem`. It is set in `provider.name` and can be overridden on the command
line with `-p`. `provider.region` is the cloud region (`--region` overrides it).

Each provider has a **tier**: `stable`, `beta` or `experimental` (`pskit providers` lists them with the triggers
each one supports). Settings that only one cloud understands go under `options:` (on the provider, a function, a
resource or a workflow); the other providers ignore them.

`providers.<name>:` in `pskit.yml` overrides any top-level key when that provider is selected, so one file can
target several clouds. See [providers/README.md](../providers/README.md) and [providers.md](../providers.md).

## Stage

A **stage** is one independent copy of the service: `dev`, `staging`, `prod` (lowercase, up to 16 characters).
`provider.stage` is the default; `-s prod` picks another. Each provider + stage pair has its own build folder
and Terraform state in `.pskit/<provider>-<stage>/`, so deploying `prod` never touches `dev`.

`stages.<name>:` overrides any key for that stage only (memory, environment, region, a remote state backend).
`${opt:stage}` puts the stage name into a value. See [deployment/stages.md](../deployment/stages.md).

## Variables

Values in `pskit.yml` can contain variables, resolved when the file is loaded:

| Variable | Value |
|---|---|
| `${env:NAME}` / `${env:NAME, default}` | an environment variable |
| `${opt:stage}`, `${opt:region}`, `${opt:provider}` | the effective command-line values |
| `${self:custom.receipts_bucket}` | any value in the merged file |
| `${file(config/limits.json)}` | the content of a JSON, YAML or text file |
| `${tf:aws_dynamodb_table.orders.arn}` | left for Terraform to resolve |

## Workflow, state and engine

A **workflow** is a state machine that chains functions, under `workflows.<name>`. It has `start_at` and
`states`. Each **state** has a `type`:

| Type | Does |
|---|---|
| `task` | runs a function (`function:`), with optional `retry` and `catch` |
| `choice` | picks the next state from rules (`choices`, `default`) |
| `wait` | waits `seconds` (or `seconds_path`) |
| `pass` | passes data on, or injects a `result` |
| `parallel` | runs `branches` at the same time |
| `map` | runs an `iterator` for every item of `items_path` |
| `succeed` / `fail` | ends the run (`fail` with `error` and `cause`) |

The **engine** runs it: `native` compiles it to AWS Step Functions, Google Cloud Workflows (or Azure Logic Apps
when asked); `embedded` runs it in pskit's own engine inside a generated `<workflow>-orchestrator` function.
`engine: auto` (default) picks native where the provider has one. An **execution** is one run, with an id,
status and history. See [deployment/workflows.md](../deployment/workflows.md) and [workflows.md](../workflows.md).

## Package, artifact, Terraform and deployment

**Packaging** builds the **artifact**: a reproducible `artifact.zip` with your code, the dependencies from
`requirements.txt`, pskit's runtime and a manifest. `package:` controls it (`source`, `include`, `exclude`,
`requirements`, `pip_args`, `vendor`).

pskit then writes **Terraform** JSON (`main.tf.json`) for the provider and runs `terraform` (or `tofu`). It never
calls cloud APIs itself. `provider.state` sets a remote Terraform backend; `provider.terraform` picks the binary
and can merge raw Terraform (`extra`).

A **deployment** is what `pskit deploy` leaves running for one provider and stage. `pskit info` shows it from the
Terraform output named `pskit` (functions, URLs, ids, console links); `deployment.json` and the dashboard read the
same data. `pskit remove` destroys it. See [deployment/README.md](../deployment/README.md) and
[deployment/deploy-remove-info.md](../deployment/deploy-remove-info.md).

## Hooks, IAM and secrets

**Hooks** are shell commands in `hooks:` run at `before_package`, `after_package`, `before_deploy`,
`after_deploy`, `before_remove` and `after_remove`, with `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER` and
`PSKIT_WORK_DIR` set. A failing hook stops the command.

**IAM** (`iam:` on the provider or a function) adds permission `statements` (`effect`, `actions`, `resources`)
to the role pskit creates, or names an existing `role`. Bound resources get their permissions automatically on
AWS.

**Secrets** are read with `get_secret("name")` in handlers. The store (environment, Vault / OpenBao, AWS Secrets
Manager) comes from environment variables, so the code does not change. See [handlers.md](../handlers.md).

## Local runs: dev, invoke, test

- **`pskit dev`**: a local HTTP server with hot reload on port 3000 that routes requests to your handlers.
- **`pskit invoke`**: runs one function on this machine with a synthetic event (`-t http|queue|...`).
- **`pskit workflow run`**: runs a workflow on the embedded engine locally.
- **`LocalRunner`**: the same from `pytest`.

Locally `PSKIT_PROVIDER` is `local` and `.env` is loaded. See
[functions/invoke-and-test.md](../functions/invoke-and-test.md) and [local-development.md](../local-development.md).

## Studio, Hana and the dashboard

- **pskit studio** (`pskit studio --open`): a web UI on your machine that edits `pskit.yml`, handler code, on-prem
  servers, services, clusters and load balancers, and runs validate, deploy, test and logs. Changes are a
  **draft** until you click **Save**. See [studio-guide/README.md](../studio-guide/README.md).
- **Hana**: the AI assistant inside studio (**Ask Hana**, or Ctrl+I). She answers questions and changes the
  project after you approve a plan. See [assistant.md](../assistant.md).
- **Dashboard** (`pskit dashboard --open`, or `--serve` for live logs and workflow executions): a page that shows
  what is deployed. See [deployment/monitoring-and-dashboard.md](../deployment/monitoring-and-dashboard.md).

## On-premises terms

| Term | Meaning |
|---|---|
| **host** | the pskit process that runs your functions on a machine (`provider.name: onprem`), with built-in schedule, queue, storage, topic and workflow services |
| **saved server** | an SSH machine saved once by name (`pskit resources onprem servers add`); used to deploy, create services and build clusters |
| **deploy method** | `provider.options.deploy.method`: `local` (this machine), `ssh` or `docker` |
| **on-prem service** | a Docker container pskit starts from its catalog (PostgreSQL, Redis, MinIO, Kafka, ...) and adds as a resource |
| **runtime install** | software from the catalog installed on a server (Docker, Python, Node.js, nginx, ...) |
| **driver** | `resources.<key>.options.driver` (`redis`, `minio`, `s3`, `sqs`, ...): how the host reaches a queue, bucket or topic |
| **env file** | `.env.onprem` (or `provider.options.env_file`): generated passwords and URLs, copied next to the host, never in `pskit.yml` |
| **admin token** | `provider.options.admin_token`: protects the host's `/__pskit/*` admin API |
| **placement** | `provider.options.placement`: groups of functions on different servers ([placement.md](../placement.md)) |
| **scaling cluster** | a master plus joined servers running Docker Swarm, Kubernetes (k3s) or Nomad ([cluster.md](../cluster.md)) |
| **master / joined server** | the cluster's control plane and main replica / extra servers that run web replicas |
| **web replicas** | copies of the HTTP part behind the load balancer (`options.cluster.replicas`) |
| **load balancer** | OpenResty (nginx) on a saved server; one URL for clusters and projects, by path ([load-balancers.md](../load-balancers.md)) |
| **algorithm** | how a load balancer picks a server: round robin, sticky, weighted, IP hash, least connections, least time |
| **replicated database** | a primary that takes writes plus read replicas, optionally behind pgpool-II or ProxySQL |
| **network map / firewall** | the ports each server must open, per role (`pskit firewall`, studio *Network map*) |

The on-prem pages start at [onprem/README.md](../onprem/README.md).

## See also

- [Learning path](README.md)
- [Build the orders app from the terminal](end-to-end-cli.md)
- [Build the orders app in studio](end-to-end-studio.md)
- [Run the orders app on your own servers](end-to-end-onprem-cluster.md)
- [Configuration reference](../configuration.md)
- [Architecture](../architecture.md)
