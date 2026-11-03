# py-serverless-kit documentation

Write a Python function once, describe its triggers in `pskit.yml`, and deploy it to any of 10 clouds or to an on-premises host with Terraform. Moving to another target means changing `provider.name`. The handler code stays the same.

## Start here: guides by topic

Every task in these folders is explained twice: click by click **in studio** and as **terminal** commands.

| Folder | What it covers |
|---|---|
| [guide/](guide/README.md) | Learning path, [concepts](guide/concepts.md), and one full application built end to end: [from the terminal](guide/end-to-end-cli.md), [in studio](guide/end-to-end-studio.md), [on premises with a cluster, load balancer and replicated database](guide/end-to-end-onprem-cluster.md) |
| [studio-guide/](studio-guide/README.md) | `pskit studio` page by page: navigation, every button and field, the function wizard, trigger forms, servers, services, cluster, load balancers, network map, deploy, test, logs, Hana |
| [functions/](functions/README.md) | Create a function (one file or its own app folder), configure it, call and test it |
| [triggers/](triggers/README.md) | One page per trigger: [http](triggers/http.md), [schedule](triggers/schedule.md), [queue](triggers/queue.md), [storage](triggers/storage.md), [topic](triggers/topic.md), [smtp](triggers/smtp.md); support per provider |
| [deployment/](deployment/README.md) | Every deployment type, [stages](deployment/stages.md), [deploy / info / remove](deployment/deploy-remove-info.md), [workflows](deployment/workflows.md), [logs](deployment/logs.md), [monitoring and dashboard](deployment/monitoring-and-dashboard.md), [settings and variables](deployment/settings-and-config.md) |
| [onprem/](onprem/README.md) | [Servers](onprem/servers.md), [software and terminal](onprem/terminal-and-software.md), [every on-prem service](onprem/services/README.md), [resources](onprem/resources.md), [resources from other clouds](onprem/cloud-resources.md), [AWS-compatible S3 and Secrets Manager (Python and Node.js)](onprem/aws-compatible/README.md) |
| [onprem/scaling/](onprem/scaling/README.md) | [Docker Swarm](onprem/scaling/docker-swarm.md), [Kubernetes (k3s)](onprem/scaling/kubernetes-k3s.md), [Nomad](onprem/scaling/nomad.md), [replicas and alerts](onprem/scaling/replicas-and-alerts.md), [load balancers](onprem/load-balancers.md), [database scaling](onprem/database-scaling.md), [network map](onprem/network-map.md), [firewall](onprem/firewall.md), [function groups on several servers](onprem/placement.md) |
| [providers/](providers/README.md) | One folder per provider: [AWS](providers/aws/README.md), [Azure](providers/azure/README.md), [GCP](providers/gcp/README.md), [Alibaba](providers/alibaba/README.md), [Tencent](providers/tencent/README.md), [Huawei](providers/huawei/README.md), [Oracle](providers/oracle/README.md), [IBM](providers/ibm/README.md), [DigitalOcean](providers/digitalocean/README.md), [Cloudflare](providers/cloudflare/README.md), [on premises](providers/onprem/README.md) |

Hana, the studio assistant, searches all of these pages before she answers. After changing anything under `docs/`, run
`python scripts/build_hana_docs_index.py` (a test fails when the index is out of date).

## Reference pages

