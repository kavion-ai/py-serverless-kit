# pskit workflow executions

Purpose: List executions of the deployed workflows (newest first).

When to use:
- The command help says: List executions of the deployed workflows (newest first).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit workflow executions [NAME] [OPTIONS]
```

Arguments:
- `name` (string, optional)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `--status` (string): RUNNING, SUCCEEDED, FAILED, TIMED_OUT, CANCELLED or ABORTED.
- `-n/--limit` (int; default 20): (no help text)
- `--offset` (int; default 0): Skip this many (on-prem).
- `--token` (string): Next-page token printed by a previous call (AWS/GCP).
- `--json` (flag; default off): (no help text)

Examples:

```
pskit workflow executions
```

Example copied from this command's help text.

```
pskit workflow executions order --status FAILED -n 50
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit workflow cancel`, `pskit workflow run`, `pskit workflow show`, `pskit workflow start`, `pskit workflow status`

Safety: callback for `pskit workflow executions` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
