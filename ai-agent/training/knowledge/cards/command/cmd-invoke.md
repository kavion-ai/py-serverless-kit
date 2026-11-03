# pskit invoke

Purpose: Invoke a function locally with a synthetic event.

When to use:
- The command help says: Invoke a function locally with a synthetic event.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit invoke [OPTIONS]
```

Options:
- `-c/--config` (string): Config file (default: pskit.yml).
- `-p/--provider` (string): Override provider.name (aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem, or a plug-in).
- `-s/--stage` (string): Stage, e.g. dev / staging / prod.
- `-r/--region` (string): Override provider.region.
- `--server` (string): On premises: use this saved SSH server (pskit resources onprem servers list); 'local' for this machine. Default: the server the stage was last deployed to.
- `--cluster` (string): On premises: run the functions on this scaling cluster (pskit cluster list) instead of one server. Default: options.cluster, else where the stage was last deployed.
- `-v/--verbose` (flag; default off): Show tracebacks on errors.
- `-f/--function` (string; required): Function name from the config.
- `-t/--type` (choice; choices http, schedule, queue, storage, topic, invoke, workflow, smtp): Event type (default: the function's first event, or invoke).
- `-d/--data` (string): JSON payload or @file.json.
- `--method` (string): HTTP method (http events).
- `--path` (string): HTTP path incl. query string (http events).
- `-H/--header` (string; repeatable): HTTP header 'Name: value' (repeatable).
- `--env-file` (string; default .env): (no help text)

Examples:

```
pskit invoke -f hello
```

Example copied from this command's help text.

```
pskit invoke -f hello -t http --method POST --path "/hello?x=1" -d '{"name": "Ada"}'
```

Example copied from this command's help text.

```
pskit invoke -f worker -t queue -d @message.json
```

Example copied from this command's help text.

Studio equivalent: Test > Run locally

Related: `pskit dev`, `pskit validate`

Safety: callback for `pskit invoke` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-invoke`
