# pskit logs

Purpose: Show, list or delete logs of a deployment.

When to use:
- The command help says: Show, list or delete logs of a deployment.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit logs [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `-f/--follow` (flag; default off): Keep printing new entries.
- `-n/--lines` (int; default 100): How many recent entries to show first.
- `--function` (string): Only this function.
- `--level` (string): Minimum level: DEBUG, INFO, WARNING, ERROR.
- `--source` (choice; choices function, host, stdout, stderr, invocation): Only one kind of entry.
- `-q/--grep` (string): Only entries containing this text.
- `--json` (flag; default off): One JSON object per line.
- `--streams` (flag; default off): List log streams (per function / container) instead.
- `--delete` (string; repeatable): Delete a log stream (repeatable).
- `--delete-all` (flag; default off): Delete every log stream (of --function, or of all functions).
- `-y/--yes` (flag; default off): Don't ask for confirmation before deleting.

Examples:
- No example is written in this command's help. The synopsis is `pskit logs [OPTIONS]`.

Studio equivalent: Logs > Stored logs

Related: `pskit trigger`, `pskit dashboard`

Safety: callback for `pskit logs` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Prompt text starts: Delete {what} of {where}? This cannot be undone
- Option `-y/--yes`: Don't ask for confirmation before deleting.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-logs`
