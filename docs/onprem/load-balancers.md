# On-prem load balancers

Search terms: load balancer, LB, nginx, OpenResty, round robin, sticky sessions, weighted, ip hash,
least connections, least time, shared load balancer, one URL, attach, detach

An on-prem load balancer is a saved server that runs OpenResty (nginx with Lua) in Docker and spreads HTTP requests
over the servers that run your functions. Users call one URL; the load balancer picks a server per request, retries
another one when a server fails, and skips a server that is down. pskit writes and reloads the nginx config for you
(checked with `nginx -t` first, reloaded without dropping connections).

## The two kinds of on-prem load balancer

pskit has two kinds of on-prem load balancer. Both run the same OpenResty image and the same algorithms.

| Kind | Command | Serves | URL shape | Studio |
|---|---|---|---|---|
| **Cluster load balancer** (one per cluster) | `pskit cluster balancer set CLUSTER SERVER` | the deployments of **one** cluster, one **port** per deployment | `http://lb/` (port 80), `http://lb:8081/`, ... | **Scaling cluster → Load balancer** card |
| **Named (shared) load balancer** | `pskit lb create NAME --server SERVER` | many projects and clusters, one **path** each | `http://lb/orders/`, `http://lb/billing/` | **Load balancers** page |

The load balancer server must be **outside** the clusters it serves, and must reach each backend's functions port.

## The six load balancing algorithms and when to use each

The on-prem load balancer has six algorithms. **Static** ones follow a fixed rule; **dynamic** ones measure live
load per request. The default is `least_connections`. `pskit lb algorithms` prints the full pros and cons; the
studio's algorithm picker shows them with an animation.

| Algorithm (studio label) | Kind | How it picks a server | Use it when | Watch out |
|---|---|---|---|---|
| `round_robin` (Round robin) | static | each server in turn | servers of the same size, requests of about the same cost | ignores load; not sticky |
| `sticky_round_robin` (Sticky round robin) | static | the first request picks a server; a cookie keeps the session there | per-user state in memory, uploads in parts, WebSockets | uneven with a few busy users; sessions move when a server joins or leaves; clients without cookies are spread like round robin |
| `weighted_round_robin` (Weighted round robin) | static | in turn, a weight 3 server gets three requests per one of a weight 1 server | servers of different sizes; draining a server slowly | weights are set by hand |
| `ip_hash` (IP hash) | static | the client IP always maps to the same server | sticky without cookies (API clients, devices) | many users behind one NAT land on one server |
| `least_connections` (Least connections) | dynamic | fewest requests in progress (default) | mixed workloads, long requests (uploads, reports, streaming) | a fast and a slow server can look alike |
| `least_time` (Least time) | dynamic | lowest average response time x requests in progress | latency-sensitive APIs on uneven hardware | can pile onto one fast server until it slows; each load balancer measures on its own |

Aliases are accepted: `rr`, `sticky`, `wrr`, `ip`, `least_conn`, `fastest`, and dashed forms. A **weight** (1..100
per saved server, `--weight app1=3`) is used by weighted round robin, least connections and least time.

## Pick a load balancer topology

On-prem load balancers can be arranged in three ways. Pick the one that matches how many projects and clusters you
run.

| Topology | When | How |
|---|---|---|
| **A single load balancer for one project** | one project, one public URL | the cluster's own load balancer, or a named one with `provider.options.balancer` |
| **One common (shared) load balancer for several projects and clusters** | several projects or clusters behind one address, each under its own path | one named load balancer; attach each cluster, or name it in each project |
| **Separate load balancers per project or cluster** | isolation (public vs internal), different algorithms, different networks | one named load balancer (or cluster load balancer) per project or cluster, each on its own server |

The sections below give the steps for each.

## Topology 1: a single load balancer for one project on a cluster

A cluster load balancer gives every deployment of one cluster one URL. The first deployment uses the load
balancer's port (80); each further deployment on the same cluster needs its own `balancer_port`.

**In studio**

