# pskit cluster

Purpose: Scale on-prem functions over several servers (Swarm, Kubernetes, Nomad).

When to use:
- The command help says: Scale on-prem functions over several servers (Swarm, Kubernetes, Nomad).
- Also while functions are running
- Master only as a backup; joined servers take the requests

Usage:

```
pskit cluster COMMAND
```

Options:
- (no options)

Examples:

```
pskit cluster create prod --orchestrator swarm --master edge1
```

Example copied from this command's help text.

```
pskit cluster join prod edge2
```

also while functions are running

```
pskit cluster set prod --no-master-serves
```

master only as a backup; joined servers take the requests

```
pskit cluster status prod
```

CPU / memory / disk of every server, replicas, full?

Studio equivalent: none

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster create`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`

Safety: callback for `pskit cluster` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`, `docs/cli.md#pskit-cluster`
