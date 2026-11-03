# Network map page in studio

Search terms: network map, connections, inbound, outbound, ports, machines, topology diagram, firewall rules, servers not used, which server talks to which, required ports

The **Network map** page draws every on-prem server and the connections it has to accept (inbound) and open
(outbound) for this project: deploys, function groups, clusters, load balancers and services. Sidebar: **Network map**
(⌘). It reads the project's settings; it changes nothing. Background: [On-prem network map](../onprem/network-map.md)
and [On-prem networking](../onprem-network.md).

## Read the network map in studio

The studio network map is a diagram of machines and arrows.

1. Open **Network map**. If nothing is set up yet, it says to save a server under Resources → Servers, then deploy to
   it, create a cluster, a load balancer or a service.
2. Nodes are your saved servers, other addresses pskit knows from a deploy or a service, and the special nodes **This
   machine (pskit)**, **Users / clients** and **Internet**.
3. Line styles show the level of each connection. Tick or untick the levels in the toolbar:
   - **required**: it does not work without it;
   - **feature**: needed for that feature;
   - **optional**: pskit falls back to an SSH tunnel.
4. **servers not used anywhere (N)** also shows saved servers nothing in the project names.
5. Click a machine on the map (or in the **Machines** list). Arrows into it turn green (inbound to the selected
   machine) and arrows out of it blue (outbound from it). Click empty space to clear.
6. **Refresh** reloads the map.

## See the ports one machine must allow

The details card of a selected machine lists its connections in two tables:

- **Inbound — accept**: the port, the level badge and where it comes **from**, and why.
- **Outbound — open**: the port, level and where it goes **to**.

For saved servers (and known addresses), **Used in** lists the functions that run there (links to their pages) and
every place that names it: deploy target, function group, cluster, load balancer or service. An address that is not a
saved server says "Not a saved server: an address pskit knows from a deploy or a service. Save it to manage it here."

The ready-made `ufw` rules for each server are on the [Firewall panel](firewall.md). From the terminal:

```bash
pskit firewall                    # every server
pskit firewall --server edge2     # one server (name or address)
pskit firewall --json
pskit resources onprem servers usage
```

## See also

- [Firewall panel](firewall.md)
- [On-prem network map](../onprem/network-map.md) and [On-prem firewall](../onprem/firewall.md)
- [Servers panel: where a server is used](servers.md#see-where-a-server-is-used-edit-it-or-forget-it)
- [Placement](placement.md)
