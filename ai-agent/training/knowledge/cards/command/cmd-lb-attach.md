# pskit lb attach

Purpose: Serve every deployment of a cluster on load balancer NAME (http://<lb>/<service>/), now and on deploys.

When to use:
- The command help says: Serve every deployment of a cluster on load balancer NAME (http://<lb>/<service>/), now and on deploys.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb attach NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--cluster` (string; required): Cluster whose deployments it serves.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb attach NAME [OPTIONS]`.

Studio equivalent: Load balancers > + Attach cluster

Related: `pskit lb algorithms`, `pskit lb create`, `pskit lb detach`, `pskit lb forget`, `pskit lb list`, `pskit lb logs`, `pskit lb remove`, `pskit lb routes`

Safety: callback for `pskit lb attach` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
