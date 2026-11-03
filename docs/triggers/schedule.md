# Schedule trigger

Search terms: schedule, cron, timer, rate, every 5 minutes, scheduled job, nightly job, recurring, timezone, EventBridge Scheduler, Cloud Scheduler, timer trigger, cron trigger

The pskit `schedule` trigger runs a function on a timer: every N minutes, hours or days (a rate), or on a standard
5-field cron expression. pskit converts the portable syntax to each cloud's scheduler.

## Write a schedule trigger in pskit.yml

The pskit `schedule` trigger needs exactly one of `rate` or `cron`.

```yaml
events:
  - schedule: 5 minutes                # shorthand rate
  - schedule: "0 3 * * *"              # shorthand cron (anything that is not a rate)
  - schedule:
      cron: "30 8 * * 1-5"             # minute hour day-of-month month day-of-week
      timezone: Europe/Berlin          # default UTC
      input: {report: daily}           # becomes event.data
      enabled: true                    # false pauses it
      name: morning-report             # optional, used in the native resource name
```

| Key | Default | Meaning |
|---|---|---|
| `rate` | | `<n> minute(s) / hour(s) / day(s)`, e.g. `1 hour`, `15 minutes` |
| `cron` | | standard 5-field cron: `min hour dom month dow` |
| `input` | `null` | any JSON value; the handler gets it as `event.data` |
| `timezone` | `UTC` | IANA zone for cron schedules |
| `enabled` | `true` | `false` creates the schedule paused |
| `name` | | optional label for the native schedule |

Validation errors: `schedule needs exactly one of 'rate' (e.g. '5 minutes') or 'cron' (5 fields)`,
`rate must look like '<n> minutes|hours|days'`, `cron must be a standard 5-field expression: 'min hour dom month dow'`.

## Read the schedule event in the handler

For a `schedule` trigger `event.type == "schedule"` and `event.data` is the `input` (or `None`).

```python
from py_serverless_kit import Context, Event


def nightly_report(event: Event, ctx: Context):
    kind = (event.data or {}).get("report", "daily")
    ctx.logger.info("report run", extra={"kind": kind, "at": event.time.isoformat()})
    return {"report": kind}
```

`event.time` is the scheduled time when the cloud sends one, otherwise the current UTC time. One function may have
several schedules with different `input` values to tell them apart. A failing scheduled run raises, so the cloud's
retry rules apply.

## Add a schedule trigger in studio

1. Sidebar **Functions** → open the function → **2 Triggers** → card **Schedule** (default `rate: 5 minutes`).
2. **Run**: choose one of
   - **Every…**: **Interval** number plus `minute` / `hour` / `day`, or a preset chip (`1 minute`, `5 minutes`,
     `15 minutes`, `1 hour`, `6 hours`, `1 day`).
   - **At a specific time**: **Repeat** (**Every day**, **Weekdays**, **On days…**, **Monthly**, **Yearly**),
     **Days** checkboxes, **On** (month and day), **At** (HH:MM). The help line shows the cron it writes.
   - **Cron expression**: type 5 fields or click a preset (**Every day 09:00**, **Weekdays 08:30**, **Every hour**,
     **1st of month**). The help line describes it in words.
3. **Timezone** (time and cron modes): pick an IANA zone; empty = UTC.
4. **Input**: JSON passed as `event.data`, e.g. `{"report": "daily"}`.
5. **Enabled**: on = active, off = paused (`enabled: false`).
6. **Apply changes**, then **Save**.

## Schedules per provider

The pskit schedule is rendered in each cloud's own dialect. A rate or cron that the dialect cannot express fails when
pskit builds the Terraform (`pskit package`, `pskit plan`, `pskit deploy`), not in `pskit validate`.

