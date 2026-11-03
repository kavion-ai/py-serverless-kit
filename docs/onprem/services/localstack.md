# LocalStack (SQS, S3, Secrets Manager)

Search terms: LocalStack, AWS emulator, SQS, S3, Secrets Manager, SSM, awslocal, 4566, test credentials

LocalStack emulates Amazon SQS, S3, Secrets Manager and SSM Parameter Store on one port (4566). Use it as a **queue**
(`sqs` driver), a **bucket** (`s3` driver) or a **secret manager** (`get_secret()`). Credentials are not checked
(`test` / `test`). It is for development and tests.

## LocalStack at a glance

The LocalStack service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `localstack` |
| Studio card | **AWS emulators** > **LocalStack (SQS, S3, Secrets Manager)** |
| Docker image | `localstack/localstack:3.8` |
| Port | `4566` |
| Use as | `queue` (Queue, resource type `queue`), `storage` (Bucket, resource type `storage`), `secrets` (Secret manager, resource type `custom`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | kept in `/var/lib/localstack` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | Status (JSON) on port `4566` at `/_localstack/health` (no login) |
| Console | awslocal |

## Create LocalStack in studio

The studio creates LocalStack from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **AWS emulators**, click the **LocalStack (SQS, S3, Secrets Manager)**
   card. The drawer title changes to *Create LocalStack (SQS, S3, Secrets Manager)*.
4. **Resource key**: type `jobs` (the form suggests a free name). Handlers and triggers use this key.
5. **Use as**: pick **Queue** / **Bucket** / **Secret manager**.
6. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
7. **Port**: leave empty for `4566`, or type another one if that port is taken.
8. **Security**: LocalStack runs without authentication; choose **Listen on**: *This machine only (127.0.0.1)* or
   *Network (0.0.0.0)* and limit the port with the firewall.
9. **Web UI**: built in (Status (JSON)); *How to use* shows its address and login.
10. **Trigger functions**: tick the functions that run for each message / object. Each gets an event on `resource:
    jobs`.
11. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
12. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
13. The resource and the triggers are added to the draft. Click **Save** in the top bar to write `pskit.yml`, then
    deploy.

## Create LocalStack from the terminal

`pskit resources onprem create KEY --service localstack` starts LocalStack and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create jobs --service localstack --attach worker --save                 # here, or the deploy target
pskit resources onprem create jobs --service localstack --server edge1 --attach worker --save   # a saved server
pskit resources onprem create jobs --service localstack --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
pskit resources onprem create jobs --service localstack --role storage --save
pskit resources onprem create secrets --service localstack --role secrets --save
```

- `--role` picks `queue`, `storage`, `secrets` (default `queue`).
- `-a / --attach FUNCTION` (repeatable) adds the trigger to that function.
- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for LocalStack

Creating LocalStack adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env
file (`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5`
and the defaults.

Used as **Queue** (`--role queue`):

```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: http://10.0.0.5:4566/000000000000/jobs
      endpoint: http://10.0.0.5:4566
      region: us-east-1
      access_key: test
      secret_key: test
      create_queue: true
```

Used as **Bucket** (`--role storage`):

```yaml
resources:
  jobs:
    type: storage
    external: true
    options:
      driver: s3
      endpoint: http://10.0.0.5:4566
      bucket: jobs
      access_key: test
      secret_key: test
      path_style: true
      create_bucket: true
```

Used as **Secret manager** (`--role secrets`):

```yaml
resources:
  secrets:
    type: custom
    external: true
    connection:
      driver: aws
      url: http://10.0.0.5:4566
      region: us-east-1
```

```text
# .env.onprem
PSKIT_SECRETS_DRIVER=aws
PSKIT_SECRETS_URL=http://10.0.0.5:4566
PSKIT_SECRETS_REGION=us-east-1
PSKIT_SECRETS_ACCESS_KEY=test
PSKIT_SECRETS_SECRET_KEY=test
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use LocalStack from a handler

A handler reaches LocalStack through `resource("jobs")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

As a queue, functions with `queue: {resource: jobs}` run for each batch of messages, and `submit_queue` publishes
through the on-prem host (so the resource's driver is used):

```python
from py_serverless_kit import BatchResult, resource
from py_serverless_kit.runtime.onprem_host import submit_queue


def send_job(event, ctx):
    """HTTP trigger: put the request body on the jobs queue."""
    payload = event.http.json() if event.http else event.data
    message_id = submit_queue(resource("jobs").native_name, payload)
    return {"id": message_id}


def on_job(event, ctx):
    """Trigger: queue: {resource: jobs}. A failed record is retried."""
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
      - queue: {resource: jobs}
```

As a bucket, functions with `storage: {resource: jobs}` run for each new or deleted object, and `put_object` writes
through the on-prem host:

```python
from py_serverless_kit import resource
from py_serverless_kit.runtime.onprem_host import put_object


def upload(event, ctx):
    """HTTP trigger: write one object into the jobs bucket."""
    put_object(resource("jobs").native_name, "in/hello.txt", b"hello")
    return {"written": "in/hello.txt"}


def on_file(event, ctx):
    """Trigger: storage: {resource: jobs}."""
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
      - storage: {resource: jobs}
```

As a secret manager, `get_secret()` and `put_secret()` read the `PSKIT_SECRETS_*` variables pskit wrote to the env
file. With the key `secrets` it is the default store; with another key pass `store="<key>"`:

```python
from py_serverless_kit import get_secret, put_secret


def handler(event, ctx):
    api_key = get_secret("api-key")                 # one value
    db_password = get_secret("prod/db", "password") # one field of a JSON secret
    put_secret("last-run", ctx.request_id)
    return {"has_key": bool(api_key), "has_db_password": bool(db_password)}
```

Node.js handlers use `getSecret("api-key")` from the `pskit` package. More: [secrets
guide](../../resource-guides/onprem/secrets.md).

`pskit resources usage jobs` (studio: **How to use** on the resource row) prints the same code for Python and Node.js
with the libraries to install, and `pskit resources onprem usage jobs` shows how to connect from any other program.

## Open the LocalStack web UI, console and terminal

The LocalStack row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Status (JSON) on port `4566` at
  `/_localstack/health` (no login). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Browse** opens pskit's own browser (buckets and objects over S3, Secrets Manager secrets).
- **Console** runs one command at a time with **awslocal** and the service's credentials, for example `sqs
  list-queues`, `s3 ls`, `secretsmanager list-secrets`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status jobs --reveal      # state, health, endpoint, credentials
pskit resources onprem usage jobs                # connect from any program
pskit resources onprem logs jobs -n 100
pskit resources onprem gui jobs                  # print the web UI links (starts a companion)
pskit resources onprem gui jobs --check
pskit resources onprem console jobs "sqs list-queues"
pskit resources onprem terminal jobs
pskit resources onprem tunnel jobs                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove LocalStack

LocalStack backups stream a dump out of the container into `.pskit/backups/jobs-<time>.tar.gz` on this machine (also
from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up now**.

```bash
pskit resources onprem backup jobs
pskit resources onprem backup jobs --dir ~/backups
```

To remove LocalStack: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the
Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and
data*.

```bash
pskit resources onprem remove jobs --save                 # keep the data volume
pskit resources onprem remove jobs --delete-data --save   # delete it too
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
- [Existing secrets guide](../../resource-guides/onprem/secrets.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
