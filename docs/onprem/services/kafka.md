# Kafka (Redpanda, single node)

Search terms: Kafka, Redpanda, Kafka API, rpk, topic, consumer group, kafka-python, 9092, Kafka UI

This service runs Redpanda, a single-node server with the Kafka API (no ZooKeeper). pskit consumes the topic through a
driver class it copies into your app (`pskit_drivers/kafka_queue.py`, needs `kafka-python`). It has **no
authentication**: keep the port on a private network.

## Kafka at a glance

The Kafka service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `kafka` |
| Studio card | **Queues & streams** > **Kafka (Redpanda, single node)** |
| Docker image | `redpandadata/redpanda:v24.3.6` |
| Port | `9092` |
| Use as | `queue` (Queue, resource type `queue`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | kept in `/var/lib/redpanda/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | companion **Kafka UI** (default port `8088`; login: user admin, password in the env file (sign-in page /auth)) |
| Console | rpk |

## Create Kafka in studio

The studio creates Kafka from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Queues & streams**, click the **Kafka (Redpanda, single node)** card. The
   drawer title changes to *Create Kafka (Redpanda, single node)*.
4. **Resource key**: type `events` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `9092`, or type another one if that port is taken.
7. **Security**: Kafka runs without authentication; choose **Listen on**: *This machine only (127.0.0.1)* or *Network
   (0.0.0.0)* and limit the port with the firewall.
8. **Web UI**: keep **Also start Kafka UI** on to get its web UI; **Web UI login** *With password* (empty **Web UI
   password** = generated) or *Without password* (only on 127.0.0.1, a private network or a tunnel).
9. **Trigger functions**: tick the functions that run for each message / object. Each gets an event on `resource:
   events`.
10. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
11. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
12. The resource and the triggers are added to the draft. Click **Save** in the top bar to write `pskit.yml`, then
    deploy.

## Create Kafka from the terminal

`pskit resources onprem create KEY --service kafka` starts Kafka and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create events --service kafka --attach worker --save                 # here, or the deploy target
pskit resources onprem create events --service kafka --server edge1 --attach worker --save   # a saved server
pskit resources onprem create events --service kafka --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
pskit resources onprem create events --service kafka --gui --save    # also start Kafka UI
```

- `-a / --attach FUNCTION` (repeatable) adds the trigger to that function.
- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Kafka

Creating Kafka adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  events:
    type: queue
    external: true
    options:
      driver: custom
      class: pskit_drivers.kafka_queue:KafkaQueue
      bootstrap_servers: 10.0.0.5:9092
      topic: events
      group_id: shop-events
```

pskit also copies `pskit_drivers/kafka_queue.py` into your code (under `package.source`, once; edit it freely) and
adds `kafka-python>=2.0.3` to `requirements.txt`.

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Kafka from a handler

A handler reaches Kafka through `resource("events")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

As a queue, functions with `queue: {resource: events}` run for each batch of messages, and `submit_queue` publishes
through the on-prem host (so the resource's driver is used):

```python
from py_serverless_kit import BatchResult, resource
from py_serverless_kit.runtime.onprem_host import submit_queue


def send_job(event, ctx):
    """HTTP trigger: put the request body on the events queue."""
    payload = event.http.json() if event.http else event.data
    message_id = submit_queue(resource("events").native_name, payload)
    return {"id": message_id}


def on_job(event, ctx):
    """Trigger: queue: {resource: events}. A failed record is retried."""
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
      - queue: {resource: events}
```

`pskit resources usage events` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage events` shows how to connect from any other
program.

## Open the Kafka web UI, console and terminal

The Kafka row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: companion **Kafka UI** (default port `8088`;
  login: user admin, password in the env file (sign-in page /auth)). **Check web UI** finds out why a UI does not open
  (container, port, firewall).
- **Console** runs one command at a time with **rpk** and the service's credentials, for example `cluster info`,
  `topic list`, `topic describe events`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status events --reveal      # state, health, endpoint, credentials
pskit resources onprem usage events                # connect from any program
pskit resources onprem logs events -n 100
pskit resources onprem gui events                  # print the web UI links (starts a companion)
pskit resources onprem gui events --check
pskit resources onprem console events "cluster info"
pskit resources onprem terminal events
pskit resources onprem tunnel events                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Kafka

Kafka backups stream a dump out of the container into `.pskit/backups/events-<time>.tar.gz` on this machine (also from
an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up now**.

```bash
pskit resources onprem backup events
pskit resources onprem backup events --dir ~/backups
```

To remove Kafka: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted,
its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources
table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove events --save                 # keep the data volume
pskit resources onprem remove events --delete-data --save   # delete it too
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
