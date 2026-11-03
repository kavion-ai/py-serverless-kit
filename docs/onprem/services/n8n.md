# n8n (workflow automation)

Search terms: n8n, workflow automation, integrations, HTTP node, no-code, 5678

n8n is visual workflow automation with hundreds of integrations. Its HTTP node can call your pskit functions. You
create the owner account on the first visit.

## n8n at a glance

The n8n service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `n8n` |
| Studio card | **Automation, web & tools** > **n8n (workflow automation)** |
| Docker image | `n8nio/n8n:latest` |
| Port | `5678` |
| Use as | `custom` (Service, resource type `custom`) |
| Login | the service's own admin account, created on the first visit (leave User and Password empty) |
| Data | kept in `/home/node/.n8n` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | n8n on port `5678` at `/` (create the admin account on the first visit) |
| Console | no client: use *Shell in the container* (`sh`) |

## Create n8n in studio

The studio creates n8n from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Automation, web & tools**, click the **n8n (workflow automation)** card.
   The drawer title changes to *Create n8n (workflow automation)*.
4. **Resource key**: type `automation` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `5678`, or type another one if that port is taken.
7. **Security**: leave **User** and **Password** empty (the service asks you to create its admin account on the first
   visit; pskit refuses a user or password here). Choose **Listen on**.
8. **Web UI**: built in (n8n); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create n8n from the terminal

`pskit resources onprem create KEY --service n8n` starts n8n and prints the `pskit.yml` entry; add `--save` to write
it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local` it goes
where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create automation --service n8n --save                 # here, or the deploy target
pskit resources onprem create automation --service n8n --server edge1 --save   # a saved server
pskit resources onprem create automation --service n8n --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for n8n

Creating n8n adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  automation:
    type: custom
    external: true
    connection:
      url: http://10.0.0.5:5678
```

```text
# .env.onprem
PSKIT_AUTOMATION_URL=http://10.0.0.5:5678
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use n8n from a handler

A handler reaches n8n through `resource("automation")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import urllib.request

from py_serverless_kit import resource


def ping(event, ctx):
    r = resource("automation")
    url = r["url"]                                       # http://<address>:<port>
    with urllib.request.urlopen(url, timeout=5) as resp:
        return {"url": url, "status": resp.status}
```

`pskit resources usage automation` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage automation` shows how to connect from any
other program.

## Open the n8n web UI, console and terminal

The n8n row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: n8n on port `5678` at `/` (create the admin
  account on the first visit). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status automation --reveal      # state, health, endpoint, credentials
pskit resources onprem usage automation                # connect from any program
pskit resources onprem logs automation -n 100
pskit resources onprem gui automation                  # print the web UI links (starts a companion)
pskit resources onprem gui automation --check
pskit resources onprem terminal automation
pskit resources onprem tunnel automation                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove n8n

n8n backups stream a dump out of the container into `.pskit/backups/automation-<time>.tar.gz` on this machine (also
from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up now**.

```bash
pskit resources onprem backup automation
pskit resources onprem backup automation --dir ~/backups
```

To remove n8n: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted, its
variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources
table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove automation --save                 # keep the data volume
pskit resources onprem remove automation --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
