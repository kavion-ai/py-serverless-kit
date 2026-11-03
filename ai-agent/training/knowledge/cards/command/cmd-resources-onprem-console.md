# pskit resources onprem console

Purpose: Run commands in a service (redis-cli, psql, mongosh, rpk, ...).

When to use:
- The command help says: Run commands in a service (redis-cli, psql, mongosh, rpk, ...).
- Interactive redis-cli

Usage:

```
pskit resources onprem console KEY [COMMAND] [OPTIONS]
```

Arguments:
- `key` (string, required)
- `command` (string, optional)

Options:
- `--shell` (flag; default off): A shell (sh) in the container instead of the service's client.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:

```
pskit resources onprem console cache
```

interactive redis-cli

```
pskit resources onprem console cache "LLEN jobs"
```

Example copied from this command's help text.

```
pskit resources onprem console orders-db "SELECT count(*) FROM orders;"
```

Example copied from this command's help text.

```
pskit resources onprem console secrets "kv get secret/db-password"
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`, `pskit resources onprem monitor`

Safety: callback for `pskit resources onprem console` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
