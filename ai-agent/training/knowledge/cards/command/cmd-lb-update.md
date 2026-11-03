# pskit lb update

Purpose: Change the port, default algorithm, weights or address (routes on the default algorithm switch too).

When to use:
- The command help says: Change the port, default algorithm, weights or address (routes on the default algorithm switch too).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb update NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--port` (int_range): (no help text)
- `--address` (string): (no help text)
- `--algorithm` (string): round_robin, sticky_round_robin, weighted_round_robin, ip_hash, least_connections or least_time (pskit lb algorithms explains each).
- `--weight` (string; repeatable): Weight 1..100 of a saved server (weighted round robin, least connections, least time). Repeat it.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb update NAME [OPTIONS]`.

Studio equivalent: Load balancers > Update

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb create`, `pskit lb detach`, `pskit lb forget`, `pskit lb list`, `pskit lb logs`, `pskit lb remove`

Safety: callback for `pskit lb update` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
