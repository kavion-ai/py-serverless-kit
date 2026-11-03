# pskit resources onprem

Purpose: Create services for on-premises functions with Docker, here or on an SSH server.

When to use:
- The command help says: Create services for on-premises functions with Docker, here or on an SSH server.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem COMMAND
```

Options:
- (no options)

Examples:

```
pskit resources onprem catalog
```

Example copied from this command's help text.

```
pskit resources onprem create jobs --service redis --attach worker --save
```

Example copied from this command's help text.

```
pskit resources onprem create orders-db --service postgres --ssh deploy@192.0.2.10 --pem key.pem --save
```

Example copied from this command's help text.

```
pskit resources onprem create py --service python --ssh deploy@192.0.2.10 --pem key.pem
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`

Safety: callback for `pskit resources onprem` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-resources-onprem`

An address or login copied from the command help was rewritten in this card. Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.
