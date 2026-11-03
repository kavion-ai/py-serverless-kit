# MongoDB

Search terms: MongoDB, Mongo, document database, mongosh, mongodump, Mongo Express, 27017, pymongo

MongoDB is a document database. pskit creates the root user (any name except `admin`), writes a connection URL with
`authSource=admin` to the env file, and adds a `database` resource.

## MongoDB at a glance

The MongoDB service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `mongodb` |
| Studio card | **Databases** > **MongoDB** |
| Docker image | `mongo:7` |
| Port | `27017` |
| Use as | `database` (Database, resource type `database`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/data/db` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.archive`) |
| Web UI | companion **Mongo Express** (default port `8081`; login: the MongoDB user and password) |
| Console | mongosh |
| Import a dump | `.archive`, `.archive.gz`, `.gz` |
| Replication | Replica set — see [database scaling](../database-scaling.md) |

## Create MongoDB in studio

The studio creates MongoDB from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Databases**, click the **MongoDB** card. The drawer title changes to
   *Create MongoDB*.
4. **Resource key**: type `orders-db` (the form suggests a free name). Handlers and triggers use this key.
5. **Scaling**: keep **Single server**, or pick **Primary + read replicas** (see [database
   scaling](../database-scaling.md)).
6. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*).
7. **Port**: leave empty for `27017`, or type another one if that port is taken.
8. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*. Do not use `admin` as the user.
9. **Import data** (optional): pick a dump on this machine (.archive, .archive.gz, .gz) to load once the database is
   up.
10. **Alerts** (optional): send CPU, memory, disk, lag or down alerts to a webhook or a function (see [replicas and
    alerts](../scaling/replicas-and-alerts.md)).
11. **Web UI**: keep **Also start Mongo Express** on to get its web UI; **Web UI login** *With password* (empty **Web
    UI password** = generated) or *Without password* (only on 127.0.0.1, a private network or a tunnel).
12. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
13. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
14. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create MongoDB from the terminal

`pskit resources onprem create KEY --service mongodb` starts MongoDB and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create orders-db --service mongodb --save                 # here, or the deploy target
pskit resources onprem create orders-db --service mongodb --server edge1 --save   # a saved server
pskit resources onprem create orders-db --service mongodb --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export ORDERS_DB_PASSWORD='Str0ng.pass-1'
pskit resources onprem create orders-db --service mongodb --user app --password-env ORDERS_DB_PASSWORD --bind 127.0.0.1 --local --save
pskit resources onprem create orders-db --service mongodb --gui --save    # also start Mongo Express
pskit resources onprem create orders-db --service mongodb --server db1 --import ./backups/orders-db.archive --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for MongoDB

Creating MongoDB adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  orders-db:
    type: database
    external: true
    connection:
      host: 10.0.0.5
      port: 27017
      user: pskit
      password_env: PSKIT_ORDERS_DB_PASSWORD
      url_env: PSKIT_ORDERS_DB_URL
```

```text
# .env.onprem
PSKIT_ORDERS_DB_URL=mongodb://pskit:<password>@10.0.0.5:27017/?authSource=admin
PSKIT_ORDERS_DB_PASSWORD=<password>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use MongoDB from a handler

A handler reaches MongoDB through `resource("orders-db")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
from pymongo import MongoClient

from py_serverless_kit import resource


def add_note(event, ctx):
    r = resource("orders-db")
    client = MongoClient(ctx.env[r["url_env"]])           # PSKIT_ORDERS_DB_URL (authSource=admin)
    try:
        notes = client["app"]["notes"]
        notes.insert_one({"body": "hello"})
        return {"count": notes.count_documents({})}
    finally:
        client.close()
```

Add `pymongo` to `requirements.txt`.

`pskit resources usage orders-db` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage orders-db` shows how to connect from any
other program.

## Open the MongoDB web UI, console and terminal

The MongoDB row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: companion **Mongo Express** (default port
  `8081`; login: the MongoDB user and password). **Check web UI** finds out why a UI does not open (container, port,
  firewall).
- **Console** runs one command at a time with **mongosh** and the service's credentials, for example
  `db.getCollectionNames()`, `db.stats()`, `db.notes.insertOne({body: 'hi'})`. Switch to *Shell in the container* for
  `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): the service's client.

```bash
pskit resources onprem status orders-db --reveal      # state, health, endpoint, credentials
pskit resources onprem usage orders-db                # connect from any program
pskit resources onprem logs orders-db -n 100
pskit resources onprem gui orders-db                  # print the web UI links (starts a companion)
pskit resources onprem gui orders-db --check
pskit resources onprem console orders-db "db.getCollectionNames()"
pskit resources onprem terminal orders-db
pskit resources onprem tunnel orders-db                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove MongoDB

MongoDB backups stream a dump out of the container into `.pskit/backups/orders-db-<time>.archive` on this machine
(also from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up
now**.

```bash
pskit resources onprem backup orders-db
pskit resources onprem backup orders-db --dir ~/backups
```

To remove MongoDB: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted,
its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources
table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove orders-db --save                 # keep the data volume
pskit resources onprem remove orders-db --delete-data --save   # delete it too
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
