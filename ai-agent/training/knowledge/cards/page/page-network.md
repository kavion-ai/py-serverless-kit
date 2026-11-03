# Studio: Network map

How to open: Left navigation label Network map.

What it is for: The page subtitle says it shows every on-prem server and the connections it has to accept (inbound) and open (outbound) for this project: deploys, function groups, clusters, load balancers and services. Click a machine for its details.

What you see: A Refresh button. A toolbar of level checkboxes plus "servers not used anywhere". The legend says "inbound to the selected machine" and "outbound from it". The canvas aria-label is "Connections between the project's machines". When a machine is selected, tables are titled "Inbound — accept" and "Outbound — open". An "All machines" control clears the selection. The empty copy is: "No servers and no connections yet. Save a server under Resources → Servers, then deploy to it, create a cluster, a load balancer or a service there; this map follows."

What you can do: Refresh reloads the map. Select a machine to list inbound rules, outbound rules, and where that server is used. The page does not open ports. It describes the connections the project already implies. Changing a deploy target, a cluster, a load balancer or a service changes what the next refresh shows.

Tips and limits: The empty state points at Resources, then Servers, to save a machine first. There is no deploy button on this page. The written guide for the same picture is docs/onprem-network.md. Firewall edits, when you want to change what a host allows, are on Deploy, section Firewall, and the command `pskit firewall`.

Sources: `dashboard-ui/src/studio/views/Network.tsx`, `docs/onprem-network.md`
