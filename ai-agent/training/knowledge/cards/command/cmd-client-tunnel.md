# pskit client tunnel

Purpose: Forward the host's port here over SSH (firewalled host port).

When to use:
- The command help says: Forward the host's port here over SSH (firewalled host port).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit client tunnel [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `--local-port` (int): Port on this machine (default: the host's port).

Examples:
- No example is written in this command's help. The synopsis is `pskit client tunnel [OPTIONS]`.

Studio equivalent: none

Related: `pskit client info`, `pskit client install-node`

Safety: callback for `pskit client tunnel` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
