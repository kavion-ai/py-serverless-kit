# pskit cluster balancer set

Purpose: Make saved SERVER the load balancer of cluster NAME (installs Docker and OpenResty there).

When to use:
- The command help says: Make saved SERVER the load balancer of cluster NAME (installs Docker and OpenResty there).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster balancer set NAME SERVER [OPTIONS]
```

Arguments:
- `name` (string, required)
- `server` (string, required)

Options:
- `--port` (int_range; default 80): Port users call on the load balancer.
- `--address` (string): Its address in the URL users call (default: the server's host).
- `--algorithm` (string): round_robin, sticky_round_robin, weighted_round_robin, ip_hash, least_connections or least_time (pskit lb algorithms explains each).
- `--weight` (string; repeatable): Weight 1..100 of a saved server (weighted round robin, least connections, least time). Repeat it.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster balancer set NAME SERVER [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster balancer logs`, `pskit cluster balancer remove`, `pskit cluster balancer sync`

Safety: callback for `pskit cluster balancer set` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
