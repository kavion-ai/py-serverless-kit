# Tencent Cloud databases (`type: database`)

TencentDB for MySQL, PostgreSQL and SQL Server. pskit never creates databases: declare them with `external: true` and
pskit hands their connection details to your functions.

## 1. Create the instance (console)

**TencentDB for MySQL** (PostgreSQL and SQL Server are similar in their own consoles):

1. Console → **TencentDB for MySQL** → **Instance List** → **Create**: region, version, architecture, specification,
   **VPC** and subnet, security group, root password → buy.
2. Open the instance → **Database Management** → **Account Management** → **Create Account** (for example `pskitapp`,
   host `%`), and **Database List** → **Create Database** (for example `orders`); grant the account on it.
3. Network access, pick one:
   - **VPC** (recommended): run the function in the same VPC and subnet with the `vpc_id` / `subnet_id` function
     options (below), and allow the subnet in the instance's **Security Group**.
   - **Public network**: **Instance Details** → *Public Network Address* → **Enable**, and allow the callers in the
     security group. SCF has no fixed outbound IP without a VPC/NAT setup.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host / port | instance → **Instance Details** → *Private Network Address* (VPC) or *Public Network Address* | `10.0.0.12:3306` / `gz-cdb-xxxx.sql.tencentcdb.com:12345` |
| Database | **Database Management → Database List** | `orders` |
| User / password | **Database Management → Account Management** (reset password there) | `pskitapp` |
| VPC / subnet IDs | **Instance Details** → *Network* | `vpc-xxxx` / `subnet-xxxx` |

```bash
export ORDERS_DB_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: tencent
  region: ap-guangzhou
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}

resources:
  orders-db:
    type: database
    external: true                 # required for database
    connection:
      host: 10.0.0.12
      port: 3306
      database: orders
      user: pskitapp
      password_env: ORDERS_DB_PASSWORD
    functions: [api]

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /orders/count}]
    options:                       # merged into tencentcloud_scf_function as-is
      vpc_id: vpc-xxxx
      subnet_id: subnet-xxxx
```

## 4. Use it in a handler

`requirements.txt`: `pymysql` (PostgreSQL: `psycopg[binary]`)

```python
import pymysql
from py_serverless_kit import resource


def api(event, ctx):
    db = resource("orders-db")
    conn = pymysql.connect(host=db["host"], port=int(db["port"]), user=db["user"],
                           password=ctx.env[db["password_env"]], database=db["database"])
    with conn, conn.cursor() as cur:
        cur.execute("select count(*) from orders")
        return {"orders": cur.fetchone()[0]}
```

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send --list       # the variables and a ready-to-run snippet
```

Running it locally (`pskit invoke -f api`) needs the public network address and your IP allowed in the security group.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timeout from the function | set `vpc_id` / `subnet_id`, or enable the public address; check the security group |
| `Access denied for user` | account host or password wrong; the account needs rights on the database |
| `pskit does not create database resources` | add `external: true` |
