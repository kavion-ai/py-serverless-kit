# pskit cluster balancer sync

Purpose: Rewrite the load balancer's config from the cluster's servers and deployments.

When to use:
- The command help says: Rewrite the load balancer's config from the cluster's servers and deployments.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster balancer sync NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster balancer sync NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster balancer logs`, `pskit cluster balancer remove`, `pskit cluster balancer set`

Safety: callback for `pskit cluster balancer sync` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Rewrite the load balancer's config from the cluster's servers and deployments.
