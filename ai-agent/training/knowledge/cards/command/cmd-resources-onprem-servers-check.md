# pskit resources onprem servers check

Purpose: Which saved servers answer on their SSH port (no login).

When to use:
- The command help says: Which saved servers answer on their SSH port (no login).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem servers check [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem servers check [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem servers add`, `pskit resources onprem servers list`, `pskit resources onprem servers remove`, `pskit resources onprem servers test`, `pskit resources onprem servers top`, `pskit resources onprem servers usage`

Safety: callback for `pskit resources onprem servers check` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

(empty help)
