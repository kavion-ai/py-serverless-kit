# NATS JetStream

Search terms: NATS, JetStream, nats-py, durable consumer, nats-box, 4222, 8222, message streaming

NATS JetStream is a lightweight messaging server with persistent streams. pskit consumes a JetStream stream with a
durable pull consumer, through a driver class it copies into your app (`pskit_drivers/nats_queue.py`, needs
`nats-py`). Monitoring runs on port 8222.

## NATS JetStream at a glance

The NATS JetStream service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `nats` |
| Studio card | **Queues & streams** > **NATS JetStream** |
| Docker image | `nats:2.10-alpine` |
| Port | `4222` (also `8222`). Extra ports move with the main port |
| Use as | `queue` (Queue, resource type `queue`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | Monitoring (JSON) on port `8222` at `/` (no login) |
| Console | nats (nats-box helper) |

## Create NATS JetStream in studio

The studio creates NATS JetStream from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Queues & streams**, click the **NATS JetStream** card. The drawer title
   changes to *Create NATS JetStream*.
4. **Resource key**: type `jobs` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `4222`, or type another one if that port is taken.
7. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
8. **Web UI**: built in (Monitoring (JSON)); *How to use* shows its address and login.
9. **Trigger functions**: tick the functions that run for each message / object. Each gets an event on `resource:
   jobs`.
10. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
11. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
12. The resource and the triggers are added to the draft. Click **Save** in the top bar to write `pskit.yml`, then
    deploy.

## Create NATS JetStream from the terminal

`pskit resources onprem create KEY --service nats` starts NATS JetStream and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create jobs --service nats --attach worker --save                 # here, or the deploy target
pskit resources onprem create jobs --service nats --server edge1 --attach worker --save   # a saved server
pskit resources onprem create jobs --service nats --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export JOBS_PASSWORD='Str0ng.pass-1'
pskit resources onprem create jobs --service nats --user app --password-env JOBS_PASSWORD --bind 127.0.0.1 --local --save
```

- `-a / --attach FUNCTION` (repeatable) adds the trigger to that function.
- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for NATS JetStream

Creating NATS JetStream adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env
file (`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5`
and the defaults.

```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: custom
      class: pskit_drivers.nats_queue:NatsQueue
      url_env: PSKIT_JOBS_URL
      stream: jobs
      subject: jobs.jobs
      durable: pskit
    connection:
      monitor_url: http://10.0.0.5:8222
```

```text
# .env.onprem
PSKIT_JOBS_URL=nats://pskit:<password>@10.0.0.5:4222
PSKIT_JOBS_PASSWORD=<password>
```

pskit also copies `pskit_drivers/nats_queue.py` into your code (under `package.source`, once; edit it freely) and adds
`nats-py>=2.6` to `requirements.txt`.

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use NATS JetStream from a handler

A handler reaches NATS JetStream through `resource("jobs")`, which returns the connection values pskit passes to bound
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

`pskit resources usage jobs` (studio: **How to use** on the resource row) prints the same code for Python and Node.js
with the libraries to install, and `pskit resources onprem usage jobs` shows how to connect from any other program.

## Open the NATS JetStream web UI, console and terminal

The NATS JetStream row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Monitoring (JSON) on port `8222` at `/` (no
  login). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** runs one command at a time with **nats (nats-box helper)** and the service's credentials, for example
  `server info`, `stream ls`, `stream info jobs`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status jobs --reveal      # state, health, endpoint, credentials
pskit resources onprem usage jobs                # connect from any program
pskit resources onprem logs jobs -n 100
pskit resources onprem gui jobs                  # print the web UI links (starts a companion)
pskit resources onprem gui jobs --check
pskit resources onprem console jobs "server info"
pskit resources onprem terminal jobs
pskit resources onprem tunnel jobs                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove NATS JetStream

NATS JetStream backups stream a dump out of the container into `.pskit/backups/jobs-<time>.tar.gz` on this machine
(also from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up
now**.

```bash
pskit resources onprem backup jobs
pskit resources onprem backup jobs --dir ~/backups
```

To remove NATS JetStream: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
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
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