| Provider | Native service | Expression written | Arbitrary rates (`7 minutes`) | `timezone` |
|---|---|---|---|---|
| aws | EventBridge Scheduler | `rate(5 minutes)` or `cron(m h dom mon dow *)` (`?` added, weekday 1-7) | yes | yes |
| azure | timer trigger | 6-field NCRONTAB, `0 */5 * * * *` | minute rates under 60; others need a cron form | ignored, warning (Linux Consumption runs UTC) |
| gcp | Cloud Scheduler | 5-field cron (rates converted) | no | yes |
| alibaba | timer trigger | `@every 5m`, or 6-field cron with `CRON_TZ=` | yes | yes, cron form |
| tencent | timer trigger | 7-field cron (seconds ... year) | no | not applied |
| huawei | timer trigger | `Rate` `5m`, or 6-field cron with `?` | yes | not applied |
| digitalocean | `project.yml` scheduler trigger | 5-field cron | no | not applied |
| cloudflare | Cron Triggers | 5-field cron | no | not applied |
| onprem | the host's built-in scheduler | rate in seconds, or 5-field cron | yes | yes (needs tzdata, vendored on deploy) |
| oracle, ibm | not supported | | | |

Rate to cron conversion: minutes must divide 60 (`*/15 * * * *`), hours must divide 24 (`0 */6 * * *`), days give
`0 0 */N * *` up to 31. Otherwise the error is `rate '7 minutes' is not expressible as cron; use a divisor of 60
minutes`. AWS cron cannot restrict both day-of-month and day-of-week
(`AWS cron cannot restrict both day-of-month and day-of-week`).

`enabled: false` is honoured by aws, gcp, alibaba, tencent, huawei, digitalocean (left out), cloudflare (left out)
and onprem. The Azure renderer does not read `enabled`, so the timer is still created there.

## How the input reaches the handler

The pskit schedule `input` is sent as the payload of the native schedule, wrapped as
`{"__pskit": "schedule", "data": <input>}` (AWS, GCP, Alibaba, Tencent, Huawei, DigitalOcean). The adapter unwraps
it, so the handler sees `event.type == "schedule"` and `event.data == input`. Azure passes the configured `input` to
the generated timer function; Cloudflare maps each cron to its input; on premises the host passes it directly. On GCP
a function with only queue or topic triggers gets its schedule through that Pub/Sub topic.

## Test a schedule trigger

- Locally: `pskit invoke -f nightly-report` (type `schedule` is the default when it is the first trigger; with no
  `-d` the configured `input` is used). Another input: `pskit invoke -f nightly-report -t schedule -d '{"report": "weekly"}'`.
- `pskit dev`: `curl -X POST "localhost:3000/__pskit/invoke/nightly-report?type=schedule" -d '{"report": "daily"}'`.
- Studio: **Test** → the function → the `rate(...)` / `cron(...)` card → **Payload (JSON)** → **▶ Run locally**.
- Deployed: `pskit trigger -f nightly-report -e 0` runs it now on AWS and on premises, and over the function URL on
  GCP, IBM, DigitalOcean, Cloudflare and Oracle. Elsewhere `pskit trigger --list` prints the console steps.
  `pskit logs -f --function nightly-report` shows the run.

## Common schedule trigger errors

| Message or symptom | Fix |
|---|---|
| `schedule needs exactly one of 'rate' ... or 'cron'` | keep one of them |
| `rate '7 minutes' is not expressible as cron; use a divisor of 60 minutes` | use 5, 10, 15, 20, 30 ... or a cron |
| `AWS cron cannot restrict both day-of-month and day-of-week` | use `*` in one of them |
| `Linux Consumption timers run in UTC; timezone is ignored` (Azure) | convert the time to UTC |
| `timezone X needs the IANA database ...` (onprem) | deploy (`pskit deploy` vendors tzdata); until then UTC |
| `<Provider> does not support 'schedule' events` (Oracle, IBM) | run it elsewhere or call it from another scheduler over HTTP |
| runs at an unexpected hour | the default timezone is UTC |

## See also

- [README.md](README.md)
- [../functions/invoke-and-test.md](../functions/invoke-and-test.md)
- [../events.md](../events.md)
- [../deployment/logs.md](../deployment/logs.md)
- [../providers/README.md](../providers/README.md)
