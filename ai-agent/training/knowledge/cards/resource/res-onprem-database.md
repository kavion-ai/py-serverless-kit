# On-premises databases (`type: database`)

A database your functions use: a self-hosted PostgreSQL / MySQL server, or a cloud database the host can reach. pskit
never creates or watches databases: declare them with `external: true` and pskit hands their details to handlers.

## 1. Set up PostgreSQL

Skip what you already have.

- **Docker:** `docker run -d --name pg -p 5432:5432 -e POSTGRES_PASSWORD=<admin password> postgres:16`
- **Linux package:** `sudo apt install postgresql`

Create a database and a user for the functions:

If the host runs on another machine, let PostgreSQL accept it:

- `postgresql.conf`: `listen_addresses = '*'` (or the server's address),
- `pg_hba.conf`: `host  orders  pskitapp  192.0.2.10/24  scram-sha-256` (the host's subnet),
- `sudo systemctl restart postgresql`, and open port 5432 in the firewall.

With pgAdmin: right-click *Login/Group Roles → Create*, then *Databases → Create → Database* with that owner.

## 2. Collect the values

| Value | Example |
|---|---|
| Host / port | `db.internal` / `5432` |
| Database | `orders` |
| User / password | `pskitapp` / `s3cret` |

Test from the host machine: `psql "postgresql://pskitapp@db.internal:5432/orders" -c 'select 1'`.

## 3. Declare it in `pskit.yml`

`options.driver` is not used for databases (validation error).

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`). Dependencies are installed on premises.

The host is a long-running process, so a module-level connection pool (`psycopg_pool.ConnectionPool`) is reused across
invocations.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `KeyError: 'ORDERS_DB_PASSWORD'` | export it where the host runs (see README) |
| `connection refused` | `listen_addresses`, the firewall, or the port |
| `no pg_hba.conf entry for host` | add a `pg_hba.conf` line for the host's address and reload PostgreSQL |
| pskit does not create database resources | add `external: true` |

An address or login copied from the source was rewritten in this card. Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.

```bash
sudo -u postgres psql        # Docker: docker exec -it pg psql -U postgres
```
