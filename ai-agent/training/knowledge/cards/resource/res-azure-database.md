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

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`; Azure SQL: `pymssql`)

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connection timed out` from the function | enable *Allow public access from any Azure service* (Networking) |
| `connection timed out` locally | add your client IP under **Networking → Firewall rules** |
| `no pg_hba.conf entry ... SSL off` | pass `sslmode=require` |
| pskit does not create database resources | add `external: true` |

```bash
export ORDERS_DB_PASSWORD='...'
```
