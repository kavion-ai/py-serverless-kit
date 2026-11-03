# HashiCorp Nomad scaling cluster

Search terms: Nomad, HashiCorp Nomad, nomad job, nomad agent, Consul, create cluster, join server, drain,
web replica per server, no load balancer, scale out, pskit cluster nomad

A HashiCorp Nomad scaling cluster in pskit runs the Nomad agent (with the Docker driver) on a **master** server and
on every joined server. Unlike Swarm and k3s, Nomad has **no built-in load balancing**: the master's port answers
with the main replica, and each other server's port answers with that server's own web replica.

## How a Nomad cluster serves requests

A Nomad cluster deployment is one Nomad job with two task groups:

| Task group | Count | Where | Answers on |
|---|---|---|---|
| `main` | 1 | the master (pinned) | the master's functions port (default 8080) |
| `web` | `replicas` | servers other than the master, **at most one per server** (`distinct_hosts`) | that server's functions port |

So on Nomad, web replicas above the number of joined servers cannot be placed and the cluster counts as full: join
more servers instead of raising `replicas`. Containers use host networking. For **one URL** for all servers, add a
[load balancer](../load-balancers.md) (optional). `pskit deploy` succeeds without one: it waits until the main
replica answers `/__pskit/health` on the master, and prints each allocation and the main replica's logs every
10 seconds while it waits.

## Before you create a Nomad cluster

A Nomad cluster needs:

* Docker running on **your** machine to build the image.
* Linux servers with SSH and root or passwordless `sudo`, and outbound HTTPS the first time
  (`releases.hashicorp.com`, Docker install).
* The Nomad ports open: TCP 4646 (HTTP API), TCP 4647 (RPC) and TCP + UDP 4648 (gossip) on the master, from the
  workers. See [Firewall rules](../firewall.md).
* The servers saved once (`pskit resources onprem servers add ...`).

## Create a Nomad cluster in studio

The studio creates a Nomad cluster from the **Scaling cluster** page.

1. Open **Scaling cluster** and click **+ New cluster**.
2. Set **Cluster name**, pick **Orchestrator → HashiCorp Nomad**, choose the **Master server**, and optionally the
   **Cluster address (optional)**.
3. **Master serves requests** is off by default on Nomad: the master stays a backup for load balancers.
4. Click **Create**. pskit installs Docker and the Nomad agent as a systemd unit.

## Create a Nomad cluster from the terminal

The `pskit cluster create` command with `--orchestrator nomad` installs the Nomad agent on the master.

```bash
pskit cluster create prod --orchestrator nomad --master edge1 --advertise 10.0.0.5
pskit cluster create prod -o nomad --master edge1 --nomad-version 1.11.3   # pin another Nomad release
```

## Join a server to a Nomad cluster

Joining a server to a Nomad cluster installs Docker and the Nomad client there and points it at the master.

**In studio**: on **Scaling cluster**, **Servers** card, **+ Join server**, pick the **Server**, **Join**.

**From the terminal**

```bash
pskit cluster join prod edge2 --advertise 10.0.0.6
```

## Deploy functions to a Nomad cluster

Deploying to a Nomad cluster submits the job through the Nomad API on the master. Data of the main replica lives in
`/var/lib/pskit/<stack>` on the master.

**In studio**: on **Scaling cluster** turn on **Deploy this project's functions to prod**, set **Web replicas**
(no more than the joined servers), save, then **Deploy → Run on → Scaling cluster**.

**From the terminal**

```yaml
provider:
  name: onprem
  options:
    cluster: {name: prod, replicas: 2}     # 2 joined servers, one web replica each
```

```bash
pskit deploy
pskit cluster requests prod     # each server's URL and its share of the HTTP requests
```

## Remove (drain) a server from a Nomad cluster

Removing a server from a Nomad cluster drains its node through the Nomad API (120-second deadline), stops the agent,
and purges the node.

**In studio**: **Remove** on the server's row, then **Remove server**.

**From the terminal**

```bash
pskit cluster leave prod edge2
```

## Remove the whole Nomad cluster

Removing the whole Nomad cluster stops the jobs, uninstalls the Nomad agent (binary, unit, config and data) from
every server and the master, and forgets the cluster.

```bash
pskit cluster remove prod --uninstall [--delete-data]
```

In studio: **Remove** on the master's row, then **Uninstall** or **Uninstall and delete data**.

## See also

* [Scaling options compared](README.md), [Docker Swarm](docker-swarm.md), [Kubernetes (k3s)](kubernetes-k3s.md)
* [Replicas, scale and capacity alerts](replicas-and-alerts.md)
* [Load balancers](../load-balancers.md), [Firewall rules](../firewall.md)
* Reference: [cluster.md](../../cluster.md)
