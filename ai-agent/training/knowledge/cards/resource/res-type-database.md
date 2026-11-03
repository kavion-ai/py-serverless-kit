# Resource: database

A database resource is a SQL or document store the functions query. Use it for orders, users, and any data that must stay after the invocation ends. pskit passes connection details. It leaves the database itself in place.

The schema requires `external: true` for `type: database`. A managed database is rejected with the message that pskit does not create that type. The guide index names Amazon RDS / Aurora, Azure PostgreSQL / MySQL / SQL, Cloud SQL, Alibaba ApsaraDB RDS / PolarDB, TencentDB, Huawei RDS, OCI Autonomous DB or MySQL HeatWave, IBM Databases for PostgreSQL / MySQL, DigitalOcean managed databases, Cloudflare D1 / Hyperdrive, and on-premises PostgreSQL / MySQL.

Declare `type: database`, `external: true`, and a `connection` map of scalars: `host`, `port`, `database`, `user`, and `password_env`. `password_env` is the name of a variable. Put the secret in `${env:ORDERS_DB_PASSWORD}` on the provider environment, or in the on-prem `env_file`. `functions` limits the binding. With the list omitted, every user function receives `PSKIT_RESOURCE_ORDERS_DB_*` for a key `orders-db`.

There is no database event. Call the database from an HTTP, queue, or schedule handler. The library table lists `psycopg[binary]` and `pg` for PostgreSQL, `pymysql` and `mysql2` for MySQL or MariaDB, and `pymongo` and `mongodb` for MongoDB. Read the password with `ctx.env[db["password_env"]]` in Python and `process.env[r.get("password_env")]` in Node.js. `resource("orders-db")["host"]` is the host string.

Open:

Resources > + Add resource

Resources > How to use

Resources > Test

The tester shows the variables and a snippet for a database. It sends messages for queues, buckets, and topics.

```
pskit resources usage orders-db -p aws -s dev
pskit resources send --list
pskit trigger -f api -e 0
```

On premises, a one-click database is still `type: database` with `external: true`, created with the on-prem service form. Cloud databases often sit on a private network. The function must be able to open that network, which each cloud guide describes.

Sources: `docs/resources.md#fields`, `docs/resource-usage.md#databases-caches-and-other-services`, `src/py_serverless_kit/config/schema.py`
