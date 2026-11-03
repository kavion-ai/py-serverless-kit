# pskit

Purpose: py-serverless-kit: write Python functions once, deploy them to any cloud.

When to use:
- The command help says: py-serverless-kit: write Python functions once, deploy them to any cloud.
- Check terraform, CLIs and credentials
- Run locally

Usage:

```
pskit COMMAND
```

Options:
- `--version` (flag; default off): Show the version and exit.

Examples:

```
pskit doctor
```

check terraform, CLIs and credentials

```
pskit init my-api --provider aws
```

Example copied from this command's help text.

```
pskit dev
```

run locally

```
pskit deploy --stage dev
```

terraform apply

Studio equivalent: none

Related: `pskit client`, `pskit cluster`, `pskit dashboard`, `pskit deploy`, `pskit dev`, `pskit doctor`, `pskit firewall`, `pskit function`

Safety: callback for `pskit` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-resources-onprem`

Help text from the command (click docstring, with the `\b` marker removed): py-serverless-kit: write Python functions once, deploy them to any cloud.

Typical flow:
  pskit doctor                   # check terraform, CLIs and credentials
  pskit init my-api --provider aws
  pskit dev                      # run locally
  pskit deploy --stage dev       # terraform apply
  pskit dashboard --open         # see everything you deployed

Subcommands: `pskit client`, `pskit cluster`, `pskit dashboard`, `pskit deploy`, `pskit dev`, `pskit doctor`, `pskit firewall`, `pskit function`, `pskit info`, `pskit init`, `pskit invoke`, `pskit lb`, `pskit logs`, `pskit package`, `pskit plan`, `pskit providers`, `pskit remove`, `pskit resources`, `pskit settings`, `pskit studio`, `pskit tf`, `pskit trigger`, `pskit validate`, `pskit workflow`.
