# pskit resources onprem catalog

Purpose: Services and runtimes that can be created.

When to use:
- The command help says: Services and runtimes that can be created.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem catalog [OPTIONS]
```

Options:
- `--json` (flag; default off): Print JSON.

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem catalog [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`, `pskit resources onprem monitor`

Safety: callback for `pskit resources onprem catalog` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

(empty help)
