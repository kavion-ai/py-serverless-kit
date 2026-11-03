# RustFS (S3-compatible)

Search terms: RustFS, S3 compatible, object storage, MinIO alternative, bucket, console 9001, s3 driver

RustFS is an S3-compatible object store with a web console (port 9001), an alternative to MinIO. pskit adds a
`storage` resource on the `s3` driver with the endpoint and keys; boto3 and the AWS CLI work with its endpoint.

## RustFS at a glance

The RustFS service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `rustfs` |
| Studio card | **Object storage** > **RustFS (S3-compatible)** |
| Docker image | `rustfs/rustfs:latest` |
| Port | `9000` (also `9001`). Extra ports move with the main port |
| Use as | `storage` (Bucket, resource type `storage`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | Console on port `9001` at `/` (the service's user and password) |
| Console | aws s3 (helper) |

## Create RustFS in studio

The studio creates RustFS from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Object storage**, click the **RustFS (S3-compatible)** card. The drawer
   title changes to *Create RustFS (S3-compatible)*.
4. **Resource key**: type `files` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `9000`, or type another one if that port is taken.
7. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
8. **Web UI**: built in (Console); *How to use* shows its address and login.
9. **Trigger functions**: tick the functions that run for each message / object. Each gets an event on `resource:
   files`.
10. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
11. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
12. The resource and the triggers are added to the draft. Click **Save** in the top bar to write `pskit.yml`, then
    deploy.

## Create RustFS from the terminal

`pskit resources onprem create KEY --service rustfs` starts RustFS and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create files --service rustfs --attach worker --save                 # here, or the deploy target
pskit resources onprem create files --service rustfs --server edge1 --attach worker --save   # a saved server
pskit resources onprem create files --service rustfs --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export FILES_PASSWORD='Str0ng.pass-1'
pskit resources onprem create files --service rustfs --user app --password-env FILES_PASSWORD --bind 127.0.0.1 --local --save
```

- `-a / --attach FUNCTION` (repeatable) adds the trigger to that function.
- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for RustFS

Creating RustFS adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  files:
    type: storage
    external: true
    options:
      driver: s3
      endpoint: http://10.0.0.5:9000
      bucket: files
      access_key_env: PSKIT_FILES_ACCESS_KEY
      secret_key_env: PSKIT_FILES_SECRET_KEY
      path_style: true
      create_bucket: true
    connection:
      console_url: http://10.0.0.5:9001
```

```text
# .env.onprem
PSKIT_FILES_ACCESS_KEY=pskit
PSKIT_FILES_SECRET_KEY=<password>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use RustFS from a handler

A handler reaches RustFS through `resource("files")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

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

## Open the RustFS web UI, console and terminal

The RustFS row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Console on port `9001` at `/` (the service's
  user and password). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Browse** opens pskit's own browser (buckets and objects over S3).
- **Console** runs one command at a time with **aws s3 (helper)** and the service's credentials, for example `s3 ls`,
  `s3 ls s3://files`, `s3api list-buckets`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status files --reveal      # state, health, endpoint, credentials
pskit resources onprem usage files                # connect from any program
pskit resources onprem logs files -n 100
pskit resources onprem gui files                  # print the web UI links (starts a companion)
pskit resources onprem gui files --check
pskit resources onprem console files "s3 ls"
pskit resources onprem terminal files
pskit resources onprem tunnel files                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove RustFS

RustFS has no backup command in pskit; copy its data volume yourself if you need one.

To remove RustFS: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted,
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
- [Storage trigger](../../triggers/storage.md)
- [Existing storage guide](../../resource-guides/onprem/storage.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
