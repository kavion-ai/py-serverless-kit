# pskit lb create

Purpose: Make saved SERVER load balancer NAME (Docker and OpenResty there), or add the one already running there.

When to use:
- The command help says: Make saved SERVER load balancer NAME (Docker and OpenResty there), or add the one already running there.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit lb create NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--server` (string; required): Saved server that runs it (outside the clusters it serves).
- `--port` (int_range): Port users call (default 80).
- `--address` (string): Its address in the URLs (default: the server's host).
- `--algorithm` (string): round_robin, sticky_round_robin, weighted_round_robin, ip_hash, least_connections or least_time (pskit lb algorithms explains each).
- `--weight` (string; repeatable): Weight 1..100 of a saved server (weighted round robin, least connections, least time). Repeat it.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit lb create NAME [OPTIONS]`.

Studio equivalent: Load balancers > + Create load balancer

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb detach`, `pskit lb forget`, `pskit lb list`, `pskit lb logs`, `pskit lb remove`, `pskit lb routes`

Safety: callback for `pskit lb create` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
