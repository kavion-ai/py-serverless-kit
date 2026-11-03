# On-premises provider (onprem)

Search terms: onprem, on-premises, on premise, self-hosted, local host process, own server, bare metal, ssh deploy,
docker deploy, admin token, host options, data_dir, built-in services, pskit_host, terraform_data

The on-premises provider (`provider.name: onprem`) runs your functions in **one long-lived Python process, the host**,
on this machine, on a server over SSH, in a Docker container, or on a scaling cluster of several servers. The host
serves HTTP, runs schedules, file-backed queues, storage buckets, topics, SMTP triggers and embedded workflows. No cloud
account is needed. Terraform uses only its built-in `terraform_data` resource to start and stop the host. Tier:
**experimental**.

| Item | Value |
|---|---|
| Terraform plugin | none (built-in `terraform_data` with `local-exec`) |
| Default region | `local` |
| Triggers | http, schedule, queue, storage, topic, smtp |
| Workflows | embedded engine inside the host (not cut off by a function timeout) |
| Python | `python3.9` to `python3.14` |
| Node.js | `nodejs18`, `nodejs20`, `nodejs22`, `nodejs24` (each function runs in a `node` worker driven by the Python host) |
| Max timeout | 3600 s (not enforced: the host does not kill a handler at `timeout`) |
| Dependencies | pip wheels for the target OS and CPU, vendored into the bundle; `tzdata` is added |

This page covers the provider settings. The on-prem platform (saved servers, services such as Redis or Postgres,
scaling clusters, load balancers, placement) has its own section: [onprem/README.md](../../onprem/README.md).

Pages in this folder:

- [deploy-methods.md](deploy-methods.md): `deploy.method` local, ssh and docker, every `deploy:` key, Python and
  Node.js on the server, saved servers, `--server`.
- [host-api.md](host-api.md): the host's `/__pskit/*` control API, admin token, logs and stats.

## Set up on-premises "credentials" step by step

The on-premises provider has no cloud login. What you need depends on where the host runs:

1. **This machine (`method: local`, the default):** nothing. The host runs with the Python that runs `pskit`.
2. **A server over SSH (`method: ssh`):** OpenSSH (`ssh`, `scp`) on this machine and a login on the server: a key file
   (`.pem`, `id_ed25519`), the SSH agent, or a password through `sshpass`. Save the server once with
   `pskit resources onprem servers add edge1 --ssh ubuntu@10.0.0.5 --pem ~/.ssh/edge1.pem`
   (see [onprem/servers.md](../../onprem/servers.md)).
3. **Docker (`method: docker`):** a Docker CLI on this machine. For a remote server also OpenSSH and a login; pskit
   installs Docker on the server when it is missing.
4. **Optional secrets:** `PSKIT_ADMIN_TOKEN` (protects `/__pskit/*`), `PSKIT_SSH_KEY` (a key path you reference as
   `pem: ${env:PSKIT_SSH_KEY}`).
5. Run `pskit doctor -p onprem`. It checks Terraform, and `ssh` / `scp` or Docker for the configured method.

In studio, **Setup & credentials** -> **Provider** `onprem` shows these checks and an **On-premises connection**
section (**Where the host runs**: **This machine**, **SSH server** or **Docker**, plus host, user, port, key, known
hosts, sudo and Docker host).

## Configure the onprem provider block in pskit.yml

Every top-level key of `provider.options` the on-premises provider accepts (other keys warn *unknown option ... is
ignored*):

```yaml
provider:
  name: onprem
  region: local
  runtime: python3.12
  options:
    host: 127.0.0.1             # bind address on the target (0.0.0.0 to accept other machines)
    port: 8080                  # 1-65535; give each service/stage on one machine its own port
    advertise: https://fn.internal.example   # URL written into pskit info (optional)
    data_dir: .pskit/onprem-data             # queues, buckets, topics, executions, logs
    poll_seconds: 0.5           # how often schedules, queues and buckets are polled (> 0)
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"   # x-pskit-token header for /__pskit/* (except health)
    env_file: .env.onprem       # KEY=VALUE file copied next to the host as host.env, loaded at start
    execution_retention: 500    # finished workflow executions kept (>= 1)
    workflow_workers: 8         # workflow runs at once (>= 1)
    log_buffer: 5000            # log entries kept in memory (>= 100)
    log_level: INFO             # DEBUG | INFO | WARNING | ERROR | CRITICAL
    capture_output: true        # also record print() / stdout / stderr
    services: {}                # built-in queue / storage / topic / schedule / workflow (below)
    deploy: {method: local}     # where the host runs: deploy-methods.md
    # cluster: prod             # run on a scaling cluster instead of deploy (below)
    # placement: {...}          # groups of functions on different servers (below)
    # balancer: edge            # put this deployment behind a shared load balancer (below)
```

