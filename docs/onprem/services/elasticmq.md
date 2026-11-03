# ElasticMQ (SQS-compatible)

Search terms: ElasticMQ, SQS compatible, Amazon SQS emulator, sqs driver, 9324, 9325, queue browser

ElasticMQ is an Amazon SQS compatible queue server. pskit uses it through the `sqs` driver with an `endpoint`. It
keeps messages **in memory**: a restart empties it, so use it for development and tests. The driver creates the queue
again when it is missing (`create_queue: true`).

## ElasticMQ at a glance

The ElasticMQ service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `elasticmq` |
| Studio card | **Queues & streams** > **ElasticMQ (SQS-compatible)** |
| Docker image | `softwaremill/elasticmq-native:1.6.11` |
| Port | `9324` (also `9325`). Extra ports move with the main port |
| Use as | `queue` (Queue, resource type `queue`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | not persisted (a restart empties it) |
| Backup | no |
| Web UI | Queue browser on port `9325` at `/` (no login) |
| Console | aws sqs (helper) |

## Create ElasticMQ in studio

The studio creates ElasticMQ from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Queues & streams**, click the **ElasticMQ (SQS-compatible)** card. The
   drawer title changes to *Create ElasticMQ (SQS-compatible)*.
4. **Resource key**: type `jobs` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `9324`, or type another one if that port is taken.
7. **Security**: ElasticMQ runs without authentication; choose **Listen on**: *This machine only (127.0.0.1)* or
   *Network (0.0.0.0)* and limit the port with the firewall.
8. **Web UI**: built in (Queue browser); *How to use* shows its address and login.
9. **Trigger functions**: tick the functions that run for each message / object. Each gets an event on `resource:
   jobs`.
10. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
11. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
12. The resource and the triggers are added to the draft. Click **Save** in the top bar to write `pskit.yml`, then
    deploy.

## Create ElasticMQ from the terminal

`pskit resources onprem create KEY --service elasticmq` starts ElasticMQ and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create jobs --service elasticmq --attach worker --save                 # here, or the deploy target
pskit resources onprem create jobs --service elasticmq --server edge1 --attach worker --save   # a saved server
pskit resources onprem create jobs --service elasticmq --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `-a / --attach FUNCTION` (repeatable) adds the trigger to that function.
- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for ElasticMQ

Creating ElasticMQ adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: sqs
      queue_url: http://10.0.0.5:9324/000000000000/jobs
      endpoint: http://10.0.0.5:9324
      region: us-east-1
      access_key: pskit
      secret_key: pskit
      create_queue: true
    connection:
      ui_url: http://10.0.0.5:9325
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use ElasticMQ from a handler

A handler reaches ElasticMQ through `resource("jobs")`, which returns the connection values pskit passes to bound
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

## Open the ElasticMQ web UI, console and terminal

The ElasticMQ row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Queue browser on port `9325` at `/` (no
  login). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** runs one command at a time with **aws sqs (helper)** and the service's credentials, for example `sqs
  list-queues`, `sqs get-queue-attributes --queue-url http://elasticmq:9324/000000000000/jobs --attribute-names All`.
  Switch to *Shell in the container* for `sh`.
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

## Back up and remove ElasticMQ

ElasticMQ has no backup command in pskit (it keeps data in memory only).

To remove ElasticMQ: **Remove** on the row, then **Remove, keep data**. The container is deleted, its variables leave
the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources table, **Delete**
on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove jobs --save                 # keep the data volume
pskit resources onprem remove jobs --delete-data --save   # delete it too
```

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Queue trigger](../../triggers/queue.md)
- [Existing queue guide](../../resource-guides/onprem/queue.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
