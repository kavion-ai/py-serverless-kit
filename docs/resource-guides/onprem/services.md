# One-click services for on-premises functions

pskit can **create** the queue, stream, bucket, database or cache your on-premises functions use, then add it to
`pskit.yml` as a resource and, for queues, streams and buckets, as a trigger. It starts the service as a Docker container
on this machine or on any server you can reach with SSH. That can be the server your functions run on or a different
one. It can also install Python or Docker on an SSH server.

| Service | Use as | Driver in `pskit.yml` | Default port | Backup | Web UI |
|---|---|---|---|---|---|
| Redis | queue, stream, cache | `redis` (list), `redis_stream` (consumer group) | 6379 | RDB snapshot | Redis Commander (companion) |
| Valkey | queue, stream, cache | `redis`, `redis_stream` | 6379 | RDB snapshot | Redis Commander (companion) |
| KeyDB | queue, stream, cache | `redis`, `redis_stream` | 6379 | RDB snapshot | Redis Commander (companion) |
| Dragonfly | queue, stream, cache (password only) | `redis`, `redis_stream` | 6379 | snapshot (`.tar.gz`) | Redis Commander (companion) |
| Apache Kafka (KRaft) | queue | `custom`: `pskit_drivers.kafka_queue:KafkaQueue` | 9092 | data directory | Kafka UI (companion) |
| LavinMQ | queue | `custom`: `pskit_drivers.rabbitmq_queue:RabbitQueue` (AMQP) | 5672 | definitions | Management UI (15672) |
| Azurite | queue, storage | `azure_queue` (10001), `azure_blob` (10000), own account and key | 10000 | data directory | Azure Storage Explorer (desktop) |
| LocalStack | queue, storage | `sqs`, `s3` (one port) | 4566 | data directory | status page |
| fake-gcs-server | storage | `gcs` (emulator) | 4443 | | |
| RustFS | storage | `s3` with endpoint and keys | 9000 | data directory | Console (9001) |
| Kafka (Redpanda, one node) | queue | `custom`: `pskit_drivers.kafka_queue:KafkaQueue` (adds `kafka-python`) | 9092 | data directory (`.tar.gz`) | Kafka UI (companion) |
| NATS JetStream | queue | `custom`: `pskit_drivers.nats_queue:NatsQueue` (adds `nats-py`) | 4222 (monitor 8222) | data directory | monitoring (8222) |
| RabbitMQ | queue | `custom`: `pskit_drivers.rabbitmq_queue:RabbitQueue` (adds `pika`) | 5672 (UI 15672) | definitions (queues, users) | Management UI (15672) |
| ElasticMQ (SQS API) | queue | `sqs` with `endpoint` | 9324 (UI 9325) | none (in memory) | queue browser (9325) |
| MinIO | storage | `minio` | 9000 (console 9001) | data directory | Console (9001) |
| PostgreSQL | database | connection values | 5432 | `pg_dumpall` (`.sql`) | Adminer (companion) |
| MySQL / MariaDB | database | connection values | 3306 | `mysqldump` / `mariadb-dump` (`.sql`) | Adminer (companion) |
| MongoDB | database | connection values | 27017 | `mongodump --archive` | Mongo Express (companion) |
| Memcached | cache | connection values | 11211 | none | |
| Mailpit (SMTP) | custom | connection values | 1025 (web 8025) | none | Mailbox (8025) |
| SMTP server (Node.js) | smtp: runs functions with each mail | `smtp` trigger ([guide](../../smtp/README.md)) | 25 | none | DNS guide |
| Python 3, Docker | runtime on an SSH server | — | — | — | |
| LocalEmu | queue, storage, secrets | `sqs`, `s3`, Secrets Manager (one port) | 4566 | none | Dashboard (`/_localemu/dashboard`) and pskit's browser |
| AWS Secrets Manager compatible (Python / Node.js) | secrets (`aws` driver) | `get_secret()`, boto3, AWS SDKs with the endpoint; SigV4 with the user / password | 4584 | data directory | Secrets console (`/ui/`) and pskit's browser |
| Amazon S3 compatible (Python / Node.js) | storage | `s3` with endpoint and keys; boto3, AWS SDKs, the AWS CLI; SigV4 with the user / password | 9000 | data directory (`.tar.gz`) | S3 console (`/ui/`) and pskit's browser |
| Infisical | secrets (`infisical` driver) | `get_secret()` with a machine identity | 8080 | — | Infisical web UI (own sign-up) |
| Grafana | dashboards | URL, admin user and password | 3000 | data directory | Grafana |
| Prometheus | metrics | URL | 9090 | — | Prometheus UI |
| Uptime Kuma | uptime monitoring | URL | 3001 | data directory | own sign-up |
| Jaeger | tracing (OTLP 4317 / 4318) | URL, OTLP endpoints | 16686 | — | Jaeger UI |
| Keycloak | identity, SSO, OIDC | URL, issuer, admin login | 8080 | — | Admin console (`/admin/`) |
| Meilisearch, Typesense | search | URL, API key (the password) | 7700, 8108 | — | Meilisearch search preview |
| Qdrant | vector database | URL, API key | 6333 (gRPC 6334) | — | Dashboard (`/dashboard`) |
| ClickHouse | analytics database | URL, user, password | 8123 (native 9000) | — | SQL playground (`/play`) |
| Neo4j | graph database | `bolt://` URL, user `neo4j` | 7687 (browser 7474) | — | Neo4j Browser |
| Eclipse Mosquitto | MQTT broker | `mqtt://` URL | 1883 | — | |
| n8n | workflow automation | URL | 5678 | data directory | own sign-up |
| Portainer | Docker UI for the server | URL | 9000 (9443) | — | own sign-up |
| Gitea | Git hosting | URL | 3000 | data directory | install page |
| Nginx Proxy Manager | reverse proxy, Let's Encrypt | URL | 81 (80, 443) | — | Admin UI |

