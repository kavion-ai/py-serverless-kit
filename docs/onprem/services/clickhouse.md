# ClickHouse (analytics database)

Search terms: ClickHouse, analytics database, column store, OLAP, SQL playground, 8123, 9000

ClickHouse is a column-store SQL database for analytics and logs. HTTP runs on the main port (the SQL playground is at
`/play`); the native protocol is on 9000. pskit creates the user and a database named after the resource key.

## ClickHouse at a glance

The ClickHouse service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `clickhouse` |
| Studio card | **Databases** > **ClickHouse (analytics database)** |
| Docker image | `clickhouse/clickhouse-server:24.8` |
| Port | `8123` (also `9000`). Extra ports move with the main port |
| Use as | `database` (Database, resource type `database`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/var/lib/clickhouse` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | SQL playground on port `8123` at `/play` (the service's user and password) |
| Console | no client: use *Shell in the container* (`sh`) |

## Create ClickHouse in studio

The studio creates ClickHouse from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Databases**, click the **ClickHouse (analytics database)** card. The
   drawer title changes to *Create ClickHouse (analytics database)*.
4. **Resource key**: type `analytics-db` (the form suggests a free name). Handlers and triggers use this key.
5. **Scaling**: ClickHouse runs on one server here (**Single server**).
6. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*).
7. **Port**: leave empty for `8123`, or type another one if that port is taken.
8. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
9. **Alerts** (optional): send CPU, memory, disk, lag or down alerts to a webhook or a function (see [replicas and
   alerts](../scaling/replicas-and-alerts.md)).
10. **Web UI**: built in (SQL playground); *How to use* shows its address and login.
11. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
12. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
13. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create ClickHouse from the terminal

`pskit resources onprem create KEY --service clickhouse` starts ClickHouse and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create analytics-db --service clickhouse --save                 # here, or the deploy target
pskit resources onprem create analytics-db --service clickhouse --server edge1 --save   # a saved server
pskit resources onprem create analytics-db --service clickhouse --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export ANALYTICS_DB_PASSWORD='Str0ng.pass-1'
pskit resources onprem create analytics-db --service clickhouse --user app --password-env ANALYTICS_DB_PASSWORD --bind 127.0.0.1 --local --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for ClickHouse

Creating ClickHouse adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env
file (`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5`
and the defaults.

```yaml
resources:
  analytics-db:
    type: database
    external: true
    connection:
      host: 10.0.0.5
      port: 8123
      database: analytics_db
      user: pskit
      url_env: PSKIT_ANALYTICS_DB_URL
      password_env: PSKIT_ANALYTICS_DB_PASSWORD
```

```text
# .env.onprem
PSKIT_ANALYTICS_DB_URL=http://10.0.0.5:8123
PSKIT_ANALYTICS_DB_USER=pskit
PSKIT_ANALYTICS_DB_PASSWORD=<password>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use ClickHouse from a handler

A handler reaches ClickHouse through `resource("analytics-db")`, which returns the connection values pskit passes to
bound functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import urllib.parse
import urllib.request

from py_serverless_kit import resource


def count_rows(event, ctx):
    r = resource("analytics-db")
    query = urllib.parse.urlencode({"query": "SELECT version()", "database": r["database"]})
    req = urllib.request.Request(f"http://{r['host']}:{r['port']}/?{query}", headers={
        "X-ClickHouse-User": r["user"],
        "X-ClickHouse-Key": ctx.env[r["password_env"]],   # PSKIT_ANALYTICS_DB_PASSWORD
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return {"version": resp.read().decode().strip()}
```

`pskit resources usage analytics-db` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage analytics-db` shows how to connect from any
other program.

## Open the ClickHouse web UI, console and terminal

The ClickHouse row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: SQL playground on port `8123` at `/play` (the
  service's user and password). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status analytics-db --reveal      # state, health, endpoint, credentials
pskit resources onprem usage analytics-db                # connect from any program
pskit resources onprem logs analytics-db -n 100
pskit resources onprem gui analytics-db                  # print the web UI links (starts a companion)
pskit resources onprem gui analytics-db --check
pskit resources onprem terminal analytics-db
pskit resources onprem tunnel analytics-db                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove ClickHouse

ClickHouse has no backup command in pskit; copy its data volume yourself if you need one.

To remove ClickHouse: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the
Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and
data*.

```bash
pskit resources onprem remove analytics-db --save                 # keep the data volume
pskit resources onprem remove analytics-db --delete-data --save   # delete it too
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
