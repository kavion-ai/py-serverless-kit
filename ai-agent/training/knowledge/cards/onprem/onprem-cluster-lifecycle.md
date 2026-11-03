## Commands

| Command | |
|---|---|
| `pskit cluster create NAME -o swarm\|kubernetes\|nomad --master SERVER [--advertise IP] [--[no-]master-serves]` | install on the master and save |
| `pskit cluster join NAME SERVER [--advertise IP]` | add a server (installs, joins, copies images) |
| `pskit cluster set NAME --master-serves\|--no-master-serves` | send requests to the master too, or keep it as a backup only |
| `pskit cluster leave NAME SERVER` | drain and remove a server |
| `pskit cluster status NAME [--json]` | servers, replicas, full or not |
| `pskit cluster check NAME [--no-alert]` | status once and the alert when full (exit 3 when full) |
| `pskit cluster watch NAME [--interval 60]` | check until Ctrl+C |
| `pskit cluster alerts NAME [--function F] [--stage S] [--webhook URL] [--cooldown M] [--cpu/--memory/--disk %] [--test]` | alert settings |
| `pskit cluster scale NAME --replicas N [--stack S]` | web replicas now (until the next deploy) |
| `pskit cluster requests NAME [--follow] [--stack S]` | recent requests, and each server's URL with its share of HTTP |
| `pskit cluster balancer set NAME SERVER [--port 80] [--address IP]` | nginx on a server outside the cluster: one URL for all of it |
| `pskit cluster balancer sync NAME` / `logs NAME [-n 100]` / `remove NAME` | rewrite its config now / its access log / stop it |
| `pskit cluster list` / `pskit cluster remove NAME` | list / forget a cluster |
| `pskit cluster remove NAME --uninstall [--delete-data]` | uninstall the cluster from the master and every server, then forget it |
| `pskit deploy --cluster NAME` / `pskit deploy --server NAME` | deploy the functions to the cluster / to one server |
| `pskit resources onprem create KEY --service S --cluster NAME [--node SERVER]` | a resource on a server of the cluster |
