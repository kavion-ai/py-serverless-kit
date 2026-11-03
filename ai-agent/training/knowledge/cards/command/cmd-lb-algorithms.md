# pskit lb algorithms

Purpose: The load balancing algorithms: how each picks a server, static or dynamic, pros, cons, when to use it.

When to use:
- The command help says: The load balancing algorithms: how each picks a server, static or dynamic, pros, cons, when to use it.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb algorithms [OPTIONS]
```

Options:
- `--json` (flag; default off): (no help text)

Examples:
- No example is written in this command's help. The synopsis is `pskit lb algorithms [OPTIONS]`.

Studio equivalent: Load balancers > How it spreads requests

Related: `pskit lb attach`, `pskit lb create`, `pskit lb detach`, `pskit lb forget`, `pskit lb list`, `pskit lb logs`, `pskit lb remove`, `pskit lb routes`

Safety: callback for `pskit lb algorithms` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
