# IBM Cloud resources

How to attach IBM Cloud services you created in the [IBM Cloud console](https://cloud.ibm.com) to a Code Engine
functions deployment made with pskit.

| `type` | IBM Cloud service | Guide |
|---|---|---|
| `queue` | IBM MQ (Event Streams for Kafka-style queues) | [queue.md](queue.md) |
| `storage` | Cloud Object Storage bucket | [storage.md](storage.md) |
| `topic` | Event Streams (Kafka) topic | [topic.md](topic.md) |
| `database` | Databases for PostgreSQL / MySQL | [database.md](database.md) |
| `cache` | Databases for Redis | [cache.md](cache.md) |
| `custom` | Secrets Manager, Cloudant, anything else | [custom.md](custom.md) |

## What pskit supports on IBM Cloud

- **HTTP triggers only.** Code Engine functions get no `schedule`, `queue`, `storage` or `topic` triggers from pskit:
  the Terraform provider has no function subscriptions. `pskit validate` rejects those events.
- **Every resource must be `external: true`.** pskit creates no buckets, queues or topics on IBM Cloud; a managed
  resource is a validation error (`managed ... resources that no event uses are not supported on IBM Cloud Code Engine
  yet`). Create the service in the console and declare it.
- Handlers **use** the services through their SDKs, with the values pskit passes as `PSKIT_RESOURCE_<KEY>_*`
  environment variables (`resource("<key>")` in code).
- Need to *react* to new objects or messages? Run that consumer on the [on-premises host](../../resources.md#on-premises-drivers),
  which can watch a Cloud Object Storage bucket (`driver: ibm_cos`) or IBM MQ / Event Streams (`driver: custom`), or
  have the producer call the function's HTTPS URL.

## Values you need for most IBM Cloud services

| Value | Where |
|---|---|
| Region | service instance → **Overview** (or the region shown in the resource list) |
| Resource group | **Resource list** → the instance → *Resource group* column |
| Credentials | service instance → **Service credentials** → **New credential** → expand **View credentials** |
| Endpoints | service instance → **Endpoints** (or **Overview → Endpoints**); use the **public** endpoint |

## Secrets on Code Engine

pskit writes every function variable as a literal `run_env_variables` entry, so `environment:` values (including
`${env:...}`) are stored in Terraform state. Protect the state, or keep only an API key in the environment and fetch the
rest from [Secrets Manager](custom.md#secrets-manager) at run time.

## Credentials for deploying

```bash
export IC_API_KEY=<API key>     # Manage → Access (IAM) → API keys → Create
```
