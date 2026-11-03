# pskit function

Purpose: Give a function its own folder, code and requirements.txt.

When to use:
- The command help says: Give a function its own folder, code and requirements.txt.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit function COMMAND
```

Options:
- (no options)

Examples:

```
pskit function split get-item
```

Example copied from this command's help text.

```
pskit function split --all --dry-run
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit function split`

Safety: callback for `pskit function` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Functions as sub-projects: functions/<name>/ with their own code and requirements.txt, so a server of
provider.options.placement gets only the code and dependencies of the functions it runs.

Examples:
  pskit function split get-item
  pskit function split --all --dry-run

Subcommands: `pskit function split`.
