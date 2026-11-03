# Prometheus (metrics)

Search terms: Prometheus, metrics, time series, PromQL, scrape targets, 9090, monitoring

Prometheus is a metrics database with a query UI. It scrapes itself by default; add targets in
`/etc/prometheus/prometheus.yml` inside the container (Console, shell mode). It has **no login**: keep it on a private
network.

## Prometheus at a glance

The Prometheus service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `prometheus` |
| Studio card | **Monitoring & tracing** > **Prometheus (metrics)** |
| Docker image | `prom/prometheus:v2.55.1` |
| Port | `9090` |
| Use as | `custom` (Service, resource type `custom`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | kept in `/prometheus` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | Prometheus UI on port `9090` at `/` (no login) |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Prometheus in studio

The studio creates Prometheus from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Monitoring & tracing**, click the **Prometheus (metrics)** card. The
   drawer title changes to *Create Prometheus (metrics)*.
4. **Resource key**: type `metrics` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `9090`, or type another one if that port is taken.
7. **Security**: Prometheus runs without authentication; choose **Listen on**: *This machine only (127.0.0.1)* or
   *Network (0.0.0.0)* and limit the port with the firewall.
8. **Web UI**: built in (Prometheus UI); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Prometheus from the terminal

`pskit resources onprem create KEY --service prometheus` starts Prometheus and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create metrics --service prometheus --save                 # here, or the deploy target
pskit resources onprem create metrics --service prometheus --server edge1 --save   # a saved server
pskit resources onprem create metrics --service prometheus --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Prometheus

Creating Prometheus adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env
file (`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5`
and the defaults.

```yaml
resources:
  metrics:
    type: custom
    external: true
    connection:
      url: http://10.0.0.5:9090
```

```text
# .env.onprem
PSKIT_METRICS_URL=http://10.0.0.5:9090
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Prometheus from a handler

A handler reaches Prometheus through `resource("metrics")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import urllib.request

from py_serverless_kit import resource


def ping(event, ctx):
    r = resource("metrics")
    url = r["url"]                                       # http://<address>:<port>
    with urllib.request.urlopen(url, timeout=5) as resp:
        return {"url": url, "status": resp.status}
```

`pskit resources usage metrics` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage metrics` shows how to connect from any other
program.

## Open the Prometheus web UI, console and terminal

The Prometheus row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Prometheus UI on port `9090` at `/` (no
  login). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status metrics --reveal      # state, health, endpoint, credentials
pskit resources onprem usage metrics                # connect from any program
pskit resources onprem logs metrics -n 100
pskit resources onprem gui metrics                  # print the web UI links (starts a companion)
pskit resources onprem gui metrics --check
pskit resources onprem terminal metrics
pskit resources onprem tunnel metrics                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Prometheus

Prometheus has no backup command in pskit; copy its data volume yourself if you need one.

To remove Prometheus: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the
Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and
data*.

```bash
pskit resources onprem remove metrics --save                 # keep the data volume
pskit resources onprem remove metrics --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
