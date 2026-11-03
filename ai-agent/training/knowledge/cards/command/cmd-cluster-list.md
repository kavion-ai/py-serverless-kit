# pskit cluster list

Purpose: Clusters, their servers and deployments.

When to use:
- The command help says: Clusters, their servers and deployments.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster list [OPTIONS]
```

Options:
- `--json` (flag; default off): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster list [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster remove`, `pskit cluster requests`

Safety: callback for `pskit cluster list` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Clusters, their servers and deployments.

cli.json lists 2 options and 0 arguments for `pskit cluster list`.
Every option line above is copied from that dump (flag, Click type, default, and help).
