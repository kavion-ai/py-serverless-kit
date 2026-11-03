# pskit lb forget

Purpose: Forget load balancer NAME in this project only (it keeps running for other projects).

When to use:
- The command help says: Forget load balancer NAME in this project only (it keeps running for other projects).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb forget NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb forget NAME [OPTIONS]`.

Studio equivalent: Load balancers > Forget

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb create`, `pskit lb detach`, `pskit lb list`, `pskit lb logs`, `pskit lb remove`, `pskit lb routes`

Safety: callback for `pskit lb forget` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
