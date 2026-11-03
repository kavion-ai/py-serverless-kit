# pskit settings import

Purpose: Write the settings of an exported FILE into this project (the current ones are backed up first).

When to use:
- The command help says: Write the settings of an exported FILE into this project (the current ones are backed up first).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit settings import FILE [OPTIONS]
```

Arguments:
- `file` (path, required)

Options:
- `--replace` (flag; default off): Drop saved servers, clusters and services the file does not have.
- `--dry-run` (flag; default off): Only show what would change.
- `--yes` (flag; default off): Do not ask.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit settings import FILE [OPTIONS]`.

Studio equivalent: Setup & credentials > Import into this project

Related: `pskit settings export`

Safety: callback for `pskit settings import` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Prompt text starts: Import into {root}?
- Option `--yes`: Do not ask.

Sources: `src/py_serverless_kit/cli/main.py`
