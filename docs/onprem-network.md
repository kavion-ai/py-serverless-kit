# Network and firewall rules (on premises)

Which machine must accept **inbound** connections, and which must be allowed **outbound**, at each step: saving
servers, deploying, running, clusters, joining servers, load balancers, function groups on several servers, and
resources / triggers. Ports in *italics* are defaults you can change.

**You do not have to work these out by hand.** Every step prints the rules it just made necessary, with your
servers' names and addresses and `ufw` commands: `pskit cluster create`, `pskit cluster join`, `pskit deploy`
(one server, function groups or a cluster), `pskit lb create`, `pskit lb attach`, `pskit cluster balancer set`,
a project's `balancer` route, and `pskit resources onprem create`. `pskit firewall` lists everything the project
needs now, per server (`--server edge2`, `--json`); the studio shows the same in a **Firewall** panel (Deploy,
cluster and load balancer pages) and in each job's output:

```
Firewall - edge2 joined cluster prod (open these; docs/onprem-network.md):
  edge1 (10.0.0.5)
    [REQUIRED] inbound  TCP 2377     from edge2 (10.0.0.6)  - cluster prod: Swarm cluster management (managers)
    [REQUIRED] inbound  UDP 4789     from edge2 (10.0.0.6)  - cluster prod: Swarm overlay network (VXLAN)
    ...
    ufw on edge1:
      sudo ufw allow from 10.0.0.6 to any port 2377 proto tcp
```

**Legend:** 🟥 **required** (it does not work without it) · 🟨 **needed for that feature** · 🟩 optional
(convenience; pskit falls back to an SSH tunnel)

## The machines

| Role | What it is |
|---|---|
| **Admin machine** | where you run `pskit` / the studio (your laptop, a CI runner) |
| **Function server** | runs a function host (one machine, or one placement group) |
| **Cluster master / worker** | servers of a scaling cluster (Swarm, k3s, Nomad) |
| **Load balancer server** | runs OpenResty for `pskit lb` or `pskit cluster balancer` |
| **Resource server** | runs an on-prem service (Redis, Postgres, MinIO, SMTP, ...) |
| **Users** | browsers, apps, other systems calling your functions |

`FN_PORT` below is `provider.options.port` (*8080*), or a placement group's own `port`.

---

