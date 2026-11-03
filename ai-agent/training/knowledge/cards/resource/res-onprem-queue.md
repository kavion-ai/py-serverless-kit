# On-premises queues (`type: queue`)

Trigger functions on the host from a queue the host's built-in queue, Redis / Valkey, RabbitMQ or Kafka through a custom driver, or a queue in a cloud. Every option gives the same at-least-once handling: `batch_size`, `visibility_timeout`, `max_receive`, `dead_letter` and `BatchResult` work the same way.
## Create one in one click

The studio (*Resources → On-prem services → + Create service*) or the CLI starts the broker with Docker, here or on any SSH server, writes the resource and adds the trigger: Details, backups and removal: services.md. The sections below show the same setups by hand.
## Built-in queue No setup

. The queue is a directory under the host's `data_dir`. Use a shared folder (NFS, SMB) instead: `options: {driver: directory, path: /mnt/shared/queues}` with `external: true`.
### 1. Set up Redis - **Docker:** `docker run -d --name redis -p 6379:6379 redis:7

redis-server --requirepass <password>` (Valkey: `valkey/valkey:8`). - **Linux package:** `sudo apt install redis-server`; in `/etc/redis/redis.conf` set `requirepass <password>` and `bind` to an address the host can reach; `sudo systemctl restart redis-server`. - **Managed Redis** (Azure Cache, ElastiCache, Upstash, DigitalOcean): copy the host, port and password from its console; TLS endpoints use `rediss://`.
### 2. Collect the values | Value | Where | Example | |---|---|---| | URL |

`redis://[user:password@]host:port/db`, `rediss://` for TLS | `redis://:s3cret@192.0.2.10:6379/0` | | Key | the Redis list the queue uses (default: the resource's native name) | `jobs` | Check it with `redis-cli -u "$REDIS_URL" ping` from the host machine.
### 3. Declare it in `pskit.yml`

Other producers can `LPUSH jobs '<text>'`; plain strings are delivered as the record body. How messages are leased: resources.md → Redis layout.
## Redis / Valkey stream (`redis_stream`)

A stream with a consumer group instead of a list: native leases and delivery counts, several hosts can share one group, and other services can read the same stream with groups of their own. Needs Redis 6.2+ or Valkey. Messages are `XADD jobs * body <text> attributes <json>`; another producer may `XADD` any fields (the `body` field, else the first field's value, becomes the record body). An entry is acknowledged and deleted once the handler succeeded. A failed entry is claimable again at once; after `max_receive` deliveries it goes to `dead_letter`. An entry a crashed host never settled is taken over (`XAUTOCLAIM`) once it has been idle for `visibility_timeout`.
## Kafka and NATS

JetStream Both use a driver class that one-click creation copies into `pskit_drivers/` (with `kafka-python` or `nats-py` in `requirements.txt`). By hand: Templates: `examples/19-custom-drivers/app/kafka_queue.py` and `pskit_drivers/nats_queue.py` after a one-click NATS creation.

```bash
pskit resources onprem create jobs --service redis --attach worker --save                 # Redis list
pskit resources onprem create jobs --service valkey --role stream --attach worker --save  # Valkey stream
pskit resources onprem create events --service kafka --attach worker --save               # Kafka (Redpanda)
pskit resources onprem create tasks --service nats --ssh deploy@192.0.2.10 --pem k.pem --save
```