Infisical starts with its own PostgreSQL and Redis (*sidecar* containers on a private Docker network, removed with it).
Its `ENCRYPTION_KEY` and `AUTH_SECRET` are generated once and kept in the env file, so creating it again reuses them.
Services marked *own sign-up* ask you to create their admin account on the first visit, so pskit sets no password.

## pskit's own browsers (when the native UI is missing)

Some services ship without a usable web UI. OpenBao's release images say *"OpenBao UI is not available in this
binary"*, and MinIO's community console no longer has the admin pages. For these, **Browse** on the service's row
opens pskit's UI in the studio:

| Service | Browser | What you can do |
|---|---|---|
| MinIO, RustFS, LocalStack, LocalEmu, Amazon S3 compatible | **Buckets (S3)** | Create and delete buckets (with every object and old version); folders and breadcrumbs; filter by name; 25 to 1000 objects per page with next / previous; upload several files (up to 64 MB each); download; info (size, type, ETag, metadata); old versions (list, download); rename / move and copy; share links valid 1 hour, 1 day or 7 days (S3 presigned URLs); bucket versioning on / off; bucket policy (private, public read, or your JSON) |
| fake-gcs-server | **Buckets (Cloud Storage)** | The same, without versioning, policies and signed links |
| OpenBao | **Secrets** | Folders, open a secret (values hidden until *Show values*), copy a value, versions (pick an old one), add / edit (each save is a new version), delete |
| LocalStack, LocalEmu, AWS Secrets Manager compatible | **Secrets (Secrets Manager)** | List with paging, open, add / edit, delete |

The studio talks to the service from your machine. When its port is closed by a firewall, it goes over the server's
SSH login instead (`127.0.0.1:<port>` on the server). Credentials stay in `.pskit/onprem-services.json` and never
reach the browser page.

Every service and role above was created with Docker and driven through its pskit driver (publish, receive, settle;
put, list, get) during development. Queues and buckets on Azurite, LocalStack, fake-gcs-server and RustFS are created
on first use by the driver (`create_queue` / `create_bucket`), from the host's side, so a firewall between your laptop
and the server doesn't matter and an emulator restart is survived. Extra ports (consoles, Azurite's queue port) move
with the main port: a second RabbitMQ on port 5682 gets its UI on 15682.

## In the studio

1. **Resources → + On-prem service** (or *On-prem services → + Create service*, or *Add resource → Create a <type> on
   premises*).
