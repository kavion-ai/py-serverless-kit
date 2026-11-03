# pskit studio

Purpose: Edit the project in the browser (writes pskit.yml).

When to use:
- The command help says: Edit the project in the browser (writes pskit.yml).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit studio [OPTIONS]
```

Options:
- `-d/--dir` (path; default .): Project root.
- `--host` (string; default 127.0.0.1): Bind address.
- `--port` (int; default 8770): (no help text)
- `--open` (flag; default off): Open in the browser.
- `--vscode-image` (string): code-server image for the full VS Code view.

Examples:

```
pskit studio --open
```

Example copied from this command's help text.

```
pskit studio -d path/to/project --port 8800
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit init`, `pskit doctor`

Safety: callback for `pskit studio` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-studio`
