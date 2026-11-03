# pskit resources onprem backup

Purpose: Dump a service's data to .pskit/backups.

When to use:
- The command help says: Dump a service's data to .pskit/backups.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem backup KEY [OPTIONS]
```

Arguments:
- `key` (string, required)

Options:
- `-o/--output` (string): File to write (default: .pskit/backups/<key>-<time>.<ext>).
- `-d/--dir` (path): Folder to write <key>-<time>.<ext> into (created when missing).
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem backup KEY [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`, `pskit resources onprem monitor`

Safety: callback for `pskit resources onprem backup` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