2. Pick a service. For Redis / Valkey choose **Queue** (list), **Stream** (consumer group) or **Cache**.
3. **Where**: *This machine*, or *SSH server* with host, user, port, *Log in with* (key file, SSH agent / default
   key, or password, see [SSH login](#ssh-login-key-agent-or-password)) and *use sudo*. When
   `provider.options.deploy` already targets a server, it is filled in.
4. Tick the functions to **trigger** (queues, streams and buckets). Each gets `queue: {resource: <key>}` or
   `storage: {resource: <key>}`.
5. **Create**. The output streams below the form. When it finishes, the resource, `provider.options.env_file` and the
   triggers are added to the draft; review them and **Save**.
6. **Deploy**, then test with **Resources → Test** or `pskit resources send <key>`.

Each row then offers **Details** (container state, health, endpoint, credentials with *Show values*, the container
log), **Backup**, **Add to pskit.yml** (if you removed it from the file) and **Remove** (keep or delete the data volume;
the resource and its triggers are taken out of the draft).

## Credentials and network

The create form has a **Security** box (CLI flags in brackets):

| Setting | Default | Notes |
|---|---|---|
| User (`--user`) | `pskit`; `default` for Redis / Valkey | Redis / Valkey with another user get an ACL user and the `default` user is disabled |
| Password (`--password`, `--password-env VAR`) | 24 random characters | 8-128 characters of letters, digits and `!#%*+,.:=?@^_~-`; URLs are percent-encoded for you |
| Listen on (`--bind`) | `127.0.0.1` here, `0.0.0.0` on an SSH server | `127.0.0.1` lets only programs on that machine connect |

Kafka (Redpanda), ElasticMQ, Memcached and Mailpit run **without authentication** in this setup; the form says so and
the CLI refuses a password for them. Keep them on `127.0.0.1` or a private network.

```bash
export ORDERS_DB_PASSWORD='Str0ng.pass#1'
pskit resources onprem create orders-db --service postgres --user orders_app --password-env ORDERS_DB_PASSWORD --save
pskit resources onprem create cache --service redis --role cache --user app --password-env CACHE_PASSWORD --bind 127.0.0.1
```

To change a password later: *Remove → Stop service, keep data*, create it again with the same key and the new
password, then redeploy.

## Web UIs

Services with a built-in UI (RabbitMQ, LavinMQ, MinIO, RustFS, ElasticMQ, NATS monitoring, Mailpit, pskit's S3 and
Secrets Manager servers) show its URL and
login in *How to use* and *Details*. For the others pskit starts a **companion** UI next to the service, on a private
Docker network with it, listening on the same interface as the service:

| Service | Companion | Default port | Login |
|---|---|---|---|
| PostgreSQL, MySQL, MariaDB | Adminer | 8089 | the database user and password (server filled in) |
| Redis, Valkey, KeyDB, Dragonfly | Redis Commander | 8082 | `admin` + a generated password (`PSKIT_<KEY>_GUI_PASSWORD`) |
| Kafka (Redpanda), Apache Kafka | Kafka UI | 8088 | `admin` + a generated password (sign-in page `/auth`) |
| MongoDB | Mongo Express | 8081 | the MongoDB user and password |

A second UI of the same kind on one server takes the next free port (8083, 8084, ...); *Details* shows the real one.

Start it with *Also start the web UI* when creating, *Details > Add web UI*, or the CLI:

```bash
pskit resources onprem create orders-db --service postgres --gui --save
pskit resources onprem gui cache                 # add / show the web UI of an existing service
pskit resources onprem gui cache --remove
pskit resources onprem tunnel orders-db --remote-port 8089     # firewalled: browse http://127.0.0.1:8089
```

Azurite has no web UI: attach **Azure Storage Explorer** (desktop) with the connection string from the env file.

### With or without a password

The create form's **Web UI login** (and *Details > Add web UI*) chooses how the companion UI signs in:

| Choice | Redis Commander, Kafka UI | Mongo Express | Adminer |
|---|---|---|---|
| **With password** (default) | user `admin`, a generated password, or yours | the MongoDB login, or `<user>` + yours | the database login (always) |
| **Without password** | open (`HTTP_USER` unset, `AUTH_TYPE=DISABLED`) | open (`ME_CONFIG_BASICAUTH=false`) | not offered |

Your own or a generated password goes to the env file as `PSKIT_<KEY>_GUI_PASSWORD` and shows in *How to use*.

```bash
export CACHE_UI_PASSWORD='Ui.pass-2026'
pskit resources onprem create cache --service redis --role cache --gui --gui-password-env CACHE_UI_PASSWORD
pskit resources onprem create cache --service redis --role cache --gui --gui-login none --bind 127.0.0.1
pskit resources onprem gui cache --login none            # switch an existing UI (it is recreated)
```

Without a password, anyone who reaches the port can use the UI, and the UI holds the service's credentials. Use it on
`127.0.0.1`, on a private network, with the port open only to your IP, or keep the port closed and use the tunnel.
pskit prints a warning when a UI without login listens on `0.0.0.0`.

Built-in UIs keep their own sign-in: RabbitMQ, LavinMQ, MinIO and RustFS use the service's user and password;
ElasticMQ, NATS monitoring and Mailpit have none.

### The UI does not open

Run the check. It changes nothing, and tests every UI of the service, from the server itself (over SSH) and from your
machine:

```bash
pskit resources onprem gui jobs --check          # studio: Details > Check web UI
```

```text
== Queue browser: http://13.72.87.80:9325/
  container pskit-shop-jobs: running
  published: 0.0.0.0:9325 (container port 9325)
  on the server (http://127.0.0.1:9325/): http 200
  from this machine (http://13.72.87.80:9325/): timeout
Queue browser: no answer from outside: a firewall drops the connection
  - Azure: add an inbound rule for TCP 9325 to the network security group, e.g. `az vm open-port -g my-rg -n my-vm --port 9325 ...`
  - Azure applies EVERY NSG on the path: one on the subnet and one on the network interface both need the rule ...
  - Works right away without opening any port: `pskit resources onprem tunnel jobs --remote-port 9325`
```

| Verdict | Meaning and fix |
|---|---|
| the container is not running | `pskit resources onprem logs <key>`; start the UI again with `gui <key>` |
| container port N is not published | the container was made without that port (older pskit): remove keeping the data and create again |
| does not answer on the server itself | the app is still starting or failed: its logs |
| published on 127.0.0.1 only | created with *Listen on: this machine*: use the tunnel, or recreate with `0.0.0.0` |
| a firewall drops the connection (timeout) | open the **UI's port** (not only the service's) in the cloud firewall; see below |
| the connection was refused | a host firewall (ufw / firewalld) rejects it, or the address is not this server |
| reachable | open the URL with `http://` (not `https://`) |

"I allowed inbound and it still does not open" is almost always one of these:

- The rule opens the service's port (9324, 6379, ...) but not the **UI's** port (9325, 8082, 15672, ...). The check
  prints the exact port.
- **Azure** applies every network security group on the path: the one on the **subnet** and the one on the **network
  interface** both need the rule (VM > Networking shows both). The rule's source must include your public IP (use
  *Any* to test), and its priority number must be lower than any Deny rule's. The check reads the resource group and
  VM name from the instance metadata and prints the `az vm open-port` command.
- **AWS**: the instance's security group, and the subnet's network ACL. **GCP**: a firewall rule, and the instance's
  network tags if the rule uses target tags.
- ufw or firewalld on the server (the check reports them); Docker-published ports usually bypass ufw.
- Your own network (company VPN, proxy) blocks outgoing non-web ports: try from another network, or
  `Test-NetConnection <host> -Port <port>` (PowerShell) / `nc -vz <host> <port>`.
- The address in the links is a private IP: set *Advanced > Address* to the public one, or use the tunnel.

The tunnel always works over SSH (port 22), with no firewall change:

```bash
pskit resources onprem tunnel jobs --remote-port 9325      # then browse http://127.0.0.1:9325
```

### Try the web UIs in local Docker first

Everything works the same on your own machine with Docker Desktop (or Docker Engine), with no server and no
firewall. Pick *Where: This machine* in the studio, or `--local`:

```bash
pskit resources onprem create cache --service redis --role cache --local --gui                      # Redis Commander
pskit resources onprem create docs  --service mongodb --local --gui --gui-login none                # Mongo Express, open
pskit resources onprem create events --service kafka --local --gui                                  # Kafka UI
pskit resources onprem create jobs  --service elasticmq --local                                     # built-in queue browser
pskit resources onprem create mq    --service rabbitmq --local                                      # management UI
pskit resources onprem gui cache                  # prints each URL and login
pskit resources onprem gui cache --check          # container, port and HTTP answer
pskit resources onprem usage cache                # the env file password, the URL, code examples
```

Then open the printed links, for example:

| UI | URL | Login |
|---|---|---|
| Redis Commander | http://127.0.0.1:8082 | `admin` / `PSKIT_CACHE_GUI_PASSWORD` in `.env.onprem` |
| Mongo Express (no login) | http://127.0.0.1:8081 | none |
| Kafka UI | http://127.0.0.1:8088/auth | `admin` / `PSKIT_EVENTS_GUI_PASSWORD` |
| ElasticMQ queue browser | http://127.0.0.1:9325 | none |
| RabbitMQ management | http://127.0.0.1:15672 | the service user / `PSKIT_MQ_PASSWORD` |

