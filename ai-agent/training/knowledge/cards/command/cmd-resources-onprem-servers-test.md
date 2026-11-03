# pskit resources onprem servers test

Purpose: Log in and show the OS, CPU, memory, disk, Docker access, sudo and installed runtimes.

When to use:
- The command help says: Log in and show the OS, CPU, memory, disk, Docker access, sudo and installed runtimes.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem servers test NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem servers test NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem servers add`, `pskit resources onprem servers check`, `pskit resources onprem servers list`, `pskit resources onprem servers remove`, `pskit resources onprem servers top`, `pskit resources onprem servers usage`

Safety: callback for `pskit resources onprem servers test` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
