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

```bash
export ORDERS_DB_PASSWORD='...'
export ORDERS_DB_CA_B64='LS0tLS1CRUdJTi...'   # the base64 certificate, one line
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: ibm
  region: us-south
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}
    ORDERS_DB_CA_B64: ${env:ORDERS_DB_CA_B64}

resources:
  orders-db:
    type: database
    external: true
    connection:
      host: xxxx.databases.appdomain.cloud
      port: 31234
      database: ibmclouddb
      user: admin
      password_env: ORDERS_DB_PASSWORD
      ca_cert_env: ORDERS_DB_CA_B64

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /orders}]
```

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`)

```python
import base64
import os
import tempfile

import psycopg
from py_serverless_kit import resource


def api(event, ctx):
    db = resource("orders-db")
    ca_path = os.path.join(tempfile.gettempdir(), "orders-db-ca.pem")
    if not os.path.exists(ca_path):
        with open(ca_path, "wb") as f:
            f.write(base64.b64decode(ctx.env[db["ca_cert_env"]]))
    with psycopg.connect(
        host=db["host"], port=int(db["port"]), dbname=db["database"], user=db["user"],
        password=ctx.env[db["password_env"]], sslmode="verify-full", sslrootcert=ca_path,
    ) as conn:
        count = conn.execute("select count(*) from orders").fetchone()[0]
    return {"orders": count}
```

## 5. Test

```bash
pskit validate
pskit invoke -f api            # locally, against the real database
pskit deploy
pskit resources send --list    # the PSKIT_RESOURCE_* variables and a snippet
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `certificate verify failed` | pass the instance's CA certificate as `sslrootcert` |
| connection timed out | the instance has only a *Private* endpoint; enable *Public*, or check **Settings → Allowlist** |
| `pskit does not create database resources` | add `external: true` |
