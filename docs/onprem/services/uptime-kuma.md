# Uptime Kuma (uptime monitor)

Search terms: Uptime Kuma, uptime monitor, status page, health checks, alerts, 3001

Uptime Kuma checks HTTP, TCP, DNS, Docker containers and more every minute and alerts by mail, Slack or Telegram. You
create the admin account on the first visit, so pskit sets no user or password.

## Uptime Kuma at a glance

The Uptime Kuma service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `uptime-kuma` |
| Studio card | **Monitoring & tracing** > **Uptime Kuma (uptime monitor)** |
| Docker image | `louislam/uptime-kuma:1` |
| Port | `3001` |
| Use as | `custom` (Service, resource type `custom`) |
| Login | the service's own admin account, created on the first visit (leave User and Password empty) |
| Data | kept in `/app/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | Uptime Kuma on port `3001` at `/` (create the admin account on the first visit) |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Uptime Kuma in studio

The studio creates Uptime Kuma from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Monitoring & tracing**, click the **Uptime Kuma (uptime monitor)** card.
   The drawer title changes to *Create Uptime Kuma (uptime monitor)*.
4. **Resource key**: type `uptime` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `3001`, or type another one if that port is taken.
7. **Security**: leave **User** and **Password** empty (the service asks you to create its admin account on the first
   visit; pskit refuses a user or password here). Choose **Listen on**.
8. **Web UI**: built in (Uptime Kuma); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Uptime Kuma from the terminal

`pskit resources onprem create KEY --service uptime-kuma` starts Uptime Kuma and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create uptime --service uptime-kuma --save                 # here, or the deploy target
pskit resources onprem create uptime --service uptime-kuma --server edge1 --save   # a saved server
pskit resources onprem create uptime --service uptime-kuma --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Uptime Kuma

Creating Uptime Kuma adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env
file (`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5`
and the defaults.

```yaml
resources:
  uptime:
    type: custom
    external: true
    connection:
      url: http://10.0.0.5:3001
```

```text
# .env.onprem
PSKIT_UPTIME_URL=http://10.0.0.5:3001
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Uptime Kuma from a handler

A handler reaches Uptime Kuma through `resource("uptime")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import urllib.request

from py_serverless_kit import resource


def ping(event, ctx):
    r = resource("uptime")
    url = r["url"]                                       # http://<address>:<port>
    with urllib.request.urlopen(url, timeout=5) as resp:
        return {"url": url, "status": resp.status}
```

`pskit resources usage uptime` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage uptime` shows how to connect from any other
program.

## Open the Uptime Kuma web UI, console and terminal

The Uptime Kuma row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Uptime Kuma on port `3001` at `/` (create the
  admin account on the first visit). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status uptime --reveal      # state, health, endpoint, credentials
pskit resources onprem usage uptime                # connect from any program
pskit resources onprem logs uptime -n 100
pskit resources onprem gui uptime                  # print the web UI links (starts a companion)
pskit resources onprem gui uptime --check
pskit resources onprem terminal uptime
pskit resources onprem tunnel uptime                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Uptime Kuma

Uptime Kuma backups stream a dump out of the container into `.pskit/backups/uptime-<time>.tar.gz` on this machine
(also from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up
now**.

```bash
pskit resources onprem backup uptime
pskit resources onprem backup uptime --dir ~/backups
```

To remove Uptime Kuma: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the
Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and
data*.

```bash
pskit resources onprem remove uptime --save                 # keep the data volume
pskit resources onprem remove uptime --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
