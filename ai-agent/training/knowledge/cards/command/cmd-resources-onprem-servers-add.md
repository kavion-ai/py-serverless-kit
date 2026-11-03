# pskit resources onprem servers add

Purpose: Save (or replace) server NAME.

When to use:
- The command help says: Save (or replace) server NAME.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem servers add NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--ssh` (string; required): user@host[:port]
- `--pem` (string): Private key (empty: the SSH agent or your default key).
- `--ssh-password-env` (string): Log in with the password in this variable (sshpass).
- `--ssh-password-file` (string): Log in with the password in this file (sshpass).
- `--sudo` (flag; default off): Run docker / installs with sudo -n.
- `--description` (string): A note shown in the studio.
- `--home` (string): Where pskit keeps files there (default /opt/pskit; cluster files in ~).
- `--bind` (string): Address the functions and services listen on (0.0.0.0, 127.0.0.1 or an IP).
- `--data-dir` (string): Where data lives there (default: Docker volumes / the app).
- `--test/--no-test` (flag; default True): Log in once after saving (default: yes).
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem servers add NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem servers check`, `pskit resources onprem servers list`, `pskit resources onprem servers remove`, `pskit resources onprem servers test`, `pskit resources onprem servers top`, `pskit resources onprem servers usage`

Safety: callback for `pskit resources onprem servers add` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
