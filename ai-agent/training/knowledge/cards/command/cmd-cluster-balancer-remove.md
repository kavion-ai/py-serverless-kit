# pskit cluster balancer remove

Purpose: Stop the load balancer of cluster NAME (the functions keep running on the cluster).

When to use:
- The command help says: Stop the load balancer of cluster NAME (the functions keep running on the cluster).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster balancer remove NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--yes` (flag; default off): Do not ask.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster balancer remove NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster balancer logs`, `pskit cluster balancer set`, `pskit cluster balancer sync`

Safety: callback for `pskit cluster balancer remove` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Prompt text starts: Stop the load balancer of cluster {name}? Its URL stops answering.
- Option `--yes`: Do not ask.

Sources: `src/py_serverless_kit/cli/main.py`
