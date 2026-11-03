# Grafana (dashboards)

Search terms: Grafana, dashboards, monitoring, alerts, data sources, Prometheus, 3000

Grafana shows dashboards and alerts over Prometheus, Loki, PostgreSQL, ClickHouse and many other data sources. pskit
sets the admin user and password and adds a `custom` resource with the URL.

## Grafana at a glance

The Grafana service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `grafana` |
| Studio card | **Monitoring & tracing** > **Grafana (dashboards)** |
| Docker image | `grafana/grafana:11.3.0` |
| Port | `3000` |
| Use as | `custom` (Service, resource type `custom`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/var/lib/grafana` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | Grafana on port `3000` at `/` (the service's user and password) |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Grafana in studio

The studio creates Grafana from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Monitoring & tracing**, click the **Grafana (dashboards)** card. The
   drawer title changes to *Create Grafana (dashboards)*.
4. **Resource key**: type `dashboards` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `3000`, or type another one if that port is taken.
7. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
8. **Web UI**: built in (Grafana); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Grafana from the terminal

`pskit resources onprem create KEY --service grafana` starts Grafana and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create dashboards --service grafana --save                 # here, or the deploy target
pskit resources onprem create dashboards --service grafana --server edge1 --save   # a saved server
pskit resources onprem create dashboards --service grafana --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export DASHBOARDS_PASSWORD='Str0ng.pass-1'
pskit resources onprem create dashboards --service grafana --user app --password-env DASHBOARDS_PASSWORD --bind 127.0.0.1 --local --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Grafana

Creating Grafana adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  dashboards:
    type: custom
    external: true
    connection:
      url: http://10.0.0.5:3000
      user: pskit
      password_env: PSKIT_DASHBOARDS_PASSWORD
```

```text
# .env.onprem
PSKIT_DASHBOARDS_URL=http://10.0.0.5:3000
PSKIT_DASHBOARDS_USER=pskit
PSKIT_DASHBOARDS_PASSWORD=<password>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Grafana from a handler

A handler reaches Grafana through `resource("dashboards")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import urllib.request

from py_serverless_kit import resource


def ping(event, ctx):
    r = resource("dashboards")
    url = r["url"]                                       # http://<address>:<port>
    with urllib.request.urlopen(url, timeout=5) as resp:
        return {"url": url, "status": resp.status}
```

Other connection values: `user`, `password_env`.

`pskit resources usage dashboards` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage dashboards` shows how to connect from any
other program.

## Open the Grafana web UI, console and terminal

The Grafana row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Grafana on port `3000` at `/` (the service's
  user and password). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status dashboards --reveal      # state, health, endpoint, credentials
pskit resources onprem usage dashboards                # connect from any program
pskit resources onprem logs dashboards -n 100
pskit resources onprem gui dashboards                  # print the web UI links (starts a companion)
pskit resources onprem gui dashboards --check
pskit resources onprem terminal dashboards
pskit resources onprem tunnel dashboards                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Grafana

Grafana backups stream a dump out of the container into `.pskit/backups/dashboards-<time>.tar.gz` on this machine
(also from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up
now**.

```bash
pskit resources onprem backup dashboards
pskit resources onprem backup dashboards --dir ~/backups
```

To remove Grafana: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted,
its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources
table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove dashboards --save                 # keep the data volume
pskit resources onprem remove dashboards --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
