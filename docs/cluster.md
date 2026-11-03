# Scaling cluster (on premises)

By default the on-prem provider runs all functions in **one host process on one server**. Nothing about that
changes. A **scaling cluster** adds a second option: a **master server** plus any number of **joined servers**,
run by one of three orchestrators:

| Orchestrator | What pskit installs | Load balancing | Good for |
|---|---|---|---|
| **Docker Swarm** (`swarm`) | Docker on every server; `swarm init` on the master, `swarm join` on the others | The routing mesh: the functions' port answers on **every** server | The simplest setup; Docker you already know |
| **Kubernetes** (`kubernetes`) | [k3s](https://k3s.io) (lightweight Kubernetes, no Docker needed) | k3s ServiceLB: the functions' port answers on **every** server | Teams that use `kubectl`, or want to grow into Kubernetes |
| **HashiCorp Nomad** (`nomad`) | Docker plus the Nomad agent ([releases.hashicorp.com](https://releases.hashicorp.com/nomad/), 1.11.3 by default) as a systemd unit | No load balancer. The main replica answers on the master's port; each web replica answers on its own server's port. Add nginx, HAProxy or Traefik only when you want one URL for all of them | Teams that use Nomad / Consul |

pskit does everything over SSH from your machine: it installs the orchestrator, joins servers, copies the function
image to every server (**no container registry needed**), deploys, and watches capacity.

Every deploy and every resource picks where it runs:

| | One server (as before) | A scaling cluster |
|---|---|---|
| **Functions** | `pskit deploy --server edge1` / `options.deploy.server` | `pskit deploy --cluster prod` / `options.cluster: prod` |
| **Resources** (Redis, Postgres, MinIO, SMTP, ...) | `pskit resources onprem create cache --service redis --server edge1` | `... --cluster prod` (the server with the most free memory) or `--cluster prod --node edge2` |

In the studio: *Deploy → Run on: One machine / Scaling cluster*, and *Create a service → Where: This machine / One
SSH server / Scaling cluster*.

## How the functions run in a cluster

Each deployment (`pskit-<service>-<stage>`) runs the function host image as two workloads:

```
                      users ──► :8080 (Swarm mesh / k3s ServiceLB / each Nomad server)
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
         web replica          web replica          web replica        ← `replicas` copies, spread over servers
     (HTTP routes, invoke)  (HTTP routes, invoke)  (HTTP routes, invoke)
              │ queues, topics, buckets, workflows, logs, /__pskit admin
              └────────────────────┼────────────────────┘
                                   ▼
                          main replica (1, on the master)
        schedules · built-in queues / topics / buckets · workflow executions · logs · stats · data volume
```

* **web** replicas serve your HTTP routes and `invoke()` calls. Adding replicas or servers adds HTTP capacity.
* The **main** replica runs on the master with the data volume. It owns everything stateful: schedules run once,
  not once per replica; built-in queues, topics and buckets live in one place; workflow executions are recorded
  there; queue, storage and topic triggers run there.
* A web replica hands those to main. `submit_queue()`, `put_object()`, workflow starts and `/__pskit/*` admin
  calls are forwarded to it. Its log lines and invocation counts are sent to main every second, tagged with
  `replica`, so `pskit logs`, the studio's **Logs** view and `/__pskit/stats` show the whole cluster.
* Resources with a driver (Redis, SQS, S3, MinIO, ...) are used directly by every replica, as on one server.

Your handler code does not change.

### Nomad does not need a load balancer

Swarm and k3s publish the functions' port on every server and spread HTTP across the web replicas. Nomad does not.
The main replica listens on the master's port. Each web replica listens on its own server's port, one per server.
`pskit deploy` waits until the main replica answers `http://127.0.0.1:<port>/__pskit/health` on the master. That
check does not go through a load balancer, and the deploy succeeds without one.

Send traffic to the master and the main replica handles it. Send traffic to another server and that server's web
replica handles it. For a single URL that spreads requests across the web replicas, let pskit run a
[load balancer](#load-balancer-one-url-for-the-whole-cluster-optional) on one more server, or put your own nginx,
HAProxy or Traefik in front.

While that wait runs, the deploy prints each Nomad allocation and the main replica's logs every 10 seconds, as
they happen. If the port never answers, the output ends with `nomad job status` and those logs.

## Set up

1. **Save the servers** (once): *Resources → On-prem services → Servers → + Add server*, or

   ```bash
   pskit resources onprem servers add edge1 --ssh root@10.0.0.5 --pem ~/.ssh/edge.pem
   pskit resources onprem servers add edge2 --ssh root@10.0.0.6 --pem ~/.ssh/edge.pem
   ```

   The SSH user needs root or passwordless `sudo`.

2. **Create the cluster** on the master: studio *Scaling cluster → + New cluster*, or

   ```bash
   pskit cluster create prod --orchestrator swarm --master edge1      # or kubernetes / nomad
   ```

   Servers in one private network should use their private IP: `--advertise 10.0.0.5` (and `--advertise` on join).

   **Does the master serve requests too?** The studio's *Master serves requests* switch, or
   `--master-serves` / `--no-master-serves`, decides whether load balancers send requests to the master next to
   the joined servers. See [The master and requests](#the-master-and-requests). Default: off on Nomad, on on
   Swarm and k3s. Change it later with `pskit cluster set prod --master-serves` (or the switch on the cluster page).

3. **Join servers**, now or any time later (also while functions are running):

   ```bash
   pskit cluster join prod edge2
   ```

   pskit installs the agent, joins it, and copies the images already deployed, so replicas can start there at once.
   Joining again is safe. A server left half-joined by a failed join, removed while it was off, or still in an
   old swarm leaves that membership first. pskit refuses only a server that manages another swarm with nodes or
   services, or whose swarm is locked.

4. **Point the functions at the cluster** in `pskit.yml` (studio: the *Deploy this project's functions to …*
   switch on the cluster page):

   ```yaml
   provider:
     name: onprem
     options:
       cluster: prod                     # or the mapping below
       # cluster:
       #   name: prod
       #   replicas: 3                   # web replicas (default 2), plus 1 main replica
       #   cpu: 0.25                     # CPU cores each replica reserves (default 0.25)
       #   memory: 256                   # MB each replica reserves (default 256)
       port: 8080
       admin_token: "${env:PSKIT_ADMIN_TOKEN}"
   ```

5. **Deploy**: `pskit deploy` (or studio *Deploy*). pskit builds the image on this machine (Docker must run here),
   copies it to every server that does not have it yet, applies the stack / manifest / job on the master, and
   waits until `/__pskit/health` answers. `pskit remove` deletes the workloads. The main replica's data stays on
   the master: a Docker volume for Swarm, `/var/lib/pskit/<stack>` for Kubernetes and Nomad.

   The image is sent gzip-compressed in 16 MB parts, each with a checksum. A dropped connection (`scp: Couldn't
   send packet: Broken pipe`) is retried up to 6 times with growing pauses. Each retry sends only the parts that
   are missing, and parts already copied stay on the server, so running `pskit deploy` again resumes the copy. The
   deploy stops only if the master cannot get the image. A worker that fails gets a warning, and replicas placed on
   it start once a later deploy finishes the copy.

### One server or the cluster, per deploy

Where a deploy goes, first match wins:

1. `pskit deploy --cluster NAME` (studio: *Run on → Scaling cluster*): that cluster. The replicas / cpu / memory of
   `options.cluster` are kept when it names another cluster.
2. `pskit deploy --server NAME` or `--server local` (studio: *Run on → One machine*): that one machine, even when
   pskit.yml has `options.cluster`.
3. `options.cluster` in pskit.yml, then `options.deploy` (`server`, `host`, ...).
4. Where the stage was last deployed: a cluster or a saved server. The stage remembers it, like a server.

So `pskit deploy --cluster prod` once moves a stage to the cluster, and `pskit deploy --server edge1` once moves it
back to one server. The old place keeps running until you `pskit remove` it there. On a cluster the master is the
SSH target that `pskit logs`, `pskit trigger`, the dashboard and the studio use when the port is closed to your
machine; `pskit info` shows `deployed on: cluster prod (master edge1 (10.0.0.5))`.

## Per-server settings: home path, bind address, data directory

A saved server can carry three optional defaults (*Add a server* in the studio, or
`pskit resources onprem servers add edge1 --ssh root@10.0.0.5 --home /srv/pskit --bind 10.0.0.5 --data-dir /data/pskit`):

| Setting | Functions on this server | Resources on this server | In a cluster |
|---|---|---|---|
| **Home path** | app in `<home>/<service>-<stage>` (instead of `/opt/pskit/...`) | – | scripts and image copies in `<home>/pskit-cluster` |
| **Bind address** | the host listens on it (`options.host`) | port published on it | a specific IP is the server's cluster address |
| **Data directory** | `options.data_dir` (built-in queues, buckets, ...) | data in `<data>/<container>` (bind mount, not a Docker volume) | the master keeps the main replica's data in `<data>/<stack>` |

pskit.yml wins: `deploy.path`, `data_dir` and a `host` other than the default `127.0.0.1`. Settings apply to what you
create or deploy afterwards; existing services keep their volumes.

## Resources on a cluster

A resource can run on one server of a cluster:

```bash
pskit resources onprem create cache --service redis --cluster prod                # auto placement
pskit resources onprem create orders-db --service postgres --cluster prod --node edge2
```

* **Auto placement** measures every server of the cluster (as `pskit cluster status` does) and picks the reachable
  one with the most free memory that is under every capacity limit. When every server is over a limit the create
  fails with "join a server", the same signal as the capacity alert.
* The address written to the env file is that server's **cluster address** (its `--advertise` address), which the
  function replicas on every server reach.
* It is a plain Docker container with a data volume on that server, as on one server: status, logs, backups, the
  web UI and the data browser work the same. It is **one instance, not replicated**: the orchestrator does not
  move it. Use a managed or replicated database when that matters.
* With `options.cluster` in pskit.yml, *Create a service* and `pskit resources onprem create` default to the
  cluster.
* `pskit cluster status` and the studio's cluster page list the resources and the server each runs on. When that
  server leaves the cluster (or the cluster is forgotten) the resource keeps running there as a one-server resource.

### Ports to open

Every step, every role: [network and firewall rules](onprem-network.md).

| Between the servers | |
|---|---|
| Swarm | 2377/tcp, 7946/tcp+udp, 4789/udp |
| Kubernetes (k3s) | 6443/tcp (to the master), 8472/udp, 10250/tcp |
| Nomad | 4646-4648/tcp, 4648/udp |
| **From users** | the functions' `port` (default 8080) on every server. Swarm and k3s spread HTTP from any server. On Nomad each server answers for itself |
| **With a load balancer** | from users: its port (default 80) on the load balancer. From the load balancer: the functions' `port` on every cluster server |

## Load balancer: one URL for the whole cluster (optional)

Add one more saved server **outside** the cluster as its load balancer. pskit runs OpenResty (nginx) there in
Docker (container `pskit-lb`, host network) and spreads each deployment's HTTP over the cluster's servers with the
algorithm you pick (`--algorithm`: round robin, sticky round robin, weighted round robin, IP hash, least
connections (the default) or least time; `--weight edge1=3` per server; see
[load balancers](load-balancers.md#the-six-algorithms)). It works the same way for all three orchestrators.
To share one load balancer between clusters and projects by path instead (`http://lb/<service>/`), attach a
named one: `pskit lb attach edge --cluster prod` ([load balancers](load-balancers.md)).

```
                users ──► http://<lb1>/  (nginx on lb1, port 80)
                              │  fewest open connections first
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
     edge1 (master)       edge2 (join)      edge3 (join)      :8080 on each
```

```bash
pskit resources onprem servers add lb1 --ssh root@10.0.0.9 --pem ~/.ssh/edge.pem
pskit cluster balancer set prod lb1              # installs Docker + nginx on lb1; --port 8000 for another port
pskit deploy --cluster prod
#   pskit-shop-prod is running on cluster prod: http://10.0.0.5:8080
#   Updating the load balancer on lb1 ...
#     http://10.0.0.9 -> pskit-shop-prod on edge2, edge3 (backup edge1)
#   Public URL (load balancer on lb1): http://10.0.0.9
```

| Orchestrator | Behind the load balancer |
|---|---|
| Swarm, k3s | every server (each server's port already reaches every web replica; the load balancer adds one URL and skips a server that is down) |
| Nomad | the servers with a web replica, plus the master's main replica when the master serves requests |

When the master does **not** serve requests, it is listed on every load balancer as a **backup** only (see below).

### The master and requests

| Master serves requests | What happens |
|---|---|
| **on** (Swarm / k3s default) | Load balancers spread requests over every server, the master included. Nomad: the master's main replica answers them next to the web replicas. Swarm / k3s: web replicas may also run on the master. Uses the master's spare CPU, but heavy traffic competes with the control plane, schedules, queues and data that live there |
| **off** (Nomad default) | The master is idle for requests while a joined server is up: load balancers list it as a `backup` and send it traffic only while every other server is down. Swarm / k3s also keep web replicas off the master (a placement constraint / node affinity) while another server can run them. With no joined server yet, the master still serves everything |

Set it when creating the cluster (`--master-serves` / `--no-master-serves`, or the studio switch) and change it any
time with `pskit cluster set NAME --master-serves|--no-master-serves` or the switch on the cluster page. The load
balancers (the cluster's own and attached named ones) are updated at once. On Swarm and k3s, web replicas move on
or off the master at the next `pskit deploy`; so after the first server joins a cluster whose master does not
serve, deploy again to move them off the master. Clusters created before this setting keep their old behaviour
(off on Nomad, on on Swarm and k3s). Without a load balancer, users who call the master's own address still reach it.

**pskit keeps it up to date.** You do not edit nginx config:

| When | What happens on the load balancer |
|---|---|
| `pskit deploy` | the deployment is added (or updated) and its URL printed |
| `pskit cluster join` | the new server is added |
| `pskit cluster leave` | the server is taken off **before** it is drained, so no request goes to a server that is stopping |
| `pskit remove` | the deployment is taken off **before** its replicas stop, so users do not get 502 in between |
| `pskit cluster balancer sync prod` | rewritten now (after the load balancer was offline during one of the above) |

Each change is checked by `nginx -t` in a throwaway container first. A config nginx refuses leaves the running one
untouched, and nginx reloads without dropping connections. If the load balancer is offline during a deploy, join
or leave, that step still goes through and prints a warning with the `sync` command to run later.

**Logs, tests and the admin API do not change.** The deployment's endpoint stays the master's address
(`pskit info`, `pskit logs`, `pskit test` and the studio use it), and `pskit cluster requests` still shows which
server handled each request. The load balancer has its own access log, one line per request with the server that
answered:

```bash
pskit cluster balancer logs prod -n 200
#   2026-10-26T05:39:44+00:00 203.0.113.7 port=80 "GET /hello HTTP/1.1" 200 17 0.004s upstream=10.0.0.6:8080 0.003s
```

`pskit cluster status prod` shows the load balancer's CPU, memory and disk, whether nginx runs, and each
deployment's URL on it. `pskit cluster list` shows the same URLs.

**Several deployments on one cluster** each need their own port on the load balancer. The first one uses the
load balancer's port (80); give the others one in `pskit.yml`, and the deploy stops with this hint when two would
share a port:

```yaml
provider:
  name: onprem
  options:
    cluster: {name: prod, replicas: 3, balancer_port: 8081}
```

What nginx does with each request: picks the server with the fewest open connections; a server that fails 3 times
rests for 10 seconds; a request that cannot connect, times out, or gets 502 / 503 / 504 is tried on another
server (up to 3, never for a `POST` that already reached a server); WebSocket upgrades pass through; up to 100 MB
request bodies and 900 seconds per request. It passes `X-Forwarded-For`, `X-Real-IP` and `X-Forwarded-Proto`.
For HTTPS, put your TLS terminator in front of it, or use your own nginx / HAProxy instead of this one.

`pskit cluster balancer remove prod` stops nginx and forgets the load balancer. The functions keep running on the
cluster, and users reach the servers on their own ports again.

## Live requests: which server handled what

The cluster page's **Live requests** card lists requests as they happen: time, the **server** and **replica** that
handled each one, method and path, status, duration and function, plus every server's URL and its share of HTTP
(click a server to see only its requests). It polls the main replica every 2 seconds, and only while the card is on screen, the browser tab is
visible and *Live* is on. Off screen it does nothing.

```bash
pskit cluster requests prod --follow
#   12:04:53  edge1        main                   200     45.4 ms  send: POST /send
#   12:04:53  edge2        node-b-2               500     10.9 ms  hello: GET /hello
```

Each replica knows the server it runs on (`PSKIT_NODE`, set by the orchestrator) and records it with each request;
web replicas ship their entries to the main replica every second. `GET /__pskit/requests?since=N` on the
deployment's port returns them (admin token required).

The same command prints a balance table before the requests, and again when the HTTP counts change. It lists
**every** server of the cluster, including ones that have handled nothing yet:

```text
The master's URL is the main replica. Each other server's URL is one web replica. A load balancer is optional, and only when you want one URL for all of them.
  server           serves  requests   share  url
  edge1            main           0    0.0%  http://10.0.0.5:8080
  edge2            web            2  100.0%  http://10.0.0.6:8080
```

On Swarm and k3s every URL spreads HTTP across the web replicas (`serves` is `web`). On Nomad the master's URL is
the main replica and each other URL is that server's web replica. Schedules and other non-HTTP events stay in
the request list and are left out of the share.

## Live logs

`pskit logs -f` and the studio's **Logs** view follow a cluster deployment the same way they follow one machine.
The cluster page has a **Live logs** card for the deployment selected there.

Web replicas send their lines to the main replica. On Swarm and k3s the tail reads that collected buffer (the
published port forwards `/__pskit/logs` to the main replica). On Nomad each server listens on its own port, so
the tail reads every server's own buffer and shows them together. A web replica's lines show even when that
server cannot reach the main replica. Picking one server in the Logs view reads that server only.

## Monitor, scale and add servers when it is full

The studio's **Scaling cluster** page shows every server's CPU (over one second), memory and disk with the
limits, the orchestrator's view (ready, drained, offline), each deployment's running / desired replicas, and
replicas that cannot be placed. It refreshes every 30 seconds. From a shell:

```bash
pskit cluster status prod
#   server         role    state       cpu   mem  disk  load
#   edge1          master  ready       91%   62%   40%  3.1 2.8 2.5  FULL (cpu)
#   edge2          worker  ready       88%   71%   35%  2.9 2.7 2.6  FULL (cpu)
#   limits: cpu 85%  memory 85%  disk 90%
#   workload pskit-shop-prod_web: 4/6 running
#   pending  pskit-shop-prod_web.5: no suitable node (insufficient resources on 2 nodes)
# FULL: all 2 server(s) are over a capacity limit; 2 replica(s) cannot be placed. Add a server: pskit cluster join prod SERVER
```

The cluster counts as **full** when any of these holds:

* every reachable, schedulable server is over a limit (default CPU 85 %, memory 85 %, disk 90 %);
* replicas cannot be placed: the orchestrator found no server with the CPU / memory a replica reserves;
* no server is ready.

**Add capacity on the go.** Join another server: *+ Join server* in the studio (it can save a new server in the
same dialog), or `pskit cluster join prod edge3`. Then raise the replicas: the *Scale* button for a quick change,
or `options.cluster.replicas` so the next deploy keeps it. To retire a server, `pskit cluster leave prod edge2`
drains it first, so its replicas move to the others.

**Remove the whole cluster, master included.** The master cannot leave on its own, since the others depend on it.
`pskit cluster remove prod --uninstall` (in the studio: *Remove* on the master's row) takes off everything pskit
installed: the deployments stop, the cluster's load balancer is removed and named load balancers drop its routes,
the agent is uninstalled from every joined server, then the orchestrator from the master (Swarm: `docker swarm
leave`; k3s: its uninstall scripts, images included; Nomad: the agent, its binary, unit, config and data), with
the deployments' images and the `pskit-cluster` folder. Docker itself and the saved servers stay. The main
replicas' data stays on the master unless you add `--delete-data` (*Uninstall and delete data*). A server that
does not answer is reported and skipped. Without `--uninstall`, `pskit cluster remove` only forgets the cluster.

### Alert DevOps (optional)

When the cluster is full, pskit can call **one of your functions** and / or POST to a **webhook** (Slack, Teams,
Google Chat or any URL), at most once per cooldown (default 30 minutes):

```bash
pskit cluster alerts prod --function notify-devops --webhook https://hooks.slack.com/services/... --cooldown 30
pskit cluster alerts prod --cpu 80 --memory 90 --disk 90       # when a server counts as full
pskit cluster alerts prod --test                               # send a test alert now
```

The function gets `event.data`:

```json
{
  "type": "pskit.cluster.capacity", "test": false, "cluster": "prod", "orchestrator": "swarm", "full": true,
  "subject": "[pskit] cluster prod needs another server",
  "message": "pskit cluster prod is full: all 2 server(s) are over a capacity limit. Add a server: pskit cluster join prod SERVER",
  "reasons": ["all 2 server(s) are over a capacity limit"],
  "nodes": [{"server": "edge1", "role": "master", "cpu": 91.0, "memory": 62.0, "disk": 40.0, "over": ["cpu"], "...": "..."}],
  "workloads": [{"name": "pskit-shop-prod_web", "running": 4, "desired": 6}],
  "pending": ["..."], "capacity": {"cpu": 85, "memory": 85, "disk": 90}, "checked_at": "2026-10-24T09:00:00Z"
}
```

A mail to DevOps from that function (any SMTP relay you have):

```python
import os
import smtplib
from email.message import EmailMessage


def notify_devops(event, ctx):
    alert = event.data
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.environ["ALERT_FROM"], os.environ["DEVOPS_EMAIL"], alert["subject"]
    lines = [alert["message"], ""] + [
        f"{n['server']:<12} cpu {n['cpu']}%  memory {n['memory']}%  disk {n['disk']}%  {'FULL' if n['over'] else ''}"
        for n in alert["nodes"]
    ]
    msg.set_content("\n".join(lines))
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)
    return {"sent": True}
```

The function runs on the deployed host of the stage set with `--stage` (or any deployed on-prem stage of this
project): it must be deployed. The webhook body has `text` (what Slack / Teams show) plus the same fields.

**Who checks?** Checks run where pskit runs:

* the studio, while it is open, with *Watch while the studio runs* (every 60 s by default);
* `pskit cluster watch prod --interval 60` around the clock on an always-on machine (a systemd unit, `tmux`, ...),
  or `pskit cluster check prod` from cron. `check` exits with status 3 when the cluster is full.

Recent alerts are listed on the cluster page (and kept in `.pskit/onprem-clusters.json`).

## Where things are kept

| What | Where |
|---|---|
| Clusters, joined servers, load balancer, limits, alert settings, recent alerts, deployments | `.pskit/onprem-clusters.json` (out of git) |
| All of the above on another machine | `pskit settings export` here, `pskit settings import` there (one encrypted file with the SSH logins and keys; [cli.md](cli.md#pskit-settings)) |
| The load balancer's nginx config | `~/pskit-cluster/lb/conf.d/` on the load balancer server (one file per deployment) |
| SSH logins | the saved servers (`.pskit/onprem-servers.json`; passwords in `.pskit/ssh/`) |
| Join tokens | never stored: read from the master at each join; the join script deletes itself |
| Scripts and manifests pskit runs | `~/pskit-cluster/` on the servers |

## Commands

| Command | |
|---|---|
| `pskit cluster create NAME -o swarm\|kubernetes\|nomad --master SERVER [--advertise IP] [--[no-]master-serves]` | install on the master and save |
| `pskit cluster join NAME SERVER [--advertise IP]` | add a server (installs, joins, copies images) |
| `pskit cluster set NAME --master-serves\|--no-master-serves` | send requests to the master too, or keep it as a backup only |
| `pskit cluster leave NAME SERVER` | drain and remove a server |
| `pskit cluster status NAME [--json]` | servers, replicas, full or not |
| `pskit cluster check NAME [--no-alert]` | status once and the alert when full (exit 3 when full) |
| `pskit cluster watch NAME [--interval 60]` | check until Ctrl+C |
| `pskit cluster alerts NAME [--function F] [--stage S] [--webhook URL] [--cooldown M] [--cpu/--memory/--disk %] [--test]` | alert settings |
| `pskit cluster scale NAME --replicas N [--stack S]` | web replicas now (until the next deploy) |
| `pskit cluster requests NAME [--follow] [--stack S]` | recent requests, and each server's URL with its share of HTTP |
| `pskit cluster balancer set NAME SERVER [--port 80] [--address IP]` | nginx on a server outside the cluster: one URL for all of it |
| `pskit cluster balancer sync NAME` / `logs NAME [-n 100]` / `remove NAME` | rewrite its config now / its access log / stop it |
| `pskit cluster list` / `pskit cluster remove NAME` | list / forget a cluster |
| `pskit cluster remove NAME --uninstall [--delete-data]` | uninstall the cluster from the master and every server, then forget it |
| `pskit deploy --cluster NAME` / `pskit deploy --server NAME` | deploy the functions to the cluster / to one server |
| `pskit resources onprem create KEY --service S --cluster NAME [--node SERVER]` | a resource on a server of the cluster |

## Limits and notes

* Docker must run on **your** machine to build the image; servers need Linux (x86_64 or arm64) with SSH, and
  root or passwordless `sudo`.
* The main replica is one process on the master: schedules, built-in queues and workflow executions do not
  scale out. Use a queue driver (Redis, SQS, ...) when queue consumers must scale with the replicas.
* Nomad serves each server on its own port. The master's port is the main replica, and each other server runs
  one web replica. For one URL for all of them, add a [load balancer](#load-balancer-one-url-for-the-whole-cluster-optional).
* The load balancer is one server: if it goes down, its URL does. For no single point there, put two behind a
  floating IP (keepalived) or DNS with both addresses, each set up with the same nginx config.
* The orchestrators' own security is yours to tighten: limit the cluster ports to your network, and enable Nomad
  ACLs or Kubernetes RBAC as your policies need.
