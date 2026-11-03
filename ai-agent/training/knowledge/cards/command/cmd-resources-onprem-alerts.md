# pskit resources onprem alerts

Purpose: Alerts of a service: show, set, test or check now.

When to use:
- The command help says: Alerts of a service: show, set, test or check now.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem alerts KEY [OPTIONS]
```

Arguments:
- `key` (string, required)

Options:
- `--on/--off` (flag; default off): Turn the alerts on or off (settings are kept).
- `--webhook` (string): POST alerts to this URL (Slack / Teams incoming webhook, any URL).
- `--function` (string): Run this function of the project with each alert.
- `--stage` (string): The deployed on-prem stage that runs the function (default: any).
- `--cpu` (int): Alert at this CPU percent of a container (default 90).
- `--memory` (int): ... memory percent (default 90).
- `--disk` (int): ... percent of the data disk used (default 85).
- `--lag` (int): ... seconds a replica is behind (default 60).
- `--cooldown` (int): Minutes between alerts (default 30).
- `--test` (flag; default off): Send a test alert now.
- `--check` (flag; default off): Measure now and alert when over a limit (for cron).
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem alerts KEY [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`, `pskit resources onprem monitor`

Safety: callback for `pskit resources onprem alerts` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