| Option | Default | Meaning |
|---|---|---|
| `host` | `127.0.0.1` | Bind address on the target. `0.0.0.0` is shown as `127.0.0.1` in URLs unless `advertise` is set. Docker always binds `0.0.0.0` inside the container. |
| `port` | `8080` | HTTP port of the host. |
| `advertise` | `http://<host>:<port>` | URL in `pskit info`. SSH and remote Docker use the server address when unset. |
| `data_dir` | local: `.pskit/onprem-data/<service>-<stage>`; SSH: `<path>/data`; Docker: `/var/pskit/data` | Where the host keeps data. `pskit remove` never deletes it. |
| `poll_seconds` | `0.5` | Poll interval. |
| `admin_token` | empty | Token for the control API ([host-api.md](host-api.md)). |
| `env_file` | none | Secrets for the host and `<name>_env` driver options; never written to Terraform state. Warns if the file is missing. |
| `execution_retention`, `workflow_workers`, `log_buffer`, `log_level`, `capture_output` | 500, 8, 5000, `INFO`, `true` | Host tuning. |

Studio: **Overview & provider** -> **On-premises options** (**Bind address**, **Port**, **Advertised URL**, **Data
directory**, **Poll interval (s)**, **Admin token**), then the sections **On-premises deployment**, **Built-in
services** and **Host tuning**.

## Choose the built-in on-prem services (options.services)

`provider.options.services` picks how the host implements each kind. Omitted kinds are `builtin`: directories the host
creates under `data_dir` at start.

```yaml
options:
  services:
    schedule: builtin                          # the only schedule implementation
    queue: builtin                             # or {use: directory, path: /var/pskit/queues}
    storage: {use: directory, path: .onprem/buckets}
    topic: builtin
    workflow: embedded                         # builtin is an alias of embedded
```

| Kind | Values |
|---|---|
| `schedule` | `builtin` |
| `queue`, `storage`, `topic` | `builtin`, or `{use: directory, path: ...}` (path required). Relative paths are under the project (local) or the remote path / `/var/pskit/data` (SSH / Docker). |
| `workflow` | `embedded` (or `builtin`) |

A single queue, bucket or topic can instead live in a real service (Redis, S3/MinIO, SQS, Azure Queue, Pub/Sub, ...):
declare it under `resources:` with `options.driver`. See [onprem/resources.md](../../onprem/resources.md) and
[onprem/cloud-resources.md](../../onprem/cloud-resources.md). Studio: **Overview & provider** -> **Built-in services**.

## Run on several servers: cluster, placement and balancer options

Three options spread one project over more than one machine. They are explained in the on-prem pages; this table only
names the keys.

| Option | Shape | Page |
|---|---|---|
| `cluster` | `NAME` or `{name, replicas: 1-500 (default 2), cpu: 0.05-64 (default 0.25), memory: 32-262144 MB (default 256), balancer_port}` | [onprem/scaling/README.md](../../onprem/scaling/README.md) |
| `placement` | `{default: GROUP, groups: {GROUP: {server: NAME \| cluster: NAME \| local: true, functions: [...], port, advertise}}}` | [onprem/placement.md](../../onprem/placement.md) |
| `balancer` | `NAME`, `{name, path, algorithm, weights}` or a list of those | [onprem/load-balancers.md](../../onprem/load-balancers.md) |

