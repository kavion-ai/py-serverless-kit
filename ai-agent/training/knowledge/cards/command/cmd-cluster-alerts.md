# pskit cluster alerts

Purpose: Who hears about a full cluster, and when a server counts as full.

When to use:
- The command help says: Who hears about a full cluster, and when a server counts as full.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster alerts NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--function` (string): Function called with the capacity event ("" clears).
- `--stage` (string): Stage whose deployed host runs it (default: any deployed stage).
- `--webhook` (string): Also POST the event here (Slack / Teams / any URL; "" clears).
- `--cooldown` (int): Minutes between two alerts (default 30).
- `--cpu` (int): A server is full at this CPU percent (default 85).
- `--memory` (int): ... memory percent (default 85).
- `--disk` (int): ... disk percent (default 90).
- `--test` (flag; default off): Send a test alert now.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster alerts NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`, `pskit cluster requests`

Safety: callback for `pskit cluster alerts` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
