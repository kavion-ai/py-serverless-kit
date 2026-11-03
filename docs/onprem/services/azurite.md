# Azurite (Azure Blob + Queue emulator)

Search terms: Azurite, Azure Storage emulator, Azure Blob, Azure Queue, connection string, 10000, 10001, Azure Storage
Explorer

Azurite emulates Azure Storage blobs (port 10000) and queues (port 10001) with your own account name and key. Use it
as a **queue** (`azure_queue` driver) or a **bucket** (`azure_blob` driver); the Azure SDKs work unchanged with its
connection string. It has no web UI: browse it with Azure Storage Explorer.

## Azurite at a glance

The Azurite service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `azurite` |
| Studio card | **Object storage** > **Azurite (Azure Blob + Queue emulator)** |
| Docker image | `mcr.microsoft.com/azure-storage/azurite:3.33.0` |
| Port | `10000` (also `10001`). Extra ports move with the main port |
| Use as | `queue` (Queue, resource type `queue`), `storage` (Bucket, resource type `storage`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | none |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Azurite in studio

The studio creates Azurite from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Object storage**, click the **Azurite (Azure Blob + Queue emulator)**
   card. The drawer title changes to *Create Azurite (Azure Blob + Queue emulator)*.
4. **Resource key**: type `files` (the form suggests a free name). Handlers and triggers use this key.
5. **Use as**: pick **Queue** / **Bucket**.
6. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
7. **Port**: leave empty for `10000`, or type another one if that port is taken.
8. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*. The **User** is the Azure account name: 3-24
   lowercase letters and digits.
9. **Trigger functions**: tick the functions that run for each message / object. Each gets an event on `resource:
   files`.
10. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
11. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
12. The resource and the triggers are added to the draft. Click **Save** in the top bar to write `pskit.yml`, then
    deploy.

## Create Azurite from the terminal

`pskit resources onprem create KEY --service azurite` starts Azurite and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create files --service azurite --attach worker --save                 # here, or the deploy target
pskit resources onprem create files --service azurite --server edge1 --attach worker --save   # a saved server
pskit resources onprem create files --service azurite --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
pskit resources onprem create files --service azurite --role storage --save
export FILES_PASSWORD='Str0ng.pass-1'
pskit resources onprem create files --service azurite --user app --password-env FILES_PASSWORD --bind 127.0.0.1 --local --save
```

- `--role` picks `queue`, `storage` (default `queue`).
- `-a / --attach FUNCTION` (repeatable) adds the trigger to that function.
- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Azurite

Creating Azurite adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

Used as **Queue** (`--role queue`):

```yaml
resources:
  files:
    type: queue
    external: true
    options:
      driver: azure_queue
      connection_string_env: PSKIT_FILES_CONNECTION_STRING
      queue: files
      create_queue: true
    connection:
      account: pskit
      blob_endpoint: http://10.0.0.5:10000/pskit
      queue_endpoint: http://10.0.0.5:10001/pskit
```

```text
# .env.onprem
PSKIT_FILES_CONNECTION_STRING=DefaultEndpointsProtocol=http;AccountName=pskit;AccountKey=<base64 of the password>;BlobEndpoint=http://10.0.0.5:10000/pskit;QueueEndpoint=http://10.0.0.5:10001/pskit;
```

Used as **Bucket** (`--role storage`):

```yaml
resources:
  files:
    type: storage
    external: true
    options:
      driver: azure_blob
      connection_string_env: PSKIT_FILES_CONNECTION_STRING
      container: files
      create_bucket: true
    connection:
      account: pskit
      blob_endpoint: http://10.0.0.5:10000/pskit
      queue_endpoint: http://10.0.0.5:10001/pskit
```

```text
# .env.onprem
PSKIT_FILES_CONNECTION_STRING=DefaultEndpointsProtocol=http;AccountName=pskit;AccountKey=<base64 of the password>;BlobEndpoint=http://10.0.0.5:10000/pskit;QueueEndpoint=http://10.0.0.5:10001/pskit;
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Azurite from a handler

A handler reaches Azurite through `resource("files")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

As a queue, functions with `queue: {resource: files}` run for each batch of messages, and `submit_queue` publishes
through the on-prem host (so the resource's driver is used):

```python
from py_serverless_kit import BatchResult, resource
from py_serverless_kit.runtime.onprem_host import submit_queue


def send_job(event, ctx):
    """HTTP trigger: put the request body on the files queue."""
    payload = event.http.json() if event.http else event.data
    message_id = submit_queue(resource("files").native_name, payload)
    return {"id": message_id}


def on_job(event, ctx):
    """Trigger: queue: {resource: files}. A failed record is retried."""
    result = BatchResult()
    for record in event.records:
        try:
            ctx.logger.info("job", extra={"id": record.id, "body": record.json()})
        except Exception:
            result.fail(record)
    return result
```

```yaml
functions:
  send:
    handler: app.handlers.send_job
    events:
      - http: POST /jobs
  worker:
    handler: app.handlers.on_job
    events:
      - queue: {resource: files}
```

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

## Open the Azurite web UI, console and terminal

The Azurite row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, health, endpoint, credentials (**Show values**) and **Show logs**.
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status files --reveal      # state, health, endpoint, credentials
pskit resources onprem usage files                # connect from any program
pskit resources onprem logs files -n 100
pskit resources onprem terminal files
pskit resources onprem tunnel files                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Azurite

Azurite backups stream a dump out of the container into `.pskit/backups/files-<time>.tar.gz` on this machine (also
from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up now**.

```bash
pskit resources onprem backup files
pskit resources onprem backup files --dir ~/backups
```

To remove Azurite: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted,
its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources
table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

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
- [Queue trigger](../../triggers/queue.md)
- [Existing queue guide](../../resource-guides/onprem/queue.md)
- [Storage trigger](../../triggers/storage.md)
- [Existing storage guide](../../resource-guides/onprem/storage.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
