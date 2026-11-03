# pskit function split

Purpose: Move functions out of a shared code file into functions/<name>/handler.py with their own requirements.txt.

When to use:
- The command help says: Move functions out of a shared code file into functions/<name>/handler.py with their own requirements.txt.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit function split [NAMES] [OPTIONS]
```

Arguments:
- `names` (string, optional)

Options:
- `--all` (flag; default off): Every function that shares a code file with another.
- `--dry-run` (flag; default off): Only show what would move.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:

```
pskit function split get-item
```

Example copied from this command's help text.

```
pskit function split --all --dry-run
```

Example copied from this command's help text.

Studio equivalent: Functions > Own folder

Related: none

Safety: callback for `pskit function split` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