1. Save the load balancer server under **Resources → Servers** (it must not be in the cluster).
2. Open **Scaling cluster**, select the cluster, find the **Load balancer** card and click **+ Set up load balancer**.
3. In **Set up a load balancer for prod** pick the **Server**, the **Port** (default 80), optionally the **Address in
   the URL (optional)**, and **How it spreads requests** (the algorithm, plus **Weights (optional)**).
4. Click **Set up**. Deploy the project; the **Deployed functions** card shows the public URL.
5. Later: **Sync now** rewrites the config, **Show log** reads the access log, **Change** opens the same drawer
   (button **Apply**), **Remove** stops nginx.

**From the terminal**

```bash
pskit resources onprem servers add lb1 --ssh root@10.0.0.9 --pem ~/.ssh/edge.pem
pskit cluster balancer set prod lb1 --algorithm least_time --weight edge1=2   # --port 80, --address IP
pskit deploy --cluster prod          # prints: Public URL (load balancer on lb1): http://10.0.0.9
pskit cluster balancer logs prod -n 200
pskit cluster balancer sync prod     # after the load balancer was offline
pskit cluster balancer remove prod
```

A second deployment on the same cluster:

```yaml
provider:
  name: onprem
  options:
    cluster: {name: prod, replicas: 3, balancer_port: 8081}
```

## Topology 1b: a single load balancer for one project on one server

A project that runs on one server (or on placement groups) uses a named load balancer through
`provider.options.balancer`. The host must listen on the network, not on `127.0.0.1`.

**In studio**

1. Open **Load balancers**, click **+ Create load balancer**, fill **Name**, **Server**, **Port**, **How it spreads
   requests**, and click **Create**.
2. On the load balancer's panel turn on **Put this project on edge** (`provider.options.balancer`). Optionally set
   **Path** (empty: the service name) and **Algorithm for this route**.
3. Save, then **Deploy**. The route is added on deploy and dropped on remove.

**From the terminal**

```bash
pskit lb create edge --server lb1 --algorithm least_connections
```

```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0                     # listen on the network
    advertise: http://10.0.0.5:8080   # the address the load balancer calls
    balancer: edge                    # route /<service>/
    # balancer: {name: edge, path: shop, algorithm: sticky_round_robin, weights: {app1: 3}}
```

```bash
pskit deploy        # http://10.0.0.9/shop/ -> your functions
```

The path prefix is removed before the request reaches your functions (`/shop/orders` arrives as `/orders`) and
passed in `X-Forwarded-Prefix: /shop`. `/shop` redirects to `/shop/`.

## Topology 2: one common load balancer for several projects and clusters

One named load balancer can serve many projects and clusters, each under its own path. Its routes are stored on the
load balancer server, so projects in other folders or on other machines share it without overwriting each other.

```text
http://lb1/orders/   -> project orders (its server)
http://lb1/billing/  -> project billing
http://lb1/shop/     -> deployment shop on cluster prod
http://lb1/report/   -> deployment report on cluster batch
```

**In studio**

1. **Load balancers → + Create load balancer**. In **Attach clusters now (optional)** tick every cluster to serve.
2. Or later: on its panel, **Clusters** card, **+ Attach cluster**, pick the **Cluster**, **Attach**. The same is on
   **Scaling cluster → Shared load balancers → + Attach a load balancer**.
3. For a project on its own server(s), open the project in studio and turn on **Put this project on edge**.
4. The **Routes** card lists every route with **URL**, **Owner**, **Source**, **Algorithm** and **Backends**.

**From the terminal**

```bash
pskit lb create edge --server lb1
pskit lb attach edge --cluster prod       # every deployment on prod: http://lb1/<service>/
pskit lb attach edge --cluster batch
# in each other project folder (or on another machine):
pskit lb create edge --server lb1         # finds the running one and adds it; port and algorithm are kept
# then provider.options.balancer: edge in that project's pskit.yml, and pskit deploy
pskit lb status edge                      # every route, marking those of other projects
```

Each deployment on an attached cluster gets `/<service>/`, or `/<service>-<stage>/` when two stages of one service
share it. A path belongs to one deployment (`pskit-<service>-<stage>`); another one gets an error and must pick
another path. A project's own `balancer` setting wins over the cluster route.

## Topology 3: separate load balancers per project or cluster

