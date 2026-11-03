# pskit cluster requests

Purpose: Recent requests of one deployment, and how HTTP is spread across each server (live with --follow).

When to use:
- The command help says: Recent requests of one deployment, and how HTTP is spread across each server (live with --follow).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster requests NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--stack` (string): The deployment (default: the first one on the cluster).
- `-f/--follow` (flag; default off): Keep printing new requests until Ctrl+C.
- `-n/--lines` (int_range; default 50): How many recent requests first.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster requests NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`

Safety: callback for `pskit cluster requests` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
