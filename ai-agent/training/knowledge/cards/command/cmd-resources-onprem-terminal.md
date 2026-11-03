# pskit resources onprem terminal

Purpose: A full terminal in the browser (Docker): a server or a service.

When to use:
- The command help says: A full terminal in the browser (Docker): a server or a service.
- Redis-cli in the browser

Usage:

```
pskit resources onprem terminal [KEY] [OPTIONS]
```

Arguments:
- `key` (string, optional)

Options:
- `--server` (string): SSH to this saved server.
- `--shell` (flag; default off): With KEY: sh in the container instead of the service's client.
- `--list` (flag; default off): Show running terminals.
- `--stop` (string): Stop a terminal by name (pskit-term-7681), or 'all'.
- `--open/--no-open` (flag; default True): Open it in the browser.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:

```
pskit resources onprem terminal --server edge1
```

Example copied from this command's help text.

```
pskit resources onprem terminal cache
```

redis-cli in the browser

```
pskit resources onprem terminal --list
```

Example copied from this command's help text.

```
pskit resources onprem terminal --stop all
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`

Safety: callback for `pskit resources onprem terminal` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
