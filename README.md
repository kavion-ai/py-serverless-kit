# py-serverless-kit

[![CI](https://github.com/kavion-ai/py-serverless-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/kavion-ai/py-serverless-kit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/py-serverless-kit.svg)](https://pypi.org/project/py-serverless-kit/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/kavion-ai/py-serverless-kit/blob/main/LICENSE)

**Write your functions once in Python or Node.js. Deploy them to any of 10 clouds, or to your own servers, by changing one line of YAML.**

`py-serverless-kit` (CLI: `pskit`) is a Serverless-Framework-style toolkit built on **Terraform**. Your handlers use one small, provider-neutral API (`Event`, `Context`, `Response`) in Python, JavaScript or TypeScript. A `pskit.yml` file says which cloud they run on and what triggers them: HTTP, schedules, queues, storage, topics and, on premises, e-mail. The same file can define workflows in the style of Step Functions. `pskit deploy` generates Terraform for the chosen cloud, applies it, and builds an HTML dashboard of everything you deployed.

**[Read the full documentation](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/README.md)**

## One handler, every cloud

**Python**

```python
# app/handlers.py
from py_serverless_kit import Event, Context, NotFound

def get_order(event: Event, ctx: Context):
    order = ORDERS.get(event.http.path_params["id"])
    if order is None:
        raise NotFound("no such order")      # -> HTTP 404 JSON on every cloud
    return order                              # -> HTTP 200 JSON
```

**Node.js (TypeScript or JavaScript)**

```ts
// src/handlers.ts
import { NotFound } from "pskit";
import type { Context, Event } from "pskit";

export async function getOrder(event: Event, ctx: Context) {
  const order = ORDERS.get(event.http!.pathParams.id);
  if (!order) throw new NotFound("no such order");   // -> HTTP 404 JSON on every cloud
  return order;                                       // -> HTTP 200 JSON
}
```

**The same YAML for both.** Only `runtime` and the handler path differ:

```yaml
# pskit.yml
service: orders
provider:
  name: aws             # <- change to gcp, azure, onprem, ... and redeploy. That's the migration.
  region: us-east-1
  runtime: python3.12   # or nodejs20
functions:
  get-order:
    handler: app.handlers.get_order     # Node.js: src.handlers.getOrder
    events:
      - http: GET /orders/{id}
```

```bash
pskit deploy                      # terraform apply on AWS
pskit deploy --provider gcp       # same code, Google Cloud Functions
pskit dashboard --open            # every function, trigger, URL and resource id
pskit studio --open               # or build all of the above in a web UI instead of YAML
```

---

## Why

Teams that build on AWS Lambda and Step Functions end up with code full of API Gateway event parsing, SQS record loops and hand-written ASL. When the business needs another cloud, every function has to be rewritten. `py-serverless-kit` fixes this at each layer:

| Layer | Locked-in way | With pskit |
|---|---|---|
| Handler code | Parses `event["requestContext"]["http"]["method"]`, `Records[].body`, ... | Uses `event.http.method`, `event.records[].body`: the same on every cloud |
| Triggers / infra | SAM / CloudFormation / console clicks | One `pskit.yml`, rendered to Terraform for the target cloud |
| Workflows | Step Functions ASL | Portable state machine, compiled to Step Functions or Google Cloud Workflows, or run by the built-in engine elsewhere |
| Visibility | One console per cloud | One generated dashboard across all clouds and stages |

## Python and Node.js

Both languages get the same YAML, triggers, workflows, resources, local tools and deploy commands.

| | Python | Node.js |
|---|---|---|
| **Runtimes** | `python3.9` to `python3.14` | `nodejs18`, `nodejs20`, `nodejs22`, `nodejs24` |
| **Languages** | Python | JavaScript, or TypeScript that pskit compiles for you |
| **Dependencies** | `requirements.txt` | `package.json`, bundled by pskit or the platform's build |
| **Handler** | `app.handlers.get_order` is `get_order` in `app/handlers.py` | `src.handlers.getOrder` is the `getOrder` export of `src/handlers.ts` |
| **New project** | `pskit init my-api -p aws` | `pskit init my-api -p aws --typescript` or `--runtime nodejs22` |
| **Example** | [01-hello-http](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/01-hello-http) | [21-nodejs-typescript](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/21-nodejs-typescript) |

A service uses one language. To mix them, split the functions into two services that call each other over HTTP or a queue. Which versions you can use depends on the provider: see the [table below](#supported-providers). More: [Node.js and TypeScript](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/nodejs.md) and the [Handler API](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/handlers.md).

## Features

### Build

- **Triggers:** HTTP (path params, CORS, auth), schedules (rate/cron, translated into each cloud's cron dialect), queues, object storage, pub/sub topics, e-mail ([SMTP](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/smtp/README.md), on premises) and direct function-to-function `invoke()`.
- **Workflows:** task / choice / wait / pass / parallel / map / succeed / fail with retry and catch. Native on AWS and GCP, opt-in Logic Apps on Azure, and an embedded engine elsewhere. Run them locally with `pskit workflow run`. Every run returns an `execution_id`, and `pskit workflow start|executions|status|cancel` and the dashboard list, follow and cancel runs.
- **Resources:** a `resources:` section for buckets, queues, topics, databases, caches or any service, created by pskit or attached as `external`. Handlers read them with `resource("name")` on every cloud. See [using resources from code](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/resource-usage.md) and the [per-cloud guides](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/resource-guides/README.md).
- **Local development:** `pskit dev` (hot-reloading HTTP server), `pskit invoke` with synthetic queue, storage and schedule events, and a `LocalRunner` for pytest.
- **Config that scales:** `extends:`, per-provider `providers:` blocks, per-stage `stages:` blocks, and `${env:}`, `${opt:}`, `${self:}`, `${file()}` variables.

### Deploy

- **10 clouds and your own servers:** AWS Lambda, Azure Functions, Google Cloud Functions (gen2), Alibaba Function Compute, Oracle Functions, IBM Code Engine, DigitalOcean Functions, Tencent SCF, Huawei FunctionGraph, Cloudflare Workers, and `onprem`.
- **Terraform underneath:** real, reviewable `main.tf.json`, any backend (S3, GCS, azurerm, ...), works with OpenTofu. Escape hatches: `terraform.extra`, `${tf:...}` references, per-function `options`.
- **Production details:** deterministic artifacts (no redeploy when nothing changed), partial batch failures (`BatchResult`), structured JSON logs, consistent HTTP error mapping, stack traces hidden from clients, a Python runtime with no third-party dependencies inside your function, and hooks (`before_deploy`, ...).

### Run on your own servers

- **Deploy methods:** a process on this machine, SSH/SCP onto a server, or Docker. pskit can install Docker on a server that lacks it and bring a bundled CPython when the server has no Python. See [on premises](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/onprem/README.md).
- **[Scaling clusters](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/cluster.md):** Docker Swarm, Kubernetes (k3s) or Nomad over a master and joined servers, with live capacity monitoring and an alert when every server is full.
- **[Function groups on several servers](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/placement.md):** each function in its own folder with its own dependencies, on servers that call each other and run workflows across machines.
- **[Load balancers](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/load-balancers.md):** six algorithms, with one balancer serving several projects and clusters by path.
- **[On-prem services](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/onprem/services/README.md):** a catalog of 44 queues, databases, buckets, caches, secret managers and tools, started as Docker containers and added to `pskit.yml`, with [database scaling](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/onprem/database-scaling.md).
- **[AWS-compatible servers](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/onprem/aws-compatible/README.md):** S3 and Secrets Manager servers, each in Python and Node.js, so AWS SDK code runs on your machines with only an endpoint change.
- **[Network and firewall rules](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/onprem-network.md):** `pskit firewall` and a network map show which ports each server must open.
- **[pskit client and HTTP API](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/client.md):** call an on-prem host's queues, buckets, topics and functions from any Python or Node.js program, or over HTTP.

### Studio, dashboard and assistant

- **[Studio](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/studio-guide/README.md):** `pskit studio` builds the project in a web UI instead of YAML: provider cards, a function wizard, a visual workflow builder, resources, servers, services, clusters, a code editor or full VS Code in Docker, and deploy, test and logs.
- **[Hana, the AI assistant](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/assistant.md):** a chat in studio that answers questions and changes your project with your approval. The model runs on your machine or server, so nothing you type is sent to a cloud.
- **[Dashboard](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/dashboard.md):** a self-contained page listing every deployment, function, trigger, endpoint, console link, workflow and resource. `pskit dashboard --serve` adds live on-prem logs and stats and workflow executions.

### Teams and security

- **[Accounts and encrypted project data](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/studio-guide/accounts-and-team.md):** the first `pskit studio` start asks who will use the project.
  - **Just me:** no login and nothing encrypted.
  - **A team:** `.env` files and `.pskit` settings are encrypted (AES-256-GCM) into `.pskit-vault/`, which is safe to commit, so secrets can be shared through git.
- **Login:** every login needs a shared master key plus a personal username and password. An admin also keeps a recovery code offline.
- **Permissions:** an admin sets create, read, update and delete per feature, with `viewer`, `developer` and `operator` presets. An account can decrypt only the data its permissions allow.
- **Audit log:** every change, refused action, login and deploy is recorded.
- **Limits:** other permissions are enforced by pskit on each person's own computer. Read [what this protects against](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/security-vault.md#what-this-protects-against-and-what-it-does-not), and report problems through the [security policy](https://github.com/kavion-ai/py-serverless-kit/blob/main/SECURITY.md).

## Supported providers

| Provider | Tier | HTTP | Schedule | Queue | Storage | Topic | Workflows | Python | Node.js |
|---|---|:-:|:-:|:-:|:-:|:-:|---|---|---|
| AWS Lambda | stable | ✅ | ✅ | ✅ SQS | ✅ S3 | ✅ SNS | native (Step Functions) | 3.9–3.13 | 18, 20, 22 |
| Google Cloud Functions | stable | ✅ | ✅ | ✅ Pub/Sub | ✅ GCS | ✅ Pub/Sub | native (Cloud Workflows) | 3.9–3.13 | 18, 20, 22 |
| Azure Functions | stable | ✅ | ✅ | ✅ Storage Queue | ✅ Blob | ✅ Service Bus | embedded, or Logic Apps (`engine: native`) | 3.9–3.12 | 18, 20, 22 |
| Alibaba Function Compute | beta | ✅ | ✅ | – | ✅ OSS | ✅ MNS | embedded | 3.9, 3.10, 3.12 | 18, 20 |
| Huawei FunctionGraph | beta | ✅ | ✅ | – | ✅ OBS | ✅ SMN | embedded | 3.9, 3.10, 3.12 | 18 |
| Tencent SCF | beta | ✅ | ✅ | – | ✅ COS | – | embedded | 3.9, 3.10 | 18 |
| DigitalOcean Functions | beta | ✅ | ✅ | – | – | – | embedded | 3.9, 3.11 | 18 |
| IBM Code Engine | beta | ✅ | – | – | – | – | embedded | 3.11 | 18, 20 |
| Oracle Cloud Functions | experimental | ✅ | – | – | ✅ | – | embedded | 3.9, 3.11 | 18, 20 |
| Cloudflare Workers | experimental | ✅ | ✅ | – | – | – | embedded | 3.11–3.13 | 18, 20, 22 |
| On-premises | experimental | ✅ | ✅ | ✅ files | ✅ directory | ✅ files | embedded (local, SSH, Docker or cluster) | 3.9–3.14 | 18–24 |

On premises, queues can also live in Redis or other drivers, storage in MinIO or any S3-compatible store, and functions can be triggered by e-mail.

Run `pskit providers` for the live matrix. If a config uses a trigger the target cloud can't support, **`pskit validate` fails with a clear message instead of deploying something half-working.**

> **Maturity, honestly stated:** the Terraform generated for every provider is checked with `terraform validate` against the real provider plugins (in CI, too). The *stable* providers cover the most surface area. *beta* and *experimental* providers follow vendor docs for event payloads that `validate` can't check, so try them on a non-production account first. See [docs/providers.md](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/providers.md) for each provider's details and limits.

## Install

```bash
pip install py-serverless-kit
```

You need:

- **Python 3.9 or newer** to run `pskit`, also for Node.js projects.
- **Terraform 1.5 or newer** (or OpenTofu) on your `PATH`, plus credentials for your cloud. See [Getting started](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/getting-started.md#6-configure-cloud-credentials).
- **Node.js 18 or newer and npm** on your `PATH`, only for Node.js projects.

Run `pskit doctor` to check your tools and credentials.

## Quick start

**Python**

```bash
pskit init my-api --provider aws --template full   # templates: http | events | workflow | full
cd my-api
pskit dev                                          # http://127.0.0.1:3000/hello
pskit invoke -f hello --path "/hello?name=Ada"
pskit workflow run order-pipeline -i '{"amount": 42}'
pskit deploy --stage dev
pskit info
pskit dashboard --open
pskit remove --stage dev
```

**Node.js**

```bash
pskit init my-api --provider aws --typescript      # or --runtime nodejs22 for JavaScript
cd my-api
pskit dev
pskit invoke -f hello --path "/hello?name=Ada"
pskit deploy --stage dev
```

**In the browser**

```bash
pskit studio --open                                # on a new or existing project
```

### Move to another cloud

Change `provider.name`, or keep one file with per-cloud blocks:

```yaml
provider:
  name: aws
  region: us-east-1
providers:              # applied only when that provider is selected
  gcp:   {region: europe-west1, options: {project: my-project}}
  azure: {region: westeurope, options: {subscription_id: "${env:ARM_SUBSCRIPTION_ID}"}}
```

```bash
pskit deploy --provider gcp
pskit deploy --provider azure --stage prod
```

### Triggers at a glance

```yaml
functions:
  api:
    handler: app.api.handle
    events:
      - http: {method: POST, path: /orders, cors: true}
      - http: GET /orders/{id}
  nightly:
    handler: app.jobs.nightly
    events:
      - schedule: {cron: "0 2 * * *", input: {report: daily}, timezone: Europe/Berlin}
  worker:
    handler: app.jobs.process
    timeout: 60
    events:
      - queue: {name: orders, batch_size: 10, dead_letter: orders-dlq}
  thumbnails:
    handler: app.media.on_upload
    events:
      - storage: {bucket: my-uploads-bucket, events: [created], suffix: .jpg}
  audit:
    handler: app.audit.on_event
    events:
      - topic: order-events
```

Retry only the messages that failed, in either language:

```python
from py_serverless_kit import BatchResult, Event, Context

def process(event: Event, ctx: Context):
    result = BatchResult()               # retry only failed messages where the cloud supports it
    for record in event.records:
        try:
            handle(record.json())
        except Exception:
            result.fail(record)
    return result
```

```ts
import { BatchResult } from "pskit";
import type { Context, Event } from "pskit";

export async function process(event: Event, ctx: Context) {
  const result = new BatchResult();
  for (const record of event.records) {
    try { await handle(record.json()); } catch { result.fail(record); }
  }
  return result;
}
```

### Workflows (portable Step Functions)

```yaml
workflows:
  order-pipeline:
    start_at: Validate
    states:
      Validate:
        type: task
        function: validate-order
        retry: [{errors: [TimeoutError], max_attempts: 3, backoff_rate: 2}]
        catch: [{errors: [ValueError], next: Rejected}]
        next: Route
      Route:
        type: choice
        choices: [{variable: "$.amount", gt: 1000, next: ManualReview}]
        default: Charge
      ManualReview: {type: wait, seconds: 3600, next: Charge}
      Charge: {type: task, function: charge-order, end: true}
      Rejected: {type: fail, error: OrderRejected}
```

The same definition becomes **AWS Step Functions** on AWS, **Google Cloud Workflows** on GCP, and an **embedded orchestrator function** on the other clouds. On Azure, `engine: native` makes it a Logic App instead. `pskit workflow show order-pipeline --format asl` prints the generated ASL.

## Commands

| Group | Commands |
|---|---|
| **Start** | `init`, `studio`, `doctor`, `providers` |
| **Develop** | `dev`, `invoke`, `validate`, `function`, `workflow` |
| **Deploy** | `package`, `plan`, `deploy`, `info`, `remove`, `tf` |
| **Operate** | `logs`, `trigger`, `dashboard`, `resources`, `settings` |
| **On premises** | `cluster`, `lb`, `firewall`, `client` |
| **Accounts** | `login`, `logout`, `whoami`, `vault` |

Run `pskit <command> --help`, or see the [CLI reference](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/cli.md).

## How it works

```
 pskit.yml ──► config loader ──► provider validation ──► packager ──────────► artifact.zip
 (extends, providers:,          (capabilities,           (your code + pskit
  stages:, ${vars})              limits, runtimes)        runtime + manifest + shim)
                                        │
                                        ▼
                              provider renderer ──► .pskit/<provider>-<stage>/main.tf.json
                                                              │ terraform init / apply
                                                              ▼
                                       deployment.json ──► dashboard/index.html

 At runtime:  cloud event ──► shim ──► runtime adapter for the cloud ──► Event ──► your handler
              your result ──► Response / raw value ──► adapter ──► native cloud response
```

More: [docs/architecture.md](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/architecture.md).

## Examples

Twenty-one runnable examples live in [`examples/`](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/). They are tested in CI.

| | |
|---|---|
| [01-hello-http](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/01-hello-http) | Minimal HTTP function |
| [02-rest-api](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/02-rest-api) | CRUD, path params, validation errors, CORS, cookies, binary, JWT |
| [03-scheduled-jobs](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/03-scheduled-jobs) | rate/cron schedules with input and time zones |
| [04-queue-worker](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/04-queue-worker) | Queue consumer, partial batch failures, dead-letter queue |
| [05-storage-events](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/05-storage-events) | Object created/deleted with filters |
| [06-pubsub-topic](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/06-pubsub-topic) | Topic fan-out and filters |
| [07-workflow-orders](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/07-workflow-orders) | Every workflow state type, retry/catch |
| [08-multi-cloud](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/08-multi-cloud) | Same code, all 11 providers |
| [09-function-invoke](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/09-function-invoke) | Function-to-function `invoke()` |
| [10-stages-and-config](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/10-stages-and-config) | Stages, variables, secrets |
| [11-custom-terraform](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/11-custom-terraform) | `terraform.extra`, `${tf:...}`, remote state, hooks |
| [12-async-and-context](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/12-async-and-context) | async handlers, logging, deadlines |
| [13-migrate-from-aws-lambda](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/13-migrate-from-aws-lambda) | Before/after migration of Lambda + Step Functions |
| [14-testing](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/14-testing) | Unit-testing handlers and workflows with pytest |
| [15-ci-cd-deploy](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/15-ci-cd-deploy) | GitHub Actions deploys per stage |
| [16-on-premises](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/16-on-premises) | HTTP, schedule, queue, storage, topic and a workflow on one machine |
| [17-on-premises-remote](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/17-on-premises-remote) | SSH/SCP or Docker onto a server |
| [18-resources](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/18-resources) | Managed and external resources, bindings, Redis/MinIO on premises |
| [19-custom-drivers](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/19-custom-drivers) | Your own on-prem queue/storage driver class; RabbitMQ and Kafka templates |
| [20-onprem-external-clouds](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/20-onprem-external-clouds) | On-prem host watching queues and buckets in AWS, Azure, GCP, Alibaba, Cloudflare and MinIO |
| [21-nodejs-typescript](https://github.com/kavion-ai/py-serverless-kit/tree/main/examples/21-nodejs-typescript) | Node.js and TypeScript: HTTP routes, a queue worker, a schedule and a workflow |

## Documentation

**Start at the [documentation home](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/README.md)**, which lists every guide. The most used pages:

| | |
|---|---|
| [Getting started](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/getting-started.md) | Install, credentials, first deploy |
| [Learning path and concepts](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/guide/README.md) | One application built end to end, from the terminal, in studio and on premises |
| [Scenarios](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/scenarios.md) | Step-by-step guides by use case |
| [Configuration reference](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/configuration.md) | Every `pskit.yml` key, variables, `extends`, stages |
| [Handler API](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/handlers.md) | `Event`, `Context`, `Response`, errors, `BatchResult`, `invoke()` |
| [Node.js and TypeScript](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/nodejs.md) | JavaScript and TypeScript handlers, runtimes per provider, npm dependencies |
| [Events](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/events.md) | Every trigger, with a per-provider matrix |
| [Workflows](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/workflows.md) | State machine reference, engines, limitations |
| [Resources](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/resources.md) | Storage, queues, topics, databases, external services |
| [Providers](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/providers.md) | Options, credentials, resources and limits per cloud |
| [On premises](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/onprem/README.md) | Servers, services, scaling, load balancers, firewall |
| [Studio guide](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/studio-guide/README.md) | Every page and button of the web UI |
| [Accounts and team setup](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/studio-guide/accounts-and-team.md) | Just me or a team, master key, recovery code, user permissions |
| [CLI](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/cli.md) | Every command and flag |
| [Migrating from AWS](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/migrating-from-aws.md) | Lambda + Step Functions → pskit |
| [Troubleshooting](https://github.com/kavion-ai/py-serverless-kit/blob/main/docs/troubleshooting.md) | Common errors and fixes |

## Contributing

- Contributor guide: [deploy_docs/CONTRIBUTING.md](https://github.com/kavion-ai/py-serverless-kit/blob/main/deploy_docs/CONTRIBUTING.md)
- Security policy: [SECURITY.md](https://github.com/kavion-ai/py-serverless-kit/blob/main/SECURITY.md)

## Author

Created and maintained by **Asif Khan @ [Kavion.ai](https://kavion.ai)**.

Source code, issues and releases: <https://github.com/kavion-ai/py-serverless-kit>

## License

MIT, see [LICENSE](https://github.com/kavion-ai/py-serverless-kit/blob/main/LICENSE).
