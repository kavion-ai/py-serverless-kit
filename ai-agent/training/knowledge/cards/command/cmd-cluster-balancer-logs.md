# pskit cluster balancer logs

Purpose: The load balancer's recent requests (upstream= is the server that answered) and errors.

When to use:
- The command help says: The load balancer's recent requests (upstream= is the server that answered) and errors.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster balancer logs NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `-n/--lines` (int_range; default 100): (no help text)
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster balancer logs NAME [OPTIONS]`.

Studio equivalent: none

Related: `pskit cluster balancer remove`, `pskit cluster balancer set`, `pskit cluster balancer sync`

Safety: callback for `pskit cluster balancer logs` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`

Help text from the command (click docstring, with the `\b` marker removed):

The load balancer's recent requests (upstream= is the server that answered) and errors.
