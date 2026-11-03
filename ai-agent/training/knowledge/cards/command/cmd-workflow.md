# pskit workflow

Purpose: Run or inspect workflows (state machines).

When to use:
- The command help says: Run or inspect workflows (state machines).
- Local, embedded engine
- The deployed workflow

Usage:

```
pskit workflow COMMAND
```

Options:
- (no options)

Examples:

```
pskit workflow run order -i '{"id": 1}' --history
```

local, embedded engine

```
pskit workflow show order --format asl
```

Example copied from this command's help text.

```
pskit workflow start order -i @input.json --wait
```

the deployed workflow

```
pskit workflow executions order --status FAILED
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit workflow cancel`, `pskit workflow executions`, `pskit workflow run`, `pskit workflow show`, `pskit workflow start`, `pskit workflow status`

Safety: callback for `pskit workflow` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-workflow`
