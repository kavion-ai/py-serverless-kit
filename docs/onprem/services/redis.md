# Redis

Search terms: Redis, redis queue, redis stream, consumer group, cache, redis-cli, Redis Commander, 6379, key value
store, on-prem cache

Redis is an in-memory key-value store. On premises pskit runs it in Docker and you use it three ways: as a **queue**
(the `redis` driver: leased lists with crash recovery), as a **stream** (the `redis_stream` driver: a consumer group,
so several hosts share the work) or as a **cache** your handlers talk to directly.

## Redis at a glance

The Redis service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `redis` |
| Studio card | **Redis-compatible (cache, queue, stream)** > **Redis** |
| Docker image | `redis:7-alpine` |
| Port | `6379` |
| Use as | `queue` (Queue, resource type `queue`), `stream` (Stream (consumer group), resource type `queue`), `cache` (Cache, resource type `cache`) |
| Login | user (default `default`) and password (generated when empty) |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.rdb`) |
| Web UI | companion **Redis Commander** (default port `8082`; login: user admin, password in the env file) |
| Console | redis-cli |

## Create Redis in studio

The studio creates Redis from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Redis-compatible (cache, queue, stream)**, click the **Redis** card. The
   drawer title changes to *Create Redis*.
4. **Resource key**: type `jobs` (the form suggests a free name). Handlers and triggers use this key.
5. **Use as**: pick **Queue** / **Stream (consumer group)** / **Cache**.
6. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
7. **Port**: leave empty for `6379`, or type another one if that port is taken.
8. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
9. **Web UI**: keep **Also start Redis Commander** on to get its web UI; **Web UI login** *With password* (empty **Web
   UI password** = generated) or *Without password* (only on 127.0.0.1, a private network or a tunnel).
10. **Trigger functions**: tick the functions that run for each message / object. Each gets an event on `resource:
    jobs`.
11. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**.
12. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
13. The resource and the triggers are added to the draft. Click **Save** in the top bar to write `pskit.yml`, then
    deploy.

## Create Redis from the terminal

`pskit resources onprem create KEY --service redis` starts Redis and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create jobs --service redis --attach worker --save                 # here, or the deploy target
pskit resources onprem create jobs --service redis --server edge1 --attach worker --save   # a saved server
pskit resources onprem create jobs --service redis --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
pskit resources onprem create jobs --service redis --role stream --save
pskit resources onprem create cache --service redis --role cache --save
export JOBS_PASSWORD='Str0ng.pass-1'
pskit resources onprem create jobs --service redis --user app --password-env JOBS_PASSWORD --bind 127.0.0.1 --local --save
pskit resources onprem create jobs --service redis --gui --save    # also start Redis Commander
```

- `--role` picks `queue`, `stream`, `cache` (default `queue`).
- `-a / --attach FUNCTION` (repeatable) adds the trigger to that function.
- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Redis

Creating Redis adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

Used as **Queue** (`--role queue`):

```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis
      url_env: PSKIT_JOBS_URL
      key: jobs
```

```text
# .env.onprem
PSKIT_JOBS_URL=redis://:<password>@10.0.0.5:6379/0
PSKIT_JOBS_PASSWORD=<password>
```

Used as **Stream (consumer group)** (`--role stream`):

```yaml
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis_stream
      url_env: PSKIT_JOBS_URL
      key: jobs
```

```text
# .env.onprem
PSKIT_JOBS_URL=redis://:<password>@10.0.0.5:6379/0
PSKIT_JOBS_PASSWORD=<password>
```

Used as **Cache** (`--role cache`):

```yaml
resources:
  cache:
    type: cache
    external: true
    connection:
      host: 10.0.0.5
      port: 6379
      url_env: PSKIT_CACHE_URL
      password_env: PSKIT_CACHE_PASSWORD
```

```text
# .env.onprem
PSKIT_CACHE_URL=redis://:<password>@10.0.0.5:6379/0
PSKIT_CACHE_PASSWORD=<password>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Redis from a handler

A handler reaches Redis through `resource("jobs")`, which returns the connection values pskit passes to bound
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

As a cache (`--role cache`, key `cache`), connect with a Redis client:

```python
import redis

from py_serverless_kit import resource


def count_visit(event, ctx):
    r = resource("cache")
    client = redis.from_url(ctx.env[r["url_env"]])   # PSKIT_CACHE_URL from the env file
    return {"visits": client.incr("visits")}
```

Add `redis` to `requirements.txt`.

`pskit resources usage jobs` (studio: **How to use** on the resource row) prints the same code for Python and Node.js
with the libraries to install, and `pskit resources onprem usage jobs` shows how to connect from any other program.

## Open the Redis web UI, console and terminal

The Redis row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: companion **Redis Commander** (default port
  `8082`; login: user admin, password in the env file). **Check web UI** finds out why a UI does not open (container,
  port, firewall).
- **Console** runs one command at a time with **redis-cli** and the service's credentials, for example `PING`, `INFO
  server`, `KEYS *`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): the service's client.

```bash
pskit resources onprem status jobs --reveal      # state, health, endpoint, credentials
pskit resources onprem usage jobs                # connect from any program
pskit resources onprem logs jobs -n 100
pskit resources onprem gui jobs                  # print the web UI links (starts a companion)
pskit resources onprem gui jobs --check
pskit resources onprem console jobs "PING"
pskit resources onprem terminal jobs
pskit resources onprem tunnel jobs                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Redis

Redis backups stream a dump out of the container into `.pskit/backups/jobs-<time>.rdb` on this machine (also from an
SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up now**.

```bash
pskit resources onprem backup jobs
pskit resources onprem backup jobs --dir ~/backups
```

To remove Redis: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted,
its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources
table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

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
- [Existing cache guide](../../resource-guides/onprem/cache.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