Local services listen on `127.0.0.1`, so only your machine can open them. `docker ps` lists them (named
`pskit-<project>-<key>` and `...-ui`). Clean up with *Remove* (or `pskit resources onprem remove <key> --delete-data`).

## Databases: one server, or a primary with read replicas

A database (PostgreSQL, MySQL, MariaDB, MongoDB) is created in one of two shapes. The create form asks under
**Scaling**:

- **Single server**: one container on this machine or a server. To scale it up, give that server more CPU and
  memory (vertical scaling). Nothing else changes.
- **Primary + read replicas** (horizontal scaling): the **primary** takes every write, each **read replica** on
  another server keeps a copy and answers reads, and an optional **load balancer** gives the functions one address
  that sends writes to the primary and reads to the replicas. Add replicas later as reads grow.

You only pick the servers: which one writes (the primary), which ones read (the replicas) and which one runs the load
balancer. Save them first (**Servers**, below). pskit installs Docker where it is missing and sets up replication for
each engine:

| Engine | Replication | *Synchronous* means | Load balancer (one address) |
|---|---|---|---|
| PostgreSQL | streaming replication (WAL), each replica starts from `pg_basebackup` | `synchronous_standby_names = 'ANY 1 (*)'`: a commit waits until one replica has it on disk | pgpool-II, port 6432 |
| MySQL | GTID replication; a replica copies the databases, then follows | semi-synchronous: a commit waits for one replica (async again after 10 s without one) | ProxySQL, port 6033 |
| MariaDB | GTID replication, as MySQL | built-in semi-synchronous, as MySQL | ProxySQL, port 6033 |
| MongoDB | replica set (`rs_<key>`), members share a generated key file | write concern `w: majority` | none: the driver routes from one replica set URL |

**Asynchronous** (default) is the fastest: the primary commits at once and replicas follow a few milliseconds behind,
so a crash of the primary can lose the last writes. **Synchronous** loses no committed write, at the cost of a
round trip to a replica per commit. PostgreSQL waits while no replica is connected, so keep at least two replicas
with *sync*.

The load balancer sends writes, transactions and `SELECT ... FOR UPDATE` to the primary and plain reads to the
replicas, and falls back to the primary only when no replica is up. Without a load balancer, the functions'
`URL` is the primary and the replicas are listed in `READ_URLS`.

The form draws the result as you pick (functions → load balancer → primary → replicas, solid lines for sync,
moving dashes for async). **Details** shows the same picture with each member's state, every replica's lag, what the
primary reports (`pg_stat_replication`, `SHOW REPLICAS`, `rs.status()`), and **+ Add read replica** / **Remove**.

```bash
# primary db1, replicas db2 + db3, pgpool-II on lb1, synchronous
pskit resources onprem create orders-db --service postgres --primary db1 --replica db2 --replica db3 \
    --balancer lb1 --sync sync --save
pskit resources onprem create users-db --service mongodb --primary db1 --replica db2 --replica db3   # replica set
pskit resources onprem create try-db --service mysql --primary local --replica local --replica local \
    --balancer local                     # everything on this machine (ports 3306, 3307, 3308; ProxySQL 6033)

pskit resources onprem replicas list orders-db     # members, state, lag
pskit resources onprem replicas add orders-db db4  # copies the data, follows the primary, joins the load balancer
pskit resources onprem replicas remove orders-db r1 --delete-data
```

Handlers do not change. In `.env.onprem`:

| Variable | Points at |
|---|---|
| `PSKIT_<KEY>_URL` | the load balancer, else the primary (MongoDB: the replica set URL with `readPreference=secondaryPreferred`) |
| `PSKIT_<KEY>_WRITE_URL` | the primary, directly |
| `PSKIT_<KEY>_READ_URLS` | the replicas, comma separated |

Good to know:

- One member per server: a replica on the primary's server protects nothing. The load balancer may share a server
  with a member (its port differs).
- Replication uses its own user (`pskit_repl`) and generated password. The password and MongoDB's key file stay in
  `.pskit/onprem-services.json` and are never shown in the studio or the job log.
- The job prints the firewall rules: replicas → primary on the database port, the load balancer → every member,
  your function servers → the load balancer (or every member without one). See
  [network rules](../../onprem-network.md).
- *This machine (try it)* runs every member here on its own port, on a private Docker network. Use it to see
  replication work. MongoDB needs servers, because its members must be reached at the same address by the functions
  and by each other.
- pgpool-II knows the database user pskit created. Users you add later connect to the members directly, or are added
  to pgpool (`PGPOOL_POSTGRES_CUSTOM_USERS`).
- If the primary fails: MongoDB elects a new primary on its own. For PostgreSQL and MySQL / MariaDB, the replicas keep
  serving reads. Promoting one is a manual step today (`pg_ctl promote` / `STOP REPLICA; SET GLOBAL read_only=OFF`).
- Console, Terminal, Backup and the web UI work on the primary.

## Servers: several machines

Save each machine once under **On-prem services → Servers → + Add server** (name, host, user, port, *Log in with*,
sudo), or with the CLI. Every place that asks *where* then offers it: the create form's **Server** list, **Deploy →
Machine**, the shell and the terminal.

```bash
pskit resources onprem servers add edge1 --ssh ubuntu@10.0.0.5 --pem ~/.ssh/edge1.pem
pskit resources onprem servers add db-box --ssh azureuser@13.72.87.80              # SSH agent / default key
pskit resources onprem servers add lab --ssh root@192.168.1.20 --ssh-password-env LAB_PW --sudo
pskit resources onprem servers list
pskit resources onprem servers test edge1        # OS, CPU, memory, disk, Docker access, sudo, Python / Node / nginx
pskit resources onprem servers check             # ✓ / ✗: which servers answer on their SSH port (no login)
pskit resources onprem servers top edge1 --watch 5   # live CPU, memory and disk use
pskit resources onprem servers usage edge1       # where it is used: deploy, function groups, clusters, LBs, services
pskit resources onprem create cache --service redis --server edge1 --save
pskit resources onprem servers remove lab        # services there keep running
```

