# Huawei Cloud resources

How to attach Huawei Cloud services you created in the [console](https://console-intl.huaweicloud.com) to a
FunctionGraph deployment made with pskit.

| `type` | Huawei Cloud service | Trigger in pskit | Guide |
|---|---|---|---|
| `storage` | OBS bucket | ✓ OBS trigger | [storage.md](storage.md) |
| `queue` | DMS for RabbitMQ / Kafka | – (SDK only) | [queue.md](queue.md) |
| `topic` | SMN topic | ✓ SMN trigger | [topic.md](topic.md) |
| `database` | RDS for MySQL / PostgreSQL | – | [database.md](database.md) |
| `cache` | DCS for Redis | – | [cache.md](cache.md) |
| `custom` | CSMS secrets, DDS, any other service | – | [custom.md](custom.md) |

## Values you need for every Huawei Cloud resource

| Value | Where |
|---|---|
| Region | console header, top left (for example *CN North-Beijing4* = `cn-north-4`). Resources must be in the same region as `provider.region` for triggers |
| Project ID | account name (top right) → **My Credentials** → **API Credentials** → the project of your region |
| Access key / secret key | **My Credentials** → **Access Keys** → **Create Access Key** (downloaded once as a CSV) |
| VPC / subnet IDs | **Virtual Private Cloud** → **My VPCs** / **Subnets** → the *ID* column |

## How pskit runs on Huawei Cloud (why some steps matter)

- Each pskit function is a **FunctionGraph** function in the app `provider.options.app` (default `default`).
- Environment variables (your `environment:` plus the `PSKIT_RESOURCE_*` bindings) are passed as the function's
  `user_data`. They are visible in the FunctionGraph console under **Configuration → Environment Variables** and stored
  in Terraform state.
- Managed resources that no event uses are a validation error on Huawei: create them in the console and declare them
  with `external: true`.
- pskit has **no queue trigger** on Huawei. Queues can still be bound and used from handlers through the SDK.
- `iam.statements` are ignored. Give functions cloud permissions with an **IAM agency** (`iam.role: <agency name>`):
  **Identity and Access Management → Agencies → Create Agency** → *Cloud service* → **FunctionGraph** → attach the
  policies the function needs (for example *OBS OperateAccess*, *SMN Administrator*, *VPC Administrator* for VPC
  access). With an agency, FunctionGraph hands the function temporary credentials through its native context:
  `ctx.raw.getSecurityAccessKey()`, `ctx.raw.getSecuritySecretKey()`, `ctx.raw.getSecurityToken()`.
- RDS, DCS and DMS instances live **inside a VPC**. A function only reaches their private address when it is attached
  to that VPC: set `vpc_id` and `network_id` (subnet ID) under `functions.<name>.options` (passed straight to
  `huaweicloud_fgs_function`) and use an agency with VPC permissions.
- `pskit trigger` / `pskit resources send` can only send HTTP requests on Huawei; for OBS and SMN, `--list` prints the
  console steps.

## Credentials for deploying

```bash
export HW_ACCESS_KEY=<access key>
export HW_SECRET_KEY=<secret key>
export HW_REGION_NAME=cn-north-4
```
