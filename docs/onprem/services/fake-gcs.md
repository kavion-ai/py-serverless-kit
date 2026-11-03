# fake-gcs-server (Cloud Storage emulator)

Search terms: fake-gcs-server, Google Cloud Storage emulator, GCS, gcs driver, emulator, 4443, bucket

fake-gcs-server emulates the Google Cloud Storage JSON API. pskit adds a `storage` resource on the `gcs` driver in
emulator mode. It has **no authentication**: use it for development and tests.

## fake-gcs-server at a glance

The fake-gcs-server service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `fake-gcs` |
| Studio card | **Object storage** > **fake-gcs-server (Cloud Storage emulator)** |
| Docker image | `fsouza/fake-gcs-server:1.52` |
| Port | `4443` |
| Use as | `storage` (Bucket, resource type `storage`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | none |
| Console | Cloud Storage JSON API (GET path) |

## Create fake-gcs-server in studio

The studio creates fake-gcs-server from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Object storage**, click the **fake-gcs-server (Cloud Storage emulator)**
   card. The drawer title changes to *Create fake-gcs-server (Cloud Storage emulator)*.
4. **Resource key**: type `files` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `4443`, or type another one if that port is taken.
7. **Security**: fake-gcs-server runs without authentication; choose **Listen on**: *This machine only (127.0.0.1)* or
   *Network (0.0.0.0)* and limit the port with the firewall.
8. **Trigger functions**: tick the functions that run for each message / object. Each gets an event on `resource:
   files`.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource and the triggers are added to the draft. Click **Save** in the top bar to write `pskit.yml`, then
    deploy.

## Create fake-gcs-server from the terminal

`pskit resources onprem create KEY --service fake-gcs` starts fake-gcs-server and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create files --service fake-gcs --attach worker --save                 # here, or the deploy target
pskit resources onprem create files --service fake-gcs --server edge1 --attach worker --save   # a saved server
pskit resources onprem create files --service fake-gcs --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `-a / --attach FUNCTION` (repeatable) adds the trigger to that function.
- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for fake-gcs-server

Creating fake-gcs-server adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem
env file (`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address
`10.0.0.5` and the defaults.

```yaml
resources:
  files:
    type: storage
    external: true
    options:
      driver: gcs
      endpoint: http://10.0.0.5:4443
      emulator: true
      bucket: files
      project: pskit
      create_bucket: true
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use fake-gcs-server from a handler

A handler reaches fake-gcs-server through `resource("files")`, which returns the connection values pskit passes to
bound functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

As a bucket, functions with `storage: {resource: files}` run for each new or deleted object, and `put_object` writes
through the on-prem host:

```python
from py_serverless_kit import resource
from py_serverless_kit.runtime.onprem_host import put_object


def upload(event, ctx):
    """HTTP trigger: write one object into the files bucket."""
    put_object(resource("files").native_name, "in/hello.txt", b"hello")
    return {"written": "in/hello.txt"}


def on_file(event, ctx):
    """Trigger: storage: {resource: files}."""
    for record in event.records:
        ctx.logger.info("object", extra={"bucket": record.bucket, "key": record.key,
                                          "action": record.action, "size": record.size})
```

```yaml
functions:
  upload:
    handler: app.handlers.upload
    events:
      - http: POST /upload
  on-file:
    handler: app.handlers.on_file
    events:
      - storage: {resource: files}
```

`pskit resources usage files` (studio: **How to use** on the resource row) prints the same code for Python and Node.js
with the libraries to install, and `pskit resources onprem usage files` shows how to connect from any other program.

## Open the fake-gcs-server web UI, console and terminal

The fake-gcs-server row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, health, endpoint, credentials (**Show values**) and **Show logs**.
- **Browse** opens pskit's own browser (buckets over Cloud Storage).
- **Console** runs one command at a time with **Cloud Storage JSON API (GET path)** and the service's credentials, for
  example `/storage/v1/b`, `/storage/v1/b/files/o`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status files --reveal      # state, health, endpoint, credentials
pskit resources onprem usage files                # connect from any program
pskit resources onprem logs files -n 100
pskit resources onprem console files "/storage/v1/b"
pskit resources onprem terminal files
pskit resources onprem tunnel files                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove fake-gcs-server

fake-gcs-server has no backup command in pskit; copy its data volume yourself if you need one.

To remove fake-gcs-server: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the
Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and
data*.

```bash
pskit resources onprem remove files --save                 # keep the data volume
pskit resources onprem remove files --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Storage trigger](../../triggers/storage.md)
- [Existing storage guide](../../resource-guides/onprem/storage.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
