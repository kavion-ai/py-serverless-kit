# pskit resources onprem gui

Purpose: Start (or --remove) the web UI of a service.

When to use:
- The command help says: Start (or --remove) the web UI of a service.
- Start Redis Commander (generated password)
- No sign-in: keep it on 127.0.0.1 or a tunnel
- It does not open? find out why

Usage:

```
pskit resources onprem gui KEY [OPTIONS]
```

Arguments:
- `key` (string, required)

Options:
- `--port` (int): Port for the UI (default: Adminer 8089, Redis Commander 8082, ...).
- `--login` (choice; choices password, none; default password): Sign-in of the companion UI; none = no login (keep it private).
- `--password-env` (string): Your own UI password from this environment variable (default: generated).
- `--check` (flag; default off): Find out why a web UI does not open (container, ports, server, firewall).
- `--remove` (flag; default off): Stop and delete the companion web UI.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:

```
pskit resources onprem gui cache
```

start Redis Commander (generated password)

```
pskit resources onprem gui cache --login none
```

no sign-in: keep it on 127.0.0.1 or a tunnel

```
pskit resources onprem gui cache --check
```

it does not open? find out why

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem list`, `pskit resources onprem logs`, `pskit resources onprem monitor`

Safety: callback for `pskit resources onprem gui` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
