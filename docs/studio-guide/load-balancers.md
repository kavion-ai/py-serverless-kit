# Load balancers page in studio

Search terms: load balancer, LB, shared load balancer, OpenResty, nginx, round robin, sticky sessions, weighted round robin, ip hash, least connections, least time, routes, attach cluster, one URL many projects, pskit lb

The **Load balancers** page manages shared on-prem load balancers: one URL in front of many projects and clusters, by
path (`http://lb/orders/`, `http://lb/billing/`). pskit runs OpenResty (nginx) in Docker on a saved server and keeps
the routes on that server, so projects in other folders or on other machines share it. Sidebar: **Load balancers**
(⇆). It does the same as `pskit lb`. Load balancers are stored in `.pskit/onprem-balancers.json`; a project uses one
through `provider.options.balancer`. When the project's provider is not `onprem`, a warning box says so (clusters can
still use a load balancer). The algorithms and setups are explained in
[On-prem load balancers](../onprem/load-balancers.md).

## Create a shared load balancer in studio

The studio **New load balancer** drawer installs OpenResty on one saved server.

1. Save one more server for it on the [Servers panel](servers.md) (or **+ Add a server** in the drawer). It must not
   be part of a cluster or used by another load balancer.
2. Open **Load balancers** and click **+ Create load balancer**.
3. **Name**: lowercase letter first; lowercase letters, digits and `-` (up to 31).
4. **Server** (required): root or passwordless sudo.
5. **Port** (80 for `http://its-address/`) and **Address in the URL (optional)** (default: its SSH host).
6. **How it spreads requests**: pick an algorithm card. **Static** cards (a fixed rule): Round robin, Sticky round
   robin, Weighted round robin, IP hash. **Dynamic** cards (decided per request from live load): Least connections,
   Least time. Each card has an animation, pros, cons and "Best for". Weighted algorithms show **Weights** (1 to 100
   per server; empty = 1).
7. **Attach clusters now (optional)**: tick clusters; every deployment on them gets `/<service>/`.
8. Click **Create** (it shows **Installing…** while pskit installs Docker and OpenResty over SSH). The log streams
   below.

```bash
pskit lb algorithms
pskit lb create edge --server lb1 --algorithm least_time
pskit lb list
```

## Put this project behind a load balancer in studio

The **Put this project on <name>** switch on a load balancer's panel writes `provider.options.balancer`.

1. Select the load balancer in the table.
2. Turn on **Put this project on <name> (provider.options.balancer)**.
3. **Path**: empty = the service name (`<url>/<service>/`).
4. **Algorithm for this route**: empty = the load balancer's own; or another algorithm for this project only.
5. Press **Save**, then [Deploy](deploy.md): the route is added on deploy and dropped on remove.

```yaml
provider:
  name: onprem
  options:
    balancer: {name: edge, path: orders, algorithm: ip_hash}
```

A plain `balancer: edge` uses the default path and algorithm.

## Manage a load balancer in studio

The studio load balancer panel shows the selected load balancer's state, its server's **CPU**, **Memory** and
**Disk**, and these buttons:

| Button | What it does | CLI |
|---|---|---|
| **Refresh** | Read its state again | `pskit lb status edge` |
| **Update** | **Update load balancer <name>**: **Port**, **Address in the URL**, **How it spreads requests**, weights; **Apply** | `pskit lb update edge --algorithm weighted_round_robin --weight app1=3` |
| **Sync** | Rewrite its settings and every route now | `pskit lb sync edge` |
| **Logs** / **Refresh logs** | Recent requests (`upstream=` is the server that answered) | `pskit lb logs edge -n 200` |
| **Remove** | Stops OpenResty and its URL stops answering. When it also serves other projects, you must type its name and click **Remove anyway** | `pskit lb remove edge --yes` |
| **Forget** | Only this project stops managing it; it keeps running for others | `pskit lb forget edge` |

When OpenResty is not running, a box says **Sync** starts it again. When the server runs other settings than the
saved ones ("another machine may have changed it"), **Sync** writes this project's settings back and **Update**
changes them.

## Attach clusters and read routes on a load balancer

The **Clusters** card lists attached clusters. **+ Attach cluster** opens **Attach a cluster to <name>**: pick the
**Cluster** and click **Attach**. **Detach** asks **Detach cluster <c> from <name>?**; the deployments keep running.

The **Routes** card lists every route: **URL**, **Owner** (this project, or "a deployment of another project or
machine"), **Source**, **Algorithm** (or the load balancer's) and **Backends** (address:port; "backup" answers only
while every other server is down). **Remove** on a route asks **Remove /<path>/ from <name>?**.

```bash
pskit lb attach edge --cluster prod
pskit lb detach edge --cluster prod
pskit lb routes remove edge xyz
```

The **Firewall: <name>** card is the [Firewall panel](firewall.md) for the load balancer's server.

## See also

- [On-prem load balancers](../onprem/load-balancers.md)
- [Scaling cluster page](cluster.md)
- [Network map](network.md) and [Firewall panel](firewall.md)
- [Load balancer reference](../load-balancers.md)
