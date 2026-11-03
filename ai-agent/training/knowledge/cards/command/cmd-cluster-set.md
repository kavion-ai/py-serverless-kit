# pskit cluster set

Purpose: Change how cluster NAME spreads requests.

When to use:
- The command help says: Change how cluster NAME spreads requests.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster set NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--master-serves/--no-master-serves` (flag; default off): Send requests to the master too (on), or use it only while every other server is down (off).
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster set NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`

Safety: callback for `pskit cluster set` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
