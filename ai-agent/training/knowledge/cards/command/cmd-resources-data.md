# pskit resources data

Purpose: Browse what an on-prem queue, topic or bucket holds (paginated).

When to use:
- The command help says: Browse what an on-prem queue, topic or bucket holds (paginated).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources data KEY [OPTIONS]
```

Arguments:
- `key` (string, required)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `--offset` (int; default 0): Skip this many items.
- `-n/--limit` (int; default 20): Items per page (max 500).
- `--prefix` (string): Buckets: only keys below this prefix.
- `--json` (flag; default off): Print JSON.

Examples:

```
pskit resources data jobs
```

Example copied from this command's help text.

```
pskit resources data jobs --offset 20 -n 20
```

Example copied from this command's help text.

```
pskit resources data uploads --prefix in/
```

Example copied from this command's help text.

Studio equivalent: Resources > Data

Related: `pskit resources check`, `pskit resources clear`, `pskit resources delete`, `pskit resources list`, `pskit resources onprem`, `pskit resources send`, `pskit resources usage`

Safety: callback for `pskit resources data` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
