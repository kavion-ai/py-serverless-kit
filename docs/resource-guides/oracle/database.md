# OCI databases (`type: database`)

Autonomous Database and MySQL HeatWave. pskit never creates databases: declare them with `external: true` and pskit
hands their connection details to your functions.

## 1. Create the database (console)

**Autonomous Database:**

1. Console → **Oracle Database → Autonomous Database** → **Create Autonomous Database**.
2. Compartment, display and database name, workload type, ADMIN password.
3. **Network access**: *Secure access from allowed IPs and VCNs only* (add the functions' VCN) or *Private endpoint
   access only* in the functions' VCN. Turn off **Require mutual TLS (mTLS) authentication** so clients can connect
   with plain TLS and no wallet → **Create**.

**MySQL HeatWave:** Console → **Databases → MySQL HeatWave → DB Systems** → **Create DB system** → admin user and
password, the VCN and subnet (use the functions' VCN) → **Create**.

Open the DB port in the subnet's security list / NSG for the functions' subnet (`1521`/`1522` for Autonomous, `3306`
for MySQL).

## 2. Collect the values

| Value | Autonomous Database | MySQL HeatWave |
|---|---|---|
| Connection | details → **Database connection** → *TLS* connection string (for example the `_low` service) | DB system → **Connections** → *Private IP address* |
| Port | in the connection string (`1521`) | `3306` |
| User | `ADMIN` or an application user | the admin user or one you created |
| Password | set at creation | set at creation |

Store the password in [Vault](custom.md#vault-secrets) or pass it as an environment variable:

```bash
export ORDERS_DB_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: oracle
  region: us-ashburn-1
  options:
    compartment_id: ocid1.compartment.oc1..aaaa
    subnet_ids: [ocid1.subnet.oc1..aaaa]
    image: iad.ocir.io/axabc12345/orders:1.0
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}

resources:
  orders-db:
    type: database
    external: true
    connection:
      dsn: (description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1521)(host=adb.us-ashburn-1.oraclecloud.com))(connect_data=(service_name=abc_orders_low.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
      user: app
      password_env: ORDERS_DB_PASSWORD

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /orders/count}]
```

For MySQL use `host`, `port`, `database` and `user` instead of `dsn`.

## 4. Use it in a handler

`requirements.txt`: `oracledb` (MySQL: `pymysql`)

```python
import oracledb
from py_serverless_kit import resource


def api(event, ctx):
    db = resource("orders-db")
    with oracledb.connect(user=db["user"], password=ctx.env[db["password_env"]], dsn=db["dsn"]) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from orders")
            return {"orders": cur.fetchone()[0]}
```

`python-oracledb` runs in thin mode, so the image needs no Oracle Client libraries.

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send --list       # variables and a snippet for this database
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `DPY-6005` / timeout | the functions' VCN isn't in the ACL / private endpoint, or a security list blocks the port |
| `DPY-4011` / handshake errors | mTLS is still required: turn it off, or use a wallet |
| `ORA-01017` | wrong user / password |
