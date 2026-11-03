# pskit trigger

Purpose: Send a real test event to a deployed function.

When to use:
- The command help says: Send a real test event to a deployed function.
- How to test every function
- E.g. an SQS message

Usage:

```
pskit trigger [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `-f/--function` (string): Function to test (all with --list).
- `-e/--event` (int): Trigger number (0 = first; see --list).
- `--direct` (flag; default off): Invoke the function directly instead of through a trigger.
- `-d/--data` (string): Payload JSON or @file.json (default: a sample for the trigger).
- `--path` (string): HTTP path incl. query string (http triggers), e.g. /items/1?x=y.
- `--list` (flag; default off): Show how to test each trigger: payload, commands, console steps.
- `--json` (flag; default off): Print JSON.

Examples:

```
pskit trigger --list
```

how to test every function

```
pskit trigger -f worker -e 0 -d '{"order_id": 1}'
```

e.g. an SQS message

```
pskit trigger -f thumbnails -e 0 -d '{"key": "in/a.png", "content": "x"}'
```

Example copied from this command's help text.

```
pskit trigger -f api -e 0 --path '/items/1'
```

Example copied from this command's help text.

Studio equivalent: Test > Send to

Related: `pskit logs`, `pskit invoke`

Safety: callback for `pskit trigger` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-trigger`