| Page | What it covers |
|---|---|
| [Scenarios](scenarios.md) | Step-by-step guides by use case: HTTP API, queues, existing resources, Redis/MinIO on premises, databases, workflows, schedules, stages, logs, testing |
| [Getting started](getting-started.md) | Install, scaffold a project, run it locally, set up cloud credentials, deploy, inspect, remove |
| [Configuration reference](configuration.md) | Every `pskit.yml` key, `extends:`, `providers:`/`stages:` overrides, variables, escape hatches |
| [Events (triggers)](events.md) | `http`, `schedule`, `queue`, `storage`, `topic`, `smtp`, with shorthand forms and per-provider support |
| [Functions on several servers (on premises)](placement.md) | Each function in its own folder with its own requirements; groups of functions on different servers (or clusters) that call each other, share queues and run workflows across machines |
| [Network and firewall rules (on premises)](onprem-network.md) | Which server must allow which inbound / outbound port for one server, function groups, clusters (Swarm, k3s, Nomad), joining servers, load balancers, resources and SMTP |
| [Load balancers (on premises)](load-balancers.md) | Six algorithms (round robin, sticky, weighted, IP hash, least connections, least time); one load balancer shared by projects and clusters by path |
| [Scaling cluster (on premises)](cluster.md) | Run on-prem functions on a master plus joined servers with Docker Swarm, Kubernetes (k3s) or Nomad: join servers on the go, monitor CPU / memory / disk, scale replicas, alert DevOps (a function or webhook) when every server is full |
| [E-mail triggers (SMTP)](smtp/README.md) | On premises: an SMTP server (Node.js) that receives mail for your domain and runs functions with from, to, subject, body and attachments (also in the Amazon SES event shape); DNS (A / MX) records, port 25, testing |
| [Node.js and TypeScript](nodejs.md) | Handlers in JavaScript or TypeScript: runtimes per provider, `tsc`, npm dependencies, local runs |
| [Handler API](handlers.md) | `Event`, `HttpRequest`, `Record`, `Context`, `Response`, errors, `BatchResult`, `invoke()`, logging |
| [Workflows](workflows.md) | State machines: native AWS Step Functions / GCP Workflows, or the embedded engine anywhere |
| [Workflow executions](workflow-executions.md) | Execution ids, async start, status/history/cancel from the CLI, dashboard and HTTP |
| [Resources](resources.md) | `resources:`: managed or external storage, queues, topics, databases and other services; on-prem Redis and S3 drivers |
| [Existing cloud code](resource-guides/compatibility.md) | Lambda ARNs, boto3 Lambda / SQS code, S3 / Azure / GCS SDKs: what works on each provider, the one-line change, the pskit way |
| [pskit client and HTTP API](client.md) | Call an on-prem host from any Python / Node.js program or over HTTP: queues, buckets, topics, functions; tunnels and timeouts |
| [Using resources from code](resource-usage.md) | Libraries to install (Python / Node.js) for every resource type and provider, handler code, local and deployed tests |
| [Resource guides](resource-guides/README.md) | Step by step, per cloud and type: create a queue, bucket, topic, database, cache or other service in the console, find its details and add it to `pskit.yml` |
| [Providers](providers.md) | Capability matrix plus one section per cloud: options, credentials, resources, limits |
| [CLI reference](cli.md) | Every `pskit` command and flag |
| [Local development](local-development.md) | `pskit dev`, `pskit invoke`, `.env`, testing with `LocalRunner` |
| [Studio](studio.md) | `pskit studio`: build functions, triggers, workflows, resources and on-prem drivers in a web UI, edit code (built-in editor or VS Code in Docker) and deploy |
| [Hana, the AI assistant](assistant.md) | The chat in `pskit studio`: answers, how-to steps and project changes with your approval; the model runs locally in Docker |
| [Dashboard](dashboard.md) | The deployment UI: static page, or live with logs and workflow executions (`--serve`) |
| [Architecture](architecture.md) | How config becomes Terraform and how the runtime dispatches events; third-party providers |
| [Migrating from AWS](migrating-from-aws.md) | Moving existing Lambda functions and Step Functions to pskit, then to other clouds |
| [Troubleshooting & FAQ](troubleshooting.md) | Common errors, provider gotchas, security notes |

Runnable examples for every scenario live in [`../examples`](../examples/README.md).

Contributors: see [`../deploy_docs/CONTRIBUTING.md`](../deploy_docs/CONTRIBUTING.md).
