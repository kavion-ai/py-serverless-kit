# On-prem services: the one-click catalog

Search terms: on-prem service, one-click service, create service, Docker container, catalog, Redis, PostgreSQL,
Kafka, MinIO, secrets, web UI, companion UI, backup, remove service, .env.onprem

pskit can start the queue, database, bucket, cache, secret manager or tool your on-premises functions use. It runs
the service as a Docker container on this machine, on a saved SSH server or on one server of a scaling cluster, then
adds it to `pskit.yml` as a resource (and, for queues, buckets and mail, as a trigger). pskit runs only `docker`,
`ssh` and `scp` commands for this; it calls no cloud API.

## Every service in the catalog

The on-prem service catalog has 44 entries (`pskit resources onprem catalog` lists them, `--json` for details). Each
link opens a page with the ports, the studio steps, the CLI command, what pskit writes and handler code.

| Service | `--service` | Use as | Port |
|---|---|---|---|
| [Redis](redis.md) | `redis` | queue, stream, cache | 6379 |
| [Valkey](valkey.md) | `valkey` | queue, stream, cache | 6379 |
| [KeyDB](keydb.md) | `keydb` | queue, stream, cache | 6379 |
| [Dragonfly](dragonfly.md) | `dragonfly` | queue, stream, cache | 6379 |
| [Memcached](memcached.md) | `memcached` | cache | 11211 |
| [RabbitMQ](rabbitmq.md) | `rabbitmq` | queue | 5672 |
| [LavinMQ (AMQP 0.9.1)](lavinmq.md) | `lavinmq` | queue | 5672 |
| [ElasticMQ (SQS-compatible)](elasticmq.md) | `elasticmq` | queue | 9324 |
| [Kafka (Redpanda, single node)](kafka.md) | `kafka` | queue | 9092 |
| [Apache Kafka (KRaft, single node)](apache-kafka.md) | `apache-kafka` | queue | 9092 |
| [NATS JetStream](nats.md) | `nats` | queue | 4222 |
| [Eclipse Mosquitto (MQTT broker)](mosquitto.md) | `mosquitto` | custom | 1883 |
| [PostgreSQL](postgres.md) | `postgres` | database | 5432 |
| [MySQL](mysql.md) | `mysql` | database | 3306 |
| [MariaDB](mariadb.md) | `mariadb` | database | 3306 |
| [MongoDB](mongodb.md) | `mongodb` | database | 27017 |
| [Qdrant (vector database)](qdrant.md) | `qdrant` | database | 6333 |
| [ClickHouse (analytics database)](clickhouse.md) | `clickhouse` | database | 8123 |
| [Neo4j (graph database)](neo4j.md) | `neo4j` | database | 7687 |
| [MinIO (S3-compatible)](minio.md) | `minio` | storage | 9000 |
| [RustFS (S3-compatible)](rustfs.md) | `rustfs` | storage | 9000 |
| [Amazon S3 compatible (Python / Node.js)](s3.md) | `s3`, `s3-node` | storage | 9000 |
| [Azurite (Azure Blob + Queue emulator)](azurite.md) | `azurite` | queue, storage | 10000 |
| [fake-gcs-server (Cloud Storage emulator)](fake-gcs.md) | `fake-gcs` | storage | 4443 |
| [LocalStack (SQS, S3, Secrets Manager)](localstack.md) | `localstack` | queue, storage, secrets | 4566 |
| [LocalEmu (AWS emulator)](localemu.md) | `localemu` | queue, storage, secrets | 4566 |
| [AWS Secrets Manager compatible (Python / Node.js)](secretsmanager.md) | `secretsmanager`, `secretsmanager-node` | secrets | 4584 |
| [OpenBao (Vault-compatible secrets)](openbao.md) | `openbao` | secrets | 8200 |
| [Infisical (secrets manager with web UI)](infisical.md) | `infisical` | secrets | 8080 |
| [SMTP server (receive mail, Node.js)](smtp.md) | `smtp` | smtp | 25 |
| [Mailpit (SMTP)](mailpit.md) | `mailpit` | custom | 1025 |
| [Grafana (dashboards)](grafana.md) | `grafana` | custom | 3000 |
| [Prometheus (metrics)](prometheus.md) | `prometheus` | custom | 9090 |
| [Uptime Kuma (uptime monitor)](uptime-kuma.md) | `uptime-kuma` | custom | 3001 |
| [Jaeger (tracing, OpenTelemetry)](jaeger.md) | `jaeger` | custom | 16686 |
| [Keycloak (login, SSO, OAuth2 / OIDC)](keycloak.md) | `keycloak` | custom | 8080 |
| [Meilisearch (search engine)](meilisearch.md) | `meilisearch` | custom | 7700 |
| [Typesense (search engine)](typesense.md) | `typesense` | custom | 8108 |
| [n8n (workflow automation)](n8n.md) | `n8n` | custom | 5678 |
| [Portainer (Docker UI)](portainer.md) | `portainer` | custom | 9000 |
| [Gitea (Git hosting)](gitea.md) | `gitea` | custom | 3000 |
| [Nginx Proxy Manager](nginx-proxy-manager.md) | `nginx-proxy-manager` | custom | 81 |

