# pskit cluster join

Purpose: Add saved SERVER to cluster NAME (installs the agent and copies the deployed images).

When to use:
- The command help says: Add saved SERVER to cluster NAME (installs the agent and copies the deployed images).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster join NAME SERVER [OPTIONS]
```

Arguments:
- `name` (string, required)
- `server` (string, required)

Options:
- `--advertise` (string): This server's address in the cluster network (default: its host).
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster join NAME SERVER [OPTIONS]`.

Studio equivalent: Scaling cluster > + Join server

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`, `pskit cluster requests`

Safety: callback for `pskit cluster join` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
