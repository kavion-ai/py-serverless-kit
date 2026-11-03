# pskit resources onprem servers top

Purpose: Live CPU, memory and disk use of a saved server.

When to use:
- The command help says: Live CPU, memory and disk use of a saved server.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem servers top NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--watch` (int; default 0): Repeat every N seconds until Ctrl+C.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem servers top NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem servers add`, `pskit resources onprem servers check`, `pskit resources onprem servers list`, `pskit resources onprem servers remove`, `pskit resources onprem servers test`, `pskit resources onprem servers usage`

Safety: callback for `pskit resources onprem servers top` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
