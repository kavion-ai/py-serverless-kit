# Run the full application on your own servers (on-prem, cluster, load balancer)

Search terms: on-premises tutorial, onprem end to end, own servers, self-hosted, bare metal, VM, cluster walkthrough, Docker Swarm, load balancer, PostgreSQL replication, Redis, MinIO, firewall, network map

This guide runs the **orders service** from [end-to-end-cli.md](end-to-end-cli.md) on your own Linux servers: save
the servers, install Docker, start PostgreSQL (with a read replica), Redis and MinIO as services, deploy to one
server, then grow to a Docker Swarm cluster with more replicas behind a load balancer, and check the firewall
rules. Every step is shown in studio and in the terminal. The handler code does not change.

## What you build and the machines you need

The orders service on premises uses five Linux servers reachable over SSH (root, or a user with passwordless
`sudo`). The addresses are examples; use yours.

| Saved server | Address | Role |
|---|---|---|
| `app1` | 10.0.0.5 | functions; later the cluster master |
| `app2` | 10.0.0.6 | joins the cluster |
| `db1` | 10.0.0.11 | PostgreSQL primary and pgpool-II (one address for the functions) |
| `db2` | 10.0.0.12 | PostgreSQL read replica, Redis cache, MinIO bucket |
| `lb1` | 10.0.0.9 | the load balancer (OpenResty), outside the cluster |

```text
users -> lb1:80 (/orders/) -> app1:8080, app2:8080 (Swarm)  -> pgpool db1:6432 -> postgres db1 (writes), db2 (reads)
                                                             -> redis db2:6379, minio db2:9000
```

