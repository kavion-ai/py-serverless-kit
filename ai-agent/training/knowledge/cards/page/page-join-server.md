# Studio: Join server

How to open: Scaling cluster > + Join server

The drawer opens only when a cluster is selected. The title is "Join a server to <cluster name>".

What it is for: Add one saved server to a cluster that already exists. The drawer text says pskit installs the cluster's orchestrator on the server over SSH, joins it to the master, and copies the deployed function images to it. Running functions keep running. New replicas can start there right away.

What you see: Server, required. The picker excludes servers that are already nodes of any cluster and servers that are a cluster load balancer (`inCluster` in Cluster.tsx). The same picker can save a new server. Cluster address is optional. The help says it is this server's IP in the cluster network, and the default is its SSH host. This card does not copy the address placeholder from the source file.

What you can do: Join is disabled until a server is chosen. It starts the studio job action join with that server and the optional address. The studio server calls `join_server` for that action. The CLI command that calls the same function is `pskit cluster join`. Removing a joined server is a different control. Its confirm title is "Remove <server> from <cluster>?" and the confirm label is "Remove server". The body says replicas move to the other servers first, then its agent stops, and the saved server is kept. That job action is leave, which calls `leave_server`. The master row does not use leave. Its Remove uninstalls the orchestrator from the master and every joined server.

Tips and limits: Join does not change provider.options.cluster. The page subtitle says you can join servers while functions run. A server that is already a member of this or another cluster is not offered. Refresh loads cluster status. That status includes each server's CPU, memory, and disk.

Sources: `dashboard-ui/src/studio/views/Cluster.tsx`, `src/py_serverless_kit/studio/server.py`, `src/py_serverless_kit/cli/main.py`
