# Neo4j (graph database)

Search terms: Neo4j, graph database, Cypher, Bolt, 7687, 7474, Neo4j Browser

Neo4j is a graph database queried with Cypher over Bolt (the main port). Neo4j Browser runs on 7474. The user is
**always `neo4j`**: leave the user empty.

## Neo4j at a glance

The Neo4j service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `neo4j` |
| Studio card | **Databases** > **Neo4j (graph database)** |
| Docker image | `neo4j:5` |
| Port | `7687` (also `7474`). Extra ports move with the main port |
| Use as | `database` (Database, resource type `database`) |
| Login | user `neo4j` (fixed) and a password |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | Neo4j Browser on port `7474` at `/` (the service's user and password) |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Neo4j in studio

The studio creates Neo4j from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Databases**, click the **Neo4j (graph database)** card. The drawer title
   changes to *Create Neo4j (graph database)*.
4. **Resource key**: type `graph-db` (the form suggests a free name). Handlers and triggers use this key.
5. **Scaling**: Neo4j runs on one server here (**Single server**).
6. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*).
7. **Port**: leave empty for `7687`, or type another one if that port is taken.
8. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*. Leave **User** empty: Neo4j's user is always
   `neo4j`.
9. **Alerts** (optional): send CPU, memory, disk, lag or down alerts to a webhook or a function (see [replicas and
   alerts](../scaling/replicas-and-alerts.md)).
10. **Web UI**: built in (Neo4j Browser); *How to use* shows its address and login.
11. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
12. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
13. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Neo4j from the terminal

`pskit resources onprem create KEY --service neo4j` starts Neo4j and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create graph-db --service neo4j --save                 # here, or the deploy target
pskit resources onprem create graph-db --service neo4j --server edge1 --save   # a saved server
pskit resources onprem create graph-db --service neo4j --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export GRAPH_DB_PASSWORD='Str0ng.pass-1'
pskit resources onprem create graph-db --service neo4j --password-env GRAPH_DB_PASSWORD --bind 127.0.0.1 --local --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Neo4j

Creating Neo4j adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  graph-db:
    type: database
    external: true
    connection:
      url: bolt://10.0.0.5:7687
      user: neo4j
      password_env: PSKIT_GRAPH_DB_PASSWORD
```

```text
# .env.onprem
PSKIT_GRAPH_DB_URL=bolt://10.0.0.5:7687
PSKIT_GRAPH_DB_USER=neo4j
PSKIT_GRAPH_DB_PASSWORD=<password>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Neo4j from a handler

A handler reaches Neo4j through `resource("graph-db")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
from neo4j import GraphDatabase

from py_serverless_kit import resource


def count_nodes(event, ctx):
    r = resource("graph-db")
    auth = (r["user"], ctx.env[r["password_env"]])         # neo4j / PSKIT_GRAPH_DB_PASSWORD
    with GraphDatabase.driver(r["url"], auth=auth) as driver:
        records, _summary, _keys = driver.execute_query("MATCH (n) RETURN count(n) AS n")
        return {"nodes": records[0]["n"]}
```

Add `neo4j` to `requirements.txt`.

`pskit resources usage graph-db` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage graph-db` shows how to connect from any other
program.

## Open the Neo4j web UI, console and terminal

The Neo4j row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Neo4j Browser on port `7474` at `/` (the
  service's user and password). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status graph-db --reveal      # state, health, endpoint, credentials
pskit resources onprem usage graph-db                # connect from any program
pskit resources onprem logs graph-db -n 100
pskit resources onprem gui graph-db                  # print the web UI links (starts a companion)
pskit resources onprem gui graph-db --check
pskit resources onprem terminal graph-db
pskit resources onprem tunnel graph-db                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Neo4j

Neo4j has no backup command in pskit; copy its data volume yourself if you need one.

To remove Neo4j: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted,
its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources
table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove graph-db --save                 # keep the data volume
pskit resources onprem remove graph-db --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Database scaling](../database-scaling.md)
- [Existing database guide](../../resource-guides/onprem/database.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
