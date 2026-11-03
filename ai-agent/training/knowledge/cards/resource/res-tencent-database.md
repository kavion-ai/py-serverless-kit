# Tencent Cloud databases (`type: database`)

TencentDB for MySQL, PostgreSQL and SQL Server. pskit never creates databases: declare them with `external: true` and
pskit hands their connection details to your functions.

## 1. Create the instance (console)

**TencentDB for MySQL** (PostgreSQL and SQL Server are similar in their own consoles):

1. Console → **TencentDB for MySQL** → **Instance List** → **Create**: region, version, architecture, specification,
   **VPC** and subnet, security group, root password → buy.
2. Open the instance → **Database Management** → **Account Management** → **Create Account** (for example `pskitapp`,
   host `%`), and **Database List** → **Create Database** (for example `orders`); grant the account on it.
3. Network access, pick one:
   - **VPC** (recommended): run the function in the same VPC and subnet with the `vpc_id` / `subnet_id` function
     options (below), and allow the subnet in the instance's **Security Group**.
   - **Public network**: **Instance Details** → *Public Network Address* → **Enable**, and allow the callers in the
     security group. SCF has no fixed outbound IP without a VPC/NAT setup.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host / port | instance → **Instance Details** → *Private Network Address* (VPC) or *Public Network Address* | `192.0.2.10:3306` / `gz-cdb-xxxx.sql.tencentcdb.com:12345` |
| Database | **Database Management → Database List** | `orders` |
| User / password | **Database Management → Account Management** (reset password there) | `pskitapp` |
| VPC / subnet IDs | **Instance Details** → *Network* | `vpc-xxxx` / `subnet-xxxx` |

## 4. Use it in a handler

`requirements.txt`: `pymysql` (PostgreSQL: `psycopg[binary]`)

## 5. Test

Running it locally (`pskit invoke -f api`) needs the public network address and your IP allowed in the security group.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timeout from the function | set `vpc_id` / `subnet_id`, or enable the public address; check the security group |
| `Access denied for user` | account host or password wrong; the account needs rights on the database |
| pskit does not create database resources | add `external: true` |

An address or login copied from the source was rewritten in this card. Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.

```bash
export ORDERS_DB_PASSWORD='...'
```
