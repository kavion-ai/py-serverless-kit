# pskit resources send

Purpose: Send a test message / object to a queue, bucket or topic.

When to use:
- The command help says: Send a test message / object to a queue, bucket or topic.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit resources send [KEY] [OPTIONS]
```

Arguments:
- `key` (string, optional)

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `-d/--data` (string): Payload JSON or @file.json (default: a sample).
- `--list` (flag; default off): How to test every resource: payload, commands, console steps.
- `--json` (flag; default off): Print JSON.

Examples:

```
pskit resources send --list
```

Example copied from this command's help text.

```
pskit resources send jobs -d '{"order_id": 1}'
```

Example copied from this command's help text.

```
pskit resources send uploads -d '{"key": "in/a.csv", "content": "a,b"}'
```

Example copied from this command's help text.

```
pskit resources send events -d '{"message": {"id": 1}, "attributes": {"type": "order"}}'
```

Example copied from this command's help text.

Studio equivalent: Resources > Test

Related: `pskit resources check`, `pskit resources clear`, `pskit resources data`, `pskit resources delete`, `pskit resources list`, `pskit resources onprem`, `pskit resources usage`

Safety: callback for `pskit resources send` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