They live in `.pskit/onprem-servers.json` (connection details only; a typed password goes to `.pskit/ssh/`,
owner-only). Services created on a server keep a copy of its connection, so editing the server later does not move them.

### Where a server is used, and how the servers connect

The **Used in** column of *Servers* says, for each server, every place that names it, with the functions behind
each: the deploy target in `pskit.yml`, the stage last deployed there, a function group
(`provider.options.placement`), a cluster (master or joined server) and its load balancer, a named load balancer, a
service or a member of a replicated database (primary, read replica, its load balancer), and software pskit
installed. A server nothing names says *not used anywhere*; **Forget** shows the same list before it asks. CLI:
`pskit resources onprem servers usage [NAME] [--json]`.

The **Network map** page draws every server and the connections it has to accept (inbound) and open (outbound):
this machine (SSH, logs, tests), the function callers, the cluster ports, load balancer → servers, replicas → primary,
functions → services, downloads from the internet. Solid lines are required, dashed ones are needed for a feature,
dotted ones are optional (pskit falls back to an SSH tunnel). Click a server for its inbound and outbound ports, why
each is needed, and where it is used. It reads the same rules as `pskit firewall`, from local files only.

### Deploy the functions to a chosen machine

```bash
pskit deploy --server edge1          # also package, plan, remove, info
```

or permanently, per stage:

```yaml
provider:
  name: onprem
  options:
    deploy: {server: edge1, path: /opt/shop}          # method defaults to ssh; docker works too
stages:
  edge2:
    provider: {options: {deploy: {server: edge2, path: /opt/shop}}}
```

The saved server's host, user, port and login replace those in `options.deploy`; `method`, `path`, `python`,
`install` and the rest stay. In the studio, **Deploy → Machine** picks one for that run.

Logs, triggers and executions follow the same choice: **Logs → Server** in the studio, or `--server` on the CLI
(`pskit logs --server edge2`, `pskit trigger --server edge2 -f api`, `pskit resources send --server edge2 jobs`). Without
it they read the host of the last deploy. The host's port (default 8080) must be reachable from this machine. Use one stage per machine:
each stage has its own Terraform state, so two machines never overwrite each other's deployment.

## Install software on a server

The catalog's *Install on a server* groups install with the server's package manager (apt, dnf, yum or apk), over SSH:

| Software | Versions | Notes |
|---|---|---|
| **Python 3** | `system` (default), 3.13, 3.12, 3.11, 3.10, 3.9, 3.14 | `system`: the distribution's python3 with venv and pip. A version: that exact CPython (standalone build through uv, any distribution) in `/opt/pskit-python`, linked as `/usr/local/bin/python3.X`; the host then runs with `python: system` and `runtime: python3.X` |
| Docker | distribution | installed and started |
| **Node.js** | 22 (default), 24, 20, 18 | NodeSource packages with npm (Alpine: its own version) |
| Java (OpenJDK) | 21, 17 | headless runtime |
| Go | 1.23.4 (any `1.x.y`) | official toolchain in `/usr/local/go` |
| **nginx** | distribution | enabled and started; put a reverse proxy to the pskit host in `/etc/nginx/conf.d/` |
| Caddy | 2.8.4 | the `caddy` binary (automatic HTTPS) |
| Certbot | distribution | with the nginx plugin where available |
| PM2 | npm | needs Node.js first |
| Git, basic tools | distribution | curl, wget, unzip, jq, htop, tmux, netcat |

```bash
pskit resources onprem create py312 --service python --version 3.12 --server edge1
pskit resources onprem create node --service nodejs --version 20 --server edge1
pskit resources onprem create web --service nginx --server edge1
```

Studio: *Servers → Install / create* opens the catalog with that server chosen. Each install is listed with the
services; *Details* runs its version check. pskit never uninstalls software (*Remove* only forgets it).

## Console and terminal

Services without a web UI (and those with one) have a **Console**: type a command, see the output.

| Service | Console runs | Try |
|---|---|---|
| Redis, Valkey, KeyDB, Dragonfly | `redis-cli` with the service's login | `INFO server`, `LLEN jobs`, `XINFO STREAM jobs` |
| PostgreSQL / MySQL / MariaDB | `psql` / `mysql` / `mariadb` on the service's database | `\dt`, `SELECT now();` |
| MongoDB | `mongosh` | `db.getCollectionNames()` |
| Kafka (Redpanda) / Apache Kafka | `rpk` / `kafka-*.sh` | `topic list`, `kafka-topics.sh --list` |
| RabbitMQ / LavinMQ | `rabbitmqctl` / `lavinmqctl` | `list_queues name messages` |
| NATS | `nats` (nats-box helper) | `stream ls` |
| MinIO / RustFS / Amazon S3 compatible | `mc` / `aws s3` | `ls local`, `s3 ls` |
| ElasticMQ / LocalStack | `aws sqs` / `awslocal` | `sqs list-queues`, `secretsmanager list-secrets` |
| OpenBao | `bao` | `kv list secret`, `kv put secret/api-key value=abc` |
| Memcached, Mailpit, fake-gcs-server | text protocol / HTTP API | `stats`, `/api/v1/messages` |

*Shell in the container* runs any line with `sh -c` inside the service's container. Each line runs on its own (no
state between lines), on this machine or over SSH; credentials are hidden in the output. When the image has no client
(Dragonfly, NATS, ElasticMQ, RustFS, Memcached), a small helper container joins the service's private network for that
command. Servers have the same **Shell** under *Servers*.

