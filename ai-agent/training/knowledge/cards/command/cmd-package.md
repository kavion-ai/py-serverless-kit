# pskit package

Purpose: Build the artifact and Terraform (no cloud calls).

When to use:
- The command help says: Build the artifact and Terraform (no cloud calls).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit package [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `--skip-deps` (flag; default off): Do not pip-install requirements into the bundle.

Examples:

```
pskit package
```

Example copied from this command's help text.

```
pskit package -p gcp -s prod --skip-deps
```

Example copied from this command's help text.

Studio equivalent: Deploy > Package

Related: `pskit plan`, `pskit deploy`, `pskit remove`

Safety: callback for `pskit package` in `src/py_serverless_kit/cli/main.py`.
- The function calls `.package(`.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-package`
