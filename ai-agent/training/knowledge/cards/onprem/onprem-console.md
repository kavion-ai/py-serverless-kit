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
