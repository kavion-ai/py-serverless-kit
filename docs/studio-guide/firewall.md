# Firewall panel in studio

Search terms: firewall, ports to open, ufw, security group, NSG, inbound rules, outbound rules, required ports, which ports, cluster ports, load balancer ports

The **Firewall** panel lists, for each on-prem server pskit set up, the ports it must allow, with ready-made `ufw`
commands. It is not a sidebar page; it appears in three places:

- **Deploy** page → **Firewall** section ("the ports each server must allow"), when the target provider is `onprem`;
- **Scaling cluster** page → **Firewall: <cluster>** card (the cluster's servers);
- **Load balancers** page → **Firewall: <name>** card (the load balancer's server).

The rules themselves and how to apply them in a cloud firewall are in [On-prem firewall](../onprem/firewall.md).

## Read the firewall panel in studio

The studio Firewall panel has one block per server (name and address).

1. Open the panel (Deploy → **Firewall**, or a cluster or load balancer page). **Refresh** reads the rules again; the
   Deploy page refreshes it after each deploy or remove.
2. Each server's table has the columns **Level**, **Direction**, **Port**, **From / to** and **Why**.
3. Levels:

   | Level | Meaning |
   |---|---|
   | **REQUIRED** | It does not work without this rule |
   | **NEEDED** | Needed for this feature |
   | **optional** | pskit falls back to an SSH tunnel |

4. Under the table, **With ufw on <server>:** shows the `ufw` commands; **copy** copies them.
5. A server with nothing to open says "No ports to open on this server." With nothing on premises yet, the panel says
   to deploy to a server, create a cluster or a load balancer first.

The deploy steps view on the Deploy page shows the same rules as its **Firewall** step after an on-prem deploy.

## Get the firewall rules from the terminal

`pskit firewall` prints the same rules as the studio Firewall panel:

```bash
pskit firewall
pskit firewall --server edge2
pskit firewall --json
```

## See also

- [On-prem firewall](../onprem/firewall.md)
- [Network map](network.md)
- [Deploy page](deploy.md), [Scaling cluster](cluster.md), [Load balancers](load-balancers.md)
- [On-prem networking](../onprem-network.md)
