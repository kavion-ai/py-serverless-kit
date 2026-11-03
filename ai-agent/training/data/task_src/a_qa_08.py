"""Category A (docs Q&A and how-to), batch 8: on-premises load balancers, placement groups and network / firewall
rules. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


LB = "docs/load-balancers.md"
PL = "docs/placement.md"
NW = "docs/onprem-network.md"

CONVERSATIONS = [
    A(141, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="detailed_spec",
      sources=[f"{LB}#create-one-and-put-projects-on-it"],
      user="Behind the pskit load balancer our shop service is reached at http://lb/shop/orders. Does my handler see the path as /shop/orders or /orders? Our redirects need to know the prefix.",
      steps=[S("search_docs", query="load balancer path prefix removed forwarded prefix",
               docs=[D(LB, "create-one-and-put-projects-on-it", start="The path prefix is removed", end="`/shop` redirects to `/shop/`.")])],
      final="""Your handler sees `/orders`. The load balancer removes the path prefix before the request reaches your functions, and sends it in the `X-Forwarded-Prefix: /shop` header. `/shop` redirects to `/shop/` [docs/load-balancers.md#create-one-and-put-projects-on-it].

**In code**
```python
from __future__ import annotations


def orders(event, ctx):
    prefix = event.http.headers.get("x-forwarded-prefix", "")
    return {"path": event.http.path, "self": prefix + event.http.path}
```
Build your redirect URLs as prefix plus path, so they work with and without the load balancer."""),

    A(142, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="beginner",
      sources=[f"{LB}#notes"],
      user="i made a load balancer and put my project on it, but it can't reach my functions. the project is on app-1 with default settings",
      steps=[S("search_docs", query="load balancer cannot reach backend host 127.0.0.1",
               docs=[D(LB, "notes", end="set `host: 0.0.0.0` and `advertise`.")])],
      final="""With the default settings the host listens on `127.0.0.1`, and the load balancer can't reach that. Set `host: 0.0.0.0` and `advertise` [docs/load-balancers.md#notes].

**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    advertise: http://192.0.2.10:8080
    port: 8080
    balancer: edge
```
Use app-1's address in `advertise`: it's the address the load balancer calls.

**In the terminal**
1. Deploy again:
```bash
pskit deploy -s prod
```
2. Open port 8080 on app-1 to the load balancer server. This lists the rules:
```bash
pskit firewall --server app-1
```"""),

    A(143, provider="onprem", stage="prod", mode="auto", page="Load balancers", persona="terse_expert",
      sources=[f"{LB}#the-six-algorithms", f"{LB}#commands"],
      user="app-1 has 3x the cores of app-2. make lb edge send it 3x the traffic",
      steps=[S("search_docs", query="weighted round robin weight per server",
               docs=[D(LB, "the-six-algorithms", start="| `weighted_round_robin`", end="is used by weighted round robin", words=260),
                     D(LB, "commands", start="pskit lb algorithms", end="pskit lb list")])],
      final="""Use `weighted_round_robin` with weights [docs/load-balancers.md#the-six-algorithms].

**In the terminal**
```bash
pskit lb update edge --algorithm weighted_round_robin --weight app-1=3 --weight app-2=1
pskit lb status edge
```

**In studio**
1. Open **Load balancers** and select `edge`.
2. Change *How it spreads requests* to weighted round robin, set the weights, and click **Update**.

`weight` is 1..100 per saved server. Least connections and least time use it too, so you can keep a dynamic algorithm and still favour app-1 [docs/load-balancers.md#the-six-algorithms]."""),

    A(144, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="informal_non_native",
      sources=[f"{LB}#create-one-and-put-projects-on-it"],
      user="we have lb edge and cluster prod with many services on it. i want every service on cluster get its path on edge automatic",
      steps=[S("search_docs", query="attach cluster to load balancer every deployment path",
               docs=[D(LB, "create-one-and-put-projects-on-it", start="A **cluster** can be attached instead", end="gets one route, `/<service>/`")])],
      final="""Attach the cluster to the load balancer. Every deployment on it gets `/<service>/` (or `/<service>-<stage>/` when two stages share the cluster), kept up to date on deploy, remove, join and leave [docs/load-balancers.md#create-one-and-put-projects-on-it].

**In the terminal**
```bash
pskit lb attach edge --cluster prod
```
To stop:
```bash
pskit lb detach edge --cluster prod
```

**In studio**
1. Open **Load balancers** and select `edge`.
2. Under *Clusters*, attach `prod`.

A project's own `balancer` setting still wins over the cluster's route for that deployment."""),

    A(145, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="terse_expert",
      sources=[f"{LB}#commands"],
      user="terminal only: last 200 requests on lb edge and which backend took each",
      steps=[S("search_docs", query="load balancer access log upstream server",
               docs=[D(LB, "commands", start="pskit lb algorithms", end="pskit lb forget edge")])],
      final="""**In the terminal**
```bash
pskit lb logs edge -n 200
```
One line per request. `upstream=` is the server that answered [docs/load-balancers.md#commands]."""),

    A(146, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="detailed_spec",
      sources=[f"{LB}#shared-between-projects-and-machines", f"{LB}#commands"],
      user="An old project that nobody deploys anymore still owns the path /xyz on our shared load balancer edge, and a new project wants that path. The old repo is gone. How do we free the path?",
      steps=[S("search_docs", query="path belongs to one deployment shared load balancer",
               docs=[D(LB, "shared-between-projects-and-machines", start="* a path belongs to one deployment")]),
             S("search_docs", query="remove route of another project",
               docs=[D(LB, "commands", start="pskit lb algorithms", end="pskit lb forget edge")])],
      final="""A path belongs to one deployment, so the new project gets an error until the old route is gone [docs/load-balancers.md#shared-between-projects-and-machines]. Remove the route from any project. It works whichever project owns it [docs/load-balancers.md#commands].

**In the terminal**
```bash
pskit lb status edge
pskit lb routes remove edge xyz
```
`lb status` marks routes of other projects, so check that `xyz` is the old one first. Then deploy the new project.

**In studio**
1. Open **Load balancers** and select `edge`.
2. Under *Routes*, click **Remove route** on `/xyz/`.

The old project's servers keep running. Remove them separately if nobody needs them."""),

    A(147, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="aws_migrator",
      sources=[f"{LB}#the-six-algorithms"],
      user="On AWS we used ALB sticky sessions for our WebSocket app. I read sticky cookies need NGINX Plus. Do I have to buy that for the pskit load balancer?",
      steps=[S("search_docs", query="sticky cookie nginx plus least time open source",
               docs=[D(LB, "the-six-algorithms", start="**Static** algorithms", end="rests for 10 s.")]),
             S("search_docs", query="sticky round robin websockets",
               docs=[D(LB, "the-six-algorithms", start="| Algorithm |", end="| `sticky_round_robin`")])],
      final="""No. Open-source nginx has no sticky cookie or least time, so pskit builds them itself on OpenResty. Sticky hashes a cookie that holds the first request's id, and least time uses Lua with a moving average of each server's response time [docs/load-balancers.md#the-six-algorithms].

`sticky_round_robin` fits your case: it's meant for in-memory sessions, uploads in parts and WebSockets. Busy users can make the load uneven, and sessions move when a server joins or leaves.

**In the terminal**
```bash
pskit lb update edge --algorithm sticky_round_robin
```

**In code** (only this project's route)
```yaml
provider:
  name: onprem
  options:
    balancer: {name: edge, algorithm: sticky_round_robin}
```"""),

    A(148, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{PL}#how-the-groups-work-together"],
      user="With placement, can a built-in queue `jobs` have one consumer in group api and another consumer in group gpu?",
      steps=[S("search_docs", query="placement built-in queue consumers groups",
               docs=[D(PL, "how-the-groups-work-together", start="Rules that keep this simple:", end="no loops when configs disagree).")])],
      final="""No. A built-in queue or bucket belongs to **one** group, and its consumers must be in that group. Validation tells you when they aren't [docs/placement.md#how-the-groups-work-together].

To share it across groups, give the queue a driver that every server reaches:
```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis
      url_env: REDIS_URL
      key: jobs
```
Or keep both consumers in one group. Sending to the queue from any group is fine either way."""),

    A(149, provider="onprem", stage="staging", mode="auto", page="Workflows", persona="terse_expert",
      sources=[f"{PL}#how-the-groups-work-together"],
      user="placement + workflows: where does the execution live, where do the steps run, and does Retry still work across groups?",
      steps=[S("search_docs", query="placement workflow default group steps retry",
               docs=[D(PL, "how-the-groups-work-together", start="| You do |", end="| `pskit logs`")])],
      final="""[docs/placement.md#how-the-groups-work-together]
- A workflow always runs, and is recorded, on the **default** group, whichever group you start it on. Executions stay in one place.
- Each step runs wherever its function is placed.
- A step's error comes back with its type, so `Retry` and `Catch` match it by name as usual.

Logs from every group also reach the default group, so `pskit logs` shows them all."""),

    A(150, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=[f"{PL}#how-the-groups-work-together"],
      user="my api function calls invoke(\"resize\") but resize is now on the gpu-box group. do i have to change the code?",
      steps=[S("search_docs", query="invoke function in another placement group",
               docs=[D(PL, "how-the-groups-work-together", end="| an HTTP request to `api`")])],
      final="""No. `invoke("resize", data)` in a function on `api` runs on the `gpu` group, and the result (or the error, with its type) comes back [docs/placement.md#how-the-groups-work-together].

The groups call each other over HTTP with a shared secret, `.pskit/onprem-<stage>/peer-token` (out of git). Just make sure the group hosts can reach each other's ports. `pskit firewall` lists them."""),

    A(151, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{PL}#each-function-is-its-own-sub-project"],
      user="deploy failed: functions resize and thumbs pin conflicting versions of Pillow on server gpu-box\nboth need different pillow, what do i do",
      steps=[S("search_docs", query="conflicting requirements versions same server placement",
               docs=[D(PL, "each-function-is-its-own-sub-project", start="* On premises with placement", end="place them on different servers.")])],
      final="""Each server installs the requirements of all its functions, so two functions on one server can't pin conflicting versions. Place them on different servers [docs/placement.md#each-function-is-its-own-sub-project].

**In code**
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    placement:
      default: api
      groups:
        api: {server: app-1}
        gpu: {server: gpu-box, functions: [resize]}
        thumbs: {server: app-2, functions: [thumbs]}
```
The other option is to agree on one Pillow version in both `functions/<name>/requirements.txt` files and keep them together.

**In studio**
1. Open **Deploy** and expand **Where functions run**.
2. Add a group on another server and tick `thumbs`, then **Save** and **Deploy**."""),

    A(152, provider="onprem", stage="dev", mode="ask", page="YAML", persona="terse_expert",
      sources=[f"{PL}#functions-on-several-servers-on-premises"],
      user="pskit.yml only: two placement groups on the same server app-1 — what do I need?",
      steps=[S("search_docs", query="placement two groups same server port",
               docs=[D(PL, "functions-on-several-servers-on-premises", start="Per group:", end="is not reachable).")])],
      final="""**In code**
Give the second group its own `port`. It's needed when two groups share a server [docs/placement.md#functions-on-several-servers-on-premises]:
```yaml
provider:
  name: onprem
  options:
    host: 0.0.0.0
    port: 8080
    placement:
      default: api
      groups:
        api: {server: app-1}
        reports: {server: app-1, functions: [report], port: 8081}
```
Set `advertise` on a group only when the other groups can't reach it at the server's own address."""),

    A(153, provider="onprem", stage="prod", mode="auto", page="Deploy", persona="terse_expert",
      sources=[f"{PL}#deploy-urls-and-load-balancers"],
      user="with placement groups, does `pskit deploy --server app-9` move all groups to app-9?",
      steps=[S("search_docs", query="placement server flag moves default group",
               docs=[D(PL, "deploy-urls-and-load-balancers", start="`--server NAME` / `--cluster NAME`")])],
      final="""No. `--server NAME` and `--cluster NAME` move the **default** group only. The other groups always run where pskit.yml puts them [docs/placement.md#deploy-urls-and-load-balancers].

To move another group, change its `server` in `provider.options.placement.groups`, or in **Deploy > Where functions run** in the studio, and deploy again."""),

    A(154, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="detailed_spec",
      sources=[f"{PL}#deploy-urls-and-load-balancers"],
      user="We're adding placement to a stage that's already deployed on one server. Will Terraform recreate the existing host? And where does each group keep its queues and logs?",
      steps=[S("search_docs", query="placement terraform resources unit folder data",
               docs=[D(PL, "deploy-urls-and-load-balancers", end="list each group's endpoint and functions.")])],
      final="""No, the existing host stays. The default group keeps `terraform_data.host`, the same resource as before, so adding placement to a deployed stage moves nothing. Every group is deployed in one Terraform apply [docs/placement.md#deploy-urls-and-load-balancers].

Each other group gets:
- `terraform_data.host_<group>`
- the unit `pskit-<service>-<stage>-<group>`
- the folder `onprem_app_<group>`
- its data (queues, buckets, logs) in `<data_dir>/groups/<group>`

`pskit info` and `deployment.json` list each group's endpoint and functions:
```bash
pskit deploy -s prod
pskit info -s prod
```"""),

    A(155, provider="onprem", stage="prod", mode="ask", page="Network map", persona="informal_non_native",
      sources=[f"{NW}#1-always-the-admin-machine-reaches-every-server-over-ssh"],
      user="our servers have no internet at all, only our lan. pskit cluster still possible?",
      steps=[S("search_docs", query="servers without internet offline install docker images",
               docs=[D(NW, "1-always-the-admin-machine-reaches-every-server-over-ssh")])],
      final="""Yes, with some preparation. The servers normally need outbound 443/80 only the first time: to install Docker, pull images, and download k3s or Nomad [docs/onprem-network.md#1-always-the-admin-machine-reaches-every-server-over-ssh].

Without internet:
1. Preinstall Docker (and k3s or Nomad) on the servers yourself.
2. Load the images yourself with `docker load`.
3. pskit copies the function image itself over SSH, so you need no registry.

Your own machine still needs outbound 443 while packaging (PyPI / npm, base images), and SSH (port 22) to every server."""),

    A(156, provider="onprem", stage="prod", mode="ask", page="Network map", persona="detailed_spec",
      sources=[f"{NW}#7-load-balancer-pskit-lb-create-pskit-lb-attach-pskit-cluster-balancer-set"],
      user="Security wants users to reach only the load balancer, not port 8080 on the app servers directly. Is that allowed with pskit's load balancer, and which rules remain?",
      steps=[S("search_docs", query="close function port to users load balancer firewall",
               docs=[D(NW, "7-load-balancer-pskit-lb-create-pskit-lb-attach-pskit-cluster-balancer-set")])],
      final="""Yes. With a load balancer you can close `FN_PORT` (8080) to users on the function and cluster servers, and allow it only from the load balancer [docs/onprem-network.md#7-load-balancer-pskit-lb-create-pskit-lb-attach-pskit-cluster-balancer-set].

Rules that remain:
- Users to the load balancer: TCP 80 (its port).
- Load balancer to every backend: TCP 8080.
- Every admin machine that uses it to the load balancer: TCP 22.
- Load balancer outbound 443, the first time (Docker, the OpenResty image).
- Between cluster servers or placement groups: their own ports, as before.

**In the terminal**
```bash
pskit firewall
pskit firewall --server lb-1
```

**In studio**
Open **Network map** and click a server to see its inbound and outbound rules."""),

    A(157, provider="onprem", stage="prod", mode="auto", page="Network map", persona="terse_expert",
      sources=[f"{NW}#8-resources-and-triggers-attaching-events"],
      user="smtp trigger server: which ports in, which out?",
      steps=[S("search_docs", query="smtp server ports firewall",
               docs=[D(NW, "8-resources-and-triggers-attaching-events", start="**SMTP server**", end="delivers each mail to")])],
      final="""[docs/onprem-network.md#8-resources-and-triggers-attaching-events]
- **In**: TCP 25 from Internet mail servers to the SMTP server, plus an MX record pointing at it.
- **Out**: from the SMTP server to the function host's `FN_PORT` (8080). It delivers each mail to `/__pskit/smtp/<name>`. With placement, any group host works.
- Plus TCP 22 from your admin machine, as for every server."""),

    A(158, provider="onprem", stage="prod", mode="ask", page="Network map", persona="terse_expert",
      sources=[f"{NW}#8-resources-and-triggers-attaching-events"],
      user="postgres primary + 2 replicas + pgpool on lb-1. firewall matrix?",
      steps=[S("search_docs", query="replicated database pgpool ports",
               docs=[D(NW, "8-resources-and-triggers-attaching-events", start="**Replicated database**", end="create, add / remove replicas, status |")])],
      final="""[docs/onprem-network.md#8-resources-and-triggers-attaching-events]
- every replica → primary: 5432
- lb-1 (pgpool-II) → every member: 5432
- every function host → lb-1: **6432** (pgpool-II, the functions' single address)
- every function host → every member: 5432, for `WRITE_URL` and `READ_URLS`
- admin machine → every member and lb-1: 22

```bash
pskit firewall --server lb-1
```"""),

    A(159, provider="onprem", stage="dev", mode="ask", page="Setup", persona="beginner",
      sources=[f"{NW}#9-the-studio-and-browser-terminals"],
      user="do i need to open a firewall port for pskit studio or the browser terminal?",
      steps=[S("search_docs", query="studio browser terminal firewall port",
               docs=[D(NW, "9-the-studio-and-browser-terminals")])],
      final="""No. The studio listens on `127.0.0.1` of your own machine, and browser terminals on `127.0.0.1:7681` and up. No firewall change is needed. They reach your servers over SSH [docs/onprem-network.md#9-the-studio-and-browser-terminals]."""),

    A(160, provider="onprem", stage="prod", mode="auto", page="Network map", persona="terse_expert",
      sources=[f"{NW}#network-and-firewall-rules-on-premises"],
      user="cli only: firewall rules machine-readable, so our ansible can apply them",
      steps=[S("search_docs", query="pskit firewall json per server",
               docs=[D(NW, "network-and-firewall-rules-on-premises", start="**You do not have to work these out by hand.**", end="in each job's output:")])],
      final="""**In the terminal**
```bash
pskit firewall --json
pskit firewall --server app-1 --json
```
It lists everything the project needs now, per server [docs/onprem-network.md#network-and-firewall-rules-on-premises]."""),
]
