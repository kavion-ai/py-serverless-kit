# pskit resources onprem servers usage

Purpose: Where each saved server is used (functions, clusters, ...).

When to use:
- The command help says: Where each saved server is used (functions, clusters, ...).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem servers usage [NAME] [OPTIONS]
```

Arguments:
- `name` (string, optional)

Options:
- `--json` (flag; default off): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem servers usage [NAME] [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem servers add`, `pskit resources onprem servers check`, `pskit resources onprem servers list`, `pskit resources onprem servers remove`, `pskit resources onprem servers test`, `pskit resources onprem servers top`

Safety: callback for `pskit resources onprem servers usage` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