*Use as* is the role. It becomes the resource type in `pskit.yml`: `stream` becomes a `queue` (on the
`redis_stream` driver) and `secrets` becomes a `custom` resource read with `get_secret()`. The catalog also has
software to **install** on a server (Docker, Python, Node.js, nginx, ...): see
[terminal and software](../terminal-and-software.md).

## How the studio groups the on-prem service catalog

The studio's *Create a service* drawer shows the on-prem service catalog in groups. Each card shows the label, a
short note, the port and the web UI.

| Group in the drawer | Services |
|---|---|
| Queues & streams | RabbitMQ, ElasticMQ, Kafka (Redpanda), NATS, Apache Kafka, LavinMQ, Mosquitto |
| Redis-compatible (cache, queue, stream) | Redis, Valkey, Dragonfly, KeyDB, Memcached |
| Object storage | MinIO, Azurite, fake-gcs-server, RustFS, Amazon S3 compatible (Python / Node.js) |
| Databases | PostgreSQL, MySQL, MariaDB, MongoDB, Qdrant, ClickHouse, Neo4j |
| Mail (receive e-mail, run functions) | SMTP server |
| Secret managers | OpenBao, AWS Secrets Manager compatible (Python / Node.js), Infisical |
| AWS emulators | LocalStack, LocalEmu |
| Monitoring & tracing | Grafana, Prometheus, Uptime Kuma, Jaeger |
| Identity & search | Keycloak, Meilisearch, Typesense |
| Automation, web & tools | Mailpit, n8n, Portainer, Gitea, Nginx Proxy Manager |
| Install on a server: ... | Docker, Python, Node.js, Java, Go, nginx, Caddy, Certbot, PM2, Git, basic tools |

## Create an on-prem service in studio

An on-prem service is created from the **Resources** page. These steps are the same for every service; each
service page lists the fields that differ.

1. Open **Resources** in the sidebar.
2. Click **+ On-prem service** in the page header. Other ways in: **+ Create service** in the *On-prem services*
   card, **+ SMTP server** in the header, **Install / create** on a saved server, or *Add resource → Create a
   &lt;type&gt; on premises* (the catalog is then filtered to services that fit that type).
3. Click a card. The drawer title becomes *Create &lt;service&gt;*; **Pick another** goes back to the catalog.
4. Fill in **Resource key** (how handlers and triggers name it) and, when the service has several roles, **Use as**.
5. Choose **Where**: **This machine**, **One SSH server** (then a saved server in **Server**, or *New connection…*)
   or **Scaling cluster** (then **Cluster** and **Server in the cluster**, *Auto* picks the server with the most free
   memory). Databases scale with replicas instead, so they do not offer *Scaling cluster*.
6. Set **Port** (empty = the default), the **Security** box (**User**, **Password**, **Listen on**), the **Web UI**
   options and the **Trigger functions** to attach.
