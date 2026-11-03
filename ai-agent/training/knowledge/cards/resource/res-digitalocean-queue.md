# Queues on DigitalOcean (`type: queue`)

DigitalOcean has **no managed queue service**, and pskit has no `queue` trigger on DigitalOcean. The usual replacement
is a Redis-compatible list in a **Managed Valkey** cluster: producers `LPUSH`, a `schedule` function pops a batch every
minute.

| Need | Option |
|---|---|
| Simple work queue | Managed Valkey list (this page) |
| Durable stream, many consumers | Managed Kafka, see topic.md |
| Messages handled the moment they arrive | the on-premises host with `driver: redis` on the same Valkey list |

## 1. Create the Valkey cluster (control panel)

1. Control panel → **Databases** → **Create Database Cluster** → engine **Valkey** (older accounts may show *Caching*
   / Redis).
2. Datacenter region, plan, cluster name → **Create Database Cluster**. Provisioning takes a few minutes.

## 2. Collect the values

| Value | Where in the control panel | Example |
|---|---|---|
| Connection string | cluster → **Overview** → **Connection details** → *Public network* → *Connection string* | `rediss://default:...@acme-valkey-do-user-0.db.ondigitalocean.com:25061` |
| Host / port / user / password | same panel, *Connection parameters* | `acme-valkey-do-user-0.db.ondigitalocean.com`, `25061`, `default` |
| Queue name | your choice: the Redis key of the list | `orders:jobs` |

TLS is required (`rediss://`).

## 4. Use it in a handler

`requirements.txt`: `redis`

`RPOP` removes the message before it is processed, so a crash loses it. For at-least-once handling use `LMOVE` to a
`<key>:processing` list and remove it after success (the layout the on-premises `redis` driver uses, described in
resources.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` DigitalOcean Functions does not support `queue` events in pskit `` | DigitalOcean has HTTP and schedule triggers only in pskit; use a `schedule` consumer |
| `rate ... can't be expressed as cron` | use a rate that divides 60 minutes (`1 minute`, `5 minutes`) |
| connection refused / timed out from the function | trusted sources on the cluster block it, see README |
| `SSL` errors | use the `rediss://` URL from *Public network* |

```bash
export JOBS_REDIS_URL='rediss://default:...@acme-valkey-do-user-0.db.ondigitalocean.com:25061'
```
