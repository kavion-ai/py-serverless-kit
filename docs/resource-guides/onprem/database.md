# On-premises databases (`type: database`)

A database your functions use: a self-hosted PostgreSQL / MySQL server, or a cloud database the host can reach. pskit
never creates or watches databases: declare them with `external: true` and pskit hands their details to handlers.

## 1. Set up PostgreSQL

Skip what you already have.

- **Docker:** `docker run -d --name pg -p 5432:5432 -e POSTGRES_PASSWORD=<admin password> postgres:16`
- **Linux package:** `sudo apt install postgresql`

Create a database and a user for the functions:

```bash
sudo -u postgres psql        # Docker: docker exec -it pg psql -U postgres
```

```sql
CREATE USER pskitapp WITH PASSWORD 's3cret';
CREATE DATABASE orders OWNER pskitapp;
```

If the host runs on another machine, let PostgreSQL accept it:

- `postgresql.conf`: `listen_addresses = '*'` (or the server's address),
- `pg_hba.conf`: `host  orders  pskitapp  10.0.0.0/24  scram-sha-256` (the host's subnet),
- `sudo systemctl restart postgresql`, and open port 5432 in the firewall.

With pgAdmin: right-click *Login/Group Roles → Create*, then *Databases → Create → Database* with that owner.

## 2. Collect the values

| Value | Example |
|---|---|
| Host / port | `db.internal` / `5432` |
| Database | `orders` |
| User / password | `pskitapp` / `s3cret` |

Test from the host machine: `psql "postgresql://pskitapp@db.internal:5432/orders" -c 'select 1'`.

```bash
export ORDERS_DB_PASSWORD='s3cret'      # in the host's environment
```

## 3. Declare it in `pskit.yml`

```yaml
resources:
  orders-db:
    type: database
    external: true                       # required for database
    connection:
      host: db.internal
      port: 5432
      database: orders
      user: pskitapp
      password_env: ORDERS_DB_PASSWORD   # the NAME of the variable, never the password
    functions: [api, worker]             # optional: only these functions get it
```

`options.driver` is not used for databases (validation error).

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`). Dependencies are installed on premises.

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

The host is a long-running process, so a module-level connection pool (`psycopg_pool.ConnectionPool`) is reused across
invocations.

## 5. Test

```bash
pskit validate
ORDERS_DB_PASSWORD=s3cret pskit invoke -f api
pskit deploy
pskit resources send --list          # the PSKIT_RESOURCE_ORDERS_DB_* variables and a snippet
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `KeyError: 'ORDERS_DB_PASSWORD'` | export it where the host runs (see [README](README.md#secrets-name_env)) |
| `connection refused` | `listen_addresses`, the firewall, or the port |
| `no pg_hba.conf entry for host` | add a `pg_hba.conf` line for the host's address and reload PostgreSQL |
| `pskit does not create database resources` | add `external: true` |
