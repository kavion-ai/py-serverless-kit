# pskit resources onprem servers list

Purpose: 

When to use:
- The command help says: 
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem servers list [OPTIONS]
```

Options:
- `--json` (flag; default off): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem servers list [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem servers add`, `pskit resources onprem servers check`, `pskit resources onprem servers remove`, `pskit resources onprem servers test`, `pskit resources onprem servers top`, `pskit resources onprem servers usage`

Safety: callback for `pskit resources onprem servers list` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

(empty help)
