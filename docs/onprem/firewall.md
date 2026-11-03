# On-prem firewall rules: every port

Search terms: firewall, ports, ufw, security group, inbound, outbound, open port, pskit firewall, REQUIRED,
NEEDED, SSH 22, 2377, 6443

The on-prem provider tells you which ports each server must open. Every on-prem step prints the rules it just
made necessary, with your servers' names, addresses and `ufw` commands, and `pskit firewall` lists every rule the
project needs now. This page explains the levels and lists every port pskit can ask for.

## The three firewall rule levels

Each on-prem firewall rule has a level. The studio and the CLI show it as a tag.

| Level | CLI tag | Studio | Meaning |
|---|---|---|---|
| required | `REQUIRED` | red badge `required` | it does not work without it |
| feature | `NEEDED` | yellow badge `feature` | needed for that feature only (for example first-time downloads) |
| optional | `optional` | grey badge `optional` | convenience; pskit falls back to an SSH tunnel |

## See the firewall rules from the terminal

The `pskit firewall` command lists the firewall rules this project's on-prem servers need now: deployments, function
groups, clusters, load balancers and services, per server, with who connects, why, and `ufw` commands.

```bash
pskit firewall                    # every server
pskit firewall --server edge2     # one server (name or address)
pskit firewall --json             # for scripts
```

Example output:

```text
Firewall - edge2 joined cluster prod (open these; docs/onprem-network.md):
  edge1 (10.0.0.5)
    [REQUIRED] inbound  TCP 2377     from edge2 (10.0.0.6)  - cluster prod: Swarm cluster management (managers)
    ufw on edge1:
      sudo ufw allow from 10.0.0.6 to any port 2377 proto tcp
```

These commands also print their rules: `pskit cluster create`, `pskit cluster join`, `pskit deploy`, `pskit lb create`,
`pskit lb attach`, `pskit cluster balancer set`, and `pskit resources onprem create`.

## See the firewall rules in studio

The studio shows the same firewall rules in a **Firewall** panel on three pages, and in each job's output:

1. **Deploy**: the **Firewall** panel below the deploy job, for the project's servers.
2. **Scaling cluster**: **Firewall: prod**, for the cluster's servers and its load balancers.
3. **Load balancers**: **Firewall: edge**, for the load balancer and its backends.

Each panel has **Refresh** and a **copy** button for the `ufw` commands. The **Network map** page draws all of them
as arrows between machines (see [Network map](network-map.md)).

## Firewall rules for SSH and downloads

pskit reaches every saved server over SSH from your machine (the admin machine). Servers download software once.

| Level | Server | Port | From / to | Why |
|---|---|---|---|---|
| required | every saved server | TCP 22 (its SSH port) inbound | the admin machine | scripts, copies, logs, tests, status |
| feature | every cluster server, load balancer, `method: docker` server | TCP 443, 80 outbound | the Internet | first time: Docker, k3s, Nomad, images |

Servers without Internet: preinstall Docker (and k3s / Nomad) and load images with `docker load`. pskit copies the
function image over SSH, so no registry is needed.

## Firewall rules for one function server

A function host on one server needs its functions port (`provider.options.port`, default 8080).

| Level | Server | Port | From | Why |
|---|---|---|---|---|
| required | the function server | TCP 22 | admin machine | deploy, logs |
| required | the function server | TCP `port` (8080) | users | HTTP routes, workflow starts, SQS / Lambda compatible APIs |
| optional | the function server | TCP `port` | admin machine | logs, tests and the studio; closed is fine, pskit tunnels over SSH |

Set `options.host: 0.0.0.0` so the port answers on the network, and `options.advertise` when users reach it by
another address.

## Firewall rules for function groups (placement)

Function groups on several servers call each other directly, so every group host must reach every other group host
on its port (a full mesh). The default group also receives logs and workflow starts.

| Level | Server | Port | From | Why |
|---|---|---|---|---|
| required | each group host | TCP its `port` | every other group host | `invoke()`, HTTP routes, workflow steps, queues; the default group also gets logs and workflow starts |
| required | group hosts that serve users | TCP its `port` | users (or only the load balancer) | HTTP |

