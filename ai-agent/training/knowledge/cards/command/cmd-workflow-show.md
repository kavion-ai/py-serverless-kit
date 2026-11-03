# pskit workflow show

Purpose: Print the compiled workflow definition.

When to use:
- The command help says: Print the compiled workflow definition.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit workflow show NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `--format` (choice; choices auto, asl, gcp, json; default auto): (no help text)

Examples:

```
pskit workflow show order
```

Example copied from this command's help text.

```
pskit workflow show order --format gcp
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit workflow cancel`, `pskit workflow executions`, `pskit workflow run`, `pskit workflow start`, `pskit workflow status`

Safety: callback for `pskit workflow show` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
