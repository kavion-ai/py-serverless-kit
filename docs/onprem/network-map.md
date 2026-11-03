# On-prem network map

Search terms: network map, network diagram, topology, connections, inbound, outbound, servers used in, machines,
which server talks to which, ports between servers, studio network page, server usage

The on-prem network map shows every saved server of the project and the connections each one has to **accept**
(inbound) and **open** (outbound): deploys, function groups, clusters, load balancers and services. It is drawn from
the same rules as [the firewall rules](firewall.md), so the map and `pskit firewall` always agree.

## What the on-prem network map shows

The on-prem network map draws machines as boxes and connections as arrows from the side that connects to the side
that must accept.

| Box | Meaning |
|---|---|
| a saved server | name, address, and `×N` (the number of places it is used) or `unused` |
| a host (dotted) | an address pskit knows from a deploy or a service, but not a saved server; save it to manage it |
| **This machine (pskit)** | the admin machine running pskit and the studio (SSH, logs, tests) |
| **Users / clients** | your functions' callers |
| **Internet** | downloads and images |

| Line | Level |
|---|---|
| solid | required: it does not work without it |
| dashed | feature: needed for that feature |
| dotted | optional: pskit falls back to an SSH tunnel |

Each arrow is labelled with its ports; hover it for every port, protocol, level and reason.

## Open the network map in studio

The studio shows the on-prem network map on the **Network map** page.

1. Open **Network map** in the sidebar. The page reads the project's servers, deployments, clusters, load balancers
   and services.
2. Use the checkboxes **required**, **feature** and **optional** to show or hide each level, and
   **servers not used anywhere (N)** to show saved servers that nothing uses.
3. Click a machine. Its inbound arrows turn green ("inbound to the selected machine") and outbound arrows blue
   ("outbound from it"); other lines fade.
4. The side panel shows its address, **Inbound — accept** and **Outbound — open** tables (port, protocol, peer,
   level badge, reason), and **Used in** with links to the functions, clusters, load balancers or services.
5. Click **Refresh** after a deploy or a change. Click the empty canvas to clear the selection.

With no servers yet, the page says so: save a server under **Resources → Servers**, then deploy to it or create a
cluster, a load balancer or a service.

## Where each saved server is used

A saved server can be a deploy target, a function group, a cluster member, a cluster load balancer, a named load
balancer, a service or database host, or have installed software. The network map's **Used in** list and the
server's **Used in N places** button (in the **Servers** card) show each use.

From the terminal:

```bash
pskit resources onprem servers usage      # where each saved server is used
pskit firewall                            # the same connections as rules, per server
```

## Read a typical on-prem network map

A typical on-prem network map for one load balancer in front of a Swarm cluster looks like this (arrows point at the
side that accepts):

```text
Users / clients ──80──────────► lb1
This machine (pskit) ──22─────► lb1, edge1, edge2
lb1 ──8080────────────────────► edge1, edge2
edge2 ──2377, 7946, 4789, 8080─► edge1 (master)
edge1 ──7946, 4789────────────► edge2
edge1, edge2 ──6379───────────► cache1 (Redis)
```

Read it per machine: on `edge1` open 2377 / 7946 / 4789 / 8080 from `edge2`, 8080 from `lb1`, and 22 from your
machine. The exact `ufw` commands are in `pskit firewall --server edge1`.

## See also

* [Firewall rules: every port](firewall.md)
* [Load balancers](load-balancers.md), [Placement](placement.md), [Database scaling](database-scaling.md)
* [Scaling options compared](scaling/README.md)
* [Servers](servers.md)
