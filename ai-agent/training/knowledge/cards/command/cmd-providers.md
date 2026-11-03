# pskit providers

Purpose: List supported clouds and what each supports.

When to use:
- The command help says: List supported clouds and what each supports.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit providers [OPTIONS]
```

Options:
- `--json` (flag; default off): (no help text)

Examples:

```
pskit providers
```

Example copied from this command's help text.

```
pskit providers --json
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit doctor`, `pskit validate`

Safety: callback for `pskit providers` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-providers`

Help text from the command (click docstring, with the `\b` marker removed):

List supported clouds and what each supports.

Examples:
  pskit providers
  pskit providers --json

cli.json lists 1 options and 0 arguments for `pskit providers`.
Every option line above is copied from that dump (flag, Click type, default, and help).
