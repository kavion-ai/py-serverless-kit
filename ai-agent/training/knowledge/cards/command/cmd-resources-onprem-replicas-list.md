# pskit resources onprem replicas list

Purpose: Members, their state and replication lag.

When to use:
- The command help says: Members, their state and replication lag.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem replicas list KEY [OPTIONS]
```

Arguments:
- `key` (string, required)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem replicas list KEY [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem replicas add`, `pskit resources onprem replicas remove`

Safety: callback for `pskit resources onprem replicas list` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

(empty help)

cli.json lists 1 options and 1 arguments for `pskit resources onprem replicas list`.
Every option line above is copied from that dump (flag, Click type, default, and help).
