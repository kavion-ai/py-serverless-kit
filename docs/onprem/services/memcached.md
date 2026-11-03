# Memcached

Search terms: Memcached, cache, in-memory cache, 11211, pymemcache, memjs

Memcached is an in-memory cache. pskit adds a `cache` resource with its host and port. It has no authentication in
this setup and nothing to back up.

## Memcached at a glance

The Memcached service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `memcached` |
| Studio card | **Redis-compatible (cache, queue, stream)** > **Memcached** |
| Docker image | `memcached:1.6-alpine` |
| Port | `11211` |
| Use as | `cache` (Cache, resource type `cache`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | not persisted (a restart empties it) |
| Backup | no |
| Web UI | none |
| Console | memcached text protocol |

## Create Memcached in studio

The studio creates Memcached from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Redis-compatible (cache, queue, stream)**, click the **Memcached** card.
   The drawer title changes to *Create Memcached*.
4. **Resource key**: type `cache` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `11211`, or type another one if that port is taken.
7. **Security**: Memcached runs without authentication; choose **Listen on**: *This machine only (127.0.0.1)* or
   *Network (0.0.0.0)* and limit the port with the firewall.
8. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
9. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
   is pulled, the container started and checked). The button turns into *Created*.
10. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Memcached from the terminal

`pskit resources onprem create KEY --service memcached` starts Memcached and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create cache --service memcached --save                 # here, or the deploy target
pskit resources onprem create cache --service memcached --server edge1 --save   # a saved server
pskit resources onprem create cache --service memcached --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Memcached

Creating Memcached adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  cache:
    type: cache
    external: true
    connection:
      host: 10.0.0.5
      port: 11211
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Memcached from a handler

A handler reaches Memcached through `resource("cache")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
from pymemcache.client.base import Client

from py_serverless_kit import resource


def cached(event, ctx):
    r = resource("cache")
    client = Client((r["host"], int(r["port"])))
    client.set("greeting", "hello", expire=60)
    return {"value": client.get("greeting").decode()}
```

Add `pymemcache` to `requirements.txt`.

`pskit resources usage cache` (studio: **How to use** on the resource row) prints the same code for Python and Node.js
with the libraries to install, and `pskit resources onprem usage cache` shows how to connect from any other program.

## Open the Memcached web UI, console and terminal

The Memcached row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, health, endpoint, credentials (**Show values**) and **Show logs**.
- **Console** runs one command at a time with **memcached text protocol** and the service's credentials, for example
  `stats`, `stats items`, `version`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status cache --reveal      # state, health, endpoint, credentials
pskit resources onprem usage cache                # connect from any program
pskit resources onprem logs cache -n 100
pskit resources onprem console cache "stats"
pskit resources onprem terminal cache
pskit resources onprem tunnel cache                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Memcached

Memcached has no backup command in pskit (it keeps data in memory only).

To remove Memcached: **Remove** on the row, then **Remove, keep data**. The container is deleted, its variables leave
the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources table, **Delete**
on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove cache --save                 # keep the data volume
pskit resources onprem remove cache --delete-data --save   # delete it too
```

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Existing cache guide](../../resource-guides/onprem/cache.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
