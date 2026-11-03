# pskit lb status

Purpose: Whether it runs, its server's use, and every route on it (from every project).

When to use:
- The command help says: Whether it runs, its server's use, and every route on it (from every project).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb status NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--json` (flag; default off): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb status NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb create`, `pskit lb detach`, `pskit lb forget`, `pskit lb list`, `pskit lb logs`, `pskit lb remove`

Safety: callback for `pskit lb status` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
