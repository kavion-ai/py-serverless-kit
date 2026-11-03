# pskit cluster check

Purpose: Status once; when full, call the alert function / webhook (respecting the cooldown).

When to use:
- The command help says: Status once; when full, call the alert function / webhook (respecting the cooldown).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster check NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--alert/--no-alert` (flag; default True): Send the alert when the cluster is full (default: yes).
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster check NAME [OPTIONS]`.

Studio equivalent: Scaling cluster > Check & alert

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`, `pskit cluster requests`

Safety: callback for `pskit cluster check` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
