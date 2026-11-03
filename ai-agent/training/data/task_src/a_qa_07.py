"""Category A (docs Q&A and how-to), batch 7: on-premises scaling cluster (how replicas work, where a deploy goes,
per-server settings, resources on a cluster, ports, load balancer, logs, limits). Hand-written; assembled by
tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


C = "docs/cluster.md"

CONVERSATIONS = [
    A(121, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=[f"{C}#limits-and-notes", f"{C}#how-the-functions-run-in-a-cluster"],
      user="Our queue worker can't keep up on a 3-server Swarm cluster. If I raise replicas from 2 to 6, do the built-in queue consumers scale with them?",
      steps=[S("search_docs", query="cluster scale queue consumers replicas built-in queue",
               docs=[D(C, "limits-and-notes", end="scale with the replicas."),
                     D(C, "how-the-functions-run-in-a-cluster", start="* The **main** replica", end="as on one server.")])],
      final="""No. The main replica is one process on the master. Schedules, built-in queues and workflow executions don't scale out, and queue, storage and topic triggers run there [docs/cluster.md#limits-and-notes]. More web replicas only add HTTP and `invoke()` capacity.

To make queue consumers scale with the replicas, use a queue **driver** (Redis, SQS, ...). Resources with a driver are used directly by every replica [docs/cluster.md#how-the-functions-run-in-a-cluster].

**In code**
```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis_stream
      url_env: REDIS_URL
      key: jobs
```

**In the terminal**
1. Create the Redis on the cluster and attach the worker:
```bash
pskit resources onprem create jobs --service redis --role stream --cluster prod --attach worker --save
```
2. Deploy:
```bash
pskit deploy --cluster prod
```
Your handler code doesn't change."""),

    A(122, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="beginner",
      sources=[f"{C}#how-the-functions-run-in-a-cluster"],
      user="if i have 4 replicas, will my nightly schedule run 4 times??",
      steps=[S("search_docs", query="schedule runs once cluster replicas",
               docs=[D(C, "how-the-functions-run-in-a-cluster", start="* **web** replicas", end="Your handler code does not change.")])],
      final="""No, it runs once. In a cluster, schedules run in the **main** replica on the master, not once per replica [docs/cluster.md#how-the-functions-run-in-a-cluster].

- **Web** replicas serve your HTTP routes and `invoke()` calls.
- The **main** replica (one, on the master) owns everything stateful: schedules, built-in queues, topics and buckets, workflow executions, logs and stats.

Your handler code doesn't change."""),

    A(123, provider="onprem", stage="staging", mode="auto", page="Deploy", persona="terse_expert",
      sources=[f"{C}#one-server-or-the-cluster-per-deploy"],
      user="staging is on app-1. move it to cluster prod for a test, then back. what's the precedence?",
      steps=[S("search_docs", query="deploy cluster or server precedence stage remembers",
               docs=[D(C, "one-server-or-the-cluster-per-deploy", end="shows `deployed on: cluster prod")])],
      final="""First match wins [docs/cluster.md#one-server-or-the-cluster-per-deploy]:
1. `--cluster NAME`
2. `--server NAME` or `--server local` (even when pskit.yml has `options.cluster`)
3. `options.cluster`, then `options.deploy` in pskit.yml
4. where the stage was last deployed

**In the terminal**
```bash
pskit deploy -s staging --cluster prod
pskit deploy -s staging --server app-1
```
The stage remembers each move. The old place keeps running until you remove it there.

**In studio**
1. Open **Deploy**.
2. Set *Run on* to *Scaling cluster* (or *One machine* to go back) and click **Deploy**."""),

    A(124, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="pasted_error",
      sources=[f"{C}#set-up"],
      user="scp: Couldn't send packet: Broken pipe\n\nduring pskit deploy --cluster prod, wifi is bad. do i start over?",
      steps=[S("search_docs", query="cluster deploy image copy broken pipe retry",
               docs=[D(C, "set-up", start="The image is sent gzip-compressed", end="start once a later deploy finishes the copy.")])],
      final="""No. The image goes in 16 MB gzip parts, each with a checksum. A dropped connection is retried up to 6 times, and only the missing parts are sent again. Parts already copied stay on the server, so running the deploy again resumes the copy [docs/cluster.md#set-up].

```bash
pskit deploy --cluster prod
```

- The deploy stops only if the **master** can't get the image.
- If a worker fails, you get a warning. Replicas placed on it start once a later deploy finishes the copy."""),

    A(125, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{C}#per-server-settings-home-path-bind-address-data-directory"],
      user="Our servers have a big /data disk and a small root disk. Can I tell pskit once per server to keep app files under /srv/pskit and data under /data/pskit, for functions and for one-click services?",
      steps=[S("search_docs", query="saved server home path data directory bind address",
               docs=[D(C, "per-server-settings-home-path-bind-address-data-directory")])],
      final="""Yes. A saved server can carry a **Home path**, a **Bind address** and a **Data directory** [docs/cluster.md#per-server-settings-home-path-bind-address-data-directory].

- Home path: functions go to `<home>/<service>-<stage>` instead of `/opt/pskit/...`.
- Data directory: functions use it as `options.data_dir`; services keep their data in `<data>/<container>` as a bind mount, not a Docker volume.

**In the terminal**
```bash
pskit resources onprem servers add app-1 --ssh root@192.0.2.10 --home /srv/pskit --data-dir /data/pskit
```

**In studio**
1. Open **Resources > On-prem services > Servers** and click **+ Add server**.
2. Fill in the home path and data directory, then save.

pskit.yml still wins (`deploy.path`, `data_dir`). The settings apply to what you create or deploy afterwards. Existing services keep their volumes."""),

    A(126, provider="onprem", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{C}#resources-on-a-cluster"],
      user="i have cluster prod with 3 server. i need redis for cache, which server it go? i can choose?",
      steps=[S("search_docs", query="create resource on cluster placement node",
               docs=[D(C, "resources-on-a-cluster", end="replicas on every server reach.", words=200)])],
      final="""Both work. By default pskit picks the reachable server with the most free memory that is under every capacity limit. With `--node` you choose the server [docs/cluster.md#resources-on-a-cluster].

**In the terminal**
```bash
pskit resources onprem create cache --service redis --role cache --cluster prod --save
pskit resources onprem create cache --service redis --role cache --cluster prod --node app-2 --save
```
(the second line picks app-2)

**In studio**
1. Open **Resources > On-prem services > + Create service** and pick Redis.
2. Under *Where*, choose *Scaling cluster*, then the cluster (and a server if you want one).

The env file gets that server's cluster address, which replicas on every server can reach. If every server is over a limit, the create fails and asks you to join a server."""),

    A(127, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="detailed_spec",
      sources=[f"{C}#resources-on-a-cluster"],
      user="If I create our Postgres with --cluster prod, will the orchestrator move it to another node when that node dies, like the function replicas?",
      steps=[S("search_docs", query="resource on cluster replicated orchestrator moves",
               docs=[D(C, "resources-on-a-cluster", start="* It is a plain Docker container", end="as a one-server resource.")])],
      final="""No. A resource on a cluster is a plain Docker container with a data volume on one server. It's **one instance, not replicated**, and the orchestrator doesn't move it [docs/cluster.md#resources-on-a-cluster]. If that server dies, the database is down until the server is back.

If availability matters:
- Use a managed or replicated database.
- Or create it as primary plus read replicas on separate servers:
```bash
pskit resources onprem create orders-db --service postgres --primary db-1 --replica db-2 --save
```
The replicas keep serving reads if the primary fails, but promoting one is a manual step.

If the server leaves the cluster, the resource keeps running there as a one-server resource."""),

    A(128, provider="onprem", stage="prod", mode="auto", page="Network map", persona="terse_expert",
      sources=[f"{C}#ports-to-open"],
      user="swarm ports between nodes + from users?",
      steps=[S("search_docs", query="swarm ports to open cluster",
               docs=[D(C, "ports-to-open")])],
      final="""[docs/cluster.md#ports-to-open]
- Between the servers (Swarm): **2377/tcp, 7946/tcp+udp, 4789/udp**
- From users: the functions' `port` (default 8080) on every server. Swarm spreads HTTP from any server.
- With a load balancer: users reach its port (default 80); the load balancer reaches the functions' `port` on every cluster server.

For the exact rules per server:
```bash
pskit firewall --server app-1
```"""),

    A(129, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="beginner",
      sources=[f"{C}#load-balancer-one-url-for-the-whole-cluster-optional"],
      user="users now use 3 different ip addresses for my cluster. how do i give them only one address?",
      steps=[S("search_docs", query="one URL for the whole cluster load balancer",
               docs=[D(C, "load-balancer-one-url-for-the-whole-cluster-optional", end="named one: `pskit lb attach edge --cluster prod`")])],
      final="""Add a load balancer on one more server **outside** the cluster. pskit runs nginx there in Docker and spreads the HTTP over the cluster's servers, by default to the server with the fewest open connections [docs/cluster.md#load-balancer-one-url-for-the-whole-cluster-optional].

**In studio**
1. Save the extra server in **Resources > On-prem services > Servers** (for example lb-1).
2. Open **Scaling cluster**, select the cluster, and set up the *Load balancer* on lb-1. Pick *How it spreads requests* and click **Apply**.
3. Deploy again from **Deploy**.

**In the terminal**
```bash
pskit resources onprem servers add lb-1 --ssh root@192.0.2.30 --pem ~/.ssh/edge.pem
pskit cluster balancer set prod lb-1
pskit deploy --cluster prod
```
The deploy prints the public URL, for example `http://192.0.2.30`. Give your users that one address."""),

    A(130, provider="onprem", stage="dev", mode="ask", page="Cluster", persona="terse_expert",
      sources=[f"{C}#where-things-are-kept"],
      user="where does pskit store the cluster definitions + LB nginx conf? is any of it in git?",
      steps=[S("search_docs", query="where cluster config is stored",
               docs=[D(C, "where-things-are-kept")])],
      final="""None of it is in git [docs/cluster.md#where-things-are-kept]:
- Clusters, joined servers, load balancer, limits, alerts, deployments: `.pskit/onprem-clusters.json` (out of git)
- SSH logins: `.pskit/onprem-servers.json`, passwords in `.pskit/ssh/`
- Load balancer nginx config: `~/pskit-cluster/lb/conf.d/` on the load balancer server, one file per deployment
- Scripts and manifests: `~/pskit-cluster/` on the servers
- The join token is never stored; it's read from the master at each join

To move it all to another machine:
```bash
pskit settings export -o ops.pskit-settings
pskit settings import ops.pskit-settings
```"""),

    A(131, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="informal_non_native",
      sources=[f"{C}#monitor-scale-and-add-servers-when-it-is-full", f"{C}#commands"],
      user="server app-3 need maintenance next week. how i take it out of cluster without break the running app?",
      steps=[S("search_docs", query="retire server cluster drain leave",
               docs=[D(C, "monitor-scale-and-add-servers-when-it-is-full", start="**Add capacity on the go.**", end="so its replicas move to the others.")]),
             S("search_docs", query="cluster leave command",
               docs=[D(C, "commands", start="| `pskit cluster leave", end="| `pskit cluster leave")])],
      final="""Use `pskit cluster leave`. It **drains** the server first, so its replicas move to the other servers before it is removed [docs/cluster.md#monitor-scale-and-add-servers-when-it-is-full].

**In the terminal**
```bash
pskit cluster status prod
pskit cluster leave prod app-3
```
After the maintenance, join it again:
```bash
pskit cluster join prod app-3
```

**In studio**
1. Open **Scaling cluster** and select the cluster.
2. Click **Remove server** on app-3's row.
3. Later, add it back with **+ Join server**.

Check first that the other servers have room (`pskit cluster status prod`), otherwise some replicas can't be placed. The master can't leave on its own."""),

    A(132, provider="onprem", stage="staging", mode="ask", page="Logs", persona="detailed_spec",
      sources=[f"{C}#live-logs"],
      user="On our Nomad cluster, does pskit logs -f show the lines from all servers, or only the master? And what if one server can't reach the main replica?",
      steps=[S("search_docs", query="cluster live logs nomad servers",
               docs=[D(C, "live-logs")])],
      final="""All servers. On Nomad each server listens on its own port, so the tail reads every server's own buffer and shows them together. A web replica's lines show even when that server can't reach the main replica [docs/cluster.md#live-logs].

**In the terminal**
```bash
pskit logs -f -s staging
```

**In studio**
1. Open **Logs**. Picking one server there reads only that server.
2. Or open **Scaling cluster**, select the deployment and use the **Live logs** card.

On Swarm and k3s it works differently: web replicas send their lines to the main replica, and the tail reads that collected buffer."""),

    A(133, provider="onprem", stage="prod", mode="ask", page="Cluster", persona="informal_non_native",
      sources=[f"{C}#set-up"],
      user="my servers have public ip and private ip. cluster should talk on private network. how i set?",
      steps=[S("search_docs", query="cluster advertise private ip",
               docs=[D(C, "set-up", start="2. **Create the cluster**", end="(and `--advertise` on join).")])],
      final="""Give each server its private IP with `--advertise`, on create and on every join [docs/cluster.md#set-up].

**In the terminal**
```bash
pskit cluster create prod --orchestrator swarm --master app-1 --advertise 198.51.100.10
pskit cluster join prod app-2 --advertise 198.51.100.11
```
Use your servers' real private addresses.

**In studio**
1. **Scaling cluster > + New cluster**: fill in *Cluster address (optional)* with the master's private IP.
2. When you join a server, fill in its cluster address too.

Resources created on the cluster then get that address in the env file, so replicas reach them over the private network."""),

    A(134, provider="onprem", stage="prod", mode="auto", page="YAML", persona="terse_expert",
      sources=[f"{C}#set-up"],
      user="yaml only: cluster prod, 4 web replicas, 0.5 cpu and 512 MB each",
      steps=[S("search_docs", query="options.cluster replicas cpu memory",
               docs=[D(C, "set-up", start="4. **Point the functions at the cluster**", end="admin_token:")])],
      final="""**In code**
```yaml
provider:
  name: onprem
  options:
    cluster:
      name: prod
      replicas: 4
      cpu: 0.5
      memory: 512
    port: 8080
```
`replicas` are web replicas (default 2), plus 1 main replica. `cpu` and `memory` are what each replica reserves (defaults 0.25 cores and 256 MB) [docs/cluster.md#set-up]."""),

    A(135, provider="onprem", stage="prod", mode="ask", page="Load balancers", persona="detailed_spec",
      sources=[f"{C}#limits-and-notes"],
      user="With the pskit cluster load balancer on lb-1, isn't lb-1 a single point of failure? What does pskit recommend?",
      steps=[S("search_docs", query="load balancer single point of failure cluster",
               docs=[D(C, "limits-and-notes", start="* The load balancer is one server", end="each set up with the same nginx config.")])],
      final="""Yes. The load balancer is one server: if it goes down, its URL does [docs/cluster.md#limits-and-notes].

To avoid that, run two load balancers with the same nginx config, and put them behind:
- a floating IP (keepalived), or
- DNS with both addresses.

pskit doesn't set up keepalived or DNS for you. The cluster servers themselves are not the problem: with Swarm or k3s, each server's port reaches every web replica, and the load balancer skips a server that is down."""),

    A(136, provider="onprem", stage="dev", mode="ask", page="Cluster", persona="terse_expert",
      sources=[f"{C}#scaling-cluster-on-premises", "docs/cli.md#pskit-cluster"],
      user="which nomad version does cluster create install, and can I pin another?",
      steps=[S("search_docs", query="nomad version cluster create",
               docs=[D(C, "scaling-cluster-on-premises", start="| **HashiCorp Nomad**", end="| **HashiCorp Nomad**")]),
             S("search_docs", query="cluster create nomad-version flag",
               docs=[D("docs/cli.md", "pskit-cluster", start="| `cluster create NAME", end="| `cluster create NAME")])],
      final="""By default 1.11.3, installed with Docker as a systemd unit [docs/cluster.md#scaling-cluster-on-premises]. Pin another with `--nomad-version` [docs/cli.md#pskit-cluster]:

```bash
pskit cluster create prod -o nomad --master app-1 --nomad-version <version>
```
Replace `<version>` with a release from releases.hashicorp.com."""),

    A(137, provider="onprem", stage="dev", mode="ask", page="Cluster", persona="beginner",
      sources=[f"{C}#scaling-cluster-on-premises"],
      user="swarm, kubernetes or nomad... i never used any of them. which one should i choose?",
      steps=[S("search_docs", query="choose orchestrator swarm kubernetes nomad",
               docs=[D(C, "scaling-cluster-on-premises", start="| Orchestrator |", end="| **HashiCorp Nomad**")])],
      final="""Start with **Docker Swarm**. It's the simplest setup, and the functions' port answers on every server, so any server can take requests [docs/cluster.md#scaling-cluster-on-premises].

- **Kubernetes (k3s)**: for teams that use `kubectl` or want to grow into Kubernetes. Also answers on every server.
- **Nomad**: for teams that use Nomad / Consul. It has no load balancing; each server answers on its own port.

pskit installs whichever you pick over SSH, so you don't have to learn it to begin. Your handler code is the same for all three.

**In studio**
1. Open **Scaling cluster** and click **+ New cluster**.
2. Pick *Orchestrator* Docker Swarm and the *Master server*, then click **Create**."""),

    A(138, provider="onprem", stage="dev", mode="ask", page="Setup", persona="informal_non_native",
      sources=[f"{C}#scaling-cluster-on-premises", f"{C}#limits-and-notes"],
      user="for k3s cluster, docker needed? on servers or on my pc?",
      steps=[S("search_docs", query="k3s docker needed laptop servers",
               docs=[D(C, "scaling-cluster-on-premises", start="| **Kubernetes**", end="| **Kubernetes**"),
                     D(C, "limits-and-notes", end="root or passwordless `sudo`.")])],
      final="""On your PC, yes. On the servers, no.

- k3s is lightweight Kubernetes and needs no Docker on the servers [docs/cluster.md#scaling-cluster-on-premises].
- Docker must run on **your** machine, because pskit builds the function image there [docs/cluster.md#limits-and-notes].
- The servers need Linux (x86_64 or arm64) with SSH, and root or passwordless `sudo`.

**In studio**
Open **Setup & credentials** to check that Docker runs on your PC."""),

    A(139, provider="onprem", stage="prod", mode="auto", page="Cluster", persona="terse_expert",
      sources=[f"{C}#commands"],
      user="want a cron job on our ops box that pages us when the cluster is full. exit code?",
      steps=[S("search_docs", query="cluster check exit code full cron",
               docs=[D(C, "commands", start="| `pskit cluster status", end="| `pskit cluster watch")])],
      final="""`pskit cluster check` exits with status **3** when the cluster is full. It also sends the configured alert, with the cooldown [docs/cluster.md#commands].

```bash
pskit cluster check prod
pskit cluster check prod --no-alert
```
Use `--no-alert` if your cron job does the paging itself. To check in a loop instead of cron:
```bash
pskit cluster watch prod --interval 60
```"""),

    A(140, provider="onprem", stage="prod", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{C}#scaling-cluster-on-premises", f"{C}#set-up"],
      user="the cluster exists now. in the studio, which buttons do i press so my functions go to it?",
      steps=[S("search_docs", query="studio deploy to scaling cluster run on",
               docs=[D(C, "scaling-cluster-on-premises", start="In the studio: *Deploy", end="SSH server / Scaling cluster*."),
                     D(C, "set-up", start="4. **Point the functions at the cluster**", end="switch on the cluster page):")])],
      final="""**In studio**
1. Open **Scaling cluster** and select your cluster.
2. Turn on *Deploy this project's functions to …* and click **Save**. This writes `provider.options.cluster` [docs/cluster.md#set-up].
3. Open **Deploy**, set *Run on* to *Scaling cluster* and click **Deploy** [docs/cluster.md#scaling-cluster-on-premises].

Docker must be running on your machine, because the image is built there."""),
]