## Firewall rules between scaling cluster servers

A scaling cluster needs the orchestrator's ports between its servers, plus the functions port.

| Orchestrator | Level | Opened on | Port | From | Why |
|---|---|---|---|---|---|
| Docker Swarm | required | master | TCP 2377 | workers | cluster management |
| Docker Swarm | required | every server | TCP 7946, UDP 7946 | the other servers | node discovery |
| Docker Swarm | required | every server | UDP 4789 | the other servers | overlay network (VXLAN) |
| Kubernetes (k3s) | required | master | TCP 6443 | workers | k3s API: agents register |
| Kubernetes (k3s) | required | every server | UDP 8472 | the other servers | Flannel VXLAN (pod network) |
| Kubernetes (k3s) | required | workers | TCP 10250 | master | kubelet (logs, exec, metrics) |
| HashiCorp Nomad | required | master | TCP 4646, 4647, 4648, UDP 4648 | workers | HTTP API, RPC, gossip |
| all | required | master | TCP `port` | workers | web replicas reach the main replica |
| all | required | every server (Nomad: workers) | TCP `port` | users, or only the load balancers | requests |

Leaving a cluster needs only SSH.

## Firewall rules for load balancers

An on-prem HTTP load balancer (named or a cluster's own) needs its public ports and must reach every backend.

| Level | Server | Port | From | Why |
|---|---|---|---|---|
| required | load balancer | TCP 22 | admin machine (every project and machine that uses it) | install, routes, logs |
| feature | load balancer, outbound | TCP 443, 80 | to the Internet | first time: Docker and the OpenResty image |
| required | load balancer | TCP its port (80) and each cluster `balancer_port` (8081, ...) | users | the public URLs |
| required | every backend | TCP its functions `port` | the load balancer | forward requests, health checks |

With a load balancer you can close the functions port to users and allow it only from the load balancer (and the
other cluster servers or group hosts). Attaching a cluster adds no new port type: its servers become backends.

## Firewall rules for on-prem services and replicated databases

An on-prem service needs its port open to the function hosts (with `--cluster`: every cluster server).

| Level | Server | Port | From | Why |
|---|---|---|---|---|
| required | service server | TCP 22 | admin machine | create, check, data browser |
| required | service server | the service port (Redis 6379, PostgreSQL 5432, MySQL / MariaDB 3306, MongoDB 27017, ...) | function hosts | your functions connect |
| optional | service server | its web console port | admin machine | console (the studio can also open it over SSH) |
| required | SMTP server | TCP 25 (and an MX record) | the Internet | incoming mail |
| required | function host | TCP `port` | SMTP server | mail is delivered to the `smtp` triggers |

A replicated database adds:

| Level | Server | Port | From | Why |
|---|---|---|---|---|
| required | primary | database port | every replica | replicas copy the primary's changes |
| required | every MongoDB member | 27017 | every other member | replica set heartbeats and elections |
| required | every member | database port | the database load balancer | pgpool-II / ProxySQL forward queries |
| required | database load balancer | 6432 (pgpool-II) / 6033 (ProxySQL) | function hosts | the functions' single address |
| required | every member (no load balancer, or MongoDB) | database port | function hosts | `WRITE_URL`, `READ_URLS`, replica set URL |

The full port list per service type is in [onprem-network.md](../onprem-network.md#8-resources-and-triggers-attaching-events).

## Firewall rules that need no change

Some on-prem parts open nothing new. Built-in triggers (schedule, built-in queue, storage, topic, workflow) run
inside the host. The studio listens on `127.0.0.1` of your machine and browser terminals on `127.0.0.1:7681+`.
External drivers (SQS, S3, Azure, GCS, Redis) need **outbound** access from every function host to that service.
Capacity alert webhooks need outbound TCP 443 from the machine running the studio or `pskit cluster watch`.

## See also

* [Network map](network-map.md)
* [Load balancers](load-balancers.md), [Placement](placement.md), [Database scaling](database-scaling.md)
* [Scaling options compared](scaling/README.md)
* Reference with examples: [onprem-network.md](../onprem-network.md)
