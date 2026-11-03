# Resource: AWS RDS or Aurora

On AWS, `type: database` is Amazon RDS or Aurora (PostgreSQL, MySQL, or Aurora PostgreSQL/MySQL). pskit requires `external: true` and passes host, port, database, user, and the name of the password variable. It leaves the database in place.

RDS lives in a VPC. pskit deploys Lambda outside any VPC unless the function sets `options.vpc_config` (`subnet_ids` and `security_group_ids`), which is merged into `aws_lambda_function`. For a private database, put the function in the VPC, add the ENI actions the guide lists (`ec2:CreateNetworkInterface`, `DescribeNetworkInterfaces`, `DescribeSubnets`, `DeleteNetworkInterface`, `AssignPrivateIpAddresses`, `UnassignPrivateIpAddresses`) under `provider.iam.statements`, and allow that security group on the database security group inbound rule for 5432 or 3306. A function in a VPC reaches other AWS APIs when the subnets have a NAT gateway or VPC endpoints. A publicly accessible database is described in the guide as a quick test, with a wide inbound rule, because the Lambda has no fixed IP.

Collect the endpoint (Aurora: the writer endpoint), port, DB name, master username, and either the password or the Secrets Manager credentials ARN. Store the password as `ORDERS_DB_PASSWORD: ${env:ORDERS_DB_PASSWORD}` and set `connection.password_env` to that name. `sslmode: require` is in the guide's connection map. `functions` can list only the handlers that should see the binding.

`requirements.txt` gets `psycopg[binary]` for PostgreSQL or `pymysql` for MySQL. Connect with `host`, `port`, `dbname`, `user`, and `password=ctx.env[db["password_env"]]`. Many concurrent Lambdas can exhaust connections. RDS Proxy pools them. Use the proxy endpoint as `host`. A password in Secrets Manager uses `secret_arn` plus `secretsmanager:GetSecretValue`, and the function still needs a path to Secrets Manager.

Open:

Resources > + Add resource

Resources > How to use

```
pskit validate
pskit trigger -f api -e 0
pskit resources send --list
```

`pskit resources send --list` prints the variables and a snippet. It sends messages for queues, buckets, and topics.

Sources: `docs/resource-guides/aws/database.md#amazon-rds-aurora-type-database`, `docs/resource-guides/aws/database.md#networking-first`
