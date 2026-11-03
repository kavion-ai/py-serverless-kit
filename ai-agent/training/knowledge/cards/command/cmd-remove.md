# pskit remove

Purpose: Destroy every resource of this service/stage.

When to use:
- The command help says: Destroy every resource of this service/stage.
- Keep buckets, queues, topics

Usage:

```
pskit remove [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `-y/--yes` (flag; default off): Do not ask for confirmation.
- `--keep-resources` (flag; default off): Keep managed buckets, queues and topics (and their data); destroy only functions and triggers.

Examples:

```
pskit remove -s dev
```

Example copied from this command's help text.

```
pskit remove -s dev --yes
```

Example copied from this command's help text.

```
pskit remove -s dev --keep-resources
```

keep buckets, queues, topics

Studio equivalent: Deploy > Remove

Related: `pskit deploy`, `pskit plan`

Safety: callback for `pskit remove` in `src/py_serverless_kit/cli/main.py`.
- The function calls `click.confirm`.
- Prompt text starts: Destroy {what} of '{cfg.service}' stage '{cfg.provider.stage}' on {project.provider.display_name}?
- The function calls `.remove(`.
- Option `-y/--yes`: Do not ask for confirmation.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-remove`
