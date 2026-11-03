# Scaling on-prem functions: all options compared

Search terms: scaling, scale out, scale up, horizontal scaling, cluster, Docker Swarm, Kubernetes, k3s, Nomad,
replicas, load balancer, placement, function groups, read replicas, more servers, high traffic

By default the on-prem provider runs every function of a project in **one host process on one server**. This page
lists every way pskit can give that project more capacity, and helps you pick one. Each option has its own page with
numbered steps for the studio and the terminal.

## The on-prem scaling options at a glance

The on-prem provider offers five scaling options. They can be combined: for example, function groups on a cluster
behind a shared load balancer, using a replicated database.

| Option | What it does | Scales | Page |
|---|---|---|---|
| **Bigger server** (scale up) | Give the one server more CPU and memory | everything, up to one machine | below |
| **Scaling cluster** | A master server plus joined servers run copies (replicas) of the function host | HTTP and `invoke()` traffic | [Docker Swarm](docker-swarm.md), [Kubernetes (k3s)](kubernetes-k3s.md), [Nomad](nomad.md) |
| **Load balancer** | One URL in front of several servers or clusters; picks a server per request | the entry point | [Load balancers](../load-balancers.md) |
| **Placement (function groups)** | Different functions on different servers, each with only its own dependencies | separation of heavy or special functions (GPU, batch) | [Placement](../placement.md) |
| **Replicated database** | One primary for writes plus read replicas, optionally behind a database load balancer | database reads | [Database scaling](../database-scaling.md) |

Replicas, the **Scale** button and capacity alerts for clusters are on
[Replicas and alerts](replicas-and-alerts.md).

## When to pick which on-prem scaling option

The on-prem scaling options answer different problems. Start from the problem you see:

| You see | Pick |
|---|---|
| One server is slow but a bigger machine is cheap | Scale up: move to a bigger server (`pskit deploy --server big1`) |
| Too many HTTP requests for one server | A **scaling cluster** with 2+ web replicas |
| Users need one stable URL for many servers | A **load balancer** (the cluster's own, or a shared named one) |
| Several projects should share one public address, each under its own path | One **shared (named) load balancer**: `http://lb/<service>/` |
| One function needs a GPU, a lot of memory, or conflicting libraries | **Placement**: put it in its own group on its own server |
| The database is the bottleneck, mostly with reads | A **replicated database**: primary + read replicas |
| Servers fill up and nobody notices | **Capacity alerts** on the cluster |

## Pick an orchestrator for a scaling cluster

A scaling cluster runs on one of three orchestrators. pskit installs it over SSH; you do not need to know it.

| Orchestrator | `--orchestrator` | What pskit installs | Load balancing built in | Pick it when |
|---|---|---|---|---|
| Docker Swarm | `swarm` | Docker on every server, `swarm init` / `swarm join` | yes: the routing mesh answers on the functions' port of **every** server | you want the simplest setup and know Docker |
| Kubernetes (k3s) | `kubernetes` | k3s (lightweight Kubernetes, no Docker needed) | yes: k3s ServiceLB answers on the port of **every** server | your team uses `kubectl` or plans to grow into Kubernetes |
| HashiCorp Nomad | `nomad` | Docker plus the Nomad agent (1.11.3 by default) as a systemd unit | no: each server answers for itself; add a load balancer for one URL | your team already runs Nomad or Consul |

All three run the same two workloads per deployment: one **main** replica on the master (schedules, built-in
queues, topics, buckets, workflow executions, logs, data) and `replicas` **web** replicas that serve HTTP and
`invoke()`. Your handler code does not change.

## What on-prem scaling does not scale

Some parts of an on-prem deployment stay on one process even in a cluster. Plan for them:

* The **main replica** is one process on the master. Schedules run once, built-in queues, topics and buckets live
  there, and workflow executions are recorded there. Use a queue driver (Redis, SQS, ...) when queue consumers must
  scale with the replicas.
* An on-prem **service** (Redis, Postgres, MinIO, ...) created on a cluster is one container on one server. The
  orchestrator does not move or replicate it. Databases scale with [read replicas](../database-scaling.md).
* A load balancer is one server. For no single point of failure, run two behind a floating IP (keepalived) or DNS.

## Scale up: move the functions to a bigger server

Scaling up an on-prem deployment means deploying the same stage to a larger saved server. No cluster is needed.

**In studio**

1. Open **Resources** in the sidebar and save the bigger server in the **Servers** card (see
   [Servers](../servers.md)).
2. Open **Deploy**. Under **Run on** pick **One machine** and choose the new server.
3. Click deploy. The old server keeps running until you remove the deployment there.

**From the terminal**

```bash
pskit resources onprem servers add big1 --ssh root@10.0.0.20 --pem ~/.ssh/edge.pem
pskit deploy --server big1          # the stage remembers big1 for the next deploys
```

## See also

* [Docker Swarm cluster](docker-swarm.md), [Kubernetes (k3s) cluster](kubernetes-k3s.md), [Nomad cluster](nomad.md)
* [Replicas, scale and capacity alerts](replicas-and-alerts.md)
* [Load balancers](../load-balancers.md), [Placement](../placement.md), [Database scaling](../database-scaling.md)
* [Network map](../network-map.md), [Firewall rules](../firewall.md)
* Reference: [cluster.md](../../cluster.md)
