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

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`)

Functions open a new connection per cold start. If you expect many concurrent invocations, create a **Connection
Pool** (cluster → **Connection Pools**) and use its host / port / database instead.

## Troubleshooting

| Symptom | Fix |
|---|---|
| timed out from the function | trusted sources block it, see README |
| `too many connections` | use a connection pool |
| pskit does not create database resources | add `external: true` |

```bash
export ORDERS_DB_PASSWORD='...'
```
