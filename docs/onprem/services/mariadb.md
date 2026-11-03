# MariaDB

Search terms: MariaDB, MySQL compatible, SQL database, mariadb-dump, Adminer, 3306, pymysql

MariaDB is a MySQL-compatible SQL database. pskit creates the user and a database named after the resource key, and
adds a `database` resource. MySQL client libraries work unchanged.

## MariaDB at a glance

The MariaDB service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `mariadb` |
| Studio card | **Databases** > **MariaDB** |
| Docker image | `mariadb:11` |
| Port | `3306` |
| Use as | `database` (Database, resource type `database`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/var/lib/mysql` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.sql`) |
| Web UI | companion **Adminer (database UI)** (default port `8089`; login: the database user and password (server is filled in)) |
| Console | mariadb |
| Import a dump | `.sql`, `.sql.gz` |
| Replication | GTID replication (binary log), load balancer ProxySQL (port 6033) — see [database scaling](../database-scaling.md) |

## Create MariaDB in studio

The studio creates MariaDB from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Databases**, click the **MariaDB** card. The drawer title changes to
   *Create MariaDB*.
4. **Resource key**: type `orders-db` (the form suggests a free name). Handlers and triggers use this key.
5. **Scaling**: keep **Single server**, or pick **Primary + read replicas** (see [database
   scaling](../database-scaling.md)).
6. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*).
7. **Port**: leave empty for `3306`, or type another one if that port is taken.
8. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
9. **Import data** (optional): pick a dump on this machine (.sql, .sql.gz) to load once the database is up.
10. **Alerts** (optional): send CPU, memory, disk, lag or down alerts to a webhook or a function (see [replicas and
    alerts](../scaling/replicas-and-alerts.md)).
11. **Web UI**: keep **Also start Adminer (database UI)** on to get its web UI.
12. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
13. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
14. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create MariaDB from the terminal

`pskit resources onprem create KEY --service mariadb` starts MariaDB and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create orders-db --service mariadb --save                 # here, or the deploy target
pskit resources onprem create orders-db --service mariadb --server edge1 --save   # a saved server
pskit resources onprem create orders-db --service mariadb --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export ORDERS_DB_PASSWORD='Str0ng.pass-1'
pskit resources onprem create orders-db --service mariadb --user app --password-env ORDERS_DB_PASSWORD --bind 127.0.0.1 --local --save
pskit resources onprem create orders-db --service mariadb --gui --save    # also start Adminer (database UI)
pskit resources onprem create orders-db --service mariadb --server db1 --import ./backups/orders-db.sql --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for MariaDB

Creating MariaDB adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  orders-db:
    type: database
    external: true
    connection:
      host: 10.0.0.5
      port: 3306
      database: orders_db
      user: pskit
      password_env: PSKIT_ORDERS_DB_PASSWORD
      url_env: PSKIT_ORDERS_DB_URL
```

```text
# .env.onprem
PSKIT_ORDERS_DB_URL=mysql://pskit:<password>@10.0.0.5:3306/orders_db
PSKIT_ORDERS_DB_PASSWORD=<password>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use MariaDB from a handler

A handler reaches MariaDB through `resource("orders-db")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import pymysql

from py_serverless_kit import resource


def db_version(event, ctx):
    r = resource("orders-db")
    conn = pymysql.connect(
        host=r["host"], port=int(r["port"]), user=r["user"], database=r["database"],
        password=ctx.env[r["password_env"]],               # PSKIT_ORDERS_DB_PASSWORD
    )
    with conn, conn.cursor() as cur:
        cur.execute("select version()")
        return {"version": cur.fetchone()[0]}
```

Add `pymysql` to `requirements.txt`.

`pskit resources usage orders-db` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage orders-db` shows how to connect from any
other program.

## Open the MariaDB web UI, console and terminal

The MariaDB row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: companion **Adminer (database UI)** (default
  port `8089`; login: the database user and password (server is filled in)). **Check web UI** finds out why a UI does
  not open (container, port, firewall).
- **Console** runs one command at a time with **mariadb** and the service's credentials, for example `SHOW TABLES;`,
  `SELECT VERSION();`, `SHOW DATABASES;`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): the service's client.

```bash
pskit resources onprem status orders-db --reveal      # state, health, endpoint, credentials
pskit resources onprem usage orders-db                # connect from any program
pskit resources onprem logs orders-db -n 100
pskit resources onprem gui orders-db                  # print the web UI links (starts a companion)
pskit resources onprem gui orders-db --check
pskit resources onprem console orders-db "SHOW TABLES;"
pskit resources onprem terminal orders-db
pskit resources onprem tunnel orders-db                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove MariaDB

MariaDB backups stream a dump out of the container into `.pskit/backups/orders-db-<time>.sql` on this machine (also
from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up now**.

```bash
pskit resources onprem backup orders-db
pskit resources onprem backup orders-db --dir ~/backups
```

To remove MariaDB: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted,
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
