# pskit firewall

Purpose: Ports each on-prem server must open (inbound / outbound), with server names.

When to use:
- The command help says: Ports each on-prem server must open (inbound / outbound), with server names.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit firewall [OPTIONS]
```

Options:
- `--server` (string): Only this server (name or address).
- `--json` (flag; default off): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:

```
pskit firewall
```

Example copied from this command's help text.

```
pskit firewall --server edge2
```

Example copied from this command's help text.

```
pskit firewall --json
```

Example copied from this command's help text.

Studio equivalent: Deploy > Firewall

Related: `pskit client`, `pskit cluster`, `pskit dashboard`, `pskit deploy`, `pskit dev`, `pskit doctor`, `pskit function`, `pskit info`

Safety: callback for `pskit firewall` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
