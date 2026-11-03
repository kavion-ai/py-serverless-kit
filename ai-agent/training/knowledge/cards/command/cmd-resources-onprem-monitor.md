# pskit resources onprem monitor

Purpose: Live CPU, memory, disk, connections and replica lag of a service.

When to use:
- The command help says: Live CPU, memory, disk, connections and replica lag of a service.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources onprem monitor KEY [OPTIONS]
```

Arguments:
- `key` (string, required)

Options:
- `--watch` (int; default 0): Repeat every N seconds until Ctrl+C.
- `--json` (flag; default off): Print JSON.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit resources onprem monitor KEY [OPTIONS]`.

Studio equivalent: none

Related: `pskit resources onprem alerts`, `pskit resources onprem backup`, `pskit resources onprem catalog`, `pskit resources onprem console`, `pskit resources onprem create`, `pskit resources onprem gui`, `pskit resources onprem list`, `pskit resources onprem logs`

Safety: callback for `pskit resources onprem monitor` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
