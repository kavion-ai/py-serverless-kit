# pskit cluster watch

Purpose: Check every INTERVAL seconds until Ctrl+C (run it on an always-on machine, e.g.

When to use:
- The command help says: Check every INTERVAL seconds until Ctrl+C (run it on an always-on machine, e.g.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster watch NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--interval` (int_range; default 60): Seconds.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster watch NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`

Safety: callback for `pskit cluster watch` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
