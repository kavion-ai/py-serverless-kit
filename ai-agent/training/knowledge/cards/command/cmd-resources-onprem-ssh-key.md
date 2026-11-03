# pskit resources onprem ssh-key

Purpose: Install an SSH key on a server that takes a password (once).

When to use:
- The command help says: Install an SSH key on a server that takes a password (once).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem ssh-key DESTINATION [OPTIONS]
```

Arguments:
- `destination` (string, required)

Options:
- `--key` (string): Key to install (default: ~/.ssh/pskit_ed25519, created if missing).
- `--password-env` (string): Send the password from this variable (needs sshpass); default: asked.

Examples:

```
pskit resources onprem ssh-key deploy@192.0.2.10
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`

Safety: callback for `pskit resources onprem ssh-key` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

An address or login copied from the command help was rewritten in this card. Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.