7. Open **Advanced** for **Address functions use** (the address functions connect to, default the SSH host or
   127.0.0.1) and **Docker image** (a mirror, another tag).
8. Click **Create**. The job log streams in the drawer: Docker is installed on an SSH server when missing, the image
   is pulled, the container is started and checked until it is ready, and the firewall rules the functions need are
   printed.
9. The resource (and triggers) are added to the draft and a toast says so. Click **Save** in the top bar, then
   deploy so the host gets the new env file.

Services created earlier but missing from `pskit.yml` show in a hint box at the top of the Resources page
(*On-prem services not in the resource list yet*) and as **Add to pskit.yml** on their row.

## Create an on-prem service from the terminal

`pskit resources onprem create KEY --service ID` creates an on-prem service. Without a place it uses the functions'
cluster (`provider.options.cluster`), then their server (`provider.options.deploy`), else this machine.

```bash
pskit resources onprem catalog                                       # what can be created
pskit resources onprem create jobs --service redis --attach worker --save
pskit resources onprem create orders-db --service postgres --server edge1 --save
pskit resources onprem create cache --service valkey --role cache --local --save
pskit resources onprem create events --service kafka --cluster prod --node vm2 --save
pskit resources onprem create files --service minio --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --sudo --save
```

| Flag | Meaning |
|---|---|
| `--service` | catalog id (required) |
| `--role` | queue, stream, cache, database, storage, secrets or custom (default: the first one) |
| `--local` / `--server NAME` / `--ssh user@host[:port]` / `--cluster NAME [--node SERVER]` | where it runs |
| `--pem`, `--ssh-password-file`, `--ssh-password-env`, `--sudo` | SSH login for `--ssh` |
| `--user`, `--password`, `--password-env VAR` | credentials (prefer `--password-env`) |
| `--port`, `--image`, `--address`, `--bind` | port on the server, Docker image, address functions use, listen interface |
| `-a / --attach FUNCTION` | add a queue / storage / smtp trigger (repeatable) |
| `--gui`, `--gui-login password\|none`, `--gui-password-env VAR` | start the companion web UI |
| `--import FILE`, `--alert-webhook URL`, `--alert-function NAME` | databases: load a dump, alerts |
| `--replica`, `--primary`, `--balancer`, `--balancer-port`, `--sync` | replicated database ([database scaling](../database-scaling.md)) |
| `--domains`, `--functions-url`, `--max-size-mb` | SMTP server |
| `--save` | write the resource and triggers into `pskit.yml` (otherwise the YAML is printed) |
| `--json` | print the created entry as JSON |

## Credentials and the on-prem env file

On-prem service passwords never go into `pskit.yml`. pskit writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`) as `PSKIT_<KEY>_URL`, `PSKIT_<KEY>_PASSWORD`,
`PSKIT_<KEY>_ACCESS_KEY` / `_SECRET_KEY`, `_TOKEN`, `_API_KEY` and similar, and refers to them from the resource as
`<name>_env: PSKIT_<KEY>_...`. `pskit deploy` ships the file to the host, which loads it at start, so handlers read
the values with `ctx.env[...]`.

- A password left empty is generated (24 random characters). Your own must be 8-128 characters of letters, digits
  and `!#%*+,.:=?@^_~-`; a user 3-64 characters starting with a letter.
- The env file is added to `.gitignore` when the project has one. Keep `.pskit/` out of git too: it holds
  `.pskit/onprem-services.json` (what was created, with credentials) and `.pskit/backups/`.
- To see the values: **Details → Show values**, *How to use → Show passwords and URLs*, or
  `pskit resources onprem status KEY --reveal`.
- To change a password: remove the service keeping its data, create it again with the same key and the new
  password, then redeploy.

Services without authentication (ElasticMQ, Kafka, Apache Kafka, Memcached, Mailpit, LocalStack, LocalEmu,
fake-gcs-server, SMTP server, Prometheus, Mosquitto, Jaeger) refuse a user or password. Uptime Kuma, n8n, Portainer,
Gitea and Nginx Proxy Manager ask you to create their admin account on the first visit, so leave both empty.

