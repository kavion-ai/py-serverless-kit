# pskit settings

Purpose: Export / import this project's .pskit settings and secrets (encrypted).

When to use:
- The command help says: Export / import this project's .pskit settings and secrets (encrypted).
- Asks for a passphrase (twice)
- Merges; --replace drops entries the file lacks

Usage:

```
pskit settings COMMAND
```

Options:
- (no options)

Examples:

```
pskit settings export -o prod.pskit-settings
```

asks for a passphrase (twice)

```
pskit settings import prod.pskit-settings --dry-run
```

Example copied from this command's help text.

```
pskit settings import prod.pskit-settings
```

merges; --replace drops entries the file lacks

Studio equivalent: none

Related: `pskit settings export`, `pskit settings import`

Safety: callback for `pskit settings` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-settings`

Help text from the command (click docstring, with the `\b` marker removed):

Move the settings .pskit keeps out of git to another machine: one passphrase-encrypted file.

Inside: saved servers, scaling clusters (and load balancers), on-prem services with their passwords,
SSH passwords and the SSH keys the servers use (also from ~/.ssh), where each on-prem stage was last
deployed, studio test events, and env files named by env_file in pskit.yml. Not inside: Terraform state.

Examples:
  pskit settings export -o prod.pskit-settings     # asks for a passphrase (twice)
  pskit settings import prod.pskit-settings --dry-run
  pskit settings import prod.pskit-settings        # merges; --replace drops entries the file lacks
  PSKIT_SETTINGS_PASSPHRASE=... pskit settings import prod.pskit-settings --yes   # from a script

Subcommands: `pskit settings export`, `pskit settings import`.
