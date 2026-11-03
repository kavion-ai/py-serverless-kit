## In studio
1. Use the server row Remove server action.

## In the terminal
1. Run:

```
pskit cluster leave prod app-1
```

## In code

leave drains the server so replicas move to the others. Removing the cluster itself is pskit cluster remove, which asks for confirmation.

## Commands | Command | | |---|---| | `pskit cluster create NAME -o

swarm\|kubernetes\|nomad --master SERVER [--advertise IP] [--[no-]master-serves]` | install on the master and save | | `pskit cluster join NAME SERVER [--advertise IP]` | add a server (installs, joins, copies images) | | `pskit cluster set NAME --master-serves\|--no-master-serves` | send requests to the master too, or keep it as a backup only | | `pskit cluster leave NAME Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