## Manage an on-prem service from its row

Each created on-prem service is a row in the *On-prem services* card (columns Key, Service, Used as, Where,
Endpoint). The buttons:

| Button | What it does | CLI |
|---|---|---|
| **How to use** (*DNS guide* for SMTP) | connection details, Python / Node.js client code, terminal tools, security | `pskit resources onprem usage KEY [--reveal]` |
| **Details** | state, health, endpoint, live monitoring, alerts, web UI links (**Check web UI**, **Add web UI** / **Remove web UI**), credentials, resource, backups, **Show logs** | `status`, `logs`, `monitor`, `alerts`, `gui` |
| **Browse** / **Browse secrets** | pskit's own browser for buckets (S3, Cloud Storage) or secrets (OpenBao, Secrets Manager) | none |
| **Console** | run one command with the service's client, or *Shell in the container* | `pskit resources onprem console KEY "..."` |
| **Terminal** | a full terminal in the browser | `pskit resources onprem terminal KEY` |
| **Add to pskit.yml** | add the resource again (shown when it is missing) | `create ... --save` |
| **Backup** | dump the data to `.pskit/backups/` or a folder you pick | `pskit resources onprem backup KEY [--dir DIR]` |
| **Remove** | stop and delete the container; *Remove, keep data* or *Delete data too* | `pskit resources onprem remove KEY [--delete-data] [--save]` |

Console and terminal are explained in [terminal and software](../terminal-and-software.md); monitoring and alerts in
[replicas and alerts](../scaling/replicas-and-alerts.md).

## Open an on-prem service web UI

An on-prem service web UI is either built in (RabbitMQ, LavinMQ, MinIO, RustFS, ElasticMQ, NATS monitoring, Mailpit,
Grafana, Keycloak, the S3 and Secrets Manager consoles, ...) or a **companion** container pskit starts next to the
service on a private Docker network:

| Services | Companion | Default port | Login |
|---|---|---|---|
| PostgreSQL, MySQL, MariaDB | Adminer | 8089 | the database user and password |
| Redis, Valkey, KeyDB, Dragonfly | Redis Commander | 8082 | `admin`, password in `PSKIT_<KEY>_GUI_PASSWORD` |
| Kafka, Apache Kafka | Kafka UI | 8088 | `admin`, password in `PSKIT_<KEY>_GUI_PASSWORD` (sign-in page `/auth`) |
| MongoDB | Mongo Express | 8081 | the MongoDB user and password |

A second companion of the same kind on one server takes the next free port. Start it with **Also start ...** in the
create form, **Details → Add web UI**, or `pskit resources onprem gui KEY`. When a UI does not open, run
**Details → Check web UI** or `pskit resources onprem gui KEY --check`; it tests the container, the published port,
the server and this machine and prints the fix (firewall rule, bind address, or
`pskit resources onprem tunnel KEY --remote-port PORT`). The full troubleshooting table is in
[the one-click services reference](../../resource-guides/onprem/services.md#the-ui-does-not-open).

## Remove an on-prem service

Removing an on-prem service stops and deletes its container (and its companion UI and sidecars). The data volume is
kept unless you ask to delete it, so creating the service again with the same key reuses the data.

1. On the service row click **Remove**.
2. Pick **Remove, keep data** or **Delete data too** (installed software only offers **Forget**: pskit never
   uninstalls).
3. The job log shows the progress; the resource and its triggers leave the draft. Click **Save**.

From the Resources table, **Delete** on a resource backed by a service asks *pskit.yml only*, *Stop service, keep
data* or *Delete service and data*.

```bash
pskit resources onprem remove jobs --save                 # keep the volume, edit pskit.yml
pskit resources onprem remove jobs --delete-data --save
pskit resources onprem list                               # what is left
```

## See also

- [On-prem overview](../README.md)
- [On-prem resources and drivers](../resources.md)
- [Attach cloud resources to on-prem functions](../cloud-resources.md)
- [Saved servers](../servers.md)
- [Database scaling](../database-scaling.md)
- [S3 compatible server reference](../aws-compatible/s3.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
