# pskit resources

Purpose: List or delete the buckets, queues and topics pskit created.

When to use:
- The command help says: List or delete the buckets, queues and topics pskit created.
- After `pskit remove --keep-resources`

Usage:

```
pskit resources COMMAND
```

Options:
- (no options)

Examples:

```
pskit resources list -s dev
```

Example copied from this command's help text.

```
pskit resources delete aws_s3_bucket.b_uploads -s dev
```

Example copied from this command's help text.

```
pskit resources delete --all-kept -s dev
```

after `pskit remove --keep-resources`

Studio equivalent: none

Related: `pskit resources check`, `pskit resources clear`, `pskit resources data`, `pskit resources delete`, `pskit resources list`, `pskit resources onprem`, `pskit resources send`, `pskit resources usage`

Safety: callback for `pskit resources` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-resources-onprem`
