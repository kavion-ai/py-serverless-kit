# Huawei RDS (`type: database`)

RDS for MySQL / PostgreSQL / SQL Server. pskit never creates databases: declare them with `external: true` and pskit
hands their connection details to your functions.

## 1. Create the instance (console)

1. Console → **Relational Database Service** → **Buy DB Instance**.
2. Region (same as the functions), DB engine and version, instance class, storage; **VPC**, **subnet** and
   **security group**; administrator password → **Buy Now**.
3. Instance → **Databases** → **Create Database** (for example `orders`), and **Accounts** → **Create Account** for an
   application user.
4. **Security group**: allow the DB port from the subnet the functions use.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host | instance → **Overview** → *Connection Information* → *Floating IP Address* (private) | `192.0.2.10` |
| Port | same panel → *Database Port* | `3306` (PostgreSQL `5432`) |
| Database | instance → **Databases** | `orders` |
| User | instance → **Accounts** | `app` |
| VPC / subnet | **Overview** → *Connection Information* | `vpc-…` / `subnet-…` |
| Public address (optional) | **Overview** → *EIP* → **Bind** | |

## 4. Use it in a handler

`requirements.txt`: `pymysql` (PostgreSQL: `pg8000`)

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timed out | `vpc_id` / `network_id` missing, agency lacks VPC permissions, or the security group blocks the port |
| `Access denied for user` | wrong user / password, or the account isn't allowed from the function's subnet |

An address or login copied from the source was rewritten in this card. Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.

```bash
export ORDERS_DB_PASSWORD='...'
```
