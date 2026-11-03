# Typesense (search engine)

Search terms: Typesense, search engine, full-text search, API key, 8108

Typesense is a fast typo-tolerant search engine with a REST API. The password is the **API key**. It has no web UI.

## Typesense at a glance

The Typesense service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `typesense` |
| Studio card | **Identity & search** > **Typesense (search engine)** |
| Docker image | `typesense/typesense:27.1` |
| Port | `8108` |
| Use as | `custom` (Service, resource type `custom`) |
| Login | an API key: the service password (generated when empty), in `PSKIT_<KEY>_API_KEY` |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | none |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Typesense in studio

The studio creates Typesense from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Identity & search**, click the **Typesense (search engine)** card. The
   drawer title changes to *Create Typesense (search engine)*.
4. **Resource key**: type `search` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `8108`, or type another one if that port is taken.
7. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
8. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
9. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
   is pulled, the container started and checked). The button turns into *Created*.
10. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Typesense from the terminal

`pskit resources onprem create KEY --service typesense` starts Typesense and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create search --service typesense --save                 # here, or the deploy target
pskit resources onprem create search --service typesense --server edge1 --save   # a saved server
pskit resources onprem create search --service typesense --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export SEARCH_PASSWORD='Str0ng.pass-1'
pskit resources onprem create search --service typesense --user app --password-env SEARCH_PASSWORD --bind 127.0.0.1 --local --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Typesense

Creating Typesense adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  search:
    type: custom
    external: true
    connection:
      url: http://10.0.0.5:8108
      api_key_env: PSKIT_SEARCH_API_KEY
```

```text
# .env.onprem
PSKIT_SEARCH_URL=http://10.0.0.5:8108
PSKIT_SEARCH_API_KEY=<password>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Typesense from a handler

A handler reaches Typesense through `resource("search")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import urllib.request

from py_serverless_kit import resource


def health(event, ctx):
    r = resource("search")
    api_key = ctx.env[r["api_key_env"]]                  # PSKIT_SEARCH_API_KEY
    req = urllib.request.Request(r["url"] + "/health", headers={"X-TYPESENSE-API-KEY": api_key})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return {"status": resp.status, "body": resp.read().decode("utf-8", "replace")}
```

`pskit resources usage search` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage search` shows how to connect from any other
program.

## Open the Typesense web UI, console and terminal

The Typesense row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, health, endpoint, credentials (**Show values**) and **Show logs**.
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status search --reveal      # state, health, endpoint, credentials
pskit resources onprem usage search                # connect from any program
pskit resources onprem logs search -n 100
pskit resources onprem terminal search
pskit resources onprem tunnel search                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Typesense

Typesense has no backup command in pskit; copy its data volume yourself if you need one.

To remove Typesense: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the
Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and
data*.

```bash
pskit resources onprem remove search --save                 # keep the data volume
pskit resources onprem remove search --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