On your own machine you need pskit, OpenSSH (`ssh`, `scp`) and Docker (a cluster deploy builds the image here).
`pskit doctor -p onprem` checks them. The queue (`order-jobs`) and topic (`order-events`) use the host's built-in
services, so they need no broker. Terms: [concepts.md](concepts.md#on-premises-terms).

## Make on-premises the provider of the project

The on-prem provider (`onprem`) runs the functions in a pskit **host** process on your servers. In this guide it
is the main provider, so the services you create are written straight into `pskit.yml`.

**From the terminal**: change the `provider` block of the orders `pskit.yml` (keep the rest):

```yaml
provider:
  name: onprem
  region: local
  stage: prod
  runtime: python3.12
  memory: 256
  timeout: 15
  environment:
    LOG_LEVEL: INFO
  options:
    host: 0.0.0.0                              # listen on every interface of the server
    port: 8080                                 # the functions' HTTP port
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"  # protects the host's /__pskit/* admin API
```

Remove `ORDERS_DB_URL` / `CACHE_URL` from `environment`, the `custom:` block and the `name:` line of the
`receipts` resource; the services below write their own settings. Then `pskit validate`.

**In studio**: **Overview & provider** → **Provider** → click the **On-premises** card → confirm **Switch
provider**. Under **Defaults for every function** set **Region** `local` and **Stage** `prod`. Top bar: **validate &
deploy as** *On-premises*, **stage** `prod`. **Save**.

Every on-prem option: [providers/onprem/README.md](../providers/onprem/README.md).

## Save the servers once

A **saved server** is an SSH login stored under a name; deploys, services, clusters and load balancers refer to
it by that name. Passwords are never written to `pskit.yml`.

**From the terminal**:

```bash
pskit resources onprem servers add app1 --ssh root@10.0.0.5 --pem ~/.ssh/shop.pem
pskit resources onprem servers add app2 --ssh root@10.0.0.6 --pem ~/.ssh/shop.pem
pskit resources onprem servers add db1  --ssh root@10.0.0.11 --pem ~/.ssh/shop.pem --data-dir /data/pskit
pskit resources onprem servers add db2  --ssh root@10.0.0.12 --pem ~/.ssh/shop.pem --data-dir /data/pskit
pskit resources onprem servers add lb1  --ssh root@10.0.0.9 --pem ~/.ssh/shop.pem
pskit resources onprem servers list
pskit resources onprem servers test app1     # OS, CPU, memory, disk, Docker access, sudo
```

`add` logs in once to test (`--no-test` skips it). Not root? Add `--sudo`. Password login: `--ssh-password-env
VAR`. Optional per-server defaults: `--home`, `--bind`, `--data-dir`.

**In studio**: **Resources** → scroll to **On-prem services** → **Servers** → **+ Add server**. In **Add a
server** fill **Name** `app1`, **Host** `10.0.0.5`, **User** `root`, **SSH port** `22`, **Log in with** **Key file
(.pem)**, **Private key (.pem)**; optional **Use sudo**, **Home path**, **Bind address**, **Data directory**,
**Description**. Click **Save and test**. Repeat for the others. Each row has **Test**, **Live**, **Shell**,
**Terminal**, **Install / create**, **Edit** and **Forget**; **Used in** shows where a server is used.

More: [onprem/servers.md](../onprem/servers.md), [studio-guide/servers.md](../studio-guide/servers.md).

## Install Docker and Python on the servers

Every on-prem service runs in Docker, and a single-server deploy with `method: ssh` runs the host with the
server's Python. pskit installs both from its catalog with the server's package manager.

**From the terminal** (`KEY` is just a name for the install):

```bash
pskit resources onprem catalog                       # services and runtimes you can create
pskit resources onprem create docker-app1 --service docker --server app1
pskit resources onprem create docker-db1  --service docker --server db1
pskit resources onprem create docker-db2  --service docker --server db2
pskit resources onprem create py312-app1  --service python --version 3.12 --server app1
```

Docker on `app2` and `lb1` is installed by `cluster join` and `lb create` when it is missing.

**In studio**: **Resources** → **Servers** → **Install / create** on the `app1` row. The catalog opens with the
server chosen; under **Install on a server: languages & Docker** pick **Docker**, click **Install**, and watch the
log. Then **Python** with **Version** `3.12`. Repeat for `db1` and `db2`.

Need a shell? **Shell** runs single commands, **Terminal** opens a full SSH terminal in the browser
(`pskit resources onprem terminal --server app1`). More:
[onprem/terminal-and-software.md](../onprem/terminal-and-software.md).

## Create the replicated PostgreSQL database

`orders-db` is created as a **primary + read replicas** database: `db1` takes the writes, `db2` keeps a copy and
answers reads, and pgpool-II on `db1` gives the functions one address that splits them.

**From the terminal**:

```bash
pskit resources onprem create orders-db --service postgres --primary db1 --replica db2 \
    --balancer db1 --sync async --save
pskit resources onprem replicas list orders-db       # members, state, replication lag
```

**In studio**: **Resources** → **+ On-prem service** (or **On-prem services** → **+ Create service**). Under
**Databases** click **PostgreSQL**. Fill **Resource key** `orders-db`, **Scaling** **Primary + read replicas**,
**Members run on** **Saved servers**, **Primary (writes)** `db1`, **Read replicas** `db2`, **Primary → replicas**
**Asynchronous (fastest)**, **Load balancer** *pgpool-II on db1*. The form draws the topology. Click **Create**;
the job log streams below. Review the draft and **Save**.

The generated password and URLs go to `.env.onprem` (`PSKIT_ORDERS_DB_URL` points at pgpool-II), never to
`pskit.yml`. The resource gets `connection.url_env: PSKIT_ORDERS_DB_URL`, so `app/store.py` works unchanged.
Engines, sync vs async and failover: [onprem/database-scaling.md](../onprem/database-scaling.md); the form:
[studio-guide/replication.md](../studio-guide/replication.md).

## Create the Redis cache and the MinIO bucket

**From the terminal**:

```bash
pskit resources onprem create cache --service redis --role cache --server db2 --save
pskit resources onprem create receipts --service minio --server db2 --attach receipt-uploaded --save
pskit resources onprem list
pskit resources onprem status cache            # state, health, endpoint (--reveal shows credentials)
pskit resources onprem console cache "INFO server"
```

**In studio**: **+ Create service** → **Redis**. **Resource key** `cache`, **Use as** **Cache**, **Where** **One
SSH server**, **Server** `db2`, **Listen on** **Network (0.0.0.0)** (the functions run on other servers).
**Create**. Then **+ Create service** → **MinIO**: **Resource key** `receipts`, **Use as** **Bucket**, **Where** **One
SSH server**, **Server** `db2`, tick `receipt-uploaded` under **Trigger functions**. **Create**, then **Save**.

Each service row has **Details**, **How to use**, **Browse** (MinIO), **Console**, **Terminal**, **Backup**
and **Remove**. The cache stays bound to `get-order` and `list-orders` only: keep `functions:` on the `cache`
resource. More: [onprem/services/README.md](../onprem/services/README.md),
[onprem/resources.md](../onprem/resources.md).

## What the services wrote to pskit.yml

With `--save` (or **Save** in studio) the three services replace the cloud definitions of `orders-db`, `cache`
and `receipts`, and `env_file` is added once. It looks like this (hosts from your servers):

```yaml
provider:
  options:
    env_file: .env.onprem            # shipped next to the host, loaded at start, never in Terraform state
resources:
  orders-db:
    type: database
    external: true
    connection: {host: 10.0.0.11, port: 6432, database: orders_db, user: pskit,
                 password_env: PSKIT_ORDERS_DB_PASSWORD, url_env: PSKIT_ORDERS_DB_URL}
  cache:
    type: cache
    external: true
    connection: {host: 10.0.0.12, port: 6379, url_env: PSKIT_CACHE_URL, password_env: PSKIT_CACHE_PASSWORD}
    functions: [get-order, list-orders]   # add it back if it was dropped
  receipts:
    type: storage
    external: true
    options: {driver: minio, endpoint: "http://10.0.0.12:9000", bucket: receipts,
              access_key_env: PSKIT_RECEIPTS_ACCESS_KEY, secret_key_env: PSKIT_RECEIPTS_SECRET_KEY}
  order-jobs: {type: queue}          # built-in queue of the host
  order-events: {type: topic}        # built-in topic of the host
```

`.env.onprem` holds the passwords; keep it and `.pskit/` out of git. `--save` rewrites `pskit.yml` without its
comments.

## Deploy to one server first

Start with one server: `app1` runs the host as a process (`method: ssh`), next to its Python 3.12.

**From the terminal**:

```bash
export PSKIT_ADMIN_TOKEN="$(openssl rand -hex 16)"
pskit validate
pskit deploy --server app1          # the stage remembers app1 for later commands
pskit info                          # deployed on: app1 (10.0.0.5), URLs of every function
```

To make it permanent per stage, set `provider.options.deploy: {server: app1}` in `pskit.yml`. A server with no
Python can use `deploy: {server: app1, python: bundle}` or `method: docker`.

**In studio**: **Deploy**. Under **Run on** choose **One machine** and **Machine** `app1 (...)`. Click the
**Deploy** card and confirm *Deploy to onprem/prod on app1?* (type `onprem/prod`, it is a production stage). The
**Steps** tab shows each phase; **Raw log** the full output. **Info** prints the URLs.

The deploy prints the firewall rules the new setup needs. More: [deployment/README.md](../deployment/README.md).

## Call the API, send events and read the logs on premises

The host answers on `http://10.0.0.5:8080`.

**From the terminal**:

```bash
curl -X POST http://10.0.0.5:8080/orders -H "content-type: application/json" \
     -d '{"customer": "ada", "items": [{"sku": "A1", "price": 5, "qty": 2}]}'
pskit trigger --list
pskit resources send order-jobs -d '{"order_id": "<id>"}'     # the built-in queue -> process-order
pskit resources send receipts -d '{"key": "incoming/r1.pdf", "content": "x"}'   # an object in MinIO
pskit workflow start fulfil-order -i '{"id": "o1", "total": 20, "items": [{"sku": "A1", "qty": 1}]}' --wait
pskit logs -f                                                  # the host's log buffer
pskit logs --function process-order --level WARNING
```

**In studio**: **Test** → pick a function → **☁ Send to onprem / prod** (the **Server** select picks the
machine). **Resources** → **Data** on `order-jobs` or `receipts` shows what they hold; **Test** sends a sample.
**Logs** shows every function's log, with a **Server** select. More: [deployment/logs.md](../deployment/logs.md).

## Create a Docker Swarm scaling cluster and join a server

A **scaling cluster** runs the functions on a master plus joined servers. pskit installs the orchestrator over SSH.
Docker Swarm is used here; Kubernetes (k3s) and Nomad work the same way.

**From the terminal**:

```bash
pskit cluster create prod --orchestrator swarm --master app1     # --advertise 10.0.0.5 on a private network
pskit cluster join prod app2
pskit cluster list
```

**In studio**: **Scaling cluster** → **+ New cluster**. In **New scaling cluster** fill **Cluster name** `prod`,
**Orchestrator** **Docker Swarm**, **Master server** `app1`, optional **Cluster address (optional)** and the
**Master serves requests** switch (*Send requests to the master too, not only to the joined servers*). Click
**Create** and wait for *Installing…* to finish. Then **+ Join server** → **Server** `app2` → **Join**.

Ports between the servers (Swarm: 2377/tcp, 7946/tcp+udp, 4789/udp) are listed in the
[network rules](../onprem-network.md). Compare orchestrators: [onprem/scaling/README.md](../onprem/scaling/README.md).
The page: [studio-guide/cluster.md](../studio-guide/cluster.md).

## Deploy the orders service to the cluster

The cluster deploy builds a Docker image on your machine, copies it to every server, and runs one main replica
on the master (schedules, queues, workflows, data) plus web replicas spread over the servers.

**From the terminal**: point the functions at the cluster in `pskit.yml`, then deploy:

```yaml
provider:
  options:
    cluster:
      name: prod
      replicas: 3        # web replicas (default 2), plus 1 main replica on the master
      cpu: 0.25          # cores each replica reserves
      memory: 256        # MB each replica reserves
```

```bash
pskit deploy --cluster prod      # moves the stage from app1 to the cluster
pskit info                       # deployed on: cluster prod (master app1 (10.0.0.5))
pskit remove --server app1       # optional: stop the old single-server deploy
```

**In studio**: **Scaling cluster** → `prod` → switch on *Deploy this project's functions to prod*
(`provider.options.cluster`), set **Web replicas** `3`, **CPU per replica** `0.25`, **Memory per replica (MB)**
`256`, **Save**. Then **Deploy** → **Run on** **Scaling cluster** → select `prod` → **Deploy**.

More: [cluster.md](../cluster.md), [onprem/scaling/docker-swarm.md](../onprem/scaling/docker-swarm.md).

## Scale the replicas and watch the cluster

The cluster counts as **full** when every server is over a limit (CPU 85 %, memory 85 %, disk 90 % by default) or
replicas cannot be placed. Add a server, then raise the replicas.

**From the terminal**:

```bash
pskit cluster status prod                   # CPU, memory, disk per server, replicas, FULL or not
pskit cluster scale prod --replicas 6       # now, until the next deploy
pskit cluster requests prod --follow        # which server answered each request
pskit cluster alerts prod --function notify-email --test   # who hears when it is full
pskit cluster watch prod --interval 60
```

Keep a new count by changing `options.cluster.replicas` and deploying.

**In studio**: **Scaling cluster** → `prod`. **Servers** shows CPU, **Memory** and **Disk** meters (refreshes every
30 s). **Deployed functions** has a **Web replicas** number and a **Scale** button. **Live requests** and **Live
logs** follow the traffic. **When every server is full** sets the limits, **Alert function**, **Webhook
(optional)** and **Cooldown (minutes)**. **Remove** on a joined server drains it first
(`pskit cluster leave prod app2 --yes`).

More: [onprem/scaling/replicas-and-alerts.md](../onprem/scaling/replicas-and-alerts.md).

## Put a load balancer in front of the cluster

A **load balancer** is OpenResty (nginx) in Docker on a saved server outside the cluster. A named load balancer is
shared by path: every deployment on an attached cluster gets `http://<lb>/<service>/`, so the orders API is
`http://10.0.0.9/orders/`.

**From the terminal**:

```bash
pskit lb algorithms                                          # the six algorithms, pros and cons
pskit lb create edge --server lb1 --algorithm least_connections
pskit lb attach edge --cluster prod
pskit lb status edge                                         # routes, health, server use
curl http://10.0.0.9/orders/orders
pskit lb logs edge -n 50                                     # each request with the server that answered
```

A custom path or algorithm for this project: `provider.options.balancer: {name: edge, path: shop, algorithm:
sticky_round_robin}`. A load balancer for one cluster only: `pskit cluster balancer set prod lb1`.

**In studio**: **Load balancers** → **+ Create load balancer**. In **New load balancer** fill **Name** `edge`,
**Server** `lb1`, **Port** `80`, **Address in the URL (optional)**, pick **Least connections** under **How it
spreads requests**, tick `prod` under **Attach clusters now (optional)**, **Create**. Later: **+ Attach cluster**,
**Update**, **Sync**, **Logs**, and the *Put this project on edge* switch with **Path** and **Algorithm for this
route**. More: [onprem/load-balancers.md](../onprem/load-balancers.md), [load-balancers.md](../load-balancers.md),
[studio-guide/load-balancers.md](../studio-guide/load-balancers.md).

## Add another read replica when reads grow

Read replicas scale database reads horizontally. pgpool-II sends writes, transactions and `SELECT ... FOR UPDATE`
to the primary and spreads plain reads over the replicas.

**From the terminal** (after saving a `db3` server):

```bash
pskit resources onprem replicas add orders-db db3      # copies the data, follows the primary, joins pgpool
pskit resources onprem replicas list orders-db
pskit resources onprem replicas remove orders-db r2     # by name, or by its server
pskit resources onprem monitor orders-db                # CPU, memory, connections, replica lag
```

**In studio**: **Resources** → **On-prem services** → `orders-db` → **Details**. The drawer draws the primary,
replicas and load balancer with each member's state and lag. Pick *Server for a new replica…* and click **+ Add
read replica**.

The handlers do not change: `PSKIT_ORDERS_DB_URL` keeps pointing at pgpool-II. More:
[onprem/database-scaling.md](../onprem/database-scaling.md).

## Check the network map and the firewall rules

Each step needs ports open between the servers. pskit lists them per server, with who connects and why.

**From the terminal**:

```bash
pskit firewall                 # every server: inbound / outbound, REQUIRED / NEEDED / optional, ufw commands
pskit firewall --server db1
pskit resources onprem servers usage    # where each saved server is used
```

**In studio**: **Network map** draws every server and its connections; click a machine for **Inbound — accept**,
**Outbound — open** and **Used in**. **Refresh** reloads it. The **Firewall** section on **Deploy** (and on the
cluster and load balancer pages) lists the rules with a copy button for the `ufw` commands.

More: [onprem/network-map.md](../onprem/network-map.md), [onprem/firewall.md](../onprem/firewall.md),
[onprem-network.md](../onprem-network.md), [studio-guide/network.md](../studio-guide/network.md).

## Remove the deployment, cluster and services

Remove in the reverse order. Saved servers and Docker stay; data is kept unless you ask to delete it.

```bash
pskit remove --yes                                  # the deployment on the cluster
pskit lb detach edge --cluster prod && pskit lb remove edge --yes
pskit cluster remove prod --uninstall --yes         # uninstall Swarm from every server (--delete-data too)
pskit resources onprem remove receipts --save       # --delete-data also deletes the volume
pskit resources onprem remove cache --save
pskit resources onprem remove orders-db --save
pskit resources onprem servers remove lb1           # only forgets the login
```

**In studio**: **Deploy** → **Remove**; **Load balancers** → **Remove**; **Scaling cluster** → **Remove** on the
master's row (*Uninstall* or *Uninstall and delete data*); **Resources** → **On-prem services** → **Remove**
(**Remove, keep data** or **Delete data too**); **Servers** → **Forget**.

## Ask Hana to do the on-prem steps

Hana turns on-prem requests into cards you confirm; nothing runs until you click. Open **Ask Hana** (Ctrl+I).

| You type | Card |
|---|---|
| "add a server app2 ssh root@10.0.0.6 key ~/.ssh/shop.pem" | **Add server**, then **Save & test** |
| "install docker on app2" | a **Run** card with `pskit resources onprem create docker --service docker --server app2` |
| "create redis on db2 as cache" | **Create on-prem service** |
| "create a cluster prod on app1" | **Create scaling cluster** |
| "create a load balancer edge on lb1" | **Create load balancer** |
| "how many servers are there?" | the answer from your saved servers |

Details: [assistant.md](../assistant.md#servers-and-on-prem-services-cards-you-confirm).

## See also

- [Learning path](README.md) and [concepts](concepts.md)
- [The same app on AWS from the terminal](end-to-end-cli.md)
- [The same app in studio](end-to-end-studio.md)
- [On-premises overview](../onprem/README.md)
- [Scaling options compared](../onprem/scaling/README.md)
- [Placement: function groups on different servers](../onprem/placement.md)
- [On-prem provider](../providers/onprem/README.md)
