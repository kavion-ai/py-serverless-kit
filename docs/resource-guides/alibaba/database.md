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

```bash
export ORDERS_DB_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: alibaba
  region: cn-hangzhou
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}

resources:
  orders-db:
    type: database
    external: true                 # required for database
    connection:
      host: pgm-xxxx.pg.rds.aliyuncs.com
      port: 5432
      database: orders
      user: pskitapp
      password_env: ORDERS_DB_PASSWORD
    functions: [api]

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /orders/count}]
    # options:                     # passed to alicloud_fcv3_function as-is (escape hatch)
    #   vpc_config: {...}          # VPC access: see the alicloud_fcv3_function docs; check with `terraform validate`
```

`functions.<fn>.options` is merged into the `alicloud_fcv3_function` resource unchanged, so use the argument names from
the [alicloud provider docs](https://registry.terraform.io/providers/aliyun/alicloud/latest/docs/resources/fcv3_function)
and verify them with `terraform validate` (`pskit package`, then `pskit tf -- validate`).

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`)

```python
import psycopg
from py_serverless_kit import resource


def api(event, ctx):
    db = resource("orders-db")
    with psycopg.connect(
        host=db["host"], port=int(db["port"]), dbname=db["database"], user=db["user"],
        password=ctx.env[db["password_env"]],
    ) as conn:
        count = conn.execute("select count(*) from orders").fetchone()[0]
    return {"orders": count}
```

## 5. Test

```bash
pskit validate
ORDERS_DB_PASSWORD=... pskit invoke -f api      # locally, against the public endpoint (whitelist your IP)
pskit deploy
pskit resources send --list                      # the variables and a ready-to-run snippet
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timeout from the function | the whitelist doesn't include the caller, or the function isn't in the VPC for an internal endpoint |
| Timeout locally | apply for a public endpoint and add your IP to the whitelist |
| `password authentication failed` | wrong account or password; check **Accounts** |
| `pskit does not create database resources` | add `external: true` |
