# pskit workflow start

Purpose: Start a deployed workflow and print its execution id.

When to use:
- The command help says: Start a deployed workflow and print its execution id.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit workflow start NAME [OPTIONS]
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
- `-i/--input` (string): JSON input or @file.json.
- `--wait` (flag; default off): Wait for the result (on-prem; native engines return at once).
- `--json` (flag; default off): (no help text)

Examples:

```
pskit workflow start order -i '{"id": 1}'
```

Example copied from this command's help text.

```
pskit workflow start order -i @input.json --wait --json
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit workflow cancel`, `pskit workflow executions`, `pskit workflow run`, `pskit workflow show`, `pskit workflow status`

Safety: callback for `pskit workflow start` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
