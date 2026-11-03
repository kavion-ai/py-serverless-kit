# Azure databases (`type: database`)

Azure Database for PostgreSQL / MySQL (flexible server) and Azure SQL Database. pskit never creates databases: declare
them with `external: true` and pskit hands their connection details to your functions.

## 1. Create the server (portal)

**PostgreSQL** (MySQL is the same with *Azure Database for MySQL flexible servers*):

1. Portal → **Azure Database for PostgreSQL flexible servers** → **+ Create**.
2. Resource group, server name, region, version, workload type; **Authentication**: *PostgreSQL authentication only*
   (or *both*), admin username and password.
3. **Networking** tab: *Public access*, tick **Allow public access from any Azure service within Azure to this server**
   (the Consumption Function App has no fixed outbound IP and no VNet), and **+ Add current client IP address** for
   your own machine → **Review + create**.
4. Open the server → **Settings → Databases** → **+ Add** → database name (for example `orders`).

**Azure SQL**: Portal → **SQL databases** → **+ Create** → create a server with SQL authentication; on **Networking**
choose *Public endpoint* and set **Allow Azure services and resources to access this server** to *Yes*.

## 2. Collect the values

| Value | PostgreSQL / MySQL | Azure SQL |
|---|---|---|
| Host | Server → **Overview** → *Server name* (`acme-pg.postgres.database.azure.com`) | Database → **Overview** → *Server name* (`acme-sql.database.windows.net`) |
| Port | `5432` (MySQL `3306`) | `1433` |
| Database | Server → **Settings → Databases** | Database → **Overview** → title |
| User | Server → **Overview** → *Administrator login* (or a user you created) | Server → *Server admin* |
| Password | the one you set (reset with **Overview → Reset password**) | the one you set |
| SSL | required by default (`sslmode=require`) | always encrypted |
| Connection strings | Server → **Settings → Connect** | Database → **Settings → Connection strings** |

```bash
export ORDERS_DB_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: azure
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}   # becomes an app setting

resources:
  orders-db:
    type: database
    external: true                   # required for database
    connection:
      host: acme-pg.postgres.database.azure.com
      port: 5432
      database: orders
      user: pskitapp
      sslmode: require
      password_env: ORDERS_DB_PASSWORD               # the setting's NAME
    functions: [api]                 # optional: only these functions get it
```

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`; Azure SQL: `pymssql`)

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

## 5. Test

```bash
pskit validate
ORDERS_DB_PASSWORD=... pskit invoke -f api       # locally, against the real server (your IP must be allowed)
pskit deploy
pskit resources send --list                       # prints the variables and a ready-to-run snippet
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connection timed out` from the function | enable *Allow public access from any Azure service* (Networking) |
| `connection timed out` locally | add your client IP under **Networking → Firewall rules** |
| `no pg_hba.conf entry ... SSL off` | pass `sslmode=require` |
| `pskit does not create database resources` | add `external: true` |