## 1. Always: the admin machine reaches every server over SSH

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | Admin machine | **every** saved server (function, cluster, load balancer, resource) | **TCP *22*** (the server's SSH port) | scripts, copying the release / image (`scp`), logs, tests, status |
| 🟥 | every server, **outbound** | Internet **TCP 443 / 80** | — | first time only: install Docker (`get.docker.com`, distro repos), pull images (Docker Hub), k3s (`get.k3s.io`, GitHub), Nomad (`releases.hashicorp.com`) |
| 🟥 | Admin machine, **outbound** | Internet **TCP 443** | — | PyPI / npm while packaging; `python: bundle` / `node: bundle` downloads; Docker base images for `method: docker` |

Servers with no Internet: preinstall Docker (and k3s / Nomad), and load the images yourself (`docker load`).
pskit copies the function image itself over SSH, so no registry is needed.

## 2. Saving a server (`pskit resources onprem servers add`, studio "Add server")

| | From | To | Port |
|---|---|---|---|
| 🟥 | Admin machine | the new server | **TCP *22*** |

Nothing else; "Test" only uses SSH.

## 3. Deploy to one server (`method: ssh`, `docker`, or `--server NAME`)

**During deploy**

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | Admin machine | function server | **TCP *22*** | copy the release / image, start it, wait for `/__pskit/health` (checked on the server itself) |
| 🟨 | function server, outbound | Internet **TCP 443** | — | `method: docker` with Docker missing: install it |

**After deploy (running)**

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | **Users** | function server | **TCP `FN_PORT`** (*8080*) | HTTP routes, workflow starts, the AWS-compatible APIs (SQS, Lambda) |
| 🟩 | Admin machine | function server | TCP `FN_PORT` | logs, `pskit test`, studio; **closed is fine**: pskit tunnels through SSH 22 |

Set `options.host: 0.0.0.0` (bind) so the port answers on the LAN, and `options.advertise` when users reach it by
another address (NAT, DNS name). A host bound to `127.0.0.1` is only reachable through the SSH tunnel.

## 4. Functions on several servers (`provider.options.placement`)

Every group is its own host, and the groups call each other directly. **Open `FN_PORT` of every group host to every
other group host** (a full mesh between them):

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | every group host | **every other** group host | **TCP its `FN_PORT`** | `invoke()`, HTTP routes of another group, workflow steps, queues / buckets owned by another group, topics |
| 🟥 | other groups | **default group** host | TCP its `FN_PORT` | logs and counts (every second), workflow starts (workflows run on the default group) |
| 🟥 | Users | the group hosts that serve HTTP (or only the load balancer, §7) | TCP `FN_PORT` | any group answers every route; it passes others on |

A group on `local: true` (your machine) must be reachable from the other groups: set its `advertise` and open its
port. Calls between groups carry a shared token (`x-pskit-token`); still keep these ports to the servers' network.

## 5. Scaling cluster: create (`pskit cluster create prod --master edge1`)

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | Admin machine | master | **TCP *22*** | install the orchestrator |
| 🟥 | master, outbound | Internet **TCP 443** | — | Docker / k3s / Nomad downloads |

## 6. Scaling cluster: join a server (`pskit cluster join prod edge2`) and run

**Between all cluster servers** (master ↔ workers, worker ↔ worker). Open on **every** cluster server, from the
other cluster servers only:

| Orchestrator | 🟥 Ports between cluster servers |
|---|---|
| **Docker Swarm** | **TCP 2377** (to the master / managers: cluster management) · **TCP + UDP 7946** (all ↔ all: node discovery) · **UDP 4789** (all ↔ all: overlay network) |
| **Kubernetes (k3s)** | **TCP 6443** (to the master: API, agents register) · **UDP 8472** (all ↔ all: Flannel VXLAN) · **TCP 10250** (master → workers: kubelet, logs) |
| **HashiCorp Nomad** | **TCP 4646** (master: HTTP API) · **TCP 4647** (workers → master: RPC) · **TCP + UDP 4648** (servers ↔ servers: gossip) |

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | Admin machine | the joining server **and** the master | **TCP *22*** | install the agent; ask the master for a join token; copy the function image (in parts, over SSH) |
| 🟥 | joining server, outbound | Internet **TCP 443** | — | Docker / k3s / Nomad downloads |
| 🟥 | every cluster server | the **master** | **TCP `FN_PORT`** | web replicas hand state to the main replica (queues, logs, workflow runs) |
| 🟥 | **Users** | **every** cluster server (Swarm / k3s), or every **worker** (Nomad) | **TCP `FN_PORT`** | without a load balancer users call any server; with one (§7), only the load balancer needs this |

Leaving (`pskit cluster leave`) needs only SSH.

## 7. Load balancer (`pskit lb create`, `pskit lb attach`, `pskit cluster balancer set`)

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | Admin machine (**every** project / machine that uses it) | load balancer server | **TCP *22*** | install, add routes, status, logs |
| 🟥 | load balancer, outbound | Internet **TCP 443** | — | first time: Docker install, `openresty/openresty` image |
| 🟥 | **Users** | load balancer server | **TCP *80*** (its port), plus each **`balancer_port`** of a cluster's own load balancer (*8081*, ...) | the public URLs: `http://lb/<path>/` |
| 🟥 | load balancer server | **every backend**: the function server, every placement group host, or every cluster server (Nomad: workers and master) | **TCP `FN_PORT`** of each | forward requests, health checks |

With a load balancer you can **close `FN_PORT` to users** on the function / cluster servers and allow it only
from the load balancer (and from the other cluster servers / group hosts, §4 and §6). Attaching a cluster
(`pskit lb attach edge --cluster prod`) adds no new ports: the cluster's servers just become backends.

## 8. Resources and triggers ("attaching events")

**Built-in triggers** (schedule, built-in queue, storage, topic, workflow) run inside the host: **no extra port**.
With placement, they use the group-to-group rules of §4.

**On-prem services** (`pskit resources onprem create ... --service NAME`, optionally `--cluster`):

| | From | To | Port |
|---|---|---|---|
| 🟥 | every function host that uses it (with `--cluster`: **every cluster server**) | resource server | the service port below |
| 🟩 | Admin machine | resource server | its web console port (the studio can also open it over SSH) |
| 🟥 | Admin machine | resource server | TCP *22* (create, check, data browser) |

| Service | Port | Console |
|---|---|---|
| Redis, Valkey, Dragonfly, KeyDB | 6379 | |
| PostgreSQL | 5432 | |
| MySQL, MariaDB | 3306 | |
| MongoDB | 27017 | |
| RabbitMQ, LavinMQ | 5672 | 15672 |
| ElasticMQ (SQS) | 9324 | 9325 |
| MinIO, RustFS, S3 compatible | 9000 | 9001 (S3 compatible: 9000) |
| Kafka (Redpanda / Apache) | 9092 | |
| NATS | 4222 | 8222 |
| LocalStack, LocalEmu | 4566 | 4566 |
| Secrets Manager compatible | 4584 | 4584 |
| OpenBao | 8200 | |
| Azurite | 10000 | |
| fake-gcs | 4443 | |
| Memcached | 11211 | |
| Mosquitto (MQTT) | 1883 | |
| Mailpit | 1025 | 8025 |
| Others (Grafana 3000, Prometheus 9090, Keycloak 8080, ...) | see `pskit resources onprem services` | |

**Replicated database** (`--primary db1 --replica db2 --replica db3 [--balancer lb1]`, studio *Scaling → Primary +
read replicas*):

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | every replica | primary | the database port (5432 / 3306 / 27017) | replicas copy the primary's changes |
| 🟥 | every MongoDB member | every other member | 27017 | replica set heartbeats and elections |
| 🟥 | load balancer server | every member | the database port | pgpool-II / ProxySQL forward queries |
| 🟥 | every function host | load balancer | 6432 (pgpool-II) / 6033 (ProxySQL) | the functions' single address |
| 🟥 | every function host | every member (no load balancer, or MongoDB) | the database port | `WRITE_URL`, `READ_URLS`, the replica set URL |
| 🟥 | Admin machine | every member and the load balancer | TCP *22* | create, add / remove replicas, status |

**SMTP server** (`smtp` resource, receives mail and runs `smtp` triggers):

| | From | To | Port | Why |
|---|---|---|---|---|
| 🟥 | **Internet mail servers** | SMTP server | **TCP 25** (and an MX record pointing at it) | incoming mail |
| 🟥 | SMTP server | function host (placement: any group host) | **TCP `FN_PORT`** | delivers each mail to `/__pskit/smtp/<name>` |

**External drivers** (`options.driver` on a queue / storage resource): **outbound** from every function host (and
every cluster server) to that service: Redis TCP 6379; SQS, S3, Azure, GCS, Alibaba, Cloudflare **TCP 443**.

**Capacity alerts** (`pskit cluster alerts --webhook`): outbound **TCP 443** from the machine running
`pskit cluster watch` / the studio to the webhook (Slack, Teams, ...).

## 9. The studio and browser terminals

The studio listens on `127.0.0.1` of the admin machine, and browser terminals (ttyd) on `127.0.0.1:7681+`: no
firewall change; they reach servers over SSH.

---

## Example: one load balancer, two placement groups

```
users ──80──► lb1 ──8080──► app1 (group api, default)  ◄──8080──►  gpu1 (group gpu)
admin ──22──► lb1, app1, gpu1
```

```bash
# lb1
sudo ufw allow from <admin-ip> to any port 22 proto tcp
sudo ufw allow 80/tcp
# app1 and gpu1
sudo ufw allow from <admin-ip> to any port 22 proto tcp
sudo ufw allow from <lb1-ip> to any port 8080 proto tcp     # the load balancer
sudo ufw allow from <app1-ip> to any port 8080 proto tcp    # on gpu1: the other group
sudo ufw allow from <gpu1-ip> to any port 8080 proto tcp    # on app1: the other group
```

## Example: Docker Swarm cluster (edge1 master, edge2, edge3) behind lb1

```bash
# on every edge server, from the other edge servers:
sudo ufw allow from <edge-subnet> to any port 2377 proto tcp
sudo ufw allow from <edge-subnet> to any port 7946
sudo ufw allow from <edge-subnet> to any port 4789 proto udp
sudo ufw allow from <edge-subnet> to any port 8080 proto tcp   # replicas -> main replica
sudo ufw allow from <lb1-ip> to any port 8080 proto tcp        # the load balancer
sudo ufw allow from <admin-ip> to any port 22 proto tcp
```

Cloud security groups: the same rules as inbound rules on each instance's group; outbound "all" is the usual
default.
