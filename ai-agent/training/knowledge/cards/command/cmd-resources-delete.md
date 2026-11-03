# pskit resources delete

Purpose: Delete buckets, queues or topics by address.

When to use:
- The command help says: Delete buckets, queues or topics by address.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources delete [ADDRESSES] [OPTIONS]
```

Arguments:
- `addresses` (string, optional)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `--all-kept` (flag; default off): Delete every resource kept by `pskit remove --keep-resources`.
- `-y/--yes` (flag; default off): Do not ask for confirmation.

Examples:
- No example is written in this command's help. The synopsis is `pskit resources delete [ADDRESSES] [OPTIONS]`.

Studio equivalent: Resources > Delete

Related: `pskit resources check`, `pskit resources clear`, `pskit resources data`, `pskit resources list`, `pskit resources onprem`, `pskit resources send`, `pskit resources usage`

Safety: callback for `pskit resources delete` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Prompt text starts: Permanently delete {len(targets)} resource(s) and their data: {', '.join(targets)}?
- Option `-y/--yes`: Do not ask for confirmation.

Sources: `src/py_serverless_kit/cli/main.py`