Separate on-prem load balancers keep projects or clusters apart, for example a public `edge` and an `internal`
one, each on its own server with its own algorithm.

```bash
pskit lb create edge --server lb1 --algorithm least_time
pskit lb create internal --server lb2 --algorithm round_robin
pskit lb attach edge --cluster prod
pskit lb attach internal --cluster batch
```

A project can be on several load balancers at once with a list:

```yaml
provider:
  name: onprem
  options:
    balancer:
      - edge
      - {name: internal, path: orders-api, algorithm: ip_hash}
```

Each cluster can also have its own cluster load balancer (`pskit cluster balancer set prod lb3`) next to attached
named ones. In studio, create each one with **+ Create load balancer** and attach clusters or projects as in
Topology 2; the studio's **Put this project on** switch handles one load balancer per project, so use the YAML
list (studio **YAML** page) for several.

## Detach a cluster or a project from a load balancer

Detaching removes routes only. The deployments keep running and users reach the servers on their own ports.

| What | In studio | From the terminal |
|---|---|---|
| A cluster from a named load balancer | **Load balancers → Clusters → Detach**, or **Scaling cluster → Shared load balancers → Detach** | `pskit lb detach edge --cluster prod` |
| A project from a named load balancer | turn off **Put this project on edge**, save, deploy | remove `balancer` from `provider.options`, then `pskit deploy` |
| One route, whoever owns it | **Load balancers → Routes → Remove** | `pskit lb routes remove edge orders` (or `port-8081`) |
| The cluster's own load balancer | **Scaling cluster → Load balancer → Remove** | `pskit cluster balancer remove prod` |

## Change, sync, inspect and remove a named load balancer

A named load balancer is managed from the **Load balancers** page (buttons **Refresh**, **Update**, **Sync**,
**Logs**, **Remove**, **Forget**) or with `pskit lb`.

```bash
pskit lb list
pskit lb update edge --algorithm weighted_round_robin --weight app1=3 --weight app2=1   # --port, --address
pskit lb sync edge             # rewrite its settings and every route from this project
pskit lb logs edge -n 200      # one line per request; upstream= is the server that answered
pskit lb remove edge           # --force when other projects still use it (their URLs stop too)
pskit lb forget edge           # this project only; it keeps running for the others
```

When the studio shows "The server runs other settings than the saved ones", another machine changed it: **Sync**
writes this project's settings back, **Update** changes them.

## What the on-prem load balancer does with each request

The on-prem load balancer picks a server with the algorithm; a server that fails 3 times rests for 10 seconds; a
request that cannot connect, times out, or gets 502 / 503 / 504 is retried on another server (never a `POST` that
already reached one). WebSocket upgrades pass through, request bodies up to 100 MB, and it sets `X-Forwarded-For`,
`X-Real-IP` and `X-Forwarded-Proto`. It speaks HTTP only: put a TLS terminator in front for HTTPS. A cluster master
that does not serve requests is listed as a `backup`, except with the hashing algorithms (`sticky_round_robin`,
`ip_hash`): nginx does not allow `backup` with hash, so there the master shares the requests.

## Load balancers with placement groups

A project whose functions are split into [placement groups](placement.md) gets one route `/<service>/` to the
servers of every group. With `options.balancer`, `placement.gateway` is on by default, so a request that lands on
the wrong group's server is passed on. A load balancer attached to clusters reaches only those clusters' servers.

## Load balancer for databases

Database traffic does not go through OpenResty. A replicated PostgreSQL uses pgpool-II and MySQL / MariaDB use
ProxySQL as the database load balancer; MongoDB needs none. See
[Database scaling](database-scaling.md#add-a-database-load-balancer-pgpool-ii-or-proxysql).

## See also

* [Scaling options compared](scaling/README.md), [Replicas and alerts](scaling/replicas-and-alerts.md)
* [Placement](placement.md), [Database scaling](database-scaling.md)
* [Firewall rules](firewall.md), [Network map](network-map.md)
* Reference: [load-balancers.md](../load-balancers.md), [cluster.md](../cluster.md#load-balancer-one-url-for-the-whole-cluster-optional)