For interactive work (`redis-cli MONITOR`, `psql` sessions, `vim`, `htop`) open a **Terminal**: a full terminal in the
browser, embedded in the studio. It is ttyd in Docker on this machine, listening on `127.0.0.1` only behind a random
secret URL; the first start builds a small image (`pskit-terminal:1`, ttyd + OpenSSH + sshpass + docker CLI). Servers
get an SSH session with their saved login; services get their client (or `sh`) through `docker exec`.

```bash
pskit resources onprem console cache                      # interactive redis-cli in this terminal
pskit resources onprem console orders-db "SELECT count(*) FROM orders;"
pskit resources onprem shell edge1                        # ssh with the saved login
pskit resources onprem shell edge1 "docker ps"
pskit resources onprem terminal --server edge1            # browser terminal
pskit resources onprem terminal cache                     # redis-cli in the browser
pskit resources onprem terminal --list
pskit resources onprem terminal --stop all
```

## Secret managers

**OpenBao** (Vault API) and **LocalStack** (*Use as: Secret manager*: AWS Secrets Manager and SSM) are one click away,
and handlers read them with `get_secret("name")` on every provider. See [secrets.md](secrets.md).

## SSH login: key, agent or password

The *SSH server* target (and `provider.options.deploy` for the functions) logs in one of three ways:

| *Log in with* | Studio | CLI | `pskit.yml` (`provider.options.deploy`) |
|---|---|---|---|
| **Key file** | path of the `.pem` / private key | `--pem ~/.ssh/server.pem` | `pem: ~/.ssh/server.pem` |
| **SSH agent / default key** | nothing to fill in | leave `--pem` out | leave `pem` out, or `auth: agent` |
| **Password** | the password (saved in `.pskit/ssh/`, owner-only, out of git) | `--ssh-password-env VAR` or `--ssh-password-file FILE` | `password_file: ~/.ssh/server.pass`, or `auth: password` with `SSHPASS` set |

*SSH agent / default key* is what `ssh user@host` does in a terminal: the agent, `~/.ssh/id_ed25519` /
`id_rsa`, and `~/.ssh/config` (`Host` aliases, `IdentityFile`, jump hosts).

Password logins go through **sshpass**, so the password never appears on a command line or in the state. Install it
on the machine that runs pskit: `sudo apt install sshpass`, `sudo dnf install sshpass`, or
`brew install hudochenkov/sshpass/sshpass`. The server must allow `PasswordAuthentication` (many cloud images allow
keys only).

**On Windows** (no sshpass), or to stop typing passwords: install a key once. pskit creates
`~/.ssh/pskit_ed25519`, logs in with the password one time (ssh asks for it in the terminal), adds the key to
`authorized_keys`, and checks that the key works:

```bash
pskit resources onprem ssh-key azureuser@13.72.87.80          # [:2222] for another port
pskit resources onprem create jobs --service elasticmq --ssh azureuser@13.72.87.80 --pem ~/.ssh/pskit_ed25519
```

```yaml
provider:
  name: onprem
  options:
    deploy:
      method: ssh
      host: 13.72.87.80
      user: azureuser
      pem: ~/.ssh/pskit_ed25519            # or: password_file: ~/.ssh/server.pass  (sshpass)
```

## Use it from any program

Each service row has **How to use**. It shows the address, user, the variable names (values with *Show passwords*),
and Python and Node.js code that connects **directly** to the service from any script, web app or cron job, with the
library to install and terminal commands:

| Service | Python | Node.js | Terminal |
|---|---|---|---|
| Redis list (queue) | `redis`: `LPUSH` the pskit envelope, `LRANGE` to look, `BRPOP` to take | `ioredis` | `redis-cli` |
| Redis / Valkey stream | `redis`: `XADD`, `XRANGE`, your own consumer group with `XREADGROUP` / `XACK` | `ioredis` | `redis-cli XADD / XRANGE` |
| Kafka | `kafka-python` producer / consumer (your own `group_id`) | `kafkajs` | `rpk` in the container |
| NATS JetStream | `nats-py`: `js.publish`, your own durable pull consumer | `nats` | `nats` CLI |
| RabbitMQ | `pika` | `amqplib` | management UI |
| ElasticMQ | `boto3` SQS with `endpoint_url` | `@aws-sdk/client-sqs` | `aws sqs --endpoint-url` |
| MinIO | `boto3` S3 with `endpoint_url` | `@aws-sdk/client-s3` | `aws s3 --endpoint-url`, `mc` |
| PostgreSQL / MySQL / MongoDB | `psycopg` / `pymysql` / `pymongo` | `pg` / `mysql2` / `mongodb` | `psql` / `mysql` / `mongosh` |
| Redis cache / Memcached | `redis` / `pymemcache` | `ioredis` / `memjs` | `redis-cli` |
| Mailpit | `smtplib` | `nodemailer` | web UI |

These scripts were run against real containers. Data written directly uses the format the pskit driver reads, so the
functions' triggers receive it. Reading directly next to a pskit trigger competes with it; the code uses separate
consumer groups where the service has them.

From the terminal: `pskit resources onprem usage <key> [--reveal]`.

When the service's port is closed to your machine (a cloud VM's security group), connecting directly times out. Either
forward it with `pskit resources onprem tunnel <key>` (scripts then use `127.0.0.1`), or skip the port entirely with the
[pskit client](../../client.md), which goes through the host.

## From the command line

```bash
pskit resources onprem catalog
pskit resources onprem create jobs --service redis --attach worker --save
pskit resources onprem create events --service kafka --attach worker --save
pskit resources onprem create tasks --service nats --ssh ubuntu@10.0.0.7 --pem ~/.ssh/mq.pem --sudo --save
pskit resources onprem create stream --service valkey --role stream --attach worker --save
pskit resources onprem create orders-db --service postgres --ssh ubuntu@10.0.0.5 --pem key.pem --save
pskit resources onprem create py --service python --ssh ubuntu@10.0.0.5 --pem key.pem

pskit resources onprem list
pskit resources onprem status jobs [--reveal]
pskit resources onprem logs jobs
pskit resources onprem backup orders-db          # -> .pskit/backups/orders-db-<time>.sql
pskit resources onprem remove jobs [--delete-data] [--save]
```

