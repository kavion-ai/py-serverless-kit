# Start here: the pskit learning path

Search terms: start here, learning path, tutorial, beginner, where to begin, documentation map, docs index, overview, how to learn pskit, guide

pskit (py-serverless-kit) lets you write a Python handler once, describe it in `pskit.yml`, and deploy it to AWS,
Azure, GCP, Alibaba, Tencent, Huawei, Oracle, IBM, DigitalOcean, Cloudflare or your own servers. You can work from
the terminal (`pskit`), from a web UI (`pskit studio`), or ask the studio's AI assistant, Hana. This page tells
you what to read, in which order.

## Learn pskit in five steps

Follow the steps in order. Each step links to one page; each page has numbered steps for both studio and the
terminal.

1. **Learn the words.** [concepts.md](concepts.md): project, service, function, handler, trigger, resource,
   stage, provider, workflow, deployment, and the on-prem terms.
2. **Build a full application from the terminal.** [end-to-end-cli.md](end-to-end-cli.md): the orders service
   (HTTP API, queue consumer, storage processor, nightly schedule, topic fan-out, workflow, database, cache),
   from `pskit init` to a `dev` and a `prod` stage on AWS, then update and remove.
3. **Build the same application in studio.** [end-to-end-studio.md](end-to-end-studio.md): every sidebar page,
   button and field, in order, plus asking Hana to do steps.
4. **Run it on your own servers.** [end-to-end-onprem-cluster.md](end-to-end-onprem-cluster.md): saved servers,
   Docker, PostgreSQL with a read replica, Redis, MinIO, a Docker Swarm cluster, scaling, a load balancer and
   the firewall rules.
5. **Go deeper** with the topic folders below when you need one feature in detail.

Short on time? [getting-started.md](../getting-started.md) deploys one HTTP function.

## Find a topic in the documentation folders

The documentation is split into folders by task. Each folder's `README.md` is its map.

| Folder | Read it when you want to |
|---|---|
| [guide/](README.md) | follow the learning path and the end-to-end guides (this folder) |
| [studio-guide/](../studio-guide/README.md) | use one studio page: launch, sidebar, draft and Save, every page and button |
| [functions/](../functions/README.md) | create a function (single file or own folder, Python or Node.js), configure memory, timeout, environment, permissions, invoke and test it |
| [triggers/](../triggers/README.md) | pick and configure a trigger: [HTTP](../triggers/http.md), [schedule](../triggers/schedule.md), [queue](../triggers/queue.md), [storage](../triggers/storage.md), [topic](../triggers/topic.md), [SMTP](../triggers/smtp.md), and which provider supports which |
| [deployment/](../deployment/README.md) | deploy anywhere: every cloud, on-prem local / SSH / Docker, function groups, clusters; [stages](../deployment/stages.md), [deploy, remove, info](../deployment/deploy-remove-info.md), [workflows](../deployment/workflows.md), [logs](../deployment/logs.md), [monitoring and dashboard](../deployment/monitoring-and-dashboard.md) |
| [onprem/](../onprem/README.md) | run on your own servers: [servers](../onprem/servers.md), [terminal and software](../onprem/terminal-and-software.md), [services](../onprem/services/README.md), [resources](../onprem/resources.md), [cloud resources](../onprem/cloud-resources.md), [scaling](../onprem/scaling/README.md), [load balancers](../onprem/load-balancers.md), [database scaling](../onprem/database-scaling.md), [network map](../onprem/network-map.md), [firewall](../onprem/firewall.md), [placement](../onprem/placement.md) |
| [providers/](../providers/README.md) | set up one cloud: credentials, the `pskit.yml` provider block and options, supported triggers and resources, deploy, logs, limits |

## Pick a path by what you want to do

| Goal | Path |
|---|---|
| A REST API on AWS | [concepts](concepts.md) → [end-to-end-cli](end-to-end-cli.md) → [triggers/http.md](../triggers/http.md) → [providers/aws](../providers/aws/README.md) |
| Build without writing YAML | [end-to-end-studio](end-to-end-studio.md) → [studio-guide](../studio-guide/README.md) → [assistant.md](../assistant.md) |
| Background jobs (queues, schedules, files) | [triggers/queue.md](../triggers/queue.md), [triggers/schedule.md](../triggers/schedule.md), [triggers/storage.md](../triggers/storage.md) → [resources.md](../resources.md) |
| A multi-step business process | [deployment/workflows.md](../deployment/workflows.md) → [workflows.md](../workflows.md) → [workflow-executions.md](../workflow-executions.md) |
| Your own servers, no cloud | [end-to-end-onprem-cluster](end-to-end-onprem-cluster.md) → [onprem/README.md](../onprem/README.md) |
| More traffic on premises | [onprem/scaling](../onprem/scaling/README.md) → [load balancers](../onprem/load-balancers.md) → [database scaling](../onprem/database-scaling.md) |
| Move from AWS Lambda | [migrating-from-aws.md](../migrating-from-aws.md) → [resource-guides/compatibility.md](../resource-guides/compatibility.md) |
| Another cloud | [providers/README.md](../providers/README.md) → the cloud's folder |
| Dev, staging and prod | [deployment/stages.md](../deployment/stages.md) |
| Something fails | [troubleshooting.md](../troubleshooting.md) |

## Use the reference pages for every option

The reference pages list every key, flag and API. The guides above link to them where they matter.

| Page | What it covers |
|---|---|
| [configuration.md](../configuration.md) | every `pskit.yml` key, `extends:`, `providers:` / `stages:` overrides, variables |
| [cli.md](../cli.md) | every `pskit` command and flag |
| [handlers.md](../handlers.md) | `Event`, `Context`, `Response`, errors, `BatchResult`, `invoke()`, secrets, logging |
| [events.md](../events.md) | trigger shorthand forms and per-provider support |
| [resources.md](../resources.md), [resource-usage.md](../resource-usage.md) | `resources:` and the code to use each resource type |
| [resource-guides/](../resource-guides/README.md) | per cloud and type: create a queue, bucket, topic, database or cache in the console |
| [providers.md](../providers.md) | capability matrix and one section per cloud |
| [workflows.md](../workflows.md), [workflow-executions.md](../workflow-executions.md) | state machine reference and execution commands |
| [local-development.md](../local-development.md) | `pskit dev`, `pskit invoke`, `.env`, `LocalRunner` |
| [nodejs.md](../nodejs.md) | handlers in JavaScript or TypeScript |
| [studio.md](../studio.md), [assistant.md](../assistant.md) | studio features and Hana |
| [dashboard.md](../dashboard.md) | the deployment dashboard |
| [cluster.md](../cluster.md), [load-balancers.md](../load-balancers.md), [placement.md](../placement.md), [onprem-network.md](../onprem-network.md) | on-prem clusters, load balancers, function groups, network rules |
| [smtp/README.md](../smtp/README.md) | e-mail triggers on premises |
| [client.md](../client.md) | the pskit client and the on-prem host's HTTP API |
| [scenarios.md](../scenarios.md) | short recipes by use case |
| [architecture.md](../architecture.md) | how `pskit.yml` becomes Terraform and how the runtime dispatches events |
| [troubleshooting.md](../troubleshooting.md) | common errors and fixes |

Runnable examples for each feature: [`examples/`](../../examples/README.md).

## See also

- [Documentation index](../README.md)
- [Concepts and glossary](concepts.md)
- [Getting started](../getting-started.md)
- [Studio guide](../studio-guide/README.md)
