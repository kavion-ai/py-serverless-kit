# On-premises resources

How to give functions on an on-premises host (`provider.name: onprem`) the queues, buckets, topics, databases and caches
they use: the host's own built-in ones, or services you already run (Redis, MinIO, RabbitMQ, PostgreSQL) or that live
in a cloud (SQS, Azure Storage queues, Pub/Sub, S3, R2, ...).

No service yet? **[Create it in one click](services.md)**: Redis, Valkey, Kafka, NATS, RabbitMQ, MinIO, PostgreSQL,
MySQL, MongoDB and more as Docker containers, on this machine or any SSH server, added to `pskit.yml` with their
triggers (studio: *Resources → On-prem services*; CLI: `pskit resources onprem create`).

| `type` | Built in | Or an existing service | Guide |
|---|---|---|---|
| `queue` | directories under `data_dir` | Redis / Valkey (list or stream), Kafka, NATS, RabbitMQ (`custom`), another on-prem host, SQS, Azure Storage queue, Pub/Sub, MNS, Cloudflare Queues | [queue.md](queue.md) |
| `storage` | directories under `data_dir` | MinIO, any S3-compatible store, S3, R2, Azure Blob, GCS, a shared folder | [storage.md](storage.md) |
| `topic` | directories under `data_dir` | a shared directory only | [topic.md](topic.md) |
| `database` | — | self-hosted PostgreSQL / MySQL, a cloud database | [database.md](database.md) |
| `cache` | — | Redis / Valkey, Memcached | [cache.md](cache.md) |
| `custom` | — | SMTP, LDAP, internal APIs, anything | [custom.md](custom.md) |
| secrets | — | OpenBao / Vault, AWS Secrets Manager (pskit's compatible server or LocalStack on premises), environment variables: `get_secret()` | [secrets.md](secrets.md) |

## How the host uses resources

- **Built in (`builtin`)**: a `queue`, `storage` or `topic` resource without `external: true` is a directory under the
  host's `data_dir`, created when the host starts. Nothing to set up. Unlike most clouds, a managed resource no event
  uses is fine on premises.
- **Drivers**: `external: true` plus `options.driver` points the resource at another service. The host **watches** it:
  queues are polled and leased, buckets are listed and diffed every `provider.options.poll_seconds`, and each message or
  object change triggers the function like a local event. Allowed drivers per type:

  | Type | Drivers |
  |---|---|
  | queue | `builtin`, `directory`, `redis`, `redis_stream`, `pskit_host`, `sqs`, `azure_queue`, `pubsub`, `mns`, `cloudflare_queue`, `custom` |
  | storage | `builtin`, `directory`, `s3`, `aws`, `oss`, `cos`, `obs`, `oci`, `ibm_cos`, `spaces`, `r2`, `minio`, `azure_blob`, `gcs`, `custom` |
  | topic | `builtin`, `directory` |

- `database`, `cache` and `custom` resources have no driver (`options.driver` is a validation error). pskit only hands
  their `connection` values to handlers, which connect with any client library (on premises `requirements.txt` **is**
  installed).

Full parameter tables: [resources.md → On-premises drivers](../../resources.md#on-premises-drivers).

## Secrets: `<name>_env`

Any driver parameter can be written as `<name>_env: VARIABLE` instead of `<name>: value`:

```yaml
options:
  driver: minio
  endpoint: http://minio.internal:9000
  access_key_env: MINIO_ACCESS_KEY     # read from the HOST's environment when it starts
  secret_key_env: MINIO_SECRET_KEY
```

The host reads `VARIABLE` from its own environment at start, so the secret never lands in Terraform state or
`pskit_host.json`. A missing variable stops the host with an error naming it.

The simplest place for those variables is an **env file** that pskit ships with the host:

```yaml
provider:
  name: onprem
  options:
    env_file: .env.onprem      # KEY=VALUE lines, relative to pskit.yml; keep it out of git
```

`pskit deploy` copies it next to the host as `host.env` (on this machine, over SSH, or into the Docker image) and the
host loads it at start, for every deploy method. Only its digest goes into `pskit_host.json`, so changing a secret
redeploys the host without writing the value anywhere else. Variables already set in the host's environment win.
One-click services write their credentials there.

Or set them where the host runs:

| Deploy method | Where |
|---|---|
| `local` (default) | the shell that runs `pskit deploy` |
| `ssh` with `install: systemd` | the unit's environment (`systemctl edit <unit>` → `[Service]` `Environment=...`) |
| `docker` | the container's environment |

For handlers, do the same with `connection`: put the variable's **name** in `connection` (`password_env: DB_PASSWORD`)
and read it with `ctx.env[res["password_env"]]`. `${env:...}`, by contrast, is resolved on the machine running
`pskit deploy` and written into the generated files.

## Publishing from a handler

The studio shows ready-to-paste Python and Node.js code for every resource (*Resources → Test a resource → Use it in
a handler*): publish and consume for queues, buckets and topics, and a connection example (PostgreSQL, MySQL,
MongoDB, Redis, Memcached, SMTP) for the others, with the client library to add. *Test connection* checks it from the
host (`pskit resources check <key>`).

Handlers in the host process can publish through the host, which honours drivers:

```python
from py_serverless_kit import resource
from py_serverless_kit.runtime.onprem_host import delete_object, put_object, submit_queue, submit_topic

submit_queue(resource("jobs").native_name, {"order_id": 1}, {"kind": "new"})   # -> message id
submit_topic(resource("events").native_name, {"order_id": 1}, {"type": "paid"})
put_object(resource("uploads").native_name, "in/a.csv", b"a,b\n")
delete_object(resource("uploads").native_name, "in/a.csv")
```

Node.js handlers have the same calls (they go through the host's loopback address, `PSKIT_HOST_URL`):

```js
const { resource, submitQueue, submitTopic, putObject, deleteObject } = require("pskit");

exports.api = async (event, ctx) => {
  const id = await submitQueue(resource("jobs").nativeName, { orderId: 1 }, { kind: "new" });
  await putObject(resource("uploads").nativeName, "in/a.csv", "a,b\n");
  return { id };
};
```

Names are the resource's **native name** (`name`, else the key).

## Testing

```bash
pskit validate
pskit deploy
pskit resources send --list                    # how to test each resource
pskit resources send jobs -d '{"order_id": 1}'
pskit resources check orders-db                # connection check from the host
pskit resources clear jobs --yes               # empty a built-in queue / bucket on the host
pskit logs -f                                  # host notes show unreachable endpoints
curl http://127.0.0.1:8080/__pskit/health
```
