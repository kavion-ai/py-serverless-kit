# pskit resources onprem replicas add

Purpose: Start one more read replica on a saved server.

When to use:
- The command help says: Start one more read replica on a saved server.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem replicas add KEY [SERVER] [OPTIONS]
```

Arguments:
- `key` (string, required)
- `server` (string, optional)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem replicas add KEY [SERVER] [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem replicas list`, `pskit resources onprem replicas remove`

Safety: callback for `pskit resources onprem replicas add` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Add a replica of KEY on SERVER (a saved server; omit it when every member runs on this machine).
