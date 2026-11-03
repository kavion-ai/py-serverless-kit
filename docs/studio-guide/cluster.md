# Scaling cluster page in studio

Search terms: scaling cluster, cluster, Docker Swarm, Kubernetes, k3s, Nomad, master, join server, replicas, scale, capacity, cluster full alert, cluster load balancer, live requests, cluster logs, uninstall cluster

The **Scaling cluster** page runs the project's on-prem functions on several servers with **Docker Swarm**,
**Kubernetes (k3s)** or **HashiCorp Nomad**: a master server plus joined servers. Sidebar: **Scaling cluster** (⧉).
Clusters are stored in `.pskit/onprem-clusters.json`; the project uses one through `provider.options.cluster`. When
the project's provider is not `onprem`, a warning box says to switch it on Overview. The concepts and how to choose an
orchestrator are in [On-prem scaling](../onprem/scaling/README.md).

## Create a scaling cluster in studio

The studio **New scaling cluster** drawer installs an orchestrator on a master server over SSH.

1. Save your servers first ([Servers panel](servers.md), or **Add a server** in the drawer).
2. Open **Scaling cluster** and click **+ New cluster**.
3. **Cluster name** (lowercase letters, digits, `-`).
4. **Orchestrator**: Docker Swarm, Kubernetes (k3s) or HashiCorp Nomad. The help says what it is and which ports must
   be open between servers (Swarm: 2377/tcp, 7946/tcp+udp, 4789/udp; k3s: 6443/tcp, 8472/udp, 10250/tcp).
5. **Master server** (required): runs the control plane and the main replica (schedules, queues, logs, data). Root or
   passwordless sudo.
6. **Cluster address (optional)**: the master's IP the other servers reach (for example its private IP). Default: its
   SSH host.
7. **Master serves requests**: **Send requests to the master too, not only to the joined servers**.
8. Click **Create**. The log streams below while it is **Installing…**.

When there are several clusters, buttons at the top (`name · orchestrator`) switch between them.

```bash
pskit cluster create prod --orchestrator swarm --master edge1
pskit cluster list
```

## Deploy the project's functions to a cluster in studio

The **Deploy this project's functions to <cluster>** switch on a cluster's card writes `provider.options.cluster`.

1. Turn the switch on. More fields appear:

   | Field | Key | Default |
   |---|---|---|
   | **Web replicas** | `cluster.replicas` | 2 (copies behind the load balancer, plus 1 main replica on the master) |
   | **CPU per replica** | `cluster.cpu` | 0.25 cores reserved |
   | **Memory per replica (MB)** | `cluster.memory` | 256 |
   | **Port on the load balancer** | `cluster.balancer_port` | the cluster load balancer's port; each deployment needs its own |

2. Press **Save**, then open [Deploy](deploy.md) and click **Deploy** (Run on → **Scaling cluster**).

Reservations decide how many replicas fit on a server; when none fit, the cluster counts as full.

```yaml
provider:
  name: onprem
  options:
    cluster: {name: prod, replicas: 4, cpu: 0.5, memory: 512}
```

```bash
pskit deploy --cluster prod
```

## Join, remove and watch cluster servers in studio

The **Servers** card of a cluster shows each server's state and **CPU**, **Memory** and **Disk** meters against the
cluster's limits ("A server is full at X% CPU, Y% memory or Z% disk"). It refreshes every 30 s; **Refresh** and
**Check & alert** (check now and send the alert if every server is full) are at the top.

- **+ Join server** opens **Join a server to <cluster>**: pick the **Server** (or add one), an optional **Cluster
  address** (its IP in the cluster network), and click **Join**.
- **Remove** on a joined server asks **Remove <server> from <cluster>?**: its replicas move to the other servers
  first, then its agent stops. The saved server is kept.
- **Remove** on the master asks **Uninstall cluster <name>?**: deployments stop, its load balancer is removed and the
  orchestrator is uninstalled from every server. Type the cluster name, then **Uninstall** or **Uninstall and delete
  data**.
- **Forget** (top) only stops pskit managing the cluster; servers and what runs on them are left as they are.
- The toggle **Send requests to the master <name> too** changes whether the master serves requests.

When the cluster is full, a banner "⚠ The cluster is full:" lists why, with **+ Join a server now**.

```bash
pskit cluster join prod edge2
pskit cluster leave prod edge2 --yes
pskit cluster set prod --master-serves
pskit cluster status prod
pskit cluster remove prod --uninstall --yes
```

## Put a load balancer in front of a cluster

A cluster can have its own load balancer (nginx in the container `pskit-lb` on a server outside the cluster) and can
be attached to [shared load balancers](load-balancers.md).

1. In the **Load balancer** card, click **+ Set up load balancer**.
2. **Server** (required): a saved server outside the cluster, root or passwordless sudo. **Port** (80 for
   `http://its-address/`). **Address in the URL (optional)**.
3. **How it spreads requests**: pick an algorithm card (static or dynamic) and, for weighted ones, **Weights**.
4. Click **Set up** (**Apply** when changing). The card then shows its state, CPU / Memory / Disk, and each
   deployment's **Public URL**, with **Sync now**, **Show log**, **Change** and **Remove**.

**Shared load balancers** lists the named load balancers attached to this cluster (each deployment gets
`http://LB/<service>/`). **+ Attach a load balancer** picks one and **Attach**; **Detach** removes the cluster's
routes from it.

```bash
pskit cluster balancer set prod lb1
pskit lb attach edge --cluster prod
```

Algorithms are explained in [On-prem load balancers](../onprem/load-balancers.md).

## Scale replicas and watch requests and logs on a cluster

The lower cards of a cluster:

- **Deployed functions**: each deployment, its endpoint, running / desired replicas and **Web replicas** with
  **Scale** (until the next deploy; keep the number in Web replicas above).
- **Live requests**: pick a deployment and turn **Live** on. A table shows each server's answers, HTTP share and URL,
  and the recent requests (time, server, replica, request, status, function).
- **Live logs**: the log tail of a deployment, the same as on one machine.
- **Resources on this cluster**: services created with *Where → Scaling cluster*.
- **Firewall: <cluster>**: the [Firewall panel](firewall.md) for the cluster's servers.

```bash
pskit cluster scale prod --replicas 6
pskit cluster requests prod --follow
```

## Alert when every cluster server is full

The **When every server is full** card calls a function and / or a webhook when no server has room.

1. Set the limits: **CPU full at %**, **Memory full at %**, **Disk full at %**.
2. **Alert function**: a function of this project, deployed (any on-prem stage); **Stage** (empty = any). The
   function gets `event.data` = `{type: "pskit.cluster.capacity", cluster, message, subject, reasons, nodes, ...}`.
3. **Webhook (optional)**: Slack, Teams or any URL gets the same JSON.
4. **Cooldown (minutes)**: at most one alert per cooldown.
5. **Watch while the studio runs** with **every (seconds)**.
6. Click **Save**, then **Send test alert**. **Recent alerts** lists what was sent.

```bash
pskit cluster alerts prod --function notify-devops --test
pskit cluster watch prod --interval 60
pskit cluster check prod
```

More: [Replicas and alerts](../onprem/scaling/replicas-and-alerts.md).

## See also

- [On-prem scaling](../onprem/scaling/README.md): [Docker Swarm](../onprem/scaling/docker-swarm.md),
  [Kubernetes (k3s)](../onprem/scaling/kubernetes-k3s.md), [Nomad](../onprem/scaling/nomad.md)
- [Load balancers page](load-balancers.md)
- [Deploy page](deploy.md)
- [Cluster reference](../cluster.md)
