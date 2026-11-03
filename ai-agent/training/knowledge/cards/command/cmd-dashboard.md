# pskit dashboard

Purpose: Generate (and optionally serve) the deployment dashboard.

When to use:
- The command help says: Generate (and optionally serve) the deployment dashboard.
- Live logs and workflow executions

Usage:

```
pskit dashboard [OPTIONS]
```

Options:
- `-d/--dir` (path; default .): Project root.
- `-o/--output` (path): Write HTML here.
- `--serve` (flag; default off): Serve the dashboard with live logs and workflow executions.
- `--host` (string; default 127.0.0.1): Bind address for --serve.
- `--port` (int; default 8765): (no help text)
- `--open` (flag; default off): Open in the browser.

Examples:

```
pskit dashboard --open
```

Example copied from this command's help text.

```
pskit dashboard --serve --open
```

live logs and workflow executions

```
pskit dashboard -o site/index.html
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit info`, `pskit studio`

Safety: callback for `pskit dashboard` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-dashboard`
