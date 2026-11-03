# pskit lb list

Purpose: Load balancers this project uses.

When to use:
- The command help says: Load balancers this project uses.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb list [OPTIONS]
```

Options:
- `--json` (flag; default off): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb list [OPTIONS]`.

Studio equivalent: none

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb create`, `pskit lb detach`, `pskit lb forget`, `pskit lb logs`, `pskit lb remove`, `pskit lb routes`

Safety: callback for `pskit lb list` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Load balancers this project uses.

cli.json lists 2 options and 0 arguments for `pskit lb list`.
Every option line above is copied from that dump (flag, Click type, default, and help).