`cluster` replaces `deploy`: the cluster's master becomes the SSH target used by logs and tests. `pskit deploy
--cluster NAME` does the same for one run.

## Terraform resources pskit creates on premises

| Resource | What it does |
|---|---|
| `terraform_data.host` | Create: runs `onprem_deploy.py apply` in `.pskit/onprem-<stage>/onprem_app/` (starts or restarts the host). Destroy: runs `onprem_deploy.py destroy` (stops the process, systemd unit or container). Replaced when the artifact or the host spec changes. |
| `terraform_data.host_<group>` | One more per placement group, in `onprem_app_<group>/`. |

`terraform.extra` resources of another cloud (`aws_*`, `google_*`, `azurerm_*`, ...) are omitted with a warning. A
state backend of `s3`, `gcs` or `azurerm` warns; set `provider.state.backend` empty under `providers.onprem` to keep
state on this machine.

## How triggers map to the on-prem host

| pskit trigger | Host implementation |
|---|---|
| `http` | The host's HTTP server on `host:port`. Only `auth: none` (check tokens in the handler). |
| `schedule` | In-process: any `rate` (minutes, hours, days) and 5-field cron. A missing IANA timezone warns and runs in UTC. A missed run fires once. |
| `queue` | One JSON file per message. `batch_size`, `batch_window`, `visibility_timeout` (default `max(30, 6 x timeout)`), `dead_letter`, `max_receive`, `fifo` are honoured; a `BatchResult` retries only failed ids. |
| `storage` | Files under `<bucket>/<key>`; `prefix`, `suffix`, `created`, `deleted`. Dropping a file in the folder also fires. |
| `topic` | Fan-out to every subscriber; `filter` matches message attributes, then JSON body fields. |
| `smtp` | Mail received by an on-prem SMTP service resource. See [triggers/smtp.md](../../triggers/smtp.md). |

Delivery is at least once. Queue, bucket and topic names are one path segment (`..`, `/` and NUL are rejected).

## Run workflows on premises

Workflows run on the embedded engine inside the host, so a long workflow is not cut off by a function timeout and
validation does not warn. Executions are stored under `<data_dir>/executions` (`execution_retention`). Start and inspect
them:

```bash
pskit workflow start order -i '{"id": 1}' --wait
pskit workflow executions order --status FAILED
pskit workflow status <execution-id> --watch
pskit workflow cancel <execution-id>
```

Over HTTP: `POST <endpoint>/workflows/<name>` or `POST <endpoint>/__pskit/workflows/<name>`. See
[deployment/workflows.md](../../deployment/workflows.md) and [workflow-executions.md](../../workflow-executions.md).

## Find the on-prem endpoint after deploy

`pskit info` shows the `endpoint` (from `advertise`, or `http://<server>:<port>`), each function's URL and a console
link to `<endpoint>/__pskit/health`, plus `deployed on: <server> (<host>)`. The stage remembers its machine in
`.pskit/onprem-<stage>/onprem_deployed.json`: `pskit trigger`, `pskit logs`, the dashboard and studio's **Test** and
**Logs** pages talk to that host. When its port is closed to this machine, pskit sends those calls over the deploy's
SSH login to `127.0.0.1:<port>` on the server. To call functions from elsewhere, open the port (`host: 0.0.0.0` plus a
firewall rule, see [onprem/firewall.md](../../onprem/firewall.md)) or run `pskit client tunnel`.

## Read logs of an on-prem deployment

The host captures `logging`, `print()` output, one entry per invocation and host notes. Read them with `pskit logs`
(`-f` follows, `--function`, `--level`, `--source`, `-q`, `--json`, `--delete`) or the studio **Logs** page. Details:
[host-api.md](host-api.md#read-on-prem-host-logs) and [deployment/logs.md](../../deployment/logs.md).

## On-prem limits and gotchas

- No cloud authorizer and no IAM mapping: `auth` must be `none`; `iam` is not used.
- The host does not kill a handler at `timeout`; `ctx.remaining_time_ms()` still counts down.
- With `method: local`, the host uses the interpreter that runs `pskit`; a different `provider.runtime` warns (use
  `deploy.python: bundle` to pin one).
- SSH and Docker deploys bind `127.0.0.1` unless `host: 0.0.0.0` (warning).
- `pskit remove` stops the host and keeps `data_dir`.

## Deploy on premises from the terminal

```bash
pskit init svc -p onprem -t full     # new project
pskit dev                            # optional: local server with hot reload
pskit deploy                         # -p onprem when provider.name is another cloud
pskit deploy --server edge1          # one run on a saved server; --server local for this machine
pskit deploy --cluster prod          # one run on a scaling cluster
pskit info
pskit logs -f
pskit remove --yes                   # stops the host; data_dir stays
```

The bundle is written to `.pskit/onprem-<stage>/onprem_app/`. See [deploy-methods.md](deploy-methods.md).

## Deploy on premises in studio

1. Run `pskit studio --open`.
2. **Overview & provider** -> click the **On-premises** card -> confirm the switch.
3. Set **Port** (and **Bind address** `0.0.0.0` for a server). In **On-premises deployment** pick a **Saved server** or
   a **Deploy method** (**This machine**, **SSH server**, **Docker**). For SSH, click **Test SSH connection**.
4. Click **Save**.
5. **Deploy** -> under **Run on** choose **One machine** (then **Machine**) or **Scaling cluster** -> click **Deploy**
   -> confirm. The output has a **Steps** tab and a **Raw log** tab.
6. **Info** shows the endpoint. **Remove** asks you to type `onprem/<stage>`; the toggle under the action cards decides
   whether buckets, queues and topics are deleted too.

## Minimal on-prem example

```yaml
service: hello-onprem
provider:
  name: onprem
  options:
    port: 8080
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
  worker:
    handler: app.handlers.worker
    events:
      - queue: {name: jobs, batch_size: 5}
```

```bash
pskit deploy && curl http://127.0.0.1:8080/hello
```

Full examples: [`examples/16-on-premises`](../../../examples/16-on-premises) (local process) and
[`examples/17-on-premises-remote`](../../../examples/17-on-premises-remote) (SSH, Docker, bundled Python).

## See also

- [deploy-methods.md](deploy-methods.md), [host-api.md](host-api.md)
- [onprem/README.md](../../onprem/README.md): servers, services, scaling, load balancers, network
- [deployment/README.md](../../deployment/README.md)
- [providers.md](../../providers.md#onprem-on-premises): the older reference
- [Providers index](../README.md)
