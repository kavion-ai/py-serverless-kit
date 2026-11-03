# pskit lb logs

Purpose: Recent requests (upstream= is the server that answered) and errors.

When to use:
- The command help says: Recent requests (upstream= is the server that answered) and errors.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb logs NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `-n/--lines` (int_range; default 100): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb logs NAME [OPTIONS]`.

Studio equivalent: Load balancers > Logs

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb create`, `pskit lb detach`, `pskit lb forget`, `pskit lb list`, `pskit lb remove`, `pskit lb routes`

Safety: callback for `pskit lb logs` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
