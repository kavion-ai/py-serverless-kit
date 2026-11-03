# DigitalOcean Managed databases (`type: database`)

Managed PostgreSQL and MySQL. pskit never creates databases: declare them with `external: true` and pskit hands their
connection details to your functions.

## 1. Create the cluster (control panel)

1. Control panel → **Databases** → **Create Database Cluster** → engine **PostgreSQL** (or **MySQL**) → version,
   datacenter region, plan, name → **Create Database Cluster**.
2. In the cluster → **Users & Databases** → **Add new database** (for example `orders`) and, optionally,
   **Add new user** for the application.

## 2. Collect the values

| Value | Where in the control panel | Example |
|---|---|---|
| Host / port | cluster → **Overview** → **Connection details** → *Public network* | `acme-pg-do-user-0.db.ondigitalocean.com`, `25060` |
| Database | same panel (choose it in the *Database* drop-down) | `orders` (default `defaultdb`) |
| User / password | same panel (*User* drop-down), or **Users & Databases** | `doadmin` / `...` |
| SSL | required (`sslmode=require`); **Download CA certificate** for `verify-full` | |

```bash
export ORDERS_DB_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: digitalocean
  region: nyc1
  options:
    namespace: fn-00000000-0000-0000-0000-000000000000
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}

resources:
  orders-db:
    type: database
    external: true
    connection:
      host: acme-pg-do-user-0.db.ondigitalocean.com
      port: 25060
      database: orders
      user: doadmin
      sslmode: require
      password_env: ORDERS_DB_PASSWORD

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /orders}]
```

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`)

```python
import psycopg
from py_serverless_kit import resource


def api(event, ctx):
    db = resource("orders-db")
    with psycopg.connect(
        host=db["host"], port=int(db["port"]), dbname=db["database"], user=db["user"],
        password=ctx.env[db["password_env"]], sslmode=db.get("sslmode", "require"),
    ) as conn:
        count = conn.execute("select count(*) from orders").fetchone()[0]
    return {"orders": count}
```

Functions open a new connection per cold start. If you expect many concurrent invocations, create a **Connection
Pool** (cluster → **Connection Pools**) and use its host / port / database instead.

## 5. Test

```bash
pskit validate
pskit invoke -f api            # locally, against the real cluster
pskit deploy
pskit resources send --list    # the PSKIT_RESOURCE_* variables and a snippet
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| timed out from the function | trusted sources block it, see [README](README.md#values-you-need-for-most-digitalocean-services) |
| `too many connections` | use a connection pool |
| `pskit does not create database resources` | add `external: true` |
