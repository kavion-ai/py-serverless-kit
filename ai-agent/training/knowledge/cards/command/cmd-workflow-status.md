# pskit workflow status

Purpose: Show one execution: status, current state, output or error.

When to use:
- The command help says: Show one execution: status, current state, output or error.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit workflow status EXECUTION_ID [OPTIONS]
```

Arguments:
- `execution_id` (string, required)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `-w/--workflow` (string): Workflow name (helps AWS/GCP resolve the id).
- `--history` (flag; default off): Print the state history.
- `--watch` (flag; default off): Poll until the execution finishes.
- `--json` (flag; default off): (no help text)

Examples:

```
pskit workflow status <execution-id>
```

Example copied from this command's help text.

```
pskit workflow status <execution-id> -w order --history --watch
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit workflow cancel`, `pskit workflow executions`, `pskit workflow run`, `pskit workflow show`, `pskit workflow start`

Safety: callback for `pskit workflow status` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
