# pskit tf

Purpose: Run any terraform command in the generated workspace.

When to use:
- The command help says: Run any terraform command in the generated workspace.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit tf [ARGS] [OPTIONS]
```

Arguments:
- `args` (unprocessed, optional)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.

Examples:

```
pskit tf -- state list
```

Example copied from this command's help text.

```
pskit tf -s prod -- output -json
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit plan`, `pskit deploy`

Safety: callback for `pskit tf` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-tf----args`
