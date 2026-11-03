# 03 · Scheduled jobs

Shows cron and rate schedules with input payloads, time zones, schedules you can disable,
and a long job that stops gracefully before its timeout.

## Schedule syntax

| YAML | Meaning |
| --- | --- |
| `- schedule: 5 minutes` | every 5 minutes (`minute(s)`, `hour(s)`, `day(s)`) |
| `- schedule: "0 9 * * 1-5"` | standard 5-field cron |
| `input: {...}` | delivered to the handler as `event.data` |
| `timezone: Europe/Berlin` | IANA zone for cron evaluation |
| `enabled: false` | keep the trigger but pause it |

You always write **standard** cron. pskit translates it per cloud:

| Cloud | `cron: "0 9 * * 1-5"` becomes |
| --- | --- |
| AWS EventBridge Scheduler | `cron(0 9 ? * 2-6 *)` (day-of-week 1-7, `?` rules) |
| GCP Cloud Scheduler | `0 9 * * 1-5` |
| Azure timer trigger | `0 0 9 * * 1-5` (seconds first) |
| Alibaba / Huawei | `0 0 9 * * 1-5` |
| Tencent | `0 0 9 * * 1-5 *` |

**Time zones** are honoured on AWS and GCP. Azure Linux consumption plans run timers in UTC,
so set the cron in UTC there (use a `providers.azure` override if needed).

**Rates** must convert to cron on clouds that only accept cron, so use a divisor of 60
minutes or 24 hours (`5 minutes`, `6 hours`, ...). `pskit validate` flags rates that don't
convert.

## Run locally

```bash
pskit invoke -f daily-report          # uses the first schedule's `input` automatically
pskit invoke -f daily-report -d '{"report": "adhoc", "days": 3}'
pskit invoke -f cleanup
```

Expected (abridged):

```json
{"report": "sales", "recipients": ["finance@example.com"],
 "period": ["2026-10-14T00:00:00+00:00", "2026-10-15T00:00:00+00:00"], "generated_at": "..."}
```

## Deploy

```bash
pskit deploy                     # EventBridge Scheduler -> Lambda
pskit deploy --provider gcp      # Cloud Scheduler -> Cloud Function (OIDC-authenticated)
pskit deploy --provider azure    # timer triggers in a Function App
```

Turn the cleanup off in one stage without touching code: `CLEANUP_ENABLED=false pskit deploy`.
