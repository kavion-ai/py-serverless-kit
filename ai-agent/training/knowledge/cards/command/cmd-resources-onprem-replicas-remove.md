# pskit resources onprem replicas remove

Purpose: Stop one read replica (by name r2, or its server).

When to use:
- The command help says: Stop one read replica (by name r2, or its server).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem replicas remove KEY NAME [OPTIONS]
```

Arguments:
- `key` (string, required)
- `name` (string, required)

Options:
- `--delete-data` (flag; default off): Also delete the replica's data volume.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem replicas remove KEY NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem replicas add`, `pskit resources onprem replicas list`

Safety: callback for `pskit resources onprem replicas remove` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
