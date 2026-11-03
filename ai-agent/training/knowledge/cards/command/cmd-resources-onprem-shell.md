# pskit resources onprem shell

Purpose: A shell on a saved SSH server (or run one command there).

When to use:
- The command help says: A shell on a saved SSH server (or run one command there).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem shell SERVER [COMMAND] [OPTIONS]
```

Arguments:
- `server` (string, required)
- `command` (string, optional)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem shell SERVER [COMMAND] [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`

Safety: callback for `pskit resources onprem shell` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
