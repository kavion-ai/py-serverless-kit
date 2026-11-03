# pskit lb detach

Purpose: Stop serving a cluster's deployments on load balancer NAME.

When to use:
- The command help says: Stop serving a cluster's deployments on load balancer NAME.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb detach NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--cluster` (string; required): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb detach NAME [OPTIONS]`.

Studio equivalent: Load balancers > Detach

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb create`, `pskit lb forget`, `pskit lb list`, `pskit lb logs`, `pskit lb remove`, `pskit lb routes`

Safety: callback for `pskit lb detach` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Stop serving a cluster's deployments on load balancer NAME.
