# Terminal, console and software on on-prem servers

Search terms: install Docker, install Python, install Node.js, nginx, Caddy, Certbot, PM2, Java, Go, runtime, shell,
console, terminal, ttyd, redis-cli, psql, SSH tunnel, browser terminal

pskit can install software on a saved SSH server, run commands there, and open a console or a full browser terminal
for a server or an on-prem service. Everything runs over SSH (and `docker exec` for services); nothing needs an agent
on the server.

## Software pskit installs on a server

The on-prem catalog has software to install on an SSH server. pskit uploads a POSIX `sh` script and runs it with the
server's package manager (apt-get, dnf, yum or apk). Scripts only add packages and start services; nothing is ever
removed.

| Software | `--service` | Versions (`--version`) | What it installs |
|---|---|---|---|
| Docker | `docker` | none | Docker, installed and started (needed by every service and by `deploy.method: docker`) |
| Python 3 | `python` | `system` (default), 3.13, 3.12, 3.11, 3.10, 3.9, 3.14 | `system`: the distribution's python3 with venv and pip. A version: that CPython (standalone build through uv, any distribution) in `/opt/pskit-python`, linked as `/usr/local/bin/python3.X` |
| Node.js | `nodejs` | 22 (default), 24, 20, 18 | Node.js and npm from NodeSource (apt / dnf); Alpine installs its own version |
| Java (OpenJDK) | `java` | 21 (default), 17 | headless OpenJDK runtime |
| Go | `go` | 1.23.4 (default), 1.22.10 | the official toolchain in `/usr/local/go`, linked into `/usr/local/bin` |
| nginx | `nginx` | none | nginx from the distribution, enabled and started |
| Caddy | `caddy` | 2.8.4 | the `caddy` binary in `/usr/local/bin` |
| Certbot (Let's Encrypt) | `certbot` | none | certbot with its nginx plugin where the distribution has it (dnf needs EPEL) |
| PM2 | `pm2` | none | `npm install -g pm2` (install Node.js first) |
| Git | `git` | none | git from the distribution |
| Basic tools | `tools` | none | curl, wget, unzip, jq, htop, tmux and netcat |

Any `1.2.3`-style version is accepted where versions are listed (for example Go `1.23.4`). Software without versions
installs the distribution's package and refuses a version.

## Install software on a server in studio

Software is installed from the same catalog as the services, on an SSH server only (never *This machine*).

1. Open **Resources** in the sidebar. In the *On-prem services* card, find the server in the **Servers** card.
2. Click **Install / create** on its row. The *Create a service* drawer opens with that server chosen.
3. Scroll to **Install on a server: languages & Docker**, **Install on a server: web servers** or
   **Install on a server: process managers & tools** and click the card (for example **Node.js**).
4. **Version**: pick one of the buttons (the first is the default) or type another version in *other version*.
5. **Where** stays **One SSH server** with the server in **Server** (or pick *Scaling cluster* and a cluster).
6. Click **Install**. The script's output streams in the drawer. When it ends, a toast says *&lt;label&gt; is
   installed* and the install is listed in the *On-prem services* table with *Used as: runtime*.

**Details** on that row runs the software's version check over SSH (*installed* or *missing*). **Remove** only
forgets it: the confirmation says the software stays installed, and the button is **Forget**.

Docker is installed automatically when you create a service on a server that lacks it.

## Install software on a server from the terminal

`pskit resources onprem create KEY --service ID` installs software when the id is a runtime. KEY is only the name of
the entry in pskit's list.

```bash
pskit resources onprem create docker --service docker --server edge1
pskit resources onprem create py312 --service python --version 3.12 --server edge1
pskit resources onprem create node --service nodejs --version 20 --server edge1
pskit resources onprem create web --service nginx --server edge1
pskit resources onprem create pm2 --service pm2 --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --sudo
pskit resources onprem status node            # runs the version check
pskit resources onprem remove node            # forgets it; nothing is uninstalled
```

A Python version installed this way is what the on-prem host runs with when the project's runtime is that version
(`runtime: python3.12` with `python: system`).

## Run commands on a server with Shell

The server shell runs one command at a time over SSH with the saved login; each line is a fresh login, so `cd` does
not carry over.

1. In the **Servers** card click **Shell** on the row. The drawer *Shell on &lt;name&gt;* opens.
2. Type a command (or click an example: `uname -a`, `df -h`, `free -m`, `docker ps`, `node -v`,
   `systemctl status nginx --no-pager`) and press Enter or **Run**.
3. The output appears under the command, with `exit N` when it fails. Use ↑ / ↓ for history and `clear` to clear.
   A command stops after 120 seconds.
4. **Full terminal** switches to an interactive session.

```bash
pskit resources onprem shell edge1                  # interactive ssh with the saved login
pskit resources onprem shell edge1 "docker ps"      # run one command and print the output
```

## Run commands in a service with the Console

The service console runs one command at a time with the on-prem service's own client and credentials (credentials
are replaced by `***` in the output).

