# pskit client install-node

Purpose: Put the pskit Node.js package (with PskitClient) in node_modules.

When to use:
- The command help says: Put the pskit Node.js package (with PskitClient) in node_modules.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit client install-node [OPTIONS]
```

Options:
- `--dir` (string; default .): Project whose node_modules gets it.

Examples:
- No example is written in this command's help. The synopsis is `pskit client install-node [OPTIONS]`.

Studio equivalent: none

Related: `pskit client info`, `pskit client tunnel`

Safety: callback for `pskit client install-node` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Copy the `pskit` package (no dependencies) to <dir>/node_modules/pskit, for scripts outside pskit.

cli.json lists 1 options and 0 arguments for `pskit client install-node`.
Every option line above is copied from that dump (flag, Click type, default, and help).
