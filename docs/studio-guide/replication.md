# Database replication in studio

Search terms: replication, read replicas, primary replica, database scaling, PostgreSQL replication, MySQL replication, MongoDB replica set, synchronous, asynchronous, read write split, database load balancer, READ_URLS, add replica, remove replica

Database replication runs a primary (all writes) and read replicas (copies that answer reads) of a one-click on-prem
database, optionally behind a load balancer that splits reads and writes. In studio it is part of the
[Create a service](onprem-services.md#create-an-on-prem-service-in-studio) drawer and of the service's **Details**.
How replication works per engine is in [Database scaling](../onprem/database-scaling.md).

## Create a replicated database in studio

The **Scaling** field of the Create a service drawer turns replication on for databases that support it.

1. Open **Resources** → **On-prem services** → **+ Create service** and pick a database card (for example
   PostgreSQL).
2. Set **Use as** to **Database** if asked. Under **Scaling**, pick **Primary + read replicas** (instead of **Single
   server**). It is disabled when pskit has no replication for that engine.
3. The **Replication · <method>** box appears:

   | Field | What it sets |
   |---|---|
   | **Members run on** | **Saved servers** (one member per server; Docker is installed when missing) or **This machine (try it)** (every member on this machine, each on its own port, to try replication) |
   | **Primary (writes)** | The server that takes every INSERT / UPDATE / DELETE. Pick your strongest server |
   | **Read replicas** | Tick one server per replica (save at least two servers). On this machine: a number (1 to 9); replica 1 uses port + 1, and so on |
   | **Primary → replicas** | **Asynchronous (fastest)** or **Synchronous (no lost writes)** |
   | **Load balancer** | A server for the engine's load balancer, or **None: connect to the primary, reads via READ_URLS**. On this machine: **Start <balancer> here (one address for the functions)** |
   | **Load balancer port** | What the functions connect to (a default that lets it share a server with a member) |

4. Fill in the rest of the drawer (security, import data, alerts, trigger functions) and click **Create**.

Without a load balancer, the functions' URL is the primary and reads can use the replicas' addresses (`READ_URLS` in
the env file).

```bash
pskit resources onprem create orders-db --service postgres --primary db-1 --replica db-2 --replica db-3 \
  --balancer lb-1 --sync async --save
pskit resources onprem replicas list orders-db
```

## Add or remove a read replica in studio

The **Replication** panel in a replicated service's **Details** shows a diagram of the primary, the replicas and the
load balancer, and a table of each **Member** (role and server), **Address**, **State** and **Replication** (lag).

- **Add**: pick **Server for a new replica…** (only free saved servers) and click **+ Add read replica**. It copies the
  current data, then follows the primary; the load balancer starts sending it reads.
- **Remove** on a replica asks **Remove replica <name>?**: its container stops and the load balancer stops sending it
  reads. **Remove, keep data** keeps its data volume; **Delete data too** deletes it.

```bash
pskit resources onprem replicas add orders-db db-4
pskit resources onprem replicas remove orders-db r2
```

## See also

- [Database scaling](../onprem/database-scaling.md)
- [On-prem services panel](onprem-services.md)
- [Monitoring and alerts](monitoring.md) (replica lag alerts)
- [Servers panel](servers.md)
