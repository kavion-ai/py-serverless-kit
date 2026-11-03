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

Store the password in Vault or pass it as an environment variable:

## 3. Declare it in `pskit.yml`

For MySQL use `host`, `port`, `database` and `user` instead of `dsn`.

## 4. Use it in a handler

`requirements.txt`: `oracledb` (MySQL: `pymysql`)

`python-oracledb` runs in thin mode, so the image needs no Oracle Client libraries.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `DPY-6005` / timeout | the functions' VCN isn't in the ACL / private endpoint, or a security list blocks the port |
| `DPY-4011` / handshake errors | mTLS is still required: turn it off, or use a wallet |
| `ORA-01017` | wrong user / password |

```bash
export ORDERS_DB_PASSWORD='...'
```
