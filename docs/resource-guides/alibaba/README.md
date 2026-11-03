# Alibaba Cloud resources

How to attach Alibaba Cloud services you created in the [Alibaba Cloud console](https://home.console.aliyun.com) to a
Function Compute 3.0 deployment made with pskit.

| `type` | Alibaba Cloud service | Trigger in pskit | Guide |
|---|---|---|---|
| `storage` | Object Storage Service (OSS) bucket | yes (OSS trigger) | [storage.md](storage.md) |
| `queue` | Simple Message Queue (SMQ, formerly MNS) queue | **no**: send / receive with the SDK | [queue.md](queue.md) |
| `topic` | Simple Message Queue (SMQ, formerly MNS) topic | yes (MNS topic trigger) | [topic.md](topic.md) |
| `database` | ApsaraDB RDS for MySQL / PostgreSQL / SQL Server, PolarDB | no (connection only) | [database.md](database.md) |
| `cache` | Tair (Redis OSS-compatible) | no (connection only) | [cache.md](cache.md) |
| `custom` | Tablestore, KMS secrets, anything else | no (connection only) | [custom.md](custom.md) |

## Values you need for every Alibaba Cloud resource

| Value | Where |
|---|---|
| Region ID | the region selector at the top of the console, or the resource's details page (`cn-hangzhou`, `ap-southeast-1`, ...) |
| Account ID | avatar menu (top right) → *Account ID* / **Security Settings** |
| AccessKey pair | avatar menu → **AccessKey** (better: a RAM user, see below) |

**Use a RAM user for the function's own SDK calls.** Console → **RAM** (Resource Access Management) → **Identities →
Users → Create User** → tick *Using permanent AccessKey to access* (*OpenAPI Access*) → copy the AccessKey ID and
AccessKey Secret (the secret is shown only once). Then **Grant Permission** with the narrowest system policy you can,
for example `AliyunOSSReadOnlyAccess` or `AliyunMNSFullAccess`.

## How pskit runs on Alibaba Cloud (why some steps matter)

- Each function is an `alicloud_fcv3_function` with its own environment variables, so a resource binding only reaches
  the functions listed in its `functions:` (or all of them).
- pskit creates **no** standalone resources here: a managed `storage`, `queue` or `topic` resource that no event uses is
  a validation error. Create it in the console and set `external: true`.
- `external: true` resources used by an event are **not created**: pskit only adds the trigger. OSS and MNS triggers are
  built for the provider's `region`, so the bucket or topic must be in that same region.
- For OSS and MNS triggers pskit creates a RAM role the trigger uses to invoke the function (`AliyunFCInvocationAccess`).
- The function itself runs with `iam.role` if you set one (a RAM role ARN). `iam.statements` are ignored with a warning.
  The examples below pass a RAM user's AccessKey instead, which works with or without a role.
- Only `TYPE`, `NAME`, `EXTERNAL` and your `connection` values reach the handler: no ARN or URL is added for you.

## Secrets

Pass secrets with `environment: {NAME: ${env:LOCAL_VAR}}` and put only the variable's **name** in `connection`
(`secret_key_env: NAME`). `${env:...}` is resolved where `pskit deploy` runs, so the value is stored in Terraform state;
protect it, or read secrets at run time from KMS (see [custom.md](custom.md)).

## Credentials for deploying

```bash
export ALICLOUD_ACCESS_KEY=<AccessKey ID>
export ALICLOUD_SECRET_KEY=<AccessKey Secret>
# or provider.options.profile: <aliyun CLI profile>
```
