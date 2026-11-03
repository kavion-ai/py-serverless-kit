# Adding resources: step-by-step guides

These guides show how to plug a service you **already created in the cloud console** into a pskit project: where to
click in the portal to find each value, what to put in `pskit.yml`, and how a handler reads it. They complement the
reference page [resources.md](../resources.md), which lists every field and provider rule.

Guides are grouped by cloud, then by resource `type`:

| Cloud | storage | queue | topic | database | cache | custom |
|---|---|---|---|---|---|---|
| [AWS](aws/README.md) | [S3 bucket](aws/storage.md) | [SQS queue](aws/queue.md) | [SNS topic](aws/topic.md) | [RDS / Aurora](aws/database.md) | [ElastiCache / MemoryDB](aws/cache.md) | [DynamoDB, Secrets Manager, ...](aws/custom.md) |
| [Google Cloud](gcp/README.md) | [Cloud Storage bucket](gcp/storage.md) | [Pub/Sub topic as a queue](gcp/queue.md) | [Pub/Sub topic](gcp/topic.md) | [Cloud SQL](gcp/database.md) | [Memorystore](gcp/cache.md) | [Firestore, Secret Manager, ...](gcp/custom.md) |
| [Azure](azure/README.md) | [Blob container](azure/storage.md) | [Storage queue](azure/queue.md) | [Service Bus topic](azure/topic.md) | [PostgreSQL / MySQL / SQL](azure/database.md) | [Redis](azure/cache.md) | [Cosmos DB, Key Vault, ...](azure/custom.md) |
| [Alibaba Cloud](alibaba/README.md) | [OSS bucket](alibaba/storage.md) | [SMQ / MNS queue](alibaba/queue.md) | [SMQ / MNS topic](alibaba/topic.md) | [ApsaraDB RDS / PolarDB](alibaba/database.md) | [Tair (Redis)](alibaba/cache.md) | [Tablestore, KMS, ...](alibaba/custom.md) |
| [Tencent Cloud](tencent/README.md) | [COS bucket](tencent/storage.md) | [TDMQ for CMQ queue](tencent/queue.md) | [TDMQ for CMQ topic](tencent/topic.md) | [TencentDB MySQL / PostgreSQL](tencent/database.md) | [TencentDB for Redis](tencent/cache.md) | [Secrets Manager, ...](tencent/custom.md) |
| [Huawei Cloud](huawei/README.md) | [OBS bucket](huawei/storage.md) | [DMS RabbitMQ / Kafka](huawei/queue.md) | [SMN topic](huawei/topic.md) | [RDS](huawei/database.md) | [DCS Redis](huawei/cache.md) | [CSMS, DDS, ...](huawei/custom.md) |
| [Oracle Cloud](oracle/README.md) | [Object Storage bucket](oracle/storage.md) | [OCI Queue](oracle/queue.md) | [Notifications topic](oracle/topic.md) | [Autonomous DB, MySQL HeatWave](oracle/database.md) | [OCI Cache](oracle/cache.md) | [Vault, Streaming, ...](oracle/custom.md) |
| [IBM Cloud](ibm/README.md) | [Cloud Object Storage bucket](ibm/storage.md) | [IBM MQ queue](ibm/queue.md) | [Event Streams topic](ibm/topic.md) | [Databases for PostgreSQL / MySQL](ibm/database.md) | [Databases for Redis](ibm/cache.md) | [Secrets Manager, Cloudant, ...](ibm/custom.md) |
| [DigitalOcean](digitalocean/README.md) | [Spaces bucket](digitalocean/storage.md) | [Valkey list as a queue](digitalocean/queue.md) | [Managed Kafka topic](digitalocean/topic.md) | [Managed PostgreSQL / MySQL](digitalocean/database.md) | [Managed Valkey](digitalocean/cache.md) | [MongoDB, OpenSearch, DO API](digitalocean/custom.md) |
| [Cloudflare](cloudflare/README.md) | [R2 bucket](cloudflare/storage.md) | [Queues](cloudflare/queue.md) | [No topics: alternatives](cloudflare/topic.md) | [D1 / Hyperdrive](cloudflare/database.md) | [Workers KV](cloudflare/cache.md) | [Secrets, Workers AI, HTTP APIs](cloudflare/custom.md) |
| [On premises](onprem/README.md) ([one-click services](onprem/services.md)) | [Built-in, MinIO, S3, R2, Blob, GCS](onprem/storage.md) | [Built-in, Redis, Kafka, NATS, RabbitMQ, another host, SQS, ...](onprem/queue.md) | [Built-in / directory](onprem/topic.md) | [PostgreSQL / MySQL](onprem/database.md) | [Redis / Valkey](onprem/cache.md) | [SMTP, LDAP, internal APIs](onprem/custom.md) |

Not every cloud can trigger a function from every type. Where pskit has no trigger, the page says so at the top and
shows how to use the service from the SDK instead. The full matrix is in [events.md](../events.md).

## The pattern every guide follows

1. **Create** the service in the portal (or find the one you have).
2. **Collect** the values the function needs: name, endpoint, connection string or key.
3. **Declare** it under `resources:` with `external: true`, so pskit never creates, changes or deletes it.
4. **Wire** it to a trigger (`queue`, `storage`, `topic` events) or just bind it to functions.
5. **Read** it in the handler with `resource("<key>")`.
6. **Test** with `pskit validate`, `pskit deploy`, then `pskit resources send` / `pskit trigger`.

```yaml
resources:
  <key>:                 # the name your code uses: resource("<key>")
    type: queue          # storage | queue | topic | database | cache | custom
    external: true       # it already exists; pskit only passes its details along
    name: <native name>  # the name in the cloud (queue / container / topic)
    connection:          # anything else the handler needs, as scalars
      some_value: ...
      secret_env: NAME_OF_SETTING   # the NAME of a secret setting, never the secret itself
```

## Secrets

Never paste a password, key or connection string into `connection:`. Values there become environment variables and are
stored in Terraform state. Instead:

- keep the secret in your shell or CI as an environment variable,
- pass it to the function as an app setting with `environment: {SETTING: ${env:LOCAL_VAR}}`,
- put only the setting's **name** in `connection` (`secret_env: SETTING`) and read it in the handler with
  `ctx.env[res["secret_env"]]`.

`${env:...}` is resolved on the machine running `pskit deploy`, so the value still ends up in Terraform state. Protect
the state (remote backend with access control) or use the cloud's secret store as described in each guide.

## Adding a guide for another cloud or type

Copy the closest existing page into `docs/resource-guides/<cloud>/<type>.md`, keep the same sections (Create, Collect,
Declare, Use in a handler, Test, Troubleshooting) and add a row to the table above.
