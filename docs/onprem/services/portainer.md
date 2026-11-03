# Portainer (Docker UI)

Search terms: Portainer, Docker UI, containers, images, volumes, 9000, 9443

Portainer manages the server's Docker containers, images, volumes and networks in the browser. pskit mounts the Docker
socket into it. Create the admin account **within 5 minutes** of the first start (otherwise restart it).

## Portainer at a glance

The Portainer service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `portainer` |
| Studio card | **Automation, web & tools** > **Portainer (Docker UI)** |
| Docker image | `portainer/portainer-ce:2.21.4` |
| Port | `9000` (also `9443`). Extra ports move with the main port |
| Use as | `custom` (Service, resource type `custom`) |
| Login | the service's own admin account, created on the first visit (leave User and Password empty) |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | Portainer on port `9000` at `/` (create the admin account on the first visit) |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Portainer in studio

The studio creates Portainer from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Automation, web & tools**, click the **Portainer (Docker UI)** card. The
   drawer title changes to *Create Portainer (Docker UI)*.
4. **Resource key**: type `portainer` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `9000`, or type another one if that port is taken.
7. **Security**: leave **User** and **Password** empty (the service asks you to create its admin account on the first
   visit; pskit refuses a user or password here). Choose **Listen on**.
8. **Web UI**: built in (Portainer); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Portainer from the terminal

`pskit resources onprem create KEY --service portainer` starts Portainer and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create portainer --service portainer --save                 # here, or the deploy target
pskit resources onprem create portainer --service portainer --server edge1 --save   # a saved server
pskit resources onprem create portainer --service portainer --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Portainer

Creating Portainer adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  portainer:
    type: custom
    external: true
    connection:
      url: http://10.0.0.5:9000
```

```text
# .env.onprem
PSKIT_PORTAINER_URL=http://10.0.0.5:9000
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Portainer from a handler

A handler reaches Portainer through `resource("portainer")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import urllib.request

from py_serverless_kit import resource


def ping(event, ctx):
    r = resource("portainer")
    url = r["url"]                                       # http://<address>:<port>
    with urllib.request.urlopen(url, timeout=5) as resp:
        return {"url": url, "status": resp.status}
```

`pskit resources usage portainer` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage portainer` shows how to connect from any
other program.

## Open the Portainer web UI, console and terminal

The Portainer row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Portainer on port `9000` at `/` (create the
  admin account on the first visit). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status portainer --reveal      # state, health, endpoint, credentials
pskit resources onprem usage portainer                # connect from any program
pskit resources onprem logs portainer -n 100
pskit resources onprem gui portainer                  # print the web UI links (starts a companion)
pskit resources onprem gui portainer --check
pskit resources onprem terminal portainer
pskit resources onprem tunnel portainer                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Portainer

Portainer has no backup command in pskit; copy its data volume yourself if you need one.

To remove Portainer: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the
Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and
data*.

```bash
pskit resources onprem remove portainer --save                 # keep the data volume
pskit resources onprem remove portainer --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
