# pskit resources onprem remove

Purpose: Stop and delete a service container.

When to use:
- The command help says: Stop and delete a service container.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem remove KEY [OPTIONS]
```

Arguments:
- `key` (string, required)

Options:
- `--delete-data` (flag; default off): Also delete its data volume.
- `--save` (flag; default off): Also remove the resource and its triggers from pskit.yml.
- `-y/--yes` (flag; default off): Do not ask for confirmation.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem remove KEY [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`

Safety: callback for `pskit resources onprem remove` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Prompt text starts: Delete {what} of {key}?
- Option `-y/--yes`: Do not ask for confirmation.

Sources: `src/py_serverless_kit/cli/main.py`
