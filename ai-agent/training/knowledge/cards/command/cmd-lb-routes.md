# pskit lb routes

Purpose: Routes on a load balancer (pskit lb status lists them).

When to use:
- The command help says: Routes on a load balancer (pskit lb status lists them).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb routes COMMAND
```

Options:
- (no options)

Examples:
- No example is written in this command's help. The synopsis is `pskit lb routes COMMAND`.

Studio equivalent: none

Related: `pskit lb routes remove`

Safety: callback for `pskit lb routes` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Routes on a load balancer (pskit lb status lists them).

Subcommands: `pskit lb routes remove`.

cli.json lists 0 options and 0 arguments for `pskit lb routes`.
Every option line above is copied from that dump (flag, Click type, default, and help).
