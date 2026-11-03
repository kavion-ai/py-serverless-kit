# Scaling on-prem databases: primary, read replicas, database load balancer

Search terms: database scaling, replication, read replicas, primary, replica set, failover, pgpool-II, ProxySQL,
PostgreSQL, MySQL, MariaDB, MongoDB, replica lag, READ_URLS

An on-prem database created by pskit runs on one server by default. To scale reads, pskit can create it as a
**replicated database**: one **primary** that takes every write, **read replicas** on other servers that copy it and
serve reads, and an optional **database load balancer** that gives your functions one address and splits reads from
writes. Handler code does not change: the resource's URL points at the load balancer (or the primary).

## Which on-prem databases can be replicated

Replication is available for four on-prem database engines. Every other service (Redis, MinIO, ...) runs on a
single server.

| Engine | Replication | `sync` mode (a commit waits for a replica) | Database load balancer | Automatic failover |
|---|---|---|---|---|
| PostgreSQL | streaming replication (WAL) | `synchronous_standby_names = ANY 1 (*)`: no committed write lost, but writes wait while no replica is connected | pgpool-II (port 6432): writes and transactions to the primary, plain SELECTs to replicas | no |
| MySQL | GTID replication (binary log) | semi-synchronous: waits for one replica, back to async after 10 s without one | ProxySQL (port 6033): writes, transactions and `SELECT ... FOR UPDATE` to the primary, other SELECTs to replicas | no |
| MariaDB | GTID replication (binary log) | built-in semi-synchronous, same as MySQL | ProxySQL (port 6033) | no |
| MongoDB | replica set | write concern `majority` | none: the driver connects to every member from one replica set URL (`readPreference=secondaryPreferred`) | yes: the members elect a new primary and the driver follows |

`async` (the default) is fastest: the primary commits at once and replicas follow milliseconds behind, so a crash of
the primary can lose the last transactions. PostgreSQL, MySQL and MariaDB have **no automatic failover** in pskit:
if the primary is lost, writes stop until you fix or recreate it. When no replica is up, the load balancer sends
reads to the primary.

## Limits of on-prem database replication

On-prem database replication follows these rules (pskit refuses other layouts with a clear message):

* One member per saved server; at most 9 read replicas.
* Only a service with the `database` role is replicated.
* **Try it on this machine**: every member can run on your machine, each on its own port (replica 1 on port + 1,
  ...) on a private Docker network, with the load balancer there too. Not for MongoDB, whose members need servers.
* A replica on this machine cannot follow a primary on a server, and vice versa.
* Members on servers need Docker there (pskit installs it) and SSH from your machine.

## Create a replicated database in studio

The studio creates a replicated database from the **Resources** page.

1. Save every server first (**Resources → Servers**): one for the primary, one per replica, and one for the load
   balancer if you want one (it may share a server with a member).
2. In the **On-prem services** card click **+ Create service** and pick **PostgreSQL**, **MySQL**, **MariaDB** or
   **MongoDB**.
3. In **Scaling** choose **Primary + read replicas** (**Single server** is the default).
4. In **Members run on** choose **Saved servers** (or **This machine (try it)**).
5. Pick **Primary (writes)** and tick the servers under **Read replicas** (on this machine: the number of replicas).
6. In **Primary → replicas** choose **Asynchronous (fastest)** or **Synchronous (no lost writes)**.
7. In **Load balancer** pick `pgpool-II on <server>` / `ProxySQL on <server>`, or **None: connect to the primary,
   reads via READ_URLS**. Optionally set **Load balancer port**.
8. Create. The job output shows each member starting, the replicas joining, and the firewall rules.

## Create a replicated database from the terminal

The `pskit resources onprem create` command makes a database replicated when you pass `--replica`.

```bash
pskit resources onprem create orders-db --service postgres \
    --primary db1 --replica db2 --replica db3 \
    --balancer lb1 --sync async --save
```

| Option | Meaning |
|---|---|
| `--primary SERVER` | saved server that takes the writes |
| `--replica SERVER` | saved server for a read replica (repeat it); `local` runs every member on this machine |
| `--balancer SERVER` | saved server for pgpool-II / ProxySQL (not for MongoDB) |
| `--balancer-port N` | its port (default 6432 / 6033) |
| `--sync async\|sync` | replication mode (default `async`) |
| `--import FILE` | load a dump (`.sql`, `.sql.gz`, `.dump`, MongoDB `.archive`) into the primary before replicas copy it |
| `--save` | write the resource into `pskit.yml` |

