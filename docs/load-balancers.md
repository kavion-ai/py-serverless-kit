# Load balancers (on premises)

A load balancer is a saved server that runs OpenResty (nginx with Lua) in Docker and spreads HTTP requests over
the servers that run your functions. One load balancer can serve **many projects and clusters by path**:

```
http://lb1/xyz/...   ->  project xyz (its servers)
http://lb1/abc/...   ->  project abc
http://lb1/yyy/...   ->  every deployment on cluster prod, by service name
```

You can have several load balancers (`edge`, `internal`, ...). Each has a default algorithm; a project can pick
its own for its route.

## The six algorithms

`pskit lb algorithms` prints the trade-offs. The studio's **Load balancers** page shows the same with a small
animation of each.

| Algorithm | Kind | How it picks a server | Good for | Watch out |
|---|---|---|---|---|
| `round_robin` | static | each in turn | servers of the same size, requests of the same cost | ignores load; not sticky |
| `sticky_round_robin` | static | a user's first request picks one; a cookie keeps the session there | in-memory sessions, uploads in parts, WebSockets | busy users make it uneven; sessions move when a server joins or leaves |
| `weighted_round_robin` | static | in turn, `weight` times as often | servers of different sizes | weights are set by hand |
| `ip_hash` | static | the client IP always maps to the same server | sticky without cookies (devices, API clients) | many users behind one NAT land on one server |
| `least_connections` | dynamic | fewest requests in progress (default) | mixed workloads, long requests | a fast and a slow server can look alike |
| `least_time` | dynamic | lowest average response time x requests in progress | latency-sensitive APIs on uneven hardware | can favor one fast server until it slows down |

**Static** algorithms follow a fixed rule; **dynamic** ones measure live load per request. Open-source nginx has
no sticky cookie or least time (both are NGINX Plus), so pskit builds them: sticky hashes a cookie that holds the
first request's id (`hash ... consistent`), and least time runs `balancer_by_lua` with a moving average of each
server's response header time. A server that fails is retried on the next one and rests for 10 s.

`weight` (1..100, per saved server) is used by weighted round robin, least connections and least time.

## Create one and put projects on it

```bash
pskit resources onprem servers add lb1 --host 10.0.0.9 --user ubuntu --key ~/.ssh/lb1.pem
pskit lb create edge --server lb1 --algorithm least_time       # Docker + OpenResty on lb1, port 80
```

A project names it in `pskit.yml`; every `pskit deploy` updates its route and `pskit remove` drops it:

```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    advertise: http://10.0.0.5:8080      # the address the load balancer calls
    balancer: edge                       # route /<service>/
    # or: balancer: {name: edge, path: shop, algorithm: sticky_round_robin, weights: {app1: 3}}
```

The path prefix is removed before the request reaches your functions (`/shop/orders` arrives as `/orders`) and
sent in `X-Forwarded-Prefix: /shop`. `/shop` redirects to `/shop/`.

A **cluster** can be attached instead; every deployment on it gets `/<service>/` (or `/<service>-<stage>/` when
two stages of a service share the cluster), kept up to date on deploy, remove, join and leave:

```bash
pskit lb attach edge --cluster prod
pskit lb detach edge --cluster prod
```

A project's own `balancer` setting wins over the cluster's route for that deployment. A project whose
[placement groups](placement.md) run on several attached clusters gets one route, `/<service>/`, to the servers of
all of them; each server passes another group's routes on to it.

## Shared between projects and machines

The routes live **on the load balancer server** (`pskit-cluster/lb-edge/routes/*.json` next to the nginx files),
not in one project. Each change rewrites only its own route files, under a lock, after `nginx -t` checked the
whole config in a throwaway container, then reloads without dropping connections. So:

* projects in other folders, or deployed from other machines, share one load balancer;
* in another project, `pskit lb create edge --server lb1` finds the running one and adds it (its port and
  algorithm are kept);
* a path belongs to one deployment (`pskit-<service>-<stage>`); another one gets an error and picks another path;
* `pskit lb status edge` lists every route, marking those of other projects.

## Commands

```bash
pskit lb algorithms
pskit lb create edge --server lb1 [--port 80] [--algorithm least_time] [--weight app1=3]
pskit lb update edge --algorithm weighted_round_robin --weight app1=3 --weight app2=1
pskit lb list
pskit lb status edge                  # running?, server use, every route
pskit lb attach edge --cluster prod
pskit lb routes remove edge xyz       # whichever project owns it
pskit lb sync edge                    # rewrite everything from this project's settings
pskit lb logs edge -n 200             # one line per request: upstream= the server that answered
pskit lb remove edge [--force]        # --force when other projects still use it
pskit lb forget edge                  # this project only; it keeps running for the others
```

A cluster's own load balancer (`pskit cluster balancer set prod lb1`, one port per deployment) takes the same
`--algorithm` and `--weight` options; see [the cluster guide](cluster.md#load-balancer-one-url-for-the-whole-cluster-optional).

## Notes

* Firewall rules for the load balancer and its backends: [network and firewall rules](onprem-network.md#7-load-balancer-pskit-lb-create-pskit-lb-attach-pskit-cluster-balancer-set).

* The load balancer server must reach each backend's port (open it in the firewall). Hosts on `127.0.0.1` cannot
  be reached: set `host: 0.0.0.0` and `advertise`.
* Its files: `<home>/pskit-cluster/lb-<name>/` on the server; container `pskit-lb-<name>` (host network).
* `.pskit/onprem-balancers.json` lists the load balancers this project uses; `pskit settings export` includes it.
* Images: `openresty/openresty:1.27.1.2-alpine`. Existing cluster load balancers move from `nginx:1.27-alpine` to
  it on their next update.
