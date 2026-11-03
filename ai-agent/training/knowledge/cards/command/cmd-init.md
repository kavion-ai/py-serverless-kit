# pskit init

Purpose: Scaffold a new project (pskit.yml, handlers, tests).

When to use:
- The command help says: Scaffold a new project (pskit.yml, handlers, tests).
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit init [DIRECTORY] [OPTIONS]
```

Arguments:
- `directory` (path, optional)

Options:
- `--name` (string): Service name (default: directory name).
- `-p/--provider` (choice; choices aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, onprem; default aws): (no help text)
- `-t/--template` (choice; choices http, events, workflow, full; default http): (no help text)
- `-l/--language` (choice; choices python, javascript, typescript): Handler language (default: python, or javascript with a nodejs --runtime).
- `--runtime` (choice; choices python3.9, python3.10, python3.11, python3.12, python3.13, python3.14, nodejs18, nodejs20, nodejs22, nodejs24): Runtime written to pskit.yml (default python3.12 / nodejs20).
- `--typescript/--ts` (flag; default off): Shorthand for --language typescript.
- `--force` (flag; default off): Overwrite existing files.

Examples:

```
pskit init my-api --provider aws
```

Example copied from this command's help text.

```
pskit init . -p gcp -t workflow
```

Example copied from this command's help text.

```
pskit init svc -p onprem -t full --name orders
```

Example copied from this command's help text.

```
pskit init api -p aws --typescript
```

Node.js 20 + TypeScript

Studio equivalent: none

Related: `pskit studio`, `pskit doctor`

Safety: callback for `pskit init` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-init-directory`
