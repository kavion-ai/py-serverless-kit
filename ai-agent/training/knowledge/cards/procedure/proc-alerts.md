## In studio
1. Open Monitoring for the service and turn alerts on.

## In the terminal
1. Run:

```
pskit resources onprem alerts orders-db --test
```

## In code

Alerts can post to a webhook or call a function. --test sends one alert now. Thresholds have defaults documented in the command help.

## Monitoring and alerts

The **Servers** list shows a check mark per server: ✓ when its SSH port answers (all probed at once when the list opens, **Re-check** to probe again), ✗ with the reason otherwise; *Test* replaces it with the result of a full login check. **Live** on a server shows its CPU, RAM and disk use, refreshed every few seconds, until you switch it off.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
