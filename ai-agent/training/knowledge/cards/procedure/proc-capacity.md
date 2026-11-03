## In studio
1. Use Check & alert on the cluster page.

## In the terminal
1. Run:

```
pskit cluster alerts prod --function notify
```

2. Run:

```
pskit cluster check prod
```

## In code

alerts records who is told when a server is full. check measures the cluster. The defaults for CPU, memory, and disk are in the command help.

### Alert DevOps (optional)

When the cluster is full, pskit can call **one of your functions** and / or POST to a **webhook** (Slack, Teams, Google Chat or any URL), at most once per cooldown (default 30 minutes): The function gets `event.data`: A mail to DevOps from that function (any SMTP relay you have): The function runs on the deployed host of the stage set with `--stage` (or any deployed Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
