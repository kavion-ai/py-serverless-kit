# pskit dev

Purpose: Run a local server with hot reload.

When to use:
- The command help says: Run a local server with hot reload.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit dev [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `--host` (string; default 127.0.0.1): (no help text)
- `--port` (int; default 3000): (no help text)
- `--env-file` (string; default .env): (no help text)

Examples:

```
pskit dev
```

Example copied from this command's help text.

```
pskit dev --port 8080 --env-file .env.local
```

Example copied from this command's help text.

Studio equivalent: none

Related: `pskit invoke`, `pskit validate`

Safety: callback for `pskit dev` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-dev`
