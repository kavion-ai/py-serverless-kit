# DigitalOcean resources

How to attach DigitalOcean services you created in the [control panel](https://cloud.digitalocean.com) to a
DigitalOcean Functions deployment made with pskit.

| `type` | DigitalOcean service | Guide |
|---|---|---|
| `queue` | no queue service: Managed Valkey (Redis-compatible) list as a queue | [queue.md](queue.md) |
| `storage` | Spaces bucket | [storage.md](storage.md) |
| `topic` | Managed Kafka topic | [topic.md](topic.md) |
| `database` | Managed PostgreSQL / MySQL | [database.md](database.md) |
| `cache` | Managed Valkey (Redis-compatible) | [cache.md](cache.md) |
| `custom` | Managed MongoDB, OpenSearch, anything else | [custom.md](custom.md) |

## What pskit supports on DigitalOcean

- **HTTP and schedule triggers only.** No `queue`, `storage` or `topic` triggers; `pskit validate` rejects them. A
  `schedule` function that polls (for example every minute) is the usual way to consume work, see [queue.md](queue.md).
- **Every resource must be `external: true`.** pskit creates no buckets, queues or topics on DigitalOcean; a managed
  resource is a validation error. Create the service in the control panel and declare it.
- Handlers use the services through their SDKs, with the values pskit passes as `PSKIT_RESOURCE_<KEY>_*` environment
  variables (`resource("<key>")` in code).
- To react to new objects or messages as they arrive, run that consumer on the
  [on-premises host](../../resources.md#on-premises-drivers): it can watch Spaces (`driver: spaces`) and Valkey / Redis
  lists (`driver: redis`).

## Values you need for most DigitalOcean services

| Value | Where |
|---|---|
| Region / datacenter | the resource's page header (for example `NYC3`) |
| Connection details | **Databases** → the cluster → **Overview** → **Connection details** (*Public network*) |
| Trusted sources | the cluster → **Settings** → **Trusted sources** |
| API / access keys | **API** (personal tokens) or **Spaces Object Storage → Access Keys** |

**Trusted sources and Functions.** Functions don't run from fixed IP addresses, so a database cluster that restricts
connections with trusted sources may refuse them. Check DigitalOcean's current Functions limits before enabling trusted
sources on a cluster your functions use, and rely on the cluster's password and TLS instead.

## Secrets on DigitalOcean

`environment:` values (including `${env:...}`) are written into the generated `project.yml` under
`.pskit/digitalocean-<stage>/do_project/`. Keep `.pskit/` out of version control (it is local build output) and don't
share it.

## Credentials for deploying

```bash
doctl auth init
doctl serverless namespaces list     # the namespace for provider.options.namespace
```
