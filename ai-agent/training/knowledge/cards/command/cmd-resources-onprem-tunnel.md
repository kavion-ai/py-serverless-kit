# pskit resources onprem tunnel

Purpose: Reach a service on a server through SSH (firewalled port).

When to use:
- The command help says: Reach a service on a server through SSH (firewalled port).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem tunnel KEY [OPTIONS]
```

Arguments:
- `key` (string, required)

Options:
- `--local-port` (int): Port on this machine (default: the remote port).
- `--remote-port` (int): Port on the server (default: the service's; e.g. its web UI).
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem tunnel KEY [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`

Safety: callback for `pskit resources onprem tunnel` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
