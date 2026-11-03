# pskit cluster remove

Purpose: Forget cluster NAME (the servers and anything running on them are left as they are).

When to use:
- The command help says: Forget cluster NAME (the servers and anything running on them are left as they are).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster remove NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--uninstall` (flag; default off): Also take off what pskit installed: deployments, load balancer, the agent on every joined server and the orchestrator on the master.
- `--delete-data` (flag; default off): With --uninstall: also delete the main replicas' data on the master.
- `--yes` (flag; default off): Do not ask.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster remove NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster requests`

Safety: callback for `pskit cluster remove` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Option `--yes`: Do not ask.

Sources: `src/py_serverless_kit/cli/main.py`
