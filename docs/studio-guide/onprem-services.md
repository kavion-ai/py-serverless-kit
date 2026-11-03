# On-prem services panel in studio

Search terms: on-prem services, one-click service, create service, Redis, PostgreSQL, MySQL, MongoDB, MinIO, Kafka, RabbitMQ, NATS, OpenBao, LocalStack, SMTP server, Docker service, install Node.js, web UI, backup, console, terminal, browse bucket, browse secrets, service details

The **On-prem services** panel starts databases, queues, caches, object stores, secret managers and tools with
Docker, on this machine or on any saved SSH server, and adds them as resources. It sits on the
[Resources page](resources.md) (sidebar **Resources**), above the [Servers panel](servers.md). Passwords go to the
env file (default `.env.onprem`), which the on-prem host loads, never into `pskit.yml`. What each service is and how
to use it from code is in [On-prem services](../onprem/services/README.md).

## Read the on-prem services table in studio

The studio on-prem services table lists the services created from this project.

| Column | What it shows |
|---|---|
| **Key** | The resource key |
| **Service** | Redis, PostgreSQL, MinIO, ... |
| **Used as** | Queue, Stream (consumer group), Cache, Database, Bucket, Service, Secret manager, SMTP server (mail trigger), or `runtime` for installed software |
| **Where** | The server (or "primary + N replicas (sync / async)" for a replicated database) |
| **Endpoint** | `address:port` |

Row buttons: **How to use** (**DNS guide** for SMTP), **Details**, **Browse** / **Browse secrets** (services with a
pskit browser), **Console**, **Terminal**, **Add to pskit.yml** (when it is not in the project), **Backup**
(services that support it) and **Remove**. The header has **Guide** and **+ Create service**.

## Create an on-prem service in studio

The studio **Create a service** drawer starts a service with Docker and adds it to the draft.

1. On **Resources**, click **+ Create service** in the On-prem services panel (or **+ On-prem service** in the page
   header, **+ SMTP server**, or **Create a <type> on premises** in the Add resource drawer).
2. Pick a card. Groups: **Queues & streams**, **Redis-compatible (cache, queue, stream)**, **Object storage**,
   **Databases**, **Mail (receive e-mail, run functions)**, **Secret managers**, **AWS emulators**, **Monitoring &
   tracing**, **Identity & search**, **Automation, web & tools**, and three **Install on a server** groups. Each card
   shows notes, the port and the web UI. **Pick another** goes back.
3. **Resource key** (required): `resource("key")` in handlers.
4. **Use as** (when the service has several roles): for example Redis as **Queue**, **Stream (consumer group)** or
   **Cache**.
5. **Scaling** (databases): **Single server** or **Primary + read replicas** (see [replication.md](replication.md)).
6. **Where**: **This machine**, **One SSH server** or **Scaling cluster** (a server of a [cluster](cluster.md);
   **Server in the cluster** = Auto, the reachable server with the most free memory under every limit, or a named
   one).
7. With **One SSH server**: **Server** = a saved server or **New connection…** with **Host**, **User**, **SSH port**,
   **Log in with** (**Key file (.pem)**, **SSH agent / default key**, **Password**), **Private key (.pem)** or **SSH
   password**, and **Use sudo**.
8. **Port** (the host port), then the **Security** box: **User**, **Password** (empty = a strong random one;
   **Show**), **Listen on** (**This machine only (127.0.0.1)** or **Network (0.0.0.0)**). Services without
   authentication say so.
9. **Import data** (optional): a dump on this machine, or a pskit backup, loaded once the service is up.
10. **Alerts** (databases) and **Web UI**: **Also start <companion>**, **Web UI login** (**With password** /
    **Without password**) and **Web UI password**.
11. **Trigger functions** (queue, stream, storage, SMTP roles): tick the functions that get a trigger on it.
12. **Advanced**: **Address functions use**, **Docker image**; for SMTP also **pskit host URL** and **Largest mail
    (MB)** (default 25).
13. Click **Create** (**Install** for runtimes). The log streams in the drawer. When it is **Created**, the resource,
    `provider.options.env_file` and the ticked triggers are added to the draft. Press **Save**.

From the terminal:

```bash
pskit resources onprem catalog
pskit resources onprem create jobs --service redis --attach worker --save
pskit resources onprem list
```