## Connect to a replicated database from a function

A replicated database writes its connection values to the on-prem env file (default `.env.onprem`, never into
`pskit.yml`). For a key `orders-db` the variables are:

| Variable | Points at |
|---|---|
| `PSKIT_ORDERS_DB_URL` | the database load balancer; without one, the primary; MongoDB: the replica set URL |
| `PSKIT_ORDERS_DB_WRITE_URL` | the primary (PostgreSQL, MySQL, MariaDB) |
| `PSKIT_ORDERS_DB_READ_URLS` | the replicas, comma separated (PostgreSQL, MySQL, MariaDB) |

With a load balancer, use `_URL` for everything. Without one, send writes to `_WRITE_URL` and spread reads over
`_READ_URLS` yourself:

```python
import os
import random


def read_url():
    urls = [u for u in os.environ.get("PSKIT_ORDERS_DB_READ_URLS", "").split(",") if u]
    return random.choice(urls) if urls else os.environ["PSKIT_ORDERS_DB_WRITE_URL"]


def list_orders(event, ctx):
    url = read_url()          # pass it to your database driver (psycopg, PyMySQL, ...)
    return {"reading_from": url.split("@")[-1]}
```

## Add a database load balancer (pgpool-II or ProxySQL)

The database load balancer for a replicated PostgreSQL is pgpool-II (`bitnamilegacy/pgpool:4.6.3`); for MySQL and
MariaDB it is ProxySQL (`proxysql/proxysql:2.7.3`). It is chosen when the database is created (`--balancer`, or
the studio **Load balancer** field). It splits reads from writes so functions need only one address, and it keeps
sending reads to the new list when replicas are added or removed. MongoDB needs no load balancer.

This is separate from the HTTP [load balancers](load-balancers.md) (OpenResty) that sit in front of functions.

## Add or remove read replicas

Read replicas of an on-prem database are added and removed while it runs. A new replica copies the current data,
then follows the primary.

**In studio**: **Resources → On-prem services**, click **Details** on the database. In the replicas panel pick
**Server for a new replica…** and click **+ Add read replica**. **Remove** on a replica row removes it (the last
replica cannot be removed: remove the whole database instead).

**From the terminal**

```bash
pskit resources onprem replicas list orders-db        # members, state and replication lag
pskit resources onprem replicas add orders-db db4     # omit the server when every member runs on this machine
pskit resources onprem replicas remove orders-db r2   # by name, or by server; --delete-data drops its volume
```

With a load balancer the functions keep working at once. Without one, the env file is updated: redeploy the
functions so they read the new `_READ_URLS`.

## Monitor a replicated database and alert on lag

pskit measures every container of a database: CPU, memory, how full the data disk is, open connections, data size,
and each replica's lag.

**In studio**: in the database's **Details**, the **Live monitoring** switch polls every 5 seconds. Under **Alert me
(optional): CPU, memory, disk, replica lag, a container down** set **Run a function**, **Webhook**, **CPU %**,
**Memory %**, **Disk %**, **Replica lag (s)**, **Cooldown (min)** and **Also when a container is down**.

**From the terminal**

```bash
pskit resources onprem monitor orders-db --watch 5
pskit resources onprem alerts orders-db --on --webhook https://hooks.slack.com/services/XXX --lag 60
pskit resources onprem alerts orders-db --test
pskit resources onprem alerts orders-db --check     # from cron: measure now and alert when over a limit
```

Defaults: CPU 90 %, memory 90 %, disk 85 %, lag 60 s, cooldown 30 minutes.

## Scale a single-server on-prem database

A single-server on-prem database scales **up**: give its server more CPU and memory. On a scaling cluster, a
non-database service can run on one server of the cluster (`--cluster prod`, or **Where → Scaling cluster**), but
it is one container, not replicated; the studio does not offer **Scaling cluster** for databases, which scale with
replicas instead.

## See also

* [Scaling options compared](scaling/README.md)
* [On-prem services](services/README.md), [On-prem resources](resources.md)
* [Firewall rules for replicated databases](firewall.md#firewall-rules-for-on-prem-services-and-replicated-databases)
* [Load balancers](load-balancers.md)
