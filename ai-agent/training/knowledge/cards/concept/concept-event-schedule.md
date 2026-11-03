# Concept: schedule events

A schedule is a rate or a cron, not both. Shorthand `- schedule: 5 minutes` is a rate. Shorthand `- schedule: "0 3 * * *"` is a 5-field cron. The long form uses exactly one of `rate` or `cron`, plus optional `input`, `timezone` (default UTC), `enabled` (default true), and `name`. A rate looks like `<n> minute(s)|hour(s)|day(s)`. The handler gets `event.type == "schedule"` and `event.data` equal to `input`.

pskit converts that syntax per cloud. AWS uses EventBridge Scheduler (`rate(5 minutes)` or cron with a day-of-week conversion and `?`). GCP Cloud Scheduler uses 5-field cron, and rates become cron such as `*/5 * * * *`. Azure uses a 6-field NCRONTAB and is always UTC on Linux Consumption. Alibaba uses `@every 5m` or a 6-field cron with `CRON_TZ=` when a timezone is set. Tencent uses a 7-field cron. Huawei uses `Rate` such as `5m` or a 6-field cron with `?`. DigitalOcean and Cloudflare use 5-field cron. On-prem uses an in-process scheduler: a rate in seconds, or 5-field cron. A rate such as `7 minutes` is valid on-prem.

A rate that cannot be expressed as cron on cron-only clouds fails validation. Use a divisor of 60 minutes or 24 hours. `timezone` is honoured by AWS, GCP, and Alibaba in the cron form. Azure ignores it with a warning.

Sources: `docs/events.md#schedule`

```text
- schedule: 5 minutes                  # shorthand rate
- schedule: "0 3 * * *"                # shorthand cron (5 fields)
- schedule:
    rate: 1 hour                       # "<n> minute(s)|hour(s)|day(s)"
    # cron: "30 8 * * 1-5"             # OR standard 5-field unix cron (exactly one of rate/cron)
    input: {report: daily}             # becomes event.data
    timezone: Europe/Berlin            # default UTC
    enabled: true
    name: morning-report               # optional, used in the resource name
```
