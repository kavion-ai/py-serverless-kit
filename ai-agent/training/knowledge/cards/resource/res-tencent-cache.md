# Tencent Cloud Redis (`type: cache`)

TencentDB for Redis. pskit never creates caches: declare them with `external: true`.

## 1. Create the instance (console)

1. Console → **TencentDB for Redis** → **Instance List** → **Create**: region, version, architecture, specification,
   **VPC** and subnet, password → buy.
2. Network access: TencentDB for Redis is reached through its **VPC** address. Run the function in the same VPC and
   subnet (`vpc_id` / `subnet_id` function options, see database.md) and allow
   the subnet in the instance's security group. Some versions also offer a public network address in **Instance
   Details**; check your console.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host / port | instance → **Instance Details** → *Private Network Address* | `192.0.2.10:6379` |
| Password | set at creation (**Account Management** → reset). For an account other than the default one, use the format shown in the console's connection example | `...` |
| VPC / subnet IDs | **Instance Details** → *Network* | `vpc-xxxx` / `subnet-xxxx` |

## 4. Use it in a handler

`requirements.txt`: `redis`

## 5. Test

Console: instance → **Log in to database** (DMC) to run `GET hits`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timeout | the function isn't in the instance's VPC / subnet, or the security group blocks it |
| `WRONGPASS` / `invalid password` | check the password format for non-default accounts in the console |

An address or login copied from the source was rewritten in this card. Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.

```bash
export CACHE_PASSWORD='...'
```
