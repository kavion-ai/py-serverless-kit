# pskit cluster status

Purpose: Every server's CPU, memory and disk, the replicas, and whether the cluster is full.

When to use:
- The command help says: Every server's CPU, memory and disk, the replicas, and whether the cluster is full.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster status NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--json` (flag; default off): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster status NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`

Safety: callback for `pskit cluster status` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