1. On the service row in the *On-prem services* card click **Console**. The drawer *Console: &lt;key&gt;* opens.
2. The mode switch shows the client (for example **redis-cli**) and **Shell in the container** (`sh -c` inside the
   container).
3. Click an example chip or type a command, then **Run**. A command stops after 60 seconds; use the terminal for
   long-running ones.

| Service | Client | Example |
|---|---|---|
| Redis / Valkey / KeyDB | `redis-cli` / `valkey-cli` / `keydb-cli` | `LLEN jobs` |
| Dragonfly | `redis-cli` (helper container) | `DBSIZE` |
| PostgreSQL / MySQL / MariaDB | `psql` / `mysql` / `mariadb` on the service's database | `SELECT now();` |
| MongoDB | `mongosh` | `db.getCollectionNames()` |
| Kafka (Redpanda) / Apache Kafka | `rpk` / `kafka-*.sh` scripts | `topic list` / `kafka-topics.sh --list` |
| RabbitMQ / LavinMQ | `rabbitmqctl` / `lavinmqctl` | `list_queues` |
| NATS | `nats` (nats-box helper) | `stream ls` |
| MinIO | `mc` (alias `local`) | `ls local` |
| RustFS, Amazon S3 compatible | `aws s3` (helper) | `s3 ls` |
| ElasticMQ / LocalStack | `aws sqs` (helper) / `awslocal` | `sqs list-queues` |
| AWS Secrets Manager compatible | `aws secretsmanager` (helper) | `secretsmanager list-secrets` |
| OpenBao | `bao` | `kv list secret` |
| Memcached | text protocol | `stats` |
| Mailpit / fake-gcs-server | HTTP GET of a path | `/api/v1/messages?limit=5` / `/storage/v1/b` |

Other services have no client: the console runs each line with `sh` in the container. When the image has no client
(Dragonfly, NATS, ElasticMQ, RustFS, the S3 and Secrets Manager servers, Memcached, Mailpit, fake-gcs-server), a
small helper container joins the service's private Docker network for that one command.

```bash
pskit resources onprem console cache                         # interactive client in this terminal
pskit resources onprem console cache "LLEN jobs"
pskit resources onprem console orders-db "SELECT count(*) FROM orders;"
pskit resources onprem console cache --shell                 # sh in the container
```

## Open a full terminal in the browser

The browser terminal is ttyd in Docker **on this machine**, so it works from Windows, macOS and Linux with only Docker
installed. It listens on `127.0.0.1` behind a random secret URL. The first start builds a small image
(`pskit-terminal:1`: ttyd, OpenSSH, sshpass, docker CLI), which takes about a minute.

1. Click **Terminal** on a server row (an SSH session with the saved login) or on a service row (the service's client
   for Redis, Valkey, KeyDB, PostgreSQL, MySQL, MariaDB and MongoDB, otherwise `sh` in the container). **Full
   terminal** in a console drawer does the same.
2. The drawer *Terminal: &lt;title&gt;* shows the terminal. **Open in a new tab** opens it full size.
3. Closing the drawer keeps the terminal running; **Stop terminal** removes it.

```bash
pskit resources onprem terminal --server edge1       # SSH session in the browser
pskit resources onprem terminal cache                # redis-cli in the browser
pskit resources onprem terminal cache --shell        # sh in the container
pskit resources onprem terminal --list
pskit resources onprem terminal --stop all           # or --stop pskit-term-7681
```

Terminals use ports from 7681 upward. Keys are mounted read-only and copied with mode 600 inside the container; a
saved password is used through sshpass.

## Reach a firewalled service with an SSH tunnel

An SSH tunnel forwards `127.0.0.1:<port>` on this machine to an on-prem service on its server, through SSH (port 22),
with no firewall change. Use it when scripts here time out because the service's port is closed.

```bash
pskit resources onprem tunnel orders-db                         # 127.0.0.1:5432 -> the server, until Ctrl+C
pskit resources onprem tunnel orders-db --local-port 15432
pskit resources onprem tunnel cache --remote-port 8082          # a web UI port instead
```

The command prints the service's variables rewritten for `127.0.0.1`. A service on this machine needs no tunnel.

## Deploy methods for on-prem functions

The on-prem functions' host is deployed with `provider.options.deploy.method`. pskit's software installs and
services above prepare a server for these methods:

| Method | Where the host runs | Needs on the server |
|---|---|---|
| `local` | this machine | the project's Python / Node.js here |
| `ssh` (alias `scp`) | a server over SSH | Python (`python` install above), Node.js for Node functions |
| `docker` | a container, here or on a server | Docker (`docker` install above) |

The full description of each method and of clusters is in [deployment](../deployment/README.md).

## See also

- [Saved servers](servers.md)
- [On-prem services](services/README.md)
- [On-prem overview](README.md)
- [Deployment](../deployment/README.md)
- [Full reference: one-click services](../resource-guides/onprem/services.md)