Without `--save` the command prints the YAML to paste. `--save` rewrites `pskit.yml` (comments are not kept).

## What gets written

```yaml
provider:
  name: onprem
  options:
    env_file: .env.onprem            # added once; shipped to the host, never into Terraform state
resources:
  jobs:
    type: queue
    external: true                   # pskit's deploy does not create or delete it
    options:
      driver: redis
      url_env: PSKIT_JOBS_URL        # read from .env.onprem on the host
      key: jobs
functions:
  worker:
    events:
      - queue: {resource: jobs}
```

- **Passwords** are generated and written to the env file (`.env.onprem` unless `provider.options.env_file` names
  another), as `PSKIT_<KEY>_URL`, `PSKIT_<KEY>_PASSWORD`, `..._ACCESS_KEY` / `..._SECRET_KEY`. `pskit deploy` copies
  that file next to the host as `host.env`, and the host loads it at start. The file is added to `.gitignore` when the
  project has one. Handlers read the same variables: `ctx.env[resource("orders-db")["password_env"]]`.
- **Driver classes** for Kafka, NATS and RabbitMQ are copied once into `pskit_drivers/` under `package.source`, and the
  client library is appended to `requirements.txt` (on premises it **is** installed). Edit them freely; pskit never
  overwrites them.
- **What was created** is kept in `.pskit/onprem-services.json`, credentials included: keep `.pskit/` out of git.
- When the main provider is not `onprem`, everything goes under `providers.onprem:` so the other clouds are unaffected.

## Existing cloud code

Code written for AWS, Azure or Google Cloud SDKs works against these services unchanged except for the endpoint:
S3 code against RustFS / MinIO / LocalStack, SQS code against LocalStack / ElasticMQ, Azure SDK code against Azurite,
`google-cloud-storage` against fake-gcs-server, AMQP code against RabbitMQ / LavinMQ, Kafka code against either
Kafka. The host itself also speaks the Lambda Invoke and SQS APIs. Details: [compatibility](../compatibility.md).

## Same server or a different one

The address in the connection is the SSH host (or `127.0.0.1` on this machine). Change it under *Advanced → Address
functions use* (`--address`) when the functions reach the server by another name or a private IP.

| Functions run | Service created | Works because |
|---|---|---|
| on this machine (`deploy.method: local`) | on this machine | both use `127.0.0.1` |
| on server A (`method: ssh`) | on server A | published on `0.0.0.0`, reached as `A` |
| on server A | on server B | published on `0.0.0.0` of B; open the port from A to B in the firewall |
| in a container (`method: docker`) | on this machine | use *Address* `host.docker.internal` (Docker Desktop) or the host's LAN IP |

### When the functions move

Deploying the functions to another server or cluster (for example after their old server was removed) keeps their
events working. Before each `pskit deploy`, pskit checks every service the functions use:

- **Address**: a service on a cluster server is reached at its cluster address from that cluster and at the server's
  own address from anywhere else. When the functions moved in or out of the cluster, pskit changes the address in the
  env file, and the deploy ships the new one. An *Address* you typed in yourself is kept.
- **SMTP server**: it sends each mail to the functions, so after the deploy pskit restarts its container with their
  new URL (see [the SMTP guide](../../smtp/README.md)).
- **Firewall**: the deploy prints the rules the new function servers need to reach each service.
- **Cannot be fixed by pskit** (printed as a warning, the deploy goes on): the service's server was removed (create the
  service again with the same key), the service runs on this machine or listens on `127.0.0.1` only while the
  functions run elsewhere (create it again on a server, or with bind `0.0.0.0`), or its container has the address built in
  (Kafka, Redpanda, fake-gcs: create it again with the same key; the data stays).

With `placement`, the check uses the default group's server; the other groups reach a service the same way.

A queue can also live in **another pskit host's built-in queue**, with no broker at all. On the host that consumes it:

```yaml
resources:
  orders:
    type: queue
    external: true
    options:
      driver: pskit_host
      endpoint: http://10.0.0.6:8080          # the other host
      queue: orders                            # its queue name there
      token_env: OTHER_HOST_ADMIN_TOKEN        # its provider.options.admin_token, if set
```

Messages are leased through that host's admin API (`/__pskit/queues/<name>/lease|ack|nack`), so a crash on either
side loses nothing.

## See what is inside

On a deployed on-prem host, **Resources → Data** on a queue, topic or bucket lists what it holds, page by page:
waiting messages (looked at, not consumed; *being processed* marks leased ones, with failure counts), pending topic
messages, or bucket objects with a prefix filter, preview (text, or base64 for binary, first 256 KiB) and delete. A
single message of a built-in queue can be deleted too.

| Backend | Browse |
|---|---|
| built-in / directory queue, topic, bucket | yes |
| Redis list, Redis / Valkey stream, another pskit host | yes (oldest first) |
| any storage driver (MinIO, S3, Azure Blob, GCS, ...) | yes (listing + preview) |
| SQS / ElasticMQ, Azure queue, Pub/Sub, MNS, Cloudflare | depth only: they cannot show a message without counting a delivery |
| custom class | yes if it implements `peek(offset, limit) -> (items, total)` |

```bash
pskit resources data jobs                    # first 20 messages
pskit resources data jobs --offset 20 -n 20  # next page
pskit resources data uploads --prefix in/
```

## Use it from code and test it

*Resources → Test a resource* shows, for the selected resource, Python and Node.js code to paste into a handler
(publish + consume for queues, streams and buckets; a connection example for databases, caches and SMTP) with the
library to add, and **Test connection**, which runs from the on-prem host once it is deployed. In a terminal:

