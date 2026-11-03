# Huawei DCS for Redis (`type: cache`)

Distributed Cache Service (DCS) for Redis. pskit never creates caches: declare them with `external: true`.

## 1. Create the instance (console)

1. Console → **Distributed Cache Service for Redis** → **Buy DCS Instance**.
2. Region (same as the functions), Redis version, instance type, capacity; **VPC** and **subnet**; password (or
   password-free access, not recommended) → **Submit**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host | instance → **Basic Information** → *Connection* → *Connection Address* (or *Domain Name Address*) | `redis-abc.dcs.huaweicloud.com` |
| Port | same panel | `6379` |
| Password | set when buying (reset with **More → Reset Password**) | |
| VPC / subnet | **Basic Information** → *Network* | |

## 4. Use it in a handler

`requirements.txt`: `redis`

## 5. Test

Console: DCS instance → **Connect to Redis** (Web CLI) → `GET hits`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timed out | function not in the instance's VPC (`vpc_id` / `network_id`, agency with VPC permissions) |
| `NOAUTH` / `WRONGPASS` | password changed: update `CACHE_PASSWORD` and redeploy |

```bash
export CACHE_PASSWORD='...'
```
