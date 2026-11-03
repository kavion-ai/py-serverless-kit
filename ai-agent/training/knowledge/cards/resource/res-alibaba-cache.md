# Alibaba Cloud Tair / Redis (`type: cache`)

Tair (Redis OSS-compatible), formerly ApsaraDB for Redis. pskit never creates caches: declare them with
`external: true`.

## 1. Create the instance (console)

1. Console → **Tair (Redis OSS-Compatible)** → **Instances** → **Create Instance**: region, edition, engine version,
   architecture, **VPC** and vSwitch, password for the default account → buy.
2. Network access, pick one:
   - **Public endpoint**: instance → **Connection Information** → **Apply for Public Endpoint**, then
     **Whitelist Settings** to allow the callers.
   - **VPC** (recommended): run the function in the same VPC (`vpc_config` function option, see
     database.md) and whitelist the vSwitch CIDR.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Host | instance → **Connection Information** → *VPC endpoint* or *Public endpoint* | `r-xxxx.redis.rds.aliyuncs.com` |
| Port | **Connection Information** | `6379` |
| Password | set at creation (**Account Management** → reset). For an account other than the default one, the password is `<user>:<password>` | `...` |
| TLS | **TLS Settings** (off by default) | |

## 4. Use it in a handler

`requirements.txt`: `redis`

Booleans in `connection` arrive as the strings `"true"` / `"false"`.

## 5. Test

Console: instance → **Logon Database** (DMS) to run `GET hits`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Connection timeout | whitelist the caller, or use the VPC endpoint from inside the VPC |
| `WRONGPASS` / `invalid password` | for a non-default account the password is `<user>:<password>` |

```bash
export CACHE_PASSWORD='...'
```
