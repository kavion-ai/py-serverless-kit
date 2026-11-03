# pskit lb routes remove

Purpose: Remove the route at PATH (xyz, or port-8081) from load balancer NAME, whichever project owns it.

When to use:
- The command help says: Remove the route at PATH (xyz, or port-8081) from load balancer NAME, whichever project owns it.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb routes remove NAME PATH [OPTIONS]
```

Arguments:
- `name` (string, required)
- `path` (string, required)

Options:
- `--yes` (flag; default off): Do not ask.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb routes remove NAME PATH [OPTIONS]`.

Studio equivalent: none

Related: none

Safety: callback for `pskit lb routes remove` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Prompt text starts: Remove /{path.strip('/')} from load balancer {name}?
- Option `--yes`: Do not ask.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Remove the route at PATH (xyz, or port-8081) from load balancer NAME, whichever project owns it.
