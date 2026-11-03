# pskit lb

Purpose: Shared on-prem load balancers: one URL, a path per project or cluster.

When to use:
- The command help says: Shared on-prem load balancers: one URL, a path per project or cluster.
- The 6 algorithms, static / dynamic, pros and cons
- Every deployment on prod: http://<lb1>/<service>/

Usage:

```
pskit lb COMMAND
```

Options:
- (no options)

Examples:

```
pskit lb algorithms
```

the 6 algorithms, static / dynamic, pros and cons

```
pskit lb create edge --server lb1 --algorithm least_time
```

Example copied from this command's help text.

```
pskit lb attach edge --cluster prod
```

every deployment on prod: http://<lb1>/<service>/

```
pskit lb status edge
```

its routes (all projects), health, server use

Studio equivalent: none

Related: `pskit lb algorithms`, `pskit lb attach`, `pskit lb create`, `pskit lb detach`, `pskit lb forget`, `pskit lb list`, `pskit lb logs`, `pskit lb remove`

Safety: callback for `pskit lb` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
