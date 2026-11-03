# pskit cluster scale

Purpose: Set the web replicas now (until the next deploy; keep it in options.cluster.replicas).

When to use:
- The command help says: Set the web replicas now (until the next deploy; keep it in options.cluster.replicas).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster scale NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--replicas` (int_range; required): (no help text)
- `--stack` (string): Deployment (default: this project's stage, pskit-<service>-<stage>).
- `-s/--stage` (string): Stage of this project (default: the configured stage).
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster scale NAME [OPTIONS]`.

Studio equivalent: Scaling cluster > Scale

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`

Safety: callback for `pskit cluster scale` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
