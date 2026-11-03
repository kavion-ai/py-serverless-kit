# pskit resources onprem replicas

Purpose: Read replicas of a replicated database: list, add, remove.

When to use:
- The command help says: Read replicas of a replicated database: list, add, remove.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem replicas COMMAND
```

Options:
- (no options)

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem replicas COMMAND`.

Studio equivalent: none

Related: `pskit resources onprem replicas add`, `pskit resources onprem replicas list`, `pskit resources onprem replicas remove`

Safety: callback for `pskit resources onprem replicas` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Read replicas of a database created with --replica. The load balancer and the env file follow.

Subcommands: `pskit resources onprem replicas add`, `pskit resources onprem replicas list`, `pskit resources onprem replicas remove`.
