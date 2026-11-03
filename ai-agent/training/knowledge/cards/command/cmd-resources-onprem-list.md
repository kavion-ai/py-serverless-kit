# pskit resources onprem list

Purpose: Services created from this project.

When to use:
- The command help says: Services created from this project.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem list [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `--json` (flag; default off): Print JSON.

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem list [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem logs`, `pskit resources onprem monitor`

Safety: callback for `pskit resources onprem list` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

(empty help)
