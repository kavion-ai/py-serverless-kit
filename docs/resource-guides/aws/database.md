# Amazon RDS / Aurora (`type: database`)

PostgreSQL or MySQL on Amazon RDS or Aurora. pskit never creates databases: declare them with `external: true` and pskit
hands their connection details to your functions.

## Networking first

An RDS instance lives in a VPC. pskit deploys Lambda functions **outside any VPC** unless you set
`functions.<fn>.options.vpc_config` (merged into `aws_lambda_function`). Pick one:

| Option | When | What to do |
|---|---|---|
| **Lambda in the VPC** (recommended) | private database | set `vpc_config` and the ENI permissions below; allow the Lambda security group in the database security group |
| Publicly accessible database | quick tests only | *Public access: Yes* and an inbound rule on 5432/3306; the Lambda has no fixed IP, so the rule must be wide open |

A Lambda in a VPC has no internet access and can't reach AWS APIs (SQS, S3, Secrets Manager, ...) unless the subnets
have a NAT gateway or VPC endpoints.

## 1. Create the database (console)

1. Console → **RDS** → **Databases** → **Create database** → *Standard create*.
2. Engine: *PostgreSQL* (or *MySQL*, *Aurora PostgreSQL/MySQL*), template, DB instance identifier.
3. **Credentials**: master username; either *Self managed* password or *Managed in AWS Secrets Manager*.
4. **Connectivity**: VPC, *Public access* (see above), VPC security group.
5. **Additional configuration** → *Initial database name* (for example `orders`) → **Create database**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host | the database → **Connectivity & security** → *Endpoint* (Aurora: the *Writer* endpoint) | `orders.abc123.eu-west-1.rds.amazonaws.com` |
| Port | **Connectivity & security** → *Port* | `5432` |
| Database | **Configuration** → *DB name* | `orders` |
| User | **Configuration** → *Master username* | `postgres` |
| Password | the one you set, or **Configuration** → *Master credentials ARN* (Secrets Manager) | |
| VPC, subnets, security group | **Connectivity & security** | `vpc-...`, `subnet-...`, `sg-...` |

```bash
export ORDERS_DB_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: aws
  region: eu-west-1
  environment:
    ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}
  iam:
    statements:                    # a Lambda in a VPC needs these to create its network interfaces
      - actions: [ec2:CreateNetworkInterface, ec2:DescribeNetworkInterfaces, ec2:DescribeSubnets,
                  ec2:DeleteNetworkInterface, ec2:AssignPrivateIpAddresses, ec2:UnassignPrivateIpAddresses]
        resources: ["*"]

resources:
  orders-db:
    type: database
    external: true
    connection:
      host: orders.abc123.eu-west-1.rds.amazonaws.com
      port: 5432
      database: orders
      user: postgres
      sslmode: require
      password_env: ORDERS_DB_PASSWORD
    functions: [api]

functions:
  api:
    handler: app.handlers.api
    events: [{http: GET /orders/count}]
    options:
      vpc_config:
        subnet_ids: [subnet-0aaa, subnet-0bbb]       # private subnets that can reach the database
        security_group_ids: [sg-0lambda]             # allowed by the database's security group
```

Then in the console: RDS database → **Connectivity & security** → its security group → **Edit inbound rules** →
*PostgreSQL* (5432), source `sg-0lambda`.

Password in Secrets Manager instead of an environment variable: put `secret_arn:` in `connection`, add
`secretsmanager:GetSecretValue` on that ARN to `iam.statements`, and read it as shown in [custom.md](custom.md#secrets-manager)
(needs a NAT gateway or a Secrets Manager VPC endpoint).

## 4. Use it in a handler

`requirements.txt`: `psycopg[binary]` (MySQL: `pymysql`)

```python
import psycopg
from py_serverless_kit import resource


def api(event, ctx):
    db = resource("orders-db")
    with psycopg.connect(
        host=db["host"], port=int(db["port"]), dbname=db["database"], user=db["user"],
        password=ctx.env[db["password_env"]], sslmode=db.get("sslmode", "require"),
    ) as conn:
        count = conn.execute("select count(*) from orders").fetchone()[0]
    return {"orders": count}
```

Many concurrent Lambdas can exhaust database connections; **RDS Proxy** (RDS → *Proxies*) pools them. Use the proxy
endpoint as `host`.

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
| Deploy: `The provided execution role does not have permissions to call CreateNetworkInterface on EC2` | add the `ec2:*NetworkInterface*` statement above |
| Function times out connecting | security group rule missing, or subnets can't route to the database |
| Function times out calling AWS APIs after adding `vpc_config` | add a NAT gateway or VPC endpoints |
| `too many connections` | use RDS Proxy, or limit `concurrency` on the function |
