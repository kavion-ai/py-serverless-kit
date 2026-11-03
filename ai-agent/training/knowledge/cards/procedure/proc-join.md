## In studio
1. Open this path:
Scaling cluster > + Join server

## In the terminal
1. Run:

```
pskit cluster join prod app-1
```

## In code

Join adds a saved server to a cluster that already exists. The commands section of the cluster doc lists join next to create, scale, leave, and remove.

## Commands | Command | | |---|---| | `pskit cluster create NAME -o

swarm\|kubernetes\|nomad --master SERVER [--advertise IP] [--[no-]master-serves]` | install on the master and save | | `pskit cluster join NAME SERVER [--advertise IP]` | add a server (installs, joins, copies images) | | `pskit cluster set NAME --master-serves\|--no-master-serves` | send requests to the master too, or keep it as a backup only | | `pskit cluster leave NAME Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
