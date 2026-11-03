# Huawei RDS (`type: database`)

RDS for MySQL / PostgreSQL / SQL Server. pskit never creates databases: declare them with `external: true` and pskit
hands their connection details to your functions.

## 1. Create the instance (console)

1. Console → **Relational Database Service** → **Buy DB Instance**.
2. Region (same as the functions), DB engine and version, instance class, storage; **VPC**, **subnet** and
   **security group**; administrator password → **Buy Now**.
3. Instance → **Databases** → **Create Database** (for example `orders`), and **Accounts** → **Create Account** for an
   application user.
4. **Security group**: allow the DB port from the subnet the functions use.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host | instance → **Overview** → *Connection Information* → *Floating IP Address* (private) | `192.168.0.20` |
| Port | same panel → *Database Port* | `3306` (PostgreSQL `5432`) |
| Database | instance → **Databases** | `orders` |
| User | instance → **Accounts** | `app` |
| VPC / subnet | **Overview** → *Connection Information* | `vpc-…` / `subnet-…` |
| Public address (optional) | **Overview** → *EIP* → **Bind** | |

```bash
export ORDERS_DB_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: huawei
  region: cn-north-4
  options:
    apig_instance_id: 0123456789abcdef0123456789abcdef
  iam:
    role: pskit-functions                     # agency with VPC permissions
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}

resources:
  orders-db:
    type: database
    external: true
    connection:
      host: 192.168.0.20
      port: 3306
      database: orders
      user: app
      password_env: ORDERS_DB_PASSWORD

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /orders/count}]
    options:                                  # join the database's VPC
      vpc_id: 11111111-2222-3333-4444-555555555555
      network_id: 66666666-7777-8888-9999-000000000000
```

## 4. Use it in a handler

`requirements.txt`: `pymysql` (PostgreSQL: `pg8000`)

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
pskit resources send --list       # variables and a snippet for this database
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timed out | `vpc_id` / `network_id` missing, agency lacks VPC permissions, or the security group blocks the port |
| `Access denied for user` | wrong user / password, or the account isn't allowed from the function's subnet |