```bash
pskit resources check orders-db        # e.g. "127.0.0.1:5432 accepts connections (3.1 ms, from host)"
pskit resources send jobs -d '{"order_id": 1}'
```

## Removing

*Resources → Delete* on a resource backed by a one-click service asks what to do with the service: **pskit.yml
only**, **Stop service, keep data** (the volume stays; creating the service again with the same key reuses it) or
**Delete service and data**. For a built-in on-prem queue, bucket or topic it offers **Delete, keep data** or
**Delete with its data** (`pskit resources clear`).

## Monitoring and alerts

The **Servers** list shows a check mark per server: ✓ when its SSH port answers (all probed at once when the list
opens, **Re-check** to probe again), ✗ with the reason otherwise; *Test* replaces it with the result of a full login
check. **Live** on a server shows its CPU, RAM and disk use, refreshed every few seconds, until you switch it off.

A service's **Details** has **Live monitoring**: switch it on to see, every 5 seconds, each container's CPU, memory and
the disk holding its data (for a replicated database: the primary, every replica and the load balancer), the open
connections, the data size and how far each replica is behind. Nothing is measured while it is off.

**Alerts** (optional, in the create form or in Details) send a message when a limit is crossed: CPU, memory or disk
percent of a container, replica lag in seconds, or a container that is down. They go to

- a **function** of the project, run through the deployed host with the alert as `event.data`
  (`{kind: "pskit.database.alert", key, service, reasons, message, sample}`). *Create a new function* adds
  `<key>-alert` to `pskit.yml` with a handler stub; deploy the project to run it;
- a **webhook**: Slack, Teams or Google Chat incoming webhooks show the message; any other URL gets the JSON.

An alert goes out at most once per cooldown (30 minutes by default). The studio checks every minute while it runs;
without it, run the check from cron on any machine with the project:

```bash
pskit resources onprem alerts orders-db --webhook https://hooks.slack.com/services/... --disk 80 --lag 30
pskit resources onprem alerts orders-db --test         # send a test alert
pskit resources onprem alerts orders-db --check        # measure now; alert when over a limit (cron: every minute)
pskit resources onprem monitor orders-db --watch 5     # the live numbers in a terminal
```

## Start a database with data

**Import data** (optional, create form) loads a dump from this machine once the database is up: `.sql`, `.sql.gz`
or `.dump` (`pg_restore`) for PostgreSQL, `.sql` / `.sql.gz` for MySQL and MariaDB, `.archive` (`mongodump
--archive`, optionally gzipped) for MongoDB. A pskit backup works as is. On a server the file goes there over SSH
first; for a replicated database it goes into the primary before the replicas start, so they copy it.

```bash
pskit resources onprem create orders-db --service postgres --server db1 --import ./backups/orders.sql
```

## Backups

`Backup` streams a dump out of the container into `.pskit/backups/` on this machine, or a folder you choose
(**Backup → Save to folder → Browse…**, remembered; CLI `--dir` / `-o`), also from an SSH server:

| Service | File | Restore |
|---|---|---|
| Redis / Valkey | `.rdb` | stop the container, copy it to `/data/dump.rdb` in the volume, start it |
| PostgreSQL | `.sql` | `psql -U pskit -f file.sql postgres` |
| MySQL / MariaDB | `.sql` | `mysql -uroot -p < file.sql` |
| MongoDB | `.archive` | `mongorestore --archive=file.archive -u pskit -p ... --authenticationDatabase admin` |
| RabbitMQ | `.definitions.json` | `rabbitmqctl import_definitions file.json` (messages are not included) |
| Kafka, NATS, MinIO | `.tar.gz` of the data directory | stop the container, extract into the volume, start it |

Data directories are copied while the service runs. For Kafka and NATS, stop producers first for a consistent copy.

## Troubleshooting

| Message | Fix |
|---|---|
| `Docker is not running on this machine` | start Docker Desktop or the docker service |
| `Docker is not installed on <host>` | create the `docker` runtime first, or let *Create* install it (needs sudo or root) |
| `pull access denied` | the image moved; set *Advanced → Docker image* (`--image`) to a mirror you can pull |
| `port is already allocated` | pick another *Port* (`--port`) |
| `did not become ready within 90 s` | the message includes the container's last log lines. On a small server Kafka needs about 1 GB of RAM. `pskit resources onprem logs <key>` shows the rest |
| `keeps restarting` or `Permission denied` in those logs | the data directory was not writable by the user the container runs as. Create the service again: pskit chowns the directory (MinIO 1001, RustFS 10001, and the image's user for the others) |
| a script times out (`TimeoutError`, `ConnectTimeoutError`, `ECONNREFUSED`) | the port is closed from your machine: `pskit resources onprem tunnel <key>`, open it to your IP, or use the pskit client through the host ([client.md](../../client.md#when-connections-time-out)) |
| `is not reachable from this machine; check the firewall` | the service runs; open the port from the functions' server |
| `sqs: ... QueueDoesNotExist` (ElasticMQ) | ElasticMQ forgets queues on restart; redeploy so the sqs driver gets `create_queue` (the default for non-AWS endpoints since 1.3.1) |
| `environment variable PSKIT_..._URL ... is not set on the host` | `provider.options.env_file` is missing or the file was deleted; recreate the service or add the line |
| the web UI does not open | `pskit resources onprem gui <key> --check` (studio: *Details > Check web UI*), see [The UI does not open](#the-ui-does-not-open) |
| `SSH password login uses sshpass, which is not installed` | install sshpass, or `pskit resources onprem ssh-key user@host` once and use the key |
| `The server rejected the SSH password` | wrong user / password, or the server only accepts keys (`PasswordAuthentication no`) |
| `Permission denied (publickey)` | pick the right key file, or *SSH agent / default key*, or install a key with `ssh-key` |
