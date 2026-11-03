# pskit cluster leave

Purpose: Drain SERVER (replicas move to the others) and remove it from cluster NAME.

When to use:
- The command help says: Drain SERVER (replicas move to the others) and remove it from cluster NAME.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster leave NAME SERVER [OPTIONS]
```

Arguments:
- `name` (string, required)
- `server` (string, required)

Options:
- `--yes` (flag; default off): Do not ask.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster leave NAME SERVER [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster list`, `pskit cluster remove`, `pskit cluster requests`

Safety: callback for `pskit cluster leave` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Prompt text starts: Remove {server} from cluster {name}?
- Option `--yes`: Do not ask.

Sources: `src/py_serverless_kit/cli/main.py`
