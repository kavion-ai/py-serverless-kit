# IBM Cloud databases (`type: database`)

Databases for PostgreSQL and Databases for MySQL. pskit never creates databases: declare them with `external: true` and
pskit hands their connection details to your functions.

## 1. Create the instance (console)

1. Console → **Catalog** → **Databases for PostgreSQL** (or **Databases for MySQL**) → region, plan, resources →
   *Endpoints*: **Public** (or *Both*) → **Create**. Provisioning takes several minutes.
2. In the instance → **Settings** → **Change Database Admin password** (the admin user is `admin`), or create a user
   with **Service credentials → New credential** (it gets its own user and password).

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host / port | instance → **Overview** → **Endpoints** → *PostgreSQL* tab → *Public* | `xxxx.databases.appdomain.cloud`, `31234` |
| Database | same tab → *Database* | `ibmclouddb` |
| User / password | the admin password you set, or **Service credentials** → `connection.postgres.authentication` | `admin` / `...` |
| CA certificate | **Endpoints** tab → *TLS certificate* (or the credential's `connection.postgres.certificate.certificate_base64`) | base64 text |

IBM Cloud Databases use a self-signed CA: the client must trust that certificate (`sslmode=verify-full` with
`sslrootcert`).

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`)

## Troubleshooting

| Symptom | Fix |
|---|---|
| `certificate verify failed` | pass the instance's CA certificate as `sslrootcert` |
| connection timed out | the instance has only a *Private* endpoint; enable *Public*, or check **Settings → Allowlist** |
| pskit does not create database resources | add `external: true` |

```bash
export ORDERS_DB_PASSWORD='...'
export ORDERS_DB_CA_B64='LS0tLS1CRUdJTi...'   # the base64 certificate, one line
```
