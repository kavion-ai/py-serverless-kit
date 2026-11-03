## In studio
1. Open this path:
Functions > + Create function

2. Choose a schedule trigger and set a rate or a cron expression.

## In the terminal
1. Run:

```
pskit invoke -f nightly -t schedule -d '{"report": "daily"}'
```

## In code

A schedule is a rate such as 5 minutes or a 5-field cron. timezone defaults to UTC. The handler sees event.type schedule and event.data from input.

## `schedule` The handler gets `event.type == "schedule"` and `event.data == input`

. pskit converts the portable syntax to each cloud's dialect: | Provider | Service | Expression | |---|---|---| | aws | EventBridge Scheduler | `rate(5 minutes)`, `cron(0 3 * * ? *)` (day-of-week converted to 1-7, `?` inserted; restricting both day-of-month and day-of-week is an error) | | gcp | Cloud Scheduler | 5-field cron; rates converted to cron Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
