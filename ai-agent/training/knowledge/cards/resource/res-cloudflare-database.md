# Cloudflare databases (`type: database`)

From a Python Worker, use **D1** (Cloudflare's SQLite database) through a binding. PostgreSQL / MySQL drivers need TCP
sockets and native code that Pyodide doesn't provide, so a Python Worker can't connect to them directly; see
PostgreSQL with Hyperdrive.

`database` resources are always `external: true`: pskit only passes their details along.

### 1. Create the database (dashboard)

1. Dashboard → **Storage & databases → D1 SQL Database** (or **Workers & Pages → D1**) → **Create database**.
2. Name (for example `shop`), location hint optional → **Create**.
3. Database → **Console**: create tables, for example
   `CREATE TABLE orders (id INTEGER PRIMARY KEY, total REAL);`

### 2. Collect the values

| Value | Where | Example |
|---|---|---|
| Database name | **D1** → the list | `shop` |
| Database ID | database → **Overview** (or *Settings*) → *Database ID* | `00000000-0000-0000-0000-000000000000` |

### 3. Declare it in `pskit.yml`

The deploy API token needs **D1 Edit** in addition to Workers.

## PostgreSQL with Hyperdrive (Node.js)

Hyperdrive pools connections to an existing PostgreSQL (or MySQL) database. It works from **JavaScript / TypeScript**
Workers with a driver such as `pg` or `postgres` (bundled by pskit); not from Python Workers.

1. Dashboard → **Storage & databases → Hyperdrive** → **Create configuration** → name, then the database's
   host, port, database, user and password (or a connection string) → **Create**.
2. Copy the configuration **ID** from its overview.
3. Bind it. On a Node.js service `options.bindings` replaces the bindings pskit generates for environment variables
   (see README), so read the connection string from the binding rather
   than from `resource()`:

The database must accept connections from the internet (Hyperdrive connects from Cloudflare) or be exposed through a
Cloudflare Tunnel.

## Troubleshooting

| Symptom | Fix |
|---|---|
| pskit does not createdatabase` resources` | add `external: true` |
| `D1_ERROR: no such table` | create the table in the database's **Console** |
| `ModuleNotFoundError: psycopg` | Python Workers have no third-party packages; use D1, or a Node.js service with Hyperdrive |

```text
resources:
  shop-db:
    type: database
    external: true
    name: shop
    connection:
      binding: DB

functions:
  api:
    handler: app.handlers.api
    events: [{http: "GET /orders/{id}"}]
    options:
      bindings:
        - {type: d1, name: DB, id: 00000000-0000-0000-0000-000000000000}
```
