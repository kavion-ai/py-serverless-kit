## In studio
1. Open Network map and read the port list for each machine.

## In the terminal
1. Run:

```
pskit firewall
```

## In code

SSH from the admin machine is the first rule. Cluster, load balancer, and service sections add their own ports. pskit firewall prints those ports.

## 1. Always: the admin machine reaches every server over SSH | | From | To | Port

| Why | |---|---|---|---|---| | 🟥 | Admin machine | **every** saved server (function, cluster, load balancer, resource) | **TCP *22*** (the server's SSH port) | scripts, copying the release / image (`scp`), logs, tests, status | | 🟥 | every server, **outbound** | Internet **TCP 443 / 80** | — |

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
