# pskit lb sync

Purpose: Rewrite the load balancer from this project's settings: every route, and attached clusters.

When to use:
- The command help says: Rewrite the load balancer from this project's settings: every route, and attached clusters.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb sync NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb sync NAME [OPTIONS]`.

Studio equivalent: Load balancers > Sync

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb create`, `pskit lb detach`, `pskit lb forget`, `pskit lb list`, `pskit lb logs`, `pskit lb remove`

Safety: callback for `pskit lb sync` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
