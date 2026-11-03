# Cloud SQL (`type: database`)

PostgreSQL, MySQL or SQL Server on Cloud SQL. pskit never creates databases: declare them with `external: true` and
pskit hands their connection details to your functions.

pskit's Cloud Functions don't run in a VPC, so the simplest path is a **public IP** instance reached through the
**Cloud SQL Python Connector**: it authenticates with the function's service account and encrypts the connection,
with no authorized networks to open. A private-IP-only instance needs a Serverless VPC Access connector, added as shown
in [cache.md](cache.md#3-declare-it-in-pskityml).

## 1. Create the instance (console)

1. Console → **SQL** → **Create instance** → *PostgreSQL* (or MySQL / SQL Server).
2. Instance ID, password for the default user (`postgres`), region (ideally `provider.region`), edition.
3. **Connections** → *Public IP* ticked (no authorized networks needed for the connector).
4. **Create instance**. Then open it → **Databases** → **Create database** → `orders`.
5. Optional: **Users** → **Add user account** → a dedicated user for the app.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Connection name | the instance → **Overview** → *Connect to this instance* → *Connection name* | `my-project:europe-west1:orders-pg` |
| Public IP | **Overview** → *Public IP address* | `34.76.1.2` |
| Database | **Databases** | `orders` |
| User | **Users** | `pskitapp` |
| Password | the one you set (**Users** → ⋮ → *Change password*) | |

```bash
export ORDERS_DB_PASSWORD='...'
```

Grant the runtime service account **Cloud SQL Client**: **IAM & Admin → IAM** → **Grant access** → the service account
→ role *Cloud SQL Client*. Enable the **Cloud SQL Admin API** (the connector uses it).

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: gcp
  region: europe-west1
  options:
    project: my-project
    service_account: orders-runtime@my-project.iam.gserviceaccount.com
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}

resources:
  orders-db:
    type: database
    external: true
    connection:
      instance: my-project:europe-west1:orders-pg
      database: orders
      user: pskitapp
      password_env: ORDERS_DB_PASSWORD
    functions: [api]

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /orders/count}]
```

The password still ends up in Terraform state through `${env:...}`. To avoid that, store it in Secret Manager and read
it at run time ([custom.md](custom.md#secret-manager)).

## 4. Use it in a handler

`requirements.txt`: `cloud-sql-python-connector[pg8000]` (MySQL: `[pymysql]`)

```python
from google.cloud.sql.connector import Connector
from py_serverless_kit import resource

_connector = None


def api(event, ctx):
    global _connector
    if _connector is None:
        _connector = Connector()
    db = resource("orders-db")
    conn = _connector.connect(
        db["instance"], "pg8000", user=db["user"], password=ctx.env[db["password_env"]], db=db["database"]
    )
    try:
        cur = conn.cursor()
        cur.execute("select count(*) from orders")
        return {"orders": cur.fetchone()[0]}
    finally:
        conn.close()
```

## 5. Test

```bash
pskit validate
pskit deploy
pskit trigger -f api -e 0
pskit resources send --list       # the variables and a ready-to-run snippet
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `403 ... cloudsql.instances.get` | grant **Cloud SQL Client** to the runtime service account |
| `Cloud SQL Admin API has not been used` | enable the Cloud SQL Admin API |
| Timeout with a private-IP-only instance | add a public IP, or a VPC connector (see [cache.md](cache.md)) |
| `password authentication failed` | wrong user/password; reset it under **Users** |
