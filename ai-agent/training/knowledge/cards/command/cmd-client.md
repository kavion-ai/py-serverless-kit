# pskit client

Purpose: Call the on-prem host from scripts.

When to use:
- The command help says: Call the on-prem host from scripts.
- Endpoint, token, reachability, code to copy
- ./node_modules/pskit for scripts outside pskit
- 127.0.0.1:8080 here -> the host on its server

Usage:

```
pskit client COMMAND
```

Options:
- (no options)

Examples:

```
pskit client info
```

endpoint, token, reachability, code to copy

```
pskit client install-node
```

./node_modules/pskit for scripts outside pskit

```
pskit client tunnel
```

127.0.0.1:8080 here -> the host on its server

Studio equivalent: none

Related: `pskit client info`, `pskit client install-node`, `pskit client tunnel`

Safety: callback for `pskit client` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-client`

Help text from the command (click docstring, with the `\b` marker removed):

Use the deployed on-prem host from any program: Python / Node.js client, HTTP, tunnel.

Examples:
  pskit client info                      # endpoint, token, reachability, code to copy
  pskit client install-node              # ./node_modules/pskit for scripts outside pskit
  pskit client tunnel                    # 127.0.0.1:8080 here -> the host on its server

Subcommands: `pskit client info`, `pskit client install-node`, `pskit client tunnel`.
