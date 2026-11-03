"""Category A (docs Q&A and how-to), batch 16: on-prem scenarios, bundle layout, Node.js limits, web UIs of one-click
services, and replicated databases. Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


SC = "docs/scenarios.md"
AR = "docs/architecture.md"
NJ = "docs/nodejs.md"
SV = "docs/resource-guides/onprem/services.md"
DBS = "databases-one-server-or-a-primary-with-read-replicas"

CONVERSATIONS = [
    A(301, provider="onprem", stage="prod", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{SC}#d-on-premises-with-redis-and-minio"],
      user="I copied scenario D (Redis + MinIO) where the Redis URL is redis://:${env:REDIS_PASSWORD}@... and access_key: ${env:MINIO_ACCESS_KEY}. Our security team says no secrets in Terraform state. Is that config OK?",
      steps=[S("search_docs", query="redis minio on premises env values state",
               docs=[D(SC, "d-on-premises-with-redis-and-minio", start="**Verify:**")])],
      final="""Not for that rule. `${env:...}` values end up in `pskit_host.json` and Terraform state. Write `_env` parameters instead and export the variables where the host runs [docs/scenarios.md#d-on-premises-with-redis-and-minio].

**In code**
```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis
      url_env: REDIS_URL
      key: media-jobs
  uploads:
    type: storage
    external: true
    name: uploads
    options:
      driver: s3
      endpoint: http://minio.example.com:9000
      access_key_env: MINIO_ACCESS_KEY
      secret_key_env: MINIO_SECRET_KEY
      prefix: incoming/
```
`REDIS_URL` now holds the whole URL with the password. Put the three variables in the host's env file (`provider.options.env_file`), which is shipped as `host.env` and recorded only by its digest."""),

    A(302, provider="onprem", stage="dev", mode="auto", page="Resources", persona="terse_expert",
      sources=[f"{SC}#d-on-premises-with-redis-and-minio"],
      user="redis-driver queue with dead_letter: jobs-dlq. where do dead letters land, redis or local?",
      steps=[S("search_docs", query="dead letter redis driver builtin queue",
               docs=[D(SC, "d-on-premises-with-redis-and-minio", start="`dead_letter: jobs-dlq` is a builtin", end="`dead_letter: jobs-dlq` is a builtin")])],
      final="""Local. `jobs-dlq` is a builtin directory queue on the host unless you declare a Redis resource named `jobs-dlq` [docs/scenarios.md#d-on-premises-with-redis-and-minio].

To keep them in Redis:
```yaml
resources:
  jobs-dlq:
    type: queue
    external: true
    options:
      driver: redis
      url_env: REDIS_URL
      key: media-jobs-dlq
```"""),

    A(303, provider="onprem", stage="prod", mode="ask", page="Logs", persona="terse_expert",
      sources=[f"{SC}#i-on-premises-logs"],
      user="terminal only: durations and status codes of every invocation as JSON lines, plus only errors of worker",
      steps=[S("search_docs", query="on-prem logs invocation json errors",
               docs=[D(SC, "i-on-premises-logs", start="pskit logs  ", end="pskit logs --source invocation --json")])],
      final="""**In the terminal**
```bash
pskit logs --source invocation --json
pskit logs --function worker --level error
```
[docs/scenarios.md#i-on-premises-logs]"""),

    A(304, provider="onprem", stage="prod", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{SC}#k-on-premises-watching-queues-and-buckets-in-other-clouds"],
      user="GET /__pskit/stats -> \"queues\": {\"orders\": 12, \"events\": null}\nevents is a pubsub driver queue. broken?",
      steps=[S("search_docs", query="stats queue depth null pubsub",
               docs=[D(SC, "k-on-premises-watching-queues-and-buckets-in-other-clouds", start="**Verify:**", end="after `max_receive` deliveries.")])],
      final="""Not broken. Pub/Sub has no backlog API, so its depth is `null`. The SQS queue (`orders`) does report its backlog [docs/scenarios.md#k-on-premises-watching-queues-and-buckets-in-other-clouds].

To see that `events` works, check the invocations:
```bash
pskit logs -f --source invocation
pskit logs --source host
```
The second one shows connection or permission problems with the subscription."""),

    A(305, provider="onprem", stage="prod", mode="ask", page="Overview", persona="detailed_spec",
      sources=[f"{AR}#bundle-layout"],
      user="For our backup plan: which folders does a running on-prem host keep its state in? Queues, workflow runs, logs, schedules?",
      steps=[S("search_docs", query="on-prem host state data_dir layout",
               docs=[D(AR, "bundle-layout", start="At run time the host keeps its state under `data_dir`")])],
      final="""Everything is under `data_dir` [docs/architecture.md#bundle-layout]:
- `queues/`, `buckets/`, `topics/`: the built-in services
- `executions/<id>.json`: workflow runs
- `logs/host.jsonl`: logs, rotated at 10 MiB
- `schedule-state.json` and `storage-snapshot.json`

Back up the whole `data_dir`. `pskit remove` doesn't delete it. Resources with a driver (Redis, MinIO, ...) keep their data in those services, so back them up there."""),

    A(306, provider="onprem", stage="dev", mode="ask", page="Deploy", persona="beginner",
      sources=[f"{AR}#bundle-layout"],
      user="what does pskit actually create on my pc when i deploy onprem? i see a .pskit folder",
      steps=[S("search_docs", query="on-premises files written onprem_app deploy",
               docs=[D(AR, "bundle-layout", start="On-premises also writes", end="waits until the container is healthy.")])],
      final="""`.pskit/onprem-<stage>/onprem_app/` holds `pskit_host.json`, `onprem_ctl.py`, `onprem_deploy.py`, `pskit-run.sh` for SSH, the staged bundle, and a Dockerfile or systemd unit when you use those methods [docs/architecture.md#bundle-layout].

Terraform runs `onprem_deploy.py apply`:
- **local**: starts the host on this machine;
- **ssh / scp**: packs `release.tar.gz`, copies it, extracts it on the server, restarts the process or unit, and waits for `/__pskit/health`;
- **docker**: builds an image here, and for a remote target copies it and waits until the container is healthy.

`.pskit/` is out of git, and you don't edit it by hand."""),

    A(307, provider="onprem", stage="dev", mode="ask", page="Functions", persona="informal_non_native",
      sources=[f"{NJ}#limitations"],
      user="can i have 2 function in python and 1 in node in same onprem service?",
      steps=[S("search_docs", query="python and node.js functions same service",
               docs=[D(NJ, "limitations")])],
      final="""No. It's one language per service. Split them into two services; they can call each other over HTTP or a queue [docs/nodejs.md#limitations].

For example, two folders, each with its own pskit.yml:
```yaml
service: orders-node
provider:
  name: onprem
  runtime: nodejs20
  options: {host: 0.0.0.0, port: 8081}
```
Give each service its own port. The Python service can reach the Node one at `http://<host>:8081`."""),

    A(308, provider="onprem", stage="dev", mode="auto", page="YAML", persona="terse_expert",
      sources=[f"{NJ}#dependencies-and-packaging"],
      user="node service on-prem with our own `npm run build` writing dist/. package keys?",
      steps=[S("search_docs", query="node package build out_dir typescript",
               docs=[D(NJ, "dependencies-and-packaging", end="npm_args: [--legacy-peer-deps]")])],
      final="""```yaml
package:
  source: .
  node:
    build: [npm, run, build]
    out_dir: dist
```
`build` replaces pskit's own `tsc`, and `out_dir` is bundled instead of `source`. Node.js 18+ and npm must be on PATH where you package [docs/nodejs.md#dependencies-and-packaging]."""),

    A(309, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#with-or-without-a-password"],
      user="i test on my laptop only, redis commander login every time is annoying. can it be without password?",
      steps=[S("search_docs", query="web ui without password redis commander",
               docs=[D(SV, "with-or-without-a-password", end="pskit prints a warning when a UI without login listens on `0.0.0.0`.")])],
      final="""Yes. Choose **Without password** for the web UI login. Keep it on `127.0.0.1` then, because anyone who reaches the port can use the UI, and the UI holds the service's credentials [docs/resource-guides/onprem/services.md#with-or-without-a-password].

**In the terminal**
```bash
pskit resources onprem gui cache --login none
```
That recreates the existing UI without a login. For a new service:
```bash
pskit resources onprem create cache --service redis --role cache --gui --gui-login none --bind 127.0.0.1
```

**In studio**
In **Resources > On-prem services**, open the service's **Details** and add the web UI again with *Web UI login* set to *Without password*.

Adminer always uses the database login; it has no "without password" option."""),

    A(310, provider="onprem", stage="prod", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{SV}#the-ui-does-not-open"],
      user="Queue browser: no answer from outside: a firewall drops the connection\n\nbut i already opened 9324 in the azure nsg!",
      steps=[S("search_docs", query="web ui does not open firewall drops connection azure nsg",
               docs=[D(SV, "the-ui-does-not-open", start="\"I allowed inbound and it still does not open\"", end="network tags if the rule uses target tags.")])],
      final="""9324 is the **service's** port. The queue browser is a separate UI port, 9325, and it needs its own rule [docs/resource-guides/onprem/services.md#the-ui-does-not-open].

Also check, on Azure:
- **both** NSGs on the path need the rule: the one on the subnet and the one on the network interface (VM > Networking shows both);
- the rule's source includes your public IP, and its priority number is lower than any Deny rule's.

**In the terminal**
```bash
pskit resources onprem gui jobs --check
```
It prints the exact port and the `az vm open-port` command. To skip the firewall entirely:
```bash
pskit resources onprem tunnel jobs --remote-port 9325
```
then browse `http://127.0.0.1:9325`."""),

    A(311, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SV}#try-the-web-uis-in-local-docker-first"],
      user="i dont have a server yet. can i try the redis and rabbitmq services and their web pages on my laptop?",
      steps=[S("search_docs", query="try one-click services local docker laptop",
               docs=[D(SV, "try-the-web-uis-in-local-docker-first", end="pskit resources onprem usage cache")])],
      final="""Yes. Everything works the same on your own machine with Docker Desktop, with no server and no firewall [docs/resource-guides/onprem/services.md#try-the-web-uis-in-local-docker-first].

**In the terminal**
```bash
pskit resources onprem create cache --service redis --role cache --local --gui
pskit resources onprem create mq --service rabbitmq --local
pskit resources onprem gui cache
```
The last line prints each URL and login. Redis Commander is at `http://127.0.0.1:8082`, the RabbitMQ management UI at `http://127.0.0.1:15672`.

**In studio**
In **Resources > On-prem services > + Create service**, choose *Where: This machine*.

Local services listen on `127.0.0.1`. Clean up with **Remove**, or `pskit resources onprem remove cache --delete-data`."""),

    A(312, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SV}#{DBS}"],
      user="Synchronous or asynchronous replication for our Postgres primary + replicas? What do we lose with each?",
      steps=[S("search_docs", query="synchronous asynchronous replication postgres replicas",
               docs=[D(SV, DBS, start="**Asynchronous** (default)", end="with *sync*.", words=120)])],
      final="""[docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas]
- **Asynchronous** (default): fastest. The primary commits at once, replicas follow a few milliseconds behind, so a primary crash can lose the last writes.
- **Synchronous**: no committed write is lost, at the cost of a round trip to a replica per commit. PostgreSQL waits while no replica is connected, so keep **at least two replicas** with sync.

**In the terminal**
```bash
pskit resources onprem create orders-db --service postgres --primary db-1 --replica db-2 --replica db-3 --balancer lb-1 --sync sync --save
```

**In studio**
In **Resources > On-prem services > + Create service**, PostgreSQL, *Scaling*: *Primary + read replicas*, then pick the synchronous option."""),

    A(313, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{SV}#{DBS}"],
      user="add a 3rd read replica db-4 to orders-db, and drop r1",
      steps=[S("search_docs", query="replicas add remove database",
               docs=[D(SV, DBS, start="pskit resources onprem replicas list orders-db", end="pskit resources onprem replicas remove orders-db r1 --delete-data")])],
      final="""```bash
pskit resources onprem replicas add orders-db db-4
pskit resources onprem replicas remove orders-db r1 --delete-data
pskit resources onprem replicas list orders-db
```
`add` copies the data, follows the primary and joins the load balancer. `list` shows members, state and lag [docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas].

In the studio, the database's **Details** has **+ Add read replica** and **Remove**."""),

    A(314, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SV}#{DBS}"],
      user="Our PostgreSQL primary on db-1 just died. The replicas are up. Does pskit fail over automatically?",
      steps=[S("search_docs", query="primary fails promote replica",
               docs=[D(SV, DBS, start="- If the primary fails:", end="- If the primary fails:")])],
      final="""No, not for PostgreSQL. The replicas keep serving reads, but promoting one is a manual step today: `pg_ctl promote` on the replica you choose [docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas]. Writes fail until then.

MongoDB is different: it elects a new primary on its own. MySQL / MariaDB are manual too (`STOP REPLICA; SET GLOBAL read_only=OFF`)."""),

    A(315, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#{DBS}"],
      user="i want see replication work but have only my laptop. possible?",
      steps=[S("search_docs", query="replicated database this machine try it",
               docs=[D(SV, DBS, start="- *This machine (try it)*", end="and by each other.", words=80)])],
      final="""Yes, for PostgreSQL, MySQL and MariaDB. *This machine (try it)* runs every member on your laptop on its own port, on a private Docker network [docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas].

**In the terminal**
```bash
pskit resources onprem create try-db --service mysql --primary local --replica local --replica local --balancer local
pskit resources onprem replicas list try-db
```
MongoDB needs real servers, because its members must be reached at the same address by the functions and by each other."""),

    A(316, provider="onprem", stage="prod", mode="ask", page="Code", persona="beginner",
      sources=[f"{SV}#{DBS}"],
      user="with primary and replicas, does my handler code need two connections, one for write and one for read?",
      steps=[S("search_docs", query="handler urls primary replicas write read",
               docs=[D(SV, DBS, start="The load balancer sends writes", end="the replicas are listed in `READ_URLS`."),
                     D(SV, DBS, start="Handlers do not change.", end="the replicas, comma separated |")])],
      final="""Not if you have a load balancer. It sends writes, transactions and `SELECT ... FOR UPDATE` to the primary and plain reads to the replicas, so one connection to `PSKIT_<KEY>_URL` is enough [docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas].

Without a load balancer, `URL` is the primary, and you read from the replicas in `PSKIT_<KEY>_READ_URLS` yourself.

**In code**
```python
from __future__ import annotations

import os

import psycopg


def report(event, ctx):
    url = os.environ["PSKIT_ORDERS_DB_URL"]
    with psycopg.connect(url) as conn:
        return {"orders": conn.execute("select count(*) from orders").fetchone()[0]}
```"""),

    A(317, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{SV}#{DBS}"],
      user="added a new db user after creating the pgpool setup, it can't log in through pgpool",
      steps=[S("search_docs", query="pgpool new database user custom users",
               docs=[D(SV, DBS, start="- pgpool-II knows the database user pskit created.", end="(`PGPOOL_POSTGRES_CUSTOM_USERS`).")])],
      final="""pgpool-II only knows the database user pskit created. Users you add later connect to the members directly, or must be added to pgpool via `PGPOOL_POSTGRES_CUSTOM_USERS` [docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas]."""),

    A(318, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SV}#{DBS}"],
      user="Can we put one read replica on the same server as the primary to save a machine?",
      steps=[S("search_docs", query="replica same server as primary",
               docs=[D(SV, DBS, start="- One member per server:", end="(its port differs).")])],
      final="""You shouldn't. A replica on the primary's server protects nothing: if that server fails, both are gone. Use one member per server [docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas].

The **load balancer** may share a server with a member, since its port differs. So with three machines: primary on db-1, replica on db-2, and pgpool on db-2 or a third box."""),

    A(319, provider="onprem", stage="dev", mode="ask", page="Resources", persona="aws_migrator",
      sources=[f"{SV}#{DBS}"],
      user="On RDS we used a MongoDB-compatible DocumentDB cluster. On-prem, can pskit create a MongoDB replica set and what URL do the functions get?",
      steps=[S("search_docs", query="mongodb replica set url functions",
               docs=[D(SV, DBS, start="| MongoDB | replica set", end="| MongoDB | replica set"),
                     D(SV, DBS, start="| `PSKIT_<KEY>_URL` |", end="| `PSKIT_<KEY>_URL` |")])],
      final="""Yes. pskit creates a replica set (`rs_<key>`) whose members share a generated key file. Synchronous means write concern `w: majority`. There's no load balancer: the driver routes from one replica set URL [docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas].

The functions get `PSKIT_<KEY>_URL`, the replica set URL with `readPreference=secondaryPreferred`.

**In the terminal**
```bash
pskit resources onprem create users-db --service mongodb --primary db-1 --replica db-2 --replica db-3 --save
```
MongoDB elects a new primary by itself if the primary fails."""),

    A(320, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SV}#{DBS}"],
      user="my postgres on one server is slow. what are my options with pskit?",
      steps=[S("search_docs", query="scale database single server replicas",
               docs=[D(SV, DBS, end="Add replicas later as reads grow.")])],
      final="""Two ways [docs/resource-guides/onprem/services.md#databases-one-server-or-a-primary-with-read-replicas]:
1. **Scale up**: give the server more CPU and memory. Nothing else changes.
2. **Scale out** with **Primary + read replicas**: the primary takes every write, each replica on another server answers reads, and an optional load balancer gives the functions one address.

**In studio**
In **Resources > On-prem services > + Create service**, pick PostgreSQL and choose *Primary + read replicas* under *Scaling*.

**In the terminal**
```bash
pskit resources onprem create orders-db --service postgres --primary db-1 --replica db-2 --balancer lb-1 --save
```
Replicas help only with reads. If writes are slow, scale up the primary or look at the queries first."""),
]
