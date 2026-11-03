# Tencent Cloud resources

How to attach Tencent Cloud services you created in the [Tencent Cloud console](https://console.tencentcloud.com) to a
Serverless Cloud Function (SCF) deployment made with pskit.

| `type` | Tencent Cloud service | Trigger in pskit | Guide |
|---|---|---|---|
| `storage` | Cloud Object Storage (COS) bucket | yes (COS trigger) | [storage.md](storage.md) |
| `queue` | TDMQ for CMQ queue | **no**: send with the SDK | [queue.md](queue.md) |
| `topic` | TDMQ for CMQ topic | **no**: publish with the SDK | [topic.md](topic.md) |
| `database` | TencentDB for MySQL / PostgreSQL / SQL Server | no (connection only) | [database.md](database.md) |
| `cache` | TencentDB for Redis | no (connection only) | [cache.md](cache.md) |
| `custom` | Secrets Manager (SSM), anything else | no (connection only) | [custom.md](custom.md) |

## Values you need for every Tencent Cloud resource

| Value | Where |
|---|---|
| Region | the region selector in each product console (`ap-guangzhou`, `ap-singapore`, ...) |
| APPID | avatar menu (top right) → **Account Information** → *APPID*; part of every COS bucket name |
| SecretId / SecretKey | **Cloud Access Management (CAM)** → **Access Key** / **API Key Management** (better: a sub-user, below) |

**Use a CAM sub-user for the function's own SDK calls.** Console → **CAM** → **Users** → **Create User** → *Custom
Creation* → *Access via API* (programmatic access) → attach the narrowest preset policy you can, for example
`QcloudCOSDataReadOnly` → copy the SecretId and SecretKey.

## How pskit runs on Tencent Cloud (why some steps matter)

- Each function is a `tencentcloud_scf_function` with its own environment variables, so a resource binding only reaches
  the functions listed in its `functions:` (or all of them).
- Only `storage` events exist here (COS trigger). `queue` and `topic` events are validation errors, so queues and topics
  are used through the SDK.
- pskit creates **no** standalone resources here: a managed resource that no event uses is a validation error. Create it
  in the console and set `external: true`.
- An `external: true` bucket used by a `storage` event is **not created**: pskit only adds the COS trigger, for the
  provider's `region`. The bucket must be in that region and be named `<name>-<APPID>`.
- The function runs with `iam.role` if you set one (an existing CAM role name). `iam.statements` are ignored with a
  warning. The examples below pass a sub-user's keys instead.
- `functions.<fn>.options` is merged into the `tencentcloud_scf_function` resource as-is, for example `vpc_id` and
  `subnet_id` to reach databases in a VPC.
- Only `TYPE`, `NAME`, `EXTERNAL` and your `connection` values reach the handler.

## Secrets

Pass secrets with `environment: {NAME: ${env:LOCAL_VAR}}` and put only the variable's **name** in `connection`
(`secret_key_env: NAME`). `${env:...}` is resolved where `pskit deploy` runs, so the value is stored in Terraform state;
protect it, or read secrets at run time from Secrets Manager (see [custom.md](custom.md)).

## Credentials for deploying

```bash
export TENCENTCLOUD_SECRET_ID=<SecretId>
export TENCENTCLOUD_SECRET_KEY=<SecretKey>
# or provider.options.profile: <tccli profile>
```
