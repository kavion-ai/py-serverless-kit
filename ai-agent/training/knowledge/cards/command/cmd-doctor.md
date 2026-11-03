# pskit doctor

Purpose: Check terraform, the cloud CLI and credentials.

When to use:
- The command help says: Check terraform, the cloud CLI and credentials.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit doctor [OPTIONS]
```

Options:
- `-p/--provider` (string): Provider to check (default: provider.name in pskit.yml).
- `-c/--config` (string): Config file (default: pskit.yml).
- `--json` (flag; default off): Machine readable output.

Examples:

```
pskit doctor
```

Example copied from this command's help text.

```
pskit doctor -p azure
```

Example copied from this command's help text.

```
pskit doctor -p onprem --json
```

Example copied from this command's help text.

Studio equivalent: Setup & credentials > Check again

Related: `pskit init`, `pskit studio`

Safety: callback for `pskit doctor` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-doctor`
