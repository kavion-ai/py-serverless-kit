# Adding resources: step-by-step guides

These guides show how to plug a service you **already created in the cloud console** into a pskit project: where to click in the portal to find each value, what to put in `pskit.yml`, and how a handler reads it. They complement the reference page resources.md, which lists every field and provider rule. Guides are grouped by cloud, then by resource `type`: | Cloud | storage | queue | topic | database | cache | custom | |---|---|---|---|---|---|---| | AWS | S3 bucket | SQS queue | SNS topic | RDS / Aurora | ElastiCache / MemoryDB | DynamoDB, Secrets Manager, ... | | Google Cloud | Cloud Storage bucket | Pub/Sub topic as a queue | Pub/Sub topic | Cloud SQL | Memorystore | Firestore, Secret Manager, ... | | Azure | Blob container | Storage queue | Service Bus topic | PostgreSQL / MySQL / SQL | Redis | Cosmos DB, Key Vault, ... | | Alibaba Cloud | OSS bucket | SMQ / MNS queue | SMQ / MNS topic | ApsaraDB RDS / PolarDB | Tair (Redis) | Tablestore, KMS, ... | | Tencent Cloud | COS bucket | TDMQ for CMQ queue | TDMQ for CMQ topic | TencentDB MySQL / PostgreSQL | TencentDB for Redis | Secrets Manager, ... | | Huawei Cloud | OBS bucket | DMS RabbitMQ / Kafka | SMN topic | RDS | DCS Redis | CSMS, DDS, ... | | Oracle Cloud | Object Storage bucket | OCI Queue | Notifications topic | Autonomous DB, MySQL HeatWave | OCI Cache | Vault, Streaming, ... | | IBM Cloud | Cloud Object Storage bucket | IBM MQ queue | Event Streams topic | Databases for PostgreSQL / MySQL | Databases for Redis | Secrets Manager, Cloudant, ... | | DigitalOcean | Spaces bucket | Valkey list as a queue | Managed Kafka topic | Managed PostgreSQL / MySQL | Managed Valkey | MongoDB, OpenSearch, DO API | | Cloudflare | R2 bucket | Queues | No topics: alternatives | D1 / Hyperdrive | Workers KV | Secrets, Workers AI, HTTP APIs | | On premises (one-click services) | Built-in, MinIO, S3, R2, Blob, GCS | Built-in, Redis, Kafka, NATS, RabbitMQ, another host, SQS, ... | Built-in / directory | PostgreSQL / MySQL | Redis / Valkey | SMTP, LDAP, internal APIs | Not every cloud can trigger a function from every type.

```text
resources:
  <key>:                 # the name your code uses: resource("<key>")
    type: queue          # storage | queue | topic | database | cache | custom
    external: true       # it already exists; pskit only passes its details along
    name: <native name>  # the name in the cloud (queue / container / topic)
    connection:          # anything else the handler needs, as scalars
      some_value: ...
      secret_env: NAME_OF_SETTING   # the NAME of a secret setting, never the secret itself
```
