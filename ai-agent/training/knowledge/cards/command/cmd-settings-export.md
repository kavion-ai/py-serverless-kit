# pskit settings export

Purpose: Write every local setting and secret of this project to one encrypted file.

When to use:
- The command help says: Write every local setting and secret of this project to one encrypted file.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit settings export [OPTIONS]
```

Options:
- `-o/--output` (string): File to write (default: <service>.pskit-settings).
- `--with-config` (flag; default off): Also include pskit.yml (the functions, resources and providers).
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit settings export [OPTIONS]`.

Studio equivalent: Setup & credentials > Export settings

Related: `pskit settings import`

Safety: callback for `pskit settings export` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

Write every local setting and secret of this project to one encrypted file.