## Install software on a server from studio

The **Install on a server** groups of the Create a service drawer install software instead of starting a container:
Docker, Python (system or an exact `3.X`), Node.js, Java, Go, nginx, Caddy, Certbot, PM2, Git and tools (curl, wget,
unzip, jq, htop, tmux, netcat). Pick a card, pick the **Server** and a **Version** when offered, and click **Install**.
**Install / create** on a row of the [Servers panel](servers.md) opens the same drawer for that server. A runtime
row's **Remove** only makes pskit forget it; the software stays installed.

```bash
pskit resources onprem create docker --service docker --server app-1
```

More: [Terminal and software](../onprem/terminal-and-software.md).

## Open a service's details, web UI and logs

**Details** on a service row opens **Service <key>**:

- State (`running`, ready or not ready), service and server, start time, and errors. When this machine cannot reach
  the port, a box suggests `pskit resources onprem tunnel <key>`.
- **Endpoint**: `address:port`.
- [Replicas](replication.md#add-or-remove-a-read-replica-in-studio), [Live monitoring and Alerts](monitoring.md)
  for container services.
- **Web UI**: **Open <UI>**, **Check web UI** (tests the container, the port, the server and this machine, and names
  the fix: firewall / NSG, bind, tunnel), **Add web UI** (with **Login**: **With password** / **Without password**)
  and **Remove web UI**.
- **Credentials (<env file>)** with **Show values**; **Resource in pskit.yml**; **Backups**.
- **Container logs**: **Show logs** / **Refresh**.

```bash
pskit resources onprem status jobs
pskit resources onprem gui jobs            # --remove to stop the web UI
pskit resources onprem logs jobs
```

## Use How to use for an on-prem service

**How to use** on a service row opens **How to use <key>**: how to connect from any program (Python and Node.js
clients, the terminal, security) and the web UI's URL, login and tunnel command. **Show passwords and URLs** reveals
secrets; **Copy guide** copies it. For an SMTP server the button is **DNS guide**: the A and MX records to add at your
domain provider, the port, and the mail fields handlers get. Terminal: `pskit resources onprem usage <key>`.

## Run commands in a service: Console and Terminal

**Console** opens **Console: <key>**: type one command per line and see its output. The mode switch picks the
service's own client (redis-cli, psql, mongosh, rpk, bao, ...) or **Shell in the container**; example chips fill the
line; ↑ / ↓ browse history and `clear` clears. **Full terminal** opens a browser terminal.

**Terminal** opens a full interactive terminal (ttyd in Docker on this machine; the first start builds a small image).
It listens on 127.0.0.1 behind a secret URL; closing the panel keeps it running, **Stop terminal** removes it.

```bash
pskit resources onprem console jobs
pskit resources onprem terminal jobs
```

## Browse buckets and secrets with pskit's own browser

**Browse** (MinIO, RustFS, LocalStack, LocalEmu, fake-gcs-server, pskit's S3 server) opens **Browse <key>**:
create and delete buckets (**Bucket settings**: **Make private**, **Make public (read)**, **Save policy**), filter by prefix,
**Upload files**, new folders, **Download**, **Info** (versions), **Rename / move**, **Copy**, **Delete**, **Share…**
links (1 hour, 1 day, 7 days or a custom time) and paging. **Browse secrets** (OpenBao and the AWS emulators) lists
secrets in folders with versions: add, **Edit**, **Delete**, **Show values** and **Copy**.

## Back up or remove an on-prem service

**Backup** opens **Back up <key>**: **Save to folder** (empty = `.pskit/backups`; **Browse…** picks any folder on this
machine, remembered). Click **Back up now**. Load a backup later with **Import data** when you create a service.

**Remove** asks **Remove <key>?**: **Remove, keep data** stops and deletes the container and keeps its data volume;
**Delete data too** deletes the volume as well. The resource and its triggers are removed from the draft.

```bash
pskit resources onprem backup jobs
pskit resources onprem remove jobs
```

## See also

- [On-prem services catalog](../onprem/services/README.md)
- [Servers panel](servers.md), [Replication](replication.md), [Monitoring and alerts](monitoring.md)
- [On-prem resources](../onprem/resources.md)
- [One-click services guide](../resource-guides/onprem/services.md)
- [E-mail triggers](../smtp/README.md)
