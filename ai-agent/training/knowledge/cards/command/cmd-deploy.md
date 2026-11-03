# pskit deploy

Purpose: Package and deploy with terraform apply.

When to use:
- The command help says: Package and deploy with terraform apply.
- Review the plan first

Usage:

```
pskit deploy [OPTIONS]
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
- `--confirm` (flag; default off): Show the plan and apply it (instead of -auto-approve).
- `--upgrade` (flag; default off): terraform init -upgrade (update provider plugins).
- `--no-dashboard` (flag; default off): Do not regenerate the dashboard.

Examples:

```
pskit deploy
```

Example copied from this command's help text.

```
pskit deploy -s prod --confirm
```

review the plan first

```
pskit deploy -p onprem --skip-deps
```

Example copied from this command's help text.

Studio equivalent: Deploy > Deploy

Related: `pskit package`, `pskit plan`, `pskit info`, `pskit remove`, `pskit tf`

Safety: callback for `pskit deploy` in `src/py_serverless_kit/cli/main.py`.
- The function calls `.deploy(`. The command help describes terraform apply, so this changes the selected stage.
- Option `--confirm`: Show the plan and apply it (instead of -auto-approve).

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-deploy`
