# pskit plan

Purpose: Show the terraform plan (what would change).

When to use:
- The command help says: Show the terraform plan (what would change).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit plan [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `--skip-deps` (flag; default off): (no help text)
- `--destroy` (flag; default off): Plan a destroy instead.

Examples:

```
pskit plan -s dev
```

Example copied from this command's help text.

```
pskit plan --destroy
```

Example copied from this command's help text.

Studio equivalent: Deploy > Plan

Related: `pskit package`, `pskit deploy`, `pskit tf`

Safety: callback for `pskit plan` in `src/py_serverless_kit/cli/main.py`.
- The function calls `.plan(`. The command help describes a terraform plan.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-plan`
