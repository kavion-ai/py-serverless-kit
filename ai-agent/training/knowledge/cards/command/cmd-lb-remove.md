# pskit lb remove

Purpose: Stop load balancer NAME on its server and forget it.

When to use:
- The command help says: Stop load balancer NAME on its server and forget it.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb remove NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--force` (flag; default off): Also when other projects still use it (their URLs stop too).
- `--yes` (flag; default off): Do not ask.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb remove NAME [OPTIONS]`.

Studio equivalent: Load balancers > Remove

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb create`, `pskit lb detach`, `pskit lb forget`, `pskit lb list`, `pskit lb logs`, `pskit lb routes`

Safety: callback for `pskit lb remove` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Prompt text starts: Stop load balancer {name}? Every URL on it stops answering.
- Option `--yes`: Do not ask.

Sources: `src/py_serverless_kit/cli/main.py`
