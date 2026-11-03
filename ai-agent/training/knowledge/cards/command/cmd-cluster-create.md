# pskit cluster create

Purpose: Install the orchestrator on MASTER and save cluster NAME.

When to use:
- The command help says: Install the orchestrator on MASTER and save cluster NAME.
- The command is defined in `src/py_serverless_kit/cli/main.py`.

Usage:

```
pskit cluster create NAME [OPTIONS]
```

Arguments:
- `name` (string, required)

Options:
- `--orchestrator/-o` (choice; choices swarm, kubernetes, nomad; required): (no help text)
- `--master` (string; required): Saved server that runs the control plane and the main replica.
- `--advertise` (string): The master's address other servers use (default: its host).
- `--nomad-version` (string): Nomad release to install (default: the tested one).
- `--master-serves/--no-master-serves` (flag; default off): Send requests to the master too, next to the joined servers. Off: the master is only a backup, used while every other server is down. Default: off on Nomad, on on Swarm and k3s.
- `-c/--config` (string): Config file (default: pskit.yml).

Examples:
- No example is written in this command's help. The synopsis is `pskit cluster create NAME [OPTIONS]`.

Studio equivalent: Scaling cluster > + New cluster

Related: `pskit cluster alerts`, `pskit cluster balancer`, `pskit cluster check`, `pskit cluster join`, `pskit cluster leave`, `pskit cluster list`, `pskit cluster remove`, `pskit cluster requests`

Safety: callback for `pskit cluster create` in `src/py_serverless_kit/cli/main.py`.
- This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. That only describes this function. The help text says what the command does.

Sources: `src/py_serverless_kit/cli/main.py`
