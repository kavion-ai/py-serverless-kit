# pskit resources onprem servers

Purpose: Saved SSH servers: name a machine once, then create services, install software, open shells and deploy to it.

When to use:
- The command help says: Saved SSH servers: name a machine once, then create services, install software, open shells and deploy to it.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem servers COMMAND
```

Options:
- (no options)

Examples:

```
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --pem ~/.ssh/edge1.pem
```

Example copied from this command's help text.

```
pskit resources onprem servers add lab --ssh deploy@192.0.2.10 --ssh-password-env LAB_PW
```

Example copied from this command's help text.

```
pskit resources onprem servers test edge1
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit resources onprem servers add`, `pskit resources onprem servers check`, `pskit resources onprem servers list`, `pskit resources onprem servers remove`, `pskit resources onprem servers test`, `pskit resources onprem servers top`, `pskit resources onprem servers usage`

Safety: callback for `pskit resources onprem servers` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

An address or login copied from the command help was rewritten in this card. Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.
