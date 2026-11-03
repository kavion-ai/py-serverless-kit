# Alibaba Cloud databases (`type: database`)

ApsaraDB RDS for MySQL / PostgreSQL / SQL Server and PolarDB. pskit never creates databases: declare them with
`external: true` and pskit hands their connection details to your functions.

## 1. Create the instance (console)

**ApsaraDB RDS** (PolarDB is similar under **PolarDB**):

1. Console → **ApsaraDB RDS** → **Instances** → **Create Instance**: billing method, region, engine and version,
   edition, instance type, storage, **VPC** and vSwitch → buy.
2. Open the instance → **Accounts** → **Create Account**: a standard account (for example `pskitapp`) and password.
3. **Databases** → **Create Database**: name (for example `orders`), authorize the account.
4. Network access, pick one:
   - **Public endpoint** (simplest): **Database Connection** → **Apply for Public Endpoint**, then
     **Whitelist and SecGroup** → **Modify** the default group to allow the function's outbound addresses. Function
     Compute has no fixed public IP without a VPC/NAT setup, so this often means a wide whitelist; prefer the VPC
     option for production.
   - **VPC** (recommended): run the function in the instance's VPC with the `vpc_config` function option (below) and
     add the vSwitch CIDR to the whitelist.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host | instance → **Database Connection** → *Internal Endpoint* (VPC) or *Public Endpoint* | `rm-xxxx.mysql.rds.aliyuncs.com` / `pgm-xxxx.pg.rds.aliyuncs.com` |
| Port | **Database Connection** → port | `3306` (MySQL), `5432` (PostgreSQL), `1433` (SQL Server) |
| Database | **Databases** | `orders` |
| User / password | **Accounts** (reset with **Reset Password**) | `pskitapp` |
| VPC / vSwitch | **Basic Information** → *Network Type* | `vpc-xxxx` / `vsw-xxxx` |

## 3. Declare it in `pskit.yml`

`functions.<fn>.options` is merged into the `alicloud_fcv3_function` resource unchanged, so use the argument names from
the alicloud provider docs
and verify them with `terraform validate` (`pskit package`, then `pskit tf -- validate`).

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`)

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timeout from the function | the whitelist doesn't include the caller, or the function isn't in the VPC for an internal endpoint |
| Timeout locally | apply for a public endpoint and add your IP to the whitelist |
| `password authentication failed` | wrong account or password; check **Accounts** |
| pskit does not create database resources | add `external: true` |

```bash
export ORDERS_DB_PASSWORD='...'
```
